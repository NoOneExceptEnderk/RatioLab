#!/usr/bin/env python3
"""Precompute canonical RatioLab surfaces and rigid poses, without a hosted engine."""
import hashlib
import json
import math
import subprocess
import os
import struct
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'src'
PARAMETERS = {'sun': 24, 'planet': 24, 'input_rpm': 60}
INCLUDE = {'S1_Sun', 'S1_Planet_1', 'S1_Planet_2', 'S1_Planet_3', 'S1_Ring',
           'S1_PlanetCarrier_lower', 'S1_Pin_planet_1', 'S1_Pin_planet_2', 'S1_Pin_planet_3', 'Shaft_input'}
SCENES = {
    'planetary': {'title': 'Planetary gearbox', 'family': 'planetary', 'parameters': PARAMETERS,
                  'include': INCLUDE,
                  'members': {'input': 'Sun gear', 'fixed': 'Ring gear', 'output': 'Planet carrier'},
                  'specs': [{'label': 'Sun / planet / ring', 'value': '24 / 24 / 72 teeth'},
                            {'label': 'Arrangement', 'value': '3 planets · fixed ring'}],
                  'scope': 'Housing, covers, retainers and the upper carrier flange are hidden to reveal the mechanism.'},
    'cycloidal': {'title': 'Cycloidal drive', 'family': 'cycloidal',
                  'parameters': {'variant': 'single', 'pins': 16, 'input_rpm': 60},
                  'include': {'Disc_cycloidal_1', 'Eccentric_1', 'Bearing_eccentric_1_envelope', 'Shaft_input', 'Shaft_output'}
                             | {f'Roller_ring_{i}' for i in range(1, 17)} | {f'Pin_output_{i}' for i in range(1, 7)},
                  'members': {'input': 'Eccentric shaft', 'fixed': 'Ring rollers', 'output': 'Output pins / shaft'},
                  'specs': [{'label': 'Disc / ring', 'value': '15 lobes / 16 rollers'},
                            {'label': 'Eccentricity', 'value': '1.2 mm · single disc'}],
                  'scope': 'Housing, covers and the opaque output flange are hidden to expose the eccentric disc and output pins. Output pins and shaft retain their canonical motion.'},
    'worm': {'title': 'Worm drive', 'family': 'worm',
             'parameters': {}, 'binary': True,
             'include': {'Screw_ZA', 'Wheel_generated'},
             'members': {'input': 'ZA worm · X axis', 'fixed': 'Shaft axes / support frame (not shown)', 'output': 'Generated wheel · Z axis'},
             'specs': [{'label': 'Worm / wheel', 'value': '1 start / 30 teeth'},
                       {'label': 'Arrangement', 'value': 'Crossed axes · cylindrical ZA'},
                       {'label': 'Default dimensions', 'value': 'Worm Ø20 × 24 mm · wheel width 10 mm · module 2 mm'}],
             'scope': 'Canonical generated ZA worm and mating wheel; supports are not part of this generated assembly. Signed rotation is measured about the different shaft axes, not a same-axis direction comparison.'},
    'parallel': {'title': 'Helical reducer', 'family': 'parallel',
                 'parameters': {'variant': 'helical', 'pinion': 20, 'wheel': 60, 'helix': 20, 'input_rpm': 60},
                 'include': {'S1_Pinion', 'S1_Wheel', 'Shaft_input', 'Shaft_output'},
                 'members': {'input': 'Helical pinion / input shaft', 'fixed': 'Shaft axes / support frame (not shown)', 'output': 'Wheel / output shaft'},
                 'specs': [{'label': 'Pinion / wheel', 'value': '20 / 60 teeth'},
                           {'label': 'Helix angle', 'value': '20° · parallel shafts'}],
                 'scope': 'Complete canonical single-stage helical train with both shafts; housing and supports are not part of this generated assembly.'},
    'harmonic': {'title': 'Strain wave drive', 'family': 'harmonic', 'parameters': {}, 'binary': True,
                 'include': {'Flexspline_cup', 'Circular_spline_generated', 'Bearing_wave_envelope', 'Generator_wave_prescribed'},
                 'members': {'input': 'Wave generator', 'fixed': 'Circular spline', 'output': 'Flexible cup'},
                 'specs': [{'label': 'Flex / circular spline', 'value': '60 / 62 teeth'},
                           {'label': 'Motion', 'value': 'Prescribed material deformation'}],
                 'scope': 'Default cup assembly with all four canonical parts. Flexspline material coordinates follow the canonical prescribed map; this is not an elastic analysis.'},


}
PHASES = (0, 0.7, 2.1, 2*math.pi, -1.3, 11.2)


