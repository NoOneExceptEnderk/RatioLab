# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Headless, workspace-confined RatioLab operations; standard library only.

This module deliberately imports no UI, GTK, preferences or network helpers.
Project handles are explicit process-lifetime capabilities, never file paths.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from math import isfinite
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import stat
import tempfile
from threading import Event, RLock
from time import monotonic
import uuid

from geometry import FAMILIES, VARIANTS, DOUBLE_STYLES, HARMONIC_OUTPUTS, INTEGER, get_specs, generate, validate
from project_document import Document

CONFIG_FORMAT = 'solidcraft-riduttori/1'
LIMITATIONS = [
    'Units are millimetres; geometry and exports use the nominal assembly pose.',
    'Sampled tooth curves and surfaces are retained; only proven construction circles may become analytic STEP cylinders.',
    'SVG/DXF files are local planar sections with placement metadata; twisted/deformed sections are not a manufacturing development.',
    'Construction-specific geometry checks are recorded in analysis metadata; they do not certify elastic response, strength or service life.',
    'Interference is discrete sampled coverage, not a continuous collision-free or exact penetration-depth guarantee.',
    'Cancellation and time limits are cooperative; one generator, triangulation or exporter unit may finish before stopping.',
]


class AgentError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details

    def data(self):
        return dict(code=self.code, message=str(self), details=self.details)


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 1048576
    result_bytes: int = 2097152
    projects: int = 32
    seconds: float = 30.
    candidates: int = 1000
    results: int = 50
    poses: int = 48
    triangles: int = 120000
    parts: int = 128
    export_bytes: int = 134217728


class Budget:
    def __init__(self, seconds, cancel=None):
        self.deadline = monotonic()+seconds
        self.cancel = cancel or Event()

    def check(self):
        if self.cancel.is_set():
            raise AgentError('cancelled', 'Operation cancelled before publication.')
        if monotonic() >= self.deadline:
            raise AgentError('budget_exceeded', 'Operation exceeded its cooperative time budget.')


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode('utf-8')


def _object(value, name):
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AgentError('invalid_arguments', name+' must be an object with string keys.')
    return value


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise AgentError('invalid_arguments', f'{name} must be an integer in [{low}, {high}].')
    return value


def _number(value, name, low, high):
    try:
        valid = type(value) in (int, float) and low <= value <= high and isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise AgentError('invalid_arguments', f'{name} must be a finite number in [{low}, {high}].')
    return value


def _family(value):
    if not isinstance(value, str) or value not in FAMILIES:
        raise AgentError('invalid_arguments', 'Unknown family.', supported=list(FAMILIES))
    return value


def _spec_keys(family):
    keys = set()
    for variant in VARIANTS.get(family, {None: None}):
        keys.update(field[0] for field in get_specs(family, variant))
    return keys


def _option_fields(family):
    import catalog
    import hardware_catalog
    import kinematics
    fields = dict(
        bearing_mode=dict(type='string', enum=list(catalog.MODES)),
        bearing=dict(type='string', enum=list(catalog.BEARINGS)),
        fit=dict(type='string', enum=list(catalog.FITS)),
        seat_allowance=dict(type='number', minimum=-.08, maximum=.8),
        shaft_allowance=dict(type='number', minimum=-.8, maximum=.08),
        shoulder=dict(type='number', minimum=.5, maximum=5),
        hardware_mode=dict(type='string', enum=list(hardware_catalog.MODES)),
        hardware_screw=dict(type='string', enum=list(hardware_catalog.FASTENERS)),
        hardware_shim=dict(type='string', enum=list(hardware_catalog.SHIM_THICKNESSES)))
    for key in ('retaining', 'keys', 'bolts', 'shims'):
        fields['hardware_'+key] = dict(type='boolean')
    if family in VARIANTS:
        fields['variant'] = dict(type='string', enum=list(VARIANTS[family]))
    if family == 'double' or any(variant in ('double', 'two_stage_double') for variant in VARIANTS.get(family, {})):
        fields['double_style'] = dict(type='string', enum=list(DOUBLE_STYLES))
    if kinematics.options(family):
        fields['io_scheme'] = dict(type='string', enum=list(kinematics.options(family)))
        if family == 'planetary':
            fields['io_scheme2'] = deepcopy(fields['io_scheme'])
    if family == 'worm':
        fields['worm_static_friction'] = dict(type='number', minimum=0,
            description='Explicit static tooth friction coefficient; omit when unknown. Not inferred from materials.')
    if family == 'harmonic':
        fields['harmonic_output'] = dict(type='string', enum=list(HARMONIC_OUTPUTS))
    if family == 'cycloidal':
        from printed_shaft import DESIGNS
        fields['eccentric_design'] = dict(type='string', enum=list(DESIGNS))
    if family == 'differential':
        from differential_wrist import OUTPUT_INTERFACES,CARRIER_STYLES,RATIO_MODES,CONFIGURATIONS
        for key,choices in (('output_interface',OUTPUT_INTERFACES),('carrier_style',CARRIER_STYLES),('ratio_mode',RATIO_MODES),('configuration',CONFIGURATIONS)):
            fields[key]=dict(type='string',enum=list(choices))
    return fields


