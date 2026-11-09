# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Omitted shaft bodies, valid interface metadata and geometry-aware presets."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from geometry import generate
from kinematics import options
from printed_shaft import interface_presets,KEYED_PRESET
import selected_export


class CadInterfaceTests(unittest.TestCase):
    def test_separate_shafts_are_absent_from_every_arrangement(self):
        for construction in ('integral','standard','d_shaft','keyed_shaft','fdm_bolted'):
            for variant in ('single','dual'):
                schemes=options('cycloidal') if construction!='fdm_bolted' else ('eccentric_output_ring','eccentric_ring_output')
                for scheme in schemes:
                    with self.subTest(construction=construction,variant=variant,scheme=scheme):
                        values=dict(KEYED_PRESET) if construction=='keyed_shaft' else {}
                        values.update(eccentric_design=construction,variant=variant,io_scheme=scheme)
                        d=generate('cycloidal',values)
                        shafts=[p for p in d.parts if p.name.startswith('Shaft_')]
                        self.assertEqual(len(shafts),1 if construction=='integral' else 0)
                        if shafts:self.assertEqual(shafts[0].port['member'],'eccentric')
                        names={p.name for p in d.parts}
                        for interface in d.analysis.get('mount_interfaces',[]):
                            self.assertIn(interface['anchor'],names)
                            self.assertTrue(set(interface['parts'])<=names)
                        if construction!='fdm_bolted':
                            record=d.analysis['eccentric_connection']
                            self.assertIn(record['part'],names)
                            self.assertEqual(record['shaft_generated'],construction=='integral')
                        self.assertTrue(any(p['member']=='output' for p in d.analysis['external_shafts']))
                        if construction in ('standard','d_shaft','keyed_shaft'):
                            self.assertTrue(any(p['member']=='eccentric' for p in d.analysis['external_shafts']))

    def test_presets_keep_surrounding_dimensions_and_reject_the_wrong_geometry(self):
        values=dict(variant='dual',bore=18,width=10,input_shaft=4)
        before=deepcopy(values)
        presets=interface_presets(values)
        self.assertEqual(values,before)
        six=next(p for p in presets if p['shaft_diameter_mm']==6)
        twelve=next(p for p in presets if p['shaft_diameter_mm']==12)
        self.assertTrue(six['available']);self.assertFalse(twelve['available'])
        self.assertTrue(twelve['reason'])
        self.assertEqual(set(six['parameters']),{'eccentric_design','input_shaft'})
        d=generate('cycloidal',dict(values,**six['parameters']))
        self.assertEqual(d.values['bore'],18);self.assertEqual(d.values['width'],10)
        self.assertEqual(d.analysis['eccentric_connection']['key_width_mm'],2)
        self.assertFalse(any(p['available'] for p in interface_presets({})))

    def test_bearing_linked_diameter_does_not_mislabel_a_din_preset(self):
        presets=interface_presets(dict(variant='dual',bearing_mode='shaft',bearing='626',bore=26,width=10))
        for p in presets:
            if p['available']:
                d=generate('cycloidal',dict(variant='dual',bearing_mode='shaft',bearing='626',bore=26,width=10,**p['parameters']))
                self.assertEqual(d.values['input_shaft'],p['shaft_diameter_mm'])

    def test_full_export_and_bom_do_not_reintroduce_omitted_shafts(self):
        with TemporaryDirectory() as temporary:
            d=generate('cycloidal',dict(KEYED_PRESET,eccentric_design='keyed_shaft',variant='dual'))
            target=Path(temporary)/'cad'
            selected_export.export(d,list(range(len(d.parts))),'step',target,revision='no-reference-shafts')
            scope=json.loads((target/'selection.json').read_text())
            self.assertFalse(any(p['name'].startswith('Shaft_') for p in scope['components']))
            self.assertEqual((target/'assembly.step').read_text().count('CLOSED_SHELL('),len(d.parts))

    def test_browser_schema_offers_the_same_filtered_presets(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge as web
        values=dict(variant='dual',bore=18,width=10,input_shaft=4)
        self.assertEqual(web.schema('cycloidal',values)['eccentric_interface_presets'],interface_presets(values))

    def test_output_machining_requirements_survive_removal_of_the_body(self):
        d=generate('cycloidal',dict(hardware_mode='standard',hardware_retaining=False,
            hardware_bolts=False,hardware_shims=False,hardware_keys=True))
        external=next(p for p in d.analysis['external_shafts'] if p['member']=='output')
        self.assertTrue(any(operation['type']=='keyway_shaft' for operation in external['machining']))
        self.assertIn('machining_origin_z_mm',external)
        self.assertFalse(any(p.name=='Shaft_output' for p in d.parts))


if __name__=='__main__':unittest.main()