def source_provenance():
    """Record source inputs rather than claiming uncommitted output is a release."""
    hashes = {path.relative_to(SOURCE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(SOURCE.rglob('*')) if path.suffix in ('.py', '.json') and path.is_file()}
    revision = subprocess.check_output(['git', '-C', str(SOURCE.parent), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(SOURCE.parent), 'status', '--porcelain', '--untracked-files=normal', '--', 'src'], text=True).strip())
    return {'sourceCommit': revision, 'sourceDirty': dirty, 'sourceHashes': hashes,
            'sourceHashScope': 'All Python and JSON inputs under the canonical src directory; hashes identify the exact local source snapshot, including any uncommitted changes.'}


def pose_matrix(descriptor, phase):
    """Schema v2: column-major rigid rotation, then an optional orbital translation."""
    from motion import IDENTITY, multiply, rotation, transform, translation
    if descriptor['kind'] == 'fixed':
        return IDENTITY
    spin = descriptor['rotation']
    matrix = rotation(spin['rate']*phase, spin['axis'], spin['pivot'])
    if descriptor['kind'] == 'orbital':
        orbit = descriptor['orbit']
        point = transform(rotation(orbit['rate']*phase, orbit['axis'], orbit['pivot']), orbit['center'])
        offset = [point[i]-orbit['center'][i] for i in range(3)]
        matrix = multiply(translation(*offset), matrix)
    return matrix


def motion_descriptor(design, plan, index):
    """Explicitly map only the supported canonical plan branches; reject drift."""
    from motion import part_axis
    part = design.parts[index]
    rates = plan.rates.get(index)
    if index in plan.warps:
        raise ValueError('Unknown nonrigid motion is not supported by the static showcase')
    if index in plan.flex:
        descriptor = {'kind': 'fixed'}
    elif not rates or not any(rates):
        descriptor = {'kind': 'fixed'}
    else:
        pivot, axis = part_axis(part)
        spin, orbit = rates[0], None
        if (design.family == 'planetary' and part.name.startswith('S1_Planet_')) or part.name.startswith('Disc_cycloidal'):
            spin, orbit = rates
        elif design.family == 'cycloidal' and part.name.startswith('Bearing_eccentric'):
            spin, orbit = 0, rates[0]
        elif design.family in ('planetary', 'cycloidal', 'harmonic'):
            pivot = (0, 0, 0)
        if design.family == 'worm' and part.name.startswith('Screw_'):
            pivot, axis = (0, 0, part.z), (1, 0, 0)
        descriptor = {'kind': 'orbital' if orbit is not None else 'rigid',
                      'rotation': {'axis': list(axis), 'pivot': list(pivot), 'rate': spin}}
        if orbit is not None:
            descriptor['orbit'] = {'axis': [0, 0, 1], 'pivot': [0, 0, 0],
                                   'center': [*part.center, 0], 'rate': orbit}
    for phase in PHASES:
        if any(abs(a-b) > 1e-10 for a, b in zip(pose_matrix(descriptor, phase), plan.matrix(index, phase))):
            raise ValueError(f'Unsupported canonical pose: {part.name}')
    return descriptor


