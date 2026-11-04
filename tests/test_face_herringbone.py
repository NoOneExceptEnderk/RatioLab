# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent swept-envelope oracle, real central material, closed moving solids."""
from functools import lru_cache
from math import pi,sin,cos,tan,atan,atan2,acos,sqrt,hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from geometry import generate,validate,get_specs
from face_geometry import Generator
from solid_geometry import signature
from stl_export import triangles
from collision_geometry import Surface,relation,cross,dot
from motion import build_plan,transform,rotation,update_operating_rates


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def unit(p):return tuple(x/sqrt(dot(p,p)) for x in p)
def rx(p,a):return p[0],p[1]*cos(a)-p[2]*sin(a),p[1]*sin(a)+p[2]*cos(a)
def rz(p,a):return p[0]*cos(a)-p[1]*sin(a),p[0]*sin(a)+p[1]*cos(a),p[2]

@lru_cache(None)
def design(beta=15,offset=0):return generate('face',dict(variant='double_helical',double_style='joined',helix=beta,offset=offset))


class FaceHerringboneTests(unittest.TestCase):
    def test_default_selector_legacy_groove_projects_and_zero_helix(self):
        joined=design();self.assertEqual(joined.values['gap'],0)
        self.assertEqual(joined.values['double_style'],'joined')
        self.assertEqual(joined.analysis['face_gear']['tooth_band_count'],1)
        self.assertNotIn('gap',{s[0] for s in get_specs('face','double_helical','joined')})
        self.assertIn('gap',{s[0] for s in get_specs('face','double_helical','separated')})
        old=generate('face',dict(variant='double_helical',gap=4))
        explicit=generate('face',dict(variant='double_helical',double_style='separated',gap=4))
        self.assertEqual(old.parts,explicit.parts)
        self.assertEqual(old.values['double_style'],'separated')
        zero=design(0);spur=generate('face')
        self.assertEqual(zero.parts[1].mesh,spur.parts[1].mesh)
        self.assertAlmostEqual(signature(zero.parts[0])['volume_mm3'],signature(spur.parts[0])['volume_mm3'],places=7)
        for bad in ('unknown',None):
            with self.assertRaises(ValueError):validate('face',dict(variant='double_helical',double_style=bad))

    def test_independent_full_generating_sweep_upper_and_lower_envelope(self):
        for beta,offset in ((15,0),(-15,0),(15,5),(15,-5)):
            g=Generator(design(beta,offset).values);s=g.joined_surface
            for hf in (.1,.5,.85):
                h=g.low+(g.high-g.low)*hf
                for R in (s.inner+.5,(s.inner+s.outer)/2,s.outer-.5,*s.anchors(h)[1:-1]):
                    limit=acos(g.x0/R);values={-1:[],1:[]}
                    # Independent raw moving involute: no F/contact/at in oracle.
                    for i in range(3001):
                        psi=-limit+2*limit*i/3000;X=R*cos(psi)
                        if not g.x0<=X<=g.x1:continue
                        y=R*sin(psi)-offset;r=hypot(y,h)
                        t=sqrt((r/g.rb)**2-1)
                        half=pi/(2*g.v['pinion'])+g.v['backlash']/(4*g.rp)+tan(g.alpha)-g.alpha-t+atan(t)
                        if half<=0:continue
                        twist=g.k*min(X-g.x0,g.x1-X)
                        for side in (-1,1):
                            phi=atan2(-h,y)+pi/2-side*half-twist
                            values[side].append(psi-g.g*phi)
                    for side in (-1,1):
                        expected=(max if side==1 else min)(values[side])
                        actual=s.at(R,h,side)[0]
                        self.assertAlmostEqual(actual,expected,delta=3e-6,msg=(beta,offset,R,h,side))

    def test_cusp_sweep_normal_cone_and_concave_intersection(self):
        g=Generator(design().values);s=g.joined_surface;h=g.low+.15*(g.high-g.low)
        ends=[g.contact(s.mid,h,1,k)[0] for k in (g.k,-g.k)];R=sum(ends)/2
        angle,kind,x,y=s.at(R,h,1);self.assertEqual(kind,2)
        r=hypot(y,h);phase=g.coordinates(x,h,1,y)[4]
        def master(radius,X,k):
            t=sqrt((radius/g.rb)**2-1)
            half=pi/(2*g.v['pinion'])+g.v['backlash']/(4*g.rp)+tan(g.alpha)-g.alpha-t+atan(t)
            a=-pi/2+half+g.k*(s.mid-g.x0)+k*(X-s.mid)
            return X,radius*cos(a),radius*sin(a)
        def edge(radius,roll):
            p=rx(master(radius,x,0),roll);return rz((p[0],p[1]+g.e,p[2]+g.height),-g.g*roll)
        dr=sub(edge(r+1e-5,phase),edge(r-1e-5,phase))
        dp=sub(edge(r,phase+1e-5),edge(r,phase-1e-5));normal=rz(unit(cross(dr,dp)),g.g*phase)
        p=rx(master(r,x,0),phase);world=(p[0],p[1]+g.e,p[2]+g.height)
        velocity=sub(cross((1,0,0),p),cross((0,0,g.g),world))
        self.assertLess(abs(dot(normal,velocity)),1e-7)
        normals=[]
        for k in (g.k,-g.k):
            n=unit(cross(sub(master(r+1e-5,x,k),master(r-1e-5,x,k)),sub(master(r,x+1e-5,k),master(r,x-1e-5,k))))
            normals.append(rx(n,phase))
        a,b=[dot(n,velocity) for n in normals];weight=b/(b-a)
        self.assertGreater(weight,0);self.assertLess(weight,1)
        mixed=unit(tuple(weight*a+(1-weight)*b for a,b in zip(*normals)))
        self.assertAlmostEqual(abs(dot(normal,mixed)),1,delta=1e-8)
        # The third sorted anchor is the concave crease at zero offset.
        seam=s.anchors(h)[2];left=s.inverse(seam,h,-1,g.bands[0]);right=s.inverse(seam,h,-1,g.bands[1])
        self.assertAlmostEqual(left[0][1],right[0][1],delta=1e-9)
        self.assertLess(left[1],s.mid);self.assertGreater(right[1],s.mid)

    def test_joined_has_real_central_tooth_material_and_valid_solids(self):
        d=design();g=Generator(d.values);s=g.joined_surface
        wheel=Surface(list(triangles(d.parts[1])))
        old=generate('face',dict(variant='double_helical',double_style='separated',gap=4))
        grooved=Surface(list(triangles(old.parts[1])))
        R=s.mid;side=[s.at(R,g.low,sign)[0] for sign in (1,-1)]
        angle=(side[0]+side[1]+2*pi/72)/2
        point=(R*cos(angle),R*sin(angle),g.height-g.low-.15)
        self.assertTrue(wheel.contains(point,1e-6))
        self.assertFalse(grooved.contains(point,1e-6))
        for p in d.parts:self.assertGreater(signature(p)['volume_mm3'],0)
        self.assertTrue(all(len(f)==1 and len(f[0])==3 for f in d.parts[1].mesh))
        self.assertGreater(d.analysis['face_gear']['engagement']['phase_span_lower_bound_teeth'],1)

    def test_actual_joined_shared_solids_multiple_poses_and_wrong_phase_controls(self):
        for beta,offset in ((15,0),(-15,0),(15,5),(15,-5)):
            d=design(beta,offset);plan=build_plan(d);meshes=[list(triangles(p)) for p in d.parts]
            for fraction in (0,.31,.73):
                phase=2*pi/24*fraction
                ss=[Surface([tuple(transform(plan.matrix(i,phase),p) for p in t) for t in mesh]) for i,mesh in enumerate(meshes)]
                self.assertEqual(relation(*ss,1e-6)['kind'],'Separated',(beta,offset,fraction))
            wrong=Surface([tuple(transform(rotation(pi/72),p) for p in t) for t in meshes[1]])
            self.assertEqual(relation(Surface(meshes[0]),wrong,1e-6)['kind'],'Intersection')

    def test_independent_fraction_refinement_probes_and_chart_units(self):
        d=design();q=d.analysis['face_gear'];g=Generator(d.values);s=g.joined_surface
        hs=q['height_grid_mm'];ts=q['joined_transition']['parameter_grid']
        self.assertIsNone(q['axial_grids_mm'])
        self.assertEqual(len(q['joined_transition']['radial_grids_by_height_mm']),len(hs))
        for t in (ts[0],ts[len(ts)//2],ts[-1]):
            for a,b in zip(hs,hs[1:]):
                for side in (-1,1):
                    p=s.point(t,a,side);v=s.point(t,b,side)
                    for f in (.19,.61,.91):
                        actual=s.point(t,a+(b-a)*f,side)
                        error=sub(actual,tuple(x+(y-x)*f for x,y in zip(p,v)))
                        self.assertLess(sqrt(dot(error,error)),.0031)
        for h in (hs[0],hs[len(hs)//2],hs[-1]):
            for a,b in zip(ts,ts[1:]):
                for side in (-1,1):
                    p=s.point(a,h,side);v=s.point(b,h,side)
                    for f in (.19,.61,.91):
                        actual=s.point(a+(b-a)*f,h,side)
                        error=sub(actual,tuple(x+(y-x)*f for x,y in zip(p,v)))
                        self.assertLess(sqrt(dot(error,error)),.0031)

    def test_precise_project_reverse_zero_rpm_worker_and_canonical_exports(self):
        import sys;sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge,cad_export,stl_export
        d=generate('face',dict(variant='double_helical',helix=15.1234567890123,offset=1.1234567890123,io_scheme='reverse'))
        self.assertEqual(d.parts,generate('face',json.loads(json.dumps(d.values))).parts)
        plan=build_plan(d)
        for rpm in (-31.1234567890123,0,125):
            other=update_operating_rates(d,dict(d.values,input_rpm=rpm));updated=build_plan(other,plan,.7)
            for i in (0,1):
                self.assertIs(other.parts[i].mesh,d.parts[i].mesh)
                for a,b in zip(plan.matrix(i,.7),updated.matrix(i,.7)):self.assertAlmostEqual(a,b,places=12)
        worker=engine_bridge.Engine().call('generate',dict(family='face',parameters=d.values))
        self.assertEqual(worker['analysis'],d.analysis)
        for style in ('joined','separated'):
            schema=engine_bridge.schema('face',dict(variant='double_helical',double_style=style))
            self.assertEqual('gap' in {f['key'] for f in schema['fields']},style=='separated')
        with TemporaryDirectory() as td:
            _,parts=cad_export.export(d,Path(td)/'step');self.assertEqual(len(parts),2)
            stl_export.export(d,Path(td)/'stl');self.assertEqual(len(list(Path(td).rglob('*.stl'))),3)


if __name__=='__main__':unittest.main()
