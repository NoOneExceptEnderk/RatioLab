# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent exact-source, complete-cap and actual-output error witnesses."""
from dataclasses import replace
from fractions import Fraction
import json,math,os,random,shutil,struct,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import mpmath as mp
from geometry import generate
from geometry_error_budget import audit,_cap_cover,UnsupportedBudget,available_report
from geometry_quality import report
from rust_geometry import call
from solid_geometry import section_loops
from stl_export import triangles,write_stl


def rotate(xy,angle):
    x,y=xy;return x*mp.cos(angle)-y*mp.sin(angle),x*mp.sin(angle)+y*mp.cos(angle)


def reference(parameters,packet):
    """Original moving-rack equation and polar involute; no interval code."""
    z=mp.mpf(parameters.get('z',24));m=mp.mpf(parameters.get('mt',2))
    alpha=mp.mpf(parameters.get('pressure',20))*mp.pi/180
    backlash=mp.mpf(parameters.get('backlash','0.15'));shift=mp.mpf(parameters.get('shift',0))
    ha=mp.mpf(parameters.get('ha',1));hf=mp.mpf(parameters.get('hf','1.25'))
    beta=mp.mpf(parameters.get('helix',0))*mp.pi/180;cb=mp.cos(beta)
    at=mp.atan(mp.tan(alpha)/cb)
    rp=z*m/(2*cb);rb=rp*mp.cos(at);root=rp-m*(hf-shift);tip=rp+m*(ha+shift)
    land=mp.pi*m/4+backlash*cb/4-hf*m*mp.tan(alpha)
    rho=min(mp.mpf('.3')*m,(land-mp.mpf('.025')*m)*mp.cos(alpha)/(1-mp.sin(alpha)))
    uc=land-rho*(1-mp.sin(alpha))/mp.cos(alpha);vc=-hf*m+rho+shift*m
    half=mp.pi/(2*z)+2*shift*mp.tan(alpha)/z-backlash/(4*rp)
    offset=half+mp.tan(at)-at
    def corner(t):
        u=(uc+rho*mp.cos(t))/cb;v=vc+rho*mp.sin(t)
        dx=-rho*mp.sin(t)/cb;dy=rho*mp.cos(t)
        phi=(u+v*dy/dx)/rp
        return rotate((u-rp*phi,rp+v),-mp.pi/2+mp.pi/z-phi)
    def flank(t):
        radius=rb*mp.sqrt(1+t*t);angle=offset-t+mp.atan(t)
        return radius*mp.cos(angle),radius*mp.sin(angle)
    def residual(t):
        q=corner(t);r=mp.sqrt(sum(x*x for x in q));roll=mp.sqrt((r/rb)**2-1)
        return mp.atan2(q[1],q[0])-offset+roll-mp.atan(roll)
    trim=packet['trim']
    end= -alpha if trim['kind']=='analytic_tangent' else mp.findroot(residual,tuple(mp.mpf(x) for x in trim['end_rad']))
    start_radius=mp.sqrt(sum(x*x for x in corner(end)));roll0=mp.sqrt((start_radius/rb)**2-1)
    roll1=mp.sqrt((tip/rb)**2-1);ar=mp.pi/z-uc/(cb*rp);at=offset-roll1+mp.atan(roll1)
    def curve(descriptor,t):
        lo=mp.mpf(descriptor['start']);hi=mp.mpf(descriptor['end']);t=mp.mpf(t)
        if descriptor['kind']=='rack_corner':return corner(-mp.pi/2+(t-lo)/(hi-lo)*(end+mp.pi/2))
        if descriptor['kind']=='involute_flank':
            oldrb=mp.mpf(descriptor['rb'])
            old=lambda r:mp.sqrt((r/oldrb)**2-1)
            return flank(roll0+(old(t)-old(lo))/(old(hi)-old(lo))*(roll1-roll0))
        tag=descriptor['tag']
        start,finish,radius=((-mp.pi/z,-ar,root) if tag=='root' else
                             (ar,mp.pi/z,root) if tag=='root_right' else (-at,at,tip))
        angle=start+(t-lo)/(hi-lo)*(finish-start)
        return radius*mp.cos(angle),radius*mp.sin(angle)
    return dict(corner=corner,flank=flank,residual=residual,end=end,roll0=roll0,roll1=roll1,
        root=root,tip=tip,rb=rb,curve=curve)


def distance(p,a,b):
    d=[b[k]-a[k] for k in range(len(p))];den=sum(x*x for x in d)
    t=max(mp.mpf(0),min(mp.mpf(1),sum((p[k]-a[k])*d[k] for k in range(len(p)))/den)) if den else mp.mpf(0)
    return mp.sqrt(sum((p[k]-a[k]-t*d[k])**2 for k in range(len(p))))


