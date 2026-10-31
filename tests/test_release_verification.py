# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Release gates must accept current payloads and reject incomplete or extra data."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


artifacts=load('release_artifacts_test',ROOT/'scripts/verify-artifacts.py')
mcp=load('release_mcp_test',ROOT/'scripts/check-installed-mcp.py')


class CatalogVerificationTests(unittest.TestCase):
    def test_mcp_requires_the_exact_current_family_inventory(self):
        from geometry import FAMILIES
        self.assertEqual(mcp.EXPECTED_FAMILIES,set(FAMILIES))
        rows=[dict(id=key) for key in FAMILIES]
        mcp.verify_families(rows);mcp.verify_families(list(reversed(rows)))
        for invalid in [None,{},rows[:-1],rows[:-1]+[rows[0]],rows[:-1]+[dict(id='unknown')],
                        rows+[dict(id='extra')],rows[:-1]+[dict(id=None)]]:
            with self.subTest(invalid=invalid),self.assertRaises(RuntimeError):mcp.verify_families(invalid)

    def test_previous_ten_family_runtime_and_duplicate_wolfrom_are_rejected(self):
        from geometry import FAMILIES
        current = [dict(id=key) for key in FAMILIES]
        previous = [row for row in current if row['id'] != 'wolfrom']
        self.assertEqual(len(previous), 10)
        for rows in (previous, current+[dict(id='wolfrom')],
                     [row for row in current if row['id'] != 'spur']+[dict(id='wolfrom')]):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                mcp.verify_families(rows)


class ArtifactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)/'source';self.root.mkdir()
        self.out=Path(self.directory.name)/'artifacts';self.out.mkdir()
        sources={'pyproject.toml':'[tool.setuptools]\npy-modules=["fixture"]\n',
                 'src/fixture.py':'VALUE=1\n','src/ratiolab_resources/__init__.py':'',
                 'src/ratiolab_resources/version.json':'{"release":"1.2.3"}\n',
                 'LICENSE':'test GPL notice','COPYRIGHT':'test copyright',
                 'CHANGELOG.md':'# Changelog\n\n## 1.2.3\n\nFixture change.\n',
                 'docs/installation.md':'fixture installation','docs/mcp.md':'fixture MCP',
                 'docs/development.md':'fixture development','CONTRIBUTING.md':'fixture contributing',
                 'build-support/ratiolab_build.py':'# fixture build helper',
                 'packaging/mcp_entrypoint.py':'# fixture entrypoint',
                 'scripts/check-installed-mcp.py':'# fixture verifier'}
        for name in ('DejaVuSans.ttf','DejaVuSansMono.ttf','DejaVuSans-Bold.ttf',
                     'LICENSE-DejaVu.txt','AUTHORS-DejaVu.txt','SOURCE.json'):
            sources['packaging/fonts/'+name]='fixture font asset'
        for name,body in sources.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body.encode('utf-8'))
        self.payload={'fixture.py':sources['src/fixture.py'],
                      'ratiolab_resources/__init__.py':'',
                      'ratiolab_resources/version.json':sources['src/ratiolab_resources/version.json'],
                      'fixture-1.2.3.dist-info/METADATA':'License-Expression: GPL-3.0-only\n'}
        for source,destination in [('LICENSE','LICENSE'),('COPYRIGHT','COPYRIGHT'),
                                   ('docs/installation.md','INSTALL.md'),('docs/mcp.md','MCP.md'),
                                   ('CHANGELOG.md','CHANGELOG.md')]:
            self.payload['ratiolab_resources/'+destination]=sources[source]
        for name in ('LICENSE','COPYRIGHT'):self.payload['fixture-1.2.3.dist-info/licenses/'+name]=sources[name]
        with tarfile.open(self.out/'fixture-1.2.3.tar.gz','w:gz') as archive:
            for name,body in sources.items():
                data=body.encode();member=tarfile.TarInfo('fixture-1.2.3/'+name);member.size=len(data)
                archive.addfile(member,io.BytesIO(data))

    def verify(self,payload=None):
        with zipfile.ZipFile(self.out/'fixture-1.2.3-py3-none-any.whl','w') as archive:
            for name,body in (self.payload if payload is None else payload).items():archive.writestr(name,body)
        with patch.object(artifacts,'__file__',str(self.root/'scripts/verify-artifacts.py')),patch('builtins.print'):
            artifacts.verify(self.out)

    def test_packaged_changelog_is_required_and_compared_to_source(self):
        self.verify()
        missing=dict(self.payload);missing.pop('ratiolab_resources/CHANGELOG.md')
        with self.assertRaisesRegex(AssertionError,'missing'):self.verify(missing)
        stale=dict(self.payload,**{'ratiolab_resources/CHANGELOG.md':'old changelog'})
        with self.assertRaisesRegex(AssertionError,'CHANGELOG.md'):self.verify(stale)

    def test_extra_resources_and_private_update_state_remain_rejected(self):
        for name in ('ratiolab_resources/surplus.md','ratiolab_resources/updates.json','updates.json'):
            payload=dict(self.payload);payload[name]='{}'
            with self.subTest(name=name),self.assertRaises(AssertionError):self.verify(payload)


if __name__=='__main__':unittest.main()
