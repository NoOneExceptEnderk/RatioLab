"""Verify an actual agent subprocess, both MCP eras, and its real exported files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from queue import Queue, Empty
import subprocess
import tempfile
from threading import Thread

MODERN = '2026-07-28'
LEGACY = '2025-11-25'


class Client:
    def __init__(self, command, workspace, protocol, environment):
        self.protocol, self.serial = protocol, 0
        self.errors = tempfile.TemporaryFile()
        self.process = subprocess.Popen([*command, '--workspace', str(workspace)], cwd=workspace,
                                        env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.errors)
        self.responses = Queue()
        def read():
            for line in self.process.stdout:
                try:
                    self.responses.put(json.loads(line.decode('utf-8')))
                except (ValueError, UnicodeError) as error:
                    self.responses.put(error)
            self.responses.put(EOFError('MCP subprocess closed its output'))
        self.reader = Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, message):
        self.process.stdin.write((json.dumps(message, ensure_ascii=False)+'\n').encode('utf-8'))
        self.process.stdin.flush()

    def request(self, method, params=None):
        self.serial += 1
        params = dict(params or {})
        if self.protocol == MODERN:
            params['_meta'] = {'io.modelcontextprotocol/protocolVersion': MODERN,
                               'io.modelcontextprotocol/clientCapabilities': {}}
        self.send(dict(jsonrpc='2.0', id=self.serial, method=method, params=params))
        while True:
            try:
                response = self.responses.get(timeout=60)
            except Empty as error:
                raise RuntimeError('MCP response timed out: '+method) from error
            if isinstance(response, Exception):
                raise RuntimeError('Invalid MCP subprocess output: '+str(response))
            if 'id' not in response:
                continue
            if response.get('id') != self.serial or 'error' in response:
                raise RuntimeError('MCP protocol request failed: '+str(response))
            result = response['result']
            if self.protocol == MODERN and result.get('resultType') != 'complete':
                raise RuntimeError('MCP modern result is missing its discriminator')
            return result

    def tool(self, name, arguments, *, error=False):
        result = self.request('tools/call', dict(name='ratiolab.'+name, arguments=arguments))
        if bool(result.get('isError')) != error:
            raise RuntimeError('MCP tool failed: '+name+' '+str(result))
        value = result['structuredContent']
        assert json.loads(result['content'][0]['text']) == value
        return value

    def close(self):
        try:
            self.process.stdin.close()
            try:
                code = self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
                raise RuntimeError('MCP subprocess did not exit after input closed')
            if code:
                self.errors.seek(0)
                raise RuntimeError('MCP subprocess failed: '+self.errors.read().decode('utf-8',errors='replace')[-3000:])
            self.reader.join(timeout=1)
        finally:
            self.process.stdout.close()
            self.errors.close()


def check(executable, report=None, *, module=False, environment=None):
    # Preserve a venv Python's symlink: resolving it launches the base Python
    # and silently loses the installed wheel's environment.
    executable = str(Path(executable).expanduser().absolute())
    command = [executable]+(['-m', 'ratiolab_mcp'] if module else [])
    environment = dict(os.environ if environment is None else environment)
    for key in ('DISPLAY', 'WAYLAND_DISPLAY'):
        environment.pop(key, None)
    proofs = []
    with tempfile.TemporaryDirectory(prefix='RatioLab agent Ω ') as temporary:
        for protocol in (MODERN, LEGACY):
            workspace = Path(temporary)/protocol
            workspace.mkdir()
            client = Client(command, workspace, protocol, environment)
            try:
                if protocol == MODERN:
                    discovery = client.request('server/discover')
                    assert MODERN in discovery['supportedVersions']
                    assert discovery['cacheScope'] == 'private' and discovery['ttlMs'] == 0
                else:
                    result = client.request('initialize',dict(protocolVersion=LEGACY, capabilities={},
                                            clientInfo=dict(name='RatioLab native verifier',version='1')))
                    assert result['protocolVersion'] == LEGACY
                    client.send(dict(jsonrpc='2.0',method='notifications/initialized'))
                tools = client.request('tools/list')['tools']
                assert len(tools)>=13 and len({t['name'] for t in tools})==len(tools)
                families = client.tool('discover',{})['families']
                assert len(families)==9
                model = client.tool('project_create',dict(family='parallel',parameters=dict(pinion=20,wheel=60)))
                handle, revision = model['handle'],model['revision']
                changed = client.tool('project_update',dict(handle=handle,revision=revision,parameters=dict(wheel=66)))
                client.tool('project_update',dict(handle=handle,revision=revision,parameters=dict(wheel=80)),error=True)
                undone = client.tool('project_history',dict(handle=handle,revision=changed['revision'],action='undo'))
                assert undone['parameters']['wheel']==60
                revision = undone['revision']
                source = client.tool('project_describe',dict(handle=handle,revision=revision))
                subset = client.tool('project_describe',dict(handle=handle,revision=revision,components=[2]))
                assert len(subset['components'])==1 and subset['components'][0]['index']==2
                assert subset['components'][0]['name']==source['components'][1]['name']
                saved = client.tool('project_save',dict(handle=handle,revision=revision,path='project Ω.json'))
                revision = saved['revision']
                assert json.loads((workspace/'project Ω.json').read_text(encoding='utf-8'))['parameters']['wheel']==60
                client.tool('project_save',dict(handle=handle,revision=revision,path='../outside.json'),error=True)
                exported = client.tool('export',dict(handle=handle,revision=revision,path='CAD subset',kind='step',components=[2]))
                target = workspace/exported['path']
                manifest = json.loads((target/'manifest.json').read_text(encoding='utf-8'))
                assert manifest['complete'] and manifest['complete_assembly'] is False
                for record in manifest['files']:
                    data = (target/record['path']).read_bytes()
                    assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256']
                assert (target/'assembly.step').read_text(encoding='utf-8').startswith('ISO-10303-21;')
                search = client.tool('search',dict(handle=handle,revision=revision,axes=dict(wheel=[60,66]),settings=dict(target=3,tolerance_percent=.01)))
                assert search['complete'] and len(search['search']['proposals'])==1
                analysis = client.tool('interference',dict(handle=handle,revision=revision,settings=dict(max_seconds=.01,max_poses=1)))
                assert not analysis['complete'] and not analysis['analysis']['coverage_complete']
                opened = client.tool('project_open',dict(path='project Ω.json'))
                assert opened['parameters']['wheel']==60
                proofs.append(dict(protocol=protocol,requests=client.serial,tools=len(tools),families=len(families),
                                   history='passed',stale_revision='rejected',path_escape='rejected',
                                   step_subset='passed',manifest_hashes='passed',search='passed',
                                   interference_incomplete='reported',save_open='passed'))
            finally:
                client.close()
    result = dict(mcp='passed',display_required=False,protocols=proofs)
    if report:
        Path(report).parent.mkdir(parents=True,exist_ok=True)
        Path(report).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable',type=Path)
    parser.add_argument('--module',action='store_true',help='Run Python -m ratiolab_mcp for a source/wheel test')
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.executable,args.report,module=args.module),indent=2))
