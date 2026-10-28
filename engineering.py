"""Geometria e statica nominale. Unità: mm, N, N·m, rpm, W.

Fonti, convenzioni e dominio delle formule in CALCOLI.md.
Nessuna verifica ISO/AGMA di resistenza o distribuzione elastica del load.
"""
from math import pi, sin, cos, tan, atan, acos, sqrt, radians, degrees
LOAD_FIELDS = [('input_rpm', 'Input speed [rpm]', 1500, 0, 100000, 50), ('input_torque', 'Input torque [N·m]', 1, 0, 10000, 0.1), ('efficiency', 'Assumed overall efficiency [%]', 90, 1, 100, 1)]

def gear_dimensions(z, m, pressure=20, beta=0, x=0, ha=1, hf=1.25, backlash=0.15):
    b = radians(beta)
    an = radians(pressure)
    mt = m / cos(b)
    at = atan(tan(an) / cos(b))
    r = mt * z / 2
    from tooth_profiles import rack_parameters
    tool=rack_parameters(z,mt,degrees(at),backlash=backlash,depth=m,shift=x,normal_pressure=pressure,hf=hf)
    rack_minimum=(hf*m-tool['tip_radius']*(1-sin(an))-r*sin(at)**2)/m
    return dict(rack_minimum_shift=rack_minimum, teeth=z, mn=m, mt=mt, alpha_n=pressure, alpha_t=degrees(at), beta=beta, x=x, pitch_radius=r, base_radius=r * cos(at), tip_radius=r + m * (ha + x), root_radius=r - m * (hf - x), virtual_teeth=z / cos(b) ** 3, minimum_shift=ha - z / cos(b) ** 3 * sin(an) ** 2 / 2, normal_thickness=m * (pi / 2 + 2 * x * tan(an)))


def gear_warnings(gear):
    """Use calculated geometry, rather than translated note text, for warnings."""
    if gear['x'] < gear['rack_minimum_shift']:
        return [
            f"Rounded-rack undercut: minimum x {gear['rack_minimum_shift']:.3f}; "
            f"indicative virtual-tooth limit {gear['minimum_shift']:.3f}. Actual trimming is reported per part."
        ]
    return []


def geometry_warnings(design):
    warnings = []
    if 'gear' in design.analysis:
        warnings.extend(gear_warnings(design.analysis['gear']))
    for pair in design.analysis.get('meshes', []):
        warnings.extend(pair.get('warnings', []))
    return list(dict.fromkeys(warnings))


