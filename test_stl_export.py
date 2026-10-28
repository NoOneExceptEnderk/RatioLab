# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""STL: fori aperti, superficie chiusa, volume e coordinate di montaggio."""
import struct
import tempfile
import unittest
from pathlib import Path
from geometry import FAMILIES, VARIANTS, generate, Part
from solid_geometry import signature
from stl_export import triangles, export, write_stl

class StlExportTests(unittest.TestCase):

    def assert_solid(self, part):
        edges = {}
        volume = 0.0
        for a, b, c in triangles(part):
            for x, y in ((a, b), (b, c), (c, a)):
                key = tuple(sorted((x, y)))
                count, balance = edges.get(key, (0, 0))
                edges[key] = (count + 1, balance + (1 if (x, y) == key else -1))
            volume += sum((a[i] * (b[(i + 1) % 3] * c[(i + 2) % 3] - b[(i + 2) % 3] * c[(i + 1) % 3]) for i in range(3))) / 6
        self.assertTrue(edges)
        self.assertTrue(all((n == 2 and balance == 0 for n, balance in edges.values())), part.name)
        expected = signature(part)['volume_mm3']
        self.assertAlmostEqual(volume / expected, 1.0, places=7, msg=part.name)

    def test_all_default_families_and_variants(self):
        for family in FAMILIES:
            for variant in list(VARIANTS.get(family, {})) or [None]:
                design = generate(family, {'variant': variant} if variant else {})
                for part in design.parts:
                    with self.subTest(family=family, variant=variant, part=part.name):
                        self.assert_solid(part)

    def test_catalog_hardware_and_multiple_holes(self):
        for family in ('double', 'planetary', 'cycloidal'):
            d = generate(family, {'bearing_mode': 'gear' if family == 'cycloidal' else 'shaft', 'hardware_mode': 'standard'})
            for part in d.parts:
                with self.subTest(family=family, part=part.name):
                    self.assert_solid(part)

    def test_binary_files_and_assembly_coordinates(self):
        d = generate('planetary')
        with tempfile.TemporaryDirectory() as folder:
            assembly, parts = export(d, Path(folder) / 'planetary')
            self.assertEqual(len(parts), len(d.parts))
            total = 0
            for part, path in zip(d.parts, parts):
                data = path.read_bytes()
                count = struct.unpack_from('<I', data, 80)[0]
                self.assertEqual(len(data), 84 + 50 * count)
                coords = []
                for i in range(count):
                    row = struct.unpack_from('<12fH', data, 84 + 50 * i)
                    self.assertAlmostEqual(sum((n * n for n in row[:3])), 1.0, places=5)
                    coords.extend((row[3:6], row[6:9], row[9:12]))
                expected = signature(part)
                for axis in range(3):
                    self.assertAlmostEqual(min((p[axis] for p in coords)), expected['min'][axis], places=4)
                    self.assertAlmostEqual(max((p[axis] for p in coords)), expected['max'][axis], places=4)
                total += count
            data = assembly.read_bytes()
            self.assertEqual(struct.unpack_from('<I', data, 80)[0], total)
            self.assertEqual(len(data), 84 + 50 * total)

    def test_failed_export_cleans_incomplete_file(self):
        invalid = Part('invalid', [(0, 0), (1, 0), (2, 0)])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'part.stl'
            with self.assertRaises(ValueError):
                write_stl(path, [invalid])
            self.assertFalse(path.exists())
            self.assertFalse(list(Path(folder).glob('*.tmp')))
if __name__ == '__main__':
    unittest.main()
