# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Local RatioLab server configuration for supported MCP clients."""
import json


# Name, configuration file, and upstream setup guide.
CLIENTS = {
    'codex': ('Codex', '~/.codex/config.toml', 'https://learn.chatgpt.com/docs/extend/mcp?surface=cli'),
    'claude': ('Claude Code', '~/.claude.json', 'https://code.claude.com/docs/en/mcp#user-scope'),
    'opencode': ('OpenCode', 'opencode.json', 'https://opencode.ai/docs/migrate-v1/#mcp-servers'),
    'antigravity': ('Antigravity', 'mcp_config.json', 'https://antigravity.google/docs/mcp'),
    'cursor': ('Cursor', '~/.cursor/mcp.json', 'https://cursor.com/docs/mcp#configuration-locations'),
    'copilot': ('GitHub Copilot', 'mcp-config.json', 'https://code.visualstudio.com/docs/agents/reference/mcp-configuration'),
    'gemini': ('Gemini CLI', '~/.gemini/settings.json', 'https://geminicli.com/docs/tools/mcp-server/'),
    'claude-desktop': ('Claude Desktop', 'claude_desktop_config.json', 'https://modelcontextprotocol.io/docs/develop/connect-local-servers'),
    'cline': ('Cline', 'cline_mcp_settings.json', 'https://docs.cline.bot/mcp/mcp-overview'),
    'kiro': ('Kiro', '~/.kiro/settings/mcp.json', 'https://kiro.dev/docs/mcp/configuration/'),
    'zed': ('Zed', 'settings.json', 'https://zed.dev/docs/ai/mcp'),
    'continue': ('Continue', '.continue/mcpServers/ratiolab.json', 'https://docs.continue.dev/customize/deep-dives/mcp'),
    'generic': ('MCP JSON', '', None),
}


def configuration(client, launch):
    """Format the same executable, workspace arguments and optional environment."""
    if client not in CLIENTS:
        raise KeyError(client)
    if client == 'codex':
        section = 'mcp_servers.ratiolab'
        lines = [f'[{section}]']
        values = {key: launch[key] for key in ('command', 'args')}
        values.update({f'env.{key}': value for key, value in launch.get('env', {}).items()})
        for key, value in values.items():
            quoted = json.dumps(value, ensure_ascii=False).replace('\x7f', '\\u007f')
            lines.append(f'{key} = {quoted}')
        return '\n'.join(lines) + '\n'

    return json.dumps(json_configuration(client, launch), ensure_ascii=False, indent=2) + '\n'


def json_configuration(client, launch):
    if client == 'opencode':
        # The V1 layout is also accepted by OpenCode V2.
        entry = {'type': 'local', 'command': [launch['command'], *launch['args']]}
        if 'env' in launch:
            entry['environment'] = launch['env']
        payload = {'mcp': {'ratiolab': entry}}
    elif client == 'zed':
        payload = {'context_servers': {'ratiolab': launch}}
    else:
        entry = {'type': 'stdio', **launch} if client in ('claude', 'cursor', 'copilot') else launch
        if client == 'copilot':
            entry['tools'] = ['*']
        payload = {'mcpServers': {'ratiolab': entry}}
    return payload
