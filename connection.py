"""Client del protocollo SolidCraft: localhost, autenticazione, batch atomico."""
import json
import os
import shutil
import sys
from pathlib import Path
import socket
import subprocess
import time
from external_programs import child_environment, system_library_search

PORT = 7878
APPIMAGE = Path.home() / 'AppImages/solidcraft.appimage'


def control_directory():
    configured = os.environ.get('SOLIDCRAFT_CONTROL_DIR')
    if configured:
        folder = Path(configured).expanduser()
        if folder.is_absolute():
            return folder
        raise ControlConfigurationError('SOLIDCRAFT_CONTROL_DIR must be an absolute path to the CAD token directory.')
    if sys.platform != 'linux':
        raise ControlConfigurationError('Set SOLIDCRAFT_CONTROL_DIR to the token directory of your '
                                        'SolidCraft installation. STL export needs no CAD connection.')
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    return data / 'solidcraft/control'


class ControlError(RuntimeError):
    pass


class ControlConfigurationError(ControlError):
    pass


class Client:
    def __init__(self, port=PORT):
        self.port = port
        self.sock = None
        self.io = None
        self.seq = 0

    def __enter__(self):
        folder = control_directory()
        try:
            self.token = (folder / f'{self.port}.token').read_text(encoding='utf-8').strip()
        except OSError as e:
            raise ControlError('SolidCraft is disconnected. Click Connect SolidCraft.') from e
        try:
            self.sock = socket.create_connection(('127.0.0.1', self.port), timeout=5)
            self.sock.settimeout(3700)
            self.io = self.sock.makefile('rwb')
        except OSError as e:
            self.__exit__()
            raise ControlError(
                f'SolidCraft is not responding on local port {self.port}. '
                'Click Connect SolidCraft.'
            ) from e
        return self

    def __exit__(self, *args):
        try:
            if self.io:
                self.io.close()
        finally:
            if self.sock:
                self.sock.close()

    def call(self, method, params=None):
        self.seq += 1
        request = {'id': self.seq, 'method': method, 'params': params or {}, 'token': self.token}
        payload = (json.dumps(request, separators=(',', ':'), allow_nan=False) + '\n').encode()
        if len(payload) > 16 * 1024 * 1024:
            raise ControlError('Model too large for the local protocol.')
        try:
            self.io.write(payload)
            self.io.flush()
            line = self.io.readline(32 * 1024 * 1024)
            if not line:
                raise ControlError('Connection lost. Check the CAD document before trying again.')
            reply = json.loads(line)
        except (OSError, ValueError) as e:
            raise ControlError(
                'No response available. The operation may still be running: '
                'check SolidCraft before trying again.'
            ) from e
        if not reply.get('ok'):
            if reply.get('running'):
                # Never resend a timed-out mutation. Retrieve its original reply on this connection.
                deadline = time.monotonic() + 3600
                while time.monotonic() < deadline:
                    time.sleep(1)
                    pending = self.call('control.pending')
                    if pending.get('done'):
                        original = pending.get('reply', {})
                        if not original.get('ok'):
                            raise ControlError(original.get('error', 'CAD operation failed'))
                        return original.get('result')
                    if pending.get('pending') is None:
                        raise ControlError('Could not retrieve the result. Check the document before trying again.')
                raise ControlError('CAD is still working. Do not send the model again: wait and check SolidCraft.')
            raise ControlError(reply.get('error', 'SolidCraft error'))
        return reply.get('result')

    def execute(self, command, **params):
        return self.call('engine.execute', {'command': command, 'params': params})

    def execute_commands(self, commands):
        if not any(c['command'] == 'file.insert_step' for c in commands):
            return self.call('engine.batch', {'commands': commands, 'rollback': True})
        # The control protocol refuses file reads inside engine.batch. One explicit
        # checkpoint spans the interleaved imports and modelling batches instead.
        checkpoint = self.execute('edit.checkpoint')['checkpoint']
        completed = 0
        pending = []

        def flush():
            nonlocal completed, pending
            if not pending:
                return
            result = self.call('engine.batch', {'commands': pending, 'rollback': False})
            if result.get('failed'):
                raise ControlError(str(result['failed']))
            completed += len(pending)
            pending = []

        try:
            for command in commands:
                if command['command'] != 'file.insert_step':
                    pending.append(command)
                    continue
                flush()
                imported = self.execute(command['command'], **command['params'])
                if imported.get('warnings'):
                    raise ControlError('Incomplete STEP import: ' + str(imported['warnings'][:3]))
                completed += 1
            flush()
            self.execute('edit.restore_checkpoint', checkpoint=checkpoint, forget=True)
            return {'completed': completed}
        except Exception as error:
            try:
                self.execute('edit.restore_checkpoint', checkpoint=checkpoint)
                restored = 'The document has been restored.'
            except Exception:
                restored = 'Restore not confirmed: check the document before trying again.'
            raise ControlError(str(error) + '\n' + restored) from error

    def insert(self, design, visible_roles=None, asset_dir=None):
        design.prepare_assets(asset_dir)
        commands = design.commands(asset_dir)
        registry = self.call('engine.commands')
        known = {c['id'] for c in registry}
        missing = {c['command'] for c in commands} - known
        if missing:
            raise ControlError('This CAD version does not support: ' + ', '.join(sorted(missing)))
        before = self.call('document.inspect')
        if before.get('active_sketch'):
            raise ControlError('Finish the active sketch in SolidCraft before inserting the model.')
        result = self.execute_commands(commands)
        if result.get('failed'):
            failure = result['failed']
            restored = result.get('rolled_back', False)
            message = ('The document has been restored.' if restored
                       else 'Check the document: restore not confirmed.')
            raise ControlError(
                f"Command {failure.get('index')}: {failure.get('command')}\n"
                f"{failure.get('error')}\n{message}"
            )
        # Check error rows as some kernel failures are stored on the timeline instead of thrown.
        after = self.call('document.inspect')
        old = {str(t.get('id')) for t in before.get('timeline', [])}
        errors = [t for t in after.get('timeline', [])
                  if str(t.get('id')) not in old and t.get('error')]
        if errors:
            raise ControlError(
                'CAD created the group but reported timeline errors. Check SolidCraft:\n'
                + str(errors)[:1800]
            )
        if visible_roles is not None:
            hidden = [f'{design.token}_{i}_{p.name}_body'
                      for i, p in enumerate(design.parts) if p.role not in visible_roles]
            if hidden:
                self.execute('browser.visibility', visible=False, items=hidden)
        if any(p.stations or p.double or abs(p.twist) > 1e-8 for p in design.parts):
            try:
                self.call('ui.set', {'visualStyle': 1})
            except ControlError:
                pass
        try:
            self.call('ui.view', {'view': 'iso'})
            self.call('ui.view', {'view': 'fit'})
        except ControlError:
            pass
        return result


