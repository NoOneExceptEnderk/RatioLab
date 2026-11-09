# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""One daemon worker and one replaceable request; UI delivery is caller-owned."""
from dataclasses import dataclass
from threading import Lock,Thread


@dataclass(frozen=True)
class Request:
    family: str
    values: dict
    view_flags: tuple
    document_identity: str
    reconcile_token: object
    quality: dict = None


class LatestOnly:
    def __init__(self,prepare,post,complete):
        self.prepare=prepare;self.post=post;self.complete=complete
        self.lock=Lock();self.serial=0;self.queued=None;self.thread=None;self.closed=False

    def invalidate(self):
        with self.lock:
            self.serial+=1;self.queued=None

    def submit(self,request):
        with self.lock:
            if self.closed:return
            self.serial+=1;self.queued=(self.serial,request)
            if self.thread is None:
                self.thread=Thread(target=self.run,daemon=True,name='RatioLab geometry')
                self.thread.start()

    def run(self):
        while True:
            with self.lock:
                if self.closed or self.queued is None:
                    self.thread=None;return
                serial,request=self.queued;self.queued=None
            try:result=self.prepare(request,lambda serial=serial:self.current(serial));error=None
            except Exception as caught:result=None;error=caught
            with self.lock:current=not self.closed and serial==self.serial
            if current:self.post(self.deliver,serial,request,result,error)

    def current(self,serial):
        with self.lock:return not self.closed and serial==self.serial

    def deliver(self,serial,request,result,error):
        with self.lock:current=not self.closed and serial==self.serial
        if current:self.complete(request,result,error)
        return False

    def close(self):
        with self.lock:
            self.closed=True;self.serial+=1;self.queued=None
