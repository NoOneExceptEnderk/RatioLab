# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Register the local server in the selected client's user configuration."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import external_programs
from mcp_clients import json_configuration


class RegistrationError(ValueError):
    """An error safe to display without revealing client configuration."""


def config_path(client, project=None):
    home = Path.home()
    xdg = Path(os.environ.get('XDG_CONFIG_HOME') or home/'.config')
    roaming = Path(os.environ.get('APPDATA') or home/'AppData/Roaming')
    if client == 'continue':
        if project is None:
            raise ValueError('project path required')
        return project/'.continue/mcpServers/ratiolab.json'
    if client == 'opencode':
        override = os.environ.get('OPENCODE_CONFIG')
        directory = Path(os.environ.get('OPENCODE_CONFIG_DIR') or xdg/'opencode')
        jsonc = directory/'opencode.jsonc'
        return Path(override).expanduser() if override else jsonc if jsonc.is_file() else directory/'opencode.json'
    if client == 'claude-desktop':
        directory = {'darwin': home/'Library/Application Support', 'win32': roaming}.get(sys.platform, xdg)
        return directory/'Claude/claude_desktop_config.json'
    if client == 'cline':
        override = os.environ.get('CLINE_MCP_SETTINGS_PATH')
        if override:
            return Path(override).expanduser()
        directory = {'darwin': home/'Library/Application Support', 'win32': roaming}.get(sys.platform, xdg)
        extension = directory/'Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json'
        cli = home/'.cline/data/settings/cline_mcp_settings.json'
        return extension if extension.is_file() and not cli.is_file() else cli
    if client == 'zed':
        if sys.platform == 'win32':
            return roaming/'Zed/settings.json'
        modern = xdg/'zed/settings.json'
        legacy = home/'.zed/settings.json'
        return legacy if sys.platform == 'darwin' and legacy.is_file() and not modern.is_file() else modern
    destinations = {
        'claude': home/'.claude.json',
        'antigravity': home/'.gemini/config/mcp_config.json',
        'cursor': home/'.cursor/mcp.json',
        'copilot': Path(os.environ.get('COPILOT_HOME') or home/'.copilot')/'mcp-config.json',
        'gemini': Path(os.environ.get('GEMINI_CLI_HOME') or home)/'.gemini/settings.json',
        'kiro': home/'.kiro/settings/mcp.json',
    }
    return destinations[client]


# Mask comments and trailing commas without changing offsets. A string match
# takes precedence over comment and comma matches so quoted values stay intact.
_STRING = r'"(?:\\.|[^"\\])*"'
_COMMENTS = re.compile(_STRING + r'|(?P<comment>//[^\r\n]*|/\*[\s\S]*?\*/)')
_TRAILING = re.compile(_STRING + r'|(?P<comma>,)(?=[ \t\r\n]*[}\]])')
_SPACE = re.compile(r'[ \r\n\t]*')


def _mask_jsonc(text):
    masked = _COMMENTS.sub(lambda match: re.sub(r'[^\r\n]', ' ', match[0])
                           if match['comment'] else match[0], text)
    masked = _TRAILING.sub(lambda match: ' ' if match['comma'] else match[0], masked)
    return ' '+masked[1:] if masked.startswith('\ufeff') else masked


