# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Poses for the local viewer. No changes to design geometry or CAD commands.
Phase is the reference angle in radians; the viewer advances it at the input
operating RPM. Matrices are column-major, with translation in world millimetres.
"""
from parallel_multistage import VARIANTS as PARALLEL_MULTISTAGE_VARIANTS
from dataclasses import dataclass, field
from math import pi, remainder, isfinite
from copy import copy, deepcopy
from parallel_multistage import VARIANTS as PARALLEL_MULTISTAGE_VARIANTS

SPEED_KEYS = frozenset(('input_rpm', 'input_b_rpm', 'output_difference_rpm'))


def same_geometry(design, family, values):
    """The supported rotary families have no speed-dependent construction."""
    from precise_numbers import SOURCE_KEY
    def geometric(values):
        result={key:value for key,value in values.items() if key not in SPEED_KEYS and key!=SOURCE_KEY}
        sources={key:value for key,value in values.get(SOURCE_KEY,{}).items() if key not in SPEED_KEYS}
        if sources:result[SOURCE_KEY]=sources
        return result
    return bool(design and design.family==family and geometric(design.values)==geometric(values))



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
    # GTK adjustments return 18.0 for an unchanged validated tooth count 18.
    # Reuse the accepted physical scalars as well as their surfaces; only speed
    # values and their source map come from this operating-only edit. In
    # particular, Rust's integer tooth-count contract must remain intact.
    d.values = {key: value if key in SPEED_KEYS or key == '_decimal_inputs'
                else design.values[key] for key, value in values.items()}
    d.analysis = dict(design.analysis)
    for key in ('input', 'output', 'kinematics', 'interstage_mounting'):
        if key in d.analysis:d.analysis[key] = deepcopy(d.analysis[key])
    d.metrics = list(design.metrics)
    d.parts = [copy(p) for p in design.parts]
    for p in d.parts:
        p.port = dict(p.port)
    f, v, r = d.family, d.values, d.analysis
    rpm = v['input_rpm']
    if f == 'rack':
        from rack_geometry import operating
        operating(d)
    elif f == 'differential':
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
    elif f == 'parallel' and v['variant'] in PARALLEL_MULTISTAGE_VARIANTS:
        from parallel_multistage import apply_kinematics
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
    from rust_geometry import call
    return tuple(call('affine_multiply',dict(a=a,b=b)))

def translation(x=0, y=0, z=0):
    return (*IDENTITY[:12], x, y, z, 1.0)

def rotation(angle, axis=(0, 0, 1), pivot=(0, 0, 0)):
    from rust_geometry import call
    return tuple(call('affine_rotation',dict(angle=angle,axis=axis,pivot=pivot)))


def transform_points(m, points, check=None):
    from rust_geometry import call
    return [tuple(p) for p in call('affine_transform',dict(matrix=m,points=points),check=check)]


def transform(m, p):
    return transform_points(m,[p])[0]


def posed_triangles(m, triangles, check=None):
    points=transform_points(m,[p for triangle in triangles for p in triangle],check)
    return [tuple(points[i:i+3]) for i in range(0,len(points),3)]


def orbital_matrix(spin, orbit, center):
    from rust_geometry import call
    return tuple(call('affine_orbital',dict(spin=spin,orbit=orbit,center=center)))


def rigid(rate, pivot=(0, 0, 0), axis=(0, 0, 1)):
    return lambda phase: rotation(phase * rate, axis, pivot)

def orbital(spin, orbit, center):
    return lambda phase:orbital_matrix(phase*spin,phase*orbit,center)

def part_axis(p):
    if p.frame:
        o, *basis = p.frame
        pivot = tuple((o[i] + p.center[0] * basis[0][i] + p.center[1] * basis[1][i] for i in range(3)))
        return (pivot, basis[2])
    if p.axis_x:
        return ((0, p.center[1], p.z), (1, 0, 0))
    return ((*p.center, 0), (0, 0, 1))

@dataclass(frozen=True)
class _KernelPose:
    parameters: dict

    def __call__(self,phase):
        from rust_geometry import pose_matrices
        return pose_matrices(phase,[self.parameters])[0]

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
    phase_limits: tuple | None = None
    _frame_phase: object = field(default=None,init=False,repr=False)
    _frame_poses: dict = field(default_factory=dict,init=False,repr=False)
    _frame_matrices: dict = field(default_factory=dict,init=False,repr=False)
    # Full labelled orientation period; geometric tooth symmetry is not assumed.

    def matrix(self, index, phase):
        if isinstance(self.poses.get(index),_KernelPose):
            if phase != self._frame_phase or self.poses != self._frame_poses:
                from rust_geometry import pose_matrices
                rows=[(i,p.parameters) for i,p in self.poses.items() if isinstance(p,_KernelPose)]
                self._frame_matrices=dict(zip((i for i,_ in rows),pose_matrices(phase,[p for _,p in rows])))
                self._frame_phase=phase
                self._frame_poses=dict(self.poses)
            return self._frame_matrices[index]
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
        angle((index, 'spin'), rpm/ref)
        plan.poses[index] = _KernelPose(dict(kind='rotation',rate=rpm/ref,
            offset=plan.coordinate_offsets[index,'spin'],axis=axis or a,pivot=pivot or o))
        plan.rates[index] = (rpm / ref,)

    def orbit(index, spin, orbit, center):
        angle((index, 'spin'), spin)
        angle((index, 'orbit'), orbit)
        plan.poses[index] = _KernelPose(dict(kind='orbital',spin_rate=spin,
            spin_offset=plan.coordinate_offsets[index,'spin'],orbit_rate=orbit,
            orbit_offset=plan.coordinate_offsets[index,'orbit'],center=center))
    for i, p in enumerate(parts):
        if 'rpm' in p.port:
            global_axis = f in ('planetary', 'cycloidal', 'harmonic', 'wolfrom')
            spin(i, p.port['rpm'], (0, 0, 0) if global_axis else None)
    if f == 'rack':
        r=d.analysis['rack']['pitch_radius_mm']
        angle((1,'linear'),primary/ref)
        low,high=d.analysis['rack']['pinion_angle_limits_rad']
        rate=plan.coordinate_rates[1,'linear'];offset=plan.coordinate_offsets[1,'linear']
        plan.poses[1]=_KernelPose(dict(kind='linear',rate=rate,offset=offset,scale=r,axis=(1,0,0),limits=(low,high)))
        pinion=dict(plan.poses[0].parameters,limits=(low,high))
        plan.poses[0]=_KernelPose(pinion)
        plan.phase_limits=tuple(sorted(((low-offset)/rate,(high-offset)/rate))) if rate else (phase,phase)
        plan.message='Pinion rotation drives rack translation along +X. Preview stops at the finite working stroke.'
    elif f in ('spur', 'helical', 'double'):
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
    elif f == 'parallel' and v['variant'] in PARALLEL_MULTISTAGE_VARIANTS:
        pass  # Every rotating body already has an explicit shaft-indexed RPM port.
    elif f in ('bevel','hypoid','face'):
        pass  # Explicit RPM ports rotate about each part's physical shaft frame.
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
                plan.poses[i] = _KernelPose(dict(kind='rotation',rate=rate,offset=offset,axis=(1,0,0),pivot=(0,0,0)))
                plan.rates[i] = (rate,)
            elif group in ('output','spider'):
                plan.poses[i] = _KernelPose(dict(kind='differential',carrier_rate=wc,carrier_offset=oc,spin_rate=wo,spin_offset=oo))
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