def checked_parameters(family, parameters):
    _family(family)
    parameters = _object(parameters, 'parameters')
    numeric, options = _spec_keys(family), _option_fields(family)
    extra = sorted(parameters.keys()-numeric-options.keys())
    if extra:
        raise AgentError('invalid_parameters', 'Unknown parameter keys.', keys=extra)
    for key, value in parameters.items():
        if key in numeric:
            _number(value, key, -1e12, 1e12)
        else:
            field = options[key]
            expected = {'string': str, 'boolean': bool}.get(field['type'])
            if expected and type(value) is not expected:
                raise AgentError('invalid_parameters', key+' has the wrong value type.')
            if 'enum' in field and value not in field['enum']:
                raise AgentError('invalid_parameters', key+' is not an available option.', allowed=field['enum'])
            if field['type'] == 'number':
                _number(value, key, field.get('minimum', -float('inf')), field.get('maximum', float('inf')))
    try:
        return validate(family, deepcopy(parameters))
    except (ValueError, TypeError, OverflowError) as error:
        raise AgentError('invalid_parameters', str(error)) from error


class Workspace:
    """Reject ambiguous portable names and every symlink/reparse component.

    The directory is explicitly granted by the person configuring the server.
    It must not be concurrently restructured by an untrusted OS user: this is
    a local file API, not an OS sandbox against a hostile filesystem owner.
    """
    def __init__(self, root):
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise AgentError('invalid_workspace', 'Workspace must be an explicit absolute directory.')
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise AgentError('invalid_workspace', 'Workspace is not a directory.')
        self.private = Path(tempfile.mkdtemp(prefix='.ratiolab-agent-', dir=self.root))

    @staticmethod
    def linked(path):
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)

    def path(self, name, *, parents=False):
        if not isinstance(name, str) or not name or len(name) > 512 or '\\' in name or ':' in name or '\x00' in name:
            raise AgentError('unsafe_path', 'Use an unambiguous relative workspace path with forward slashes.')
        value = PurePosixPath(name)
        if value.is_absolute() or PureWindowsPath(name).drive:
            raise AgentError('unsafe_path', 'Absolute paths are not accepted.')
        segments = name.split('/')
        reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
        if any(not p or p in ('.', '..') or p.startswith('.') or p.endswith((' ', '.'))
               or any(ord(c)<32 or c in '<>"|?*' for c in p) or p.split('.')[0].upper() in reserved for p in segments):
            raise AgentError('unsafe_path', 'Traversal, hidden/reserved names and ambiguous Windows paths are forbidden.')
        current = self.root
        for index, part in enumerate(segments):
            current /= part
            if current.exists() or current.is_symlink():
                if self.linked(current):
                    raise AgentError('unsafe_path', 'Symlinks and Windows reparse points are forbidden.')
                if index < len(segments)-1 and not current.is_dir():
                    raise AgentError('unsafe_path', 'A path parent is not a directory.')
            elif index < len(segments)-1:
                if not parents:
                    raise AgentError('not_found', 'Workspace parent directory does not exist.')
                current.mkdir()
        if not current.resolve(strict=False).is_relative_to(self.root):
            raise AgentError('unsafe_path', 'Path escapes workspace.')
        return current

    def read(self, name, limit):
        path = self.path(name)
        flags = (os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
                 | getattr(os, 'O_NONBLOCK', 0))
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or self.linked(path):
                raise AgentError('unsafe_path', 'Import requires an ordinary unaliased regular file.')
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or (before.st_dev,before.st_ino) != (info.st_dev,info.st_ino):
                    raise AgentError('unsafe_path', 'Import requires a regular file with no hard-link aliases.')
                data = stream.read(limit+1)
        except FileNotFoundError as error:
            raise AgentError('not_found', 'Workspace file does not exist.') from error
        if len(data) > limit:
            raise AgentError('resource_limit', 'Input JSON exceeds size limit.', maximum_bytes=limit)
        return path, data

    def close(self):
        shutil.rmtree(self.private, ignore_errors=True)


