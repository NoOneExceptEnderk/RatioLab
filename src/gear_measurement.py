# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Theoretical involute measurement geometry, independent of GTK and sampling.

Lengths are mm, angles named ``*_rad`` are radians. References and the
deliberately limited supported domain are in docs/technical/calculations.md.
"""
from math import atan, cos, hypot, isfinite, pi, sqrt, tan


def wildhaber_span(geometry):
    """Enumerate every usable integer tooth span on an external spur profile.

    ISO 21771:2007 A.2.1 (A.6), (A.9). Symmetric jaws contact at
    R=hypot(rb,W/2); only the actual useful involute interval is accepted.
    ``geometry`` comes from the constructed profile, not nominal dimensions.
    A supported profile can still have no geometrically usable integer k.
    """
    result = dict(supported=False, status='unsupported', usable_spans=[],
                  recommended_k=None,
                  scope='external spur cylindrical involute; symmetric flat jaws; theoretical dimensions only',
                  basis='ISO 21771:2007 A.2.1 equations (A.6), (A.9); actual allowance-reduced profile; no gauge tolerances or strength assessment')
    beta = geometry['helix_angle_abs_deg']
    if not isfinite(beta):
        raise ValueError('Invalid helix angle for span measurement.')
    if geometry['internal']:
        result['reason'] = 'Internal flat-jaw span measurement is not supported.'
        return result
    if abs(beta) > 1e-7:
        result['reason'] = 'Helical flat-jaw span and usable-facewidth checks are not supported.'
        return result
    z = geometry['teeth']
    rb = geometry['base_radius_mm']
    rp = geometry['reference_radius_mm']
    half = geometry['reference_half_angle_rad']
    at = geometry['transverse_pressure_angle_rad']
    lower = geometry['involute_start_radius_mm']
    upper = geometry['involute_end_radius_mm']
    if (not all(isfinite(v) for v in (z, rb, rp, half, at, lower, upper)) or
            isinstance(z, bool) or int(z) != z or z < 3 or
            not 0 < at < pi/2 or not 0 < rb <= rp or
            not rb <= lower <= upper):
        raise ValueError('Invalid constructed involute geometry for span measurement.')
    inv_at = tan(at)-at
    pb = 2*pi*rb/z
    sb = 2*rb*(half+inv_at)
    tolerance = max(upper, rp)*1e-10
    spans = []
    for k in range(1, int(z)+1):
        w = (k-1)*pb+sb
        # Positive roll excludes the reversed involute branch before squaring.
        if w <= 0:
            continue
        roll = w/(2*rb)
        radius = hypot(rb, w/2)
        if not lower-tolerance <= radius <= upper+tolerance:
            continue
        contact_alpha = atan(roll)
        flank_half = half+inv_at-(roll-contact_alpha)
        if not 0 < flank_half < pi/z:
            continue
        spans.append(dict(k=k, span_mm=w, contact_radius_mm=radius,
                          contact_diameter_mm=2*radius,
                          contact_pressure_angle_rad=contact_alpha,
                          contact_roll=roll,
                          root_margin_mm=max(0, radius-lower),
                          tip_margin_mm=max(0, upper-radius)))
    recommended = min(spans, key=lambda q: (abs(q['contact_radius_mm']-rp), q['k'])) if spans else None
    result.update(supported=True, status='ok' if spans else 'no_usable_span',
                  usable_spans=spans,
                  recommended_k=recommended['k'] if recommended else None,
                  recommendation_basis='usable contact radius nearest the reference circle',
                  base_pitch_mm=pb, base_tooth_thickness_mm=sb,
                  involute_start_radius_mm=lower, involute_end_radius_mm=upper,
                  reason='' if spans else 'No integer tooth span has symmetric contacts on both useful involute flanks.')
    return result


def _inverse_involute(value):
    """Nonnegative principal inverse of tan(alpha)-alpha, 0 <= alpha < pi/2."""
    left, right = 0., pi/2-1e-12
    for _ in range(100):
        mid = (left+right)/2
        if tan(mid)-mid < value:
            left = mid
        else:
            right = mid
    return (left+right)/2


def over_gauges(geometry, diameter_mm, gauge_type='ball'):
    """Theoretical over/between balls or axial rollers on one spur profile.

    ISO 21771:2007 A.5 (A.42)-(A.46), A.6, A.7 (A.47)-(A.48).
    Positive physical radii/counts; the internal sign is translated explicitly.
    Unsupported domain and unusable gauges return a reason, never a valid M.
    """
    if gauge_type not in ('ball', 'roller'):
        raise ValueError('Gauge type must be ball or roller.')
    if isinstance(diameter_mm, bool) or not isfinite(diameter_mm) or diameter_mm <= 0:
        raise ValueError('Gauge diameter must be a positive finite length in mm.')
    result = dict(supported=False, status='unsupported', dimension_mm=None,
                  gauge_type=gauge_type, gauge_diameter_mm=diameter_mm,
                  scope='external/internal spur involute; balls or axial cylindrical rollers; theoretical dimensions only',
                  basis='ISO 21771:2007 A.5 equations (A.42)-(A.46), A.6, A.7 equations (A.47)-(A.48); actual allowance-reduced profile',
                  contact_type='point contact for balls; axial line contact for rollers',
                  gauge_note='Spur balls and axial rollers have the same theoretical transverse dimension. Conservative root/tip-circle clearance may exclude usable gauges; finite gauge length, axial access, tolerances and elastic contact are not calculated.')
    beta = geometry['helix_angle_abs_deg']
    if not isfinite(beta):
        raise ValueError('Invalid helix angle for gauge measurement.')
    if abs(beta) > 1e-7:
        result['reason'] = 'Helical/double-helical balls and rollers require distinct 3D contact and placement calculations and are not supported.'
        return result
    z = geometry['teeth']
    rb, rp = geometry['base_radius_mm'], geometry['reference_radius_mm']
    half, at = geometry['reference_half_angle_rad'], geometry['transverse_pressure_angle_rad']
    lower, upper = geometry['involute_start_radius_mm'], geometry['involute_end_radius_mm']
    root, tip = geometry['root_radius_mm'], geometry['tip_radius_mm']
    internal = geometry['internal']
    if (not all(isfinite(v) for v in (z, rb, rp, half, at, lower, upper, root, tip)) or
            isinstance(z, bool) or int(z) != z or z < 3 or
            not 0 < at < pi/2 or not 0 < rb <= rp or
            not rb <= lower <= upper or not 0 < half < pi/z or
            not (0 < tip < root if internal else 0 < root < tip)):
        raise ValueError('Invalid constructed involute geometry for gauge measurement.')
    z = int(z)
    result.update(supported=True, internal=internal, teeth=z,
                  parity='odd' if z % 2 else 'even',
                  dimension_kind='between gauges' if internal else 'over gauges')
    def reject(status, reason):
        result.update(status=status, reason=reason)
        return result
    db = 2*rb
    inv_at = tan(at)-at
    eta = pi/z-half+(inv_at if internal else -inv_at)
    target = eta-diameter_mm/db if internal else diameter_mm/db-eta
    if target < 0:
        return reject('no_solution',
                      'No nonnegative centre-pressure involute solution exists; the negative internal branch exceeds local concave flank curvature and penetrates the tooth.' if internal else
                      'No nonnegative centre-pressure involute solution exists for this external gauge diameter.')
    alpha_k = _inverse_involute(target)
    roll = tan(alpha_k)+(diameter_mm/db if internal else -diameter_mm/db)
    if internal and diameter_mm/2 >= rb*roll-max(rp, upper)*1e-12:
        return reject('no_seating', 'The gauge radius reaches or exceeds the local concave involute curvature radius; a stable symmetric seat is unavailable.')
    if roll <= 0:
        return reject('reverse_contact', 'The solution contacts the reverse involute branch, outside the generated profile.')
    contact = rb*hypot(1, roll)
    centre = rb/cos(alpha_k)
    tolerance = max(rp, upper, diameter_mm)*1e-10
    result.update(centre_circle_diameter_mm=2*centre,
                  centre_pressure_angle_rad=alpha_k, contact_roll=roll,
                  contact_radius_mm=contact, contact_diameter_mm=2*contact,
                  contact_pressure_angle_rad=atan(roll),
                  involute_start_radius_mm=lower, involute_end_radius_mm=upper)
    if contact < lower-tolerance or contact > upper+tolerance:
        at_root = contact > upper if internal else contact < lower
        return reject('root_or_fillet_contact' if at_root else 'beyond_tip',
                      'Contact lies in the root/blend region, outside the useful involute.' if at_root else
                      'Contact lies beyond the tooth tip, outside the useful involute.')
    flank = half+(roll-atan(roll)-inv_at if internal else inv_at-roll+atan(roll))
    if not 0 < flank < pi/z:
        return reject('no_seating', 'The symmetric contact falls outside the actual tooth-space flanks.')
    radius = diameter_mm/2
    if (centre+radius > root+tolerance if internal else centre-radius < root-tolerance):
        return reject('root_intersection', 'The gauge intersects the root-circle envelope and cannot seat on these two involute contacts.')
    separation = 2*centre*(cos(pi/(2*z)) if z % 2 else 1)
    if (separation/2-radius >= tip-tolerance if internal else separation/2+radius <= tip+tolerance):
        return reject('hidden_gauge', 'Parallel-jaw clearance past the tooth-tip circle is not established by this conservative check; a potentially usable gauge may be excluded.')
    if separation <= diameter_mm+tolerance:
        return reject('gauge_overlap', 'The two measuring gauges overlap or touch each other.')
    result.update(status='ok', reason='', dimension_mm=separation+(-diameter_mm if internal else diameter_mm),
                  gauge_centre_separation_mm=separation,
                  root_margin_mm=upper-contact if internal else contact-lower,
                  tip_margin_mm=contact-lower if internal else upper-contact)
    return result


def default_gauge(geometry):
    """Choose a theoretical diameter by targeting a useful reference contact.

    This is not a stock gauge recommendation. Try the reference circle clamped
    inside the useful interval, then its midpoint. Return explicit failure if
    no accessible symmetric gauge is found; never assign a fixed module ratio.
    """
    if abs(geometry['helix_angle_abs_deg']) > 1e-7:
        return over_gauges(geometry, 1.)
    rb = geometry['base_radius_mm']
    lower, upper = geometry['involute_start_radius_mm'], geometry['involute_end_radius_mm']
    at, half, z = geometry['transverse_pressure_angle_rad'], geometry['reference_half_angle_rad'], geometry['teeth']
    internal = geometry['internal']
    eta = pi/z-half+((tan(at)-at) if internal else -(tan(at)-at))
    targets = (min(upper, max(lower, geometry['reference_radius_mm'])), (lower+upper)/2)
    for contact in targets:
        roll = sqrt(max(0, (contact/rb)**2-1))
        alpha = roll-eta if internal else roll+eta
        if not 0 < alpha < pi/2:
            continue
        diameter = 2*rb*(eta-(tan(alpha)-alpha) if internal else tan(alpha)-alpha+eta)
        if diameter > 0:
            result = over_gauges(geometry, diameter)
            result['diameter_selection_basis'] = 'target useful involute contact nearest the reference circle, then interval midpoint; not a stock gauge size'
            if result['status'] == 'ok':
                return result
    return dict(supported=True, status='no_default_gauge', dimension_mm=None,
                reason='No accessible default gauge was found at the reference or midpoint contact; choose a diameter explicitly.',
                scope='external/internal spur involute', basis='ISO 21771:2007 A.5-A.7')


def gauge_report_lines(result):
    """Shared human-readable output for standard and explicitly selected reports."""
    lines = ['Theoretical balls / rollers: '+result['scope']+'.']
    if result['status'] == 'ok':
        lines.append(f"{result['gauge_type'].capitalize()} diameter {result['gauge_diameter_mm']:.6f} mm; {result['parity']} teeth; {result['dimension_kind']} M = {result['dimension_mm']:.6f} mm.")
        lines.append(f"Both contacts R {result['contact_radius_mm']:.6f} mm; useful involute root/tip margins {result['root_margin_mm']:.6f}/{result['tip_margin_mm']:.6f} mm.")
    else:
        if 'gauge_diameter_mm' in result:
            lines.append(f"{result['gauge_type'].capitalize()} diameter {result['gauge_diameter_mm']:.6f} mm.")
        lines.append('Unavailable ('+result['status']+'): '+result['reason'])
    if 'diameter_selection_basis' in result:
        lines.append('Diameter selection: '+result['diameter_selection_basis']+'.')
    if 'gauge_note' in result:
        lines.append(result['gauge_note'])
    lines.append(result['basis']+'.')
    return lines


def measurement_query(design, source_index, diameter_mm, gauge_type='ball', revision=None):
    """Read-only query on a generated, explicitly selected cylindrical member."""
    from copy import deepcopy
    if design.family not in ('spur', 'helical', 'double', 'parallel', 'internal', 'planetary'):
        raise ValueError('This family has no supported cylindrical gauge measurement.')
    if isinstance(source_index, bool) or not isinstance(source_index, int) or not 0 <= source_index < len(design.parts):
        raise ValueError('Select an existing source component.')
    part = design.parts[source_index]
    profile = part.profile_metadata.get('tooth_profile', {})
    if 'measurement_geometry' not in profile:
        raise ValueError('The selected component has no cylindrical involute profile.')
    result = over_gauges(profile['measurement_geometry'], diameter_mm, gauge_type)
    return dict(format='ratiolab-gauge-measurement/1', family=design.family,
                source_position=source_index+1, part=part.name, revision=revision,
                parameters=deepcopy(design.values), geometry=deepcopy(profile['measurement_geometry']),
                result=result)


def measurement_query_text(query):
    return '\n'.join(['RatioLab theoretical gauge measurement',
                      f"Family: {query['family']} · source component {query['source_position']}: {query['part']}",
                      f"Document revision: {query['revision']}",
                      'Read-only query; project parameters have not been changed.', '']+
                     gauge_report_lines(query['result']))+'\n'


def export_measurement(query, target):
    """Publish selected query text and complete context as one new export folder."""
    import json
    from export_transaction import directory
    with directory(target) as staging:
        (staging/'measurement.json').write_text(json.dumps(query, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        (staging/'measurement.txt').write_text(measurement_query_text(query), encoding='utf-8')
