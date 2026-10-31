# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Browser RPC boundary for the unchanged, standard-library RatioLab engine.

Only the active design is retained. Geometry calculations and canonical exports
keep Python doubles; float32 little-endian arrays are a display transport only.
All part selections are zero-based; export source positions stay one-based.
"""
from array import array
from dataclasses import asdict, fields
from copy import deepcopy
from io import BytesIO
import json
from math import isfinite, sqrt
from pathlib import Path
import sys
import tempfile
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

import geometry
import motion
import catalog as bearings
import hardware_catalog as hardware
import kinematics
import parameter_help

API_VERSION = 1
PROJECT_FORMAT = 'solidcraft-riduttori/1'
MAX_INPUT_BYTES = 1048576
MAX_TRIANGLES = 1000000
MAX_EXPORT_BYTES = 134217728
LIMITATIONS = [
    'Units are millimetres. Exports use nominal assembly coordinates.',
    'Display buffers use float32; calculations and source geometry retain Python float64 precision.',
    'Sampled geometry and ideal motion do not establish strength, service life or manufacturing readiness.',
    'SVG/DXF are local planar sections with placement metadata; twisted/deformed sections are not manufacturing developments.',
    'Strain-wave motion is prescribed deformation, not an elastic solution.',
]
# This controls the compact editor only; every canonical numeric field is exposed.
ADVANCED = {'pressure', 'backlash', 'profile_shift', 'addendum', 'dedendum',
            'clearance', 'assembly_clearance', 'output_clearance', 'profile_tolerance',
            'wave_clearance', 'wave_factor'}


class BridgeError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def help_for(family, key, values):
    try:
        return asdict(parameter_help.lookup(family, key, values))
    except KeyError:
        return None


def option_definitions(family):
    fields = {}

    def choices(key, values, default):
        fields[key] = dict(key=key, type='choice', choices=[dict(value=k, label=v) for k, v in values.items()], default=default)

    choices('bearing_mode', bearings.MODES, 'manual')
    choices('bearing', {k: b.label for k, b in bearings.BEARINGS.items()}, '608' if family == 'cycloidal' else '626')
    choices('fit', bearings.FITS, 'nominal')
    choices('hardware_mode', hardware.MODES, 'none')
    choices('hardware_screw', {k: k for k in hardware.FASTENERS}, 'M3')
    choices('hardware_shim', hardware.SHIM_THICKNESSES, '.5')
    for key in ('retaining', 'keys', 'bolts', 'shims'):
        fields['hardware_'+key] = dict(key='hardware_'+key, type='boolean', default=not (family in ('parallel', 'internal') and key == 'bolts'))
    for key, default, low, high, step in [('seat_allowance', 0, -.08, .8, .01), ('shaft_allowance', 0, -.8, .08, .01), ('shoulder', 1, .5, 5, .1)]:
        fields[key] = dict(key=key, type='number', default=default, minimum=low, maximum=high, step=step)
    if family in geometry.VARIANTS:
        choices('variant', geometry.VARIANTS[family], next(iter(geometry.VARIANTS[family])))
    if geometry.is_double(family) or any(geometry.is_double(family, v) for v in geometry.VARIANTS.get(family, {})):
        choices('double_style', geometry.DOUBLE_STYLES, 'joined' if family == 'double' else 'separated')
    if kinematics.options(family):
        choices('io_scheme', kinematics.options(family), kinematics.default(family))
        if family == 'planetary':
            choices('io_scheme2', kinematics.options(family), kinematics.default(family))
    if family == 'harmonic':
        choices('harmonic_output', geometry.HARMONIC_OUTPUTS, 'flex')
    if family == 'worm':
        fields['worm_static_friction'] = dict(key='worm_static_friction', type='number', default=None, minimum=0, optional=True)
    if family == 'cycloidal':
        from printed_shaft import DESIGNS
        choices('eccentric_design', DESIGNS, 'standard')
    if family == 'differential':
        import differential_wrist as wrist
        for key, source in [('configuration', wrist.CONFIGURATIONS), ('output_interface', wrist.OUTPUT_INTERFACES), ('carrier_style', wrist.CARRIER_STYLES), ('ratio_mode', wrist.RATIO_MODES)]:
            choices(key, source, wrist.OPTION_DEFAULTS[key])
    return fields


def family_check(family):
    if not isinstance(family, str) or family not in geometry.FAMILIES:
        raise BridgeError('invalid_parameters', 'Unknown gear or reducer family.')
    return family


def parameters_check(family, values):
    family_check(family)
    if not isinstance(values, dict) or not all(isinstance(key, str) for key in values):
        raise BridgeError('invalid_parameters', 'Parameters must be an object with string keys.')
    numeric = {spec[0] for variant in geometry.VARIANTS.get(family, {None: None}) for spec in geometry.get_specs(family, variant)}
    options = option_definitions(family)
    for key, value in values.items():
        field = options.get(key)
        if key in numeric or field and field['type'] == 'number':
            if type(value) not in (int, float) or not isfinite(value):
                raise BridgeError('invalid_parameters', key+': a finite numeric value is required.')
        elif field and field['type'] == 'boolean':
            if type(value) is not bool:
                raise BridgeError('invalid_parameters', key+': a boolean value is required.')
        elif field and field['type'] == 'choice':
            if type(value) is not str or value not in [choice['value'] for choice in field['choices']]:
                raise BridgeError('invalid_parameters', key+': unknown option.')
        else:
            raise BridgeError('invalid_parameters', 'Unknown parameter: '+key)
    return geometry.validate(family, dict(values))


def editor_metadata():
    from ratiolab_resources import root
    metadata_file = root()/'web-catalog.json'
    return json.loads(metadata_file.read_text(encoding='utf-8')) if metadata_file.is_file() else {}


def schema(family, parameters=None):
    family_check(family)
    supplied = dict(parameters or {})
    # Schema does not generate geometry, but rejects invalid option names.
    variant = supplied.get('variant')
    specs = geometry.get_specs(family, variant, supplied.get('double_style'))
    if family == 'differential':
        from differential_wrist import labelled_specs, inactive_fields
        specs = labelled_specs(specs, supplied)
        inactive = inactive_fields(supplied)
    else:
        inactive = set()
    fields = []
    advanced = set(editor_metadata().get('advanced', ADVANCED))
    for key, label, default, low, high, step in specs:
        fields.append(dict(key=key, label=label, type='integer' if key in geometry.INTEGER else 'number', default=default,
                           minimum=low, maximum=high, step=step, advanced=key in advanced,
                           inactive=key in inactive, help=help_for(family, key, supplied)))
    options = option_definitions(family)
    for key, field in options.items():
        field.update(help=help_for(family, key, supplied))
    return dict(family=family, fields=fields, options=list(options.values()), defaults=geometry.defaults(family, variant),
                bearing_supported=family in bearings.SUPPORTED, hardware_supported=family in hardware.SUPPORTED)


def catalog():
    metadata = editor_metadata()
    labels = metadata.get('catalog', {})
    return dict(api_version=API_VERSION, project_format=PROJECT_FORMAT, units='mm', index_base=0,
                families=[dict(key=family, label=labels.get(family, [label, ''])[0], description=labels.get(family, [label, ''])[1],
                               **{k: v for k, v in schema(family).items() if k != 'family'}) for family, label in geometry.FAMILIES.items()],
                bearings={key: value.data() for key, value in bearings.BEARINGS.items()},
                hardware=dict(fasteners=hardware.FASTENERS, keys=hardware.KEYS, shims=hardware.SHIMS,
                              shim_thicknesses=hardware.SHIM_THICKNESSES, verified=hardware.VERIFIED), limitations=LIMITATIONS)


def float_bytes(values):
    packed = array('f', values)
    if sys.byteorder != 'little':
        packed.byteswap()
    return packed.tobytes()


def archive(folder):
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED, compresslevel=6) as output:
        total = 0
        for path in sorted(Path(folder).rglob('*')):
            if path.is_file():
                data = path.read_bytes()
                total += len(data)
                if total > MAX_EXPORT_BYTES:
                    raise BridgeError('resource_limit', 'Export exceeds the 128 MiB uncompressed limit.')
                from zipfile import ZipInfo
                info = ZipInfo(path.relative_to(folder).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                output.writestr(info, data)
    return stream.getvalue()


def number(value, name, low=None, high=None):
    if type(value) not in (int, float) or not isfinite(value) or (low is not None and value < low) or (high is not None and value > high):
        raise BridgeError('invalid_arguments', name+': a finite number in the supported range is required.')
    return value


def vector(value, name, size=3):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise BridgeError('invalid_arguments', name+': expected '+str(size)+' finite coordinates.')
    return tuple(number(x, name) for x in value)


def settings_check(cls, supplied, **defaults):
    """Reject mistyped settings before the canonical domain/range validation."""
    if not isinstance(supplied, dict) or set(supplied)-{f.name for f in fields(cls)}:
        raise BridgeError('invalid_arguments', 'Unknown analysis settings.')
    baseline = cls(**defaults)
    for key, value in supplied.items():
        default = getattr(baseline, key)
        if type(default) is int:
            if type(value) is not int:
                raise BridgeError('invalid_arguments', key+': an integer is required.')
        elif type(default) is float:
            number(value, key)
        elif isinstance(default, tuple):
            vector(value, key, len(default))
        elif type(value) is not type(default):
            raise BridgeError('invalid_arguments', key+': invalid setting type.')
    result = cls(**dict(defaults, **supplied))
    result.validate()
    return result


class Engine:
    def __init__(self):
        self.design = None
        self.plan = None
        self.design_id = 0
        self.buffers = []
        self.query = None
        self.proposal = None
        self.surfaces = {}
        self.progress = lambda message, fraction: None

    def invalidate_queries(self):
        self.query = self.proposal = None
        self.surfaces.clear()

    def remember(self, method, data, text, proposal=None):
        # One completed query and at most one candidate assembly. No history of
        # meshes, queries or solver proposals survives the next analysis query.
        query_id = uuid4().hex
        self.proposal = proposal
        self.query = dict(design_id=self.design_id, query_id=query_id, method=method,
                          data=deepcopy(data), text=text)
        return deepcopy(self.query)

    def require(self, args):
        if self.design is None or type(args.get('design_id')) is not int or args['design_id'] != self.design_id:
            raise BridgeError('stale_design', 'This operation requires the active design_id.')
        return self.design

    def add_buffer(self, data):
        index = len(self.buffers)
        self.buffers.append(data)
        return index

    def project(self):
        return dict(format=PROJECT_FORMAT, family=self.design.family, parameters=self.design.values)

    def generate(self, family, parameters):
        # Wolfrom edits are transactional; browser document tokens still block
        # exports for an invalid draft. Other families keep their invalidation.
        if family != 'wolfrom':
            self.design = self.plan = None
            self.invalidate_queries()
            self.design_id += 1
        values = parameters_check(family, parameters)
        design = geometry.generate(family, values)
        plan = motion.build_plan(design)
        if family == 'wolfrom':
            self.invalidate_queries()
            self.design_id += 1
        result = self.pack_design(design, plan)
        self.design, self.plan = design, plan
        return result

    def pack_design(self, design, plan):
        """Pack an independent assembly without replacing the active source."""
        import stl_export
        from solid_geometry import PALETTE
        from engineering import geometry_warnings
        values = design.values
        if len(design.parts) > 256:
            raise BridgeError('resource_limit', 'The browser supports at most 256 components.')
        parts, triangles = [], 0
        lower, upper = [float('inf')]*3, [-float('inf')]*3
        for index, part in enumerate(design.parts):
            positions, normals, materials = array('f'), array('f'), array('f')
            lo, hi = [float('inf')]*3, [-float('inf')]*3
            references = None
            if index in plan.flex:
                from wave_geometry import material_vertices, unmap_point
                references = material_vertices(part)
                a, b = design.analysis['pitch_ellipse_semiaxes_mm']
                rp = values['module']*values['teeth']/2
            for triangle in stl_export.triangles(part):
                triangles += 1
                if triangles > MAX_TRIANGLES:
                    raise BridgeError('resource_limit', 'Mesh exceeds the browser triangle limit.')
                aa, bb, cc = triangle
                u = [bb[k]-aa[k] for k in range(3)]
                v = [cc[k]-aa[k] for k in range(3)]
                normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                length = sqrt(sum(x*x for x in normal))
                if length <= 1e-15:
                    raise BridgeError('invalid_geometry', 'Degenerate triangle: '+part.name)
                normal = tuple(x/length for x in normal)
                for point in triangle:
                    positions.extend(point)
                    normals.extend(normal)
                    for axis in range(3):
                        lo[axis] = min(lo[axis], point[axis]); hi[axis] = max(hi[axis], point[axis])
                    if references is not None:
                        if point not in references:
                            weight = max(0, min(1, (point[2]+values['cup_length']-values['diaphragm'])/(values['cup_length']-values['diaphragm'])))
                            references[point] = unmap_point(point[0]-part.center[0], point[1]-part.center[1], weight, a, b, rp)
                        materials.extend(references[point])
            if not positions:
                raise BridgeError('invalid_geometry', 'Component has no mesh: '+part.name)
            mesh = dict(positions=self.add_buffer(float_bytes(positions)), normals=self.add_buffer(float_bytes(normals)), vertex_count=len(positions)//3)
            if materials:
                mesh['material'] = self.add_buffer(float_bytes(materials))
            for axis in range(3):
                lower[axis] = min(lower[axis], lo[axis]); upper[axis] = max(upper[axis], hi[axis])
            parts.append(dict(index=index, source_index=index+1, name=part.name, role=part.role,
                              color=part.color if part.color != (.35, .72, .9) else PALETTE[index % len(PALETTE)],
                              bounds_mm=dict(minimum=lo, maximum=hi), mesh=mesh, port=part.port,
                              center=part.center, frame=part.frame, axis_x=part.axis_x,
                              profile_geometry=part.profile_metadata, manufacturing=part.manufacturing))
        return dict(design_id=self.design_id, family=design.family, values=design.values, metrics=design.metrics,
                    notes=design.notes, warnings=geometry_warnings(design), requirements=design.requirements,
                    analysis=design.analysis, parts=parts, triangle_count=triangles,
                    bounds_mm=dict(minimum=lower, maximum=upper), motion=self.motion_metadata(design, plan), limitations=LIMITATIONS)

    def motion_metadata(self, design=None, plan=None):
        design, plan = design or self.design, plan or self.plan
        result = dict(supported=plan.supported, message=plan.message, reference_rpm=plan.reference_rpm,
                      phase_units='radians', phase_radians_per_second=plan.reference_rpm*2*__import__('math').pi/60,
                      matrix_layout='column-major', rates=plan.rates,
                      angular_rates=plan.angular_rates, angular_offsets=plan.angular_offsets,
                      coordinates=[dict(index=k[0], coordinate=k[1], rate=v, offset=plan.coordinate_offsets[k]) for k, v in plan.coordinate_rates.items()],
                      deforming_indices=list(plan.flex), warping_indices=list(plan.warps))
        if plan.flex:
            from wave_geometry import arc_coefficients
            a, b = design.analysis['pitch_ellipse_semiaxes_mm']
            rp = design.values['module']*design.values['teeth']/2
            result['wave_arc_coefficients'] = arc_coefficients(a, b, rp)
        return result

    def pose(self, args):
        design = self.require(args)
        phases = args.get('phases', [0])
        if not isinstance(phases, list) or not 1 <= len(phases) <= 64 or any(type(p) not in (int, float) or not isfinite(p) or abs(p)>1e9 for p in phases):
            raise BridgeError('invalid_arguments', 'Supply 1 to 64 finite phases in radians (magnitude at most 1e9).')
        return dict(design_id=self.design_id, frames=[dict(phase=phase, parts=[dict(index=i, matrix=self.plan.matrix(i, phase),
                    deformation=self.plan.deformation(i, phase), warp=self.plan.warp(i, phase)) for i in range(len(design.parts))]) for phase in phases])

    def documents(self, args):
        design = self.require(args)
        self.proposal = None
        if args.get('indices') is not None:
            indices = args['indices']
            if not isinstance(indices, list):
                raise BridgeError('invalid_arguments', 'indices must be an explicit component list.')
            from selected_export import subset
            design = subset(design, indices, self.design_id)
        import bom
        from engineering import report_text
        bill = bom.build(design)
        prefix = 'SELECTED COMPONENTS ONLY. Calculations below describe the SOURCE configuration.\n\n' if hasattr(design, 'export_scope') else ''
        report = prefix+report_text(design)
        return self.remember('documents', dict(bom=bill, bom_text=bom.as_text(bill), analysis=design.analysis,
                            report_text=report, scope=getattr(design, 'export_scope', None)), bom.as_text(bill)+'\n'+report)

    def metrology(self, args):
        design = self.require(args)
        import gear_measurement as measurement
        index = args.get('source_index')
        gauge_type = args.get('gauge_type', 'ball')
        if gauge_type not in ('ball', 'roller'):
            raise BridgeError('invalid_arguments', 'Gauge type must be ball or roller.')
        diameter = args.get('gauge_diameter')
        if diameter is not None:
            number(diameter, 'gauge_diameter', 1e-300)
        self.proposal = None
        # The canonical query owns family/profile validation and unsupported text.
        query = measurement.measurement_query(design, index, diameter if diameter is not None else 1., gauge_type, self.design_id)
        if diameter is None:
            default = measurement.default_gauge(query['geometry'])
            if 'gauge_diameter_mm' in default:
                query = measurement.measurement_query(design, index, default['gauge_diameter_mm'], gauge_type, self.design_id)
                if 'diameter_selection_basis' in default:
                    query['result']['diameter_selection_basis'] = default['diameter_selection_basis']
            else:
                query['result'] = default
        return self.remember('metrology', query, measurement.measurement_query_text(query))

    def search_schema(self, args):
        design = self.require(args)
        import combination_search as search
        return dict(design_id=self.design_id, supported=design.family in search.FAMILIES,
                    variables=[dict(key=s[0], label=s[1], default=s[2], minimum=s[3], maximum=s[4], step=s[5],
                                    integer=s[0] in geometry.INTEGER, current=design.values.get(s[0])) for s in search.variables(design.family, design.values)],
                    settings=asdict(search.Settings()), max_results=100)

    def search(self, args):
        design = self.require(args)
        import combination_search as search
        settings = settings_check(search.Settings, args.get('settings', {}))
        if settings.max_results > 100:
            raise BridgeError('resource_limit', 'Browser search retains at most 100 results.')
        grids = args.get('grids')
        if not isinstance(grids, dict) or not grids or len(grids) > len(search.variables(design.family, design.values)):
            raise BridgeError('invalid_arguments', 'Supply explicit finite grids for unlocked variables.')
        axes = {}
        for key, grid in grids.items():
            if isinstance(grid, str):
                axes[key] = search.parse_grid(grid)
            elif isinstance(grid, list) and 1 <= len(grid) <= 1000:
                axes[key] = tuple(number(value, key) for value in grid)
            else:
                raise BridgeError('invalid_arguments', 'Each grid must be a string or 1 to 1000 finite numbers.')
        self.proposal = None
        result = search.search(design.family, deepcopy(design.values), axes, settings, progress=self.progress)
        result.revision = self.design_id
        data = asdict(result)
        data.update(complete=result.complete, partial=not result.complete)
        for row, proposal in zip(data['proposals'], result.proposals):
            row['xyz'] = proposal.xyz
        return self.remember('search', data, result.text())

    def require_query(self, args, method=None):
        self.require(args)
        if not self.query or args.get('query_id') != self.query['query_id'] or self.query['design_id'] != self.design_id or (method and self.query['method'] != method):
            raise BridgeError('stale_query', 'This query is no longer current; run it again.')
        return self.query

    def search_apply(self, args):
        query = self.require_query(args, 'search')
        import combination_search as search
        data = query['data']
        index = args.get('proposal_index')
        if type(index) is not int or not 0 <= index < len(data['proposals']):
            raise BridgeError('invalid_arguments', 'Select a current search proposal.')
        if self.design.values != data['base']:
            raise BridgeError('stale_query', 'The search baseline has changed.')
        row = data['proposals'][index]
        checked = geometry.generate(self.design.family, deepcopy(row['values']))
        settings = settings_check(search.Settings, data['settings'])
        lo, hi = search.nominal_bounds(checked)
        if (checked.values != row['values'] or any(checked.values.get(k) != v for k, v in data['base'].items() if k not in data['axes'])
                or any(checked.values[k] not in grid for k, grid in data['axes'].items())
                or not search.matches(checked.analysis['signed_ratio'], settings)
                or checked.analysis['signed_ratio'] != row['ratio']
                or any(b-a > limit for a, b, limit in zip(lo, hi, settings.max_xyz))
                or tuple(lo) != tuple(row['minimum']) or tuple(hi) != tuple(row['maximum'])):
            raise BridgeError('invalid_proposal', 'Fresh candidate no longer matches the finite search proposal.')
        # Canonical values can contain hidden fields (joined helices retain
        # gap=0). Apply only freshly checked unlocked changes to the editor,
        # preserving locked raw entries and their original precision.
        changes = {key: deepcopy(checked.values[key]) for key in data['axes']
                   if checked.values[key] != data['base'][key]}
        return dict(design_id=self.design_id, query_id=query['query_id'],
                    values=deepcopy(checked.values), changes=changes)

    def interference(self, args):
        design = self.require(args)
        import interference
        settings = settings_check(interference.Settings, args.get('settings', {}))
        self.proposal = None
        result = interference.analyze(design, settings=settings, progress=self.progress, plan=self.plan)
        result.revision = self.design_id
        return self.remember('interference', asdict(result), result.text())

    def backlash(self, args):
        design = self.require(args)
        import backlash_solver
        from interference import Settings
        target = number(args.get('desired_backlash_mm'), 'desired_backlash_mm', 0)
        settings = settings_check(Settings, args.get('settings', {}), step_degrees=30., max_seconds=60.)
        # Release the old candidate before constructing a successor.
        self.proposal = self.query = None
        proposal = backlash_solver.solve(design, target, settings=settings, progress=self.progress)
        proposal.revision = self.design_id
        proposal_id = uuid4().hex
        result = self.remember('backlash', dict(proposal_id=proposal_id, **proposal.payload(), applicable=proposal.applicable), proposal.text(), proposal)
        if proposal.design is not None:
            result['candidate'] = self.pack_design(proposal.design, motion.build_plan(proposal.design))
            result['candidate']['proposal_id'] = proposal_id
            result['candidate']['is_candidate'] = True
        return result

    def proposal_apply(self, args):
        self.require(args)
        import backlash_solver
        if not self.query or self.query['method'] != 'backlash' or not self.proposal or args.get('proposal_id') != self.query['data']['proposal_id']:
            raise BridgeError('stale_proposal', 'No matching current backlash proposal.')
        if self.proposal.source_values != self.design.values or self.proposal.revision != self.design_id:
            raise BridgeError('stale_proposal', 'The proposal source has changed.')
        checked = backlash_solver.revalidate(self.proposal)
        return dict(design_id=self.design_id, proposal_id=args['proposal_id'], center_extra=checked.values['center_extra'])

    def query_export(self, args):
        query = self.require_query(args)
        kind = args.get('format')
        if kind not in ('txt', 'json'):
            raise BridgeError('invalid_arguments', 'Query export format must be txt or json.')
        data = (query['text'] if kind == 'txt' else json_text(query)+'\n').encode('utf-8')
        return dict(design_id=self.design_id, query_id=query['query_id'], name='ratiolab-'+query['method']+'.'+kind,
                    mime='text/plain;charset=utf-8' if kind == 'txt' else 'application/json', bytes=len(data), buffer=self.add_buffer(data))

    def rates(self, args):
        design = self.require(args)
        phase = number(args.get('phase'), 'phase', -1e9, 1e9)
        if ('parameters' in args) == ('rpm_patch' in args):
            raise BridgeError('invalid_arguments', 'Supply either full parameters or an RPM patch.')
        if 'rpm_patch' in args:
            patch = args['rpm_patch']
            if not isinstance(patch, dict) or not patch or set(patch)-motion.SPEED_KEYS or set(patch)-set(design.values):
                raise BridgeError('invalid_arguments', 'The RPM patch may contain only current operating speed keys.')
            supplied = dict(design.values, **patch)
        else:
            supplied = args['parameters']
            if not isinstance(supplied, dict) or set(supplied) != set(design.values):
                raise BridgeError('invalid_arguments', 'Supply all validated source parameters.')
        values = parameters_check(design.family, supplied)
        if not motion.same_geometry(design, design.family, values):
            raise BridgeError('geometry_changed', 'Only operating speed keys may change in a rates update.')
        updated = motion.update_operating_rates(design, values)
        plan = motion.build_plan(updated, previous=self.plan, phase=phase)
        # Everything above can fail without modifying active source or queries.
        self.design, self.plan = updated, plan
        self.design_id += 1
        self.invalidate_queries()
        from engineering import geometry_warnings
        return dict(design_id=self.design_id, family=updated.family, phase=phase, values=updated.values,
                    analysis=updated.analysis, metrics=updated.metrics, notes=updated.notes, warnings=geometry_warnings(updated),
                    requirements=updated.requirements, motion=self.motion_metadata(),
                    ports=[dict(index=i, port=p.port) for i, p in enumerate(updated.parts)])

    def motion_reset(self, args):
        """Restore construction phase without changing source values or meshes."""
        design = self.require(args)
        plan = motion.build_plan(design)
        self.plan = plan
        self.design_id += 1
        self.invalidate_queries()
        return dict(design_id=self.design_id, phase=0., motion=self.motion_metadata())

    def pick(self, args):
        design = self.require(args)
        import component_geometry as component
        origin = vector(args.get('ray_origin'), 'ray_origin')
        direction = vector(args.get('ray_direction'), 'ray_direction')
        if sum(x*x for x in direction) < 1e-24:
            raise BridgeError('invalid_arguments', 'Ray direction must be nonzero.')
        indices = args.get('visible_indices')
        if not isinstance(indices, list) or len(indices) > len(design.parts) or len(set(indices)) != len(indices) or any(type(i) is not int or not 0 <= i < len(design.parts) for i in indices):
            raise BridgeError('invalid_arguments', 'Supply explicit visible source indices.')
        animated = args.get('animated', False)
        if type(animated) is not bool:
            raise BridgeError('invalid_arguments', 'animated must be a boolean.')
        if animated and (self.plan.flex or self.plan.warps):
            raise BridgeError('unsupported_pose', 'Animated nonrigid surface picking is unavailable; pause and use nominal geometry.')
        section = args.get('section_y')
        if section is not None:
            number(section, 'section_y')
        transforms, offsets = {}, {}
        for name, target, key, size in [('matrices', transforms, 'matrix', 16), ('explosion_offsets', offsets, 'offset', 3)]:
            rows = args.get(name, [])
            if not isinstance(rows, list) or len(rows) > len(design.parts):
                raise BridgeError('invalid_arguments', name+': expected per-part records.')
            for row in rows:
                if not isinstance(row, dict) or type(row.get('index')) is not int or row['index'] not in indices or row['index'] in target:
                    raise BridgeError('invalid_arguments', name+': duplicate or non-visible component.')
                target[row['index']] = vector(row.get(key), name, size)
        for m in transforms.values():
            axes = [m[k:k+3] for k in (0, 4, 8)]
            dot = lambda a, b: sum(x*y for x, y in zip(a, b))
            determinant = dot(axes[0], (axes[1][1]*axes[2][2]-axes[1][2]*axes[2][1], axes[1][2]*axes[2][0]-axes[1][0]*axes[2][2], axes[1][0]*axes[2][1]-axes[1][1]*axes[2][0]))
            if (any(abs(m[k]) > 1e-7 for k in (3, 7, 11)) or abs(m[15]-1) > 1e-7 or abs(determinant-1) > 1e-7
                    or any(abs(dot(a, b)-(1 if i == j else 0)) > 1e-7 for i, a in enumerate(axes) for j, b in enumerate(axes))):
                raise BridgeError('invalid_arguments', 'Picking matrices must be rigid column-major transforms.')
        if animated and set(transforms) != set(indices):
            raise BridgeError('invalid_arguments', 'Animated picking requires the actual current matrix of every visible part.')
        surfaces = []
        for index in indices:
            if index not in self.surfaces:
                self.surfaces[index] = component.triangles(design.parts[index])
            ts = self.surfaces[index]
            matrix, offset = transforms.get(index, motion.IDENTITY), offsets.get(index, (0, 0, 0))
            if matrix != motion.IDENTITY or offset != (0, 0, 0):
                ts = tuple(tuple(tuple(a+b for a, b in zip(motion.transform(matrix, q), offset)) for q in t) for t in ts)
            surfaces.append((index, ts))
        hit = component.pick(origin, direction, surfaces, section_y=section)
        return dict(design_id=self.design_id, hit=None if hit is None else dict(source_index=hit[0], point=hit[1], triangle=hit[2]),
                    basis='Discrete sampled surface facets in mm; no analytic CAD measurement.')

    def surface_distance(self, args):
        self.require(args)
        import component_geometry as component
        points = args.get('points')
        if not isinstance(points, list) or len(points) != 2:
            raise BridgeError('invalid_arguments', 'Supply exactly two world surface points.')
        a, b = (vector(p, 'point') for p in points)
        return dict(design_id=self.design_id, points=[a, b], distance_mm=component.distance(a, b),
                    basis='Euclidean distance between supplied sampled surface points, not minimum surface clearance.')

    def export(self, args):
        original = self.require(args)
        kind = args.get('kind', 'project')
        if kind not in ('project', 'stl', 'svg', 'dxf', 'profiles', 'step', 'bom', 'report', 'package'):
            raise BridgeError('invalid_arguments', 'Unknown export format.')
        indices = args.get('indices')
        if indices is not None:
            if not isinstance(indices, list):
                raise BridgeError('invalid_arguments', 'indices must be a list of zero-based component positions.')
            from selected_export import subset
            design = subset(original, indices, self.design_id)
        else:
            design = original
        config = self.project()
        if kind == 'project':
            if indices is not None:
                raise BridgeError('invalid_arguments', 'A desktop project always describes the full source configuration. Use a selected geometry export.')
            data, filename, mime = (json_text(config)+'\n').encode('utf-8'), 'model.config.json', 'application/json'
        else:
            import bom
            import cad_export
            import profile_export
            import stl_export
            from engineering import report_text
            with tempfile.TemporaryDirectory(prefix='ratiolab-web-') as temporary:
                folder = Path(temporary)/'export'
                if kind == 'package':
                    preview = args.get('preview_png')
                    if not isinstance(preview, (bytes, bytearray, memoryview, list)) or len(preview)>16777216 or (isinstance(preview, list) and any(type(n) is not int or not 0 <= n <= 255 for n in preview)):
                        raise BridgeError('invalid_arguments', 'Complete packages require an encoded preview_png byte array (at most 16 MiB).')
                    import package_export
                    package_export.export(design, config, folder, bytes(preview))
                else:
                    folder.mkdir()
                    if kind == 'stl': stl_export.export(design, folder/'model')
                    if kind == 'step': cad_export.write_files(design, folder)
                    if kind in ('svg', 'dxf', 'profiles'): profile_export.write_files(design, folder)
                    if kind == 'bom': bom.export(design, folder/'model')
                    if kind == 'report':
                        (folder/'model.calculations.txt').write_text(('SELECTED COMPONENTS ONLY. Calculations below describe the SOURCE configuration.\n\n' if hasattr(design, 'export_scope') else '')+report_text(design), encoding='utf-8')
                        (folder/'model.calculations.json').write_text(json_text(design.analysis)+'\n', encoding='utf-8')
                    if hasattr(design, 'export_scope'):
                        (folder/'selection.json').write_text(json_text(design.export_scope)+'\n', encoding='utf-8')
                    # Project parameters describe the source assembly, including for a subset.
                    (folder/'model.config.json').write_text(json_text(dict(config, selected_export=design.export_scope) if hasattr(design, 'export_scope') else config)+'\n', encoding='utf-8')
                data = archive(folder)
            filename, mime = 'ratiolab-'+kind+'.zip', 'application/zip'
        return dict(design_id=self.design_id, name=filename, mime=mime, bytes=len(data), buffer=self.add_buffer(data),
                    scope=getattr(design, 'export_scope', None))

    def call(self, method, args):
        # Preserve the accepted Wolfrom source and its query leases on rejection.
        # A failed RPC never returns that source as a result for the new draft.
        target = args.get('family') if isinstance(args, dict) else None
        project = args.get('project') if isinstance(args, dict) else None
        if method == 'import_project' and isinstance(project, dict):
            target = project.get('family')
        transactional = method in ('generate', 'import_project') and (target == 'wolfrom' or
            method == 'import_project' and self.design is not None and self.design.family == 'wolfrom')
        if not transactional:
            return self._call(method, args)
        retained = dict(self.__dict__, buffers=list(self.buffers), surfaces=dict(self.surfaces))
        try:
            return self._call(method, args, transactional=True)
        except Exception:
            self.__dict__.update(retained)
            raise

    def _call(self, method, args, transactional=False):
        self.buffers.clear()
        if method in ('generate', 'import_project') and not transactional:
            self.design = self.plan = None
            self.invalidate_queries()
        if not isinstance(args, dict):
            raise BridgeError('invalid_arguments', 'RPC payload must be an object.')
        if method == 'catalog': return catalog()
        if method == 'schema': return schema(args.get('family'), args.get('parameters'))
        if method == 'validate': return dict(family=family_check(args.get('family')), values=parameters_check(args['family'], args.get('parameters', {})))
        if method == 'generate': return self.generate(args.get('family'), args.get('parameters', {}))
        if method == 'import_project':
            project = args.get('project')
            if not isinstance(project, dict) or project.get('format') != PROJECT_FORMAT or 'selected_export' in project:
                raise BridgeError('invalid_project', 'Expected a complete solidcraft-riduttori/1 project.')
            family = family_check(project.get('family'))
            parameters = project.get('parameters')
            if not isinstance(parameters, dict) or not all(isinstance(key, str) for key in parameters):
                raise BridgeError('invalid_parameters', 'Parameters must be an object with string keys.')
            # Desktop project loading ignores retired and unknown settings. Keep
            # this compatibility at the import boundary; live RPCs stay strict.
            if family == 'wolfrom':
                unsupported = set(parameters) & {'helix', 'double_style', 'profile_shift', 'module2', 'fixed_ring', 'one_rim'}
                if unsupported:
                    raise BridgeError('invalid_parameters', 'Unsupported Wolfrom parameter(s): '+', '.join(sorted(unsupported)))
            known = {spec[0] for variant in geometry.VARIANTS.get(family, {None: None})
                     for spec in geometry.get_specs(family, variant)} | option_definitions(family).keys()
            result = self.generate(family, {key: value for key, value in parameters.items() if key in known})
            result['ignored_parameters'] = sorted(parameters.keys() - known)
            return result
        if method == 'project':
            self.require(args)
            return dict(design_id=self.design_id, project=self.project())
        if method == 'pose': return self.pose(args)
        if method == 'export': return self.export(args)
        if method in ('documents', 'metrology', 'search_schema', 'search', 'search_apply', 'interference',
                      'backlash', 'proposal_apply', 'query_export', 'rates', 'motion_reset', 'pick', 'surface_distance'):
            return getattr(self, method)(args)
        if method == 'clear':
            self.design = self.plan = None
            self.invalidate_queries()
            self.design_id += 1
            return dict(cleared=True)
        raise BridgeError('unknown_method', 'Unknown engine method: '+str(method))


_engine = Engine()


def set_progress(callback):
    """Optional native/JS callback(message, fraction); synchronous worker progress.

    A callback cannot process queued cancellation messages during Python work.
    Cancellation continues to terminate the entire worker and its source design.
    """
    _engine.progress = callback if callback is not None else lambda message, fraction: None


def dispatch(method, payload, preview=None):
    """Return JSON metadata; retrieve indexed binary blocks before the next call."""
    try:
        if not isinstance(payload, str) or len(payload.encode('utf-8')) > MAX_INPUT_BYTES:
            raise BridgeError('resource_limit', 'RPC JSON exceeds 1 MiB.')
        args = json.loads(payload)
        if preview is not None:
            if method != 'export' or not isinstance(args, dict):
                raise BridgeError('invalid_arguments', 'Binary preview data is supported only for exports.')
            args['preview_png'] = preview
        result = _engine.call(method, args)
        return json_text(dict(ok=True, result=result, buffer_count=len(_engine.buffers)))
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        _engine.buffers.clear()
        return json_text(dict(ok=False, error=dict(code=getattr(error, 'code', 'invalid_parameters'), message=str(error))))


def buffer(index):
    return _engine.buffers[index]


def clear_buffers():
    _engine.buffers.clear()
