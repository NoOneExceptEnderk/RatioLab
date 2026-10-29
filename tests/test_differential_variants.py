# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Wrist interface choices share geometry, saved options and ideal speed rules."""
from itertools import product
import json
from math import hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from geometry import generate, circle_info, profile_sections, section_holes, contains
from solid_geometry import signature
from differential_wrist import OUTPUT_INTERFACES, CARRIER_STYLES, RATIO_MODES
from ratiolab_agent import AgentService
import cad_export
import stl_export
import profile_export


class DifferentialVariantsTests(unittest.TestCase):
    def test_legacy_configs_keep_the_original_flange_open_and_custom_counts(self):
        legacy=dict(module=2,width=4,side_teeth=17,output_teeth=25)
        old=generate('differential',legacy)
        explicit=generate('differential',dict(legacy,output_interface='flange',carrier_style='open',ratio_mode='custom'))
        self.assertEqual(old.parts,explicit.parts)
        self.assertEqual((old.values['side_teeth'],old.values['output_teeth']),(17,25))
        self.assertEqual(len(old.parts),17)
        self.assertEqual(generate('differential').values['ratio_mode'],'custom')

    def test_all_orthogonal_choices_roundtrip_as_closed_solids_with_the_same_rolling_equations(self):
        for output,carrier,mode in product(OUTPUT_INTERFACES,CARRIER_STYLES,RATIO_MODES):
            with self.subTest(output=output,carrier=carrier,mode=mode):
                d=generate('differential',dict(output_interface=output,carrier_style=carrier,ratio_mode=mode,input_rpm=-7.5,input_b_rpm=17.25))
                self.assertEqual(len(d.parts),17-(output!='flange')+4*(carrier=='split'))
                for p in d.parts:self.assertGreater(signature(p)['volume_mm3'],0,p.name)
                q=d.analysis['kinematics']['rates_rpm'];zs=d.values['side_teeth'];zo=d.values['output_teeth']
                self.assertAlmostEqual(zs*(q['input_a']-q['carrier'])+zo*q['output_spin'],0)
                self.assertAlmostEqual(zs*(q['input_b']-q['carrier'])-zo*q['output_spin'],0)
                self.assertAlmostEqual(q['carrier']-zo/zs*q['output_spin'],-7.5)
                self.assertAlmostEqual(q['carrier']+zo/zs*q['output_spin'],17.25)
                restored=generate('differential',json.loads(json.dumps(d.values)))
                self.assertEqual(restored.parts,d.parts)
                self.assertEqual(restored.analysis,d.analysis)

    def test_ratio_presets_affect_relative_spin_without_changing_carrier_mean(self):
        for mode,teeth,spin in [('one_to_one',24,-12),('spin_2_1',48,-6)]:
            d=generate('differential',dict(ratio_mode=mode,output_teeth=31))
            self.assertEqual(d.values['output_teeth'],teeth)
            self.assertEqual(d.analysis['kinematics']['rates_rpm']['carrier'],0)
            self.assertEqual(d.analysis['kinematics']['rates_rpm']['output_spin'],spin)
            stationary=generate('differential',dict(d.values,input_rpm=0,input_b_rpm=12))
            q=stationary.analysis['kinematics']['rates_rpm']
            self.assertEqual(q['carrier'],6)
            self.assertEqual(q['output_spin'],6 if mode=='one_to_one' else 3)
        self.assertEqual(generate('differential',dict(ratio_mode='custom',output_teeth=31)).values['output_teeth'],31)

    def test_hollow_passage_is_real_and_continuous_in_all_output_axis_members(self):
        d=generate('differential',dict(output_interface='hollow',passage_diameter=6,output_extension=19))
        wanted=d.values['passage_diameter']/2
        output=[p for p in d.parts if p.port['member']=='output']
        self.assertEqual({p.name for p in output},{'Bevel_output','Hub_output','Shaft_output'})
        for p in output:
            for z,_,outer in profile_sections(p):
                holes=section_holes(p,z,outer)
                self.assertTrue(holes,p.name)
                bore=circle_info(holes[0])
                self.assertIsNotNone(bore,p.name)
                for coordinate in bore[:2]:self.assertAlmostEqual(coordinate,0,places=12)
                self.assertGreaterEqual(bore[2],wanted-1e-10)
        shaft=next(p for p in output if p.name=='Shaft_output')
        support=next(p for p in d.parts if p.name=='Carrier_output_bridge')
        self.assertAlmostEqual(shaft.z+shaft.width-support.z-support.width,19)
        self.assertAlmostEqual(circle_info(shaft.outer)[2]-circle_info(shaft.holes[0])[2],1)
        self.assertIn('no full cable route',d.analysis['wrist_construction']['passage_scope'].lower())

    def test_split_seats_join_holes_clear_layer_gap_and_butt_corner_interfaces(self):
        for clearance,thickness,hole in ((.1,2.1,1),(.3,4,3),(1,3,6)):
            d=generate('differential',dict(carrier_style='split',assembly_clearance=clearance,plate=thickness,carrier_bolt_diameter=hole))
            cheeks=[p for p in d.parts if p.name.startswith('Carrier_cheek_')]
            self.assertEqual(len(cheeks),4)
            seat=d.values['input_shaft']/2+max(2,2*clearance+.6)
            for p in cheeks:
                self.assertFalse(p.holes,'Seats must be open notches, not renamed full rings')
                self.assertFalse(contains(p.outer,(0,0)))
                self.assertFalse(contains(p.outer,(seat*.5,0)))
                self.assertFalse(contains(p.outer,(-seat*.5,0)))
            for label in ('output','rear'):
                front=next(p for p in d.parts if p.name==f'Carrier_{label}_bridge_front')
                rear=next(p for p in d.parts if p.name==f'Carrier_{label}_bridge_rear')
                self.assertAlmostEqual(rear.z-(front.z+front.width),clearance)
                self.assertGreaterEqual(front.width,1-1e-10)
                self.assertEqual(len(front.holes),2)
                self.assertEqual(front.holes,rear.holes)
                # Matching bolt holes are entirely inside both lap polygons.
                for p in (front,rear):
                    for loop in p.holes:self.assertTrue(all(contains(p.outer,q) for q in loop))
                    bounds=signature(p)
                    self.assertLessEqual(bounds['max'][0],min(p.z for p in cheeks)+1e-9)
                    self.assertGreaterEqual(bounds['min'][0],-min(p.z for p in cheeks)-1e-9)
            for p in d.parts:self.assertGreater(signature(p)['volume_mm3'],0,p.name)

    def test_invalid_active_walls_seats_and_options_fail_without_restricting_inactive_flange_fields(self):
        cases=[dict(output_interface='hollow',passage_diameter=6.1),dict(carrier_style='split',plate=2,assembly_clearance=1),
               dict(carrier_style='split',carrier_bolt_diameter=6,module=1,side_teeth=16,output_teeth=16,width=3,input_shaft=2,output_shaft=2),
               dict(ratio_mode='spin_2_1',side_teeth=31),dict(output_interface='missing'),dict(carrier_style='missing'),dict(ratio_mode='missing')]
        for values in cases:
            with self.subTest(values=values),self.assertRaises(ValueError):generate('differential',values)
        self.assertEqual(generate('differential',dict(output_interface='solid',flange_radius=6)).values['flange_radius'],6)

    def test_split_hollow_models_export_the_same_actual_bores_and_member_count(self):
        d=generate('differential',dict(output_interface='hollow',carrier_style='split',ratio_mode='spin_2_1'))
        with TemporaryDirectory() as folder:
            root=Path(folder)
            _,step=cad_export.export(d,root/'step')
            assembly,parts=stl_export.export(d,root/'model')
            _,profiles=profile_export.export(d,root/'profiles')
            self.assertEqual(len(step),20)
            self.assertEqual(len(parts),20)
            self.assertGreater(assembly.stat().st_size,84)
            shaft=next(p for p in profiles['components'] if p['name']=='Shaft_output')
            self.assertEqual(shaft['profiles'][0]['holes'],1)
            for p in d.parts:self.assertGreater(signature(p)['volume_mm3'],0)

    def test_mcp_discovery_presets_and_saved_configuration_expose_orthogonal_options(self):
        with TemporaryDirectory() as folder:
            service=AgentService(Path(folder));self.addCleanup(service.close)
            discovery=service.discover('differential')
            for key,choices in (('output_interface',OUTPUT_INTERFACES),('carrier_style',CARRIER_STYLES),('ratio_mode',RATIO_MODES)):
                self.assertEqual(discovery['options'][key]['enum'],list(choices))
            self.assertEqual(discovery['named_presets']['spin_2_1']['canonical_defaults']['output_teeth'],48)
            self.assertIn('output_teeth',discovery['parameter_conditions'])
            created=service.project_create('differential',dict(output_interface='hollow',carrier_style='split',ratio_mode='spin_2_1'))
            service.project_save(created['handle'],created['revision'],'wrist.config.json')
            saved=json.loads((Path(folder)/'wrist.config.json').read_text())
            self.assertEqual(saved['parameters'],created['parameters'])
            reopened=service.project_open('wrist.config.json')
            self.assertEqual(reopened['parameters'],created['parameters'])


if __name__=='__main__':unittest.main()