def _unique_pairs(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise RegistrationError('The client configuration has duplicate keys.')
    return result


_DECODER = json.JSONDecoder(object_pairs_hook=_unique_pairs)


def _members(masked, opening):
    """Yield a validated object's property names and raw value bounds."""
    position = _SPACE.match(masked, opening + 1).end()
    while masked[position] != '}':
        key, after = _DECODER.raw_decode(masked, position)
        colon = _SPACE.match(masked, after).end()
        start = _SPACE.match(masked, colon + 1).end()
        _, end = _DECODER.raw_decode(masked, start)
        yield key, (start, end)
        position = _SPACE.match(masked, end).end()
        if masked[position] == ',':
            position = _SPACE.match(masked, position + 1).end()


def _set_member(text, keys, value):
    masked = _mask_jsonc(text)
    opening = _SPACE.match(masked).end()
    for index, key in enumerate(keys):
        if masked[opening] != '{':
            raise ValueError('configuration object required')
        members = dict(_members(masked, opening))
        if key in members:
            opening, end = members[key]
            continue
        for remaining in reversed(keys[index + 1:]):
            value = {remaining: value}
        newline = '\r\n' if '\r\n' in text else '\n'
        line = text.rfind('\n', 0, opening) + 1
        indent = re.match(r'[ \t]*', text[line:opening])[0]
        suffix = text[opening + 1:]
        entry = json.dumps(key) + ': ' + json.dumps(value, ensure_ascii=False)
        insertion = newline + indent + '  ' + entry + (',' if members else '')
        if not suffix.startswith(('\n', '\r\n')):
            insertion += newline + indent + ('  ' if members else '')
        return text[:opening + 1] + insertion + suffix
    return text[:opening] + json.dumps(value, ensure_ascii=False) + text[end:]


def merge_configuration(text, client, launch):
    """Change the RatioLab entry while preserving comments and other servers."""
    document = _DECODER.decode(_mask_jsonc(text))
    if not isinstance(document, dict):
        raise ValueError('configuration object required')
    payload = json_configuration(client, launch)
    key, servers = next(iter(payload.items()))
    fields = (key, 'ratiolab')
    container = document.get(key, {})
    if not isinstance(container, dict):
        raise ValueError('server map required')
    if client == 'opencode' and ('servers' in container or 'timeout' in container):
        container = container.get('servers', {})
        if not isinstance(container, dict):
            raise ValueError('server map required')
        fields = (key, 'servers', 'ratiolab')
    entry = servers['ratiolab']
    if 'ratiolab' not in container:
        return _set_member(text, fields, entry)
    current = container['ratiolab']
    if (not isinstance(current, dict) or current.get('type') not in (None, 'stdio', 'local')
            or any(key in current for key in ('url', 'httpUrl', 'serverUrl'))):
        raise RegistrationError('A server named ratiolab already uses a different transport.')
    for name, value in entry.items():
        if name in ('type', 'tools') and name in current:
            continue
        if name in ('env', 'environment') and name in current:
            if not isinstance(current[name], dict):
                raise ValueError('environment map required')
            for variable, content in value.items():
                if current[name].get(variable) != content:
                    text = _set_member(text, (*fields, name, variable), content)
        elif current.get(name) != value:
            text = _set_member(text, (*fields, name), value)
    return text


def _write_json_config(path, client, launch):
    from gi.repository import Gio

    if not path.is_absolute():
        raise RegistrationError('The client configuration path must be absolute.')
    path = path.resolve()
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        payload = json.dumps(json_configuration(client, launch), ensure_ascii=False, indent=2) + '\n'
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.ratiolab-mcp-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
                stream.write(payload)
            os.link(temporary, path)  # Do not overwrite a concurrently created config.
        finally:
            Path(temporary).unlink(missing_ok=True)
        return
    if not stat.S_ISREG(mode):
        raise ValueError('regular config file required')
    target = Gio.File.new_for_path(str(path))
    _, data, etag = target.load_contents()
    updated = merge_configuration(data.decode('utf-8'), client, launch).encode('utf-8')
    if updated != data:
        target.replace_contents(updated, etag, False, Gio.FileCreateFlags.NONE)


def _register_codex(launch):
    environment = external_programs.child_environment()
    name = 'codex.exe' if sys.platform == 'win32' else 'codex'
    executable = shutil.which(name, path=environment.get('PATH', os.defpath))
    if executable is None:
        desktop = {'linux': '/usr/lib/chatgpt/resources/codex',
                   'darwin': '/Applications/ChatGPT.app/Contents/Resources/codex'}.get(sys.platform)
        if not desktop or not Path(desktop).is_file():
            raise RegistrationError('Codex CLI was not found.')
        executable = desktop

    def run(*args):
        with external_programs.system_library_search():
            result = subprocess.run([executable, 'mcp', *args], env=environment, cwd=Path.home(),
                                    capture_output=True, timeout=12)
        if result.returncode:
            raise RegistrationError('Codex could not update its MCP configuration.')
        return result.stdout

    rows = json.loads(run('list', '--json'))
    variables = launch.get('env', {})
    if any(row['name'] == 'ratiolab' for row in rows):
        entry = json.loads(run('get', 'ratiolab', '--json'))
        transport = entry['transport']
        if (transport.get('type') != 'stdio' or transport.get('cwd') or transport.get('env_vars')
                or not entry.get('enabled') or entry.get('startup_timeout_sec') is not None
                or entry.get('tool_timeout_sec') is not None or entry.get('enabled_tools') is not None
                or entry.get('disabled_tools') is not None):
            raise RegistrationError('Codex already has a customized entry named ratiolab.')
        variables = {**(transport.get('env') or {}), **variables}
        if (transport['command'], transport.get('args') or [], transport.get('env') or {}) == (
                launch['command'], launch['args'], variables):
            return
    options = [part for key, value in variables.items() for part in ('--env', f'{key}={value}')]
    run('add', 'ratiolab', *options, '--', launch['command'], *launch['args'])


def register(client, launch, *, project=None):
    if client == 'codex':
        _register_codex(launch)
    else:
        _write_json_config(config_path(client, project), client, launch)
