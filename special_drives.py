# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Cylindrical ZA/ZI worms and strain wave envelopes. Sources are in VARIANTS.md.
Worm wheels and strain wave teeth remain concept approximations.
"""
from math import pi,sin,cos,tan,atan,acos,atan2,sqrt,hypot,radians,degrees,ceil
from geometry import CircleProfile,Part,gear_part,involute,circle,circle_info,polar,clean,sample_curve,TAU

def round_loop(r):
    return circle(r,max(96,ceil(pi/acos(max(-1,min(1,1-.002/r))))))

def za_profile(starts,module,diameter,pressure,backlash):
    rp=diameter/2;root=rp-1.25*module;tip=rp+module;k=module*starts/2;pitch=TAU/starts
    def half(r):return pi/(2*starts)-(r-rp)*tan(radians(pressure))/k-backlash/(4*k)
    if half(tip)<=0 or half(root)>=pitch/2:raise ValueError('Profilo ZA appuntito o fianchi sovrapposti: controllare angolo, modulo e clearance.')
    pts=[]
    for j in range(starts):
        a=j*pitch
        pts+=sample_curve(lambda q:polar(root,a+q),-pitch/2,-half(root))[:-1]
        pts+=sample_curve(lambda r:polar(r,a-half(r)),root,tip)[:-1]
        pts+=sample_curve(lambda q:polar(tip,a+q),-half(tip),half(tip))[:-1]
        pts+=sample_curve(lambda r:polar(r,a+half(r)),tip,root)[:-1]
        pts+=sample_curve(lambda q:polar(root,a+q),half(root),pitch/2)[:-1]
    return clean(pts)

def zi_profile(starts,module,diameter,pressure,backlash):
    """Transverse screw involute; radial runout remains a study construction."""
    rp=diameter/2;rb=rp*cos(radians(pressure));root=rp-1.25*module;tip=rp+module
    inv=lambda r:sqrt(max(0,(r/rb)**2-1))-atan(sqrt(max(0,(r/rb)**2-1)))
    angle=lambda r:pi/(2*starts)-backlash/(4*rp)+inv(rp)-inv(r)
    start=max(root,rb);pitch=TAU/starts;points=[]
    if angle(tip)<=0 or angle(start)>=pitch/2:raise ValueError('Impossible ZI screw flank thickness.')
    for j in range(starts):
        a=j*pitch;ar=angle(start);at=angle(tip)
        points+=sample_curve(lambda q:polar(root,a+q),-pitch/2,-ar)[:-1]
        points+=[polar(root,a-ar)]
        points+=sample_curve(lambda r:polar(r,a-angle(r)),start,tip)[:-1]
        points+=sample_curve(lambda q:polar(tip,a+q),-at,at)[:-1]
        points+=sample_curve(lambda r:polar(r,a+angle(r)),tip,start)
        points+=[polar(root,a+ar)]
        points+=sample_curve(lambda q:polar(root,a+q),ar,pitch/2)[1:]
    return clean(points)

def worm(d):
    v=d.values;m=v['module'];z=v['teeth'];starts=v['starts'];D=v['diameter'];length=v['length'];width=v['width'];bore=v['bore'];hand=v['worm_hand']
    lead=pi*m*starts;gamma=atan(m*starts/D);mn=m*cos(gamma);an=degrees(atan(tan(radians(v['pressure']))*cos(gamma)));root=D/2-1.25*m
    if root<=bore/2+.5:raise ValueError('Bore too large for the worm root diameter.')
    jl=v['journal_length'];jr=v['journal_diameter']/2
    if jl and (jr>root or jr<=bore/2+.5):raise ValueError('Journals must fit between the bore and thread root, with at least 0.5 mm wall thickness.')
    if v['variant']=='za':outline=za_profile(starts,m,D,v['pressure'],v['backlash'])
    else:
        beta=pi/2-gamma;at=degrees(atan(tan(radians(an))/cos(beta)))
    # Axial tooth thickness becomes transverse thickness through cot(gamma).
        outline=zi_profile(starts,m,D,at,v['backlash']/tan(gamma))
    radius=D/2+m;step=min(6,degrees(2*acos(max(0,1-.02/radius))))
    turns=length/lead;n=max(1,ceil(360*turns/step))
    hole=[round_loop(bore/2)] if bore else []
    if 2*(len(outline)+sum(len(h) for h in hole))*(n+6)>250000:raise ValueError('Worm too detailed (250,000 face limit): reduce length, diameter or starts, or increase module.')
    stations=[]
    def level(z,outer):stations.append(dict(z=z,outer=outer,holes=hole))
    def rotated(z,radius=None):
        angle=TAU*(z-jl)/lead
        return [polar(radius if radius is not None else hypot(x,y),atan2(y,x)+angle) for x,y in outline]
    if jl:level(0,rotated(jl,jr));level(jl,rotated(jl,jr))
    for j in range(n+1):
        q=jl+length*j/n;level(q,rotated(q))
    if jl:level(jl+length,rotated(jl+length,jr));level(2*jl+length,rotated(jl+length,jr))
    if hand<0:
    # Mirror the triangulated faces too, preserving volume regardless of the diagonal.
        mirror=lambda loop:[(x,-y) for x,y in reversed(loop)]
        outline=mirror(outline);hole=[mirror(h) for h in hole]
        stations=[dict(z=s['z'],outer=mirror(s['outer']),holes=hole) for s in stations]
    p=Part('Screw_'+v['variant'].upper(),outline,hole,length+2*jl,twist=hand*360*turns,axis_x=True,color=(.95,.65,.3),stations=stations,alternate_diagonal=hand<0);p.profile_metadata['screw_profile']=dict(method=v['variant'].upper()+' cylindrical screw flanks',root_runout='unblended study runout',conjugate_wheel=False)
    d.parts.append(p)
    wheel=gear_part('Wheel_concept',z,mn,an,v['backlash'],width,v['wheel_bore'],helix=degrees(gamma));wheel.center=(0,-(D+m*z)/2);wheel.z=-width/2;wheel.color=(.23,.68,.82)
    # Cylinder envelope gives the wheel a real throat. Tooth flanks remain
    # a helical surrogate; this does not solve the worm/hob flank envelope.
    throat_radius=D/2+m
    if width/2>=throat_radius*.95:raise ValueError('Wheel too wide for the cylindrical throat study (half width < 0.95 worm tip radius).')
    maxstep=2*acos(max(-1,min(1,1-.01/throat_radius)))
    intervals=max(4,ceil(2*__import__('math').asin(width/(2*throat_radius))/maxstep))
    if intervals%2:intervals+=1
    wheel.stations=[]
    for j in range(intervals+1):
        h=width*j/intervals;q=h-width/2;delta=throat_radius-sqrt(throat_radius**2-q*q)
        angle=radians(wheel.twist)*q/width
        contour=[polar(hypot(x,y)+delta,atan2(y,x)+angle) for x,y in wheel.outer]
        wheel.stations.append(dict(z=h,outer=contour,holes=wheel.holes))
    if hand<0:
        def mirror_profile(loop):
            mirrored=[(x,-y) for x,y in reversed(loop)]
            if isinstance(loop,CircleProfile) and loop.intact():
                return CircleProfile(mirrored,loop.radius,(loop.center[0],-loop.center[1]))
            return mirrored
        wheel.outer=mirror_profile(wheel.outer);wheel.holes=[mirror_profile(h) for h in wheel.holes]
        wheel.stations=[dict(z=s['z'],outer=mirror_profile(s['outer']),holes=wheel.holes) for s in wheel.stations]
        wheel.twist=-wheel.twist;wheel.alternate_diagonal=True
    wheel.profile_metadata['wheel_throat']=dict(method='worm tip-cylinder throat; helical flank surrogate',radius_mm=throat_radius,max_radial_sag_mm=throat_radius-sqrt(throat_radius**2-width**2/4),axial_chord_threshold_mm=.01,conjugate=False)
    d.parts.append(wheel)
    d.metrics=[f'Worm cilindrica {v["variant"].upper()} · nominal ratio {z/starts:g}:1',f'{starts} principio/i · avanzamento {lead:.3f} mm · γ {degrees(gamma):.3f}°',f'Centre distance {(D+m*z)/2:.3f} mm · length filetto {length:g} mm',f'Codoli {jl:g} mm per side · total length {length+2*jl:g} mm']
    d.analysis['wheel_geometry']=wheel.profile_metadata['wheel_throat']
    d.analysis.update(signed_ratio=hand*z/starts,worm_axis='+X',wheel_axis='+Z',wheel_side='negative Y',profile=v['variant'].upper(),lead_mm=lead,lead_angle_deg=degrees(gamma),normal_module_mm=mn,normal_pressure_deg=an,center_distance_mm=(D+m*z)/2,thread_turns=turns,thread_length_mm=length,journal_length_mm=jl)
    d.notes+=['Signed worm ratio follows the displayed +X worm / +Z wheel axes (wheel on negative Y): left hand reverses wheel rotation.',
        'ZA worm profile: straight flanks in axial section; ZI: involute in transverse section. Helical surfaces use a nominal angular sagitta of 0.02 mm; geometry is shared by CAD and preview.',
        'ASSEMBLY STUDY ONLY: the worm uses the stated geometric profile; the wheel has a worm tip-cylinder throat with approximate helical flanks, not a conjugate worm/hob envelope. Contact, interference and manufacturability of the pair are unverified. Self locking is not claimed.']
    d.requirements.append('Design worm/wheel supports, bearings, retainers, fasteners and lubrication; a conjugate wheel profile is not included.')

def ellipse_axes(radius,amplitude):
    """Preserve the numerical pitch-line perimeter using periodic quadrature."""
    a=radius+amplitude;lo=radius*.1;hi=radius
    def perimeter(b):
        return sum(hypot(a*sin(TAU*(j+.5)/1024),b*cos(TAU*(j+.5)/1024)) for j in range(1024))*TAU/1024
    if perimeter(lo)>TAU*radius:raise ValueError('Deformation too large for the pitch radius.')
    for _ in range(45):
        b=(lo+hi)/2
        if perimeter(b)>TAU*radius:hi=b
        else:lo=b
    return a,(lo+hi)/2

def refine_angles(points,radius):
    maxstep=2*acos(max(0,1-.002/radius));out=[]
    for a,b in zip(points,points[1:]+points[:1]):
        delta=(atan2(b[1],b[0])-atan2(a[1],a[0]))%TAU
        if delta>TAU-1e-8:delta=0
        if delta>pi:raise ValueError('Non-monotonic angles in the flexible profile.')
        # Radial edges have delta zero; retain them for the toothed contour.
        n=max(1,ceil(delta/maxstep))
        if n>1000:raise ValueError('Non-monotonic tooth contour in the cup construction.')
        out.extend([(a[0]+(b[0]-a[0])*j/n,a[1]+(b[1]-a[1])*j/n) for j in range(n)])
    return out

def harmonic(d):
    v=d.values;z=v['teeth'];m=v['module'];rp=m*z/2;root=rp-1.25*m;inner=root-v['wall'];w=v['width'];L=v['cup_length'];t=v['diaphragm'];variant=v['variant'];amp=m*v['wave_factor'];bearing=v['bearing_thickness'];clearance=v['wave_clearance']
    if t>=L-1:raise ValueError('Diaphragm/flange too thick for the flexible body length.')
    a,b=ellipse_axes(rp,amp)
    from wave_geometry import map_point, arc_coefficients
    def deform(points,weight=1):return [map_point(atan2(y,x),hypot(x,y)-rp,weight,a,b,rp) for x,y in points]
    if b-1.25*m-v['wall']-bearing-2*clearance<=v['bore']/2+.5:raise ValueError('Bore/bearing too large for the wave generator; reduce bore, deformation or thicknesses.')
    gear=gear_part('Flexspline_'+variant,z,m,v['pressure'],v['backlash'],w)
    flange=v.get('flange_width',0);base_radius=root+flange
    reference=refine_angles(gear.outer,max(base_radius,rp+m+amp))
    # Radial edges become coincident vertices in the circular body. Normalize
    # them to avoid tiny faces caused by rounded profile coordinates.
    angles=[];radii=[]
    for x,y in reference:
        theta=atan2(y,x)
        if angles and abs((theta-angles[-1]+pi)%TAU-pi)<1e-8:theta=angles[-1]
        r=hypot(x,y);r=root if abs(r-root)<1e-8 else r
        angles.append(theta);radii.append(r)
    reference=[polar(r,q) for r,q in zip(radii,angles)]
    outer_body=[polar(root,q) for q in angles]
    deformed_body=deform(outer_body)
    toothed=deform(reference)
    count=max(192,len(round_loop(inner+amp)))
    inner_round=circle(inner,count);inner_deformed=deform(inner_round)
    if variant=='hat':base_outer=[polar(base_radius,q) for q in angles];bottom_hole=inner_round
    else:
        if v['output_bore']/2>=inner-.5:raise ValueError('Output bore too large for the cup diaphragm.')
        if not v['output_bore']:raise ValueError('For the cup, use an output bore greater than zero (annular diaphragm).')
        base_outer=outer_body;bottom_hole=circle(v['output_bore']/2,count)
    stations=[]
    def level(h,outer,hole,outer_reference=None,hole_reference=None,weight=0):
        # Immutable material coordinates supplied by construction avoid a
        # nonlinear inverse for every preview vertex on GTK's main thread.
        material=lambda loop:[(atan2(y,x),hypot(x,y)-rp,weight) for x,y in loop]
        stations.append(dict(z=h,outer=outer,holes=[hole],
            material_outer=material(outer if outer_reference is None else outer_reference),
            material_holes=[material(hole if hole_reference is None else hole_reference)]))
    level(0,base_outer,bottom_hole);level(t,base_outer,bottom_hole)
    level(t,outer_body,inner_round)
    # Blend axially from the circular body to the deformed tooth section.
    for j in range(1,7):
        f=j/6;h=t+(L-t)*f
        out=deform(outer_body,f)
        hole=deform(inner_round,f)
        level(h,out,hole,outer_body,inner_round,f)
    level(L,toothed,inner_deformed,reference,inner_round,1);level(L+w,toothed,inner_deformed,reference,inner_round,1)
    p=Part('Flexspline_'+variant,toothed,[inner_deformed],L+w,-L,stations=stations);d.parts.append(p)
    ring=gear_part('Circular_spline_concept',z+2,m,v['pressure'],v['backlash'],w,phase=pi/(z+2),internal=True,rim=v['rim']);ring.color=(.69,.59,.86);d.parts.append(ring)
    # The bearing is a deformed envelope, not an identified catalog part.
    outer=[polar(hypot(x,y)-clearance,atan2(y,x)) for x,y in inner_deformed]
    bore=[polar(hypot(x,y)-clearance-bearing,atan2(y,x)) for x,y in inner_deformed]
    cam=[polar(hypot(x,y)-2*clearance-bearing,atan2(y,x)) for x,y in inner_deformed]
    d.parts.append(Part('Bearing_wave_envelope',outer,[bore],w,role='support',color=(.52,.61,.7)))
    d.parts.append(Part('Generator_wave_concept',cam,[round_loop(v['bore']/2)] if v['bore'] else [],w,color=(.95,.65,.3)))
    # Ring, cam and bearing use the same shared geometry path; the CAD kernel
    # does not independently reconstruct the deformed tooth profiles.
    ring.outer=round_loop(circle_info(ring.outer)[2])
    for q in d.parts[1:]:q.stations=[dict(z=0,outer=q.outer,holes=q.holes),dict(z=q.width,outer=q.outer,holes=q.holes)]
    circular=v['harmonic_output']=='circular';ratio=(z+2)/2 if circular else -z/2
    d.metrics=[f'Strain wave · {variant.replace("_"," ")} · ratio {ratio:+g}:1',f'Flexspline {z} · ring {z+2} teeth · body {L:g} mm',f'Linea primitiva: semiassi {a:.3f} / {b:.3f} mm',f'Diaphragm/flange {t:g} mm · wave bearing {bearing:g} mm']
    d.analysis['wave_mapping']=dict(method='uniform pitch arc length with local normal tooth offsets',arc_fourier_modes=8,arc_coefficients=list(arc_coefficients(a,b,rp)),aspect_q=(a*a-b*b)/(a*a+b*b),domain_max_q=.25,elastic_solution=False,conjugate=False)
    p.profile_metadata['wave_mapping']=d.analysis['wave_mapping']
    p.profile_metadata['undeformed_tooth_reference']=gear.profile_metadata['tooth_profile']
    d.analysis.update(signed_ratio=ratio,illustrative_amplitude_mm=amp,pitch_ellipse_semiaxes_mm=[a,b],reference_pitch_perimeter_mm=TAU*rp,harmonic_output=v['harmonic_output'],housing_variant=variant)
    d.notes+=['STRAIN WAVE GEOMETRIC STUDY ONLY: cup/diaphragm or external flange form one continuous flexible solid. Axial circular→deformed transition with uniform pitch arc length and locally normal tooth orientation. This is neither an elastic solution nor a stress state.',
        'Wave generator and bearing envelope follow the deformed cavity with separate radial clearances. The bearing envelope is not a selected commercial component.',
        'Arc-length mapped involute study teeth, not industrial conjugate profiles: interference is possible. Cup/flat cup/silk hat outer shapes do not certify load capacity. Design supports, fatigue fillets and fasteners.',
        'Wave generator input; '+('fixed flexspline, ring output (same direction).' if circular else 'fixed ring, flexspline output (opposite direction).')]
    d.requirements.append('Design conjugate profiles, flexspline elastic/fatigue checks, fillets, flange and fasteners, actual bearings and seals.')
