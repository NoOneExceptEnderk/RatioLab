# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Dimensional assemblies: teeth, shafts, flanges, seats and housings.
Reference geometry only; catalog bearings are applied by standard_parts.
No structural sizing is performed.
"""
from math import pi,sin,cos,hypot,radians
from parameter_errors import ParameterError
from geometry import Part,circle,polar,transformed,gear_part,cycloid,TAU,batch_circles

SILVER=(.65,.72,.8);BEARING=(.42,.49,.59);HOUSING=(.32,.39,.49)


def annulus(d,name,radius,bore,width,z=0,center=(0,0),holes=None,role='support',color=SILVER):
    loops=([circle(bore)] if bore else [])+list(holes or [])
    p=Part(name,circle(radius),loops,width,z,center,color=color,role=role)
    d.parts.append(p);return p



def _planetary_dimensions(v):
    # Same dimensional expressions and operation order as the assembly. Exact
    # inputs build sources first; one bounded Rust batch resolves the layout.
    from precise_numbers import symbolic,evaluate_sources,select_source
    q={key:symbolic(value) for key,value in v.items()}
    minimum=lambda *args:select_source('min',args)
    maximum=lambda values:select_source('max',values)
    m=q['module'];t=q['plate'];c=q['assembly_clearance'];bore=q['bore']
    mt=m/cos(radians(v.get('helix',0)));rshaft=bore/2
    stages=[(v['sun'],v['planet'],q['width'],0)]
    if v['variant'] in ('two_stage','two_stage_double'):
        stages.append((v['sun2'],v['planet2'],q['width2'],q['width']+3*t+4*c+q['stage_gap']))
    max_ring=maximum(mt*(zs+2*zp)/2+1.25*m+q['rim'] for zs,zp,w,z in stages)
    outside=max_ring+c+q['housing_wall'];bolt=minimum(1.5,q['rim']/4)
    bearingwall=maximum((.6,minimum(1.5,m*.65)));rbearing=rshaft+bearingwall
    rows=[]
    for zs,zp,w,z0 in stages:
        zr=zs+2*zp;a=mt*(zs+zp)/2
        rring=mt*zr/2+1.25*m+q['rim'];fixR=rring-q['rim']/2
        pin=maximum((.3,rshaft-minimum(c/2,rshaft*.15)))
        carrierR=a+pin+maximum((1.5,t*.7));tip_ring=mt*zr/2-m
        rows.append(dict(a=a,fixR=fixR,pin=pin,carrierR=carrierR,tip_ring=tip_ring,
            carrier_outside=carrierR+c,
            lower=z0-c-t,upper=z0+w+c,tie_length=w+2*c+2*t,top=z0+w+c+t,
            active=(w-v.get('gap',0))/2 if v['variant'] in ('double','two_stage_double') else w))
    bottom=-2*t-3*c;top=rows[-1]['top']+2*c;extension=q['shaft_extension']
    for i,(zs,zp,w,z0) in enumerate(stages):
        start=z0+w+c
        end=stages[i+1][3]+stages[i+1][2]*.65 if i+1<len(stages) else top+t+extension
        rows[i].update(coupling_start=start,coupling_width=end-start)
    return evaluate_sources(dict(stages=stages,rows=rows,rshaft=rshaft,
        outside=outside,bolt=bolt,rbearing=rbearing,bearing_outer=rbearing-.02,
        bearing_inner=rshaft+.02,bottom=bottom,top=top,
        input_width=stages[0][2]*.6-bottom+extension,input_z=bottom-extension,
        housing_width=top-bottom-t,housing_z=bottom+t,housing_bore=max_ring+c,
        diameter=2*outside,body_length=top+t-bottom))


@batch_circles()
def planetary(d):
    v=d.values;m=v['module'];pa=v['pressure'];backlash=v['backlash'];n=v['planets'];t=v['plate'];bore=v['bore']
    beta=v.get('helix',0);variant=v['variant'];layout=_planetary_dimensions(v)
    stages=layout['stages'];rshaft=layout['rshaft']
    outside=layout['outside'];bolt=layout['bolt'];rbearing=layout['rbearing'];ratio=1
    if v['rim']<2:raise ParameterError('planetary.rim', ('rim',), 'The assembly with fasteners requires a ring at least 2 mm thick.', 'Increase the ring thickness.')
    pair_plans=[]
    from internal_mesh import plan_planetary_internal_pair, validate_axial_pair
    from tooth_tips import parameters as tip_parameters
    for index,(zs,zp,w,z0) in enumerate(stages):
        tag=f'S{index+1}';zr=zs+2*zp;dims=layout['rows'][index];a=dims['a'];ratio*=1+zr/zs
        plan=plan_planetary_internal_pair(zp,zr,m,pa,beta,backlash);pair_plans.append(plan)
        def gear(name,teeth,center=(0,0),phase=0,helix=0,internal=False):
            role='ring' if internal else 'sun' if name=='Sun' else 'planet'
            p=gear_part(tag+'_'+name,teeth,m,pa,backlash,w,bore,center,phase,helix,internal,v['rim'],z0,ha=plan['ring_addendum_coefficient'] if internal else 1, minimum_join_radius_mm=plan['minimum_join_radius_mm'] if internal else None,
                        **tip_parameters(v,role+(str(index+1) if index else '')))
            if variant in ('double','two_stage_double'):
                p.double=True;p.gap=v['gap'];p.core_radius=min(hypot(x,y) for x,y in p.outer)*.96
                if not internal and rshaft>=p.core_radius-.25:raise ValueError('Bore too large for the continuous double helix hub.')
            d.parts.append(p);return p
        gear('Sun',zs,helix=beta)
        for j in range(n):
            theta=TAU*j/n;phase=(pi+theta*(zs+zp))/zp+pi
            planet=gear(f'Planet_{j+1}',zp,polar(a,theta),phase,-beta)
        ring_phase=(zp*(pi/zp+pi)-pi)/zr
        ring=gear('Ring',zr,phase=ring_phase,helix=-beta,internal=True)
        from tooth_tips import verify_internal_pair
        verification=verify_internal_pair(planet,ring,zp,zr,backlash)
        if verification:
            plan['verification']=verification
        axial_failure=validate_axial_pair(planet,ring,zp,zr)
        if axial_failure:
            plan['verification'].update(status='unresolved',failure_reason=axial_failure,certified_separation_lower_bound_mm=None)
        else:
            plan['verification']['axial_scope']='Ideal spur/twisted transverse sections; common phase ratio and groove material subsets; excludes exported surface interpolation.'
        ring.profile_metadata['tooth_profile']['construction_version']=plan['construction_version']
        if abs(ring.profile_metadata['tooth_profile']['involute_end_radius_mm']-plan['ring_join_radius_mm'])>1e-8:
            raise ValueError('Paired ring contour and plan disagree.')
        fixR=dims['fixR']
        # Axial fixing holes are entirely outside the roots of the internal teeth.
        holes=[circle(bolt,32,polar(fixR,TAU*j/4+pi/4)) for j in range(4)] if not beta else []
        ring.holes.extend(holes)
        pin=dims['pin'];carrierR=dims['carrierR']
        tip_ring=dims['tip_ring']
        if dims['carrier_outside']>=tip_ring:raise ValueError('Planet carrier too large for the ring: reduce bore/pins or enlarge the gearing.')
        pinholes=[circle(pin,48,polar(a,TAU*j/n)) for j in range(n)]
        annulus(d,tag+'_PlanetCarrier_lower',carrierR,rbearing,t,dims['lower'],holes=pinholes)
        annulus(d,tag+'_Flange_output',carrierR,rshaft,t,dims['upper'],holes=pinholes)
        annulus(d,tag+'_Retainer_ring_lower',layout['housing_bore'],dims['carrier_outside'],t,dims['lower'],holes=holes,role='housing',color=HOUSING)
        annulus(d,tag+'_Retainer_ring_upper',layout['housing_bore'],dims['carrier_outside'],t,dims['upper'],holes=holes,role='housing',color=HOUSING)
        for j in range(4 if not beta else 0):annulus(d,tag+f'_TieRod_ring_{j+1}',bolt,0,dims['tie_length'],dims['lower'],polar(fixR,TAU*j/4+pi/4),role='housing',color=HOUSING)
        for j in range(n):annulus(d,tag+f'_Pin_planet_{j+1}',pin,0,dims['tie_length'],dims['lower'],polar(a,TAU*j/n),role='support')
        annulus(d,tag+'_Bearing_planetcarrier_envelope',layout['bearing_outer'],layout['bearing_inner'],t,dims['lower'],role='support',color=BEARING)
    bottom=layout['bottom'];top=layout['top']
    annulus(d,'Shaft_input',rshaft,0,layout['input_width'],layout['input_z'])
    for index,(zs,zp,w,z0) in enumerate(stages):
        dims=layout['rows'][index]
        annulus(d,f'S{index+1}_'+('Coupling_interstage' if index+1<len(stages) else 'Shaft_output'),
                rshaft,0,dims['coupling_width'],dims['coupling_start'])
    # Fixed enclosure and removable end plates. Rotor plates have axial clearance to both covers.
    annulus(d,'Housing_tubular',outside,layout['housing_bore'],layout['housing_width'],layout['housing_z'],role='housing',color=HOUSING)
    annulus(d,'Cover_input',outside,rbearing,t,bottom,role='housing',color=HOUSING)
    annulus(d,'Cover_output',outside,rbearing,t,top,role='housing',color=HOUSING)
    annulus(d,'Bearing_input_envelope',layout['bearing_outer'],layout['bearing_inner'],t,bottom,color=BEARING)
    annulus(d,'Bearing_output_envelope',layout['bearing_outer'],layout['bearing_inner'],t,top,color=BEARING)
    label={'spur':'Single stage · spur','helical':'Single stage · helical','double':'Single stage · double helical','two_stage':'Two stages in cascade','two_stage_double':'Two stages · double helical'}[variant]
    d.metrics=[label+f' · reduction {ratio:.5g}:1',f'{len(stages)} stages · {n} planets per stage',f'Z sun / planet / ring: '+ ' → '.join(f'{zs}/{zp}/{zs+2*zp}' for zs,zp,w,z in stages),f"Housing diameter {layout['diameter']:.2f} mm · body length {layout['body_length']:.2f} mm"]
    for i,plan in enumerate(pair_plans,1):
        d.metrics.append(f"Stage {i} ring: derived ha {plan['ring_addendum_coefficient']:.6f} · tip shortened {plan['ring_tip_relief_mm']:.4f} mm · neutral transverse polygon clearance {plan['verification']['status']}")
    from engineering import mesh
    d.analysis.update(signed_ratio=ratio,meshes=[])
    for index,((zs,zp,w,z0),plan,dims) in enumerate(zip(stages,pair_plans,layout['rows'])):
        active=dims['active']
        for a,b,internal in [(zs,zp,False),(zp,zs+2*zp,True)]:
            suffix=str(index+1) if index else ''
            q=mesh(a,b,m,pa,beta,active,internal=internal,strict=False,backlash=backlash,internal_plan=plan if internal else None,
                   tooth_tips1=tip_parameters(v,('planet' if internal else 'sun')+suffix),
                   tooth_tips2=tip_parameters(v,('ring' if internal else 'planet')+suffix))
    # Do not divide torque by planet count: the load-sharing factor is unknown.
            q['torque_factor']=None;d.analysis['meshes'].append(q)
    d.notes.append('Planetary rings use paired shortened involute teeth (planetary_paired_involute_v1). Neutral-backlash transverse polygon verification excludes unsampled analytic curves, exported 3D triangle interpolation, cutter envelopes, radial assembly and manufacturing checks.')
    d.notes.append('Contact ratio calculated for both meshes of each stage. Forces per planet are not estimated: actual load sharing requires stiffness and load distribution factors.')
    d.notes.extend(['Fixed ring; sun input and carrier output. In two stage models, the first stage output drives the second stage sun.',
        'Dimensional assembly with flanges, pins, shafts, housing and bearing envelopes. Seats, fasteners and fits are nominal: keys, threads, seals and catalog bearings are not generated. No automatic CAD motion joints.'])
    if beta:d.notes.append('Helices: sun of one hand, planets and ring of the opposite hand. Axial forces require specific bearing sizing. Flanges retain the ring without mounting holes in the swept region; clamping must be designed.')
    if min(min(zs,zp) for zs,zp,w,z in stages)<2/sin(radians(pa))**2:d.notes.append('Low tooth count: check undercut and profile shift.')


def cycloidal(d):
    v=d.values;n=v['pins'];R=v['radius'];e=v['eccentric'];r=v['pin_radius'];c=v['clearance'];w=v['width'];k=v['output_count'];ro=v['output_pin'];outR=v['output_radius'];bore=v['bore'];t=v['plate'];ax=v['assembly_clearance']
    count=2 if v['variant']=='dual' else 1;disc_gap=v.get('disc_gap',ax);span=count*w+(count-1)*disc_gap
    pts=cycloid(n,R,e,r,c,tolerance=v['profile_tolerance']);minr=min(hypot(x,y) for x,y in pts);hole_r=ro+e+v['output_clearance']
    if outR+hole_r>minr-.8 or outR-hole_r<bore/2+.8:raise ParameterError('cycloidal.output_material', ('output_radius', 'output_pin', 'eccentric', 'output_clearance', 'bore', 'radius', 'pins', 'pin_radius', 'clearance'), 'Output holes leave no material between the eccentric seat and disc edge.', 'Reduce the output hole size or adjust the output pitch radius to leave material on both sides.')
    if 2*hole_r>=2*outR*sin(pi/k)-.5:raise ParameterError('cycloidal.output_overlap', ('output_pin', 'eccentric', 'output_clearance', 'output_radius', 'output_count'), 'Output holes overlap.', 'Reduce the output hole size or pin count, or increase the output pitch radius.')
    rin=v['input_shaft']/2;rout=v['output_shaft']/2;cam=.72*bore/2;radial=min(.08,ax/3)
    if rin+e+.4>=cam:raise ParameterError('cycloidal.input_shaft', ('input_shaft', 'eccentric', 'bore'), 'Input shaft too large for the eccentricity and seat: reduce shaft diameter/eccentricity or enlarge the eccentric seat.', '')
    if bore/2-cam<.6:raise ParameterError('cycloidal.bearing_seat', ('bore',), 'Seat too small for the eccentric bearing.', 'Increase the eccentric seat diameter.')
    flangeR=outR+ro+max(2,t*.8)
    if rout+1.5>=outR-ro or flangeR+ax>=R-r:raise ParameterError('cycloidal.output_flange', ('output_shaft', 'output_radius', 'output_pin', 'plate', 'assembly_clearance', 'radius', 'pin_radius'), 'Incompatible output flange: reduce shaft/pins or increase ring radius.', '')
    outside=R+r+v['housing_wall'];inside=R+r+ax
    for j in range(count):
        phase=j*pi;delta=-phase/(n-1);center=polar(e,phase);z=j*(w+disc_gap)
        # Offset phase is solved from the input crank angle. Holes keep a common output datum.
        holes=[circle(bore/2)]+[circle(hole_r,64,polar(outR,TAU*i/k)) for i in range(k)]
        d.parts.append(Part(f'Disc_cycloidal_{j+1}',transformed(pts,angle=delta),holes,w,z,center))
        # Offset cam: outside is eccentric, the shaft bore remains on the world axis.
        # The driving cam uses gear visibility; Supports hides its bearing, not the cam.
        annulus(d,f'Eccentric_{j+1}',cam,0,w,z,center,holes=[circle(rin,96,(-center[0],-center[1]))],role='gear')
        annulus(d,f'Bearing_eccentric_{j+1}_envelope',bore/2-radial,cam+radial,w-2*radial,z+radial,center,color=BEARING)
    bottom=-ax-t;top=span+ax+t
    pinholes=[circle(r,48,polar(R,TAU*j/n)) for j in range(n)]
    for j in range(n):annulus(d,f'Roller_ring_{j+1}',r,0,top+t-bottom,bottom,polar(R,TAU*j/n),role='gear',color=(.64,.7,.78))
    outputholes=[circle(ro,48,polar(outR,TAU*j/k)) for j in range(k)]
    for j in range(k):annulus(d,f'Pin_output_{j+1}',ro,0,span+ax+t,0,polar(outR,TAU*j/k),role='gear',color=(.94,.65,.3))
    annulus(d,'Flange_output',flangeR,rout,t,span+ax,holes=outputholes)
    annulus(d,'Shaft_output',rout,0,t+8,span+ax)
    output_bearing_outer=flangeR+max(1,t*.65)
    if output_bearing_outer+ax>=R-r:raise ValueError('Insufficient space for the output flange support seat.')
    annulus(d,'Bearing_flanges_output_envelope',output_bearing_outer-.02,flangeR+.02,t,span+ax,color=BEARING)
    annulus(d,'Seat_support_output',inside,output_bearing_outer,t,span+ax,holes=pinholes,role='housing',color=HOUSING)
    annulus(d,'Shaft_input',rin,0,span-bottom+8,bottom-8)
    bearing=rin+max(.8,min(1.5,t*.5))
    annulus(d,'Cover_input',outside,bearing,t,bottom,holes=pinholes,role='housing',color=HOUSING)
    annulus(d,'Bearing_input_envelope',bearing-.02,rin+.02,t,bottom,color=BEARING)
    annulus(d,'Housing_tubular',outside,inside,top-bottom-t,bottom+t,role='housing',color=HOUSING)
    annulus(d,'Cover_output',outside,flangeR+ax,t,top,holes=pinholes,role='housing',color=HOUSING)
    d.metrics=[('Dual disc · opposing eccentrics' if count==2 else 'Complete single disc')+f' · reduction −{n-1}:1',f'{n-1} lobes · {n} rollers · {k} output pins',f'Discs: {count} × {w:g} mm · spacing {disc_gap:g} mm',f'Output holes Ø {2*hole_r:.3f} mm · housing Ø {2*outside:.2f} mm']
    d.analysis.update(signed_ratio=-(n-1),shortening_coefficient=e*n/R,output_hole_radius_mm=hole_r,profile_clearance_mm=c,output_clearance_mm=v['output_clearance'],disc_gap_mm=disc_gap)
    d.notes.extend(['Sampled offset profile with radial clearance. Output through shared pins and a flange; includes eccentric cams, shafts, seats and bearing envelopes.',
        'Dimensional assembly: bearing envelopes are not catalog parts; keys, threads and seals are not generated. Complete nominal fits before construction.'])
    if count==2:d.notes.append(f'Second profile phase: −180°/{n-1} = {-180/(n-1):.5g}°. Eccentrics at 180°; holes share the same output pins. Compensates ideal eccentric force; residual dynamic torque is not automatically eliminated.')
    else:d.notes.append('The single disc requires specific balancing: no calculated counterweight is included.')
