# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native/browser scope identity and archive inventory against actual writers."""
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'webapp'))
import engine_bridge
import selected_export


class ExportScopeTests(unittest.TestCase):
    def test_native_and_browser_keep_identical_component_identity_and_files(self):
        for family in ('helical', 'planetary', 'harmonic'):
            engine=engine_bridge.Engine()
            model=engine.call('generate',dict(family=family,parameters={}))
            original=engine.design
            indices=sorted({0,len(original.parts)-1})
            expected=[dict(source_index=i+1,name=original.parts[i].name) for i in indices]
            for kind in ('step','stl','profiles'):
                with self.subTest(family=family,kind=kind), TemporaryDirectory() as temporary:
                    target=selected_export.export(original,indices,kind,Path(temporary)/'selected',revision=model['design_id'])
                    result=engine.call('export',dict(design_id=model['design_id'],kind=kind,indices=indices))
                    self.assertEqual(result['component_count'],len(indices))
                    self.assertEqual(result['scope']['components'],expected)
                    self.assertIs(engine.design,original)
                    with ZipFile(BytesIO(engine.buffers[result['buffer']])) as archive:
                        self.assertEqual(result['files'],sorted(archive.namelist()))
                        selection=json.loads(archive.read('selection.json'))
                        self.assertEqual(selection['components'],expected)
                        self.assertEqual(json.loads((target/'selection.json').read_text())['components'],expected)
                        if kind=='step':
                            native=json.loads((target/'step-info.json').read_text())
                            browser=json.loads(archive.read('step-info.json'))
                            self.assertEqual(native['components'],browser['components'])
                            self.assertEqual(len([n for n in archive.namelist() if n.startswith('step-parts/') and n.endswith('.step')]),len(indices))
                        if kind=='profiles':
                            self.assertEqual(json.loads((target/'profiles.json').read_text()),json.loads(archive.read('profiles.json')))
                        if kind=='stl':
                            self.assertEqual(len(list(target.rglob('*.stl'))),len(indices)+1)
                            self.assertEqual(len([n for n in archive.namelist() if n.endswith('.stl')]),len(indices)+1)
            for indices in ([],[len(original.parts)],[-1]):
                with self.assertRaises(ValueError):engine.call('export',dict(design_id=model['design_id'],kind='step',indices=indices))
            with self.assertRaises(engine_bridge.BridgeError):
                engine.call('export',dict(design_id=model['design_id'],kind='project',indices=[0]))


if __name__=='__main__':unittest.main()
