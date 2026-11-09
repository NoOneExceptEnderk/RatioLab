# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Resident collision meshes preserve literal facets and conservative controls."""
from contextlib import ExitStack
from copy import deepcopy
from math import pi
from threading import Event
from unittest.mock import patch
import hashlib
import struct
import unittest

from collision_geometry import Surface,distance,relation,triangle_distance
from geometry import Part,generate
from interference import analyze,Settings
from motion import IDENTITY,MotionPlan,multiply,posed_triangles,rotation,translation
from rust_geometry import call,control_scope
from solid_geometry import faces
from stl_export import triangles,triangulate
from test_interference import box,design


def literal(part):
    return tuple(triangle for face in faces(part) for triangle in triangulate(face))


def digest(mesh):
    result=hashlib.sha256()
    for triangle in mesh:
        result.update(struct.pack('<9d',*(x for p in triangle for x in p)))
    return result.hexdigest()


class CollisionReuseTests(unittest.TestCase):
    def own(self,surface):
        self.addCleanup(surface.close)
        return surface

    def test_shared_facets_match_literal_faces_and_preserve_mutation_detection(self):
        tube=Part('tube',[(0,0),(6,0),(6,6),(0,6)],
                  holes=[[(1,1),(5,1),(5,5),(1,5)]],width=3)
        cases=[tube,box('box')]
        for family,values in [('spur',{}),('helical',{}),('internal',{}),
                              ('internal',dict(variant='double')),('worm',{}),('cycloidal',{})]:
            cases.append(generate(family,values).parts[0])
        for part in cases:
            with self.subTest(part=part.name):
                source=deepcopy(part)
                with ExitStack() as stack:
                    surface=Surface.from_part(part);stack.callback(surface.close)
                    self.assertIsNone(surface._triangles)
                    expected=literal(part)
                    self.assertEqual(surface.triangle_count,len(expected))
                    self.assertEqual(digest(surface.triangles),digest(expected))
                    self.assertEqual(part,source)
        first=self.own(Surface.from_part(tube))
        tube.center=(2.,3.)
        second=self.own(Surface.from_part(tube))
        self.assertNotEqual(digest(first.triangles),digest(second.triangles))
        self.assertEqual(digest(second.triangles),digest(literal(tube)))

    def test_posed_coordinates_are_bit_identical_to_literal_affine_path(self):
        original=self.own(Surface.from_part(box('source',x=2,y=-3,z=.125)))
        for angle in (0.,.31,1.27):
            matrix=multiply(translation(4,-2,3),rotation(angle,axis=(1,2,3)))
            with self.subTest(angle=angle):
                moved=self.own(original.posed(matrix))
                self.assertIsNone(moved._triangles)
                expected=posed_triangles(matrix,original.triangles)
                self.assertEqual(digest(moved.triangles),digest(expected))
                self.assertEqual(moved.triangle_count,original.triangle_count)

    def test_refitted_distance_matches_exhaustive_world_triangle_distances(self):
        tube=Part('tube',[(0,0),(6,0),(6,6),(0,6)],
                  holes=[[(1,1),(5,1),(5,5),(1,5)]],width=3)
        first=self.own(Surface.from_part(tube))
        source=self.own(Surface.from_part(box('moving',size=1)))
        for angle in (.0,.31,1.27):
            for offset in ((2.,2.,.5),(7.,0.,0.),(6.000002,0.,0.),(-2.,3.,4.)):
                matrix=multiply(translation(*offset),rotation(angle,axis=(1,2,3)))
                second=source.posed(matrix)
                try:
                    expected=min(triangle_distance(a,b)[0] for a in first.triangles for b in second.triangles)**.5
                    self.assertAlmostEqual(distance(first,second)[0],expected,places=11)
                finally:second.close()

    def test_contact_witness_policy_matches_original_world_rebuild(self):
        first=self.own(Surface.from_part(box('fixed')))
        source=self.own(Surface.from_part(box('moving')))
        for offset in ((2.,0.,0.),(1.,.3,.2),(2.,2.,2.),(.1,.1,.1)):
            matrix=translation(*offset)
            moved=source.posed(matrix)
            raw=Surface(posed_triangles(matrix,source.triangles))
            try:self.assertEqual(relation(first,moved,.01),relation(first,raw,.01))
            finally:moved.close();raw.close()
        outer=self.own(Surface.from_part(box('outer',size=10)))
        inner=self.own(Surface.from_part(box('inner',size=1)))
        moved=self.own(inner.posed(translation(3,3,3)))
        self.assertEqual(relation(outer,moved,.01)['kind'],'Containment')

    def test_large_and_nearly_collinear_refits_keep_micrometre_clearances(self):
        for width in (2.,20000.):
            first=self.own(Surface.from_part(box('fixed',size=width)))
            for gap in (1.5e-6,2e-6,1e-5):
                second=first.posed(translation(width+gap,0,0))
                try:
                    self.assertAlmostEqual(distance(first,second)[0],(width+gap)-width,places=12)
                    self.assertEqual(relation(first,second,1e-6)['kind'],'Separated')
                finally:second.close()
        mesh=list(triangles(box('collinear')));a,b,c=mesh[0]
        midpoint=tuple((x+y)/2 for x,y in zip(a,b))
        source=self.own(Surface([(a,midpoint,c),(midpoint,b,c),(a,b,midpoint),*mesh[1:]]))
        moved=self.own(source.posed(translation(.3,-.2,1.)))
        self.assertEqual(moved.thin_triangles,source.thin_triangles)
        self.assertEqual(moved.edge_approximation_mm,source.edge_approximation_mm)

    def test_deformed_mesh_starts_from_original_material_and_matches_literal_map(self):
        from test_wave_interference import fixture
        from wave_geometry import material_vertices,posed_vertices
        d,plan=fixture();part=d.parts[0];before=deepcopy(d)
        source=self.own(Surface.from_part(part,deformation=plan.deformation(0,0.),flex=True))
        references=material_vertices(part)
        matrix=rotation(.27,axis=(1,2,3))
        seen=[]
        for phase in (.73,1.21,.73):
            mapped=posed_vertices(part,references,plan.deformation(0,phase))
            expected=posed_triangles(matrix,[[mapped[q] for q in t] for t in source.triangles])
            moved=source.posed(matrix,plan.deformation(0,phase))
            try:
                seen.append(digest(moved.triangles))
                self.assertEqual(seen[-1],digest(expected))
                self.assertEqual(moved.triangle_count,source.triangle_count)
            finally:moved.close()
        self.assertEqual(seen[0],seen[2]);self.assertEqual(d,before)
        for value in (None,(0,0,5,4,4,2,.5)):
            with self.assertRaisesRegex(ValueError,'deformation'):
                source.posed(IDENTITY,value)

    def test_singular_reflected_and_invalid_inputs_remain_rejected(self):
        source=self.own(Surface.from_part(box('source')))
        before=call('collision_stats',{})['surfaces']
        matrices=[(0.,)*16,(-1.,*IDENTITY[1:]),(float('nan'),*IDENTITY[1:])]
        for matrix in matrices:
            with self.assertRaises(ValueError):source.posed(matrix)
        self.assertEqual(call('collision_stats',{})['surfaces'],before)
        opened=box('open');opened.mesh=[[[[0,0,0],[1,0,0],[0,1,0]]]]
        with self.assertRaisesRegex(ValueError,'not closed'):Surface.from_part(opened)

    def test_cancellation_during_pose_and_after_handle_adoption_does_not_leak(self):
        import collision_geometry
        armed=[]
        class Cancelled(Exception):pass
        def check():
            if armed:raise Cancelled('original control exception')
        source=self.own(Surface.from_part(box('source'),check))
        baseline=call('collision_stats',{})['surfaces']
        actual=collision_geometry._call
        def invalidate_after_create(operation,parameters=None,**kwargs):
            result=actual(operation,parameters,**kwargs)
            if operation=='collision_pose':armed.append(True)
            return result
        with patch.object(collision_geometry,'_call',invalidate_after_create):
            with self.assertRaisesRegex(Cancelled,'original control'):source.posed(translation(3,2,1))
        armed.clear()
        self.assertEqual(call('collision_stats',{})['surfaces'],baseline)
        armed.append(True)
        with self.assertRaises(Cancelled):source.posed(translation(3,2,1))
        armed.clear();self.assertEqual(call('collision_stats',{})['surfaces'],baseline)
        with control_scope(lambda:(_ for _ in ()).throw(Cancelled())):source.close()
        self.assertEqual(call('collision_stats',{})['surfaces'],baseline-1)

    def test_backend_binding_and_owned_triangles_survive_source_release(self):
        source=Surface.from_part(box('source'))
        with patch('rust_geometry._library',side_effect=AssertionError('wrong global backend')):
            moved=source.posed(translation(3,2,1))
            source.close()
            owned=moved.triangles;expected=digest(owned)
            moved.nearest((0,0,0));moved.close()
            self.assertEqual(digest(owned),expected)
        a=self.own(Surface.from_part(box('A')));b=self.own(Surface.from_part(box('B')))
        b._identity=('different',-1)
        for query in (distance,lambda a,b:relation(a,b,.01)):
            with self.assertRaisesRegex(ValueError,'different Rust backends'):query(a,b)

    def test_analyze_transfers_handles_and_matrices_and_closes_all_resources(self):
        import collision_geometry
        actual=collision_geometry._call;seen=[]
        def observe(operation,parameters=None,**kwargs):
            if operation in ('collision_create','collision_pose','collision_create_surface'):
                seen.append((operation,parameters))
            return actual(operation,parameters,**kwargs)
        d=design([box('moving',x=3),box('fixed',x=8)])
        from motion import rigid
        plan=MotionPlan(poses={0:rigid(1)},rates={0:(1,)})
        baseline=call('collision_stats',{})['surfaces']
        with patch.object(collision_geometry,'_call',observe):
            result=analyze(d,Settings(step_degrees=180,max_poses=3),plan=plan)
        self.assertTrue(result.coverage_complete,result.issues)
        self.assertEqual(call('collision_stats',{})['surfaces'],baseline)
        self.assertEqual(sum(op=='collision_create_surface' for op,_ in seen),2)
        self.assertFalse(any(op=='collision_create' for op,_ in seen))
        self.assertTrue(any(op=='collision_pose' for op,_ in seen))
        self.assertFalse(any('triangles' in data or 'points' in data for _,data in seen))
        cancel=Event()
        def progress(message,fraction):
            if message.startswith('Pose 2/'):cancel.set()
        result=analyze(d,Settings(step_degrees=180,max_poses=3),plan=plan,cancel=cancel,progress=progress)
        self.assertTrue(result.cancelled);self.assertEqual(result.completed_poses,1)
        self.assertEqual(call('collision_stats',{})['surfaces'],baseline)

    def test_existing_face_and_triangle_resource_limits_are_not_bypassed(self):
        baseline=call('collision_stats',{})['surfaces']
        with self.assertRaisesRegex(ValueError,'Assembly triangle limit'):
            Surface.from_part(box('small budget'),max_triangles=1)
        large=Part('large face',[(float(i),float(i%3)) for i in range(40001)],width=1)
        with self.assertRaisesRegex(ValueError,'Face vertex limit'):
            Surface.from_part(large)
        self.assertEqual(call('collision_stats',{})['surfaces'],baseline)


if __name__=='__main__':unittest.main()
