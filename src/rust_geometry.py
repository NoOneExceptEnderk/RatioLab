# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Transport to the Rust kernel. Mathematical calculations run in Rust.

Decimal strings are retained by the protocol; callers must not convert precise
source text to float before this boundary. The browser adapter exposes the same
synchronous request through its already instantiated WebAssembly module.
"""
from functools import lru_cache
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
import pickle
from threading import RLock
import json
import os
from pathlib import Path
import sys


PROTOCOL = 1
_control = ContextVar('ratiolab_geometry_control', default=None)
_constructions = OrderedDict()
_construction_lock = RLock()
_construction_bytes = 0
_construction_hits = 0
_construction_misses = 0
CONSTRUCTION_ENTRIES = 64
CONSTRUCTION_BYTES = 8*1024*1024


@contextmanager
def control_scope(check):
    """Request-local cooperative cancellation; never retain callbacks in caches."""
    previous = _control.get()
    def combined():
        if previous:previous()
        if check:check()
    token = _control.set(combined)
    try:yield
    finally:_control.reset(token)


def control_check(check=None):
    inherited = _control.get()
    if inherited:inherited()
    if check and check is not inherited:check()


def _with_control(check):
    inherited = _control.get()
    if inherited is None:return check
    if check is None or check is inherited:return inherited
    def combined():
        inherited();check()
    return combined


def cached_call(operation, parameters, check=None):
    """Detached successful construction records, bounded by exact input bytes.

    Pickle is produced and consumed internally only. It preserves float bits,
    source decimal expressions and nested mutations; no wire/file pickle is read.
    Retain the backend owner alongside its epoch to prevent identity reuse.
    """
    global _construction_bytes, _construction_hits, _construction_misses
    if operation not in ('gear_part','internal_axial_derived'):
        raise ValueError('Only immutable construction records may be cached.')
    control_check(check)
    owner, identity = backend()
    snapshot = pickle.dumps(parameters, protocol=5)
    key = (identity, PROTOCOL, operation, snapshot)
    with _construction_lock:
        existing = _constructions.pop(key, None)
        if existing is not None:
            _constructions[key] = existing
            _construction_hits += 1
        else:_construction_misses += 1
    if existing is not None:
        result = pickle.loads(existing[1])
        control_check(check)
        return result
    result = call(operation, pickle.loads(snapshot), check, _backend=owner)
    encoded = pickle.dumps(result, protocol=5)
    size = len(snapshot)+len(encoded)
    control_check(check)
    if size <= CONSTRUCTION_BYTES:
        with _construction_lock:
            replaced = _constructions.pop(key, None)
            if replaced is not None:_construction_bytes -= len(snapshot)+len(replaced[1])
            while _constructions and (len(_constructions)>=CONSTRUCTION_ENTRIES or _construction_bytes+size>CONSTRUCTION_BYTES):
                old, value = _constructions.popitem(last=False)
                _construction_bytes -= len(old[3])+len(value[1])
            _constructions[key] = (owner, encoded)
            _construction_bytes += size
    return result


def clear_construction_cache():
    global _construction_bytes
    with _construction_lock:
        _constructions.clear();_construction_bytes = 0


def construction_cache_info():
    with _construction_lock:
        return dict(entries=len(_constructions),bytes=_construction_bytes,
            hits=_construction_hits,misses=_construction_misses,
            max_entries=CONSTRUCTION_ENTRIES,max_bytes=CONSTRUCTION_BYTES)


@lru_cache(maxsize=1)
def _library():
    import ctypes
    name = ('ratiolab_geometry.dll' if sys.platform == 'win32' else
            'libratiolab_geometry.dylib' if sys.platform == 'darwin' else
            'libratiolab_geometry.so')
    explicit = os.environ.get('RATIOLAB_GEOMETRY_LIBRARY')
    if explicit:
        candidates = [Path(explicit)]
    else:
        from app_paths import resource_path
        root = Path(__file__).resolve().parent.parent
        try:
            bundled = resource_path('native')/name
        except FileNotFoundError:
            bundled = root/'src/ratiolab_resources/native'/name
        candidates = [bundled, root/'target/release'/name]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise RuntimeError('Rust geometry library is missing. Build it with scripts/build-rust-engine.py.')
    library = ctypes.CDLL(str(path.resolve()))
    library.ratiolab_request.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    library.ratiolab_request.restype = ctypes.c_void_p
    library._check_type = ctypes.CFUNCTYPE(ctypes.c_int)
    library.ratiolab_request_checked.argtypes = (ctypes.c_void_p, ctypes.c_size_t, library._check_type)
    library.ratiolab_request_checked.restype = ctypes.c_void_p
    library.ratiolab_result_length.argtypes = (ctypes.c_void_p,)
    library.ratiolab_result_length.restype = ctypes.c_size_t
    library.ratiolab_free.argtypes = (ctypes.c_void_p,)
    library.ratiolab_free.restype = None
    library.ratiolab_buffer_request.argtypes = (ctypes.c_void_p,ctypes.c_size_t)
    library.ratiolab_buffer_request.restype = ctypes.c_void_p
    library.ratiolab_buffer_request_checked.argtypes = (ctypes.c_void_p,ctypes.c_size_t,library._check_type)
    library.ratiolab_buffer_request_checked.restype = ctypes.c_void_p
    library.ratiolab_buffer_data.argtypes = (ctypes.c_void_p,)
    library.ratiolab_buffer_data.restype = ctypes.c_void_p
    library.ratiolab_buffer_length.argtypes = (ctypes.c_void_p,)
    library.ratiolab_buffer_length.restype = ctypes.c_size_t
    library.ratiolab_buffer_free.argtypes = (ctypes.c_void_p,)
    library.ratiolab_buffer_free.restype = None
    return library


def backend():
    """Bind owned resources to the exact native library or Wasm instance."""
    if sys.platform=='emscripten':
        from js import ratiolabRustRequest
        return ratiolabRustRequest,('wasm',int(ratiolabRustRequest.epoch))
    library=_library()
    return library,('native',id(library))


def call(operation, parameters=None, check=None, *, _backend=None):
    # Releasing owned native resources must succeed even after the request that
    # created them was cancelled. Never let an inherited check skip a finally.
    check = None if operation in ('surface_release','surface_cursor_release','collision_release') else _with_control(check)
    if check:check()
    from precise_numbers import transport
    payload = json.dumps(dict(protocol=PROTOCOL, operation=operation,
                              parameters=transport(parameters or {})), allow_nan=False,
                         separators=(',', ':'))
    if check:check()
    stopped=[]
    if sys.platform == 'emscripten':
        from js import ratiolabRustRequest
        response = json.loads(str((_backend or ratiolabRustRequest)(payload)))
    else:
        import ctypes
        data = payload.encode('utf-8')
        source = ctypes.c_char_p(data)
        library = _backend if _backend is not None else _library()
        if check:
            def control():
                try:
                    check()
                    return 0
                except BaseException as error:
                    stopped.append(error)
                    return 1
            callback=library._check_type(control)
            pointer = library.ratiolab_request_checked(source, len(data), callback)
        else:
            pointer = library.ratiolab_request(source, len(data))
        if not pointer:
            raise RuntimeError('Rust geometry returned no response.')
        try:
            length = library.ratiolab_result_length(pointer)
            if length > 128*1024*1024:
                raise RuntimeError('Rust geometry response exceeds its resource limit.')
            response = json.loads(ctypes.string_at(pointer, length))
        finally:
            library.ratiolab_free(pointer)
    if stopped:raise stopped[0]
    if check and operation not in ('collision_create','collision_create_surface','collision_pose',
                                   'surface_create','surface_cursor_create'):check()
    if not response.get('ok'):
        raise ValueError(response.get('error', {}).get('message', 'Rust geometry calculation failed.'))
    return response['result']


def _buffer_result(operation,parameters,check=None,*,_backend=None,_preview=False):
    """Owned little-endian sampled records, identical across native and Wasm.

    Copy results before releasing Rust ownership. No views into freed/grown native
    or Wasm memory escape; callbacks retain the original caller exception.
    """
    check = _with_control(check)
    if check:check()
    from precise_numbers import transport
    payload=json.dumps(dict(protocol=PROTOCOL,operation=operation,parameters=transport(parameters)),
                       allow_nan=False,separators=(',',':'))
    if check:check()
    stopped=[]
    if sys.platform=='emscripten':
        from js import ratiolabRustRequest
        data=bytes((_backend or ratiolabRustRequest).buffer(payload).to_py())
    else:
        import ctypes
        raw=payload.encode('utf-8');source=ctypes.c_char_p(raw);library=_backend if _backend is not None else _library()
        if check:
            def control():
                try:check();return 0
                except BaseException as error:stopped.append(error);return 1
            callback=library._check_type(control)
            pointer=library.ratiolab_buffer_request_checked(source,len(raw),callback)
        else:pointer=library.ratiolab_buffer_request(source,len(raw))
        if not pointer:raise RuntimeError('Rust geometry returned no binary response.')
        try:
            length=library.ratiolab_buffer_length(pointer)
            if length>128*1024*1024:raise RuntimeError('Rust geometry response exceeds its resource limit.')
            if _preview:
                if stopped:raise stopped[0]
                if check:check()
                result=_native_preview(library.ratiolab_buffer_data(pointer),length,check)
                if check:check()
                return result
            data=ctypes.string_at(library.ratiolab_buffer_data(pointer),length)
        finally:library.ratiolab_buffer_free(pointer)
    if stopped:raise stopped[0]
    if check:check()
    if not data:raise RuntimeError('Rust geometry returned an empty binary response.')
    if data[0]:raise ValueError(data[1:].decode('utf-8'))
    payload=memoryview(data)[1:]
    return _decode_preview(payload) if _preview else payload


def call_buffer(operation,parameters,record_size,check=None,*,_backend=None):
    import struct
    data=_buffer_result(operation,parameters,check,_backend=_backend)
    if len(data)<4:raise RuntimeError('Truncated Rust geometry binary header.')
    count=struct.unpack_from('<I',data,0)[0]
    if len(data)!=4+record_size*count:raise RuntimeError('Invalid Rust geometry binary record count.')
    return data[4:]


def _decode_geometry(data,check=None):
    """Decode bounded metadata and owned binary64 coordinate arrays.

    2D contours become tuple points, matching Part's immutable point convention;
    3D material-reference rows keep the existing nested-list representation.
    """
    check=_with_control(check)
    if check:check()
    import struct
    if len(data)<4:raise RuntimeError('Truncated geometry packet.')
    size=struct.unpack_from('<I',data,0)[0]
    if size>16*1024*1024 or size>len(data)-4:raise RuntimeError('Invalid geometry metadata length.')
    metadata=json.loads(bytes(data[4:4+size]))
    if check:check()
    if not isinstance(metadata,dict) or metadata.get('format')!='ratiolab.geometry-buffer/1' or 'result' not in metadata:
        raise RuntimeError('Unsupported geometry packet format.')
    raw=data[4+size:]
    if len(raw)%8:raise RuntimeError('Misaligned geometry coordinates.')
    available=len(raw)//8;used=0;ranges=[]
    def decode(v):
        nonlocal used
        if isinstance(v,dict) and '$ratiolab.f64/1' in v:
            desc=v['$ratiolab.f64/1']
            if (len(v)!=1 or not isinstance(desc,list) or len(desc)!=3
                    or any(type(n) is not int for n in desc)):
                raise RuntimeError('Invalid coordinate descriptor.')
            start,count,width=desc
            if start<0 or count<0 or width not in (2,3) or start>available or count*width>available-start:
                raise RuntimeError('Coordinate descriptor exceeds its buffer.')
            length=count*width;used+=length
            if used>available:raise RuntimeError('Coordinate references exceed their resource limit.')
            if length:ranges.append((start,start+length))
            rows=struct.iter_unpack('<'+str(width)+'d',raw[start*8:(start+length)*8])
            if check is None:
                return list(rows) if width==2 else list(map(list,rows))
            # Keep the existing owned/mutable representation while allowing a
            # superseded GUI request to stop between coordinate blocks.
            from itertools import islice
            result=[]
            while block:=list(islice(rows,1024)):
                check()
                result.extend(block if width==2 else map(list,block))
            check()
            return result
        if isinstance(v,dict):return {k:decode(x) for k,x in v.items()}
        if isinstance(v,list):return [decode(x) for x in v]
        return v
    result=decode(metadata['result']);end=0
    for start,stop in sorted(ranges):
        if start!=end:raise RuntimeError('Overlapping or unused geometry coordinates.')
        end=stop
    if end!=available:raise RuntimeError('Unused geometry coordinates.')
    if check:check()
    return result


def call_geometry(operation,parameters,check=None,*,_backend=None):
    return _decode_geometry(_buffer_result(operation,parameters,check,_backend=_backend),check)


def _preview_layout(meta,array_bytes):
    if not isinstance(meta,dict) or meta.get('format')!='ratiolab.preview-buffer/1':
        raise RuntimeError('Unsupported preview format.')
    n,m=meta.get('vertex_floats'),meta.get('material_floats')
    fill=meta.get('material_fill')
    if fill is not None and fill!='zero':raise RuntimeError('Invalid preview material fill.')
    if (type(n) is not int or type(m) is not int or n<0 or n%6 or
            m!=(0 if fill=='zero' else n//2) or array_bytes!=4*(n+m)):
        raise RuntimeError('Invalid preview array lengths.')
    scene=meta['scene'];count=n//6
    def valid(row):
        if not isinstance(row,list) or len(row)!=2 or any(type(v) is not int or v<0 for v in row) or sum(row)>count:
            raise RuntimeError('Invalid preview draw range.')
    valid(scene['grid'])
    for part in scene['parts']:
        valid(part['side']);valid(part['edges'])
        for cap in part['caps']:valid(cap['fan']);valid(cap['plane'])
    return scene,n,m


def _decode_preview(data):
    from array import array
    import struct
    if len(data)<4:raise RuntimeError('Truncated preview packet.')
    size=struct.unpack_from('<I',data)[0]
    if size>16*1024*1024 or size>len(data)-4:raise RuntimeError('Invalid preview metadata length.')
    scene,n,m=_preview_layout(json.loads(bytes(data[4:4+size])),len(data)-4-size)
    start=4+size;vertices=array('f');materials=array('f')
    if vertices.itemsize!=4:raise RuntimeError('Preview requires IEEE binary32 arrays.')
    vertices.frombytes(data[start:start+4*n]);materials.frombytes(data[start+4*n:])
    if sys.byteorder!='little':vertices.byteswap();materials.byteswap()
    return scene,vertices,materials


def _native_floats(address,count,check):
    """Copy into an owned array while the caller still owns the Rust result.

    No borrowed ctypes object/view survives this helper, even on an exception.
    Wasm keeps its owned-byte path, so memory.grow cannot invalidate a view.
    """
    from array import array
    import ctypes
    result=array('f')
    if result.itemsize!=4:raise RuntimeError('Preview requires IEEE binary32 arrays.')
    size=count*4
    block=4*1024*1024 if check else max(size,1)
    for start in range(0,size,block):
        if check:check()
        source=None;view=None
        try:
            source=(ctypes.c_ubyte*min(size-start,block)).from_address(address+start)
            view=memoryview(source).cast('B')
            result.frombytes(view)
        finally:
            if view is not None:view.release()
            view=None;source=None
    if sys.byteorder!='little':result.byteswap()
    return result


def _native_preview(address,length,check):
    import ctypes
    if not length:raise RuntimeError('Rust geometry returned an empty binary response.')
    if ctypes.string_at(address,1)!=b'\0':
        raise ValueError(ctypes.string_at(address+1,length-1).decode('utf-8'))
    if length<5:raise RuntimeError('Truncated preview packet.')
    size=int.from_bytes(ctypes.string_at(address+1,4),'little')
    if size>16*1024*1024 or size>length-5:raise RuntimeError('Invalid preview metadata length.')
    meta=json.loads(ctypes.string_at(address+5,size))
    scene,n,m=_preview_layout(meta,length-5-size)
    start=address+5+size
    vertices=_native_floats(start,n,check)
    materials=_native_floats(start+4*n,m,check)
    return scene,vertices,materials


def preview_scene(parameters,*,_backend=None,check=None):
    return _buffer_result('preview_scene',parameters,check,_backend=_backend,_preview=True)


def web_mesh(parameters,*,_backend=None,check=None):
    import struct
    data=_buffer_result('web_mesh',parameters,check,_backend=_backend)
    if len(data)<4:raise RuntimeError('Truncated web mesh packet.')
    size=struct.unpack_from('<I',data)[0]
    if size>16*1024*1024 or size>len(data)-4:raise RuntimeError('Invalid web mesh metadata length.')
    meta=json.loads(bytes(data[4:4+size]))
    if not isinstance(meta,dict) or meta.get('format')!='ratiolab.web-mesh-buffer/1':
        raise RuntimeError('Unsupported web mesh format.')
    n,q,m,t=(meta.get(k) for k in ('position_floats','normal_floats','material_floats','triangles'))
    if any(type(x) is not int or x<0 for x in (n,q,m,t)) or n!=9*t or q!=n or m not in (0,n) or len(data)!=4+size+4*(n+q+m):
        raise RuntimeError('Invalid web mesh array lengths.')
    start=4+size
    return meta,bytes(data[start:start+4*n]),bytes(data[start+4*n:start+4*(n+q)]),bytes(data[start+4*(n+q):])


def pose_matrices(phase,poses):
    import struct
    return list(struct.iter_unpack('<16d',call_buffer('affine_poses',dict(phase=phase,poses=poses),128)))
