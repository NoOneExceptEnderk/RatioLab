"""Superfici esplicite condivise da preview e solido STEP, senza loft interpolati."""
from math import cos,sin,radians,sqrt,pi,acos,ceil
from geometry import profile_sections,section_holes,circle_info,circle


PALETTE=[(.23,.68,.82),(.96,.66,.33),(.48,.74,.59),(.69,.59,.86)]

def point(part,xy,z,angle):
    c,s=cos(angle),sin(angle);x,y=xy
    x,y=x*c-y*s+part.center[0],x*s+y*c+part.center[1]
    z+=part.z
    if part.frame:
        origin,*basis=part.frame
        return tuple(origin[i]+sum(q*basis[j][i] for j,q in enumerate((x,y,z))) for i in range(3))
    if part.axis_x:return (z-part.width/2,y+part.center[1],-x+part.z)
    return (x,y,z)


def section_loops(p,outer,z):
    loops=[]
    for j,loop in enumerate([outer]+section_holes(p,z,outer)):
        if not p.stations and (p.double or abs(p.twist)>1e-8):
            info=circle_info(loop)
            if info:
                x,y,r=info;n=max(len(loop),96,ceil(pi/acos(max(-1,min(1,1-.002/r)))))
                if n>4096:raise ValueError('Circle too large for the required precision.')
                loop=circle(r,n,(x,y))
        area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(loop,loop[1:]+loop[:1]))
        loops.append(list(reversed(loop)) if (area>0)!=(j==0) else loop)
    return loops


def rings(p):
    return [[[point(p,q,z,radians(angle)) for q in loop] for loop in section_loops(p,outer,z)] for z,angle,outer in profile_sections(p)]


def faces(p):
    if p.mesh:return [[[point(p,q[:2],q[2],0) for q in loop] for loop in face] for face in p.mesh]
    levels=rings(p);result=[]
    count=sum(2*len(loop) for level in levels[1:] for loop in level)+2
    if count>250000:raise ValueError('Solid too detailed: reduce tooth count, width or helix angle (250,000 face limit).')
    for lower,upper in zip(levels,levels[1:]):
        for a,b in zip(lower,upper):
            for j in range(len(a)):
                k=(j+1)%len(a)
                triangles=([a[j],a[k],b[j]],[a[k],b[k],b[j]]) if p.alternate_diagonal else ([a[j],a[k],b[k]],[a[j],b[k],b[j]])
                for tri in triangles:
                    u=[tri[1][i]-tri[0][i] for i in range(3)];v=[tri[2][i]-tri[0][i] for i in range(3)]
                    n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                    if sum(x*x for x in n)>1e-24:result.append([tri])
    def cleaned(loops):
        return [[q for i,q in enumerate(loop) if q!=loop[(i-1)%len(loop)]] for loop in loops]
    result.extend([cleaned([list(reversed(loop)) for loop in levels[0]]),cleaned(levels[-1])])
    return result


def signature(p):
    fs=faces(p);edges={};volume=0.;pts=[]
    for face in fs:
        for loop in face:
            pts.extend(loop)
            for a,b in zip(loop,loop[1:]+loop[:1]):
                key=tuple(sorted((a,b)));count,balance=edges.get(key,(0,0))
                edges[key]=(count+1,balance+(1 if (a,b)==key else -1))
            a=loop[0]
            for b,c in zip(loop[1:],loop[2:]):
                volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6
    if any(n!=2 or balance for n,balance in edges.values()):raise ValueError('Surface is not closed or has inconsistent orientation.')
    if volume<=0:raise ValueError('Solid volume is not positive.')
    return {'faces':len(fs),'vertices':len(set(pts)),'volume_mm3':volume,'min':[min(q[i] for q in pts) for i in range(3)],'max':[max(q[i] for q in pts) for i in range(3)]}


