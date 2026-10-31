# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nominal geometry and statics. Units: mm, N, N·m, rpm and W.

Sources, conventions and formula domains are in docs/technical/calculations.md.
No ISO/AGMA strength verification or elastic load-distribution analysis.
"""
from math import pi, sin, cos, tan, atan, acos, sqrt, radians, degrees
LOAD_FIELDS = [('input_rpm', 'Input speed [rpm]', 1500, 0, 100000, 50), ('input_torque', 'Input torque [N·m]', 1, 0, 10000, 0.1), ('efficiency', 'Assumed overall efficiency [%]', 90, 1, 100, 1)]

def gear_dimensions(z, m, pressure=20, beta=0, x=0, ha=1, hf=1.25, backlash=0.15, internal=False):
    """Cylindrical dimensions; ``normal_thickness`` remains nominal for compatibility."""
    b = radians(beta)
    an = radians(pressure)
    mt = m / cos(b)
    at = atan(tan(an) / cos(b))
    r = mt * z / 2
    from tooth_profiles import rack_parameters
    tool=rack_parameters(z,mt,degrees(at),backlash=backlash,depth=m,shift=x,normal_pressure=pressure,hf=hf)
    rack_minimum=(hf*m-tool['tip_radius']*(1-sin(an))-r*sin(at)**2)/m
    nominal = m * (pi / 2 + 2 * x * tan(an))
    return dict(rack_minimum_shift=rack_minimum, teeth=z, mn=m, mt=mt, alpha_n=pressure, alpha_t=degrees(at), beta=beta, x=x, pitch_radius=r, base_radius=r * cos(at), tip_radius=r-m*ha if internal else r+m*(ha+x), root_radius=r+m*hf if internal else r-m*(hf-x), internal=internal, virtual_teeth=z / cos(b) ** 3, minimum_shift=ha - z / cos(b) ** 3 * sin(an) ** 2 / 2, normal_thickness=nominal,
                nominal_reference_normal_thickness_mm=nominal,
                reference_normal_thickness_with_allowance_mm=nominal-backlash*cos(b)/2,
                nominal_reference_transverse_thickness_mm=nominal/cos(b),
                reference_transverse_thickness_with_allowance_mm=nominal/cos(b)-backlash/2,
                reference_thickness_basis='theoretical reference arcs; useful generated involute must be checked separately')


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


def mesh(z1, z2, m, pressure=20, beta=0, width=10, x=0, center_extra=0, internal=False, gap=0, strict=True, backlash=0, internal_plan=None):
    """Balance x1=x, x2=-x for external pairs only; use explicit working distance."""
    a1 = gear_dimensions(z1, m, pressure, beta, x, backlash=backlash)
    a2 = gear_dimensions(z2, m, pressure, beta, 0 if internal else -x, backlash=backlash, internal=internal)
    if internal_plan is not None:
        expected=dict(zp=z1,zr=z2,mn=m,alpha_n_deg=pressure,beta_deg=beta,backlash_mm=backlash)
        if not internal or internal_plan.get('construction_inputs')!=expected or x!=0 or center_extra!=0:
            raise ValueError('Paired internal plan does not match the mesh construction inputs.')
        a2['tip_radius']=internal_plan['ring_tip_radius_mm']
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
    ra2 = a2['tip_radius']
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
        if internal_plan is None: warnings.append('Axial ring assembly; the tangent root construction is not a pinion-cutter envelope. Check involute, trochoid and trimming interference for the actual cutter.')
    for k, g in enumerate((a1, a2), 1):
        if internal and k == 2:
            continue
        if g['x'] + 1e-09 < g['rack_minimum_shift']:
            warnings.append(f'Wheel {k}: rounded-rack undercut; actual envelope and trimming are recorded per part.')
    from tooth_profiles import external_half, internal_half
    from gear_measurement import wildhaber_span, default_gauge
    endpoints=lambda fn,a,b:[fn(a),fn(b)]
    def usable(g,ring=False):
        if ring:
            if internal_plan is not None:
                info=internal_plan['ring_profile']
            else:
                _,info=internal_half(g['teeth'],g['mt'],g['alpha_t'],backlash,m,1,1.25,endpoints)
            g['tooth_thickness'] = info['tooth_thickness']
            g['wildhaber_span'] = wildhaber_span(info['measurement_geometry'])
            g['over_gauges'] = default_gauge(info['measurement_geometry'])
            return sqrt(max(0,info['involute_end_radius_mm']**2-g['base_radius']**2))
        _,info=external_half(g['teeth'],g['mt'],g['alpha_t'],backlash,m,g['x'],pressure,1,1.25,endpoints)
        g['tooth_thickness'] = info['tooth_thickness']
        g['wildhaber_span'] = wildhaber_span(info['measurement_geometry'])
        g['over_gauges'] = default_gauge(info['measurement_geometry'])
        return sqrt(max(0,info['involute_start_radius_mm']**2-g['base_radius']**2))
    lower1=usable(a1);bound2=usable(a2,internal);span=a*sin(aw)
    lower=max(lower1,g2-span if internal else span-g2)
    upper=min(g1,bound2-span if internal else span-bound2)
    usable_ea=max(0,upper-lower)/(pi*a1['mt']*cos(at))
    if usable_ea+eb<1:
        warnings.append('Usable involute contact ratio after root trimming/blending is below 1; nominal tip/base-circle ratio overstates the active flank. Change tooth counts or tooth geometry to maintain continuous engagement.')
    if internal_plan is not None and internal_plan['verification']['status']!='clear':
        warnings.append('Planetary internal polygon clearance unresolved: '+internal_plan['verification']['failure_reason'])
    result=dict(profile_contact_transverse=usable_ea, profile_contact_total=usable_ea+eb,
                profile_contact_basis='intersection of usable involute intervals after root envelope/blend; excludes fillet contact, elastic deflection and 3D interference',
                z1=z1, z2=z2, internal=internal, center_distance_mm=a, reference_center_mm=a0, working_pressure_deg=degrees(aw), contact_transverse=ea, contact_overlap=eb, contact_total=ea + eb, extra_backlash_mm=added, nominal_pair_backlash_mm=backlash, working_pair_backlash_mm=backlash * a / a0 + (added or 0), gear1=a1, gear2=a2, warnings=warnings)
    if internal_plan is not None:result['internal_pair_construction']=internal_plan
    return result

def force_components(torque, diameter, pressure, beta=0):
    ft = 2000 * abs(torque) / diameter
    return dict(tangential_N=ft, radial_N=ft * tan(radians(pressure)), axial_N=ft * tan(radians(beta)))

def attach_report(d):
    v = d.values
    r = d.analysis
    if d.family in ('spur', 'helical', 'double', 'parallel', 'internal', 'planetary', 'wolfrom'):
        from gear_measurement import wildhaber_span, default_gauge
        for part in d.parts:
            profile = part.profile_metadata.get('tooth_profile', {})
            thickness = profile.get('tooth_thickness')
            if thickness is None:
                continue
            span = wildhaber_span(profile['measurement_geometry'])
            profile['wildhaber_span'] = span
            gauges = default_gauge(profile['measurement_geometry'])
            profile['over_gauges'] = gauges
            if 'gear' in r:
                r['gear']['wildhaber_span'] = span
                r['gear']['over_gauges'] = gauges
            if span['status'] == 'ok':
                chosen = next(q for q in span['usable_spans'] if q['k'] == span['recommended_k'])
                d.metrics.append(f"{part.name}: Wildhaber W{chosen['k']} {chosen['span_mm']:.4f} mm recommended · contact R {chosen['contact_radius_mm']:.4f} mm · {len(span['usable_spans'])} usable k in calculation report")
            else:
                d.metrics.append(f"{part.name}: Wildhaber span unavailable · {span['reason']}")
            ref, tip = thickness['reference'], thickness['tip']
            actual = ref['generated_transverse_arc_mm']
            reference = f"{actual:.4f} mm generated" if actual is not None else 'outside usable involute'
            d.metrics.append(f"{part.name}: reference tooth arc {ref['nominal_transverse_arc_mm']:.4f} mm nominal / {reference} (transverse)")
            d.metrics.append(f"{part.name}: tip chord {tip['generated_transverse_chord_mm']:.4f} mm transverse · chord/mn {thickness['tip_chord_over_normal_module']:.4f} (geometry only)")
    if d.family == 'differential':
        if v.get('configuration','wrist')=='classic':
            r['input']=dict(carrier_rpm=v['input_rpm'],prescribed_side_difference_rpm=v['output_difference_rpm'],
                            scope='Direct carrier input; prescribed side difference is a boundary condition, not a second physical input or load-based split')
        else:r['input'] = dict(input_a_rpm=v['input_rpm'], input_b_rpm=v['input_b_rpm'],
                          scope='Two independently prescribed speeds; no load or power balance calculated')
        return r
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
    if 'input_a_rpm' in load:
        lines.append(f"Inputs A / B: {load['input_a_rpm']:+g} / {load['input_b_rpm']:+g} rpm. No combined power or output torque estimate.")
    if 'carrier_rpm' in load:
        lines.append(f"Carrier input: {load['carrier_rpm']:+g} rpm; prescribed B−A: {load['prescribed_side_difference_rpm']:+g} rpm. Speed boundary condition only; no load-based speed split, torque or power estimate.")
    if 'rpm' in load:
        lines.append(f"Input: {load['rpm']:g} rpm · {load['torque_Nm']:g} N·m · {load['power_W']:.3f} W")
    if 'signed_ratio' in r:
        lines.append(f"Ratio i = input speed / output speed = {r['signed_ratio']:.6g}; negative = opposite rotation.")
    for i, q in enumerate(r.get('meshes', []), 1):
        lines.append(f"Mesh {i}: Z {q['z1']}/{q['z2']} · centre distance {q['center_distance_mm']:.6f} mm · αw {q['working_pressure_deg']:.6f}°")
        lines.append(f"  εα {q['contact_transverse']:.6f} · εβ {q['contact_overlap']:.6f} · ε total {q['contact_total']:.6f}")
        if q.get('internal_pair_construction'):
            plan=q['internal_pair_construction'];check=plan['verification']
            lines.append(f"  Paired ring {plan['construction_version']}: ha {plan['ring_addendum_coefficient']:.9f}; tip relief {plan['ring_tip_relief_mm']:.6f} mm; radial exclusion margins {plan['planet_root_exclusion_margin_mm']:.6f}/{plan['ring_root_exclusion_margin_mm']:.6f} mm.")
            lines.append(f"  Neutral transverse polygon clearance: {check['status']}; {check['evaluated_intervals']} intervals; certified separation lower bound {check['certified_separation_lower_bound_mm']} mm. {check['scope']}")
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
        if d.family in ('spur', 'helical', 'double', 'parallel', 'internal', 'planetary', 'wolfrom') and 'tooth_thickness' in p:
            thickness = p['tooth_thickness']
            lines.append(f"  Tooth thickness ({'internal' if thickness['internal'] else 'external'}): total transverse pair backlash {thickness['pair_backlash_transverse_mm']:.6f} mm; per-gear reference reduction {thickness['per_gear_reference_reduction_transverse_mm']:.6f} mm.")
            for label in ('reference', 'tip'):
                q = thickness[label]
                lines.append(f"  {label.capitalize()} R {q['radius_mm']:.6f} mm: nominal transverse arc {q['nominal_transverse_arc_mm']:.6f} mm; nominal normal arc {q['nominal_normal_arc_mm']:.6f} mm.")
                if q['on_usable_involute']:
                    lines.append(f"    Generated transverse arc {q['generated_transverse_arc_mm']:.6f} mm; generated normal arc {q['generated_normal_arc_mm']:.6f} mm; transverse chord {q['generated_transverse_chord_mm']:.6f} mm.")
                else:
                    lines.append('    Generated thickness unavailable: circle lies outside the usable involute after root trimming/blending.')
            lines.append(f"  Tip transverse chord / normal module: {thickness['tip_chord_over_normal_module']:.6f}; geometric thin-tip quantity only, no minimum safe thickness or structural capacity calculated.")
            lines.append('  Thickness basis: '+thickness['basis']+'.')
        if 'wildhaber_span' in p:
            span = p['wildhaber_span']
            lines.append('  Wildhaber span: '+span['scope']+'.')
            if span['status'] == 'ok':
                lines.append(f"    Recommended k={span['recommended_k']}: {span['recommendation_basis']}; choose any usable k below.")
                for q in span['usable_spans']:
                    lines.append(f"    k={q['k']}: W_k {q['span_mm']:.6f} mm; both contacts R {q['contact_radius_mm']:.6f} mm (diameter {q['contact_diameter_mm']:.6f} mm); root/tip involute margins {q['root_margin_mm']:.6f}/{q['tip_margin_mm']:.6f} mm.")
            else:
                lines.append('    Unavailable: '+span['reason'])
            lines.append('    '+span['basis']+'.')
        if 'over_gauges' in p:
            from gear_measurement import gauge_report_lines
            lines.extend('  '+line for line in gauge_report_lines(p['over_gauges']))
        lines.append('  Domain: '+p['domain'])
    if 'wave_mapping' in r:
        q=r['wave_mapping']
        lines.append('Strain wave: '+q['method']+'; eight arc Fourier modes; prescribed deformation, no elastic solution.')
        if q.get('ring_envelope'):
            e=q['ring_envelope']
            lines.append(f"  Generated ring: {e['method']}; reference pair backlash {q['reference_pair_backlash_mm']:g} mm; numerical radial enclosure relief <= {e['numerical_enclosure_relief_mm']:.6f} mm; measured refinement change {e['measured_refinement_change_mm']:.6f} mm.")
    if 'wheel_geometry' in r:
        q=r['wheel_geometry'];lines.append(f"Wheel: {q['method']} · reference R {q['reference_wheel_radius_mm']:.6f} mm · root clearance {q['root_clearance_mm']:.6f} mm · section chord threshold {q['chord_threshold_mm']:g} mm; ideal rigid generated envelope.")
    if 'forces' in r:
        lines.append('Reference forces: ' + ', '.join((f'{k} = {v:.3f}' for k, v in r['forces'].items())))
    lines += ['', 'ASSUMPTIONS AND LIMITATIONS'] + d.notes + ['', 'Sources and formulas: docs/technical/calculations.md. No result is an allowable load or ISO/AGMA certification.']
    return '\n'.join(lines) + '\n'
