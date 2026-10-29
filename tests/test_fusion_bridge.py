# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Local bridge security, idempotency and owned-group rollback without Fusion."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

ADDIN = Path(__file__).resolve().parents[1]/'src/ratiolab_resources/fusion_addin/RatioLabBridge'


def load(name):
    qualified = '_test_ratiolab_' + name
    spec = importlib.util.spec_from_file_location(qualified, ADDIN/(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


transport = load('bridge_server')
backend = load('fusion_import')


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.fired = threading.Event()
        self.executions = []
        def execute(method, params):
            self.executions.append((method, params, threading.get_ident()))
            return dict(done=True)
        self.server = transport.BridgeServer(lambda: self.fired.set(), execute,
                                            endpoint=Path(self.folder.name)/'endpoint.json',
                                            wait_seconds=.01)

    def tearDown(self):
        self.server.stop()
        self.folder.cleanup()

    def request(self, method='import_model', **changes):
        request = dict(protocol=transport.PROTOCOL, id=str(uuid.uuid4()),
                       token=self.server.token, method=method, params={})
        request.update(changes)
        return request

    def test_timeout_and_same_id_retry_never_repeat_a_mutation(self):
        request = self.request()
        reply = self.server.request(request)
        self.assertTrue(reply['running'])
        self.assertEqual(self.executions, [])
        # Only the CustomEvent handler drains work; a socket thread cannot.
        self.server.drain()
        reply = self.server.request(request)
        self.assertTrue(reply['ok'])
        self.server.drain()
        self.assertEqual(len(self.executions), 1)
        changed = dict(request, params={'different': True})
        with self.assertRaisesRegex(ValueError, 'different payload'):
            self.server.request(changed)

    def test_authentication_allowlist_and_uuid_are_checked_before_dispatch(self):
        for changes in ({'token': 'wrong'}, {'method': 'exec'}, {'id': 'not-a-uuid'},
                        {'protocol': 'other/1'}, {'params': []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.server.request(self.request(**changes))
        self.assertFalse(self.fired.is_set())
        self.assertEqual(self.server.pending.qsize(), 0)

    def test_json_rejects_ambiguous_keys_and_nonfinite_numbers(self):
        for value in ('{"id":1,"id":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                transport.strict_json(value)

    def test_dispatch_failure_is_logged_without_credentials_or_sdk_calls(self):
        def fail():
            raise TypeError('native overload ' + self.server.token)
        self.server.fire_event = fail
        reply = self.server.request(self.request('status'))
        self.assertFalse(reply['ok'])
        log = self.server.endpoint.with_name('dispatch-error.log').read_text(encoding='utf-8')
        self.assertIn('TypeError: native overload', log)
        self.assertNotIn(self.server.token, log)
        self.server.drain()
        self.assertEqual(self.executions, [])

    def test_stop_wakes_pending_caller_and_keeps_newer_session_endpoint(self):
        self.server.wait_seconds = 5
        replies = []
        worker = threading.Thread(target=lambda: replies.append(self.server.request(self.request())))
        worker.start()
        self.assertTrue(self.fired.wait(1))
        endpoint = self.server.endpoint
        endpoint.write_text(json.dumps(dict(session_id='new-session')), encoding='utf-8')
        self.server.stop()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertIn('stopped', replies[0]['error'])
        self.assertTrue(endpoint.exists())
        self.server.drain()
        self.assertEqual(self.executions, [])

    def test_real_loopback_request_only_executes_when_main_thread_drains(self):
        self.server.wait_seconds = 2
        info = self.server.start()
        self.assertEqual(info['host'], '127.0.0.1')
        self.assertEqual(info['session_id'], self.server.session_id)
        replies = []
        def client():
            with socket.create_connection((info['host'], info['port']), timeout=2) as stream:
                stream.sendall(json.dumps(self.request('status')).encode() + b'\n')
                replies.append(json.loads(stream.makefile('rb').readline()))
        worker = threading.Thread(target=client)
        worker.start()
        self.assertTrue(self.fired.wait(1))
        self.assertEqual(self.executions, [])
        self.server.drain()
        worker.join(2)
        self.assertTrue(replies[0]['ok'])
        self.assertEqual(self.executions[0][2], threading.get_ident())
        self.server.stop()
        self.assertFalse(self.server.endpoint.exists())

    def test_malformed_socket_request_receives_a_bounded_error(self):
        info = self.server.start()
        with socket.create_connection((info['host'], info['port']), timeout=2) as stream:
            stream.sendall(b'{"invalid":}\n')
            reply = json.loads(stream.makefile('rb').readline())
        self.assertFalse(reply['ok'])
        self.assertFalse(self.fired.is_set())


class AddinEntrypointTests(unittest.TestCase):
    def test_native_two_argument_custom_event_overload_and_lifecycle(self):
        class Event:
            def add(self, handler):
                self.handler = handler
                return True
            def remove(self, handler):
                self.removed = handler
        class Application:
            activeDocument = None
            version = 'native-shaped-test'
            def __init__(self):
                self.event = Event()
                self.fired = []
            def registerCustomEvent(self, event_id):
                self.event_id = event_id
                return self.event
            def fireCustomEvent(self, event_id, additional_info):
                self.fired.append((event_id, additional_info))
                # Native Fusion 2705.1.30 delivers the event while returning
                # False. Completion, rather than this result, is authoritative.
                return False
            def unregisterCustomEvent(self, event_id):
                self.unregistered = event_id
                return True
        app = Application()
        adsk = ModuleType('adsk')
        core, fusion = ModuleType('adsk.core'), ModuleType('adsk.fusion')
        core.Application = SimpleNamespace(get=lambda: app)
        core.CustomEventHandler = type('CustomEventHandler', (), {})
        adsk.core, adsk.fusion = core, fusion
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(sys.modules, {'adsk': adsk, 'adsk.core': core, 'adsk.fusion': fusion}):
            entrypoint = load('RatioLabBridge')
            # Redirect only the discovered endpoint; entrypoint/helper loading
            # and the required native fireCustomEvent signature are unchanged.
            original_loader = entrypoint._local_module
            def local_module(name):
                module = original_loader(name)
                if name == 'bridge_server':
                    module.endpoint_path = lambda: Path(folder)/'endpoint.json'
                return module
            with patch.object(entrypoint, '_local_module', side_effect=local_module):
                entrypoint.run(None)
                try:
                    server = entrypoint._server
                    server.wait_seconds = .001
                    request = dict(protocol=transport.PROTOCOL, id=str(uuid.uuid4()),
                                   token=server.token, method='status', params={})
                    self.assertTrue(server.request(request)['running'])
                    self.assertEqual(app.fired, [(app.event_id, '')])
                    app.event.handler.notify(None)
                    reply = server.request(request)
                    self.assertTrue(reply['ok'])
                    self.assertEqual(reply['result']['version'], app.version)
                finally:
                    entrypoint.stop(None)
                self.assertEqual(app.unregistered, app.event_id)
                self.assertIs(app.event.removed, app.event.handler)
                self.assertFalse((Path(folder)/'endpoint.json').exists())


class PackageFixture:
    def prepare(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root/'step-parts').mkdir()
        self.step = self.root/'step-parts/001-part.step'
        self.step.write_bytes(b'ISO-10303-21;\nEND-ISO-10303-21;\n')
        self.manifest = dict(format='ratiolab-fusion-import/1', id=str(uuid.uuid4()),
                             family='spur', name='RatioLab spur', units='mm',
                             parameters={'teeth': 18}, bom={'parts': ['Gear']}, notes=['Nominal coordinates'],
                             components=[dict(index=1, name='Gear', role='gear', visible=True,
                                              color=[.35, .72, .9], step='step-parts/001-part.step',
                                              sha256=hashlib.sha256(self.step.read_bytes()).hexdigest(),
                                              expected_volume_mm3=1000.,
                                              expected_bounds_mm=[[0., 0., 0.], [10., 10., 10.]])])

    def write_manifest(self):
        self.path = self.root/'manifest.json'
        data = json.dumps(self.manifest).encode('utf-8')
        self.path.write_bytes(data)
        self.digest = hashlib.sha256(data).hexdigest()
        return str(self.path), self.digest


class PackageTests(PackageFixture, unittest.TestCase):
    def setUp(self):
        self.prepare()

    def test_stages_hashed_step_snapshots_and_removes_them_after_use(self):
        path, digest = self.write_manifest()
        original = self.step.read_bytes()
        with backend.staged_package(path, digest) as (manifest, paths):
            self.assertEqual(manifest['id'], self.manifest['id'])
            self.assertEqual(paths[0].read_bytes(), original)
            self.step.write_bytes(b'changed after staging')
            self.assertEqual(paths[0].read_bytes(), original)
        self.assertFalse(paths[0].exists())

    def test_manifest_and_step_hash_failures_are_detected_before_import(self):
        path, digest = self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'manifest SHA256'):
            backend.validate_manifest(path, '0' * 64)
        self.step.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'STEP SHA256'):
            with backend.staged_package(path, digest):
                self.fail('Tampered package was accepted')

    def test_paths_cannot_escape_or_use_windows_alternate_streams(self):
        for relative in ('../outside.step', '/absolute.step', 'C:/outside.step',
                         'step-parts\\001-part.step', 'step-parts/file.step:stream'):
            self.manifest['components'][0]['step'] = relative
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                backend.validate_manifest(*self.write_manifest())

    def test_invalid_units_dimensions_and_repeated_indices_are_rejected(self):
        original = copy.deepcopy(self.manifest)
        for mutate in (lambda m: m.update(units='cm'),
                       lambda m: m['components'][0].update(expected_volume_mm3=-1),
                       lambda m: m['components'][0].update(color=[float('inf'), 0, 0]),
                       lambda m: m['components'].append(copy.deepcopy(m['components'][0])),
                       lambda m: m['components'][0].update(expected_bounds_mm=[[0, 0, 0], [0, 1, 1]])):
            self.manifest = copy.deepcopy(original)
            mutate(self.manifest)
            with self.assertRaises(ValueError):
                backend.validate_manifest(*self.write_manifest())


class FakeCollection:
    def __init__(self, values=None):
        self.values = list(values or [])

    @property
    def count(self):
        return len(self.values)

    def item(self, index):
        return self.values[index]


class FakeAttributes:
    def __init__(self):
        self.values = {}

    def add(self, group, name, value):
        self.values[group, name] = json.loads(value)
        return object()


class FakeComponent:
    def __init__(self):
        self.name = ''
        self.occurrences = FakeOccurrences()
        self.attributes = FakeAttributes()
        self.bodies = []


class FakeOccurrence:
    def __init__(self, owner):
        self.owner = owner
        self.component = FakeComponent()
        self.deleted = False
        self.isLightBulbOn = True

    @property
    def bRepBodies(self):
        return FakeCollection(self.component.bodies)

    @property
    def childOccurrences(self):
        return self.component.occurrences

    def deleteMe(self):
        self.deleted = True
        self.owner.values.remove(self)
        return True


class FakeOccurrences(FakeCollection):
    def addNewComponent(self, transform):
        occurrence = FakeOccurrence(self)
        self.values.append(occurrence)
        return occurrence


def body(scale=1, solid=True):
    return SimpleNamespace(isSolid=solid, volume=scale ** 3,
                           boundingBox=SimpleNamespace(minPoint=SimpleNamespace(x=0, y=0, z=0),
                                                       maxPoint=SimpleNamespace(x=scale, y=scale, z=scale)))


class FakeDesign:
    def __init__(self):
        self.rootComponent = FakeComponent()
        self.activeEditObject = self.rootComponent


class ImportTests(PackageFixture, unittest.TestCase):
    def setUp(self):
        self.prepare()
        self.document = SimpleNamespace(creationId='document-1', name='Existing design')
        self.design = FakeDesign()
        self.preexisting = self.design.rootComponent.occurrences.addNewComponent(None)
        self.preexisting.component.name = 'User component'
        self.preexisting.component.bodies.append(body())
        self.imports = []
        def import_step(options, target):
            self.assertFalse(options.isViewFit)
            self.assertTrue(Path(options.filename).is_file())
            target.bodies.append(body())
            self.imports.append(target)
            return FakeCollection(target.bodies)
        manager = SimpleNamespace(createSTEPImportOptions=lambda filename: SimpleNamespace(filename=filename, isViewFit=True),
                                  importToTarget2=import_step)
        self.app = SimpleNamespace(activeDocument=self.document, activeProduct=self.design,
                                   userInterface=SimpleNamespace(activeCommand='SelectCommand'),
                                   activeEditObject=self.design.rootComponent,
                                   importManager=manager, version='test-Fusion')
        adsk = ModuleType('adsk')
        core, fusion = ModuleType('adsk.core'), ModuleType('adsk.fusion')
        core.Matrix3D = SimpleNamespace(create=lambda: object())
        fusion.Design = SimpleNamespace(cast=lambda value: value if isinstance(value, FakeDesign) else None)
        fusion.Sketch = SimpleNamespace(cast=lambda value: value if getattr(value, 'is_sketch', False) else None)
        adsk.core, adsk.fusion = core, fusion
        self.sdk = patch.dict(sys.modules, {'adsk': adsk, 'adsk.core': core, 'adsk.fusion': fusion})
        self.sdk.start()
        self.addCleanup(self.sdk.stop)
        self.importer = backend.FusionImporter(self.app)
        self.importer.session_id = 'bridge-session'

    def params(self):
        path, digest = self.write_manifest()
        return dict(manifest_path=path, manifest_sha256=digest,
                    document_id=self.importer.document_info()['id'])

    def test_status_tracks_native_document_identity_and_home(self):
        value = self.importer.handle('status', {})
        self.assertEqual(value['document'], dict(id='document-1', name='Existing design'))
        self.assertEqual(value['bridge_session'], 'bridge-session')
        self.app.activeDocument = SimpleNamespace(creationId='document-1', name='Copied design')
        new_id = self.importer.document_info()['id']
        self.assertNotEqual(new_id, 'document-1')
        self.assertEqual(self.importer.document_info()['id'], new_id)
        self.app.activeDocument = None
        self.assertIsNone(self.importer.handle('status', {})['document'])

    def test_success_imports_nominal_geometry_and_metadata_in_an_owned_group(self):
        self.manifest['components'][0]['visible'] = False
        result = self.importer.handle('import_model', self.params())
        roots = self.design.rootComponent.occurrences.values
        self.assertEqual(len(roots), 2)
        self.assertIs(roots[0], self.preexisting)
        group = roots[1].component
        imported = group.occurrences.item(0)
        self.assertEqual(imported.component.name, 'Gear')
        self.assertFalse(imported.isLightBulbOn)
        self.assertEqual(group.attributes.values['RatioLab', 'parameters'], {'teeth': 18})
        self.assertEqual(group.attributes.values['RatioLab', 'bom'], self.manifest['bom'])
        self.assertEqual(imported.component.attributes.values['RatioLab', 'component']['color'], [.35, .72, .9])
        self.assertEqual(result['components'][0]['solid_bodies'], 1)
        self.assertEqual(result['components'][0]['volume_mm3'], 1000)
        self.assertEqual(result['components'][0]['bounds_mm'], [[0, 0, 0], [10, 10, 10]])
        second = self.importer.handle('import_model', self.params())
        self.assertNotEqual(second['group_name'], result['group_name'])

    def test_stale_document_active_command_and_sketch_leave_existing_geometry_alone(self):
        params = self.params()
        with self.assertRaisesRegex(ValueError, 'document changed'):
            self.importer.import_model(dict(params, document_id='stale-document'))
        self.app.userInterface.activeCommand = 'ExtrudeCommand'
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.importer.import_model(params)
        self.app.userInterface.activeCommand = 'SelectCommand'
        self.design.activeEditObject = SimpleNamespace(is_sketch=True)
        with self.assertRaisesRegex(ValueError, 'sketch'):
            self.importer.import_model(params)
        self.assertEqual(self.design.rootComponent.occurrences.values, [self.preexisting])
        self.assertEqual(self.imports, [])

    def test_failed_second_import_rolls_back_only_the_new_top_occurrence(self):
        part = copy.deepcopy(self.manifest['components'][0])
        part.update(index=2, name='Second gear')
        self.manifest['components'].append(part)
        original_import = self.app.importManager.importToTarget2
        def fail_second(options, target):
            if self.imports:
                raise RuntimeError('Native STEP failure')
            return original_import(options, target)
        self.app.importManager.importToTarget2 = fail_second
        with self.assertRaisesRegex(RuntimeError, 'Native STEP failure'):
            self.importer.import_model(self.params())
        self.assertEqual(self.design.rootComponent.occurrences.values, [self.preexisting])
        self.assertFalse(self.preexisting.deleted)
        self.assertEqual(self.preexisting.component.name, 'User component')
        self.assertEqual(len(self.preexisting.component.bodies), 1)

    def test_wrong_scale_or_surface_import_is_rejected_and_rolled_back(self):
        for invalid in (body(scale=10), body(solid=False)):
            def wrong(options, target):
                target.bodies.append(invalid)
                return FakeCollection(target.bodies)
            self.app.importManager.importToTarget2 = wrong
            with self.assertRaises(ValueError):
                self.importer.import_model(self.params())
            self.assertEqual(self.design.rootComponent.occurrences.values, [self.preexisting])


if __name__ == '__main__':
    unittest.main()