def step(p,name):
    """ISO 10303-21 FACETED_BREP: ogni lato usa gli stessi due triangoli della preview."""
    fs=faces(p);entities=[];points={}
    def add(value):entities.append(value);return len(entities)
    def ref(i):return '#'+str(i)
    def refs(ids):return '('+','.join(map(ref,ids))+')'
    def num(x):
        text=format(float(x),'.15g')
        return text if '.' in text or 'e' in text else text+'.'
    for face in fs:
        for loop in face:
            for q in loop:
                if q not in points:points[q]=add("CARTESIAN_POINT('',("+','.join(map(num,q))+"))")
    faceids=[]
    for face in fs:
        bounds=[]
        for j,loop in enumerate(face):
            wire=add("POLY_LOOP('',"+refs(points[q] for q in loop)+")")
            bounds.append(add(('FACE_OUTER_BOUND' if j==0 else 'FACE_BOUND')+"('',"+ref(wire)+",.T.)"))
        loop=face[0];a=loop[0];b=loop[1]
        u=tuple(b[i]-a[i] for i in range(3));length=sqrt(sum(x*x for x in u));u=tuple(x/length for x in u)
        n=[0.,0.,0.]
        for b,c in zip(loop,loop[1:]+loop[:1]):
            n[0]+=(b[1]-c[1])*(b[2]+c[2]);n[1]+=(b[2]-c[2])*(b[0]+c[0]);n[2]+=(b[0]-c[0])*(b[1]+c[1])
        length=sqrt(sum(x*x for x in n))
        if length<1e-15:raise ValueError('Degenerate face in the shared geometry.')
        n=tuple(x/length for x in n)
        axis=add("DIRECTION('',("+','.join(map(num,n))+"))")
        direction=add("DIRECTION('',("+','.join(map(num,u))+"))")
        placement=add("AXIS2_PLACEMENT_3D('',"+ref(points[a])+","+ref(axis)+","+ref(direction)+")")
        plane=add("PLANE('',"+ref(placement)+")")
        faceids.append(add("FACE_SURFACE('',"+refs(bounds)+","+ref(plane)+",.T.)"))
    shell=add("CLOSED_SHELL('',"+refs(faceids)+")")
    solid=add("FACETED_BREP('"+name.replace("'","''")+"',"+ref(shell)+")")
    mm=add("(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))")
    rad=add("(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))")
    sr=add("(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())")
    unc=add("UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-7),"+ref(mm)+",'distance_accuracy_value','')")
    context=add("(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(("+ref(unc)+")) GLOBAL_UNIT_ASSIGNED_CONTEXT("+refs([mm,rad,sr])+") REPRESENTATION_CONTEXT('',''))")
    shape=add("SHAPE_REPRESENTATION('',("+ref(solid)+"),"+ref(context)+")")
    application=add("APPLICATION_CONTEXT('configuration controlled 3d designs of mechanical parts and assemblies')")
    add("APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,"+ref(application)+")")
    product_context=add("PRODUCT_CONTEXT('',"+ref(application)+",'mechanical')")
    product=add("PRODUCT('RatioLab','RatioLab part','',("+ref(product_context)+"))")
    formation=add("PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('','',"+ref(product)+",.NOT_KNOWN.)")
    definition_context=add("PRODUCT_DEFINITION_CONTEXT('part definition',"+ref(application)+",'design')")
    definition=add("PRODUCT_DEFINITION('design','',"+ref(formation)+","+ref(definition_context)+")")
    product_shape=add("PRODUCT_DEFINITION_SHAPE('','',"+ref(definition)+")")
    add("SHAPE_DEFINITION_REPRESENTATION("+ref(product_shape)+","+ref(shape)+")")
    data='\n'.join(f'#{i}={v};' for i,v in enumerate(entities,1))
    return "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('RatioLab: shared preview geometry'),'2;1');\nFILE_NAME('part.step','2026-10-23T00:00:00',(''),(''),'RatioLab','RatioLab','');\nFILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));\nENDSEC;\nDATA;\n"+data+"\nENDSEC;\nEND-ISO-10303-21;\n"
