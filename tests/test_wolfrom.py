# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Exact mesh equations, compound clocking, strict gates and nominal solids."""
from copy import deepcopy
from fractions import Fraction
import json
from math import pi, hypot, remainder
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from geometry import FAMILIES, defaults, generate, get_specs, validate
from engineering import report_text
from motion import build_plan, update_operating_rates
from wolfrom import assembly_phases, dimensions, rates


class WolfromTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = generate('wolfrom')

    def assert_phases(self, s, p1, p2, ro, n):
        assembly = assembly_phases(s,p1,p2,ro,n)
        rf = s+2*p1
        # Solve the three mesh equations independently with exact Fractions.
        wc = Fraction(s,s+rf)
        wp = -Fraction(rf-p1,p1)*wc
        wo = wc+Fraction(p2,ro)*(wp-wc)
        for angle in (0., .127, -2.718, 43.1):
            for compound in assembly['compounds']:
                theta = compound['theta_rad']+float(wc)*angle
                phi1 = compound['planet_phase_rad']+float(wp)*angle
                phi2 = compound['planet2_phase_rad']+float(wp)*angle
                phif = assembly['fixed_ring_phase_rad']
                phio = assembly['output_ring_phase_rad']+float(wo)*angle
                residuals = (s*angle+p1*phi1-(s+p1)*theta-pi*(p1+1),
                             p1*phi1-rf*phif+(rf-p1)*theta-pi,
                             p2*phi2-ro*phio+(ro-p2)*theta-pi)
                for residual in residuals:
                    self.assertAlmostEqual(remainder(residual,2*pi),0,places=9)
                self.assertAlmostEqual(compound['planet2_phase_rad']-compound['planet_phase_rad'],assembly['common_clocking_rad'],places=13)
        return assembly

    def test_catalogue_order_derived_fields_and_project_roundtrip(self):
        self.assertEqual(list(FAMILIES)[-1],'wolfrom')
        self.assertEqual(list(FAMILIES)[:-1],['spur','helical','double','planetary','cycloidal','harmonic','worm','parallel','internal','differential'])
        fields = {q[0] for q in get_specs('wolfrom')}
        self.assertNotIn('module2',fields)
        self.assertNotIn('fixed_ring',fields)
        self.assertEqual(defaults('wolfrom')['planet2'],59)
        d = self.design
        restored = generate('wolfrom',json.loads(json.dumps(d.values)))
        self.assertEqual(restored.values,d.values)
        self.assertEqual(restored.analysis,d.analysis)
        self.assertAlmostEqual(d.analysis['wolfrom']['module2_mm'],45/76)
        self.assertEqual(d.analysis['wolfrom']['fixed_ring_teeth'],162)

    def test_exact_forward_inverse_mesh_rates_and_reverse_output(self):
        for p2,ro,ratio in ((59,135,600),(61,135,-600),(60,136,1360)):
            v = validate('wolfrom',dict(planet2=p2,output_ring=ro))
            for rpm in (Fraction(600),Fraction(-600),Fraction(0),Fraction(12345,17)):
                q = rates(v,rpm)
                wc = Fraction(18,180)*rpm
                wp = wc-Fraction(18,72)*(rpm-wc)
                wo = wc+Fraction(p2,ro)*(wp-wc)
                for key,expected in (('sun',rpm),('carrier',wc),('planet',wp),('output',wo),('ring',0)):
                    self.assertAlmostEqual(float(q[key]),float(expected))
                self.assertAlmostEqual(18*(q['sun']-q['carrier'])+72*(q['planet']-q['carrier']),0)
                self.assertAlmostEqual(162*(q['ring']-q['carrier'])-72*(q['planet']-q['carrier']),0)
                self.assertAlmostEqual(ro*(q['output']-q['carrier'])-p2*(q['planet']-q['carrier']),0)
                self.assertAlmostEqual(float(q['output']*ratio),float(rpm))
                self.assertEqual(dimensions(v)['signed_ratio'],ratio)
            built = generate('wolfrom',v)
            self.assertEqual(built.analysis['signed_ratio'],ratio)
            self.assert_phases(18,72,p2,ro,3)
        self.assertEqual(self.design.analysis['kinematics']['rates_rpm'],dict(sun=600,ring=0,carrier=60,planet=-75,output=1))

    def test_identical_compound_clocking_and_general_modular_inverse(self):
        a = self.assert_phases(18,72,59,135,3)
        for row,deg in zip(a['compounds'],(182.5,302.5,62.5)):
            self.assertAlmostEqual(row['planet_phase_rad']*180/pi,deg)
        b = self.assert_phases(18,18,17,55,3)
        self.assertEqual(b['k1'],0)
        self.assertEqual(generate('wolfrom',dict(planet=18,planet2=17,output_ring=55)).analysis['signed_ratio'],55)
        # First-stage spacing passes, and B is integral, but gcd(18,12)=6
        # cannot divide B=297. A mere divisibility-by-n test misses this.
        with self.assertRaisesRegex(ValueError,'gcd'):
            assembly_phases(18,18,12,54,4)
        with self.assertRaisesRegex(ValueError,'tooth phases'):
            assembly_phases(18,72,59,135,4)
        self.assertEqual(len(generate('wolfrom',dict(planets=1)).analysis['wolfrom']['assembly']['compounds']),1)

    def test_random_assembly_against_brute_tooth_reindex_and_mesh_equations(self):
        rng = Random(31847)
        passed = failed = 0
        for _ in range(250):
            s,p1,p2 = (rng.randrange(12,80) for _ in range(3))
            ro = rng.randrange(p2+10,180)
            n = rng.randrange(1,7)
            rf = s+2*p1
            B = Fraction(p1*ro+p2*s,n)
            possible = (s+rf)%n == 0 and any((p2*k+B)%p1 == 0 for k in range(p1))
            if possible:
                self.assert_phases(s,p1,p2,ro,n)
                v = dict(sun=s,planet=p1,planet2=p2,output_ring=ro,module=.5)
                if p1*ro != rf*p2:
                    q = rates(v,Fraction(-137,19))
                    self.assertEqual(s*(q['sun']-q['carrier'])+p1*(q['planet']-q['carrier']),0)
                    self.assertEqual(rf*(q['ring']-q['carrier'])-p1*(q['planet']-q['carrier']),0)
                    self.assertEqual(ro*(q['output']-q['carrier'])-p2*(q['planet']-q['carrier']),0)
                passed += 1
            else:
                with self.assertRaises(ValueError):assembly_phases(s,p1,p2,ro,n)
                failed += 1
        self.assertGreater(passed,40)
        self.assertGreater(failed,40)

    def test_invalid_parameters_rejected_without_mutating_accepted_design(self):
        d = self.design
        before = deepcopy((d.values,d.analysis,[p.port for p in d.parts]))
        bad = [dict(planet2=60),dict(output_ring=59),dict(planets=4),dict(planets=9),
               dict(planets=2.5),dict(sun=18.5),dict(planet2=float('nan')),
               dict(output_ring=float('inf')),dict(planet=True),dict(module=.2),
               dict(pressure=0),dict(bore=40),dict(bore=1,assembly_clearance=.6),
               dict(layer_gap=0),dict(width2=0),dict(plate=0),dict(backlash=.4),
               dict(variant='helical'),dict(helix=0),dict(profile_shift=0),
               dict(module2=45/76),dict(fixed_ring=162),dict(one_rim=True),
               dict(io_scheme='ring_sun_output'),dict(bearing_mode='shaft'),
               dict(hardware_mode='standard'),dict(input_rpm=float('nan')),
               dict(pressure=14.5)]
        for change in bad:
            with self.subTest(change=change),self.assertRaises(ValueError):
                generate('wolfrom',dict(d.values,**change))
        self.assertEqual((d.values,d.analysis,[p.port for p in d.parts]),before)

    def test_retired_project_fields_are_ignored_without_relaxing_geometry_gates(self):
        legacy = dict(material='al_6061_t6', stress_E=-1, stress_safety_factor=8,
                      manufacturing_technology='fdm',
                      manufacturing_settings={'fdm': {'infill': 999}},
                      stress_custom_obsolete={'invalid': True}, manufacturing_=None)
        supplied = dict(self.design.values, **legacy)
        before = deepcopy(supplied)
        restored = generate('wolfrom', supplied)
        self.assertEqual(restored.values, self.design.values)
        self.assertEqual(restored.parts, self.design.parts)
        self.assertEqual(restored.analysis, self.design.analysis)
        self.assertEqual(restored.metrics, self.design.metrics)
        self.assertEqual(restored.notes, self.design.notes)
        self.assertEqual(supplied, before)
        for change in (dict(helix=0), dict(profile_shift=0), dict(module2=45/76),
                       dict(material_density=1), dict(stress=1), dict(manufacturing=1)):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'Unsupported Wolfrom'):
                generate('wolfrom', dict(supplied, **change))

    def test_strict_profile_contact_and_clear_certificate_gates(self):
        from internal_mesh import _plan
        with self.assertRaisesRegex(ValueError,'must be clear'):
            generate('wolfrom',dict(backlash=0))
        _plan.cache_clear()
        try:
            with patch('internal_mesh.PLAN_INTERVAL_BUDGET',0),self.assertRaisesRegex(ValueError,'budget exhausted'):
                generate('wolfrom')
        finally:
            _plan.cache_clear()
        from engineering import mesh
        def trimmed(*args,**kwargs):
            q = mesh(*args,**kwargs)
            if not kwargs.get('internal'):
                q['profile_contact_total'] = .999
            return q
        with patch('engineering.mesh',side_effect=trimmed),self.assertRaisesRegex(ValueError,'usable and nominal'):
            generate('wolfrom')
        for pair in self.design.analysis['meshes']:
            self.assertGreaterEqual(pair['contact_total'],1)
            self.assertGreaterEqual(pair['profile_contact_total'],1)
            self.assertIsNone(pair['torque_factor'])
            self.assertNotIn('forces',pair)
        self.assertEqual([p['verification']['status'] for p in self.design.analysis['wolfrom']['internal_pair_plans']],['clear','clear'])

    def test_nominal_axial_radial_envelopes_connected_hubs_and_closed_solids(self):
        from solid_geometry import signature
        d = self.design
        v = d.values
        geometry = d.analysis['wolfrom']
        signatures = {p.name:signature(p) for p in d.parts}
        for info in signatures.values():self.assertGreater(info['volume_mm3'],0)
        self.assertGreater(geometry['adjacent_center_separation_mm'],2*max(geometry['planet_tip_radii_mm'])+v['assembly_clearance'])
        self.assertLess(geometry['pin_radius_mm'],v['bore']/2)
        self.assertGreater(geometry['hub_radius_mm'],v['bore']/2)
        self.assertLess(geometry['carrier_radius_mm']+v['assembly_clearance'],min(p['ring_tip_radius_mm'] for p in geometry['internal_pair_plans']))
        self.assertFalse(any(p.role=='housing' for p in d.parts))
        for j in range(1,4):
            rim1,rim2,hub = (next(p for p in d.parts if p.name==f'Compound_{j}_{suffix}') for suffix in ('rim1','rim2','hub'))
            self.assertEqual(rim1.z+rim1.width,hub.z)
            self.assertEqual(hub.z+hub.width,rim2.z)
            self.assertEqual(rim1.center,rim2.center)
            self.assertEqual(rim1.center,hub.center)
            self.assertEqual(len({p.port['rigid_group'] for p in (rim1,rim2,hub)}),1)
            # Each hub outer circle lies inside the actual two rim root circles,
            # so the full annular hub face touches material on both gear faces.
            for rim in (rim1,rim2):
                self.assertLess(geometry['hub_radius_mm'],min(hypot(*xy) for xy in rim.outer))
                self.assertEqual(rim.holes[0],hub.holes[0])
        for p in d.parts:
            self.assertIn('rpm',p.port)
            self.assertIn('label',p.port)
            self.assertEqual(p.profile_metadata['wolfrom']['rigid_group'],p.port['rigid_group'])

    def test_rate_metadata_reuse_and_signed_zero_phase_continuity(self):
        d = self.design
        original = deepcopy(d.analysis)
        oracle = build_plan(d)
        plan = build_plan(d)
        phase = input_angle = 0.
        for rpm,seconds in ((600,.13),(-317.125,.19),(0,.2),(43,.11),(-600,.17)):
            values = dict(d.values,input_rpm=rpm)
            updated = update_operating_rates(d,values)
            regenerated = generate('wolfrom',values)
            for name in ('analysis','metrics','notes','values','requirements'):
                self.assertEqual(getattr(updated,name),getattr(regenerated,name),name)
            self.assertEqual([p.port for p in updated.parts],[p.port for p in regenerated.parts])
            next_plan = build_plan(updated,plan,phase)
            for index,(a,b) in enumerate(zip(d.parts,updated.parts)):
                self.assertIs(a.outer,b.outer)
                self.assertIs(a.holes,b.holes)
                for x,y in zip(plan.matrix(index,phase),next_plan.matrix(index,phase)):
                    self.assertAlmostEqual(x,y,places=9)
            phase += (next_plan.reference_rpm if rpm else 0)*seconds*2*pi/60
            input_angle += rpm*seconds*2*pi/60
            for index in range(len(d.parts)):
                for x,y in zip(next_plan.matrix(index,phase),oracle.matrix(index,input_angle)):
                    self.assertAlmostEqual(x,y,places=8)
            # Both compound rims and hub have the same rigid matrix; the pins
            # and plates likewise share a common global carrier transform.
            groups = {}
            for index,p in enumerate(updated.parts):
                matrix = next_plan.matrix(index,phase)
                self.assertEqual(matrix,groups.setdefault(p.port['rigid_group'],matrix))
            d,plan = updated,next_plan
        self.assertEqual(self.design.analysis,original)
        with self.assertRaisesRegex(ValueError,'Unsupported Wolfrom'):
            update_operating_rates(d,dict(d.values,input_b_rpm=1))

    def test_export_profiles_bom_and_calculation_metadata(self):
        from bom import build,port_properties
        from profile_export import write_files
        d = self.design
        bom = json.loads(json.dumps(build(d)))
        self.assertEqual(len(bom['analysis']['meshes']),3)
        self.assertEqual(len(bom['analysis']['wolfrom']['internal_pair_plans']),2)
        self.assertEqual(len(bom['ports']),len(d.parts))
        for p in d.parts:
            self.assertEqual(port_properties(p)['Kinematic member'],p.port['label'])
        commands = d.commands()
        ports = [q['params']['values']['local.solidcraft.kinematic_port'] for q in commands
                 if 'local.solidcraft.kinematic_port' in q['params'].get('values',{})]
        self.assertEqual(ports,[p.port for p in d.parts])
        with TemporaryDirectory() as folder:
            metadata = write_files(d,folder)
            saved = json.loads((Path(folder)/'profiles.json').read_text())
            self.assertEqual(len(saved['components']),len(d.parts))
            for component,p in zip(metadata['components'],d.parts):
                self.assertEqual(component['profile_geometry']['wolfrom']['rigid_group'],p.port['rigid_group'])
            rings = [p for p in saved['components'] if p['name'] in ('Ring_fixed','Ring_output')]
            self.assertTrue(all(p['profile_geometry']['wolfrom']['internal_pair_construction']['verification']['status']=='clear' for p in rings))
        report = report_text(d)
        self.assertIn('Mesh 3:',report)
        self.assertIn('Overall efficiency is a user assumption',report)
        self.assertIn('No physical reversibility',report)
        self.assertEqual(report.count('Neutral transverse polygon clearance: clear'),2)


if __name__ == '__main__':
    unittest.main()
