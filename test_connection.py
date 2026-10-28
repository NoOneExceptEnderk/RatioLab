"""Exercise CAD failures without sockets, real credentials or document mutations."""
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from connection import Client, ControlError, connect_or_launch


class ConnectionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.control_dir = Path(self.folder.name)
        environment = patch.dict('os.environ', {'SOLIDCRAFT_CONTROL_DIR': self.folder.name})
        environment.start()
        self.addCleanup(environment.stop)

    def token(self, port=7878):
        (self.control_dir / f'{port}.token').write_text('test-only-token\n')

    @patch('connection.socket.create_connection')
    def test_missing_token_never_opens_socket(self, connect):
        with self.assertRaisesRegex(ControlError, 'disconnected'):
            with Client():
                self.fail('Connection should not succeed')
        connect.assert_not_called()

    @patch('connection.socket.create_connection')
    def test_token_port_and_resources(self, connect):
        self.token(port=7890)
        sock = connect.return_value
        with Client(port=7890) as client:
            self.assertEqual(client.token, 'test-only-token')
            self.assertIs(client.io, sock.makefile.return_value)
        connect.assert_called_once_with(('127.0.0.1', 7890), timeout=5)
        sock.settimeout.assert_called_once_with(3700)
        sock.makefile.assert_called_once_with('rwb')
        sock.makefile.return_value.close.assert_called_once_with()
        sock.close.assert_called_once_with()

    @patch('connection.socket.create_connection')
    def test_connection_refused_reports_configured_port(self, connect):
        self.token(port=7890)
        connect.side_effect = ConnectionRefusedError()
        with self.assertRaisesRegex(ControlError, 'local port 7890'):
            with Client(port=7890):
                self.fail('Connection should not succeed')

    @patch('connection.socket.create_connection')
    def test_stream_setup_failure_closes_socket(self, connect):
        self.token()
        sock = connect.return_value
        sock.makefile.side_effect = OSError('stream unavailable')
        with self.assertRaises(ControlError):
            with Client():
                self.fail('Connection should not succeed')
        sock.close.assert_called_once_with()

    def test_socket_closes_even_if_stream_close_fails(self):
        client = Client()
        client.io = Mock()
        client.sock = Mock()
        client.io.close.side_effect = OSError('close failed')
        with self.assertRaises(OSError):
            client.__exit__()
        client.sock.close.assert_called_once_with()


