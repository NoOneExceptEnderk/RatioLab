# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Bevel wrist ideal equations, compound rigid motion and shared export solids."""
import json
from math import cos, sin, pi, hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from geometry import generate, get_specs, circle_info
from motion import build_plan, transform, IDENTITY, rotation, multiply
from solid_geometry import signature
from engineering import report_text
from differential_wrist import dimensions
import cad_export
import stl_export
import profile_export


class DifferentialWristTests(unittest.TestCase):
    def test_bearing_envelopes_stay_closed_with_material_at_clearance_endpoints(self):
        spec=next(s for s in get_specs('differential') if s[0]=='assembly_clearance')
        for clearance in (spec[3],spec[2],.8,spec[4]):
            d=generate('differential',dict(assembly_clearance=clearance))
            bearings=[p for p in d.parts if p.name.startswith('Bearing_')]
            self.assertEqual(len(bearings),3)
            for part in d.parts:
                self.assertGreater(signature(part)['volume_mm3'],0,(clearance,part.name))
            for part in bearings:
                outer=circle_info(part.outer)[2];inner=circle_info(part.holes[0])[2]
                self.assertGreaterEqual(outer-inner,.6-1e-10,(clearance,part.name))

    def test_speed_changes_keep_all_physical_angles_and_integrate_new_signed_rates(self):
        d=generate('differential',dict(input_rpm=12,input_b_rpm=0))
        plan=build_plan(d);phase=1.7
        angles={key:value/plan.reference_rpm*phase for key,value in d.analysis['kinematics']['rates_rpm'].items()}
        for changes in (dict(input_rpm=-7.5),dict(input_b_rpm=17.25),dict(input_rpm=0),
                        dict(input_b_rpm=0),dict(input_b_rpm=-3),dict(input_rpm=31)):
            d=generate('differential',dict(d.values,**changes))
            updated=build_plan(d,previous=plan,phase=phase)
            for i,part in enumerate(d.parts):
                for old,new in zip(plan.matrix(i,phase),updated.matrix(i,phase)):
                    self.assertAlmostEqual(old,new,places=10,msg=part.name)
            # Integrate independently in seconds and compare every member's pose.
            seconds=.37
            phase+=seconds*updated.reference_rpm*2*pi/60
            for key,value in d.analysis['kinematics']['rates_rpm'].items():angles[key]+=seconds*value*2*pi/60
            for i,part in enumerate(d.parts):
                group=part.port['member']
                if group=='output':expected=multiply(rotation(angles['carrier'],(1,0,0)),rotation(angles['output_spin'],(0,0,1)))
                else:expected=rotation(angles['input_a' if group=='A' else 'input_b' if group=='B' else 'carrier'],(1,0,0))
                for actual,wanted in zip(updated.matrix(i,phase),expected):self.assertAlmostEqual(actual,wanted,places=10,msg=part.name)
            plan=updated

    def test_two_mesh_equations_for_equal_opposite_zero_and_mixed_inputs(self):
        for a,b in ((12,12),(12,-12),(0,12),(12,0),(-5,17),(0,0)):
            for zs,zo in ((24,24),(17,25),(32,20)):
                with self.subTest(a=a,b=b,zs=zs,zo=zo):
                    d=generate('differential',dict(input_rpm=a,input_b_rpm=b,side_teeth=zs,output_teeth=zo,width=4))
                    q=d.analysis['kinematics']['rates_rpm'];wc=q['carrier'];wo=q['output_spin']
                    # Independent stationary contact-line velocity constraints.
                    self.assertAlmostEqual(zs*(a-wc)+zo*wo,0)
                    self.assertAlmostEqual(zs*(b-wc)-zo*wo,0)
                    p=build_plan(d)
                    self.assertEqual(p.reference_rpm,max(abs(a),abs(b)) or 1)
                    for i in range(len(d.parts)):
                        self.assertEqual(p.matrix(i,0),IDENTITY)
                    self.assertNotIn('signed_ratio',d.analysis)
                    self.assertNotIn('output',d.analysis)
                    self.assertNotIn('torque_Nm',d.analysis['input'])

    def test_output_spin_axis_follows_carrier_with_two_rigid_rotations(self):
        d=generate('differential',dict(input_rpm=0,input_b_rpm=12))
        p=build_plan(d);i=next(i for i,x in enumerate(d.parts) if x.name=='Flange_output')
        phase=pi/2;tilt=phase/2;spin=phase/2
        actual=transform(p.matrix(i,phase),(1,0,5))
        expected=(cos(spin),sin(spin)*cos(tilt)-5*sin(tilt),sin(spin)*sin(tilt)+5*cos(tilt))
        for x,y in zip(actual,expected):self.assertAlmostEqual(x,y)
        self.assertEqual(p.matrix(next(i for i,x in enumerate(d.parts) if x.name=='Bevel_input_A'),phase),IDENTITY)

    def test_pitch_cones_closed_solids_independent_stubs_and_roundtrip(self):
        d=generate('differential')
        q=dimensions(d.values)
        self.assertAlmostEqual(d.analysis['bevel']['side_pitch_angle_deg']+d.analysis['bevel']['output_pitch_angle_deg'],90)
        for part in d.parts:
            self.assertGreater(signature(part)['volume_mm3'],0,part.name)
        gear=d.parts[0]
        self.assertLess(hypot(*gear.stations[0]['outer'][0]),hypot(*gear.stations[1]['outer'][0]))
        shafts={p.name:signature(p) for p in d.parts if p.name.startswith('Shaft_input')}
        self.assertGreater(shafts['Shaft_input_A']['min'][0],0)
        self.assertLess(shafts['Shaft_input_B']['max'][0],0)
        self.assertAlmostEqual(q['cone_distance'],(24**2+24**2)**.5)
        self.assertFalse(any(word in p.name.lower() for p in d.parts for word in ('belt','pulley','motor')))
        restored=generate(d.family,json.loads(json.dumps(d.values)))
        self.assertEqual(d.parts,restored.parts)
        self.assertEqual(d.analysis,restored.analysis)
        self.assertIn('sampled approximations', ' '.join(d.notes).lower())

    def test_invalid_dimensions_and_unsupported_connections_are_rejected(self):
        for values in (dict(width=25),dict(input_shaft=24,module=1,width=4),dict(flange_radius=6),
                       dict(side_teeth=24.5),dict(input_b_rpm=float('nan')),
                       dict(input_rpm=float('inf')),dict(io_scheme='forward'),
                       dict(variant='belt')):
            with self.subTest(values=values),self.assertRaises(ValueError):generate('differential',values)

    def test_step_stl_profiles_retain_whole_assembly_and_nominal_pose(self):
        d=generate('differential');before=json.dumps(d.commands(),sort_keys=True)
        plan=build_plan(d)
        for i in range(len(d.parts)):plan.matrix(i,1.7)
        with TemporaryDirectory() as folder:
            root=Path(folder)
            _,step=cad_export.export(d,root/'step')
            assembly,parts=stl_export.export(d,root/'stl')
            _,profiles=profile_export.export(d,root/'profiles')
            self.assertEqual(len(step),len(d.parts))
            self.assertEqual(len(parts),len(d.parts))
            self.assertGreater(assembly.stat().st_size,84)
            self.assertEqual(len(profiles['components']),len(d.parts))
            self.assertFalse(profiles['components'][0]['extrudible'])
            self.assertTrue(profiles['components'][0]['profile_geometry']['bevel_profile']['conjugacy_verified'])
            self.assertIn('Analytic working flanks',profiles['components'][0]['profile_geometry']['bevel_profile']['verification_scope'])
        self.assertEqual(before,json.dumps(d.commands(),sort_keys=True))
        self.assertIn('No combined power or output torque estimate',report_text(d))


if __name__=='__main__':unittest.main()
