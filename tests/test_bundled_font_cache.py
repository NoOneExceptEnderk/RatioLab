# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""A real upgrade must discover added fonts with an existing normalized-time cache."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('font_bundle_support',ROOT/'packaging/bundle_support.py')
support = importlib.util.module_from_spec(spec);spec.loader.exec_module(support)


class BundledFontCacheTests(unittest.TestCase):
    def test_salt_depends_on_font_content_and_names_but_not_timestamps(self):
        with TemporaryDirectory() as folder:
            root = Path(folder);fonts = root/'fonts';fonts.mkdir()
            font = fonts/'one.ttf';font.write_bytes(b'font-v1')
            template = ROOT/'packaging/fonts.conf';output = root/'fonts.conf'
            support.write_font_config(fonts,template,output);initial = output.read_bytes()
            os.utime(font,(0,0));os.utime(fonts,(0,0))
            support.write_font_config(fonts,template,output);self.assertEqual(output.read_bytes(),initial)
            font.write_bytes(b'font-v2');support.write_font_config(fonts,template,output)
            self.assertNotEqual(output.read_bytes(),initial)
            font.write_bytes(b'font-v1');font.rename(fonts/'renamed.ttf')
            support.write_font_config(fonts,template,output);self.assertNotEqual(output.read_bytes(),initial)

    @unittest.skipUnless(shutil.which('fc-list') and shutil.which('fc-match'),'Fontconfig tools required')
    def test_upgrade_at_same_path_and_epoch_mtime_discovers_chinese_and_tamil(self):
        with TemporaryDirectory() as folder:
            root = Path(folder);fonts = root/'runtime/share/fonts';fonts.mkdir(parents=True)
            config = root/'runtime/etc/fonts/fonts.conf';config.parent.mkdir(parents=True)
            cache = root/'cache'
            source = ROOT/'packaging/fonts'
            for path in source.glob('DejaVu*.ttf'):
                shutil.copyfile(path,fonts/path.name);os.utime(fonts/path.name,(0,0))
            os.utime(fonts,(0,0))
            old = (ROOT/'packaging/fonts.conf').read_text().replace(' salt="@FONT_SET_SHA256@"','')
            config.write_text(old)
            env = dict(os.environ,FONTCONFIG_FILE=str(config),FONTCONFIG_PATH=str(config.parent),XDG_CACHE_HOME=str(cache))
            def run(*args):
                return subprocess.run(args,env=env,check=True,capture_output=True,text=True,timeout=30).stdout
            before = run('fc-list','-f','%{family}\\n')
            self.assertNotIn('Noto',before)
            cached = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in cache.rglob('*') if p.is_file()}
            self.assertTrue(cached,'The regression must start with a real old cache')
            for path in source.glob('Noto*'):
                if path.suffix not in ('.ttf','.ttc'):continue
                shutil.copyfile(path,fonts/path.name);os.utime(fonts/path.name,(0,0))
            os.utime(fonts,(0,0))
            # The unsalted previous config reproduces the installed defect.
            self.assertNotIn('Noto',run('fc-list','-f','%{family}\\n'))
            support.write_font_config(fonts,ROOT/'packaging/fonts.conf',config)
            families = run('fc-list','-f','%{family}\\n')
            self.assertIn('Noto Sans CJK SC',families)
            self.assertIn('Noto Sans Tamil',families)
            self.assertIn('Noto',run('fc-match','-f','%{family}', 'sans-serif:lang=zh-cn:charset=4e2d'))
            self.assertIn('Tamil',run('fc-match','-f','%{family}', 'sans-serif:lang=ta:charset=0ba4'))
            # No deleting or overwriting existing unrelated font-cache entries.
            after = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in cache.rglob('*') if p.is_file()}
            for name,digest in cached.items():self.assertEqual(after[name],digest)


if __name__ == '__main__':unittest.main()