def generate_scene(scene_id='planetary', provenance=None):
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))
    from geometry import generate
    from motion import build_plan
    from stl_export import triangles
    config = SCENES[scene_id]
    design = generate(config['family'], config['parameters'])
    plan = build_plan(design)
    if not plan.supported:
        raise ValueError(plan.message)
    if config['include'] - {part.name for part in design.parts}:
        raise ValueError('A selected canonical part is missing')
    meshes = []
    bounds = [[float('inf')] * 3, [float('-inf')] * 3]
    for index, part in enumerate(design.parts):
        if part.name not in config['include']:
            continue
        vertices, normals, indices, materials, lookup = [], [], [], [], {}
        binary = config.get('binary', False)
        references = {}
        if index in plan.flex:
            from wave_geometry import material_vertices
            references = material_vertices(part)
        for triangle in triangles(part):
            a, b, c = triangle
            u = [b[i] - a[i] for i in range(3)]
            v = [c[i] - a[i] for i in range(3)]
            normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            length = math.sqrt(sum(value*value for value in normal))
            if length < 1e-12:
                continue
            normal = tuple(float32(value/length) if binary else round(value/length, 6) for value in normal)
            for vertex in triangle:
                point = tuple(float32(value) if binary else round(value, 5) for value in vertex)
                key = point + normal
                if key not in lookup:
                    lookup[key] = len(vertices)//3
                    vertices.extend(point)
                    normals.extend(normal)
                    if references:
                        materials.extend(float32(value) for value in references[tuple(vertex)])
                indices.append(lookup[key])
                for axis in range(3):
                    bounds[0][axis] = min(bounds[0][axis], point[axis])
                    bounds[1][axis] = max(bounds[1][axis], point[axis])
        descriptor = motion_descriptor(design, plan, index)
        mesh = {'name': part.name, 'partName': part.name, 'sourceIndex': index,
                'positions': vertices, 'normals': normals, 'indices': indices,
                'color': list(part.color), 'role': part.port.get('role', part.role),
                'member': part.port.get('member'), 'transform': descriptor}
        if materials:
            flex, wave, a, b, rp, length, diaphragm = plan.deformation(index, 0)
            mesh['materials'] = materials
            mesh['deformation'] = {'kind': 'strain-wave', 'flexRate': plan.rates[index][0],
                                   'waveRate': plan.rates[index][1], 'flexOffset': flex, 'waveOffset': wave,
                                   'ellipseAxes': [a, b], 'pitchRadius': rp, 'bodyLength': length,
                                   'diaphragm': diaphragm, 'center': [*part.center, 0],
                                   'arcCoefficients': design.analysis['wave_mapping']['arc_coefficients']}
            for phase in PHASES:
                expected = plan.deformation(index, phase)
                actual = (flex+mesh['deformation']['flexRate']*phase, wave+mesh['deformation']['waveRate']*phase, a, b, rp, length, diaphragm)
                if any(abs(x-y) > 1e-12 for x,y in zip(actual, expected)):
                    raise ValueError('Unsupported canonical strain-wave deformation')
        if scene_id == 'planetary':
            # Compatibility with the existing renderer while the v2 client is reviewed.
            orbital = descriptor['kind'] == 'orbital'
            mesh['center'] = descriptor['rotation']['pivot'] if descriptor['kind'] != 'fixed' else [0, 0, 0]
            mesh['rotation'] = {'axis': [0, 0, 1], 'speed': plan.rates.get(index, (0,))[0]}
            if orbital:
                mesh['orbit'] = {'speed': descriptor['orbit']['rate'], 'center': [*part.center, 0]}
        meshes.append(mesh)
    signed_ratio = design.analysis['signed_ratio']
    direction = ('Crossed axes: positive X input / positive Z output' if scene_id == 'worm'
                 else 'Same direction' if signed_ratio > 0 else 'Opposite direction')
    metadata = {'format': 'ratiolab-showcase/3' if config.get('binary') else 'ratiolab-showcase/2', 'id': scene_id, 'title': config['title'],
                'units': 'mm', 'family': config['family'],
                'sourceRepository': 'https://github.com/NoOneExceptEnderk/RatioLab',
                'copyright': 'Copyright (C) 2026 NoOneExceptEnderk', 'license': 'GPL-3.0-only',
                'parameters': design.values, 'referenceRPM': plan.reference_rpm,
                'ratio': signed_ratio, 'signedRatio': signed_ratio, 'ratioMagnitude': abs(signed_ratio),
                'ratesRPM': design.analysis['kinematics'].get('rates_rpm', design.analysis['kinematics'].get('stage_results', [{}])[0].get('rates_rpm', {}) if design.analysis['kinematics'].get('stage_results') else {}),
                'direction': direction, 'members': config['members'], 'specs': config['specs'],
                'motion': 'Phase is the canonical reference angle in radians. Column-major rigid/orbital transforms apply rotation about axis/pivot, then optional orbital translation R_orbit(center)-center. Strain-wave material deformation precedes its fixed matrix, including tangent-frame normal transport. Rates are radians per phase radian; deformation offsets are explicit.',
                'scope': config['scope'] + ' Actual sampled RatioLab geometry and nominal kinematics; no load or complete-cycle collision validation.',
                'omittedParts': [part.name for part in design.parts if part.name not in config['include']],
                **(provenance if provenance is not None else source_provenance())}
    if scene_id == 'planetary':
        metadata['teeth'] = {'sun': design.values['sun'], 'planet': design.values['planet'], 'ring': design.values['sun']+2*design.values['planet']}
    return {'meshes': meshes, 'bounds': {'min': bounds[0], 'max': bounds[1]}, 'metadata': metadata}


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def encode_scene(scene):
    return json.dumps(scene, separators=(',', ':'), allow_nan=False) + '\n'