@dataclass
class Project:
    document: Document
    design: object
    disk_sha256: str | None = None


class AgentService:
    def __init__(self, workspace, limits=None):
        self.limits = limits or Limits()
        self.workspace = Workspace(workspace)
        self.projects = {}
        self.lock = RLock()

    def close(self):
        self.workspace.close()

    def _budget(self, cancel):
        return Budget(self.limits.seconds, cancel)

    def _get(self, handle, revision):
        if not isinstance(handle, str) or handle not in self.projects:
            raise AgentError('unknown_project', 'Unknown or expired project handle.')
        project = self.projects[handle]
        _integer(revision, 'revision', 0, 2**53-1)
        if revision != project.document.revision:
            raise AgentError('stale_revision', 'Refresh the project revision before operating.',
                             expected=project.document.revision, received=revision)
        return project

    def _summary(self, project):
        d = project.document
        return dict(handle=d.identity, revision=d.revision, family=project.design.family,
                    parameters=deepcopy(project.design.values), dirty=d.dirty, saved=d.path is not None,
                    path=d.path.relative_to(self.workspace.root).as_posix() if d.path else None,
                    components=len(project.design.parts))

    def _add(self, design, path=None, digest=None, budget=None):
        with self.lock:
            if budget:
                budget.check()
            if len(self.projects) >= self.limits.projects:
                raise AgentError('resource_limit', 'Close a project before opening another.', maximum=self.limits.projects)
            document = Document(dict(family=design.family, values={design.family: design.values}, raw={}), path)
            project = Project(document, design, digest)
            self.projects[document.identity] = project
            return self._summary(project)

    def _generate(self, family, parameters, budget):
        budget.check()
        values = checked_parameters(family, parameters)
        try:
            design = generate(family, deepcopy(values))
        except (ValueError, TypeError, OverflowError) as error:
            raise AgentError('invalid_geometry', str(error)) from error
        budget.check()
        if len(design.parts) > self.limits.parts:
            raise AgentError('resource_limit', 'Generated component limit exceeded.')
        return design

    def discover(self, family=None, variant=None, double_style=None, parameters=None, cancel=None):
        if family is None:
            if variant is not None or double_style is not None or parameters is not None:
                raise AgentError('invalid_arguments', 'Choose family before variant/style.')
            return dict(families=[dict(id=k, label=v, variants=VARIANTS.get(k, {})) for k,v in FAMILIES.items()],
                        limits=asdict(self.limits), limitations=LIMITATIONS,
                        formats=['step', 'stl', 'svg', 'dxf', 'profiles', 'package'],
                        component_indices='1-based source indices; always tied to a project revision')
        _family(family)
        options = _option_fields(family)
        supplied = deepcopy(_object(parameters if parameters is not None else {}, 'parameters'))
        for key, value in [('variant', variant), ('double_style', double_style)]:
            if value is not None:
                if key in supplied and supplied[key] != value:
                    raise AgentError('invalid_arguments', 'Conflicting '+key+' discovery arguments.')
                supplied[key] = value
        values = checked_parameters(family, supplied)
        specs = get_specs(family, values.get('variant'), values.get('double_style'))
        if family=='differential':
            from differential_wrist import labelled_specs
            specs=labelled_specs(specs,values)
        import catalog
        import kinematics
        import hardware_catalog
        presets = {}
        if family == 'cycloidal':
            from printed_shaft import PRESET, SUPPORTED_SCHEMES
            presets['fdm_bolted'] = dict(parameters=dict(PRESET, eccentric_design='fdm_bolted'),
                canonical_defaults=checked_parameters(family, dict(eccentric_design='fdm_bolted')),
                supported_io_schemes=list(SUPPORTED_SCHEMES),
                derived_fields=['bore'], explanation='6804 seat derives from print_seat_allowance; input_shaft=17 and width=16 are preset defaults. Manual bearing mode and no additional hardware are required.')
        if family == 'differential':
            for mode,description in (('one_to_one','Output teeth equal side teeth; relative spin gain is 1.'),
                                     ('spin_2_1','Output teeth are twice side teeth; relative spin gain is 1/2. Carrier mean speed is unchanged.')):
                context=dict(ratio_mode=mode,configuration=values['configuration'],variant=values['variant'])
                presets[mode]=dict(parameters=dict(ratio_mode=mode),canonical_defaults=checked_parameters(family,context),
                                   derived_fields=['output_teeth'],explanation=description)
        return dict(family=family, label=FAMILIES[family], defaults=values, named_presets=presets,
                    fields=[dict(name=k, label=label, type='integer' if k in INTEGER else 'number',
                                 default=values[k], nominal_default=default, minimum=low, maximum=high, step=step) for k,label,default,low,high,step in specs],
                    options=options, variants=VARIANTS.get(family, {}), io_schemes=kinematics.options(family),
                    bearings={k:v.data() for k,v in catalog.BEARINGS.items()},
                    bearing_catalog_supported=family in catalog.SUPPORTED,
                    hardware_catalog_supported=family in hardware_catalog.SUPPORTED,
                    derived_parameters='The generator recomputes bearing-linked bores/widths, nominal fits, printed-shaft seats, dependent teeth and I/O rates. Returned canonical parameters are authoritative; compare them after every change.',
                    limitations=LIMITATIONS, **(dict(parameter_conditions=dict(
                        flange_fields='flange_radius, bolt_count and bolt_diameter apply only to output_interface=flange',
                        output_extension='Wrist solid/hollow output extension beyond carrier outer face; classic uses shaft_extension for both side outputs beyond each outer carrier interface',
                        passage_diameter='Applies only to output_interface=hollow; minimum radial shaft wall is 1 mm',
                        carrier_bolt_diameter='Applies to split carrier lap joints and the classic direct carrier input mount; nominal holes, no stock fasteners',
                        output_teeth='Derived from side_teeth unless ratio_mode=custom; spin_2_1 supports side_teeth <=30',
                        spiral_angle='Unsigned degrees, active only for variant=spiral; zero uses exact straight geometry',
                        spiral_hand='Integer -1 or +1, active only for variant=spiral; side local hands match, transverse hand is opposite',
                        configuration='Wrist: two input shafts and one two-motion output. Classic: direct carrier input, two side outputs and an internal spider',
                        input_rpm='Wrist input A speed or classic carrier input speed, all about world +X',
                        input_b_rpm='Active only for wrist; retained but unused for classic',
                        output_difference_rpm='Active only for classic; prescribed B-A speed boundary, not a second motor or load-based split',
                        spider_pin_diameter='Classic only; real carrier-fixed pin, with spider gear bore = pin diameter + 2*spider_clearance',
                        spider_clearance='Classic only; positive radial running clearance, no bearing capacity estimate')) if family=='differential' else {}))

    def project_create(self, family, parameters=None, cancel=None):
        budget = self._budget(cancel)
        return self._add(self._generate(family, parameters if parameters is not None else {}, budget), budget=budget)

    def project_open(self, path, cancel=None):
        budget = self._budget(cancel)
        if not isinstance(path, str) or not path.lower().endswith('.json'):
            raise AgentError('invalid_format', 'Import accepts UTF-8 JSON configuration files only.')
        target, data = self.workspace.read(path, self.limits.input_bytes)
        try:
            obj = json.loads(data.decode('utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, UnicodeError, RecursionError) as error:
            raise AgentError('invalid_json', 'Invalid UTF-8 JSON configuration.') from error
        _object(obj, 'configuration')
        if set(obj) != {'format', 'family', 'parameters'} or obj.get('format') != CONFIG_FORMAT:
            raise AgentError('invalid_format', 'Expected a full solidcraft-riduttori/1 configuration; subset/script/recovery imports are not accepted.')
        design = self._generate(obj['family'], obj['parameters'], budget)
        return self._add(design, target, hashlib.sha256(data).hexdigest(), budget)

    def project_list(self, cancel=None):
        with self.lock:
            return dict(projects=[self._summary(p) for p in self.projects.values()])

    def project_update(self, handle, revision, parameters, cancel=None):
        budget = self._budget(cancel)
        with self.lock:
            project = self._get(handle, revision)
            values = dict(project.design.values)
            values.update(_object(parameters, 'parameters'))
            family = project.design.family
        design = self._generate(family, values, budget)
        with self.lock:
            project = self._get(handle, revision)
            budget.check()
            project.document.record(dict(family=family, values={family: design.values}, raw={}))
            project.design = design
            return self._summary(project)

    def project_history(self, handle, revision, action, cancel=None):
        budget = self._budget(cancel)
        with self.lock:
            project = self._get(handle, revision)
            document = project.document
            if action not in ('undo', 'redo'):
                raise AgentError('invalid_arguments', 'History action must be undo or redo.')
            target = document.index+(-1 if action == 'undo' else 1)
            if not 0 <= target < len(document.states):
                raise AgentError('no_history', 'No '+action+' state is available.')
            snapshot = deepcopy(document.states[target])
        design = self._generate(snapshot['family'], snapshot['values'][snapshot['family']], budget)
        with self.lock:
            project = self._get(handle, revision)
            budget.check()
            getattr(project.document, action)()
            project.design = design
            return self._summary(project)

    def project_save(self, handle, revision, path, overwrite=False, cancel=None):
        if type(overwrite) is not bool:
            raise AgentError('invalid_arguments', 'overwrite must be boolean.')
        if not isinstance(path, str) or not path.lower().endswith('.json'):
            raise AgentError('invalid_format', 'Project destination must have a .json extension.')
        budget = self._budget(cancel)
        with self.lock:
            project = self._get(handle, revision)
            budget.check()
            target = self.workspace.path(path, parents=True)
            if target.exists():
                if not overwrite:
                    raise AgentError('already_exists', 'File exists; explicit overwrite is required.')
                if target != project.document.path or project.disk_sha256 is None:
                    raise AgentError('conflict', 'Only this handle’s opened/saved file can be replaced; choose a new path.')
                _, old = self.workspace.read(path, self.limits.input_bytes)
                if hashlib.sha256(old).hexdigest() != project.disk_sha256:
                    raise AgentError('conflict', 'File changed outside this handle; reopen it before replacing.')
            elif overwrite:
                raise AgentError('conflict', 'Cannot replace a missing file; save to a new path instead.')
            data = json_bytes(dict(format=CONFIG_FORMAT, family=project.design.family, parameters=project.design.values))
            descriptor, temporary = tempfile.mkstemp(prefix='save-', dir=self.workspace.private)
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                budget.check()
                self.workspace.path(path)  # Recheck symlink/reparse parents immediately before publication.
                if overwrite:
                    _, current = self.workspace.read(path, self.limits.input_bytes)
                    if hashlib.sha256(current).hexdigest() != project.disk_sha256:
                        raise AgentError('conflict', 'File changed while preparing the save.')
                    os.replace(temporary, target)
                else:
                    # Same filesystem, atomic exclusive publication: never clobber an existing file.
                    os.link(temporary, target)
                project.disk_sha256 = hashlib.sha256(data).hexdigest()
                project.document.mark_saved(target)
                project.document.revision += 1
                return self._summary(project)
            except FileExistsError as error:
                raise AgentError('already_exists', 'Destination appeared while saving.') from error
            finally:
                Path(temporary).unlink(missing_ok=True)

    def project_close(self, handle, revision, cancel=None):
        with self.lock:
            project = self._get(handle, revision)
            self._budget(cancel).check()
            del self.projects[handle]
            return dict(handle=handle, revision=project.document.revision, closed=True)

    def _snapshot(self, handle, revision, cancel):
        budget = self._budget(cancel)
        with self.lock:
            project = self._get(handle, revision)
            # Published designs are never mutated by the service; readers retain
            # their revision even when another request publishes a new design.
            return project.design, budget

    def _selection(self, design, indices, revision):
        if indices is None:
            return design
        if not isinstance(indices, list) or not indices or len(indices) > self.limits.parts:
            raise AgentError('invalid_arguments', 'components must be a non-empty list of 1-based source indices.')
        for index in indices:
            _integer(index, 'component index', 1, len(design.parts))
        if len(set(indices)) != len(indices):
            raise AgentError('invalid_arguments', 'Duplicate component indices are not accepted.')
        from selected_export import subset
        selected = subset(design, [i-1 for i in indices], revision)
        selected.export_scope['index_base'] = 1
        selected.analysis['export_scope']['index_base'] = 1
        return selected

    def project_describe(self, handle, revision, components=None, cancel=None):
        design, budget = self._snapshot(handle, revision, cancel)
        design = self._selection(design, components, revision)
        import bom
        from combination_search import nominal_bounds
        from engineering import geometry_warnings
        low, high = nominal_bounds(design, budget.check)
        result = dict(handle=handle, revision=revision, family=design.family, parameters=design.values,
                      analysis=design.analysis, metrics=design.metrics, notes=design.notes,
                      requirements=design.requirements, geometry_warnings=geometry_warnings(design),
                      bounds_mm=dict(minimum=low, maximum=high, xyz=[b-a for a,b in zip(low,high)]),
                      components=[dict(index=i, name=p.name, role=p.role, port=p.port,
                                       profile_geometry=p.profile_metadata, **bom.part_info(p))
                                  for i,p in zip(getattr(design, 'source_indices', range(1,len(design.parts)+1)), design.parts)],
                      export_scope=getattr(design,'export_scope',None), limitations=LIMITATIONS)
        budget.check()
        return result

    def bom(self, handle, revision, components=None, cancel=None):
        design, budget = self._snapshot(handle, revision, cancel)
        import bom
        result = bom.build(self._selection(design, components, revision))
        budget.check()
        return dict(handle=handle, revision=revision, bom=result, limitations=LIMITATIONS)

    def export(self, handle, revision, path, kind='package', components=None, cancel=None):
        design, budget = self._snapshot(handle, revision, cancel)
        original = design
        design = self._selection(design, components, revision)
        if kind not in ('step','stl','svg','dxf','profiles','package'):
            raise AgentError('invalid_arguments', 'Unknown export kind.')
        import bom
        import cad_export
        import profile_export
        import stl_export
        from export_transaction import directory
        config = dict(format=CONFIG_FORMAT, family=original.family, parameters=original.values)
        with self.lock:
            self._get(handle, revision)
            budget.check()
            target = self.workspace.path(path, parents=True)
            if target.exists():
                raise AgentError('already_exists', 'Export directories are never replaced.')
        # Use the existing transactional exporter: every writer runs against an
        # unpublished staging directory and all files are published together.
        with directory(target) as staging:
            budget.check()
            if kind in ('step','package'):
                cad_export.write_files(design, staging); budget.check()
            if kind in ('stl','package'):
                stl_export.export(design, staging/'model'); budget.check()
            if kind in ('svg','dxf','profiles','package'):
                profile_export.write_files(design, staging); budget.check()
                # Both formats preserve shared metadata references. A request
                # for svg/dxf intentionally emits the companion format too.
            bom.export(design, staging/'model'); budget.check()
            (staging/'model.config.json').write_bytes(json_bytes(dict(config, selected_export=design.export_scope)
                                                          if hasattr(design,'export_scope') else config))
            if kind == 'package':
                assets = staging/'assets'
                design.prepare_assets(assets)
                commands = design.commands(assets)
                for command in commands:
                    if command['command'] == 'file.insert_step':
                        command['params']['path'] = 'assets/'+Path(command['params']['path']).name
                (staging/'model.script.json').write_bytes(json_bytes(dict(commands=commands)))
            scope = getattr(design,'export_scope',None)
            if scope:
                (staging/'selection.json').write_bytes(json_bytes(scope))
            (staging/'README.txt').write_text('RatioLab headless export; no GUI screenshot is included.\n'
                + ('SELECTED COMPONENTS ONLY; source calculations are retained for reference.\n' if scope else 'Full nominal assembly.\n')
                + '\n'.join(LIMITATIONS)+'\n', encoding='utf-8')
            files = []
            total = 0
            for file in sorted(staging.rglob('*')):
                budget.check()
                if file.is_file():
                    total += file.stat().st_size
                    if total > self.limits.export_bytes:
                        raise AgentError('resource_limit', 'Export byte budget exceeded.')
                    files.append(dict(path=file.relative_to(staging).as_posix(), bytes=file.stat().st_size,
                                      sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
            if len(json_bytes(files)) > self.limits.result_bytes//3:
                raise AgentError('resource_limit', 'Export inventory exceeds response budget; select fewer components.')
            (staging/'manifest.json').write_bytes(json_bytes(dict(format='ratiolab-headless-export/1', complete=True,
                complete_assembly=not bool(scope), preview='not included: headless export', units='mm',
                handle=handle, revision=revision, index_base=1, family=design.family, kind=kind, scope=scope, files=files,
                limitations=LIMITATIONS)))
            with self.lock:
                self._get(handle, revision)
                budget.check()
                self.workspace.path(path)
        return dict(handle=handle, revision=revision, path=target.relative_to(self.workspace.root).as_posix(),
                    kind=kind, complete_assembly=not bool(scope), files=files,
                    manifest=path+'/manifest.json', limitations=LIMITATIONS)

    def search(self, handle, revision, axes, settings=None, cancel=None):
        design, budget = self._snapshot(handle, revision, cancel)
        import combination_search as search
        settings = _object(settings if settings is not None else {}, 'settings')
        allowed = set(search.Settings.__dataclass_fields__)
        if settings.keys()-allowed:
            raise AgentError('invalid_arguments', 'Unknown search settings.', keys=sorted(settings.keys()-allowed))
        options = dict(max_seconds=self.limits.seconds, max_candidates=self.limits.candidates, max_results=self.limits.results)
        options.update(settings)
        _number(options['max_seconds'], 'max_seconds', .001, self.limits.seconds)
        _integer(options['max_candidates'], 'max_candidates', 1, self.limits.candidates)
        _integer(options['max_results'], 'max_results', 1, self.limits.results)
        for key in ('target','tolerance_percent'):
            if key in options:
                _number(options[key], key, 0, 1e12)
        if 'max_xyz' in options:
            if not isinstance(options['max_xyz'], (list,tuple)) or len(options['max_xyz']) != 3:
                raise AgentError('invalid_arguments', 'max_xyz must contain three finite positive dimensions.')
            for value in options['max_xyz']:
                _number(value, 'max_xyz', 1e-12, 1e12)
        axes = _object(axes, 'axes')
        if not axes or len(axes)>8:
            raise AgentError('invalid_arguments', 'Choose between one and eight finite search axes.')
        for key, values in axes.items():
            if not isinstance(values, list) or not values or len(values)>100:
                raise AgentError('invalid_arguments', key+': use 1–100 explicit numeric values.')
        try:
            result = search.search(design.family, design.values, axes, search.Settings(**options), budget.cancel)
        except (ValueError, TypeError, OverflowError) as error:
            raise AgentError('invalid_arguments', str(error)) from error
        return dict(handle=handle, revision=revision, search=asdict(result), complete=result.complete,
                    limitations=LIMITATIONS)

    def interference(self, handle, revision, settings=None, cancel=None):
        design, budget = self._snapshot(handle, revision, cancel)
        import interference
        settings = _object(settings if settings is not None else {}, 'settings')
        allowed = set(interference.Settings.__dataclass_fields__)
        if settings.keys()-allowed:
            raise AgentError('invalid_arguments', 'Unknown interference settings.', keys=sorted(settings.keys()-allowed))
        options = dict(max_seconds=self.limits.seconds, max_poses=self.limits.poses,
                       max_triangles=self.limits.triangles, max_parts=self.limits.parts)
        options.update(settings)
        _number(options['max_seconds'], 'max_seconds', .001, self.limits.seconds)
        for key, limit in [('max_poses',self.limits.poses), ('max_triangles',self.limits.triangles), ('max_parts',self.limits.parts)]:
            _integer(options[key], key, 1, limit)
        for key in ('step_degrees','tolerance_mm'):
            if key in options:
                _number(options[key], key, 1e-12, 1e12)
        try:
            result = interference.analyze(design, interference.Settings(**options), budget.cancel)
        except (ValueError, TypeError, OverflowError) as error:
            raise AgentError('invalid_arguments', str(error)) from error
        result.revision = revision
        return dict(handle=handle, revision=revision, analysis=asdict(result),
                    complete=result.coverage_complete, limitations=LIMITATIONS)
