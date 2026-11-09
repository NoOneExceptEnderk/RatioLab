# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent exact-source helical/groove witnesses and real-mesh negatives."""
from dataclasses import replace
from fractions import Fraction
import json,math,os,shutil,struct,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import mpmath as mp
from geometry import generate
from geometry_error_budget import audit,available_report,UnsupportedBudget
from geometry_quality import with_quality
from solid_geometry import kernel_part,rings,sampling_report
from rust_geometry import call,control_scope
from stl_export import triangles,write_stl
from test_total_error_budget import reference,rotate,distance,point_triangle_distance


def parameters(d):
    v=d.values;p=d.parts[0]
    return dict(z=v['teeth'],mt=v['module'],pressure=v['pressure'],backlash=v['backlash'],
        shift=v['profile_shift'],ha=v['addendum'],hf=v['dedendum'],bore=v['bore'],helix=v['helix'],
        gap=v.get('gap',0) if p.double else 0,part=kernel_part(p),
        sources=dict(width=v['width'],center=p.center,z=p.z,frame=p.frame))


def nominal(values,family):
    """Independent physical lead and groove recipe, evaluated at 120 digits."""
    defaults=dict(module=2,teeth=24,pressure=20,profile_shift=0,addendum=1,dedendum=1.25,
        width=10,helix=25 if family=='double' else 20,gap=1)
    v={k:mp.mpf(str(x)) for k,x in (defaults|values).items()}
    w=v['width'];beta=v['helix']*mp.pi/180;rp=v['module']*v['teeth']/(2*mp.cos(beta))
    root=rp-v['module']*(v['dedendum']-v['profile_shift']);rate=mp.tan(beta)/rp
    if family!='double':return dict(width=w,root=root,rate=rate,landmarks=[(mp.mpf(0),mp.mpf(0),False),(w,rate*w,False)])
    g=v['gap'];h=(w-g)/2;s=min(mp.mpf('.15'),h*mp.mpf('.08'),g*mp.mpf('.2')) if g else mp.mpf(0)
    rows=[(mp.mpf(0),mp.mpf(0),False),(h-s,rate*(h-s),False)]
    if g:rows.extend([(h,rate*h,True),(h+g,rate*h,True),(h+g+s,rate*(h-s),False)])
    rows.append((w,mp.mpf(0),False))
    return dict(width=w,root=root,rate=rate,landmarks=rows)


def core(q,root):
    r=mp.sqrt(sum(x*x for x in q));return tuple((mp.mpf('.96')*root+mp.mpf('.001')*(r-root))*x/r for x in q)


def sweep_point(q,t,model,interval):
    a,b=model['landmarks'][interval:interval+2]
    x=core(q,model['root']) if a[2] else q;y=core(q,model['root']) if b[2] else q
    xy=tuple((1-t)*x[k]+t*y[k] for k in range(2))
    angle=(1-t)*a[1]+t*b[1];z=(1-t)*a[0]+t*b[0]
    return (*rotate(xy,angle),z)


