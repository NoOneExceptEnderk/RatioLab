# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Fusion protocol, safe installation, and real standalone transfer packages."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import fusion_connection as fusion
from geometry import generate
from solid_geometry import signature


class EndpointTests(unittest.TestCase):
    def endpoint(self):
        return dict(protocol=fusion.PROTOCOL,host='127.0.0.1',port=37543,
                    token='test-token-'*4,pid=123,session_id='test-session')

    def test_only_authenticated_loopback_endpoint_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'endpoint.json'
            value=self.endpoint()
            path.write_text(json.dumps(value))
            self.assertEqual(fusion.read_endpoint(path),value)
            for key,bad in (('protocol','other/1'),('host','localhost'),('host','192.168.1.2'),
                            ('host','example.com'),('port',True),('port',0),('port',65536),
                            ('token',''),('pid',False),('session_id','')):
                with self.subTest(key=key,bad=bad):
                    path.write_text(json.dumps(dict(value,**{key:bad})))
                    with self.assertRaises(fusion.FusionError):fusion.read_endpoint(path)
            path.write_text('x'*65537)
            with self.assertRaises(fusion.FusionError):fusion.read_endpoint(path)
            path.unlink()
            with self.assertRaisesRegex(fusion.FusionError,'run RatioLabBridge'):
                fusion.read_endpoint(path)

    @patch.object(fusion.sys,'platform','win32')
    def test_connection_uses_validated_loopback_and_closes_resources(self):
        endpoint=self.endpoint()
        sock=Mock()
        with patch.object(fusion,'read_endpoint',return_value=endpoint), patch.object(fusion.socket,'create_connection',return_value=sock) as connect:
            with fusion.Client(timeout=12) as client:
                self.assertEqual(client.endpoint,endpoint)
                connect.assert_not_called()
                client._exchange(b'first\n')
                client._exchange(b'second\n')
            self.assertEqual(connect.call_count,2)
            connect.assert_called_with(('127.0.0.1',endpoint['port']),timeout=5)
            self.assertEqual(sock.settimeout.call_count,2)
            sock.settimeout.assert_called_with(12)
            self.assertEqual(sock.makefile.return_value.close.call_count,2)
            self.assertEqual(sock.close.call_count,2)

    @patch.object(fusion.sys,'platform','win32')
    def test_untrusted_endpoint_is_rejected_before_connecting(self):
        with patch.object(fusion,'read_endpoint',side_effect=fusion.FusionError('invalid')), patch.object(fusion.socket,'create_connection') as connect:
            with self.assertRaises(fusion.FusionError):fusion.Client().__enter__()
        connect.assert_not_called()

    def test_platform_install_paths_are_per_user(self):
        with patch.object(fusion.sys,'platform','win32'), patch.dict(os.environ,APPDATA=str(Path.cwd()/'roaming')):
            self.assertEqual(fusion.addins_directory(),Path.cwd()/'roaming/Autodesk/Autodesk Fusion 360/API/AddIns')
        with patch.object(fusion.sys,'platform','darwin'), patch.object(fusion.Path,'home',return_value=Path('/users/test')):
            self.assertEqual(fusion.addins_directory(),Path('/users/test/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns'))


