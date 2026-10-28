"""Standalone CAD/profile exports and their failure/publication boundaries."""
import base64
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import copy
import hashlib
import json
import math
import pickle
import re
import unittest
import xml.etree.ElementTree as ET

import cad_export
from export_transaction import directory, write_text
from geometry import CircleProfile, Design, Part, circle, generate, transformed, FAMILIES, VARIANTS
import package_export
import profile_export
import stl_export


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2ioAAAAASUVORK5CYII=')


class CadExportTests(unittest.TestCase):
    def tube(self, **kwargs):
        return Part('Tube',circle(10),[circle(3)],width=8,**kwargs)

    def test_circle_provenance_survives_safe_transforms_and_serialization(self):
        original=circle(10)
        self.assertEqual(json.loads(json.dumps(original)),[list(p) for p in original])
        for value in (copy.deepcopy(original),pickle.loads(pickle.dumps(original)),transformed(original,(12,4),.3)):
            self.assertIsInstance(value,CircleProfile)
            self.assertTrue(value.intact())
        self.assertIsInstance(asdict(self.tube())['outer'],list)
        self.assertFalse(asdict(self.tube())['outer'].intact())
        self.assertFalse(CircleProfile(iter(original)).intact())

    def test_no_fitting_of_polygons_keyways_or_mutated_circles(self):
        polygon=self.tube();polygon.outer=list(polygon.outer);polygon.holes=[list(polygon.holes[0])]
        self.assertFalse(cad_export.circular_walls(polygon))
        changed=self.tube();changed.holes[0][0]=(4,0)
        self.assertEqual(set(cad_export.circular_walls(changed)),{0})
        # A high-sided equiradial polygon is still intentionally polygonal.
        polygon=self.tube();polygon.outer=transformed(list(polygon.outer),angle=.2);polygon.holes=[]
        text,info=cad_export.document([polygon])
        self.assertEqual(info[0]['cylinders'],0)
        self.assertNotIn('CYLINDRICAL_SURFACE',text)
        self.assertIn('FACETED_BREP',text)
        polygon.name="Élément #42 'rear'"
        with TemporaryDirectory() as temporary:
            target=Path(temporary)/'faceted.step';cad_export.write(target,[polygon])
            text=target.read_text(encoding='ascii')
            self.assertIn('\\X2\\00C9\\X0\\',text)
            self.assertIn('#42',text)
            self.assertIn("''rear''",text)

    def test_invariant_and_eccentric_helical_holes(self):
        d=generate('helical')
        self.assertEqual(set(cad_export.circular_walls(d.parts[0])),{1})
        eccentric=self.tube(twist=30);eccentric.holes=[circle(2,center=(4,0))]
        self.assertNotIn(1,cad_export.circular_walls(eccentric))
        self.assertIn(0,cad_export.circular_walls(eccentric))
        groove=self.tube();groove.stations=[dict(z=z,outer=circle(r),holes=groove.holes) for z,r in ((0,10),(4,8),(8,10))]
        self.assertNotIn(0,cad_export.circular_walls(groove))
        self.assertIn(1,cad_export.circular_walls(groove))

    def test_frames_are_rigid_before_curves_are_promoted(self):
        rigid=((12,5,7),(0,1,0),(0,0,1),(1,0,0))
        self.assertEqual(len(cad_export.circular_walls(self.tube(frame=rigid))),2)
        self.assertEqual(cad_export.circular_walls(self.tube(axis_x=True))[0]['axis'],(1,0,0))
        for basis in (((2,0,0),(0,2,0),(0,0,2)),((1,0,0),(.5,1,0),(0,0,1)),((-1,0,0),(0,1,0),(0,0,1))):
            self.assertFalse(cad_export.circular_walls(self.tube(frame=((0,0,0),*basis))))

    def test_cylinder_volume_difference_and_wall_error_are_explicit(self):
        tube=self.tube()
        text,info=cad_export.document([tube])
        self.assertAlmostEqual(info[0]['cad_volume_mm3'],math.pi*(100-9)*8,places=8)
        self.assertGreater(info[0]['volume_difference_mm3'],0)
        self.assertEqual(text.count('CYLINDRICAL_SURFACE'),2)
        self.assertEqual(text.count('ADVANCED_FACE'),4)
        helical=cad_export.document(generate('helical').parts)[1][0]
        hole=helical['circular_walls'][0]
        self.assertGreater(hole['max_wall_radial_difference_mm'],hole['max_section_radial_difference_mm'])
        self.assertAlmostEqual(helical['sampled_volume_mm3']+helical['volume_difference_mm3'],helical['cad_volume_mm3'])

    def test_step_graph_units_names_and_distinct_bodies(self):
        tube=self.tube();tube.name="Ruota Ø #5 'rear'"
        text,metadata=cad_export.document([tube,self.tube(center=(30,0))])
        self.assertIn('SHAPE_DEFINITION_REPRESENTATION',text)
        self.assertIn('PRODUCT_DEFINITION_SHAPE',text)
        self.assertIn('SI_UNIT(.MILLI.,.METRE.)',text)
        self.assertIn('\\X2\\00D8\\X0\\',text)
        self.assertIn("''rear''",text)
        self.assertEqual(text.count('MANIFOLD_SOLID_BREP('),2)
        self.assertEqual(len(metadata),2)
        definitions={int(n) for n in re.findall(r'^#(\d+)=',text,re.M)}
        # References are all reachable entity IDs, excluding quoted name #5.
        self.assertTrue(all(int(n) in definitions for n in re.findall(r'#(\d+)',text)))

    def test_all_catalog_variants_have_complete_step_documents(self):
        for family in FAMILIES:
            for variant in list(VARIANTS.get(family,{})) or [None]:
                with self.subTest(family=family,variant=variant):
                    d=generate(family,dict(variant=variant) if variant else {})
                    text,info=cad_export.document(d.parts)
                    self.assertEqual(len(info),len(d.parts))
                    self.assertEqual(text.count('FACETED_BREP(')+text.count('MANIFOLD_SOLID_BREP('),len(d.parts))
                    self.assertTrue(all(p['cad_volume_mm3']>0 for p in info))

    def test_step_export_is_atomic_for_invalid_later_component(self):
        d=Design('spur',{},[self.tube(),Part('bad',[(0,0),(1,0),(2,0)])])
        with TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/'cad'
            with self.assertRaises(ValueError):cad_export.export(d,target)
            self.assertFalse(list(root.iterdir()))
            target.mkdir();(target/'valid.step').write_text('valid')
            with self.assertRaises(FileExistsError):cad_export.export(d,target)
            self.assertEqual((target/'valid.step').read_text(),'valid')
            self.assertEqual(list(root.iterdir()),[target])

    def test_failed_direct_write_preserves_valid_file(self):
        with TemporaryDirectory() as temporary:
            target=Path(temporary)/'valid.step';target.write_text('valid')
            with self.assertRaises(UnicodeEncodeError):write_text(target,'invalid Ω','ascii')
            self.assertEqual(target.read_text(),'valid')
            self.assertEqual(list(target.parent.iterdir()),[target])


