# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Poses for the local viewer. No changes to design geometry or CAD commands.
Phase is the reference angle in radians; the viewer advances it at the input
operating RPM. Matrices are column-major, with translation in world millimetres.
"""
from dataclasses import dataclass, field
from math import sin, cos, sqrt, pi, atan2, remainder, isfinite
from copy import copy, deepcopy

SPEED_KEYS = frozenset(('input_rpm', 'input_b_rpm', 'output_difference_rpm'))


def same_geometry(design, family, values):
    """The supported rotary families have no speed-dependent construction."""
    return bool(design and design.family == family and
                {k: v for k, v in design.values.items() if k not in SPEED_KEYS} ==
                {k: v for k, v in values.items() if k not in SPEED_KEYS})


def update_operating_rates(design, values):
    """Update operating metadata using the existing solvers, sharing surfaces.

    This requires identical validated geometry. Mount construction, tooth reports
    and nominal forces do not depend on operating speed. Their geometry and
    analysis records are shared read-only; only operating records are copied.
    """
    if design.family == 'wolfrom':
        from wolfrom import prepare
        prepare(values)
    if not same_geometry(design, design.family, values):
        raise ValueError('Operating-rate update requires identical geometry.')
    from geometry import get_specs
    for key, label, default, low, high, step in get_specs(design.family, values.get('variant'), values.get('double_style')):
        if key in SPEED_KEYS:
            value = values.get(key, default)
            if isinstance(value, bool) or not isfinite(value) or not low <= value <= high:
                raise ValueError(f'{label}: must be between {low} and {high}')
    from kinematics import TRIPLES, PAIRS, solve, coefficients
    d = copy(design)
    d.values = dict(values)
    d.analysis = dict(design.analysis)
    for key in ('input', 'output', 'kinematics', 'interstage_mounting'):
        if key in d.analysis:d.analysis[key] = deepcopy(d.analysis[key])
    d.metrics = list(design.metrics)
    d.parts = [copy(p) for p in design.parts]
    for p in d.parts:
        p.port = dict(p.port)
    f, v, r = d.family, d.values, d.analysis
    rpm = v['input_rpm']
    if f == 'differential':
        from differential_wrist import rates, classic_rates
        classic = v.get('configuration') == 'classic'
        speeds = (classic_rates(rpm, v['output_difference_rpm'], v['side_teeth'], v['output_teeth'])
                  if classic else rates(rpm, v['input_b_rpm'], v['side_teeth'], v['output_teeth']))
        r['kinematics']['rates_rpm'] = speeds
        transverse = speeds['spider_spin' if classic else 'output_spin']
        a, b = (speeds['side_a'], speeds['side_b']) if classic else (rpm, v['input_b_rpm'])
        if classic:
            r['kinematics']['prescribed_difference_rpm'] = v['output_difference_rpm']
            r['input'].update(carrier_rpm=rpm, prescribed_side_difference_rpm=v['output_difference_rpm'])
            d.metrics[:2] = [f"Carrier input: {speeds['carrier']:+g} rpm · prescribed B−A: {v['output_difference_rpm']:+g} rpm",
                             f"Side outputs A / B: {a:+g} / {b:+g} rpm · internal spider spin: {transverse:+g} rpm"]
        else:
            r['input'].update(input_a_rpm=rpm, input_b_rpm=v['input_b_rpm'])
            d.metrics[:2] = [f"Inputs A / B: {a:+g} / {b:+g} rpm",
                             f"Carrier tilt: {speeds['carrier']:+g} rpm · relative output spin: {transverse:+g} rpm"]
        for p in d.parts:
            member = p.port.get('member')
            if 'rpm' in p.port:
                p.port['rpm'] = a if member == 'A' else b if member == 'B' else speeds['carrier'] if member == 'carrier' else transverse
            if member in ('output', 'spider'):
                p.port.update(carrier_rpm=speeds['carrier'], relative_spin_rpm=transverse)
        return d
    if f == 'wolfrom':
        from wolfrom import apply_kinematics
        apply_kinematics(d)
    elif f in TRIPLES:
        stages = r['kinematics']['stage_results']
        speed = rpm
        for stage, old in enumerate(stages, 1):
            q = solve(coefficients(f, v, stage), v['io_scheme2' if stage == 2 else 'io_scheme'], speed)
            old.update(q)
            speed = q['rates_rpm'][q['output']]
        for p in d.parts:
            port = p.port
            if not port:
                continue
            q = stages[port.get('stage', 1)-1]
            member = port.get('member')
            if member == 'disc':
                port.update(rpm=q['rates_rpm']['output'], orbital_rpm=q['rates_rpm']['eccentric'])
            elif member in q['rates_rpm']:
                port['rpm'] = q['rates_rpm'][member]
        if 'interstage_mounting' in r:
            q = stages[0]
            r['interstage_mounting']['rpm'] = q['rates_rpm'][q['output']]
    elif f in PAIRS:
        ratio = r['signed_ratio']
        a = rpm if v['io_scheme'] == 'forward' else rpm/ratio
        b = rpm/ratio if v['io_scheme'] == 'forward' else rpm
        for p in d.parts:
            if 'rpm' in p.port:
                p.port['rpm'] = a if p.port['member'] == 'A' else b
    r['input'].update(rpm=rpm, power_W=v['input_torque']*rpm*2*pi/60)
    if 'output' in r:
        out = r['output']
        out.update(rpm=rpm/r['signed_ratio'], power_W=r['input']['power_W']*r['assumed_efficiency'])
        nominal = f"Nominal output {out['rpm']:.2f} rpm · estimated torque {out['torque_magnitude_Nm']:.3f} N·m (assumed η {r['assumed_efficiency']*100:g}%)"
        d.metrics = [nominal if line.startswith('Nominal output ') else line for line in d.metrics]
    return d
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)

def wrapped_angle(angle):
    """Reduce in float64 before a GPU uniform loses long-running phase bits."""
    return remainder(angle,2*pi)

def multiply(a, b):
    return tuple((sum((a[4 * k + r] * b[4 * c + k] for k in range(4))) for c in range(4) for r in range(4)))

def translation(x=0, y=0, z=0):
    return (*IDENTITY[:12], x, y, z, 1.0)

def rotation(angle, axis=(0, 0, 1), pivot=(0, 0, 0)):
    length = sqrt(sum((x * x for x in axis)))
    x, y, z = (v / length for v in axis)
    c = cos(angle)
    s = sin(angle)
    k = 1 - c
    rows = ((c + x * x * k, x * y * k - z * s, x * z * k + y * s), (y * x * k + z * s, c + y * y * k, y * z * k - x * s), (z * x * k - y * s, z * y * k + x * s, c + z * z * k))
    shift = tuple((pivot[i] - sum((rows[i][j] * pivot[j] for j in range(3))) for i in range(3)))
    return tuple((rows[r][col] if r < 3 and col < 3 else shift[r] if col == 3 and r < 3 else 1.0 if r == col == 3 else 0.0 for col in range(4) for r in range(4)))

def transform(m, p):
    return tuple((sum((m[4 * j + i] * p[j] for j in range(3))) + m[12 + i] for i in range(3)))

def rigid(rate, pivot=(0, 0, 0), axis=(0, 0, 1)):
    return lambda phase: rotation(phase * rate, axis, pivot)

def orbital(spin, orbit, center):

    def pose(phase):
        x, y = center
        cx = x * cos(orbit * phase) - y * sin(orbit * phase)
        cy = x * sin(orbit * phase) + y * cos(orbit * phase)
        return multiply(translation(cx - x, cy - y), rotation(spin * phase, pivot=(x, y, 0)))
    return pose

def part_axis(p):
    if p.frame:
        o, *basis = p.frame
        pivot = tuple((o[i] + p.center[0] * basis[0][i] + p.center[1] * basis[1][i] for i in range(3)))
        return (pivot, basis[2])
    if p.axis_x:
        return ((0, p.center[1], p.z), (1, 0, 0))
    return ((*p.center, 0), (0, 0, 1))

@dataclass
class MotionPlan:
    """Display poses keyed by zero-based positions in the complete Design.parts.

    rates records every labelled spin/orbit needed by the interference period;
    tooth symmetry must not shorten that orientation period.
    """
    supported: bool = True
    message: str = 'Ratios and directions of the selected arrangement at the configured input RPM.'
    poses: dict = field(default_factory=dict)
    warps: dict = field(default_factory=dict)
    flex: dict = field(default_factory=dict)
    reference_rpm: float = 1
    rates: dict = field(default_factory=dict)
    # Bevel differential coordinates are independent angles, including spin relative
    # to its carrier. Offsets retain physical pose when either speed changes.
    angular_rates: dict = field(default_factory=dict)
    angular_offsets: dict = field(default_factory=dict)
    coordinate_rates: dict = field(default_factory=dict)
    coordinate_offsets: dict = field(default_factory=dict)
    # Full labelled orientation period; geometric tooth symmetry is not assumed.

    def matrix(self, index, phase):
        return self.poses[index](phase) if index in self.poses else IDENTITY

    def warp(self, index, phase):
        return self.warps[index](phase) if index in self.warps else None

    def deformation(self, index, phase):
        return self.flex[index](phase) if index in self.flex else None

def build_plan(d, previous=None, phase=0):
    """Build nominal motion, retaining every angle for a speed-only rebuild.

    Callers may pass a previous plan only when geometry is identical.
    The phase is its current display phase, not an elapsed time in seconds.
    """
    plan = MotionPlan()
    f = d.family
    v = d.values
    parts = d.parts
    primary = v.get('input_rpm', 0)
    classic=f=='differential' and v.get('configuration','wrist')=='classic'
    secondary = v.get('output_difference_rpm' if classic else 'input_b_rpm', 0) if f == 'differential' else 0
    ref = ((max(abs(x) for x in d.analysis['kinematics']['rates_rpm'].values()) if classic else max(abs(primary), abs(secondary))) or 1.0)
    plan.reference_rpm = ref
    if primary == secondary == 0:
        plan.message = 'Operating speed is 0 rpm: the model stays stationary.'

    def angle(key, rate):
        plan.coordinate_rates[key] = rate
        offset = 0.0
        if previous is not None and key in previous.coordinate_rates:
            offset = previous.coordinate_offsets[key] + phase*(previous.coordinate_rates[key]-rate)
        plan.coordinate_offsets[key] = offset
        return lambda phase: rate*phase+offset

    def spin(index, rpm, pivot=None, axis=None):
        p = parts[index]
        o, a = part_axis(p)
        value = angle((index, 'spin'), rpm/ref)
        plan.poses[index] = lambda phase: rotation(value(phase), axis or a, pivot or o)
        plan.rates[index] = (rpm / ref,)

    def orbit(index, spin, orbit, center):
        turning = angle((index, 'spin'), spin)
        circling = angle((index, 'orbit'), orbit)
        x, y = center
        def pose(phase):
            a = circling(phase)
            return multiply(translation(x*cos(a)-y*sin(a)-x, x*sin(a)+y*cos(a)-y),
                            rotation(turning(phase), pivot=(x, y, 0)))
        plan.poses[index] = pose
    for i, p in enumerate(parts):
        if 'rpm' in p.port:
            global_axis = f in ('planetary', 'cycloidal', 'harmonic', 'wolfrom')
            spin(i, p.port['rpm'], (0, 0, 0) if global_axis else None)
    if f in ('spur', 'helical', 'double'):
        for i, p in enumerate(parts):
            if p.role == 'gear' or p.name.startswith(('Shaft', 'Key')):
                spin(i, primary)
    elif f == 'wolfrom':
        rates = d.analysis['kinematics']['rates_rpm']
        for i, p in enumerate(parts):
            if p.port.get('member') == 'planet':
                orbit(i, rates['planet']/ref, rates['carrier']/ref, p.center)
                plan.rates[i] = (rates['planet']/ref, rates['carrier']/ref)
    elif f == 'planetary':
        stages = d.analysis['kinematics']['stage_results']
        for i, p in enumerate(parts):
            name = p.name.lower()
            stage = 2 if name.startswith('s2_') else 1
            q = stages[stage - 1]
            rates = q['rates_rpm']
            wc = rates['carrier']
            ws = rates['sun']
            if 'planet_' in name and 'pin_' not in name:
                zs = v['sun2' if stage == 2 else 'sun']
                zp = v['planet2' if stage == 2 else 'planet']
                wp = wc - zs / zp * (ws - wc)
                orbit(i, wp/ref, wc/ref, p.center)
                plan.rates[i] = (wp / ref, wc / ref)
            elif 'shaft_input' in name:
                spin(i, stages[0]['rates_rpm']['sun'])
            elif 'coupling_interstage' in name or 'shaft_output' in name:
                spin(i, wc)
    elif f == 'cycloidal':
        rates = d.analysis['kinematics']['stage_results'][0]['rates_rpm']
        we = rates['eccentric']
        wo = rates['output']
        for i, p in enumerate(parts):
            if p.name.startswith('Disc_cycloidal'):
                orbit(i, wo/ref, we/ref, p.center)
                plan.rates[i] = (wo / ref, we / ref)
            elif p.name.startswith('Bearing_eccentric'):
                orbit(i, 0, we/ref, p.center)
                plan.rates[i] = (we / ref,)
    elif f == 'harmonic':
        rates = d.analysis['kinematics']['stage_results'][0]['rates_rpm']
        we = rates['wave'] / ref
        wf = rates['flex'] / ref
        a, b = d.analysis['pitch_ellipse_semiaxes_mm']
        rp = v['module'] * v['teeth'] / 2
        length = v['cup_length']
        t = v['diaphragm']
        for i, p in enumerate(parts):
            if p.name.startswith('Flexspline'):
                plan.poses.pop(i, None)
                plan.rates[i] = (wf, we)
                material = angle((i, 'spin'), wf)
                wave = angle((i, 'wave'), we)
                plan.flex[i] = lambda phase, material=material, wave=wave: (material(phase), wave(phase), a, b, rp, length, t)
            elif p.name == 'Bearing_wave_envelope':
                spin(i, rates['wave'])
        plan.message = 'Prescribed strain-wave deformation and rotation of the three members. This is not an elastic analysis.'
    elif f in ('parallel', 'internal'):
        ratio = (1 if f == 'internal' else -1) * v['wheel'] / v['pinion']
        wa = primary if v['io_scheme'] == 'forward' else primary * ratio
        wm = -wa * v['pinion'] / v['wheel']
        wb = wa / ratio
        for i, p in enumerate(parts):
            name = p.name
            if name in ('S1_Wheel', 'S2_Pinion', 'Shaft_intermediate'):
                spin(i, wm)
    elif f == 'differential':
        rates = d.analysis['kinematics']['rates_rpm']
        plan.angular_rates = {key: value/ref for key, value in rates.items()}
        plan.angular_offsets = {key: 0.0 for key in rates}
        if previous is not None and set(previous.angular_rates) == set(plan.angular_rates):
            for key, rate in plan.angular_rates.items():
                plan.angular_offsets[key] = previous.angular_offsets[key] + phase*(previous.angular_rates[key]-rate)
        transverse='spider_spin' if classic else 'output_spin'
        wc, wo = plan.angular_rates['carrier'], plan.angular_rates[transverse]
        oc, oo = plan.angular_offsets['carrier'], plan.angular_offsets[transverse]
        for i, p in enumerate(parts):
            group = p.port.get('member')
            if group in ('A', 'B', 'carrier'):
                key = ('side_a' if classic else 'input_a') if group == 'A' else ('side_b' if classic else 'input_b') if group == 'B' else 'carrier'
                rate, offset = plan.angular_rates[key], plan.angular_offsets[key]
                plan.poses[i] = lambda phase, rate=rate, offset=offset: rotation(rate*phase+offset,(1,0,0))
                plan.rates[i] = (rate,)
            elif group in ('output','spider'):
                plan.poses[i] = lambda phase, wc=wc, wo=wo, oc=oc, oo=oo: multiply(rotation(wc*phase+oc,(1,0,0)), rotation(wo*phase+oo,(0,0,1)))
                plan.rates[i] = (wc, wo)
        plan.message = ('Both input signs use world +X. Equal speeds tilt the carrier; opposing speeds spin the output. '
                        'Output spin is relative to its moving carrier; spherical involute working flanks and ideal kinematics.')
        if classic:plan.message='Carrier input C; prescribed difference B−A sets the two side outputs. The internal spider spins relative to its carrier. This boundary condition does not predict speed split from loads.'
    elif f == 'worm':
        for i, p in enumerate(parts):
            if p.name.startswith('Screw_'):
                spin(i, p.port['rpm'], (0, 0, p.z), (1, 0, 0))
    else:
        return MotionPlan(False, 'Animation unavailable for this family.')
    return plan