def mesh(z1, z2, m, pressure=20, beta=0, width=10, x=0, center_extra=0, internal=False, gap=0, strict=True, backlash=0):
    """Correzione bilanciata x1=x, x2=-x solo esterni; centre distance di lavoro esplicito."""
    a1 = gear_dimensions(z1, m, pressure, beta, x, backlash=backlash)
    a2 = gear_dimensions(z2, m, pressure, beta, 0 if internal else -x, backlash=backlash)
    if internal:
        a2.update(tip_radius=a2['pitch_radius'] - m, root_radius=a2['pitch_radius'] + 1.25 * m, internal=True)
    r1 = a1['pitch_radius']
    r2 = a2['pitch_radius']
    at = radians(a1['alpha_t'])
    a0 = r2 - r1 if internal else r1 + r2
    a = a0 + center_extra
    if a <= 0 or a0 * cos(at) > a:
        raise ValueError('Centre distance incompatible with the base circles.')
    aw = acos(a0 * cos(at) / a)
    ra1 = a1['tip_radius']
    rb1 = a1['base_radius']
    ra2 = r2 - m if internal else a2['tip_radius']
    rb2 = a2['base_radius']
    if ra1 <= rb1 or ra2 <= rb2:
        raise ValueError('Tip circle below the base circle: unsupported gear pair.')
    g1 = sqrt(ra1 * ra1 - rb1 * rb1)
    g2 = sqrt(ra2 * ra2 - rb2 * rb2)
    path = g1 - g2 + a * sin(aw) if internal else g1 + g2 - a * sin(aw)
    ea = path / (pi * a1['mt'] * cos(at))
    effective = (width - gap) / 2 if gap else width
    eb = effective * abs(sin(radians(beta))) / (pi * m)
    inv = lambda t: tan(t) - t
    added = 2 * a * (inv(aw) - inv(at)) if not internal else None
    warnings = []
    if ea <= 0:
        raise ValueError('No usable involute contact path.')
    if ea + eb < 1:
        raise ValueError('Total contact ratio below 1: increase tooth count/width or reduce centre distance.')
    if not internal and max(g1, g2) > a * sin(aw) + 1e-09:
        raise ValueError('Interference below the base circle: increase tooth counts or apply profile shift.')
    if internal:
        if z2 - z1 <= 9:
            raise ValueError('Internal ring: tooth count difference must exceed 9; closely spaced counts require a dedicated trochoidal check.')
        if g2 < a * sin(aw):
            if strict:
                raise ValueError('Internal involute interference at the pinion: increase planet/pinion tooth count.')
            warnings.append('Internal involute interference: theoretical contact extends below the planet base circle. The generated root does not establish a valid internal contact path; increase tooth count or redesign the pair.')
        warnings.append('Axial ring assembly; the tangent root construction is not a pinion-cutter envelope. Check involute, trochoid and trimming interference for the actual cutter.')
    for k, g in enumerate((a1, a2), 1):
        if internal and k == 2:
            continue
        if g['x'] + 1e-09 < g['rack_minimum_shift']:
            warnings.append(f'Wheel {k}: rounded-rack undercut; actual envelope and trimming are recorded per part.')
    from tooth_profiles import external_half, internal_half
    endpoints=lambda fn,a,b:[fn(a),fn(b)]
    def usable(g,ring=False):
        if ring:
            _,info=internal_half(g['teeth'],g['mt'],g['alpha_t'],backlash,m,1,1.25,endpoints)
            return sqrt(max(0,info['involute_end_radius_mm']**2-g['base_radius']**2))
        _,info=external_half(g['teeth'],g['mt'],g['alpha_t'],backlash,m,g['x'],pressure,1,1.25,endpoints)
        return sqrt(max(0,info['involute_start_radius_mm']**2-g['base_radius']**2))
    lower1=usable(a1);bound2=usable(a2,internal);span=a*sin(aw)
    lower=max(lower1,g2-span if internal else span-g2)
    upper=min(g1,bound2-span if internal else span-bound2)
    usable_ea=max(0,upper-lower)/(pi*a1['mt']*cos(at))
    if usable_ea+eb<1:
        warnings.append('Usable involute contact ratio after root trimming/blending is below 1; nominal tip/base-circle ratio overstates the active flank. This configuration is a geometric study.')
    return dict(profile_contact_transverse=usable_ea, profile_contact_total=usable_ea+eb,
                profile_contact_basis='intersection of usable involute intervals after root envelope/blend; excludes fillet contact, elastic deflection and 3D interference',
                z1=z1, z2=z2, internal=internal, center_distance_mm=a, reference_center_mm=a0, working_pressure_deg=degrees(aw), contact_transverse=ea, contact_overlap=eb, contact_total=ea + eb, extra_backlash_mm=added, nominal_pair_backlash_mm=backlash, working_pair_backlash_mm=backlash * a / a0 + (added or 0), gear1=a1, gear2=a2, warnings=warnings)

def force_components(torque, diameter, pressure, beta=0):
    ft = 2000 * abs(torque) / diameter
    return dict(tangential_N=ft, radial_N=ft * tan(radians(pressure)), axial_N=ft * tan(radians(beta)))

def attach_report(d):
    v = d.values
    r = d.analysis
    rpm = v['input_rpm']
    torque = v['input_torque']
    eta = v.get('efficiency', 100) / 100
    ratio = r.get('signed_ratio')
    r['input'] = dict(rpm=rpm, torque_Nm=torque, power_W=torque * rpm * 2 * pi / 60)
    r['assumed_efficiency'] = eta
    if ratio is not None:
        r['output'] = dict(rpm=rpm / ratio, torque_magnitude_Nm=torque * abs(ratio) * eta, power_W=r['input']['power_W'] * eta)
        d.metrics.append(f"Nominal output {rpm / ratio:.2f} rpm · estimated torque {r['output']['torque_magnitude_Nm']:.3f} N·m (assumed η {eta * 100:g}%)")
    if r.get('differential'):
        r['input']['scope'] = 'primary port only; no combined power balance'
        d.notes.append('Operating speed and power refer only to the primary input; total power balance and differential output torques cannot be calculated without loads and power for the other members.')
    if r.get('meshes'):
        for i, q in enumerate(r['meshes']):
            if q.get('torque_factor') is not None:
                tq = torque * q['torque_factor'] * eta ** q.get('loss_exponent', 0)
                diameter = 2 * q['gear1']['pitch_radius'] * q['center_distance_mm'] / q['reference_center_mm']
                q['forces'] = force_components(tq, diameter, q['working_pressure_deg'], q['gear1']['beta'])
            d.metrics.append(f"Mesh {i + 1}: εα {q['contact_transverse']:.3f} · εβ {q['contact_overlap']:.3f} · αw {q['working_pressure_deg']:.2f}°")
            d.notes.extend(q['warnings'])
            if 'forces' in q:
                f = q['forces']
                d.notes.append(f"Mesh {i + 1}, nominal forces: Ft {f['tangential_N']:.2f} N, Fr {f['radial_N']:.2f} N, Fa {f['axial_N']:+.2f} N. Absolute radial/tangential values; axial sign follows pinion handedness.")
    d.notes.append('Torque, speed and efficiency are assumed operating data. Nominal statics only: no impacts, dynamic factors, elastic load sharing, ISO/AGMA strength checks, allowable loads or bearing life calculations. The speed sign indicates relative direction.')
    return r

