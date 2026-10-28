"""Independent geometric expectations and subset/publication regressions."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib,json,math,struct,unittest
from geometry import Design,Part,circle,generate,profile_sections,section_holes
from solid_geometry import faces,point
from motion import build_plan,rotation,transform
import component_geometry as cg
import selected_export as se
import bom


def model():
    d=Design('spur',generate('spur').values,[Part('same',circle(10),[circle(3)],width=4),Part('same',circle(10),[],width=2,z=-5),Part('housing',circle(15),[circle(11)],width=10,role='housing')])
    d.analysis=deepcopy(generate('spur').analysis)
    return d


class ComponentTests(unittest.TestCase):
    def test_ray_frontmost_hole_empty_section_frame_and_pose(self):
        d=model();surfaces=[(i,cg.triangles(p)) for i,p in enumerate(d.parts)]
        hit=cg.pick((0,0,20),(0,0,-1),surfaces)
        self.assertEqual(hit[0],1);self.assertAlmostEqual(hit[1][2],-3)
        hit=cg.pick((5,0,20),(0,0,-1),surfaces)
        self.assertEqual(hit[0],0);self.assertAlmostEqual(hit[1][2],4)
        self.assertIsNone(cg.pick((20,0,20),(0,0,-1),surfaces))
        self.assertIsNone(cg.pick((5,0,20),(0,0,-1),surfaces,max_distance=10))
        self.assertIsNone(cg.pick((5,5,20),(0,0,-1),surfaces,section_y=0))
        p=Part('rotated',circle(10),[circle(3)],width=4,frame=((20,0,0),(0,1,0),(0,0,1),(1,0,0)))
        self.assertAlmostEqual(cg.pick((30,5,0),(-1,0,0),[(7,cg.triangles(p))])[1][0],24)
        self.assertIsNone(cg.pick((30,0,0),(-1,0,0),[(7,cg.triangles(p))]))
        from motion import MotionPlan
        plan=MotionPlan(poses={0:lambda _:rotation(math.pi/2,axis=(0,1,0))})
        ts=cg.posed(cg.triangles(d.parts[0]),plan,0,0)
        self.assertAlmostEqual(cg.pick((30,5,0),(-1,0,0),[(0,ts)])[1][0],4)

    def test_camera_inverse_projection_and_legacy_axis_explosion(self):
        for yaw,tilt in [(0,0),(.7,-1.2),(-2.1,2)]:
            q=(7,-3,5);center=(2,1,-1)
            xy=cg.project(q,center,20,1.2,yaw,tilt,800,500)
            origin,direction=cg.ray(*xy,center,20,1.2,yaw,tilt,800,500)
            # A ray through a known projected point must be collinear in 3D.
            delta=tuple(q[i]-origin[i] for i in range(3))
            from collision_geometry import cross
            self.assertLess(sum(x*x for x in cross(delta,direction)),1e-22)
        d=model();d.parts[0].axis_x=True
        for exploded in (False,True):
            p=cg.displayed_part(d,0,exploded);a=cg.dimensions(p)
            expected=[point(p,(x,y),z,0) for z in (0,4) for x,y in [(10,0),(-10,0),(0,10),(0,-10)]]
            for i in range(3):self.assertAlmostEqual(a['min_mm'][i],min(q[i] for q in expected));self.assertAlmostEqual(a['max_mm'][i],max(q[i] for q in expected))

    def test_subset_exact_indices_duplicates_all_formats_bom_and_manifest(self):
        d=model();before=deepcopy(d)
        with TemporaryDirectory() as temp:
            for kind in ('step','stl','profiles'):
                target=se.export(d,[1],kind,Path(temp)/kind,revision=('identity',12))
                scope=json.loads((target/'selection.json').read_text());self.assertEqual(scope['source_indices'],[2]);self.assertFalse(scope['complete_assembly'])
                bill=json.loads((target/'selected.bom.json').read_text());self.assertEqual(sum(r['quantity'] for r in bill['rows']),1);self.assertEqual(bill['rows'][0]['source_indices'],[2])
                self.assertIn('SELECTED COMPONENTS ONLY',(target/'selected.calcoli.txt').read_text())
                manifest=json.loads((target/'manifest.json').read_text())
                for entry in manifest['files']:self.assertEqual(hashlib.sha256((target/entry['path']).read_bytes()).hexdigest(),entry['sha256'])
                if kind=='step':
                    info=json.loads((target/'step-info.json').read_text());self.assertEqual([p['index'] for p in info['components']],[2]);self.assertEqual(len(list((target/'step-parts').glob('002-*.step'))),1)
                elif kind=='profiles':self.assertEqual([p['index'] for p in json.loads((target/'profiles.json').read_text())['components']],[2])
                else:
                    self.assertEqual(len(list((target/'selected.stl-parts').glob('002-*.stl'))),1)
                    raw=(target/'selected.stl').read_bytes();count=struct.unpack_from('<I',raw,80)[0];self.assertEqual(len(raw),84+50*count)
                    zs=[struct.unpack_from('<12fH',raw,84+50*j)[k] for j in range(count) for k in (5,8,11)]
                    self.assertEqual((min(zs),max(zs)),(-5,-3))
        self.assertEqual(d,before)
        self.assertEqual(se.subset(se.subset(d,[1,2]),[0]).source_indices,[2])
        for indices in ([],[3],[-1],['a',0]):
            with self.assertRaises(ValueError):se.subset(d,indices)

    def test_selected_package_atomic_script_and_failure(self):
        d=model();png=b'\x89PNG\r\n\x1a\nIEND\xaeB`\x82'
        with TemporaryDirectory() as temp:
            root=Path(temp);target=se.export(d,[0,1],'package',root/'package',dict(format='solidcraft-riduttori/1',family=d.family,parameters=d.values),png,('id',1))
            m=json.loads((target/'manifest.json').read_text());self.assertEqual(m['components'],2);self.assertFalse(m['complete_assembly'])
            script=json.loads((target/'model.script.json').read_text());metadata=[c['params'] for c in script['commands'] if c['command']=='component.metadata.set' and 'part_number' in c['params']]
            self.assertEqual([c['values']['local.ratiolab.selection']['source_index'] for c in metadata],[1,2])
            self.assertEqual(len({c['component'] for c in metadata}),2)
            for c in script['commands']:
                if c['command']=='file.insert_step':self.assertTrue((target/c['params']['path']).is_file());self.assertFalse(Path(c['params']['path']).is_absolute())
            self.assertIn('not a complete assembly',(target/'README.txt').read_text())
            with patch('profile_export.write_files',side_effect=RuntimeError('injected')):
                with self.assertRaises(RuntimeError):se.export(d,[0],'package',root/'failed',{},png)
            self.assertFalse((root/'failed').exists())

    def test_fixed_axis_supports_geometry_and_machining_motion_forward_reverse(self):
        for family in ('parallel','internal'):
            for variant in ('spur','helical','double'):
                for reverse in (False,True):
                    d=generate(family,dict(variant=variant,io_scheme='reverse' if reverse else 'forward',bearing_mode='shaft',hardware_mode='standard',hardware_bolts=False))
                    bearings=[p for p in d.parts if p.catalog_code];self.assertEqual(len(bearings),4 if family=='parallel' else 2)
                    plan=build_plan(d)
                    for i,p in enumerate(d.parts):
                        if p.port.get('member') in ('A','B') and p.procurement:
                            q=point(p,p.outer[0],0,0);pivot=(*p.center,0);angle=.4*p.port['rpm']/plan.reference_rpm
                            expected=transform(rotation(angle,pivot=pivot),q);actual=transform(plan.matrix(i,.4),q)
                            for a,b in zip(expected,actual):self.assertAlmostEqual(a,b,places=9)
                    for bearing in bearings:
                        host=next(p for p in d.parts if p.name.startswith('BearingBlock') and p.center==bearing.center and p.z<=bearing.z<=p.z+p.width)
                        self.assertTrue(any(op['type']=='groove_internal' for op in host.machining))
                        # Groove enlarges a local section of the actual shared surface.
                        hole_radii=[max(math.hypot(x,y) for x,y in s['holes'][0]) for s in host.stations]
                        self.assertGreater(max(hole_radii),min(hole_radii))
                        self.assertEqual(plan.matrix(d.parts.index(bearing),.4),plan.matrix(d.parts.index(host),.4))
                    shafts=[p for p in d.parts if p.name in ('Shaft_input','Shaft_output','Shaft_lato_A','Shaft_lato_B')]
                    for shaft in shafts:
                        self.assertTrue(any(o['type']=='keyway_shaft' for o in shaft.machining));self.assertTrue(any(o['type']=='groove_external' for o in shaft.machining));self.assertTrue(shaft.stations)
                    if family=='internal':self.assertIn('pinion shaft only',d.analysis['fixed_axis_supports']['scope'])

    def test_explicitly_unavailable_backend_options(self):
        for family in ('parallel','internal'):
            with self.assertRaisesRegex(ValueError,'Bearing-in-bore'):generate(family,dict(bearing_mode='gear'))
            with self.assertRaisesRegex(ValueError,'independent bearing blocks'):generate(family,dict(hardware_mode='standard',hardware_bolts=True))
        for family in ('worm','harmonic'):
            with self.assertRaises(ValueError):generate(family,dict(bearing_mode='shaft'))
            with self.assertRaises(ValueError):generate(family,dict(hardware_mode='standard'))

if __name__=='__main__':unittest.main()
