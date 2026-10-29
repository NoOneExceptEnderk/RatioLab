# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Direct carrier input, two side outputs, internal spider and prescribed speed split."""
from itertools import product
import json
from math import pi, sin, cos
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from geometry import generate, circle_info, profile_sections, section_holes, contains
from solid_geometry import signature
from motion import build_plan, transform, rotation, multiply, IDENTITY
from engineering import report_text
from ratiolab_agent import AgentService
from bom import port_properties
import cad_export
import stl_export


class DifferentialClassicTests(unittest.TestCase):
    def test_reference_benchmarks_forward_inverse_and_non_divided_rolling_constraints(self):
        for c,delta,a,b,spider in ((12,0,12,12,0),(12,24,0,24,12),(0,24,-12,12,12),(-5,-6,-2,-8,-3),(0,0,0,0,0)):
            for zs,zo in ((24,24),(17,25),(24,48)):
                d=generate('differential',dict(configuration='classic',input_rpm=c,output_difference_rpm=delta,side_teeth=zs,output_teeth=zo,width=4))
                q=d.analysis['kinematics']['rates_rpm']
                self.assertEqual((q['side_a'],q['side_b'],q['carrier']),(a,b,c))
                self.assertAlmostEqual(q['spider_spin'],spider*zs/zo)
                self.assertAlmostEqual(q['side_a']+q['side_b'],2*c)
                self.assertAlmostEqual(q['side_b']-q['side_a'],delta)
                self.assertAlmostEqual(zs*(a-c)+zo*q['spider_spin'],0)
                self.assertAlmostEqual(zs*(b-c)-zo*q['spider_spin'],0)
                self.assertNotIn('signed_ratio',d.analysis)
                self.assertNotIn('torque_Nm',d.analysis['input'])
                self.assertNotIn('input_a_rpm',d.analysis['input'])

    def test_all_saved_constructions_have_real_member_roles_closed_geometry_and_roundtrip(self):
        for variant,output,carrier,ratio in product(('straight','spiral'),('flange','solid','hollow'),('open','split'),('custom','one_to_one','spin_2_1')):
            with self.subTest(variant=variant,output=output,carrier=carrier,ratio=ratio):
                d=generate('differential',dict(configuration='classic',variant=variant,output_interface=output,carrier_style=carrier,ratio_mode=ratio))
                self.assertEqual(len(d.parts),17+2*(output=='flange')+4*(carrier=='split'))
                for p in d.parts:
                    self.assertGreater(signature(p)['volume_mm3'],0,p.name)
                    self.assertEqual(p.port['role'],'output' if p.port['member'] in ('A','B') else 'input' if p.port['member']=='carrier' else 'internal')
                names={p.name for p in d.parts}
                self.assertTrue({'Shaft_output_A','Shaft_output_B','Bevel_spider','Pin_spider','Flange_carrier_input'}<=names)
                self.assertFalse(names&{'Shaft_input_A','Shaft_input_B','Bevel_output','Shaft_output','Hub_output','Flange_output','Bearing_output_envelope'})
                self.assertEqual(generate('differential',json.loads(json.dumps(d.values))).parts,d.parts)
                spider=next(p for p in d.parts if p.name=='Bevel_spider')
                self.assertEqual(port_properties(spider)['Kinematic member'],'Internal spider')

    def test_actual_pin_radial_running_clearance_and_retainer_axial_gaps_at_endpoints(self):
        for pin,clearance,plate,gap in product((2,20),(.05,1),(3,12),(.1,1)):
            d=generate('differential',dict(configuration='classic',spider_pin_diameter=pin,spider_clearance=clearance,plate=plate,assembly_clearance=gap))
            parts={p.name:p for p in d.parts}
            spider=parts['Bevel_spider'];shaft=parts['Pin_spider']
            for z,_,outer in profile_sections(spider):
                bore=circle_info(section_holes(spider,z,outer)[0])[2]
                self.assertAlmostEqual(bore-circle_info(shaft.outer)[2],clearance)
            lower,upper=parts['Retainer_spider_lower'],parts['Retainer_spider_upper']
            self.assertAlmostEqual(spider.z-lower.z-lower.width,gap)
            self.assertAlmostEqual(upper.z-spider.z-spider.width,gap)
            self.assertEqual(shaft.port['member'],'carrier')
            for p in (spider,shaft,lower,upper):self.assertGreater(signature(p)['volume_mm3'],0)

    def test_side_hollow_passages_and_full_input_mount_width_are_reserved_before_output_interfaces(self):
        for output,plate,extension in product(('hollow','flange'),(4,12),(4,12)):
            d=generate('differential',dict(configuration='classic',output_interface=output,plate=plate,shaft_extension=extension))
            parts={p.name:p for p in d.parts};mount=parts['Flange_carrier_input']
            a,b=parts['Shaft_output_A'],parts['Shaft_output_B']
            self.assertGreater(circle_info(mount.holes[0])[2],circle_info(a.outer)[2])
            for loop in mount.holes[1:]:self.assertTrue(all(contains(mount.outer,q) and not contains(mount.holes[0],q) for q in loop))
            if output=='flange':
                fa,fb=parts['Flange_output_A'],parts['Flange_output_B']
                self.assertAlmostEqual(fa.z-(mount.z+mount.width),extension)
                self.assertEqual(circle_info(fa.holes[0])[2],circle_info(a.outer)[2])
                self.assertEqual(circle_info(fb.holes[0])[2],circle_info(b.outer)[2])
            else:
                self.assertAlmostEqual(a.z+a.width-mount.z-mount.width,extension)
                for shaft in (a,b):
                    self.assertAlmostEqual(circle_info(shaft.holes[0])[2],2)
                    self.assertAlmostEqual(circle_info(shaft.outer)[2]-circle_info(shaft.holes[0])[2],1)
            self.assertEqual(signature(mount)['min'][0],mount.z)

    def test_inactive_wrist_inputs_and_output_axis_dimensions_do_not_change_classic_models(self):
        base=generate('differential',dict(configuration='classic'))
        changed=generate('differential',dict(configuration='classic',input_b_rpm=999,output_shaft=24,output_extension=60))
        self.assertEqual(base.parts,changed.parts)
        self.assertEqual(base.analysis,changed.analysis)
        with self.assertRaises(ValueError):generate('differential',dict(configuration='classic',output_interface='hollow',input_shaft=6,passage_diameter=4.1))
        with self.assertRaises(ValueError):generate('differential',dict(configuration='classic',spider_pin_diameter=20,module=1,side_teeth=16,output_teeth=16,width=3))

    def test_motion_uses_each_derived_signed_rate_and_preserves_angles_during_carrier_or_difference_edits(self):
        d=generate('differential',dict(configuration='classic',input_rpm=-5,output_difference_rpm=-6))
        plan=build_plan(d);phase=1.7
        angles={key:value/plan.reference_rpm*phase for key,value in d.analysis['kinematics']['rates_rpm'].items()}
        for c,delta in ((0,24),(12,0),(0,0),(-7.5,17.25)):
            new=generate('differential',dict(d.values,input_rpm=c,output_difference_rpm=delta))
            updated=build_plan(new,previous=plan,phase=phase)
            q=new.analysis['kinematics']['rates_rpm']
            self.assertEqual(updated.reference_rpm,max(map(abs,q.values())) or 1)
            for i in range(len(new.parts)):
                for x,y in zip(plan.matrix(i,phase),updated.matrix(i,phase)):self.assertAlmostEqual(x,y,places=10)
            seconds=.37;phase+=seconds*updated.reference_rpm*2*pi/60
            for key,rate in q.items():angles[key]+=seconds*rate*2*pi/60
            for i,p in enumerate(new.parts):
                member=p.port['member']
                expected=(multiply(rotation(angles['carrier'],(1,0,0)),rotation(angles['spider_spin'],(0,0,1))) if member=='spider'
                          else rotation(angles['side_a' if member=='A' else 'side_b' if member=='B' else 'carrier'],(1,0,0)))
                for x,y in zip(updated.matrix(i,phase),expected):self.assertAlmostEqual(x,y,places=10)
            d,plan=new,updated

    def test_mcp_physical_labels_config_and_exports_describe_carrier_and_two_side_outputs(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);service=AgentService(root);self.addCleanup(service.close)
            discovery=service.discover('differential',parameters=dict(configuration='classic'))
            self.assertEqual(discovery['options']['configuration']['enum'],['wrist','classic'])
            labels={p['name']:p['label'] for p in discovery['fields']}
            self.assertIn('Carrier input',labels['input_rpm'])
            self.assertIn('Side output',labels['input_shaft'])
            self.assertIn('Spider',labels['output_teeth'])
            self.assertEqual(discovery['named_presets']['spin_2_1']['canonical_defaults']['configuration'],'classic')
            created=service.project_create('differential',dict(configuration='classic',variant='spiral',output_interface='hollow',carrier_style='split',input_rpm=0,output_difference_rpm=24))
            service.project_save(created['handle'],created['revision'],'classic.config.json')
            self.assertEqual(service.project_open('classic.config.json')['parameters'],created['parameters'])
            d=generate('differential',created['parameters'])
            _,metadata=cad_export.export(d,root/'step')
            assembly,parts=stl_export.export(d,root/'model')
            self.assertEqual(len(metadata),21)
            self.assertEqual(len(parts),21)
            self.assertGreater(assembly.stat().st_size,84)
            text=report_text(d)
            self.assertIn('Carrier input:',text)
            self.assertIn('prescribed B−A:',text)
            self.assertNotIn('Inputs A / B:',text)
            self.assertNotIn('torque_Nm',d.analysis['input'])


if __name__=='__main__':unittest.main()
