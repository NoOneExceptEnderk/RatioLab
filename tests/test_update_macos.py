# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Execute the actual Mac shell transaction with harmless fixed-tool fixtures."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import update_install
import update_macos
import update_receipt
from update_download import VerifiedDownload
from updates import Release, RELEASES_URL


@unittest.skipUnless(sys.platform.startswith('linux'),'Nonprivileged Linux command fixtures')
class MacUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="ratiolab mac user's fixtures ")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.home=self.root/'home';self.app=self.home/'Applications/RatioLab.app'
        self.image=self.root/'image';self.image.mkdir()
        self.opened=self.root/'opened.json'
        self.config=self.root/'config';self.config.mkdir()
        self.state=self.config/'state';self.state.write_text('S')
        self.calls=self.root/'system-calls.jsonl'
        self.cache=self.root/'cache'
        self.helpers=[];self.children=[]
        self.make_app(self.app,'0.1.11')
        self.make_app(self.image/'RatioLab.app','0.1.12')
        job=self.root/'download';job.mkdir(mode=0o700)
        name='RatioLab-0.1.12-macos-arm64.dmg';path=job/name;path.write_bytes(b'harmless fixture image')
        base=RELEASES_URL+'/download/v0.1.12/'
        release=Release('0.1.12',RELEASES_URL+'/tag/v0.1.12','',base+name,name,path.stat().st_size,base+'SHA256SUMS')
        info=job.stat();self.download=VerifiedDownload(path,hashlib.sha256(path.read_bytes()).hexdigest(),release,
                                                     job,(info.st_dev,info.st_ino))
        self.tools=self.make_tools()
        self.home_patch=patch.object(Path,'home',return_value=self.home);self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def tearDown(self):
        for helper in self.helpers:helper.cancel()
        for helper in self.helpers:
            try:helper._process.wait(timeout=5)
            except subprocess.TimeoutExpired:helper._process.kill();helper._process.wait(timeout=3)
        for child in self.children:
            if child.poll() is None:child.terminate()
            child.wait(timeout=3)

    def make_app(self,path,version,*,runtime_version=None,arch='arm64',signature=True):
        binary=path/'Contents/MacOS/RatioLab';binary.parent.mkdir(parents=True)
        info=dict(CFBundleIdentifier='local.solidcraft.reducers',CFBundleExecutable='RatioLab',
                  CFBundleShortVersionString=version)
        (path/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        (path/'Contents/arch').write_text(arch)
        (path/'Contents/signature').write_text('valid' if signature else 'invalid')
        runtime_version=runtime_version or version
        binary.write_text('#!/bin/sh\noption=${1:-}\nreport=${3:-}\ncase "$option" in\n'
            +f'--version) printf "%s\\n" {shlex.quote("RatioLab "+runtime_version)} > "$report" ;;\n'
            +f'--self-test) test ! -f {shlex.quote(str(self.config/"selftest-fails"))} || exit 7; printf "{{}}" > "$report" ;;\n'
            +'--diagnose) '
            +f'if [ "$0" = {shlex.quote(str(self.app/"Contents/MacOS/RatioLab"))} ] && '
            +f'[ {shlex.quote(runtime_version)} = 0.1.12 ] && [ -f {shlex.quote(str(self.config/"final-fails"))} ]; then exit 8; fi; '
            +'printf "{}" > "$report" ;;\n*) exit 0 ;;\nesac\n')
        binary.chmod(0o700)

    def make_tools(self):
        directory=self.root/'tools';directory.mkdir()
        # One fixture dispatcher receives the fixed command's basename. No real
        # disk image, signature service, LaunchServices, or privileged action runs.
        dispatcher=directory/'dispatch.py'
        dispatcher.write_text('''import json, os, pathlib, plistlib, shutil, subprocess, sys
root=pathlib.Path(sys.argv[1]);command=sys.argv[2];args=sys.argv[3:]
config=root/'config';app=root/'home/Applications/RatioLab.app'
with (root/'system-calls.jsonl').open('a') as stream:stream.write(json.dumps([command,*args])+'\\n')
if command=='ps':
    try:os.kill(int(args[args.index('-p')+1]),0)
    except ProcessLookupError:raise SystemExit(1)
    print('Sat Oct 31 00:00:00 2026 '+(config/'state').read_text().strip())
elif command=='stat':
    path=pathlib.Path(args[-1]);info=path.stat()
    print(str(info.st_size) if args[1]=='%z' else str(info.st_dev)+':'+str(info.st_ino))
elif command=='hdiutil':
    if args[0]=='attach':
        if (config/'mount-fails').exists():raise SystemExit(3)
        mount=pathlib.Path(args[args.index('-mountpoint')+1])
        shutil.copytree(root/'image/RatioLab.app',mount/'RatioLab.app',symlinks=True)
    else:
        if (pathlib.Path(args[1])/'RatioLab.app').exists():shutil.rmtree(pathlib.Path(args[1])/'RatioLab.app')
elif command=='PlistBuddy':
    info=plistlib.loads(pathlib.Path(args[-1]).read_bytes());print(info[args[1].split(':')[-1]])
elif command=='lipo':print((pathlib.Path(args[-1]).parents[1]/'arch').read_text())
elif command=='codesign':
    if (pathlib.Path(args[-1])/'Contents/signature').read_text()!='valid':raise SystemExit(4)
elif command=='ditto':
    if (config/'copy-fails').exists():raise SystemExit(5)
    shutil.copytree(args[0],args[1],symlinks=True)
elif command=='mv':
    source,destination=args[-2:]
    if '.ratiolab-stage.' in source and pathlib.Path(destination)==app and (config/'move-fails').exists():raise SystemExit(6)
    if '.ratiolab-backup.' in source and pathlib.Path(destination)==app and (config/'rollback-fails').exists():raise SystemExit(7)
    raise SystemExit(subprocess.call(['/bin/mv',*args]))
elif command=='open':
    version=plistlib.loads((pathlib.Path(args[-1])/'Contents/Info.plist').read_bytes())['CFBundleShortVersionString']
    receipts=list((root/'cache/install-handoffs').glob('update-result-*.json'))
    record=json.loads(receipts[0].read_text()) if receipts else None
    result=(root/'cache/install-handoffs'/record['job']/'result').read_text().strip() if record else None
    (root/'opened.json').write_text(json.dumps(dict(args=args,version=version,result=result)))
else:raise SystemExit('Unexpected fixture command')
''')
        tools={}
        for fixed in update_macos.TOOLS:
            if fixed in ('/bin/sh','/usr/bin/shasum','/usr/bin/mktemp','/bin/mkdir','/bin/rmdir','/bin/rm','/bin/sleep','/bin/cat'):continue
            tool=directory/Path(fixed).name
            tool.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(dispatcher))
                            +' '+shlex.quote(str(self.root))+' '+shlex.quote(tool.name)+' "$@"\n')
            tool.chmod(0o700);tools[fixed]=tool
        return tools

    def detection(self,path=None):
        return update_install.detect_installation(system='darwin',machine='arm64',frozen=True,current='0.1.11',
                         executable=(path or self.app)/'Contents/MacOS/RatioLab')

    def parent(self):
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
        self.children.append(child);return child

    def prepare(self,parent,**options):
        original_run=subprocess.run;original_spawn=update_install._spawn;original_access=os.access
        def run(argv,**kwargs):
            argv=list(argv)
            if argv[0] in self.tools:argv[0]=str(self.tools[argv[0]])
            return original_run(argv,**kwargs)
        def spawn(argv,**kwargs):
            helper=Path(argv[1]);text=helper.read_text()
            for fixed,replacement in self.tools.items():text=text.replace(fixed,shlex.quote(str(replacement)))
            helper.write_text(text)
            original_run(['/bin/sh','-n',str(helper)],check=True)
            return original_spawn(argv,**kwargs)
        def access(path,mode):return True if path in update_macos.TOOLS else original_access(path,mode)
        with (patch.object(update_macos.subprocess,'run',side_effect=run),
              patch.object(update_install,'_spawn',side_effect=spawn),patch.object(os,'access',side_effect=access)):
            prepared=update_install.prepare_install(self.download,self.detection(),directory=self.cache,
                                                   parent_pid=parent.pid,**options)
        self.helpers.append(prepared);return prepared

    def finish(self,prepared,parent,status):
        prepared.launch();parent.terminate();parent.wait(timeout=3)
        prepared._process.wait(timeout=8)
        self.assertEqual(prepared.status(),status,prepared.log_path.read_text())

    def calls_for(self,command):
        return [row for row in map(json.loads,self.calls.read_text().splitlines()) if row[0]==command]

    def test_standard_writable_application_updates_in_place_publishes_then_opens_and_cleans(self):
        parent=self.parent();prepared=self.prepare(parent)
        self.assertEqual(self.calls_for('hdiutil'),[])
        project=self.root/'user-project.json';project.write_text('keep project')
        preferences=self.root/'preferences.json';preferences.write_text('keep preferences')
        self.finish(prepared,parent,'installed-restart-requested')
        opened=json.loads(self.opened.read_text())
        self.assertEqual(opened,dict(args=['-n',str(self.app)],version='0.1.12',result='installed-restart-requested'))
        self.assertEqual(project.read_text(),'keep project');self.assertEqual(preferences.read_text(),'keep preferences')
        self.assertFalse(list(self.app.parent.glob('.ratiolab-*')))
        calls=self.calls_for('hdiutil');self.assertIn('-readonly',calls[0]);self.assertIn('-nobrowse',calls[0])
        for call in self.calls_for('codesign'):
            self.assertIn('--verify',call);self.assertIn('--deep',call);self.assertIn('--strict',call)
            self.assertNotIn('--sign',call);self.assertNotIn('--force',call)
        self.assertEqual(calls[-1][1],'detach')
        self.assertFalse((prepared.directory/'mount').exists())
        result=update_receipt.consume(prepared.directory.parent,current='0.1.12',executable=self.app/'Contents/MacOS/RatioLab',system='darwin')
        self.assertTrue(result.success)
        self.assertIsNone(update_receipt.consume(prepared.directory.parent,current='0.1.12',executable=self.app/'Contents/MacOS/RatioLab',system='darwin'))

    def test_sleep_running_state_transitions_never_look_like_parent_exit(self):
        parent=self.parent();prepared=self.prepare(parent);prepared.launch()
        for state in ('R','S','R','S'):
            self.state.write_text(state);time.sleep(.13)
            self.assertIsNone(prepared._process.poll());self.assertEqual(self.calls_for('hdiutil'),[])
        parent.terminate();parent.wait(timeout=3);prepared._process.wait(timeout=8)
        self.assertEqual(prepared.status(),'installed-restart-requested',prepared.log_path.read_text())

    def test_parent_birth_token_excludes_state_and_rejects_zombie(self):
        for state in ('R','S','S+'):
            result=SimpleNamespace(stdout='Sat Oct 31 00:00:00 2026 '+state)
            with patch.object(update_macos.subprocess,'run',return_value=result):
                self.assertEqual(update_macos.process_identity(123),'Sat Oct 31 00:00:00 2026')
        with patch.object(update_macos.subprocess,'run',return_value=SimpleNamespace(stdout='Sat Oct 31 00:00:00 2026 Z')):
            with self.assertRaises(ValueError):update_macos.process_identity(123)

    def test_cancel_before_arm_never_mounts_or_opens(self):
        parent=self.parent();prepared=self.prepare(parent)
        prepared.cancel();prepared._process.wait(timeout=5)
        self.assertEqual(prepared.status(),'cancelled');self.assertEqual(self.calls_for('hdiutil'),[])
        self.assertFalse(self.opened.exists())

    def test_parent_timeout_never_mounts_or_replaces(self):
        parent=self.parent();prepared=self.prepare(parent,timeout=.5)
        prepared.launch();prepared._process.wait(timeout=5)
        self.assertEqual(prepared.status(),'timeout');self.assertEqual(self.calls_for('hdiutil'),[])
        self.assertFalse(self.opened.exists());self.assertIsNone(parent.poll())

    def test_cancel_after_arm_while_parent_alive_never_starts_installation(self):
        parent=self.parent();prepared=self.prepare(parent);prepared.launch();prepared.cancel()
        prepared._process.wait(timeout=5)
        self.assertEqual(prepared.status(),'cancelled');self.assertEqual(self.calls_for('hdiutil'),[])
        self.assertFalse(self.opened.exists());self.assertIsNone(parent.poll())

    def test_changed_package_after_arm_never_mounts_or_replaces(self):
        parent=self.parent();prepared=self.prepare(parent);prepared.launch()
        prepared.package.write_bytes(b'changed image')
        parent.terminate();parent.wait(timeout=3);prepared._process.wait(timeout=8)
        self.assertEqual(prepared.status(),'checksum-mismatch');self.assertEqual(self.calls_for('hdiutil'),[])
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')

    def test_application_identity_changed_after_arm_never_mounts_or_replaces(self):
        parent=self.parent();prepared=self.prepare(parent);prepared.launch()
        info=self.app/'Contents/Info.plist';data=plistlib.loads(info.read_bytes());data['CFBundleShortVersionString']='0.1.99';info.write_bytes(plistlib.dumps(data))
        parent.terminate();parent.wait(timeout=3);prepared._process.wait(timeout=8)
        self.assertEqual(prepared.status(),'installation-changed');self.assertEqual(self.calls_for('hdiutil'),[])

    def test_payload_signature_failure_preserves_and_reopens_previous_application(self):
        (self.image/'RatioLab.app/Contents/signature').write_text('invalid')
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'signature-invalid')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')
        self.assertEqual(self.calls_for('hdiutil')[-1][1],'detach')
        outcome=update_receipt.consume(prepared.directory.parent,current='0.1.11',
                                      executable=self.app/'Contents/MacOS/RatioLab',system='darwin')
        self.assertFalse(outcome.success)
        self.assertIn('signature could not be verified',outcome.message)

    def test_wrong_payload_architecture_never_replaces_application(self):
        (self.image/'RatioLab.app/Contents/arch').write_text('x86_64')
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'package-identity-mismatch')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')

    def test_wrong_payload_info_version_never_replaces_application(self):
        info=self.image/'RatioLab.app/Contents/Info.plist'
        data=plistlib.loads(info.read_bytes());data['CFBundleShortVersionString']='0.1.99';info.write_bytes(plistlib.dumps(data))
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'package-identity-mismatch')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')

    def test_wrong_payload_runtime_version_is_rejected_even_when_info_matches(self):
        path=self.image/'RatioLab.app';shutil.rmtree(path);self.make_app(path,'0.1.12',runtime_version='0.1.99')
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'runtime-invalid')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')

    def test_mount_failure_detaches_and_keeps_original_application(self):
        (self.config/'mount-fails').touch()
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'mount-failed')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')
        self.assertEqual(self.calls_for('hdiutil')[-1][1],'detach')

    def test_copy_failure_cleans_stage_and_keeps_original_application(self):
        (self.config/'copy-fails').touch()
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'installer-failed')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')
        self.assertFalse(list(self.app.parent.glob('.ratiolab-*')))

    def test_invalid_source_signature_fails_before_helper_or_parent_close(self):
        (self.app/'Contents/signature').write_text('invalid')
        parent=self.parent()
        with self.assertRaises(subprocess.CalledProcessError):self.prepare(parent)
        self.assertFalse(self.cache.exists());self.assertIsNone(parent.poll())

    def test_failed_stage_selftest_preserves_previous_application_and_removes_stage(self):
        (self.config/'selftest-fails').touch()
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'runtime-invalid')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')
        self.assertFalse(list(self.app.parent.glob('.ratiolab-*')))

    def test_failed_final_runtime_check_rolls_back_old_application_before_reopen(self):
        (self.config/'final-fails').touch()
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'runtime-invalid')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')
        self.assertEqual(plistlib.loads((self.app/'Contents/Info.plist').read_bytes())['CFBundleShortVersionString'],'0.1.11')
        self.assertFalse(list(self.app.parent.glob('.ratiolab-*')))

    def test_failed_second_rename_restores_original_application(self):
        (self.config/'move-fails').touch()
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'installer-failed')
        self.assertEqual(json.loads(self.opened.read_text())['version'],'0.1.11')

    def test_failed_rollback_retains_original_backup_without_unsafe_restart(self):
        (self.config/'final-fails').touch();(self.config/'rollback-fails').touch()
        parent=self.parent();prepared=self.prepare(parent);self.finish(prepared,parent,'rollback-failed')
        self.assertFalse(self.opened.exists())
        backups=list(self.app.parent.glob('.ratiolab-backup.*/RatioLab.app'))
        self.assertEqual(len(backups),1)
        self.assertEqual(plistlib.loads((backups[0]/'Contents/Info.plist').read_bytes())['CFBundleShortVersionString'],'0.1.11')
        self.assertIn(str(backups[0].parent),prepared.log_path.read_text())

    def test_protected_readonly_downloads_and_source_launches_do_not_offer_replacement(self):
        self.assertTrue(self.detection().can_install)
        access=os.access
        with patch.object(os,'access',side_effect=lambda path,mode:False if path==self.app.parent else access(path,mode)):
            self.assertFalse(self.detection().can_install)
        with patch.object(os,'statvfs',return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
            self.assertFalse(self.detection().can_install)
        downloads=self.home/'Downloads/RatioLab.app';self.make_app(downloads,'0.1.11')
        self.assertFalse(self.detection(downloads).can_install)
        source=update_install.detect_installation(system='darwin',machine='arm64',frozen=False,current='0.1.11',
                                                  executable=self.app/'Contents/MacOS/RatioLab')
        self.assertFalse(source.can_install)


if __name__=='__main__':unittest.main()
