# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""MCP transport regressions, using portable reader threads rather than pipe select."""
import io
import json
import os
from pathlib import Path
from queue import Queue, Empty
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
import unittest

from ratiolab_agent import AgentService, Limits
import ratiolab_agent
from ratiolab_mcp import Server, MODERN, LEGACY, PREFIX, TOOLS, serve
from release_version import RELEASE_VERSION
from geometry import FAMILIES

ROOT=Path(__file__).resolve().parent
META={PREFIX+'protocolVersion':MODERN,PREFIX+'clientCapabilities':{}}


def request(method, params=None, ident=1, modern=True):
    values=dict(params or {})
    if modern:values['_meta']=META
    return dict(jsonrpc='2.0',id=ident,method=method,params=values)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.service=AgentService(Path(self.folder.name))
        self.server=Server(self.service)
        self.addCleanup(self.folder.cleanup);self.addCleanup(self.service.close)

    def test_modern_discovery_tools_and_call_wire_contract_without_handshake(self):
        result=self.server.process(request('server/discover'))['result']
        self.assertEqual(result['supportedVersions'],[MODERN,LEGACY])
        self.assertEqual(result['resultType'],'complete')
        self.assertEqual(result['capabilities'],{'tools':{}})
        self.assertEqual(result['cacheScope'],'private');self.assertEqual(result['ttlMs'],0)
        self.assertIn(PREFIX+'serverInfo',result['_meta'])
        self.assertEqual(result['_meta'][PREFIX+'serverInfo'],dict(name='RatioLab',version=RELEASE_VERSION))
        listed=self.server.process(request('tools/list'))['result']
        self.assertEqual([tool['name'] for tool in listed['tools']],sorted(tool['name'] for tool in TOOLS))
        self.assertEqual(len(listed['tools']),13)
        self.assertEqual(listed['ttlMs'],0);self.assertEqual(listed['cacheScope'],'private')
        called=self.server.process(request('tools/call',{'name':'ratiolab.discover','arguments':{}}))['result']
        self.assertFalse(called['isError'])
        self.assertEqual(json.loads(called['content'][0]['text']),called['structuredContent'])
        self.assertEqual({row['id'] for row in called['structuredContent']['families']},set(FAMILIES))
        # Metadata never leaks from one modern request to the next.
        self.assertEqual(self.server.process(request('tools/list',modern=False))['error']['code'],-32602)
        self.assertEqual(self.server.process(request('ping'))['error']['code'],-32601)

    def test_legacy_handshake_only_negotiates_implemented_version(self):
        params=dict(protocolVersion='2025-06-18',capabilities={},clientInfo=dict(name='test',version='1'))
        initialized=self.server.process(request('initialize',params,modern=False))['result']
        self.assertEqual(initialized['protocolVersion'],LEGACY)
        self.assertEqual(initialized['serverInfo'],dict(name='RatioLab',version=RELEASE_VERSION))
        self.assertNotIn('resultType',initialized)
        self.assertEqual(self.server.process(request('tools/list',modern=False))['error']['code'],-32602)
        self.assertIsNone(self.server.process(dict(jsonrpc='2.0',method='notifications/initialized')))
        listed=self.server.process(request('tools/list',modern=False))['result']
        self.assertNotIn('resultType',listed)
        self.assertNotIn('cacheScope',listed)
        self.assertEqual(self.server.process(request('ping',modern=False))['result'],{})
        self.assertEqual(self.server.process(request('initialize',params,modern=False))['error']['code'],-32602)

    def test_future_protocol_and_missing_required_metadata_errors_are_exact(self):
        bad=request('server/discover');bad['params']['_meta']=dict(META,**{PREFIX+'protocolVersion':'2099-01-01'})
        error=self.server.process(bad)['error']
        self.assertEqual(error['code'],-32022)
        self.assertEqual(error['data'],dict(supported=[MODERN,LEGACY],requested='2099-01-01'))
        bad=request('tools/list');bad['params']['_meta']={PREFIX+'protocolVersion':MODERN}
        self.assertEqual(self.server.process(bad)['error']['code'],-32602)
        bad=request('tools/list');bad['params']['_meta']=dict(META,**{PREFIX+'protocolVersion':True})
        self.assertEqual(self.server.process(bad)['error']['code'],-32602)
        for method in ('resources/list','prompts/list','subscriptions/listen','tasks/list'):
            self.assertEqual(self.server.process(request(method))['error']['code'],-32601)

    def test_schema_validation_protocol_vs_structured_domain_errors(self):
        def call(name,args):return self.server.process(request('tools/call',dict(name=name,arguments=args)))
        for args in [None,[],dict(family='spur',unknown=True),dict(family=True),dict(family='')]:
            self.assertEqual(call('ratiolab.project_create',args)['error']['code'],-32602)
        self.assertEqual(call('invented.tool',{})['error']['code'],-32602)
        failed=call('ratiolab.project_create',dict(family='spur',parameters=dict(misspelled=1)))['result']
        self.assertTrue(failed['isError'])
        self.assertEqual(failed['structuredContent']['error']['code'],'invalid_parameters')
        self.assertEqual(failed['structuredContent'],json.loads(failed['content'][0]['text']))
        for bad in [[],{},dict(jsonrpc='2.0',id=None,method='tools/list'),dict(jsonrpc='2.0',id=True,method='tools/list')]:
            response=self.server.process(bad)
            self.assertEqual(response['error']['code'],-32600)
            self.assertIn('id',response);self.assertIsNone(response['id'])
        self.assertIsNone(self.server.process(dict(jsonrpc='2.0',method='unrecognized/notification')))
        self.assertEqual(self.server.process(request('tools/list',dict(cursor='fake')))['error']['code'],-32602)