def point_triangle_distance(point,triangle):
    """Independent plane projection, then three segment projections."""
    a,b,c=triangle
    u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)];w=[point[k]-a[k] for k in range(3)]
    dot=lambda x,y:sum(a*b for a,b in zip(x,y))
    uu,vv,uv,wu,wv=dot(u,u),dot(v,v),dot(u,v),dot(w,u),dot(w,v)
    den=uu*vv-uv*uv
    if den>0:
        s=(wu*vv-wv*uv)/den;t=(wv*uu-wu*uv)/den
        if s>=0 and t>=0 and s+t<=1:return math.sqrt(sum((w[k]-s*u[k]-t*v[k])**2 for k in range(3)))
    def edge(x,y):
        d=[y[k]-x[k] for k in range(3)];den=dot(d,d)
        t=max(0.,min(1.,dot([point[k]-x[k] for k in range(3)],d)/den)) if den else 0.
        return math.sqrt(sum((point[k]-x[k]-t*d[k])**2 for k in range(3)))
    return min(edge(a,b),edge(b,c),edge(c,a))


class TotalErrorBudgetTests(unittest.TestCase):
    def test_outward_functions_enclose_independent_high_precision_values(self):
        rng=random.Random(20261104)
        with mp.workdps(140):
            intervals=[('-6.3','-6.2'),('-.001','.001'),('1.5707963267948966192313216916397514420985','1.5707963267948966192313216916397514420987'),
                ('3.14159265358979323846264338327950288419','3.14159265358979323846264338327950288420')]
            intervals += [(format(x,'.25f'),format(x+rng.uniform(0,.15),'.25f')) for x in [rng.uniform(-6,6) for _ in range(20)]]
            for function in ('sin','cos','atan'):
                fn=getattr(mp,function)
                for lo,hi in intervals:
                    result=call('enclose_numeric',dict(function=function,a=[lo,hi]))
                    for i in range(9):
                        x=mp.mpf(lo)+(mp.mpf(hi)-mp.mpf(lo))*i/8;value=fn(x)
                        self.assertLessEqual(mp.mpf(result['lower']),value,(function,x))
                        self.assertGreaterEqual(mp.mpf(result['upper']),value,(function,x))
            for function in ('add','sub','mul','div'):
                for a,b in [('0.1','0.2'),('1e-320','2'),('-1e-300','3.7'),('2.00000000000000000001','-1.11111111111111111111')]:
                    r=call('enclose_numeric',dict(function=function,a=a,b=b))
                    x,y=Fraction(a),Fraction(b);exact={'add':lambda:x+y,'sub':lambda:x-y,'mul':lambda:x*y,'div':lambda:x/y}[function]()
                    self.assertLessEqual(Fraction(r['lower']),exact);self.assertGreaterEqual(Fraction(r['upper']),exact)
            for value in ('1e-320','.1','2','1e200'):
                r=call('enclose_numeric',dict(function='sqrt',a=value));exact=mp.sqrt(mp.mpf(value))
                self.assertLessEqual(mp.mpf(r['lower']),exact);self.assertGreaterEqual(mp.mpf(r['upper']),exact)
        with self.assertRaises(ValueError):call('enclose_numeric',dict(function='div',a=1,b=[-1,1]))
        with self.assertRaisesRegex(ValueError,'Reversed'):
            call('enclose_numeric',dict(function='sin',a=['2.00000000000000000002','2.00000000000000000001']))

    def test_exact_source_curves_and_trim_are_enclosed_without_probe_slack(self):
        witnesses=[]
        with mp.workdps(120):
            for parameters in [dict(z=12,mt=1),dict(z=24,mt=2),dict(z=73,mt=4,shift='.2')]:
                packet=call('spur_total_profile_error',parameters);ref=reference(parameters,packet)
                for row in packet['curves']:
                    descriptor=row['curve']
                    for interval in row['intervals']:
                        a,b=interval['start'],interval['end']
                        pa=ref['curve'](descriptor,a);pb=ref['curve'](descriptor,b)
                        for name,point in [('start_box',pa),('end_box',pb)]:
                            for v,box in zip(point,interval[name]):
                                self.assertLessEqual(mp.mpf(box[0]),v);self.assertGreaterEqual(mp.mpf(box[1]),v)
                        chord=[call('curve_point',dict(curve=descriptor,t=t)) for t in (a,b)]
                        chord=[tuple(mp.mpf(x) for x in q) for q in chord]
                        for f in (mp.mpf('.17'),mp.mpf('.53'),mp.mpf('.89')):
                            value=distance(ref['curve'](descriptor,mp.mpf(a)+(mp.mpf(b)-mp.mpf(a))*f),*chord)
                            self.assertLessEqual(value,mp.mpf(interval['chord_bound_mm']))
                            witnesses.append((value,mp.mpf(interval['chord_bound_mm'])))
                if packet['trim']['kind']=='isolated_exact_intersection':
                    lo,hi=map(mp.mpf,packet['trim']['end_rad'])
                    self.assertLess(ref['residual'](lo),0);self.assertGreater(ref['residual'](hi),0)
                    self.assertLess(lo,ref['end']);self.assertGreater(hi,ref['end'])
                    for t in (lo,(lo+hi)/2,hi):
                        derivative=mp.diff(ref['residual'],t)
                        self.assertLessEqual(mp.mpf(packet['trim']['derivative'][0]),derivative)
                        self.assertGreaterEqual(mp.mpf(packet['trim']['derivative'][1]),derivative)
                join=mp.sqrt(sum((x-y)**2 for x,y in zip(ref['corner'](ref['end']),ref['flank'](ref['roll0']))))
                self.assertLess(join,mp.mpf('1e-100'))
        self.assertTrue(any(actual>bound/2 for actual,bound in witnesses),'An artificially halved bound must fail at least one independent witness')

    def test_cancellation_expression_sources_are_not_rounded_before_enclosure(self):
        source={'expression':['sub',{'expression':['add','1e200','2.00000000000000000001']},'1e200']}
        r=call('spur_total_profile_error',dict(z=24,mt=source,sources=dict(module=source,width='10.00000000000000000001')))
        exact=Fraction('2.00000000000000000001');lo,hi=r['source_enclosures']['module']
        self.assertLessEqual(Fraction(lo),exact);self.assertGreaterEqual(Fraction(hi),exact)
        self.assertGreater(r['profile_bound_mm'],0.)

    def test_caps_side_faces_bore_and_formats_have_distinct_proved_totals(self):
        for values in ({},{'teeth':12},{'teeth':73,'module':4,'profile_shift':.2},{'bore':0}):
            with self.subTest(values=values):
                d=generate('spur',values,quality=dict(export_mm=.005));r=audit(d,require_total=True)
                self.assertEqual(r['status'],'bounded_complete_surface');self.assertGreater(r['total_error_bound_mm'],.005)
                self.assertEqual(r['total_error_representation'],'binary64_model_surface')
                self.assertTrue(r['topology']['closed_oriented_mesh'])
                self.assertTrue(all(c['exact_area_and_boundary_chain'] for c in r['topology']['caps']))
                self.assertGreater(r['output_bounds']['stl']['bound_mm'],r['total_error_bound_mm'])
                self.assertIsNone(r['output_bounds']['step']['bound_mm'])
        self.assertEqual(report(generate('helical'),'export')['geometric_error_budget']['status'],'bounded_complete_surface')

    def test_missing_cap_wrong_winding_and_filled_bore_cannot_get_a_total(self):
        d=generate('spur');p=d.parts[0];rows=list(triangles(p));local=section_loops(p,p.outer,0.)
        caps=[tuple(tuple(q[:2]) for q in t) for t in rows if all(q[2]==p.width for q in t)]
        self.assertTrue(_cap_cover(local,caps,1)['exact_area_and_boundary_chain'])
        with self.assertRaises(UnsupportedBudget):_cap_cover(local,caps[1:],1)
        reversed_cap=[(caps[0][0],caps[0][2],caps[0][1]),*caps[1:]]
        with self.assertRaises(UnsupportedBudget):_cap_cover(local,reversed_cap,1)
        hole=list(reversed(local[1]));filled=[(hole[0],hole[i],hole[i+1]) for i in range(1,len(hole)-1)]
        with self.assertRaises(UnsupportedBudget):_cap_cover(local,caps+filled,1)
        cap_index=next(i for i,t in enumerate(rows) if all(q[2]==p.width for q in t))
        damaged=rows[:cap_index]+rows[cap_index+1:]
        with patch('geometry_error_budget._actual_triangles',return_value=iter(damaged)):
            with self.assertRaises(UnsupportedBudget):audit(d,require_total=True)
        with patch('geometry_error_budget._actual_triangles',return_value=iter(damaged)):
            r=audit(d)
            self.assertIsNone(r['total_error_bound_mm']);self.assertEqual(r['total_error_status'],'not_evaluated')

    def test_actual_stl_coordinates_and_full_surface_witnesses(self):
        d=generate('spur');p=d.parts[0];r=audit(d,details=True,require_total=True)
        native=list(triangles(p))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'gear.stl';write_stl(path,[p]);data=path.read_bytes()
        stl=[]
        for start in range(84,len(data),50):
            coordinates=struct.unpack_from('<9f',data,start+12)
            stl.append(tuple(tuple(coordinates[3*j:3*j+3]) for j in range(3)))
        self.assertEqual(len(stl),len(native))
        for actual,source in zip(stl,native):
            expected=tuple(struct.unpack('<3f',struct.pack('<3f',*q)) for q in source)
            self.assertEqual(actual,expected)
        probes=[]
        with mp.workdps(120):
            packet=r['source_profile'];ref=reference({},packet)
            for row in packet['curves']:
                descriptor=row['curve'];a,b=map(mp.mpf,(descriptor['start'],descriptor['end']))
                for f in (mp.mpf('.23'),mp.mpf('.71')):
                    xy=ref['curve'](descriptor,a+(b-a)*f)
                    for z in (0.,5.,10.):probes.append((float(xy[0]),float(xy[1]),z))
            # Ideal filled end caps, well inside the polygon and next to the bore.
            for rad in (mp.mpf('3.01'),(ref['root']+3)/2):
                for angle in (mp.mpf('.17'),mp.mpf('2.21'),mp.mpf('4.36')):
                    for z in (0.,10.):probes.append((float(rad*mp.cos(angle)),float(rad*mp.sin(angle)),z))
            for angle in (mp.mpf('.4'),mp.mpf('2.3')):
                probes.append((float(3*mp.cos(angle)),float(3*mp.sin(angle)),4.1))
        largest=0.
        for point in probes:
            error=min(point_triangle_distance(point,t) for t in stl);largest=max(largest,error)
            self.assertLessEqual(error,r['output_bounds']['stl']['bound_mm'])
        self.assertGreater(largest,.001)

    def test_affine_placement_exact_width_and_binary32_collapse_are_explicit(self):
        d=generate('spur',{'width':10,'_decimal_inputs':{'width':'10.00000000000000000001'}})
        d=replace(d,parts=[replace(d.parts[0],frame=((7.,-3.,4.),(2.,0.,0.),(0.,1.5,0.),(0.,0.,.75)))])
        r=audit(d,require_total=True)
        self.assertGreater(r['components']['placement_and_source_dimensions_mm'],0.)
        self.assertGreater(r['components']['placement_error_scale'],2.)
        moved=generate('spur');moved=replace(moved,parts=[replace(moved.parts[0],center=(1e8+.125,-1e8+.25))])
        m=audit(moved)
        self.assertNotEqual(m['output_bounds']['stl']['status'],'bounded_complete_surface')
        self.assertIsNone(m['output_bounds']['stl']['bound_mm'])

    def test_actual_wasm_outward_operations_source_trim_and_bore(self):
        root=Path(__file__).resolve().parents[1];node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        self.assertTrue(node,'Actual Wasm coverage requires Node.js')
        requests=[dict(operation='enclose_numeric',parameters=dict(function=f,a=['-.12','.37'])) for f in ('sin','cos','atan')]
        requests += [dict(operation='spur_total_profile_error',parameters=dict(z=z,mt=m,bore=2)) for z,m in ((12,1),(24,2))]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'requests.json';path.write_text(json.dumps(requests))
            child=subprocess.run([node,str(root/'tests/rust_wasm_protocol.mjs'),str(root),str(path)],capture_output=True,text=True,check=True,timeout=90)
        results=json.loads(child.stdout)
        for request,response in zip(requests,results):
            self.assertTrue(response['ok'],response);native=call(request['operation'],request['parameters']);wasm=response['result']
            if request['operation']=='enclose_numeric':self.assertEqual(native,wasm)
            else:
                self.assertEqual(native['audit_cells'],wasm['audit_cells'])
                self.assertAlmostEqual(native['profile_bound_mm'],wasm['profile_bound_mm'],places=10)
                self.assertAlmostEqual(native['bore_bound_mm'],wasm['bore_bound_mm'],places=12)
                self.assertEqual(native['trim']['kind'],wasm['trim']['kind'])

    def test_unresolved_or_modified_constructions_and_impossible_resolution_refuse_total(self):
        with self.assertRaisesRegex(ValueError,'budget|resolution|depth'):
            call('spur_total_profile_error',dict(z=24,mt=2,budget_refinement_mm=1e-300))
        d=generate('spur');d.parts[0].outer[0]=(999.,999.)
        self.assertEqual(available_report(d,'export')['status'],'not_evaluated')
        with self.assertRaises(UnsupportedBudget):audit(d,require_total=True)
        for extra in (dict(helix=46),dict(internal=True),dict(rack_tip_radius_mm=.5),dict(safe_pair_sampling=True)):
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                call('spur_total_profile_error',dict(z=24,mt=2,**extra))


if __name__=='__main__':unittest.main()