def report_text(d):
    r = d.analysis
    lines = ['NOMINAL CALCULATION REPORT · SOLIDCRAFT REDUCERS', d.family, '']
    lines += d.metrics + ['']
    load = r['input']
    if 'rpm' in load:
        lines.append(f"Input: {load['rpm']:g} rpm · {load['torque_Nm']:g} N·m · {load['power_W']:.3f} W")
    if 'signed_ratio' in r:
        lines.append(f"Ratio i = input speed / output speed = {r['signed_ratio']:.6g}; negative = opposite rotation.")
    for i, q in enumerate(r.get('meshes', []), 1):
        lines.append(f"Mesh {i}: Z {q['z1']}/{q['z2']} · centre distance {q['center_distance_mm']:.6f} mm · αw {q['working_pressure_deg']:.6f}°")
        lines.append(f"  εα {q['contact_transverse']:.6f} · εβ {q['contact_overlap']:.6f} · ε total {q['contact_total']:.6f}")
        lines.append(f"  Usable involute after root trimming/blending: εα {q['profile_contact_transverse']:.6f} · ε total {q['profile_contact_total']:.6f}; no fillet-contact or 3D collision solution.")
        for k in ('gear1', 'gear2'):
            g = q[k]
            lines.append(f"  {k}: mn {g['mn']:g} · mt {g['mt']:.6f} mm · αn {g['alpha_n']:g}° · αt {g['alpha_t']:.6f}° · x {g['x']:g}")
        if q.get('extra_backlash_mm') is not None:
            lines.append(f"  Backlash from increased centre distance: {q['extra_backlash_mm']:.6f} mm; total working backlash {q['working_pair_backlash_mm']:.6f} mm.")
        if 'forces' in q:
            lines.append('  Nominal forces: ' + ', '.join((f'{k} = {v:.3f}' for k, v in q['forces'].items())))
    for p in r.get('tooth_profiles', []):
        lines.append(f"Profile {p['part']}: {p['method']} · chord threshold {p['chord_threshold_mm']:g} mm")
        if 'tool' in p:
            tool=p['tool']
            lines.append(f"  Rack normal tip radius {tool['tip_radius']:.6f} mm · shift {tool['shift']:g} · undercut trimmed {p['undercut_trimmed']} · usable involute starts at R {p['involute_start_radius_mm']:.6f} mm.")
        elif 'blend_radius_mm' in p:
            lines.append(f"  Internal blend radius {p['blend_radius_mm']:.6f} mm (nominal {p['nominal_blend_radius_mm']:.6f}; adapted {p['blend_radius_adapted']}); not cutter generated.")
        lines.append('  Domain: '+p['domain'])
    if 'wave_mapping' in r:
        lines.append('Strain wave: '+r['wave_mapping']['method']+'; eight arc Fourier modes; no conjugate or elastic solution.')
    if 'wheel_geometry' in r:
        q=r['wheel_geometry'];lines.append(f"Wheel: {q['method']} · cylinder R {q['radius_mm']:.6f} mm · edge sag {q['max_radial_sag_mm']:.6f} mm · axial chord threshold {q['axial_chord_threshold_mm']:g} mm; no conjugate flank solution.")
    if 'forces' in r:
        lines.append('Reference forces: ' + ', '.join((f'{k} = {v:.3f}' for k, v in r['forces'].items())))
    lines += ['', 'ASSUMPTIONS AND LIMITATIONS'] + d.notes + ['', 'Sources and formulas: CALCOLI.md. No result is an allowable load or ISO/AGMA certification.']
    return '\n'.join(lines) + '\n'
