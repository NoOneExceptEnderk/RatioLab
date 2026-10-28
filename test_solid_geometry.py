"""Il solido trasferito deve avere esattamente le facce visibili nella preview."""
import unittest, tempfile, json
from pathlib import Path
from array import array
from geometry import generate, Design
from solid_geometry import faces, signature, section_loops
from preview3d import build_scene

class SharedSolidTests(unittest.TestCase):

    def test_closed_oriented_solid_for_twisted_parts(self):
        cases = [('double', {}), ('double', {'gap': 0}), ('double', {'helix': -35, 'gap': 2}), ('planetary', {'variant': 'two_stage_double'}), ('helical', {}), ('worm', {})]
        for family, values in cases:
            for p in generate(family, values).parts:
                if p.double or abs(p.twist) > 1e-08:
                    with self.subTest(family=family, part=p.name, values=values):
                        info = signature(p)
                        self.assertGreater(info['volume_mm3'], 0)
                        self.assertGreater(info['faces'], 2)

    def test_preview_side_triangles_equal_step_faces_bit_for_bit(self):
        for family, values in [('double', {}), ('planetary', {'variant': 'double'}), ('helical', {}), ('worm', {}), ('worm', {'variant': 'zi', 'worm_hand': -1, 'length': 12}), ('harmonic', {'variant': 'hat'})]:
            d = generate(family, values)
            for p in d.parts:
                if not (p.stations or p.double or abs(p.twist) > 1e-08):
                    continue
                with self.subTest(family=family, part=p.name):
                    scene = build_scene(Design(family, d.values, [p]), True, True)
                    start, count = scene.parts[0].side
                    actual = array('f', [scene.vertices[6 * i + j] for i in range(start, start + count) for j in range(3)])
                    expected = array('f', [v for face in faces(p)[:-2] for point in face[0] for v in point])
                    self.assertEqual(actual, expected)

    def test_export_resources_and_explicit_planes(self):
        d = generate('double')
        with tempfile.TemporaryDirectory() as folder:
            d.prepare_assets(folder)
            cmd = d.commands(folder)
            imports = [c for c in cmd if c['command'] == 'file.insert_step']
            self.assertEqual(len(imports), 1)
            step = Path(imports[0]['params']['path']).read_text()
            self.assertIn('FACETED_BREP', step)
            self.assertFalse("=FACE(''," in step)
            self.assertEqual(step.count('FACE_SURFACE('), signature(d.parts[0])['faces'])
            self.assertFalse(any((c['command'] in ('solid.loft', 'solid.sweep', 'solid.combine') for c in cmd)))
            json.dumps(cmd, allow_nan=False)

    def test_flat_parts_retain_native_extrusions(self):
        cmds = generate('spur').commands()
        self.assertTrue(any((c['command'] == 'solid.extrude' for c in cmds)))
        self.assertFalse(any((c['command'] == 'file.insert_step' for c in cmds)))
if __name__ == '__main__':
    unittest.main()
