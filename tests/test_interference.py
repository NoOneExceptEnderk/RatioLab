# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Behavior tests on closed surfaces, holes, 3D frames and discrete motion."""
from math import pi,cos,sin
from threading import Event
import unittest
from geometry import Part,Design,generate,circle
from interference import analyze,Settings,period
from motion import MotionPlan,rigid,translation,build_plan
from collision_geometry import Surface,relation
from stl_export import triangles,triangulate


def box(name,x=0,y=0,z=0,size=2):
    return Part(name,[(0,0),(size,0),(size,size),(0,size)],width=size,center=(x,y),z=z)


def design(parts):
    d=Design('spur',{'input_rpm':0});d.parts=parts;return d


def check(parts,**kw):
    return analyze(design(parts),plan=MotionPlan(),**kw)


class InterferenceTests(unittest.TestCase):
    def test_surface_distances_and_contact(self):
        for p,expected,kind in ((box('B',x=4),2,'Separated'),(box('B',x=4,y=5,z=6),29**.5,'Separated'),(box('B',x=2),0,'Boundary contact / unresolved'),(box('B',x=2,y=2,z=2),0,'Boundary contact / unresolved')):
            with self.subTest(expected=expected,kind=kind):
                r=check([box('A'),p]);self.assertTrue(r.coverage_complete);self.assertAlmostEqual(r.rows[0]['distance'],expected);self.assertEqual(r.rows[0]['kind'],kind)

    def test_intersection_is_not_box_overlap_depth(self):
        r=check([box('A'),box('B',x=1,y=.3,z=.2)])
        self.assertEqual(r.rows[0]['kind'],'Intersection');self.assertEqual(r.rows[0]['distance'],0)
        self.assertIn('NOT minimum translation',r.text())

    def test_positive_surface_distance_containment(self):
        r=check([box('Outer',size=6),box('Inner',1,1,1,size=2)])
        self.assertEqual(r.rows[0]['kind'],'Containment');self.assertAlmostEqual(r.rows[0]['distance'],1.)

    def test_real_hole_and_crossing_wall(self):
        tube=Part('tube',[(0,0),(10,0),(10,10),(0,10)],holes=[[(2,2),(8,2),(8,8),(2,8)]],width=4)
        r=check([tube,box('In hole',3,3,1)])
        self.assertEqual(r.rows[0]['kind'],'Separated');self.assertAlmostEqual(r.rows[0]['distance'],1)
        r=check([tube,box('Wall crossing',1,3,1)])
        self.assertNotEqual(r.rows[0]['kind'],'Separated')

    def test_concavity_rejects_aabb_overlap(self):
        l=Part('L',[(0,0),(6,0),(6,2),(2,2),(2,6),(0,6)],width=2)
        r=check([l,box('In notch',3,3)])
        self.assertEqual(r.rows[0]['kind'],'Separated');self.assertAlmostEqual(r.rows[0]['distance'],1)

    def test_frame_rotated_out_of_xy(self):
        a=box('A');b=box('B',z=4)
        frame=((10,2,3),(1,0,0),(0,0,1),(0,-1,0))
        a.frame=b.frame=frame
        r=check([a,b]);self.assertAlmostEqual(r.rows[0]['distance'],2)

    def test_axis_x_and_nonrigid_frame(self):
        a=box('A');a.axis_x=True
        b=box('B');b.axis_x=True;b.center=(0,5)
        r=check([a,b]);self.assertAlmostEqual(r.rows[0]['distance'],8)
        a=box('A');b=box('B',x=4);frame=((0,0,0),(2,0,0),(0,1,0),(0,0,1));a.frame=b.frame=frame
        self.assertAlmostEqual(check([a,b]).rows[0]['distance'],4)

    def test_intermediate_pose_collision_and_period(self):
        a=box('moving',3,0,size=1);b=box('fixed',-1,3,size=1)
        d=design([a,b]);p=MotionPlan(poses={0:rigid(1)},rates={0:(1,)})
        r=analyze(d,Settings(step_degrees=90),plan=p)
        self.assertTrue(r.coverage_complete);self.assertEqual(r.period_turns,1)
        hits=[x for x in r.rows if x['kind']!='Separated'];self.assertTrue(hits);self.assertEqual(hits[0]['phase_degrees'],90)
        coarse=analyze(d,Settings(step_degrees=180),plan=p)
        self.assertTrue(all(x['kind']=='Separated' for x in coarse.rows))

    def test_pose_zero_matrix_is_applied(self):
        p=MotionPlan(poses={0:lambda phase:translation(x=10)},rates={0:(0,)})
        r=analyze(design([box('A'),box('B',x=4)]),plan=p)
        self.assertAlmostEqual(r.rows[0]['distance'],4)

    def test_period_longer_than_input_turn_and_limit(self):
        p=MotionPlan(poses={0:rigid(1),1:rigid(-2/7)},rates={0:(1,),1:(-2/7,)})
        self.assertEqual(period(p),7)
        r=analyze(design([box('A',x=3),box('B',x=10)]),Settings(step_degrees=180,max_poses=3),plan=p)
        self.assertFalse(r.coverage_complete);self.assertEqual(r.requested_end_degrees,2520);self.assertEqual(r.sampled_end_degrees,360)
        self.assertIn('Pose limit',' '.join(r.issues))
        for f in ('planetary','cycloidal','worm','parallel'):
            d=generate(f);self.assertGreaterEqual(period(build_plan(d)),1)

    def test_unknown_motion_and_deformation_are_explicit(self):
        d=design([box('A'),box('B',x=4)])
        for p in (MotionPlan(poses={0:rigid(1)}),MotionPlan(flex={0:lambda phase:None},rates={0:(1,)}),MotionPlan(warps={0:lambda phase:None},rates={0:(1,)})):
            with self.subTest(plan=p):
                r=analyze(d,Settings(max_poses=1),plan=p);self.assertFalse(r.coverage_complete);self.assertTrue(r.issues)

    def test_cancel_time_and_geometry_limits(self):
        event=Event();event.set();r=check([box('A')],cancel=event)
        self.assertTrue(r.cancelled);self.assertFalse(r.coverage_complete)
        r=check([box('A')],settings=Settings(max_seconds=1e-12));self.assertFalse(r.coverage_complete)
        r=check([box('A'),box('B')],settings=Settings(max_triangles=1));self.assertFalse(r.coverage_complete);self.assertEqual(len(r.parts),2)
        r=check([box('A'),box('B')],settings=Settings(max_parts=1));self.assertFalse(r.coverage_complete)

    def test_cancel_during_triangulation(self):
        calls=[]
        class Cancelled(Exception):pass
        def callback():
            calls.append(True)
            if len(calls)>5:raise Cancelled()
        face=[[(cos(i*pi/60)*(2 if i%2 else 3),sin(i*pi/60)*(2 if i%2 else 3),0) for i in range(120)]]
        with self.assertRaises(Cancelled):triangulate(face,callback)

    def test_expected_interface_does_not_hide_intersection(self):
        d=design([box('A'),box('B',x=1)]);d.parts[0].port=d.parts[1].port={'member':'input'}
        r=analyze(d);self.assertEqual(r.rows[0]['kind'],'Intersection');self.assertIn('candidate',r.rows[0]['expected'])

    def test_open_surface_and_singular_pose_are_unsupported(self):
        p=box('A');p.mesh=[[[[0,0,0],[1,0,0],[0,1,0]]]]
        r=check([p,box('B')]);self.assertFalse(r.coverage_complete);self.assertIn('not closed',' '.join(r.issues))
        matrix=(0.,)*16;p=MotionPlan(poses={0:lambda phase:matrix},rates={0:(0,)})
        # Invalid transformed surfaces produce an explicit incomplete report.
        r=analyze(design([box('A')]),plan=p)
        self.assertFalse(r.coverage_complete);self.assertIn('unsupported',' '.join(r.issues))

    def test_nearly_collinear_shared_cycloidal_cap_keeps_topology(self):
        from collision_geometry import point_triangle,norm2,sub
        d=generate('cycloidal');part=next(p for p in d.parts if p.name=='Seat_support_output')
        surface=Surface(list(triangles(part)))
        self.assertGreater(surface.thin_triangles,0)
        self.assertLess(surface.edge_approximation_mm,1e-9)
        for tri in surface.triangles:
            q=point_triangle(tri[0],tri);self.assertLess(norm2(sub(q,tri[0])),1e-20)
        # Exact collinearity is also handled by segment/point distance.
        self.assertEqual(point_triangle((1,1,0),((0,0,0),(1,0,0),(2,0,0))),(1.,0.,0.))

    def test_thin_triangle_altitude_has_mm_units_and_scales(self):
        from collision_geometry import mul
        triangle=((0.,0.,0.),(2.,0.,0.),(1.,1e-13,0.))
        for scale in (1.,1e3,1e12):
            surface=Surface([tuple(mul(q,scale) for q in triangle)],validate=False)
            self.assertAlmostEqual(surface.edge_approximation_mm/(1e-13*scale),1.,places=12)
        d=design([Part('Very large thin cap',[(0,0),(2e12,0),(1e12,.1),(0,.1)],width=2e12)])
        r=analyze(d,Settings(tolerance_mm=.01))
        self.assertFalse(r.coverage_complete);self.assertIn('approximation',' '.join(r.issues))

    def test_exactly_collinear_contact_candidate_has_no_normal(self):
        mesh=list(triangles(box('A')));a,b,c=mesh[0]
        midpoint=tuple((x+y)/2 for x,y in zip(a,b))
        # Subdivide a real face and retain its collinear bridge triangle. The
        # original boundary topology is closed and consistently oriented.
        surface=Surface([(a,midpoint,c),(midpoint,b,c),(a,b,midpoint),*mesh[1:]])
        other=Surface(list(triangles(box('B',y=-2,z=-2))))
        self.assertGreater(surface.thin_triangles,0)
        result=relation(surface,other,.01)
        self.assertEqual(result['kind'],'Boundary contact / unresolved')
        self.assertEqual(result['distance'],0.)

    def test_skinny_face_projection_inside_out_of_plane_and_scale(self):
        from collision_geometry import point_triangle,norm2,sub,mul,segments
        for height in (1e-4,1e-5):
            for scale in (1e-3,1.,1e3):
                tri=tuple(mul(q,scale) for q in ((0.,0.,0.),(10000.,0.,0.),(5000.,height,0.)))
                for z in (0.,.02):
                    p=mul((5000.,height/3,z),scale);q=point_triangle(p,tri)
                    self.assertAlmostEqual(norm2(sub(p,q))**.5/scale,z,places=12)
                # Nearly parallel finite edges have a real interior crossing.
                x,y=segments(mul((0.,0.,0.),scale),mul((10000.,height,0.),scale),mul((0.,height,0.),scale),mul((10000.,0.,0.),scale))
                self.assertLess(norm2(sub(x,y))**.5/scale,1e-12)

    def test_skinny_cap_on_closed_surface_nearest(self):
        mesh=list(triangles(box('Large cube',size=20000.)));a,b,c=mesh[0]
        m=tuple((x+y)/2 for x,y in zip(a,b));m=(m[0],m[1],.0001)
        surface=Surface([(a,m,c),(m,b,c),(a,b,m),*mesh[1:]])
        self.assertEqual(surface.thin_triangles,0)
        self.assertLess(surface.nearest((10000.,0.,.0001/3))[0],1e-12)
        self.assertAlmostEqual(surface.nearest((10000.,-2e-6,.0001/3))[0],2e-6,places=12)

    def test_large_faces_keep_micrometre_gaps_and_aabb_lower_bound(self):
        from collision_geometry import box_distance,distance
        for width in (2.,20000.):
            for gap in (1.5e-6,2e-6,1e-5):
                first=Surface(list(triangles(box('A',size=width))))
                second=Surface(list(triangles(box('B',x=width+gap,size=width))))
                measured=distance(first,second)[0];lower=box_distance(first.tree.box,second.tree.box)**.5
                self.assertGreaterEqual(measured,lower)
                self.assertAlmostEqual(measured,(width+gap)-width,places=12)
                self.assertEqual(relation(first,second,1e-6)['kind'],'Separated')

    def test_report_and_json(self):
        r=check([box('A'),box('B',x=4)]);self.assertIn('mm',r.text());self.assertIn('Discrete',r.text());self.assertIn('coverage_complete',r.json())

if __name__=='__main__':unittest.main()
