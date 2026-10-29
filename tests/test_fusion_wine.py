# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Wine layout fixtures exercise Linux/C: boundary without requiring Fusion."""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import fusion_connection as fusion
from geometry import generate


class WineFixtureTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(prefix='ratiolab-wine-')
        self.addCleanup(folder.cleanup)
        # macOS exposes temporary directories through /var -> /private/var.
        # Canonicalize the fixture root before creating profile expectations;
        # endpoint's final component intentionally remains lexical in production.
        self.root=Path(folder.name).resolve()
        self.home=self.root/'home';self.home.mkdir()
        environment=patch.dict(os.environ,{},clear=False);environment.start();self.addCleanup(environment.stop)
        for key in ('RATIOLAB_FUSION_WINEPREFIX','WINEPREFIX','RATIOLAB_FUSION_WINEUSER'):os.environ.pop(key,None)
        platform=patch.object(fusion.sys,'platform','linux');platform.start();self.addCleanup(platform.stop)
        home=patch.object(fusion.Path,'home',return_value=self.home);home.start();self.addCleanup(home.stop)

    def profile(self,prefix=None,user='Maker',marker=True):
        prefix=prefix or self.home/'.autodesk_fusion/wineprefixes/default'
        profile=prefix/'drive_c/users'/user
        profile.mkdir(parents=True,exist_ok=True)
        if marker:(profile/'AppData/Local/Autodesk/webdeploy').mkdir(parents=True,exist_ok=True)
        return prefix,profile

    def endpoint(self,profile,port=34257):
        path=profile/'AppData/Local/RatioLab/fusion-bridge/endpoint.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        value=dict(protocol=fusion.PROTOCOL,host='127.0.0.1',port=port,token='wine-fixture-token-'*3,pid=123,session_id='fixture-session')
        path.write_text(json.dumps(value),encoding='utf-8')
        return path,value

    def test_current_prefix_discovers_unicode_profile_and_windows_paths(self):
        prefix,profile=self.profile(user='André Maker')
        selected=fusion.discover_wine_context()
        self.assertEqual(selected.prefix,prefix.resolve())
        self.assertEqual(selected.profile,profile.resolve())
        self.assertEqual(fusion.addins_directory(),profile/'AppData/Roaming/Autodesk/Autodesk Fusion 360/API/AddIns')
        self.assertEqual(fusion.endpoint_path(),profile/'AppData/Local/RatioLab/fusion-bridge/endpoint.json')
        self.assertEqual(PureWindowsPath(selected.windows_path(selected.endpoint())),
                         PureWindowsPath('C:/users/André Maker/AppData/Local/RatioLab/fusion-bridge/endpoint.json'))

    def test_each_known_legacy_and_flatpak_prefix_is_discovered_without_broad_scan(self):
        candidates=('.fusion360/wineprefixes/default','.var/app/org.winehq.Wine/data/wineprefixes/fusion360',
                    '.autodesk/wineprefixes/default','.wine')
        for relative in candidates:
            with self.subTest(relative=relative):
                # Separate home roots keep automatic selection unambiguous.
                home=self.home/str(candidates.index(relative));home.mkdir()
                prefix,profile=self.profile(home/relative)
                with patch.object(fusion.Path,'home',return_value=home):
                    self.assertEqual(fusion.discover_wine_context().profile,profile.resolve())

    def test_automatic_prefix_needs_fusion_marker(self):
        self.profile(marker=False)
        with self.assertRaisesRegex(fusion.FusionError,'No Fusion Wine profile'):fusion.discover_wine_context()

    def test_roaming_api_marker_is_sufficient(self):
        prefix,profile=self.profile(marker=False)
        (profile/'AppData/Roaming/Autodesk/Autodesk Fusion 360/API').mkdir(parents=True)
        self.assertEqual(fusion.discover_wine_context().profile,profile.resolve())

    def test_explicit_prefix_with_spaces_and_single_unmarked_user_is_supported(self):
        prefix,profile=self.profile(self.root/'Custom Wine è prefix',marker=False)
        os.environ['RATIOLAB_FUSION_WINEPREFIX']=str(prefix)
        self.assertEqual(fusion.discover_wine_context().profile,profile.resolve())

    def test_generic_wineprefix_and_specific_prefix_precedence(self):
        generic,_=self.profile(self.root/'generic')
        specific,profile=self.profile(self.root/'specific')
        os.environ['WINEPREFIX']=str(generic)
        self.assertEqual(fusion.discover_wine_context().prefix,generic.resolve())
        os.environ['RATIOLAB_FUSION_WINEPREFIX']=str(specific)
        self.assertEqual(fusion.discover_wine_context().profile,profile.resolve())

    def test_invalid_explicit_prefix_never_falls_back_to_detected_installation(self):
        self.profile()
        for name in ('RATIOLAB_FUSION_WINEPREFIX','WINEPREFIX'):
            for value in ('','relative-prefix',str(self.root/'missing')):
                with self.subTest(name=name,value=value),patch.dict(os.environ,{name:value}):
                    with self.assertRaisesRegex(fusion.FusionError,'absolute existing Wine prefix'):
                        fusion.discover_wine_context()

    def test_explicit_directory_without_c_drive_fails_actionably(self):
        os.environ['WINEPREFIX']=str(self.root)
        with self.assertRaisesRegex(fusion.FusionError,'drive_c/users'):fusion.discover_wine_context()

    def test_public_and_default_profiles_are_not_selected(self):
        prefix,profile=self.profile()
        for user in ('Public','Default','Default User','All Users'):self.profile(prefix,user)
        self.assertEqual(fusion.discover_wine_context().profile,profile.resolve())

    def test_multiple_profiles_require_user_selection(self):
        prefix,_=self.profile(user='One')
        _,two=self.profile(prefix,user='Two')
        os.environ['RATIOLAB_FUSION_WINEPREFIX']=str(prefix)
        with self.assertRaisesRegex(fusion.FusionError,'RATIOLAB_FUSION_WINEUSER'):fusion.discover_wine_context()
        os.environ['RATIOLAB_FUSION_WINEUSER']='Two'
        self.assertEqual(fusion.discover_wine_context().profile,two.resolve())

    def test_multiple_prefixes_require_explicit_prefix_selection(self):
        self.profile()
        other,profile=self.profile(self.home/'.wine')
        with self.assertRaisesRegex(fusion.FusionError,'Several Fusion Wine profiles'):fusion.discover_wine_context()
        os.environ['RATIOLAB_FUSION_WINEPREFIX']=str(other)
        self.assertEqual(fusion.discover_wine_context().profile,profile.resolve())

    def test_user_selection_rejects_path_syntax_and_unknown_user(self):
        self.profile()
        for user in ('','..','../Maker','C:\\Maker','Maker/subfolder'):
            with self.subTest(user=user),patch.dict(os.environ,RATIOLAB_FUSION_WINEUSER=user):
                with self.assertRaisesRegex(fusion.FusionError,'directory|profile'):fusion.discover_wine_context()
        os.environ['RATIOLAB_FUSION_WINEUSER']='Missing'
        with self.assertRaisesRegex(fusion.FusionError,'No Fusion Wine profile'):fusion.discover_wine_context()

    def test_strict_c_drive_conversion_rejects_outside_and_windows_drive_syntax(self):
        self.profile()
        context=fusion.discover_wine_context()
        with self.assertRaisesRegex(fusion.FusionError,'escapes'):context.windows_path(self.root/'external/manifest.json')
        # A Linux filename containing a backslash/colon cannot become a safe
        # Windows filename. PureWindowsPath alone would silently reinterpret it.
        names=['other:drive']+(['other\\directory'] if os.name!='nt' else [])
        for name in names:
            with self.subTest(name=name),self.assertRaises(fusion.FusionError):
                context.windows_path(context.profile/name/'manifest.json')

    def test_explicit_endpoint_must_match_selected_prefix_before_network_or_export(self):
        _,profile=self.profile();self.endpoint(profile)
        with patch.object(fusion.socket,'create_connection') as connect,patch.object(fusion,'prepare_import') as prepare:
            with self.assertRaisesRegex(fusion.FusionError,'does not match'):
                with fusion.Client(endpoint=self.root/'wrong-prefix/endpoint.json'):pass
        connect.assert_not_called();prepare.assert_not_called()

    def test_endpoint_keeps_the_final_file_for_native_symlink_guard(self):
        _,profile=self.profile()
        path,_=self.endpoint(profile)
        resolved=Path.resolve
        # Model an internal C-drive link without needing Windows symlink
        # privileges. Path selection must validate its target, then retain the
        # lexical file for read_endpoint's existing is_symlink check.
        alternate=profile/'AppData/Local/RatioLab/internal-endpoint.json'
        def endpoint_link(item,*args,**kwargs):
            return alternate if item==path else resolved(item,*args,**kwargs)
        with patch.object(Path,'resolve',endpoint_link):
            self.assertEqual(fusion.discover_wine_context().endpoint(),path)
        with patch.object(Path,'is_symlink',lambda item:item==path):
            with self.assertRaises(fusion.FusionError):
                with fusion.Client():pass

    def test_install_addin_uses_the_selected_wine_profile(self):
        prefix,profile=self.profile(self.root/'p')
        os.environ['WINEPREFIX']=str(prefix)
        source=self.root/'source';source.mkdir()
        for name in fusion.ADDIN_FILES:(source/name).write_text('packaged '+name)
        target=fusion.install_addin(source=source)
        self.assertEqual(target,profile/'AppData/Roaming/Autodesk/Autodesk Fusion 360/API/AddIns/RatioLabBridge')
        for name in fusion.ADDIN_FILES:self.assertEqual((target/name).read_bytes(),(source/name).read_bytes())

    def make_link(self,link,target):
        try:link.symlink_to(target,target_is_directory=target.is_dir())
        except OSError as error:self.skipTest('Host does not allow symlink fixtures: '+str(error))

    def test_external_profile_symlink_is_not_a_valid_c_drive_user(self):
        prefix,_=self.profile(self.root/'p')
        external=self.root/'external';external.mkdir()
        self.make_link(prefix/'drive_c/users/External',external)
        os.environ['WINEPREFIX']=str(prefix)
        os.environ['RATIOLAB_FUSION_WINEUSER']='External'
        with self.assertRaisesRegex(fusion.FusionError,'escapes'):fusion.discover_wine_context()

    def test_package_links_cannot_copy_external_files_into_wine(self):
        prefix,_=self.profile(self.root/'p')
        os.environ['WINEPREFIX']=str(prefix)
        context=fusion.discover_wine_context()
        manifest=fusion.prepare_import(generate('spur',{'teeth':12}),self.root/'output')
        external=self.root/'private.txt';external.write_text('user file')
        self.make_link(manifest.parent/'external.txt',external)
        with self.assertRaisesRegex(fusion.FusionError,'link'):fusion.stage_wine_import(manifest,context)
        self.assertFalse((context.local_data()/'fusion-imports'/manifest.parent.name).exists())
        self.assertEqual(external.read_text(),'user file')

    def test_client_snapshots_context_and_sends_persistent_c_drive_package(self):
        prefix,profile=self.profile(self.root/'p',user='André Maker')
        os.environ['RATIOLAB_FUSION_WINEPREFIX']=str(prefix)
        endpoint,_=self.endpoint(profile)
        output=self.root/'ordinary output è'
        with fusion.Client(endpoint=endpoint) as client:
            os.environ['RATIOLAB_FUSION_WINEPREFIX']=str(self.root/'now invalid')
            client.status=Mock(return_value={'document':{'id':'doc','name':'Test'}})
            client.call=Mock(return_value={'manifest_id':'result'})
            result=client.insert(generate('spur',{'teeth':12}),output,{'gear'})
            method,request=client.call.call_args.args
            self.assertEqual(method,'import_model')
            path=PureWindowsPath(request['manifest_path'])
            self.assertEqual(path.drive,'C:')
            staged=prefix/'drive_c'/Path(*path.parts[1:])
            original=Path(result['package_path'])
            self.assertTrue(original.is_relative_to(output))
            self.assertTrue(staged.is_relative_to(profile/'AppData/Local/RatioLab/fusion-imports'))
            self.assertNotEqual(staged.parent,original)
            self.assertEqual(staged.read_bytes(),(original/'manifest.json').read_bytes())
            self.assertEqual(request['manifest_sha256'],hashlib.sha256(staged.read_bytes()).hexdigest())
            manifest=json.loads(staged.read_text(encoding='utf-8'))
            for component in manifest['components']:
                part=staged.parent/component['step']
                self.assertEqual(component['sha256'],hashlib.sha256(part.read_bytes()).hexdigest())
            self.assertEqual({p.relative_to(original) for p in original.rglob('*')},
                             {p.relative_to(staged.parent) for p in staged.parent.rglob('*')})

    def test_modified_step_prevents_staging_and_submission(self):
        self.profile();context=fusion.discover_wine_context()
        manifest=fusion.prepare_import(generate('spur',{'teeth':12}),self.root/'output')
        value=json.loads(manifest.read_text(encoding='utf-8'))
        (manifest.parent/value['components'][0]['step']).write_text('modified',encoding='ascii')
        with self.assertRaisesRegex(fusion.FusionError,'modified'):fusion.stage_wine_import(manifest,context)
        self.assertFalse((context.local_data()/'fusion-imports'/manifest.parent.name).exists())

    def test_manifest_traversal_is_rejected_before_copy(self):
        self.profile();context=fusion.discover_wine_context()
        manifest=fusion.prepare_import(generate('spur',{'teeth':12}),self.root/'output')
        value=json.loads(manifest.read_text(encoding='utf-8'))
        for path in ('../external.step','C:/external.step','step-parts\\part.step','/absolute.step'):
            value['components'][0]['step']=path
            manifest.write_text(json.dumps(value),encoding='utf-8')
            with self.subTest(path=path),self.assertRaises(fusion.FusionError):fusion.stage_wine_import(manifest,context)

    def test_wine_transport_remains_authenticated_normal_loopback(self):
        _,profile=self.profile()
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(4)
        self.addCleanup(listener.close)
        endpoint,info=self.endpoint(profile,listener.getsockname()[1])
        observed=[]
        def server():
            with listener.accept()[0] as connection:
                with connection.makefile('rwb') as stream:
                    request=json.loads(stream.readline())
                    observed.append(request)
                    reply=dict(id=request['id'],ok=True,result=dict(application='Fusion',version='Wine fixture',
                        document=None,bridge_session=info['session_id']))
                    stream.write((json.dumps(reply)+'\n').encode());stream.flush()
        worker=threading.Thread(target=server,daemon=True);worker.start()
        with fusion.Client(endpoint=endpoint,timeout=3) as client:self.assertIsNone(client.status()['document'])
        worker.join(1);self.assertFalse(worker.is_alive())
        self.assertEqual(observed[0]['token'],info['token'])
        self.assertEqual(observed[0]['method'],'status')


if __name__=='__main__':unittest.main()