class ProfileAndPackageTests(unittest.TestCase):
    def test_svg_dxf_units_closed_contours_holes_and_placement(self):
        d=Design('spur',{},[Part('Plate',circle(10),[circle(2,center=(3,0))],width=6,center=(50,20),z=3)])
        with TemporaryDirectory() as temporary:
            folder,info=profile_export.export(d,Path(temporary)/'profiles')
            component=info['components'][0];self.assertTrue(component['extrudible'])
            self.assertEqual(component['center_mm'],[50,20])
            record=component['profiles'][0];self.assertEqual(record['holes'],1)
            root=ET.parse(folder/record['svg']).getroot()
            self.assertTrue(root.attrib['width'].endswith('mm'))
            path=root.find('{http://www.w3.org/2000/svg}path')
            self.assertEqual(path.attrib['fill-rule'],'evenodd')
            self.assertEqual(path.attrib['d'].count(' Z'),2)
            drawing=(folder/record['dxf']).read_text()
            self.assertIn('$INSUNITS\n70\n4\n',drawing)
            self.assertEqual(drawing.count('LWPOLYLINE'),2)
            self.assertIn('\nHOLES\n',drawing)
            self.assertEqual(drawing.count('\n70\n1\n38\n0\n'),2)

    def test_helices_and_deformed_profiles_cannot_be_mislabeled_extrusions(self):
        for family,variant in (('helical',None),('double','separated'),('harmonic','cup'),('worm','zi')):
            with self.subTest(family=family),TemporaryDirectory() as temporary:
                d=generate(family,dict(variant=variant) if variant else {})
                _,metadata=profile_export.export(d,Path(temporary)/'profiles')
                self.assertTrue(any(not p['extrudible'] for p in metadata['components']))
                for p in metadata['components']:
                    if not p['extrudible']:self.assertIn('not an extrusion',p['kind'])
                    self.assertTrue(p['profiles'])

    def test_complete_package_manifest_and_portable_asset_paths(self):
        d=generate('helical');config=dict(format='solidcraft-riduttori/1',family=d.family,parameters=d.values)
        with TemporaryDirectory() as temporary:
            package=package_export.export(d,config,Path(temporary)/'package',PNG)
            manifest=json.loads((package/'manifest.json').read_text())
            self.assertTrue(manifest['complete'])
            self.assertEqual(json.loads((package/'model.config.json').read_text()),config)
            self.assertEqual((package/'preview.png').read_bytes(),PNG)
            for entry in manifest['files']:
                data=(package/entry['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'])
            commands=json.loads((package/'model.script.json').read_text())['commands']
            paths=[c['params']['path'] for c in commands if c['command']=='file.insert_step']
            self.assertTrue(paths)
            self.assertTrue(all(not Path(p).is_absolute() and (package/p).is_file() for p in paths))
            self.assertEqual(len(list((package/'step-parts').glob('*.step'))),len(d.parts))

    def test_package_failure_at_reports_stage_does_not_publish_or_overwrite(self):
        d=generate('helical')
        with TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/'package'
            with patch('package_export.bom.export',side_effect=OSError('Disk full')):
                with self.assertRaises(OSError):package_export.export(d,{},target,PNG)
            self.assertFalse(list(root.iterdir()))
            target.mkdir();(target/'keep').write_text('valid')
            with patch('package_export.bom.export',side_effect=OSError('Disk full')):
                with self.assertRaises(FileExistsError):package_export.export(d,{},target,PNG)
            self.assertEqual((target/'keep').read_text(),'valid')
            self.assertEqual(list(root.iterdir()),[target])

    def test_missing_preview_and_concurrent_writer_never_publish(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/'package'
            with self.assertRaises(ValueError):package_export.export(generate('spur'),{},target,b'bad')
            with self.assertRaises(ValueError):profile_export.export(Design('spur',{}),target)
            self.assertFalse(list(root.iterdir()))
            with directory(target) as staging:
                (staging/'keep').write_text('valid')
                with self.assertRaises(FileExistsError):
                    with directory(target):self.fail('Concurrent reservation was bypassed')
            self.assertEqual((target/'keep').read_text(),'valid')
            self.assertEqual(list(root.iterdir()),[target])

    def test_stl_failure_and_existing_parts_preserve_previous_export(self):
        with TemporaryDirectory() as temporary:
            stem=Path(temporary)/'model'
            old=generate('spur');assembly,parts=stl_export.export(old,stem)
            data=assembly.read_bytes();part_data=[p.read_bytes() for p in parts]
            with self.assertRaises(FileExistsError):stl_export.export(generate('helical'),stem)
            self.assertEqual(assembly.read_bytes(),data)
            self.assertEqual([p.read_bytes() for p in parts],part_data)
        with TemporaryDirectory() as temporary:
            d=Design('spur',{},[Part('Good',circle(2)),Part('Bad',[(0,0),(1,0),(2,0)])])
            with self.assertRaises(ValueError):stl_export.export(d,Path(temporary)/'model')
            self.assertFalse(list(Path(temporary).iterdir()))


if __name__=='__main__':unittest.main()