class ProtocolTests(unittest.TestCase):
    def client(self, response=None):
        client=fusion.Client()
        client.endpoint=EndpointTests().endpoint()
        def reply(payload):
            request=json.loads(payload)
            value=dict(id=request['id'],ok=True,result={'value':3})
            if callable(response):value=response(request)
            elif response is not None:value=response
            if isinstance(value,Exception):raise value
            if isinstance(value,bytes):return value
            return (json.dumps(value)+'\n').encode()
        client._exchange=Mock(side_effect=reply)
        return client

    def test_uuid_ids_authentication_and_method_are_in_one_json_line(self):
        client=self.client()
        self.assertEqual(client.call('status'),{'value':3})
        self.assertEqual(client.call('import_model',{'manifest_path':'C:/parts a/manifest.json'}),{'value':3})
        values=[json.loads(call.args[0]) for call in client._exchange.call_args_list]
        self.assertNotEqual(values[0]['id'],values[1]['id'])
        for value in values:
            self.assertEqual(value['protocol'],fusion.PROTOCOL)
            self.assertEqual(value['token'],client.endpoint['token'])
            self.assertEqual(len(value['id']),36)
        self.assertEqual(values[1]['params']['manifest_path'],'C:/parts a/manifest.json')
        self.assertTrue(all(call.args[0].count(b'\n')==1 for call in client._exchange.call_args_list))

    def test_arbitrary_code_or_methods_are_not_sent(self):
        client=self.client()
        for method in ('eval','execute','file.read','shutdown'):
            with self.assertRaises(fusion.FusionError):client.call(method)
        client._exchange.assert_not_called()

    def test_uncertain_mutations_are_never_retried(self):
        responses=[socket.timeout('late'),b'',b'not json\n',
            lambda req:dict(id='wrong',ok=True,result={}),
            lambda req:dict(id=req['id'],ok=False,running=True,error='late'),
            lambda req:dict(id=req['id'],ok=True,result=None)]
        for response in responses:
            with self.subTest(response=type(response).__name__):
                client=self.client(response)
                with self.assertRaisesRegex(fusion.FusionError,'do not resend'):
                    client.call('import_model',{})
                self.assertEqual(client._exchange.call_count,1)

    def test_rejected_request_reports_error_without_retry(self):
        client=self.client(lambda req:dict(id=req['id'],ok=False,error='Authentication failed'))
        with self.assertRaisesRegex(fusion.FusionError,'Authentication failed'):client.call('status')
        self.assertEqual(client._exchange.call_count,1)

    def test_status_rejects_wrong_application_session_and_document(self):
        client=self.client()
        status=dict(application='Fusion',version='2600',bridge_session='test-session',document={'id':'doc1','name':'Untitled'})
        client.call=Mock(return_value=status)
        self.assertEqual(client.status(),status)
        for update in ({'application':'Other'},{'bridge_session':'previous-session'},{'document':{'id':'','name':'x'}},{'document':[]}):
            client.call.return_value=dict(status,**update)
            with self.subTest(update=update),self.assertRaises(fusion.FusionError):client.status()

    def test_insert_requires_document_before_export_or_mutation(self):
        client=self.client()
        client.status=Mock(return_value={'document':None})
        with patch.object(fusion,'prepare_import') as prepare:
            with self.assertRaisesRegex(fusion.FusionError,'Open a design document'):client.insert(Mock(),'unused')
        prepare.assert_not_called()
        client._exchange.assert_not_called()


