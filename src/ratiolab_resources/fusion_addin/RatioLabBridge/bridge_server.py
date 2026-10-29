# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Authenticated loopback transport. This module never imports or calls adsk."""
from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import secrets
import socket
import sys
import threading
import uuid

PROTOCOL = 'ratiolab-fusion/1'
MAX_REQUEST = 65536
MAX_JOBS = 256


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Non-finite JSON number')
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Non-finite JSON number')
        return result
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def endpoint_path():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))
        return base/'RatioLab/fusion-bridge/endpoint.json'
    return Path.home()/'Library/Application Support/RatioLab/fusion-bridge/endpoint.json'


@dataclass
class Job:
    request_id: str
    fingerprint: str
    method: str
    params: dict
    event: threading.Event = field(default_factory=threading.Event)
    reply: dict = None
    started: bool = False


class BridgeServer:
    """Queue work for a CustomEvent handler on Fusion's main thread.

    Once accepted, mutations stay in the session's idempotency table, even if
    the caller disconnects or times out. Retrying the same id only fetches the
    existing outcome; changing its payload is rejected. Capacity exhaustion
    rejects new work instead of forgetting a previous mutation.
    """
    def __init__(self, fire_event, execute, *, endpoint=None, wait_seconds=120):
        self.fire_event = fire_event
        self.execute = execute
        self.endpoint = Path(endpoint) if endpoint else endpoint_path()
        self.wait_seconds = wait_seconds
        self.session_id = str(uuid.uuid4())
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.jobs = OrderedDict()
        self.pending = queue.Queue(maxsize=16)
        self.stopping = threading.Event()
        self.slots = threading.BoundedSemaphore(8)
        self.listener = None
        self.thread = None

    def start(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Never enable SO_REUSEADDR on Windows: another process could steal it.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        listener.settimeout(.25)
        self.listener = listener
        info = dict(protocol=PROTOCOL, host='127.0.0.1',
                    port=listener.getsockname()[1], token=self.token,
                    pid=os.getpid(), session_id=self.session_id)
        try:
            self.endpoint.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.endpoint.with_name('.endpoint-' + self.session_id + '.tmp')
            descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                    json.dump(info, stream)
                os.replace(temporary, self.endpoint)
            finally:
                temporary.unlink(missing_ok=True)
            self.thread = threading.Thread(target=self._listen, daemon=True,
                                           name='RatioLab Fusion bridge')
            self.thread.start()
        except Exception:
            listener.close()
            self.listener = None
            raise
        return info

    def _listen(self):
        while not self.stopping.is_set():
            try:
                connection, address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if address[0] != '127.0.0.1' or not self.slots.acquire(False):
                connection.close()
                continue
            threading.Thread(target=self._connection, args=(connection,),
                             daemon=True, name='RatioLab Fusion request').start()

    def _connection(self, connection):
        request_id = None
        try:
            with connection:
                try:
                    connection.settimeout(5)
                    data = bytearray()
                    while b'\n' not in data:
                        block = connection.recv(min(4096, MAX_REQUEST + 1 - len(data)))
                        if not block:
                            raise ValueError('A newline-terminated JSON request is required')
                        data.extend(block)
                        if len(data) > MAX_REQUEST:
                            raise ValueError('Request exceeds the size limit')
                    line, extra = bytes(data).split(b'\n', 1)
                    if extra.strip():
                        raise ValueError('One request per connection is required')
                    request = strict_json(line.decode('utf-8'))
                    request_id = request.get('id') if isinstance(request, dict) else None
                    reply = self.request(request)
                except (ValueError, TypeError) as error:
                    reply = dict(id=request_id, ok=False, error=str(error))
                connection.settimeout(5)
                connection.sendall(json.dumps(reply, allow_nan=False).encode('utf-8') + b'\n')
        except OSError:
            pass
        finally:
            self.slots.release()

    def request(self, request):
        if not isinstance(request, dict) or request.get('protocol') != PROTOCOL:
            raise ValueError('Unsupported bridge protocol')
        token = request.get('token')
        if not isinstance(token, str) or not secrets.compare_digest(token, self.token):
            raise ValueError('Bridge authentication failed')
        request_id = request.get('id')
        try:
            if not isinstance(request_id, str):
                raise ValueError()
            uuid.UUID(request_id)
        except (ValueError, AttributeError):
            raise ValueError('Request id must be a UUID') from None
        method, params = request.get('method'), request.get('params', {})
        if method not in ('status', 'import_model'):
            raise ValueError('Unsupported bridge method')
        if not isinstance(params, dict):
            raise ValueError('Request params must be an object')
        fingerprint = hashlib.sha256(json.dumps([method, params], sort_keys=True,
                                                allow_nan=False).encode('utf-8')).hexdigest()
        with self.lock:
            if self.stopping.is_set():
                raise ValueError('Fusion bridge is stopping')
            job = self.jobs.get(request_id)
            if job is not None:
                if job.fingerprint != fingerprint:
                    raise ValueError('Request id was already used for a different payload')
            else:
                # Completed status probes are safe to discard; imports are not.
                if len(self.jobs) >= MAX_JOBS:
                    for key, previous in list(self.jobs.items()):
                        if previous.method == 'status' and previous.event.is_set():
                            del self.jobs[key]
                            break
                if len(self.jobs) >= MAX_JOBS:
                    raise ValueError('Session request capacity reached; restart the add-in')
                if self.pending.full():
                    raise ValueError('Fusion bridge is busy; wait for pending work')
                job = Job(request_id, fingerprint, method, params)
                self.jobs[request_id] = job
                self.pending.put_nowait(job)
                try:
                    # Some native Fusion SDK builds return False even when
                    # the event was queued and subsequently delivered. Only
                    # an exception proves a dispatch failure; handler
                    # completion (or an unknown-outcome timeout) is decisive.
                    self.fire_event()
                except Exception as error:
                    # This executes on a socket thread: do not call app.log or
                    # any other SDK method here. Keep native dispatch failures
                    # locally, with credentials redacted and no request data.
                    try:
                        details = (type(error).__name__ + ': ' + str(error)).replace(self.token, '[redacted]')
                        self.endpoint.with_name('dispatch-error.log').write_text(details[:4096] + '\n', encoding='utf-8')
                    except OSError:
                        pass
                    job.reply = dict(id=request_id, ok=False,
                                     error='Could not dispatch work to Fusion')
                    job.event.set()
        if not job.event.wait(self.wait_seconds):
            return dict(id=request_id, ok=False, running=True,
                        error='Fusion has not finished; query the same request id for its outcome')
        return job.reply

    def drain(self):
        """Called ONLY by the Fusion CustomEvent handler on the main thread."""
        while True:
            try:
                job = self.pending.get_nowait()
            except queue.Empty:
                return
            with self.lock:
                if job.event.is_set():
                    continue
                if self.stopping.is_set():
                    job.reply = dict(id=job.request_id, ok=False, error='Fusion bridge stopped')
                    job.event.set()
                    continue
                job.started = True
            try:
                result = self.execute(job.method, job.params)
                reply = dict(id=job.request_id, ok=True, result=result)
            except Exception as error:
                reply = dict(id=job.request_id, ok=False, error=str(error))
            with self.lock:
                job.reply = reply
                job.event.set()

    def stop(self):
        self.stopping.set()
        if self.listener is not None:
            self.listener.close()
        with self.lock:
            for job in self.jobs.values():
                if not job.event.is_set() and not job.started:
                    job.reply = dict(id=job.request_id, ok=False, error='Fusion bridge stopped')
                    job.event.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
        try:
            # Do not remove discovery data published by a later Fusion session.
            value = strict_json(self.endpoint.read_text(encoding='utf-8'))
            if value.get('session_id') == self.session_id:
                self.endpoint.unlink(missing_ok=True)
        except (OSError, ValueError, AttributeError):
            pass