class PipeHarness:
    """A real duplex pipe pair works on both Windows and POSIX."""
    def __init__(self, service):
        read_in,write_in=os.pipe();read_out,write_out=os.pipe()
        self.input=os.fdopen(write_in,'wb',buffering=0)
        self.output=os.fdopen(read_out,'rb',buffering=0)
        self.source=os.fdopen(read_in,'rb',buffering=0)
        self.destination=os.fdopen(write_out,'wb',buffering=0)
        self.queue=Queue()
        def read():
            for line in iter(self.output.readline,b''):
                self.queue.put(json.loads(line.decode('utf-8')))
        self.reader=Thread(target=read,daemon=True);self.reader.start()
        self.server=Thread(target=serve,args=(service,self.source,self.destination),daemon=True);self.server.start()

    def raw(self,data):self.input.write(data)
    def send(self,obj):self.raw((json.dumps(obj,ensure_ascii=False)+'\n').encode('utf-8'))
    def receive(self,timeout=5):return self.queue.get(timeout=timeout)
    def close(self):
        if not self.input.closed:self.input.close()
        self.server.join(3)
        self.source.close();self.destination.close()
        self.reader.join(1);self.output.close()


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)

    def harness(self,service):
        harness=PipeHarness(service);self.addCleanup(harness.close);return harness

    def test_utf8_line_framing_parse_errors_oversize_recovery_and_no_notification_response(self):
        service=AgentService(self.root,Limits(input_bytes=1024));h=self.harness(service)
        for raw in (b'\xff\n',b'{invalid}\n'):
            h.raw(raw);response=h.receive()
            self.assertEqual(response['error']['code'],-32700);self.assertIn('id',response);self.assertIsNone(response['id'])
        h.raw(b'x'*1100+b'\n');self.assertEqual(h.receive()['error']['code'],-32600)
        h.send(dict(jsonrpc='2.0',method='notifications/unknown'))
        h.send(request('server/discover',ident='UTF-8 Ω'))
        response=h.receive();self.assertEqual(response['id'],'UTF-8 Ω')
        self.assertEqual(response['result']['resultType'],'complete')
        with self.assertRaises(Empty):h.receive(.1)
        h.input.close();h.server.join(2);self.assertFalse(h.server.is_alive())

    def controlled_service(self):
        class Controlled(AgentService):
            def __init__(self,root):
                super().__init__(root);self.started=Event();self.stopped=Event()
            def discover(self,family=None,variant=None,double_style=None,parameters=None,cancel=None):
                self.started.set()
                if not cancel.wait(10):raise AssertionError('Cancellation was never delivered')
                self.stopped.set();return dict(cancelled=True)
        return Controlled(self.root)

    def test_cancelled_request_never_sends_response_and_reader_remains_live(self):
        service=self.controlled_service();h=self.harness(service)
        h.send(request('tools/call',dict(name='ratiolab.discover'),ident='cancel-me'))
        self.assertTrue(service.started.wait(3))
        h.send(dict(jsonrpc='2.0',method='notifications/cancelled',params=dict(requestId='cancel-me')))
        h.send(request('tools/list',ident='barrier'))
        self.assertEqual(h.receive()['id'],'barrier');self.assertTrue(service.stopped.wait(2))
        with self.assertRaises(Empty):h.receive(.1)

    def test_queue_is_bounded_duplicate_ids_rejected_and_eof_cancels_workers(self):
        service=self.controlled_service();h=self.harness(service)
        h.send(request('tools/call',dict(name='ratiolab.discover'),ident=0))
        self.assertTrue(service.started.wait(3))
        h.send(request('tools/list',ident=0))
        response=h.receive();self.assertEqual(response['id'],0);self.assertEqual(response['error']['code'],-32600)
        for i in range(1,14):h.send(request('tools/call',dict(name='ratiolab.discover'),ident=i))
        overloaded=h.receive();self.assertEqual(overloaded['error']['code'],-32603)
        h.input.close();h.server.join(2)
        self.assertFalse(h.server.is_alive());self.assertTrue(service.stopped.wait(1))

    def test_real_subprocess_complete_project_flow_and_eof_exits(self):
        runtime=Path(ratiolab_agent.__file__).resolve().parent
        process=subprocess.Popen([sys.executable,'-m','ratiolab_mcp','--workspace',str(self.root)],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=self.root,
                                 env=dict(os.environ,PYTHONPATH=str(runtime)))
        received=Queue()
        def read():
            for line in iter(process.stdout.readline,b''):received.put(json.loads(line.decode('utf-8')))
        reader=Thread(target=read,daemon=True);reader.start()
        def call(method,params=None,ident=1):
            process.stdin.write((json.dumps(request(method,params,ident))+'\n').encode('utf-8'));process.stdin.flush()
            return received.get(timeout=10)
        try:
            self.assertIn(MODERN,call('server/discover')['result']['supportedVersions'])
            project=call('tools/call',dict(name='ratiolab.project_create',arguments=dict(family='spur')))['result']['structuredContent']
            args=dict(handle=project['handle'],revision=project['revision'],path='qualità Ω.json')
            result=call('tools/call',dict(name='ratiolab.project_save',arguments=args))['result']
            self.assertFalse(result['isError']);self.assertTrue((self.root/'qualità Ω.json').is_file())
            process.stdin.close();self.assertEqual(process.wait(timeout=3),0)
            self.assertEqual(process.stderr.read(),b'')
        finally:
            if process.poll() is None:process.kill();process.wait(3)
            reader.join(1)
            for stream in (process.stdin,process.stdout,process.stderr):stream.close()


if __name__=='__main__':unittest.main()