@patch.object(fusion.sys,'platform','win32')
class LiveBridgeInteroperabilityTests(unittest.TestCase):
    def test_status_insert_and_status_use_the_real_one_request_server(self):
        # This exercises the production transport on both ends. A persistent
        # client stream would pass mocked protocol tests but fail the second
        # request because BridgeServer closes each socket after its one reply.
        path=Path(__file__).resolve().parents[1]/'src/ratiolab_resources/fusion_addin/RatioLabBridge/bridge_server.py'
        name='_test_fusion_client_transport'
        spec=importlib.util.spec_from_file_location(name,path)
        transport=importlib.util.module_from_spec(spec)
        sys.modules[name]=transport
        spec.loader.exec_module(transport)
        self.addCleanup(sys.modules.pop,name,None)
        fired=threading.Event()
        executions=[]
        replies=[]
        failures=[]
        main_thread=threading.get_ident()
        with tempfile.TemporaryDirectory() as temporary:
            endpoint=Path(temporary)/'endpoint.json'
            def execute(method,params):
                executions.append((method,params,threading.get_ident()))
                if method=='status':
                    return dict(application='Fusion',version='test',bridge_session=server.session_id,
                                document={'id':'live-doc','name':'Transport test'})
                manifest=Path(params['manifest_path'])
                self.assertEqual(params['manifest_sha256'],hashlib.sha256(manifest.read_bytes()).hexdigest())
                self.assertEqual(params['document_id'],'live-doc')
                return dict(manifest_id=json.loads(manifest.read_text(encoding='utf-8'))['id'],components=[{'index':1}])
            server=transport.BridgeServer(fired.set,execute,endpoint=endpoint,wait_seconds=3)
            server.start()
            def client_sequence():
                try:
                    with fusion.Client(endpoint=endpoint,timeout=4) as client:
                        replies.append(client.status())
                        replies.append(client.insert(generate('spur',{'teeth':12}),temporary,{'gear'}))
                        replies.append(client.status())
                except Exception as error:failures.append(error)
            with patch.object(fusion.socket,'create_connection',wraps=socket.create_connection) as connect:
                worker=threading.Thread(target=client_sequence,daemon=True)
                worker.start()
                try:
                    # Simulate Fusion's CustomEvent dispatcher on this thread;
                    # the production listener still runs on real socket threads.
                    deadline=time.monotonic()+8
                    while worker.is_alive() and time.monotonic()<deadline:
                        if fired.wait(.05):
                            fired.clear();server.drain()
                    worker.join(.2)
                    self.assertFalse(worker.is_alive(),'client/server sequence timed out')
                    self.assertFalse(failures,[(str(error),repr(error.__cause__)) for error in failures])
                    self.assertEqual(connect.call_count,4)
                    self.assertEqual([item[0] for item in executions],['status','status','import_model','status'])
                    self.assertTrue(all(item[2]==main_thread for item in executions))
                    self.assertEqual(len(replies),3)
                    self.assertTrue(Path(replies[1]['package_path']).is_dir())
                    self.assertEqual(replies[2]['document']['id'],'live-doc')
                finally:
                    server.stop();worker.join(1)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.source=self.root/'source';self.source.mkdir()
        self.destination=self.root/'addins'
        for name in fusion.ADDIN_FILES:(self.source/name).write_text('original '+name)

    def test_install_update_is_managed_and_preserves_unrelated_addins(self):
        target=fusion.install_addin(self.destination,self.source)
        other=self.destination/'OtherAddin';other.mkdir();(other/'private.py').write_text('user work')
        cache=target/'__pycache__';cache.mkdir();(cache/'bridge_server.cpython-314.pyc').write_bytes(b'cache')
        (self.source/'bridge_server.py').write_text('new release')
        self.assertEqual(fusion.install_addin(self.destination,self.source),target)
        self.assertEqual((target/'bridge_server.py').read_text(),'new release')
        self.assertEqual((other/'private.py').read_text(),'user work')
        self.assertEqual(set(p.name for p in target.iterdir()),set(fusion.ADDIN_FILES)|{fusion.INSTALL_RECORD})

    def test_modified_or_unmanaged_addin_is_preserved(self):
        target=fusion.install_addin(self.destination,self.source)
        (target/'RatioLabBridge.py').write_text('user modification')
        with self.assertRaisesRegex(fusion.FusionError,'preserve'):fusion.install_addin(self.destination,self.source)
        self.assertEqual((target/'RatioLabBridge.py').read_text(),'user modification')
        (target/fusion.INSTALL_RECORD).unlink()
        with self.assertRaises(fusion.FusionError):fusion.install_addin(self.destination,self.source)

    def test_additional_user_files_prevent_update(self):
        target=fusion.install_addin(self.destination,self.source)
        (target/'notes.txt').write_text('keep me')
        with self.assertRaises(fusion.FusionError):fusion.install_addin(self.destination,self.source)
        self.assertEqual((target/'notes.txt').read_text(),'keep me')

    def test_missing_resource_cannot_publish_partial_install(self):
        (self.source/'fusion_import.py').unlink()
        with self.assertRaises(fusion.FusionError):fusion.install_addin(self.destination,self.source)
        self.assertFalse((self.destination/'RatioLabBridge').exists())
        self.assertEqual(list(self.destination.iterdir()),[])

    def test_publish_failure_restores_previous_managed_install(self):
        target=fusion.install_addin(self.destination,self.source)
        (self.source/'bridge_server.py').write_text('replacement')
        rename=Path.rename
        def fail_publish(path,to):
            if path.name.startswith('.RatioLabBridge-') and 'backup' not in path.name and Path(to)==target:
                raise OSError('simulated publish failure')
            return rename(path,to)
        with patch.object(Path,'rename',fail_publish),self.assertRaises(OSError):fusion.install_addin(self.destination,self.source)
        self.assertEqual((target/'bridge_server.py').read_text(),'original bridge_server.py')


