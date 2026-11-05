# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Direct shaft mating geometry, closed exports and preserved disc profiles."""
import json
from math import acos, cos, hypot, pi, sin, sqrt
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from geometry import generate
from kinematics import options
from printed_shaft import KEYED_PRESET
from solid_geometry import signature
import selected_export


def arguments(construction, **extra):
    values = dict(KEYED_PRESET) if construction == 'keyed_shaft' else {}
    return dict(values, eccentric_design=construction, **extra)


class DirectShaftTests(unittest.TestCase):
    def test_all_arrangements_preserve_discs_and_keep_complete_connections(self):
        for construction in ('d_shaft','keyed_shaft'):
            for variant in ('single','dual'):
                for scheme in options('cycloidal'):
                    with self.subTest(construction=construction,variant=variant,scheme=scheme):
                        values=arguments(construction,variant=variant,io_scheme=scheme,
                            eccentric_connection_angle=37,eccentric_bore_allowance=.08)
                        d=generate('cycloidal',values)
                        old=generate('cycloidal',dict(values,eccentric_design='standard'))
                        discs=lambda x:[p for p in x.parts if p.name.startswith('Disc_cycloidal_')]
                        self.assertEqual(discs(d),discs(old))
                        self.assertEqual(d.analysis['kinematics'],old.analysis['kinematics'])
                        record=d.analysis['eccentric_connection']
                        self.assertFalse(record['intermediate_insert'])
                        names={p.name for p in d.parts}
                        self.assertIn(record['part'],names)
                        for interface in d.analysis.get('mount_interfaces',[]):
                            self.assertIn(interface['anchor'],names)
                        members=[p for p in d.parts if p.name==record['part'] or p.name.startswith('Eccentric_')]
                        for p in members:
                            self.assertGreater(signature(p)['volume_mm3'],0)
                            self.assertEqual(p.role,'gear')
                            self.assertEqual(p.port['member'],'eccentric')
                        keys=[p for p in members if p.name.startswith('Eccentric_key_')]
                        self.assertEqual(len(keys),(1 if variant=='single' else 2) if construction=='keyed_shaft' else 0)

    def test_d_flat_and_diametral_allowance_match_the_actual_shaft(self):
        for angle in (0,37,-90,180):
            d=generate('cycloidal',arguments('d_shaft',variant='dual',
                eccentric_flat_depth=.6,eccentric_bore_allowance=.1,eccentric_connection_angle=angle))
            radius=d.values['input_shaft']/2
            a=angle*pi/180;c,s=cos(a),sin(a)
            for cam in (p for p in d.parts if p.name in ('Eccentric_1','Eccentric_2')):
                world=[(x+cam.center[0],y+cam.center[1]) for x,y in cam.holes[0]]
                local=[(x*c+y*s,-x*s+y*c) for x,y in world]
                self.assertAlmostEqual(max(x for x,y in local),radius-.6+.05)
                self.assertAlmostEqual(max(hypot(x,y) for x,y in local),radius+.05)
            shaft=next(p for p in d.parts if p.name=='Shaft_input')
            self.assertTrue(all(abs(hypot(x,y)-radius)<1e-8 for x,y in shaft.stations[0]['outer']))
            # Independent circular-segment area oracle, over the entire flat span.
            cut=radius-.6
            removed=radius*radius*acos(cut/radius)-cut*sqrt(radius*radius-cut*cut)
            span=2*d.values['width']+d.values['disc_gap']
            expected=pi*radius*radius*shaft.width-removed*span
            self.assertAlmostEqual(signature(shaft)['volume_mm3']/expected,1,delta=.0002)

    def test_key_dimensions_pockets_and_procurement_are_coherent(self):
        d=generate('cycloidal',arguments('keyed_shaft',variant='dual'))
        record=d.analysis['eccentric_connection']
        self.assertEqual([record[k] for k in ('key_width_mm','key_height_mm','shaft_keyway_depth_mm','hub_keyway_depth_mm')],[2,2,1.2,1])
        self.assertAlmostEqual(record['shaft_keyway_depth_mm']+record['hub_keyway_depth_mm']-record['key_height_mm'],.2)
        shaft=next(p for p in d.parts if p.name=='Shaft_input')
        keys=[p for p in d.parts if p.name.startswith('Eccentric_key_')]
        for key in keys:
            self.assertAlmostEqual(signature(key)['volume_mm3'],2*2*8)
            self.assertEqual(key.procurement['dimensions'],'2 × 2 × 8 mm')
            self.assertGreaterEqual(key.z % (d.values['width']+d.values['disc_gap']),.5)
        self.assertTrue(all(not s['holes'] for s in shaft.stations))
        self.assertTrue(any('axial retention' in q for q in d.requirements))
        self.assertFalse(any('keys, threads and seals are not generated' in q for q in d.notes))

    def test_catalog_journals_and_json_roundtrip(self):
        for construction in ('d_shaft','keyed_shaft'):
            values=dict(arguments(construction,variant='dual'),bearing_mode='gear',bearing='6001')
            d=generate('cycloidal',values)
            again=generate('cycloidal',json.loads(json.dumps(d.values)))
            self.assertEqual(d.values,again.values)
            self.assertEqual(d.parts,again.parts)
            for cam in (p for p in d.parts if p.name in ('Eccentric_1','Eccentric_2')):
                self.assertAlmostEqual(hypot(*cam.outer[0]),6)
                signature(cam)

    def test_invalid_engagement_and_incompatible_keyed_dimensions_are_rejected(self):
        cases=[dict(eccentric_design='d_shaft',eccentric_flat_depth=2),
               dict(eccentric_design='d_shaft',eccentric_flat_depth=.1,eccentric_bore_allowance=.3),
               dict(eccentric_design='keyed_shaft'),
               dict(eccentric_design='keyed_shaft',input_shaft=6,bore=18,width=8),
               dict(eccentric_design='keyed_shaft',input_shaft=6,bore=16,width=10,variant='dual')]
        for values in cases:
            with self.subTest(values=values),self.assertRaises(ValueError):
                generate('cycloidal',values)

    def test_selected_step_exports_original_direct_parts(self):
        with TemporaryDirectory() as temporary:
            for construction in ('d_shaft','keyed_shaft'):
                d=generate('cycloidal',arguments(construction,variant='dual'))
                indices=[i for i,p in enumerate(d.parts) if p.name in ('Shaft_input','Eccentric_2')]
                target=Path(temporary)/construction
                selected_export.export(d,indices,'step',target,revision='direct-shaft')
                self.assertEqual((target/'assembly.step').read_text().count('CLOSED_SHELL('),2)
                scope=json.loads((target/'selection.json').read_text())
                self.assertEqual(scope['source_indices'],[i+1 for i in indices])

    def test_web_schema_and_native_engine_agree_on_active_dimensions(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge as web
        for construction in ('integral','d_shaft','keyed_shaft'):
            values=arguments(construction)
            schema=web.schema('cycloidal',values)
            fields={p['key']:p for p in schema['fields']}
            self.assertEqual(fields['eccentric_flat_depth']['inactive'],construction!='d_shaft')
            self.assertEqual(fields['eccentric_bore_allowance']['inactive'],construction=='integral')
            engine=web.Engine()
            result=engine.call('generate',dict(family='cycloidal',parameters=values))
            self.assertEqual(result['values']['eccentric_design'],construction)
            self.assertEqual(engine.design.parts,generate('cycloidal',values).parts)


if __name__=='__main__':unittest.main()
