# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded, exact-content snapshots of mutable application parts in Rust.

Pickle is only an internal C-speed fingerprint/snapshot: bytes are created here,
never read from files, projects or the wire. Full float bits and decimal ASTs
remain in the key. A mutated nested list always produces a different snapshot.
"""
from collections import OrderedDict
from copy import deepcopy
import pickle
from threading import RLock
from rust_geometry import backend,call,call_buffer,call_geometry,control_check

MAX_ENTRIES=64
MAX_KEY_BYTES=16*1024*1024
_cache=OrderedDict();_lock=RLock();_bytes=0;_hits=0;_misses=0


class Surface:
    def __init__(self,payload,owner,check=None,identity=None):
        self._backend=owner;self._handle=None;self._closed=False
        self._identity=identity
        self._sampling=None
        created=call('surface_create',dict(part=payload),check,_backend=owner)
        self._handle=created['handle'];self._retry=created.get('retry',False)
        self._payload=payload if self._handle is None else None
        if check:
            try:check()
            except BaseException:self.close();raise

    def parameters(self,**values):
        if self._closed:raise ValueError('Surface snapshot is closed.')
        return dict(values,**(dict(handle=self._handle) if self._handle is not None else dict(part=self._payload)))

    def call(self,op,check=None,**values):
        return call(op,self.parameters(**values),check,_backend=self._backend)

    def sampling_report(self,check=None):
        self.parameters()
        if check:check()
        if self._sampling is None:self._sampling=self.call('solid_sampling',check)
        return deepcopy(self._sampling)

    def geometry(self,op,check=None,**values):
        return call_geometry(op,self.parameters(**values),check,_backend=self._backend)

    def buffer(self,op,size,check=None,**values):
        return call_buffer(op,self.parameters(**values),size,check,_backend=self._backend)

    def web_mesh(self,**values):
        from rust_geometry import web_mesh
        return web_mesh(self.parameters(**values),_backend=self._backend)

    def faces(self,check=None):
        cursor=self.call('surface_cursor_create',check,kind='faces')['handle']
        try:
            if check:check()
            while True:
                page=call_geometry('solid_faces_chunk',dict(handle=cursor,limit=1024),check,_backend=self._backend)
                for face in page['faces']:
                    yield [[tuple(q) for q in loop] for loop in face]
                if page['done']:break
        finally:call('surface_cursor_release',dict(handle=cursor),_backend=self._backend)

    def records(self,operation,size,check=None):
        cursor=self.call('surface_cursor_create',check,kind='triangles')['handle']
        try:
            if check:check()
            while True:
                page=call_buffer(operation,dict(handle=cursor,limit=4096),size,check,_backend=self._backend)
                if not page:break
                yield page
                # A short page exhausts the cursor and is released by Rust.
                if len(page)//size<4096:break
        finally:call('surface_cursor_release',dict(handle=cursor),_backend=self._backend)

    def close(self):
        if not self._closed:
            self._closed=True
            if self._handle is not None:
                call('surface_release',dict(handle=self._handle),_backend=self._backend)
                self._handle=None

    def __del__(self):
        try:self.close()
        except BaseException:pass


def surface(part,check=None):
    global _bytes,_hits,_misses
    control_check(check)
    from solid_geometry import kernel_part
    owner,identity=backend()
    snapshot=pickle.dumps(kernel_part(part),protocol=5)
    key=(identity,snapshot)
    with _lock:
        existing=_cache.pop(key,None)
        if existing is not None and not existing._closed:
            _cache[key]=existing;_hits+=1;return existing
        if existing is not None:_bytes-=len(snapshot)
        _misses+=1
        # Decode only our just-created snapshot on a miss, so a later mutation
        # cannot change the data sent under this immutable cache key.
        payload=pickle.loads(snapshot)
        result=Surface(payload,owner,check,identity)
        while result._handle is None and result._retry and _cache:
            old,retired=_cache.popitem(last=False);_bytes-=len(old[1]);del retired
            result=Surface(payload,owner,check,identity)
        if len(snapshot)<=MAX_KEY_BYTES and result._handle is not None:
            while _cache and (len(_cache)>=MAX_ENTRIES or _bytes+len(snapshot)>MAX_KEY_BYTES):
                old,_=_cache.popitem(last=False);_bytes-=len(old[1])
            _cache[key]=result;_bytes+=len(snapshot)
        return result


def clear_surface_cache():
    global _bytes
    with _lock:_cache.clear();_bytes=0


def surface_cache_info():
    with _lock:return dict(entries=len(_cache),bytes=_bytes,hits=_hits,misses=_misses,
        max_entries=MAX_ENTRIES,max_key_bytes=MAX_KEY_BYTES)