class ProtocolTests(unittest.TestCase):
    def client(self, *replies):
        client = Client()
        client.token = 'test-only-token'
        client.io = Mock()
        client.io.readline.side_effect = [
            reply if isinstance(reply, (bytes, Exception))
            else (json.dumps(reply) + '\n').encode()
            for reply in replies
        ]
        return client

    def requests(self, client):
        return [json.loads(args.args[0]) for args in client.io.write.call_args_list]

    def test_authenticated_requests_have_sequential_ids(self):
        client = self.client({'ok': True, 'result': {'bodies': 2}},
                             {'ok': True, 'result': None})
        self.assertEqual(client.call('document.inspect'), {'bodies': 2})
        self.assertIsNone(client.execute('ui.test', enabled=True))
        self.assertEqual(self.requests(client), [
            {'id': 1, 'method': 'document.inspect', 'params': {}, 'token': 'test-only-token'},
            {'id': 2, 'method': 'engine.execute',
             'params': {'command': 'ui.test', 'params': {'enabled': True}},
             'token': 'test-only-token'},
        ])
        self.assertEqual(client.io.flush.call_count, 2)

    def test_rejected_authentication_is_not_retried(self):
        client = self.client({'ok': False, 'error': 'Authentication failed'})
        with self.assertRaisesRegex(ControlError, 'Authentication failed'):
            client.call('document.inspect')
        self.assertEqual(len(self.requests(client)), 1)

    def test_lost_timed_out_or_invalid_reply_never_resends_mutation(self):
        for reply, message in ((b'', 'Connection lost'),
                               (socket.timeout('late'), 'may still be running'),
                               (b'not json\n', 'may still be running')):
            with self.subTest(reply=type(reply).__name__):
                client = self.client(reply)
                with self.assertRaisesRegex(ControlError, message):
                    client.execute('component.create', name='test')
                self.assertEqual(len(self.requests(client)), 1)

    def test_oversize_or_nonfinite_requests_are_not_sent(self):
        client = self.client()
        with self.assertRaisesRegex(ControlError, 'too large'):
            client.call('engine.batch', {'data': 'x' * (16 * 1024 * 1024)})
        with self.assertRaises(ValueError):
            client.call('engine.batch', {'value': float('nan')})
        client.io.write.assert_not_called()

    @patch('connection.time.sleep')
    def test_pending_result_is_retrieved_without_repeating_original_command(self, sleep):
        client = self.client(
            {'ok': False, 'running': True},
            {'ok': True, 'result': {'done': False, 'pending': 1}},
            {'ok': True, 'result': {'done': True,
                                  'reply': {'ok': True, 'result': {'completed': 3}}}},
        )
        self.assertEqual(client.execute('component.create', name='test'), {'completed': 3})
        self.assertEqual([r['method'] for r in self.requests(client)],
                         ['engine.execute', 'control.pending', 'control.pending'])
        self.assertEqual(sleep.call_count, 2)

    @patch('connection.time.sleep')
    def test_pending_command_failure_is_reported(self, sleep):
        client = self.client(
            {'ok': False, 'running': True},
            {'ok': True, 'result': {'done': True,
                                  'reply': {'ok': False, 'error': 'Kernel failed'}}},
        )
        with self.assertRaisesRegex(ControlError, 'Kernel failed'):
            client.execute('component.create', name='test')
        self.assertEqual(len(self.requests(client)), 2)

    @patch('connection.time.sleep')
    def test_missing_pending_result_requires_document_check(self, sleep):
        client = self.client({'ok': False, 'running': True},
                             {'ok': True, 'result': {'pending': None}})
        with self.assertRaisesRegex(ControlError, 'Check the document'):
            client.execute('component.create', name='test')
        self.assertEqual(len(self.requests(client)), 2)

    @patch('connection.time.monotonic', side_effect=[0, 3601])
    def test_pending_deadline_does_not_resend(self, monotonic):
        client = self.client({'ok': False, 'running': True})
        with self.assertRaisesRegex(ControlError, 'Do not send the model again'):
            client.execute('component.create', name='test')
        self.assertEqual(len(self.requests(client)), 1)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.client.call = Mock()
        self.before = {'command': 'component.create', 'params': {'name': 'test'}}
        self.step = {'command': 'file.insert_step', 'params': {'path': '/test/part.step'}}
        self.after = {'command': 'component.metadata.set', 'params': {'component': 'test'}}

    def execute_call(self, command, **params):
        return call('engine.execute', {'command': command, 'params': params})

    def test_native_commands_use_atomic_batch(self):
        self.client.call.return_value = {'completed': 1}
        self.assertEqual(self.client.execute_commands([self.before]), {'completed': 1})
        self.client.call.assert_called_once_with(
            'engine.batch', {'commands': [self.before], 'rollback': True})

    def test_mixed_imports_keep_order_and_release_checkpoint(self):
        self.client.call.side_effect = [
            {'checkpoint': 'saved'}, {'completed': 1}, {'warnings': []}, {'completed': 1}, {},
        ]
        result = self.client.execute_commands([self.before, self.step, self.after])
        self.assertEqual(result, {'completed': 3})
        self.assertEqual(self.client.call.call_args_list, [
            self.execute_call('edit.checkpoint'),
            call('engine.batch', {'commands': [self.before], 'rollback': False}),
            self.execute_call('file.insert_step', path='/test/part.step'),
            call('engine.batch', {'commands': [self.after], 'rollback': False}),
            self.execute_call('edit.restore_checkpoint', checkpoint='saved', forget=True),
        ])

    def test_failed_batch_restores_checkpoint_and_stops_before_import(self):
        self.client.call.side_effect = [
            {'checkpoint': 'saved'}, {'failed': {'error': 'Bad extrusion'}}, {},
        ]
        with self.assertRaisesRegex(ControlError, 'Bad extrusion.*\nThe document has been restored'):
            self.client.execute_commands([self.before, self.step, self.after])
        self.assertEqual(self.client.call.call_args_list[-1],
                         self.execute_call('edit.restore_checkpoint', checkpoint='saved'))
        self.assertEqual(self.client.call.call_count, 3)

    def test_step_warning_rejects_import_and_restores_document(self):
        self.client.call.side_effect = [
            {'checkpoint': 'saved'}, {'warnings': ['Missing face']}, {},
        ]
        with self.assertRaisesRegex(ControlError, 'Incomplete STEP import.*\nThe document has been restored'):
            self.client.execute_commands([self.step, self.after])
        self.assertEqual(self.client.call.call_args_list[-1],
                         self.execute_call('edit.restore_checkpoint', checkpoint='saved'))

    def test_failed_restore_does_not_claim_document_was_restored(self):
        self.client.call.side_effect = [
            {'checkpoint': 'saved'}, ControlError('Connection lost'), ControlError('Offline'),
        ]
        with self.assertRaisesRegex(ControlError, 'Connection lost\nRestore not confirmed'):
            self.client.execute_commands([self.step, self.after])
        self.assertEqual(self.client.call.call_count, 3)


class InsertionTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.command = {'command': 'component.create', 'params': {'name': 'test'}}
        self.design = SimpleNamespace(
            commands=Mock(return_value=[self.command]), prepare_assets=Mock(),
            token='test', parts=[],
        )
        self.client.call = Mock()
        self.client.execute_commands = Mock(return_value={'completed': 1})
        self.registry = [{'id': 'component.create'}]

    def test_missing_cad_command_is_rejected_before_mutation(self):
        self.client.call.return_value = []
        with self.assertRaisesRegex(ControlError, 'does not support: component.create'):
            self.client.insert(self.design)
        self.client.execute_commands.assert_not_called()

    def test_active_sketch_is_rejected_before_mutation(self):
        self.client.call.side_effect = [self.registry, {'active_sketch': 'Sketch1'}]
        with self.assertRaisesRegex(ControlError, 'Finish the active sketch'):
            self.client.insert(self.design)
        self.client.execute_commands.assert_not_called()

    def test_native_batch_failure_reports_actual_rollback_status(self):
        for restored in (True, False):
            with self.subTest(restored=restored):
                self.client.call.side_effect = [self.registry, {}]
                self.client.execute_commands.return_value = {
                    'failed': {'index': 0, 'command': 'component.create', 'error': 'Kernel failed'},
                    'rolled_back': restored,
                }
                expected = 'has been restored' if restored else 'restore not confirmed'
                with self.assertRaisesRegex(ControlError, expected):
                    self.client.insert(self.design)

    def test_new_timeline_errors_are_reported_after_insertion(self):
        self.client.call.side_effect = [self.registry, {'timeline': [{'id': 1}]},
                                       {'timeline': [{'id': 1}, {'id': 2, 'error': 'Bad solid'}]}]
        with self.assertRaisesRegex(ControlError, 'CAD created the group.*timeline errors'):
            self.client.insert(self.design)
        self.client.execute_commands.assert_called_once()

    def test_old_timeline_errors_and_optional_view_failure_do_not_repeat_insertion(self):
        previous = {'timeline': [{'id': 1, 'error': 'Existing error'}]}
        self.client.call.side_effect = [self.registry, previous, previous,
                                       ControlError('View unavailable')]
        self.assertEqual(self.client.insert(self.design), {'completed': 1})
        self.client.execute_commands.assert_called_once()


@patch('connection.sys.platform', 'linux')
class LaunchTests(unittest.TestCase):
    @patch('connection.subprocess.Popen')
    @patch('connection.Client')
    def test_connected_cad_is_reused_without_launch(self, client, launch):
        self.assertIn('connected', connect_or_launch('/unused'))
        client.return_value.__enter__.return_value.call.assert_called_once_with('document.inspect')
        launch.assert_not_called()

    @patch('connection.subprocess.Popen')
    @patch('connection.APPIMAGE')
    @patch('connection.Client')
    def test_missing_appimage_reports_error_without_launch(self, client, appimage, launch):
        client.return_value.__enter__.side_effect = ControlError('Offline')
        appimage.is_file.return_value = False
        with self.assertRaisesRegex(ControlError, 'AppImage not found'):
            connect_or_launch('/unused')
        launch.assert_not_called()

    @patch('connection.time.sleep')
    @patch('connection.subprocess.Popen')
    @patch('connection.APPIMAGE')
    @patch('connection.Client')
    def test_launch_reconnects_and_records_log(self, client, appimage, launch, sleep):
        appimage.is_file.return_value = True
        appimage.__str__.return_value = '/test/solidcraft.appimage'
        client.return_value.__enter__.side_effect = [ControlError('Offline'), Mock()]
        launch.return_value.poll.return_value = None
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn('launched and connected', connect_or_launch(folder))
            self.assertTrue((Path(folder) / 'solidcraft-avvio.log').is_file())
        self.assertEqual(launch.call_args.args[0], ['/test/solidcraft.appimage', '--control', '7878'])
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        self.assertEqual(client.return_value.__enter__.call_count, 2)


if __name__ == '__main__':
    unittest.main()
