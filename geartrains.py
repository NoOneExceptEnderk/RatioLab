"""Reducers cilindrici ad assi fissi: geometria evolvente e alberi nominali."""
from math import pi, hypot
from geometry import gear_part, Part, circle
from engineering import mesh

def build_train(d):
    v = d.values
    variant = v['variant']
    double = variant == 'double'
    beta = v.get('helix', 0)
    m = v['module']
    w = v['width']
    pa = v['pressure']
    j = v['backlash']
    gap = v.get('gap', 0)
    if double and gap >= min(w, v.get('width2', w)) - 1:
        raise ValueError('The groove must leave at least 1 mm of teeth in each stage.')
    if v['wheel'] <= v['pinion']:
        raise ValueError('For a reducer, choose more driven wheel teeth than pinion teeth.')

    def pair(z1, z2, module, width, shift=0, extra=0, internal=False):
        return mesh(z1, z2, module, pa, beta, (width - gap) / 2 if double else width, shift, extra, internal, backlash=j)
    first = pair(v['pinion'], v['wheel'], m, w, v.get('profile_shift', 0), v.get('center_extra', 0), d.family == 'internal')
    d.analysis['meshes'] = [first]
    first['torque_factor'] = 1
    a1 = first['center_distance_mm']
    r1 = v['wheel'] / v['pinion']
    parts = []

    def gear(name, z, module, width, bore, center, phase=0, helix=0, zoff=0, internal=False, shift=0):
        p = gear_part(name, z, module, pa, j, width, bore, center, phase, helix, internal, v.get('rim', 5), zoff, shift)
        if double:
            p.double = True
            p.gap = gap
            p.core_radius = min((hypot(x, y) for x, y in p.outer)) * 0.96
            if not internal and bore / 2 >= p.core_radius - 0.25:
                raise ValueError('Bore too large for the continuous double helix hub.')
        d.parts.append(p)
        parts.append(p)
        return p

    def shaft(name, bore, start, end, center):
        if bore:
            d.parts.append(Part(name, circle(bore / 2), [], end - start, start, center, role='support', color=(0.65, 0.72, 0.8)))
    if d.family == 'internal':
        gear('Pinion_input', v['pinion'], m, w, v['bore'], (a1, 0), helix=beta)
        gear('Ring_output', v['wheel'], m, w, 0, (0, 0), pi / v['wheel'], beta, internal=True)
        shaft('Shaft_input', v['bore'], -8, w + 8, (a1, 0))
        d.analysis['signed_ratio'] = r1
        d.metrics = [f'Internal ring · reduction +{r1:.5g}:1', f'Centre distance {a1:.3f} mm · fixed axes, same rotation direction']
        d.requirements.append('Annular support, ring output flange, bearings, retainers and housing must be designed; no central shaft passes through the pinion.')
    else:
        x = v['profile_shift']
        gear('S1_Pinion', v['pinion'], m, w, v['bore'], (0, 0), helix=beta, shift=x)
        gear('S1_Wheel', v['wheel'], m, w, v['output_bore'], (a1, 0), pi + pi / v['wheel'], -beta, shift=-x)
        if d.family == 'parallel':
            d.analysis['signed_ratio'] = -r1
            shaft('Shaft_input', v['bore'], -8, w + 8, (0, 0))
            shaft('Shaft_output', v['output_bore'], -8, w + 8, (a1, 0))
            d.metrics = [f'Parallel shafts · reduction −{r1:.5g}:1', f'Centre distance {a1:.3f} mm · opposite rotation direction']
    if double:
        d.notes.append('Double helix: εβ is calculated on one active half, excluding the groove. Axial thrust cancellation assumes symmetric load sharing; Fa is the full torque reference for a single helix.')
    d.requirements.append('Nominal shafts without keys or retainers; supports, bearings, fasteners and housing must be designed. The automatic catalog does not yet apply to these two families.')
    d.notes.append('Total nominal pair backlash is shared between the two profiles. External profile shift is balanced, x1 = −x2; additional centre distance further increases backlash. No tool generated trochoidal fillets.')