class ImportPackageTests(unittest.TestCase):
    def test_freeform_fusion_step_uses_closed_explicit_topology(self):
        design=generate('harmonic')
        # The deformed bearing has no analytic circles: this exercises the
        # fallback Fusion otherwise imports as disconnected surface bodies.
        design.parts=[design.parts[2]]
        with tempfile.TemporaryDirectory() as temporary:
            path=fusion.prepare_import(design,temporary)
            manifest=json.loads(path.read_text(encoding='utf-8'))
            record,=manifest['components']
            step=path.parent/record['step']
            text=step.read_text(encoding='ascii')
            self.assertIn('MANIFOLD_SOLID_BREP(',text)
            self.assertIn('ADVANCED_FACE(',text)
            self.assertIn('EDGE_CURVE(',text)
            self.assertNotIn('FACETED_BREP(',text)
            self.assertEqual(record['sha256'],hashlib.sha256(step.read_bytes()).hexdigest())
            self.assertEqual(record['expected_volume_mm3'],signature(design.parts[0])['volume_mm3'])

    def test_real_step_hashes_units_bounds_bom_visibility_and_unique_packages(self):
        design=generate('spur',{'teeth':12,'width':4})
        support=copy.deepcopy(design.parts[0]);support.role='support';support.name='Support'
        design.parts.append(support)
        with tempfile.TemporaryDirectory() as temporary:
            first=fusion.prepare_import(design,temporary,{'gear'})
            second=fusion.prepare_import(design,temporary,{'gear'})
            self.assertNotEqual(first,second)
            manifest=json.loads(first.read_text(encoding='utf-8'))
            self.assertEqual(manifest['format'],'ratiolab-fusion-import/1')
            self.assertEqual(manifest['units'],'mm')
            self.assertEqual(manifest['parameters'],design.values)
            self.assertEqual(len(manifest['components']),2)
            self.assertEqual([p['visible'] for p in manifest['components']],[True,False])
            for part,record in zip(design.parts,manifest['components']):
                step=first.parent/record['step']
                self.assertTrue(step.read_text(encoding='ascii').startswith('ISO-10303-21;'))
                self.assertEqual(record['sha256'],hashlib.sha256(step.read_bytes()).hexdigest())
                self.assertGreater(record['expected_volume_mm3'],0)
                shape=signature(part)
                self.assertEqual(record['expected_bounds_mm'],[shape['min'],shape['max']])
            self.assertTrue((first.parent/'model.config.json').is_file())
            self.assertTrue((first.parent/'model.bom.csv').is_file())
            self.assertEqual(manifest['bom']['family'],'spur')

    def test_insert_captures_document_and_preserves_package_on_timeout(self):
        client=fusion.Client();client.status=Mock(return_value={'document':{'id':'original-doc','name':'Test'}})
        client.call=Mock(side_effect=fusion.FusionError('May still be running; do not resend'))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(fusion.FusionError):client.insert(generate('spur',{'teeth':12}),temporary)
            method,params=client.call.call_args.args
            self.assertEqual(method,'import_model')
            self.assertEqual(params['document_id'],'original-doc')
            manifest=Path(params['manifest_path'])
            self.assertTrue(manifest.is_file())
            self.assertEqual(params['manifest_sha256'],hashlib.sha256(manifest.read_bytes()).hexdigest())
            self.assertEqual(client.call.call_count,1)


if __name__=='__main__':unittest.main()