def asset_payloads(scene_id, scene):
    """Binary streams preserve every Float32 sample and every triangle index."""
    if not SCENES[scene_id].get('binary'):
        return {f'{scene_id}.json': encode_scene(scene).encode()}
    public = {**scene, 'meshes': []}
    raw = bytearray()
    for mesh in scene['meshes']:
        item = {key: value for key, value in mesh.items() if key not in ('positions', 'normals', 'indices', 'materials')}
        item['bufferViews'] = {}
        for field in ('positions', 'normals', 'indices', 'materials'):
            if field not in mesh:
                continue
            values = mesh[field]
            integer = field == 'indices'
            item['bufferViews'][field] = {'byteOffset': len(raw), 'length': len(values),
                                          'componentType': 'uint32' if integer else 'float32'}
            raw.extend(struct.pack('<'+('I' if integer else 'f')*len(values), *values))
        public['meshes'].append(item)
    public['geometryBuffer'] = {'uri': f'{scene_id}.bin', 'byteLength': len(raw),
                                'sha256': hashlib.sha256(raw).hexdigest(), 'byteOrder': 'little-endian'}
    return {f'{scene_id}.json': encode_scene(public).encode(), f'{scene_id}.bin': bytes(raw)}


def load_scene(scene_id):
    """Authoring-side decoder, also used to verify the public binary contract."""
    scene = json.loads((ROOT / f'assets/{scene_id}.json').read_text())
    if 'geometryBuffer' in scene:
        info = scene['geometryBuffer']
        if info['uri'] != f'{scene_id}.bin' or info['byteOrder'] != 'little-endian':
            raise ValueError('Unknown geometry buffer')
        raw = (ROOT / 'assets' / info['uri']).read_bytes()
        if len(raw) != info['byteLength'] or hashlib.sha256(raw).hexdigest() != info['sha256']:
            raise ValueError('Corrupt geometry buffer')
        for mesh in scene['meshes']:
            for field, view in mesh['bufferViews'].items():
                code = 'I' if view['componentType'] == 'uint32' else 'f'
                mesh[field] = list(struct.unpack_from('<'+code*view['length'], raw, view['byteOffset']))
    return scene


def main():
    provenance = source_provenance()
    scenes = {scene_id: generate_scene(scene_id, provenance) for scene_id in SCENES}
    payloads = {name: data for scene_id, scene in scenes.items() for name, data in asset_payloads(scene_id, scene).items()}
    if provenance != source_provenance():
        raise ValueError('Canonical source changed during generation; regenerate from one stable snapshot')
    # Budget is diagnostic only: user-requested canonical dimensions take precedence.
    # Stage every validated payload before replacing any public output.
    staged = []
    try:
        for name, data in payloads.items():
            target = ROOT / 'assets' / name
            fd, temporary = tempfile.mkstemp(prefix='.'+name+'-', dir=target.parent)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                os.fchmod(handle.fileno(), 0o644)
            staged.append((temporary, target))
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            if os.path.exists(temporary):
                os.unlink(temporary)
    for scene_id, scene in scenes.items():
        size = sum(len(data) for name, data in payloads.items() if name in (f'{scene_id}.json', f'{scene_id}.bin'))
        print(f'3D {scene_id}: {len(scene["meshes"])} genuine meshes, {sum(len(mesh["indices"])//3 for mesh in scene["meshes"])} triangles, {size:,} bytes')


if __name__ == '__main__':
    main()