class HelicalTotalErrorBudgetTests(unittest.TestCase):
    def test_normal_rack_exact_curves_trim_and_reversed_handedness(self):
        with mp.workdps(120):
            for z,beta in ((12,20),(24,-35),(24,45),(73,5)):
                args=dict(z=z,mt='2',helix=str(beta),bore=2)
                result=call('spur_total_profile_error',args);ref=reference(args,result)
                for row in result['curves']:
                    for leaf in row['intervals']:
                        for name,t in (('start_box',leaf['start']),('end_box',leaf['end'])):
                            q=ref['curve'](row['curve'],t)
                            for value,box in zip(q,leaf[name]):
                                self.assertLessEqual(mp.mpf(box[0]),value)
                                self.assertGreaterEqual(mp.mpf(box[1]),value)
                        a,b=map(mp.mpf,(leaf['start'],leaf['end']))
                        q=ref['curve'](row['curve'],a+(b-a)*mp.mpf('.37'))
                        chord=[call('curve_point',dict(curve=row['curve'],t=t)) for t in (leaf['start'],leaf['end'])]
                        chord=[tuple(mp.mpf(x) for x in p) for p in chord]
                        self.assertLessEqual(distance(q,*chord),mp.mpf(leaf['chord_bound_mm']))
                if result['trim']['kind']=='isolated_exact_intersection':
                    lo,hi=map(mp.mpf,result['trim']['end_rad'])
                    self.assertLessEqual(lo,ref['end']);self.assertGreaterEqual(hi,ref['end'])
                    self.assertGreater(mp.diff(ref['residual'],(lo+hi)/2),0)
                join=mp.sqrt(sum((x-y)**2 for x,y in zip(ref['corner'](ref['end']),ref['flank'](ref['roll0']))))
                self.assertLess(join,mp.mpf('1e-100'))
                other=call('spur_total_profile_error',dict(args,helix=str(-beta)))
                self.assertEqual(result['profile_bound_mm'],other['profile_bound_mm'])

    def test_complete_caps_bore_joined_and_grooved_all_presets(self):
        for family,values in [('helical',{}),('helical',dict(helix=-35,bore=0)),
                              ('double',dict(variant='joined')),('double',dict(variant='separated')),
                              ('double',dict(variant='separated',width=24,gap=4,helix=-35))]:
            d=generate(family,values)
            previous=None
            for tolerance in (.1,.02,.005):
                with self.subTest(family=family,values=values,tolerance=tolerance):
                    r=audit(with_quality(d,dict(export_mm=tolerance)),require_total=True)
                    self.assertEqual(r['status'],'bounded_complete_surface')
                    self.assertTrue(r['topology']['closed_oriented_mesh'])
                    self.assertTrue(all(c['exact_area_and_boundary_chain'] for c in r['topology']['caps']))
                    self.assertGreater(r['topology']['section_count'],2)
                    self.assertGreater(r['total_error_bound_mm'],r['components']['transverse_profile_mm'])
                    self.assertGreater(r['output_bounds']['stl']['bound_mm'],r['total_error_bound_mm'])
                    self.assertIsNone(r['output_bounds']['step']['bound_mm'])
                    self.assertGreater(r['components']['sweep_interpolation_mm'],0)
                    self.assertLessEqual(r['components']['sweep_interpolation_mm'],tolerance+1e-10)
                    if previous is not None:self.assertLessEqual(r['total_error_bound_mm'],previous+1e-10)
                    previous=r['total_error_bound_mm']

    def test_exact_lead_width_groove_landmarks_and_node_residuals(self):
        with mp.workdps(120):
            for family,values in [('helical',dict(helix=-35)),('double',dict(variant='joined',gap=0)),
                                  ('double',dict(variant='separated',gap=1,helix=-25))]:
                d=generate(family,values);p=d.parts[0];r=audit(d,details=True,require_total=True)
                model=nominal({k:v for k,v in values.items() if k!='variant'},family)
                rows=r['source_sweep']['intervals'];self.assertEqual(len(rows)+1,len(model['landmarks']))
                for row,(a,b) in zip(rows,zip(model['landmarks'],model['landmarks'][1:])):
                    for name,value in [('start_z',a[0]),('end_z',b[0]),('start_angle_rad',a[1]),('end_angle_rad',b[1])]:
                        lo,hi=map(mp.mpf,row[name]);self.assertLessEqual(lo,value);self.assertGreaterEqual(hi,value)
                actual=rings(p);index=0
                for interval,row in enumerate(rows):
                    n=row['intervals']
                    for j in (0,n//2,n):
                        t=mp.mpf(j)/n
                        for i in (0,len(p.outer)//3,len(p.outer)-1):
                            q=tuple(mp.mpf(x) for x in p.outer[i]);want=sweep_point(q,t,model,interval)
                            got=actual[index+j][0][i]
                            error=mp.sqrt(sum((want[k]-mp.mpf(got[k]))**2 for k in range(3)))
                            self.assertLessEqual(error,mp.mpf(r['components']['placement_and_source_dimensions_mm']))
                    index+=n

    def test_high_precision_full_boundary_witnesses_and_real_stl(self):
        with mp.workdps(120):
            for family,values in [('helical',{}),('double',dict(variant='joined',gap=0)),('double',dict(variant='separated',gap=1))]:
                d=generate(family,values);p=d.parts[0];r=audit(d,details=True,require_total=True)
                source_args=parameters(d);ref=reference(source_args,r['source_profile'])
                model=nominal({k:v for k,v in values.items() if k!='variant'},family)
                mesh=list(triangles(p));bound=r['total_error_bound_mm']
                probes=[]
                for row in r['source_profile']['curves']:
                    desc=row['curve'];lo,hi=mp.mpf(desc['start']),mp.mpf(desc['end'])
                    q=ref['curve'](desc,lo+(hi-lo)*mp.mpf('.413'))
                    for interval in range(len(model['landmarks'])-1):
                        probes.append(sweep_point(q,mp.mpf('.371'),model,interval))
                boxes=[tuple((min(p[k] for p in row),max(p[k] for p in row)) for k in range(3)) for row in mesh]
                maxima=[]
                for q in probes:
                    q=tuple(float(x) for x in q)
                    candidates=[row for row,box in zip(mesh,boxes) if all(a-bound<=q[k]<=b+bound for k,(a,b) in enumerate(box))]
                    self.assertTrue(candidates)
                    error=min(point_triangle_distance(q,t) for t in candidates)
                    self.assertLessEqual(error,bound);maxima.append(error)
                self.assertGreater(max(maxima),1e-6,'A zeroed total must fail these surface witnesses')
                with tempfile.TemporaryDirectory() as folder:
                    path=Path(folder)/'gear.stl';write_stl(path,[p]);data=path.read_bytes()
                self.assertEqual(struct.unpack_from('<I',data,80)[0],len(mesh))
                for i in (0,len(mesh)//2,len(mesh)-1):
                    coordinates=struct.unpack_from('<9f',data,84+50*i+12)
                    expected=struct.unpack('<9f',struct.pack('<9f',*(v for q in mesh[i] for v in q)))
                    self.assertEqual(coordinates,expected)

    def test_actual_missing_cap_side_and_modified_source_are_refused(self):
        for family in ('helical','double'):
            d=generate(family);p=d.parts[0];mesh=list(triangles(p));levels=rings(p)
            bottom=set(q for loop in levels[0] for q in loop)
            cap=next(i for i,row in enumerate(mesh) if all(q in bottom for q in row))
            side=next(i for i,row in enumerate(mesh) if not all(q in bottom for q in row))
            for index in (cap,side):
                damaged=mesh[:index]+mesh[index+1:]
                with patch('geometry_error_budget._actual_triangles',return_value=iter(damaged)):
                    with self.assertRaises(UnsupportedBudget):audit(d,require_total=True)
                with patch('geometry_error_budget._actual_triangles',return_value=iter(damaged)):
                    result=audit(d);self.assertIsNone(result['total_error_bound_mm'])
                    self.assertEqual(result['total_error_status'],'not_evaluated')
            altered=replace(d,parts=[replace(p,twist=p.twist+.1)])
            with self.assertRaises(UnsupportedBudget):audit(altered,require_total=True)
            bore=generate(family);bore.parts[0].holes[0].radius+=.1
            with self.assertRaises(UnsupportedBudget):audit(bore,require_total=True)
            args=parameters(d);args['part']['outer'][0]=(999.,999.)
            with self.assertRaisesRegex(ValueError,'source contour'):call('cylindrical_total_surface_error',args)

    def test_declared_affine_exact_decimal_dimensions_and_float32_collapse(self):
        d=generate('double',dict(variant='separated',_decimal_inputs={'width':'10.00000000000000000001','gap':'1.00000000000000000001'}))
        p=d.parts[0]
        moved=replace(d,parts=[replace(p,center=(.125,-.25),z=.3,
            frame=((1.,2.,3.),(1.5,.1,0.),(.2,1.,.05),(0.,.1,1.)))])
        r=audit(moved,require_total=True);self.assertGreater(r['components']['placement_error_scale'],1.)
        self.assertGreater(r['components']['placement_and_source_dimensions_mm'],0.)
        large=replace(d,parts=[replace(p,center=(1e8+.125,-1e8+.25))])
        result=audit(large,require_total=True)
        self.assertIsNone(result['output_bounds']['stl']['bound_mm'])
        self.assertIsNone(result['output_bounds']['preview']['bound_mm'])
        x=generate('helical');x.parts[0].frame=((0.,0.,0.),(0.,0.,0.),(0.,1.,0.),(0.,0.,1.))
        with self.assertRaises(UnsupportedBudget):audit(x,require_total=True)
        self.assertIsNone(available_report(generate('internal'),'export')['total_error_bound_mm'])

    def test_groove_chord_bound_contains_independent_nonlinear_map(self):
        d=generate('double',dict(variant='separated'));p=d.parts[0]
        r=audit(d,details=True,require_total=True)
        with mp.workdps(120):
            root=nominal({},'double')['root'];maximum=mp.mpf(0)
            edges=sorted(range(len(p.outer)),key=lambda i:math.dist(p.outer[i],p.outer[(i+1)%len(p.outer)]),reverse=True)[:24]
            for i in edges:
                a=tuple(mp.mpf(x) for x in p.outer[i]);b=tuple(mp.mpf(x) for x in p.outer[(i+1)%len(p.outer)])
                ga=core(a,root);gb=core(b,root)
                for t in map(mp.mpf,('.13','.5','.87')):
                    q=tuple((1-t)*a[k]+t*b[k] for k in range(2));actual=core(q,root)
                    chord=tuple((1-t)*ga[k]+t*gb[k] for k in range(2))
                    error=mp.sqrt(sum((actual[k]-chord[k])**2 for k in range(2)))
                    self.assertLessEqual(error,mp.mpf(r['components']['groove_chord_mm']))
                    maximum=max(maximum,error)
            self.assertGreater(maximum,mp.mpf('.0001'))

    def test_native_cancellation_propagates_original_exception(self):
        d=generate('double');args=parameters(d);checks=0
        def count():
            nonlocal checks
            checks+=1
        with control_scope(count):call('cylindrical_total_surface_error',args)
        total=checks;self.assertGreater(total,14)
        class Cancelled(Exception):pass
        for cut in (12,total-2):
            checks=0;original=Cancelled('cancel curved error audit')
            def check():
                nonlocal checks
                checks+=1
                if checks>=cut:raise original
            with control_scope(check):
                with self.assertRaises(Cancelled) as caught:call('cylindrical_total_surface_error',args)
            self.assertIs(caught.exception,original)
            self.assertEqual(call('surface_stats',{})['cursors'],0)

    def test_actual_wasm_encloses_same_helical_and_groove_sources(self):
        root=Path(__file__).resolve().parents[1];node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        self.assertTrue(node,'Actual Wasm requires Node.js')
        requests=[]
        for family,values in [('helical',dict(helix=-35)),('double',dict(variant='joined')),('double',dict(variant='separated'))]:
            d=generate(family,values)
            requests.append(dict(operation='cylindrical_total_surface_error',parameters=parameters(d)))
        from precise_numbers import transport
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.json';path.write_text(json.dumps(transport(requests)))
            child=subprocess.run([node,str(root/'tests/rust_wasm_protocol.mjs'),str(root),str(path)],capture_output=True,text=True,check=True,timeout=120)
        for request,response in zip(requests,json.loads(child.stdout)):
            self.assertTrue(response['ok'],response)
            native=call(request['operation'],request['parameters']);wasm=response['result']
            self.assertEqual(native['section_count'],wasm['section_count'])
            self.assertEqual(native['source_profile']['trim']['kind'],wasm['source_profile']['trim']['kind'])
            self.assertGreater(wasm['resampled_bore_bound_mm'],0)
            self.assertLess(wasm['resampled_bore_bound_mm'],.02)
            for key in ('transverse_and_groove_bound_mm','sweep_interpolation_mm','placement_and_source_dimensions_mm'):
                self.assertAlmostEqual(native[key],wasm[key],delta=1e-10)


if __name__=='__main__':unittest.main()
