# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Validate a RatioLab package, then import it on Fusion's main thread.

The transport never supplies code or Fusion expressions. STEP snapshots are
hashed while copied into a private temporary directory before any SDK import.
"""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile
import uuid

MAX_MANIFEST = 16 * 1024 * 1024
MAX_STEP = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024


def _json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('Duplicate JSON key in import manifest')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Non-finite number in import manifest')
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Non-finite number in import manifest')
        return result
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def _sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-fA-F]{64}', value) is not None


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or '\x00' in value:
        raise ValueError('Invalid manifest ' + name)
    return value


def validate_manifest(path, expected_hash):
    """Return validated metadata and confined source paths; make no SDK calls."""
    path = Path(path)
    if not path.is_absolute() or not _sha(expected_hash):
        raise ValueError('An absolute manifest path and SHA256 are required')
    path = path.resolve(strict=True)
    with path.open('rb') as stream:
        content = stream.read(MAX_MANIFEST + 1)
    if len(content) > MAX_MANIFEST:
        raise ValueError('Import manifest exceeds the size limit')
    if hashlib.sha256(content).hexdigest() != expected_hash.lower():
        raise ValueError('Import manifest SHA256 mismatch')
    manifest = _json(content.decode('utf-8'))
    if (not isinstance(manifest, dict) or manifest.get('format') != 'ratiolab-fusion-import/1'
            or manifest.get('units') != 'mm'):
        raise ValueError('Unsupported RatioLab import format or units')
    try:
        uuid.UUID(manifest.get('id', ''))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Manifest id must be a UUID') from None
    _text(manifest.get('name'), 'name')
    _text(manifest.get('family'), 'family')
    if not isinstance(manifest.get('parameters'), dict):
        raise ValueError('Manifest parameters must be an object')
    if not isinstance(manifest.get('bom'), (dict, list)) or not isinstance(manifest.get('notes'), list):
        raise ValueError('Manifest BOM and notes are required')
    components = manifest.get('components')
    if not isinstance(components, list) or not 1 <= len(components) <= 512:
        raise ValueError('Import requires 1 to 512 components')
    paths, indices, total = [], set(), 0
    for part in components:
        if not isinstance(part, dict):
            raise ValueError('Invalid component record')
        index = part.get('index')
        if not isinstance(index, int) or isinstance(index, bool) or index < 1 or index in indices:
            raise ValueError('Component indices must be distinct positive integers')
        indices.add(index)
        _text(part.get('name'), 'component name')
        _text(part.get('role'), 'component role')
        if not isinstance(part.get('visible'), bool):
            raise ValueError('Component visibility must be boolean')
        color = part.get('color')
        if not isinstance(color, list) or len(color) != 3 or not all(_number(v) and 0 <= v <= 1 for v in color):
            raise ValueError('Component RGB values must be between 0 and 1')
        volume = part.get('expected_volume_mm3')
        if not _number(volume) or volume <= 0:
            raise ValueError('Component expected volume must be positive')
        bounds = part.get('expected_bounds_mm')
        if (not isinstance(bounds, list) or len(bounds) != 2
                or not all(isinstance(row, list) and len(row) == 3 and all(_number(v) for v in row) for row in bounds)
                or any(bounds[0][i] >= bounds[1][i] for i in range(3))):
            raise ValueError('Component expected bounds must enclose a 3D solid')
        relative = part.get('step')
        if not isinstance(relative, str) or '\x00' in relative or '\\' in relative or ':' in relative:
            raise ValueError('STEP paths must be confined relative paths')
        pure = PurePosixPath(relative)
        if (pure.is_absolute() or PureWindowsPath(relative).is_absolute()
                or '..' in pure.parts or not pure.parts or pure.suffix.lower() not in ('.step', '.stp')):
            raise ValueError('STEP paths must be confined relative .step/.stp files')
        source = (path.parent/relative).resolve(strict=True)
        try:
            source.relative_to(path.parent)
        except ValueError:
            raise ValueError('STEP path escapes the import package') from None
        if not source.is_file() or not _sha(part.get('sha256')):
            raise ValueError('STEP file and SHA256 are required')
        size = source.stat().st_size
        total += size
        if not 0 < size <= MAX_STEP or total > MAX_TOTAL:
            raise ValueError('STEP package exceeds the size limit')
        paths.append(source)
    return manifest, paths


@contextmanager
def staged_package(path, expected_hash):
    manifest, sources = validate_manifest(path, expected_hash)
    with tempfile.TemporaryDirectory(prefix='ratiolab-fusion-') as temporary:
        staged, total = [], 0
        for part, source in zip(manifest['components'], sources):
            target = Path(temporary)/(str(part['index']) + '.step')
            digest, size = hashlib.sha256(), 0
            with source.open('rb') as input_stream, target.open('xb') as output_stream:
                while True:
                    block = input_stream.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    total += len(block)
                    if size > MAX_STEP or total > MAX_TOTAL:
                        raise ValueError('STEP package exceeds the size limit')
                    digest.update(block)
                    output_stream.write(block)
            if digest.hexdigest() != part['sha256'].lower():
                raise ValueError('STEP SHA256 mismatch for component ' + str(part['index']))
            staged.append(target)
        yield manifest, staged


def collection_items(collection):
    # Fusion collections support count/item consistently across SDK releases.
    return [collection.item(i) for i in range(collection.count)]


def solid_metrics(occurrence):
    """Read geometry in occurrence context; Fusion internal lengths are cm."""
    bodies = []
    def visit(current):
        bodies.extend(collection_items(current.bRepBodies))
        for child in collection_items(current.childOccurrences):
            visit(child)
    visit(occurrence)
    if not bodies or any(not body.isSolid for body in bodies):
        raise ValueError('STEP import did not produce exclusively solid BRep bodies')
    volumes = [body.volume * 1000 for body in bodies]
    if any(not math.isfinite(value) or value <= 0 for value in volumes):
        raise ValueError('Imported bodies have invalid volume')
    boxes = [body.boundingBox for body in bodies]
    minimum = [min(getattr(box.minPoint, axis) * 10 for box in boxes) for axis in ('x', 'y', 'z')]
    maximum = [max(getattr(box.maxPoint, axis) * 10 for box in boxes) for axis in ('x', 'y', 'z')]
    if not all(math.isfinite(v) for v in minimum + maximum):
        raise ValueError('Imported bodies have invalid bounds')
    return dict(solid_bodies=len(bodies), volume_mm3=sum(volumes), bounds_mm=[minimum, maximum])


def check_metrics(part, metrics):
    # The exported analytic STEP volume can differ slightly from sampled
    # preview facets. These tolerances still reject mm/cm (10x/1000x) errors.
    expected = part['expected_volume_mm3']
    if abs(metrics['volume_mm3'] - expected) > max(.01, expected * .02):
        raise ValueError('Imported volume does not match the millimetre manifest for ' + part['name'])
    expected_bounds = part['expected_bounds_mm']
    span = max(expected_bounds[1][i] - expected_bounds[0][i] for i in range(3))
    tolerance = max(.02, span * .002)
    if any(abs(actual - expected) > tolerance
           for actual_row, expected_row in zip(metrics['bounds_mm'], expected_bounds)
           for actual, expected in zip(actual_row, expected_row)):
        raise ValueError('Imported bounds do not match the millimetre manifest for ' + part['name'])


def add_metadata(component, name, value):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    if component.attributes.add('RatioLab', name, text) is None:
        raise RuntimeError('Could not write RatioLab component metadata')


class FusionImporter:
    def __init__(self, app):
        self.app = app
        self.session_id = None
        self.documents = []

    def document_info(self):
        document = self.app.activeDocument
        if document is None:
            return None
        for previous, identifier in self.documents:
            if previous == document:
                return dict(id=identifier, name=document.name)
        identifier = getattr(document, 'creationId', None) or str(uuid.uuid4())
        # Copied documents can share creationId; distinguish those open in the
        # same bridge session using retained native references, not wrapper ids.
        if any(identifier == key for _, key in self.documents):
            identifier = str(uuid.uuid4())
        self.documents.append((document, identifier))
        return dict(id=identifier, name=document.name)

    def handle(self, method, params):
        if method == 'status':
            return dict(application='Fusion', version=self.app.version,
                        document=self.document_info(), bridge_session=self.session_id)
        if method != 'import_model':
            raise ValueError('Unsupported bridge method')
        return self.import_model(params)

    def ready_design(self, document_id):
        import adsk.fusion
        info = self.document_info()
        if info is None:
            raise ValueError('Open a Fusion design before importing RatioLab components')
        if not isinstance(document_id, str) or document_id != info['id']:
            raise ValueError('The active Fusion document changed; refresh the connection before importing')
        command = self.app.userInterface.activeCommand
        if command not in ('', 'SelectCommand'):
            raise ValueError('Fusion is busy: finish the active command before importing')
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if design is None:
            raise ValueError('Activate a Fusion Design document before importing')
        for edit in (getattr(self.app, 'activeEditObject', None),
                     getattr(design, 'activeEditObject', None)):
            if edit is not None and adsk.fusion.Sketch.cast(edit) is not None:
                raise ValueError('Finish editing the active Fusion sketch before importing')
        return design, info

    def import_model(self, params):
        import adsk.core
        document_id = params.get('document_id')
        self.ready_design(document_id)
        path, digest = params.get('manifest_path'), params.get('manifest_sha256')
        if not isinstance(path, str):
            raise ValueError('An absolute manifest path is required')
        with staged_package(path, digest) as (manifest, paths):
            design, info = self.ready_design(document_id)
            top = None
            try:
                try:
                    top = design.rootComponent.occurrences.addNewComponent(adsk.core.Matrix3D.create())
                except RuntimeError as error:
                    raise RuntimeError('Fusion cannot create the assembly here; use an editable hybrid design: ' + str(error)) from error
                if top is None:
                    raise RuntimeError('Fusion could not create a RatioLab assembly; use an editable hybrid design')
                group = top.component
                group.name = manifest['name'] + ' · ' + str(uuid.uuid4())[:8]
                results = []
                for part, step in zip(manifest['components'], paths):
                    occurrence = group.occurrences.addNewComponent(adsk.core.Matrix3D.create())
                    if occurrence is None:
                        raise RuntimeError('Fusion could not create a component')
                    occurrence.component.name = part['name']
                    options = self.app.importManager.createSTEPImportOptions(str(step))
                    if options is None:
                        raise RuntimeError('Fusion could not prepare the STEP import')
                    options.isViewFit = False
                    manager = self.app.importManager
                    if hasattr(manager, 'importToTarget2'):
                        imported = manager.importToTarget2(options, occurrence.component)
                        if imported is None:
                            raise RuntimeError('Fusion STEP import failed for ' + part['name'])
                    elif not manager.importToTarget(options, occurrence.component):
                        raise RuntimeError('Fusion STEP import failed for ' + part['name'])
                    metrics = solid_metrics(occurrence)
                    check_metrics(part, metrics)
                    occurrence.isLightBulbOn = part['visible']
                    add_metadata(occurrence.component, 'component', part)
                    results.append(dict(index=part['index'], name=part['name'], **metrics))
                for key in ('id', 'family', 'parameters', 'bom', 'notes'):
                    add_metadata(group, key, manifest[key])
                add_metadata(group, 'units', 'mm')
                return dict(document=info, group_name=group.name, components=results,
                            manifest_id=manifest['id'])
            except Exception as error:
                if top is not None:
                    try:
                        if top.deleteMe() is False:
                            raise RuntimeError('Fusion refused to delete the new occurrence')
                    except Exception as rollback:
                        raise RuntimeError('Import failed and the new RatioLab group could not be removed: '
                                           + str(rollback) + '; original error: ' + str(error)) from error
                raise
