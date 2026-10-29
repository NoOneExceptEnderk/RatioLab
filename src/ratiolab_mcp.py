# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Offline MCP stdio adapter: 2026-07-28 and legacy 2025-11-25, tools only.

Stdout is reserved for newline-delimited JSON-RPC; diagnostics belong on stderr.
The reader stays available for cancellation while bounded workers run headless
service operations. Geometry validation remains in the shared core.
"""
import argparse
import inspect
import json
from queue import Queue, Full, Empty
import sys
from threading import Event, Lock, Thread
import traceback

from ratiolab_agent import AgentError, AgentService, Limits
from release_version import RELEASE_VERSION

MODERN = '2026-07-28'
LEGACY = '2025-11-25'
SUPPORTED = [MODERN, LEGACY]
PREFIX = 'io.modelcontextprotocol/'
IDENTITY = dict(name='RatioLab', version=RELEASE_VERSION)
INSTRUCTIONS = ('Local offline mechanical design tools. All file paths are relative to the explicitly granted workspace. '
                'Discover families/options first. Keep the returned opaque handle and revision; refresh with project_list '
                'after a stale_revision error. Existing files require explicit overwrite and a matching disk fingerprint. '
                'Exports are nominal geometry; headless packages contain no screenshot. Read reported geometric limits.')

STRING = dict(type='string', minLength=1)
INTEGER = dict(type='integer', minimum=0)
OBJECT = dict(type='object')
COMPONENTS = dict(type='array', minItems=1, maxItems=128, uniqueItems=True,
                  items=dict(type='integer', minimum=1), description='1-based current source positions, tied to revision.')
REFERENCE = dict(handle=STRING, revision=INTEGER)
PARAMETERS = dict(type='object', description='Patch of known geometric parameters/options; discovery lists accepted keys.')


def tool(method, description, properties, required=(), read_only=False, destructive=False):
    return dict(name='ratiolab.'+method, title=method.replace('_',' ').title(), description=description,
                inputSchema=dict(type='object', properties=properties, required=list(required), additionalProperties=False),
                annotations=dict(readOnlyHint=read_only, destructiveHint=destructive, openWorldHint=False))


TOOLS = [
    tool('discover', 'List available families and limits, or numeric specs, defaults, variants, I/O, bearing/hardware options for one family.',
         dict(family=STRING, variant=STRING, double_style=STRING, parameters=PARAMETERS), read_only=True),
    tool('project_create', 'Generate and validate a new in-memory project; return handle/revision and canonical parameters.',
         dict(family=STRING, parameters=PARAMETERS), ['family']),
    tool('project_open', 'Import only a complete UTF-8 JSON solidcraft-riduttori/1 configuration from the workspace.',
         dict(path=STRING), ['path']),
    tool('project_list', 'List live handles, revisions, paths and parameters; handles expire with the server process.', {}, read_only=True),
    tool('project_update', 'Atomically validate/generate a parameter patch before committing a new project revision.',
         dict(**REFERENCE, parameters=PARAMETERS), ['handle','revision','parameters']),
    tool('project_history', 'Undo or redo one validated Document state; always check the current revision first.',
         dict(**REFERENCE, action=dict(type='string', enum=['undo','redo'])), ['handle','revision','action']),
    tool('project_save', 'Save UTF-8 JSON atomically. Default refuses existing files; explicit overwrite requires this handle’s unchanged opened/saved file.',
         dict(**REFERENCE, path=STRING, overwrite=dict(type='boolean', default=False)), ['handle','revision','path'], destructive=True),
    tool('project_close', 'Discard this in-memory handle, including unsaved edits; disk files are preserved.',
         REFERENCE, ['handle','revision'], destructive=True),
    tool('project_describe', 'Describe nominal components, generated profile metadata, bounds, analysis, warnings and geometric limits.',
         dict(**REFERENCE, components=COMPONENTS), ['handle','revision'], read_only=True),
    tool('bom', 'Build the real BOM, machining, procurement and source-model calculations; optionally select components.',
         dict(**REFERENCE, components=COMPONENTS), ['handle','revision'], read_only=True),
    tool('export', 'Publish a new directory atomically: real STEP/STL, SVG+DXF sections, BOM or headless package with CAD script/assets/config/manifest. No PNG. svg/dxf also includes its companion format to preserve profile metadata.',
         dict(**REFERENCE, path=STRING, kind=dict(type='string', enum=['step','stl','svg','dxf','profiles','package'], default='package'), components=COMPONENTS),
         ['handle','revision','path']),
    tool('search', 'Finite geometric combination search, within server candidate/time/result limits; partial reports are explicit. Assembly families only.',
         dict(**REFERENCE, axes=dict(type='object', additionalProperties=dict(type='array', minItems=1, maxItems=100, items=dict(type='number'))), settings=OBJECT),
         ['handle','revision','axes'], read_only=True),
    tool('interference', 'Bounded discrete motion/triangle interference check; incomplete/unsupported coverage is explicit, never a certification.',
         dict(**REFERENCE, settings=OBJECT), ['handle','revision'], read_only=True),
]
TOOLS.sort(key=lambda entry: entry['name'])
TOOL_MAP = {entry['name']: entry for entry in TOOLS}


class RpcError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code, self.data = code, data


def error_response(error, request_id=None):
    payload = dict(code=error.code, message=str(error))
    if error.data is not None:
        payload['data'] = error.data
    return dict(jsonrpc='2.0', id=request_id, error=payload)


def _type_matches(value, expected):
    return {'object':isinstance(value,dict), 'array':isinstance(value,list), 'string':type(value) is str,
            'integer':type(value) is int, 'number':type(value) in (int,float), 'boolean':type(value) is bool}[expected]


def validate_arguments(arguments, schema):
    """Validate the declared small schema subset; deeper geometry uses core validators."""
    if not _type_matches(arguments, schema['type']):
        raise RpcError(-32602, 'Tool arguments must match the advertised input schema.')
    if schema['type'] == 'object':
        if not set(schema.get('required',())) <= arguments.keys():
            raise RpcError(-32602, 'Missing required tool arguments.')
        properties = schema.get('properties',{})
        if schema.get('additionalProperties') is False and arguments.keys()-properties.keys():
            raise RpcError(-32602, 'Unknown tool argument fields.')
        for key, value in arguments.items():
            child = properties.get(key, schema.get('additionalProperties'))
            if isinstance(child,dict):
                validate_arguments(value, child)
    elif schema['type'] == 'array':
        if not schema.get('minItems',0) <= len(arguments) <= schema.get('maxItems',1000000):
            raise RpcError(-32602, 'Tool array size is outside schema limits.')
        if schema.get('uniqueItems') and len({json.dumps(value,sort_keys=True) for value in arguments}) != len(arguments):
            raise RpcError(-32602, 'Duplicate array items.')
        for value in arguments:
            validate_arguments(value, schema['items'])
    elif schema['type'] in ('integer','number'):
        from math import isfinite
        if not -1e100 <= arguments <= 1e100 or not isfinite(arguments) \
                or arguments < schema.get('minimum',-1e100):
            raise RpcError(-32602, 'Tool number is not finite or below its minimum.')
    elif schema['type'] == 'string' and len(arguments) < schema.get('minLength',0):
        raise RpcError(-32602, 'Tool string is empty.')
    if 'enum' in schema and arguments not in schema['enum']:
        raise RpcError(-32602, 'Tool value is outside the advertised enumeration.')


class Server:
    def __init__(self, service):
        self.service = service
        self.initialized = False
        self.ready = False

    def prepare(self, message):
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'),str):
            raise RpcError(-32600, 'Expected one JSON-RPC 2.0 request or notification; batches are unsupported.')
        if 'id' in message and (type(message['id']) not in (str,int) or isinstance(message['id'],str) and len(message['id'])>128):
            raise RpcError(-32600, 'Request id must be a non-null string or integer.')
        params = message.get('params',{})
        if not isinstance(params,dict):
            raise RpcError(-32602, 'Request params must be an object.')
        method = message['method']
        modern = False
        if 'id' not in message:
            return method, params, modern
        meta = params.get('_meta',{})
        if not isinstance(meta,dict):
            raise RpcError(-32602, '_meta must be an object.')
        if PREFIX+'protocolVersion' in meta:
            version = meta[PREFIX+'protocolVersion']
            if not isinstance(version,str):
                raise RpcError(-32602, 'Per-request protocolVersion must be a string.')
            if version != MODERN:
                raise RpcError(-32022, 'Unsupported protocol version', dict(supported=SUPPORTED,requested=version))
            if not isinstance(meta.get(PREFIX+'clientCapabilities'),dict):
                raise RpcError(-32602, 'Modern requests require per-request clientCapabilities metadata.')
            modern = True
        elif method == 'server/discover':
            raise RpcError(-32602, 'Modern discovery requires per-request protocol metadata.')
        elif method != 'initialize' and not (method == 'ping' or self.ready):
            raise RpcError(-32602, 'Complete initialize/notifications/initialized, or send modern per-request metadata.')
        return method, params, modern

    @staticmethod
    def result(request_id, value, modern):
        if modern:
            value = dict(value, resultType='complete', _meta={PREFIX+'serverInfo':IDENTITY})
        return dict(jsonrpc='2.0', id=request_id, result=value)

    def invoke_tool(self, params, cancel):
        if params.keys()-{'name','arguments','_meta'}:
            raise RpcError(-32602, 'Unsupported tools/call fields (no tasks or multi-round-trip inputs).')
        name = params.get('name')
        if not isinstance(name,str) or name not in TOOL_MAP:
            raise RpcError(-32602, 'Unknown tool name.')
        arguments = params.get('arguments',{})
        entry = TOOL_MAP[name]
        validate_arguments(arguments, entry['inputSchema'])
        method = getattr(self.service, name.split('.',1)[1])
        try:
            inspect.signature(method).bind(**arguments, cancel=cancel)
        except TypeError as error:
            raise RpcError(-32602, 'Tool arguments do not match its signature.') from error
        try:
            value = method(**arguments, cancel=cancel)
            failed = False
        except AgentError as error:
            value, failed = dict(error=error.data()), True
        except OSError as error:
            value, failed = dict(error=dict(code='filesystem_error',message='Workspace filesystem operation failed.',
                                           details=dict(errno=error.errno, kind=type(error).__name__))), True
        result = dict(content=[dict(type='text',text=json.dumps(value,ensure_ascii=False,allow_nan=False))],
                      structuredContent=value, isError=failed)
        if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8')) > self.service.limits.result_bytes:
            value = dict(error=dict(code='resource_limit',message='Tool result exceeds response limit; request a smaller subset or budget.',details={}))
            return dict(content=[dict(type='text',text=json.dumps(value))],structuredContent=value,isError=True)
        return result

    def execute(self, message, prepared=None, cancel=None):
        method, params, modern = prepared or self.prepare(message)
        if 'id' not in message:
            if method == 'notifications/initialized' and self.initialized:
                self.ready = True
            return None
        if method == 'initialize':
            if modern or self.initialized:
                raise RpcError(-32602, 'initialize is a legacy-only, once-per-process handshake.')
            if not isinstance(params.get('protocolVersion'),str) or not isinstance(params.get('capabilities'),dict) \
                    or not isinstance(params.get('clientInfo'),dict):
                raise RpcError(-32602, 'initialize requires protocolVersion, capabilities and clientInfo.')
            if any(not isinstance(params['clientInfo'].get(key),str) or not params['clientInfo'][key]
                   for key in ('name','version')):
                raise RpcError(-32602, 'clientInfo requires non-empty name and version strings.')
            self.initialized = True
            value = dict(protocolVersion=LEGACY, capabilities=dict(tools={}), serverInfo=IDENTITY, instructions=INSTRUCTIONS)
        elif method == 'server/discover':
            if params.keys()-{'_meta'}:
                raise RpcError(-32602, 'Discovery accepts only standard metadata.')
            value = dict(supportedVersions=SUPPORTED, capabilities=dict(tools={}), instructions=INSTRUCTIONS)
        elif method == 'ping' and not modern:
            value = {}
        elif method == 'tools/list':
            if params.keys()-{'_meta','cursor'} or params.get('cursor') is not None:
                raise RpcError(-32602, 'The complete deterministic tool list fits in one page; no cursor is accepted.')
            value = dict(tools=TOOLS)
        elif method == 'tools/call':
            value = self.invoke_tool(params, cancel or Event())
        else:
            raise RpcError(-32601, 'Method not found; this server advertises tools only.')
        if modern and method in ('server/discover', 'tools/list'):
            value.update(ttlMs=0, cacheScope='private')
        return self.result(message['id'], value, modern)

    def process(self, message, cancel=None):
        try:
            return self.execute(message, cancel=cancel)
        except RpcError as error:
            if isinstance(message,dict) and 'id' not in message and isinstance(message.get('method'),str):
                return None
            request_id = message.get('id') if isinstance(message,dict) and type(message.get('id')) in (str,int) else None
            return error_response(error, request_id)


def serve(service, input_stream=None, output_stream=None):
    """Read notifications during tool work; bound pending input, output and workers."""
    source = input_stream or sys.stdin.buffer
    destination = output_stream or sys.stdout.buffer
    server = Server(service)
    queue = Queue(maxsize=8)
    active, active_lock, output_lock = {}, Lock(), Lock()
    stopping = Event()

    def send(value):
        if value is not None and not stopping.is_set():
            data = (json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')
            with output_lock:
                destination.write(data); destination.flush()

    def worker():
        while not stopping.is_set():
            try:
                message, prepared, cancel = queue.get(timeout=.1)
            except Empty:
                continue
            try:
                try:
                    result = server.execute(message, prepared, cancel)
                except RpcError as error:
                    result = error_response(error,message['id'])
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    result = error_response(RpcError(-32603,'Internal error; see server stderr.'),message['id'])
                with active_lock:
                    if not cancel.is_set():
                        send(result)
                    active.pop(message['id'],None)
            finally:
                queue.task_done()

    workers = [Thread(target=worker,daemon=True,name='ratiolab-mcp-worker') for _ in range(2)]
    for thread in workers:
        thread.start()
    try:
        while True:
            raw = source.readline(service.limits.input_bytes+1)
            if not raw:
                break
            if len(raw) > service.limits.input_bytes:
                while raw and not raw.endswith(b'\n'):
                    raw = source.readline(service.limits.input_bytes+1)
                send(error_response(RpcError(-32600,'Message exceeds the configured byte limit.')))
                continue
            if not raw.strip():
                continue
            if not raw.endswith(b'\n'):
                send(error_response(RpcError(-32700,'Incomplete newline-delimited JSON-RPC frame.')))
                continue
            try:
                message = json.loads(raw.decode('utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (ValueError,UnicodeError,RecursionError):
                send(error_response(RpcError(-32700,'Invalid UTF-8 JSON.')))
                continue
            try:
                prepared = server.prepare(message)
                method, params, modern = prepared
                if 'id' not in message:
                    if method == 'notifications/cancelled':
                        request_id = params.get('requestId')
                        if type(request_id) in (str,int):
                            with active_lock:
                                if request_id in active:
                                    active[request_id].set()
                    else:
                        server.execute(message, prepared)
                    continue
                with active_lock:
                    if message['id'] in active:
                        raise RpcError(-32600,'Duplicate in-flight request id.')
                if method != 'tools/call':
                    send(server.execute(message, prepared))
                    continue
                request_id = message['id']
                cancel = Event()
                with active_lock:
                    if request_id in active:
                        raise RpcError(-32600,'Duplicate in-flight request id.')
                    active[request_id] = cancel
                    try:
                        queue.put_nowait((message,prepared,cancel))
                    except Full:
                        del active[request_id]
                        raise RpcError(-32603,'Server work queue is full; retry after a response.')
            except RpcError as error:
                if not isinstance(message,dict) or 'id' in message:
                    request_id = message.get('id') if isinstance(message,dict) and type(message.get('id')) in (str,int) else None
                    send(error_response(error,request_id))
    except (BrokenPipeError,KeyboardInterrupt):
        pass
    finally:
        stopping.set()
        with active_lock:
            for cancel in active.values():
                cancel.set()
        for thread in workers:
            thread.join(timeout=.5)
        # A non-preemptible core unit may still be finishing. Daemon workers
        # cannot delay stdio process exit; they check cancellation before any
        # publication. Avoid deleting a staging directory under an active writer.
        if not any(thread.is_alive() for thread in workers):
            service.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='RatioLab local offline MCP server (stdio).')
    parser.add_argument('--workspace', required=True, help='Explicit absolute workspace granted to this server.')
    args = parser.parse_args(argv)
    try:
        service = AgentService(args.workspace)
    except (AgentError,OSError) as error:
        print(str(error),file=sys.stderr)
        return 2
    return serve(service)


if __name__ == '__main__':
    raise SystemExit(main())
