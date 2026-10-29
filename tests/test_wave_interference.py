# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Checker protocol, immutable deformation references and exact topology reuse."""
from copy import deepcopy
from math import pi,hypot
from threading import Event
import unittest
from unittest.mock import patch
from geometry import Part,Design,circle
from special_drives import ellipse_axes
from wave_geometry import map_point,material_vertices,posed_vertices
from interference import analyze,Settings,period
from motion import MotionPlan
from collision_geometry import Surface


def fixture():
    rp=4.;a,b=ellipse_axes(rp,.25);base=circle(rp,16)
    refs=[(__import__('math').atan2(y,x),hypot(x,y)-rp) for x,y in base]
    metadata=dict(schema='ratiolab.wave-map/1',ellipse_axes_mm=[a,b],pitch_radius_mm=rp,
                  body_length_mm=2.,diaphragm_mm=.5,conjugate=True)
    stations=[]
    for z,weight in ((0,0),(2,1)):
        material=[(*p,weight) for p in refs]
        stations.append(dict(z=z,outer=[map_point(*p,a,b,rp) for p in material],holes=[],
                             material_outer=material,material_holes=[]))
    p=Part('Flexspline_fixture',stations[-1]['outer'],width=2,center=(3,-2),z=7,
           stations=stations,profile_metadata=dict(wave_mapping=metadata))
    box=Part('Fixed',[(20,0),(22,0),(22,2),(20,2)],width=2,z=7)
    d=Design('harmonic',{'input_rpm':1},[p,box],analysis=dict(wave_mapping=metadata))
    plan=MotionPlan(flex={0:lambda phase:(0,phase,a,b,rp,2.,.5)},rates={0:(0.,1.)})
    return d,plan


class PrescribedWaveInterferenceTests(unittest.TestCase):
    def test_prescribed_pose_uses_original_material_and_preserves_shared_topology(self):
        d,plan=fixture();before=deepcopy(d);original=material_vertices(d.parts[0])
        first=posed_vertices(d.parts[0],original,plan.deformation(0,.73))
        posed_vertices(d.parts[0],original,plan.deformation(0,1.21))
        self.assertEqual(first,posed_vertices(d.parts[0],original,plan.deformation(0,.73)))
        for point,material in original.items():
            x,y=map_point(*material,*d.analysis['wave_mapping']['ellipse_axes_mm'],4,0,.73)
            self.assertEqual(first[point],(x+3,y-2,point[2]))
        self.assertEqual(period(plan),1)
        with patch('interference.Surface',wraps=Surface) as surface:
            result=analyze(d,Settings(step_degrees=180,max_poses=3,max_seconds=20),plan=plan)
        self.assertTrue(result.coverage_complete,result.issues)
        self.assertEqual((result.completed_poses,result.completed_pairs),(3,3))
        self.assertEqual(result.parts[0]['deformation'],'prescribed pitch-arc/normal map')
        counts=[len(call.args[0]) for call in surface.call_args_list]
        self.assertEqual(len(counts),5)
        self.assertEqual(counts[2:],[counts[0]]*3)
        self.assertEqual(d,before)

    def test_stale_material_or_nominal_geometry_is_explicitly_rejected(self):
        for target in ('material','geometry','schema','missing'):
            d,plan=fixture();station=d.parts[0].stations[-1]
            if target=='material':
                u,offset,w=station['material_outer'][0];station['material_outer'][0]=(u,offset+.01,w)
            elif target=='geometry':
                x,y=station['outer'][0];station['outer'][0]=(x+.01,y)
            elif target=='schema':d.parts[0].profile_metadata['wave_mapping']['schema']='unknown'
            else:station.pop('material_outer')
            result=analyze(d,Settings(max_poses=1),plan=plan)
            self.assertFalse(result.coverage_complete)
            self.assertFalse(result.parts[0]['supported'])
            self.assertTrue(any('material' in issue.lower() for issue in result.issues),result.issues)

    def test_malformed_and_unknown_deformations_are_results_not_uncaught_errors(self):
        for deformation in (None,('bad',0,1,1,1,1,1),(0,0,float('nan'),1,1,1,1),(0,0,1,1,1,1),
                            (0,0,5,4,4,2,.5)):
            d,plan=fixture();plan.flex[0]=lambda phase,value=deformation:value
            result=analyze(d,Settings(max_poses=1),plan=plan)
            self.assertFalse(result.coverage_complete)
            self.assertFalse(result.parts[0]['supported'])
        d,plan=fixture();d.family='spur'
        self.assertFalse(analyze(d,Settings(max_poses=1),plan=plan).parts[0]['supported'])

    def test_cancellation_time_and_triangle_limits_remain_honest(self):
        d,plan=fixture();cancel=Event()
        def progress(message,fraction):
            if message.startswith('Pose 2/'):cancel.set()
        result=analyze(d,Settings(step_degrees=180,max_poses=3),plan=plan,cancel=cancel,progress=progress)
        self.assertTrue(result.cancelled)
        self.assertFalse(result.coverage_complete)
        self.assertEqual(result.completed_poses,1)
        for settings in (Settings(max_triangles=1),Settings(max_seconds=1e-12),Settings(max_poses=1)):
            result=analyze(d,settings,plan=plan)
            self.assertFalse(result.coverage_complete)
            self.assertTrue(result.issues)


if __name__=='__main__':unittest.main()
