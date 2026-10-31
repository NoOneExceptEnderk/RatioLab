# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded coalescing and stale delivery without a GTK display."""
from threading import Event,get_ident
import time
import unittest
from geometry_refresh import LatestOnly


def wait_until(predicate):
    until=time.monotonic()+3
    while time.monotonic()<until:
        if predicate():return
        time.sleep(.002)
    raise AssertionError('Worker did not finish')


class LatestGeometryTests(unittest.TestCase):
    def test_burst_keeps_only_active_and_latest_request_and_delivers_on_caller(self):
        started=Event();release=Event();prepared=[];posted=[];completed=[];main=get_ident()
        def prepare(value,current):
            prepared.append((value,get_ident()))
            if value==0:
                started.set()
                if not release.wait(2):raise TimeoutError('Test release missing')
            return value*2
        worker=LatestOnly(prepare,lambda *args:posted.append(args),
                          lambda *args:completed.append((args,get_ident())))
        try:
            worker.submit(0);self.assertTrue(started.wait(1))
            thread=worker.thread;self.assertTrue(thread.daemon)
            for value in range(1,101):worker.submit(value)
            self.assertEqual(worker.queued[1],100);self.assertIs(worker.thread,thread)
            release.set();wait_until(lambda:worker.thread is None)
            self.assertEqual([value for value,_ in prepared],[0,100])
            self.assertTrue(all(identity!=main for _,identity in prepared))
            self.assertEqual(len(posted),1);self.assertFalse(completed)
            callback,*args=posted.pop();callback(*args)
            self.assertEqual(completed,[((100,200,None),main)])
        finally:release.set();worker.close()

    def test_invalidation_also_rejects_result_already_posted_to_ui(self):
        posted=[];completed=[]
        worker=LatestOnly(lambda value,current:value,lambda *args:posted.append(args),lambda *args:completed.append(args))
        worker.submit('old');wait_until(lambda:worker.thread is None)
        self.assertEqual(len(posted),1);worker.invalidate()
        callback,*args=posted.pop();callback(*args);self.assertFalse(completed);worker.close()

    def test_stale_failure_is_discarded_and_close_drops_queued_work(self):
        started=Event();release=Event();prepared=[];posted=[];completed=[]
        def prepare(value,current):
            prepared.append(value)
            if value=='obsolete':
                started.set();release.wait(2);raise ValueError('Obsolete failure')
            return value
        worker=LatestOnly(prepare,lambda *args:posted.append(args),lambda *args:completed.append(args))
        try:
            worker.submit('obsolete');self.assertTrue(started.wait(1));worker.submit('latest')
            release.set();wait_until(lambda:worker.thread is None)
            for callback,*args in posted:callback(*args)
            self.assertEqual(completed,[('latest','latest',None)])
            posted.clear();completed.clear();started.clear();release.clear()
            worker.submit('obsolete');self.assertTrue(started.wait(1));worker.submit('never')
            worker.close();worker.submit('also never');release.set()
            wait_until(lambda:worker.thread is None)
            self.assertEqual(prepared,['obsolete','latest','obsolete'])
            self.assertFalse(posted);self.assertFalse(completed)
        finally:release.set();worker.close()


if __name__=='__main__':unittest.main()