def connect_or_launch(log_dir):
    try:
        with Client() as c:
            c.call('document.inspect')
        return 'SolidCraft connected on local port 7878.'
    except ControlConfigurationError:
        raise
    except (ControlError, OSError):
        pass
    configured = os.environ.get('SOLIDCRAFT_EXECUTABLE')
    if configured:
        executable = Path(shutil.which(configured) or configured).expanduser()
        if not executable.is_file():
            raise ControlError(f'SOLIDCRAFT_EXECUTABLE not found: {executable}')
    elif sys.platform == 'linux':
        executable = APPIMAGE
        if not executable.is_file():
            raise ControlError(f'AppImage not found: {APPIMAGE}. Launch SolidCraft with --control 7878 '
                               'or set SOLIDCRAFT_EXECUTABLE. STL export needs no CAD connection.')
    else:
        raise ControlError('No SolidCraft executable configured on this platform. '
                           'If a compatible CAD installation is available, launch it with '
                           '--control 7878 and set SOLIDCRAFT_CONTROL_DIR; optionally set '
                           'SOLIDCRAFT_EXECUTABLE to its executable. STL export needs no CAD connection.')
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / 'solidcraft-avvio.log').open('ab') as log:
        with system_library_search():
            proc = subprocess.Popen(
                [str(executable), '--control', str(PORT)], env=child_environment(),
                stdout=log, stderr=log, start_new_session=(sys.platform != 'win32')
            )
    for _ in range(90):
        if proc.poll() is not None:
            raise ControlError(f'SolidCraft exited. Details in {log_dir}/solidcraft-avvio.log')
        time.sleep(.35)
        try:
            with Client() as c:
                c.call('document.inspect')
            return 'SolidCraft launched and connected.'
        except (ControlError, OSError):
            pass
    raise ControlError('Launch has not completed. Check SolidCraft and click Connect SolidCraft again.')
