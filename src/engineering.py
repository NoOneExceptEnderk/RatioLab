# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nominal geometry and statics. Units: mm, N, N·m, rpm and W.

Sources, conventions and formula domains are in docs/technical/calculations.md.
No ISO/AGMA strength verification or elastic load-distribution analysis.
"""
from math import pi, sin, cos, tan, atan, acos, sqrt, radians, degrees
from ratio_display import ratio_parts

LOAD_FIELDS = [('input_rpm', 'Input speed [rpm]', 1500, 0, 100000, 50), ('input_torque', 'Input torque [N·m]', 1, 0, 10000, 0.1), ('efficiency', 'Assumed overall efficiency [%]', 90, 1, 100, 1)]

def gear_dimensions(z, m, pressure=20, beta=0, x=0, ha=1, hf=1.25, backlash=0.15, internal=False, topping_mm=0):
    """Rust reference dimensions, with verified decimal results in metadata."""
    from rust_geometry import call
    return call('engineering_dimensions',dict(z=z,m=m,pressure=pressure,beta=beta,x=x,
        ha=ha,hf=hf,backlash=backlash,internal=internal,topping_mm=topping_mm))


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


def mesh(z1, z2, m, pressure=20, beta=0, width=10, x=0, center_extra=0, internal=False, gap=0, strict=True, backlash=0, internal_plan=None,pinion_rack_tip_radius_mm=None,tooth_tips1=None,tooth_tips2=None):
    from rust_geometry import call
    return call('engineering_mesh',dict(z1=z1,z2=z2,m=m,pressure=pressure,beta=beta,
        width=width,x=x,center_extra=center_extra,internal=internal,gap=gap,strict=strict,
        backlash=backlash,internal_plan=internal_plan,pinion_rack_tip_radius_mm=pinion_rack_tip_radius_mm,
        tooth_tips1=tooth_tips1,tooth_tips2=tooth_tips2))


def force_components(torque, diameter, pressure, beta=0):
    from rust_geometry import call
    return call('engineering_forces',dict(torque=torque,diameter=diameter,pressure=pressure,beta=beta))


def attach_report(d):
    v = d.values
    r = d.analysis
    if d.family in ('spur', 'helical', 'double', 'parallel', 'internal', 'planetary', 'wolfrom'):
        from gear_measurement import wildhaber_span, default_gauge
        from solid_geometry import sampling_report
        sampling=[]
        for part in d.parts:
            profile = part.profile_metadata.get('tooth_profile', {})
            thickness = profile.get('tooth_thickness')
            if thickness is None:
                continue
            part.profile_metadata['surface_sampling']=sampling_report(part)
            sampling.append(dict(part=part.name,**part.profile_metadata['surface_sampling']))
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
        r['surface_sampling']=sampling
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
    if d.family=='rack':
        from rack_geometry import operating
        operating(d)
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
    lines.extend(metric for metric in d.metrics if not metric.startswith('Input/output ratio '))
    lines.append('')
    for item in r.get('tooth_tip_treatments',[]):
        lines.append(f"{item['part']}: topping {item['topping_mm']:.6g} mm; semitopping height {item['semitopping_mm']:.6g} mm, normal ramp angle {item['semitopping_angle_deg']:.6g} deg; finished tip radius {item['finished_tip_radius_mm']:.9g} mm; primary involute tip limit {item['active_tip_radius_mm']:.9g} mm.")
    if r.get('rack',{}).get('rack_tip_treatment'):
        item=r['rack']['rack_tip_treatment']
        lines.append(f"Rack: topping {item['topping_mm']:.6g} mm; semitopping height {item['semitopping_mm']:.6g} mm, normal ramp angle {item['semitopping_angle_deg']:.6g} deg; finished tip height {item['finished_tip_height_mm']:.9g} mm.")
    load = r['input']
    if 'input_a_rpm' in load:
        lines.append(f"Inputs A / B: {load['input_a_rpm']:+g} / {load['input_b_rpm']:+g} rpm. No combined power or output torque estimate.")
    if 'carrier_rpm' in load:
        lines.append(f"Carrier input: {load['carrier_rpm']:+g} rpm; prescribed B−A: {load['prescribed_side_difference_rpm']:+g} rpm. Speed boundary condition only; no load-based speed split, torque or power estimate.")
    if 'rpm' in load:
        lines.append(f"Input: {load['rpm']:g} rpm · {load['torque_Nm']:g} N·m · {load['power_W']:.3f} W")
    if 'signed_ratio' in r:
        ratio = r['signed_ratio']
        notation = ''.join(ratio_parts(ratio, 10))
        lines.append(f"Input/output ratio: {notation} (i = {ratio:+.12g}); negative = opposite rotation.")
    if d.family=='rack':
        q=r['rack'];out=r['linear_output']
        lines.append(f"Rack output: {out['velocity_mm_s']:+.6f} mm/s along world +X; nominal force magnitude {out['nominal_force_magnitude_N']:.6f} N using assumed efficiency.")
        lines.append(f"x = {q['pitch_radius_mm']:.9g} mm * pinion angle [rad]; no dimensionless rotary ratio.")
    for i, q in enumerate(r.get('meshes', []), 1):
        lines.append(f"Mesh {i}: Z {q['z1']}/{q['z2']} · centre distance {q['center_distance_mm']:.6f} mm · αw {q['working_pressure_deg']:.6f}°")
        lines.append(f"  εα {q['contact_transverse']:.6f} · εβ {q['contact_overlap']:.6f} · ε total {q['contact_total']:.6f}")
        if q.get('internal_pair_construction'):
            plan=q['internal_pair_construction'];check=plan['verification']
            if plan['construction_version']=='fixed_internal_rack_pair_v1':
                lines.append(f"  Paired generating rack: normal tip radius {plan['pinion_profile']['tool']['tip_radius']:.9f} mm; full nominal contact preserved {plan['nominal_contact_preserved']}; ring tip relief {plan['ring_tip_relief_mm']:.9f} mm.")
                lines.append(f"  Construction: {check['status']}; {check['scope']}")
            else:
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
                if q.get('generated_transverse_arc_mm') is not None:
                    lines.append(f"    Generated transverse arc {q['generated_transverse_arc_mm']:.6f} mm; generated normal arc {q['generated_normal_arc_mm']:.6f} mm; transverse chord {q['generated_transverse_chord_mm']:.6f} mm.")
                else:
                    lines.append('    Generated thickness unavailable: circle lies outside the usable involute after root trimming/blending.')
            lines.append(f"  Tip transverse chord / normal module: {thickness['tip_chord_over_normal_module']:.6f}; geometric thin-tip quantity only, no minimum safe thickness or structural capacity calculated.")
            lines.append('  Thickness basis: '+thickness['basis'].rstrip('.')+'.')
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
    from geometry_quality import settings, SCOPE
    if settings(d):
        lines.append('Representation requests (mm): '+str(settings(d)))
        lines.append(SCOPE)
    if r.get('surface_sampling'):
        lines.append('Surface interpolation relative to sampled 2D contours:')
        lines.append('  Reference construction policy; preview/export representations can use independent thresholds.')
        for q in r['surface_sampling']:
            if q['status']=='bounded':
                lines.append(f"  {q['part']}: requested {q['requested_interpolation_mm']:.9g} mm; interpolation bound {q['interpolation_bound_mm']:.9g} mm; {q['section_count']} sections.")
            else:
                lines.append(f"  {q['part']}: interpolation not evaluated for {q['reference']}.")
        lines.append('  Binary64 interpolation bound only; transverse profile error and GPU/STL conversion are separate. No total-model error or manufacturing grade certified.')
    if 'forces' in r:
        lines.append('Reference forces: ' + ', '.join((f'{k} = {v:.3f}' for k, v in r['forces'].items())))
    lines += ['', 'ASSUMPTIONS AND LIMITATIONS'] + d.notes + ['', 'Sources and formulas: docs/technical/calculations.md. No result is an allowable load or ISO/AGMA certification.']
    return '\n'.join(lines) + '\n'
