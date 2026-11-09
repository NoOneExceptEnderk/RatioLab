#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Audit source interface messages against the shared offline language catalog."""
import argparse
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def normalize_fields(text):
    names = {}
    def replace(match):
        name = match[1]
        if re.fullmatch(r'(?:arg\d+|message\d+|value)', name):
            return match[0]
        if name not in names:
            names[name] = '{arg'+str(len(names))+'}'
        return names[name]
    return re.sub(r'\{([A-Za-z_]\w*)(?::[^{}]+)?\}', replace, text)


def is_message(text):
    """Exclude identifiers, units, code, paths and markup rather than translate data."""
    if not isinstance(text, str) or len(text.strip()) < 3 or not re.search(r'[A-Za-z]{3}', text):
        return False
    literal = re.sub(r'\{(?:arg\d+|value|[A-Za-z_]\w*(?::[^{}]+)?)\}', '', text)
    if not re.search(r'[A-Za-z]{3}', literal):
        return False
    if not re.search(r'[a-z]{2}|[A-Z]{3} [A-Z]{3}', literal):
        return False
    if any(word in text for word in ('://', ' xmlns', '<svg', '<div', '<!doctype',
            'import ', 'def ', 'return ', 'function(', '=>', 'self.', 'Gtk.',
            'background:', 'border:', 'font-size:', 'ratiolab_', 'SELECT ',
            'PROTOCOL_VERSION', 'sys.', '__name__', '\x00', '$', '&&', '||',
            '#version', 'uniform ', 'gl_', 'precision ', 'void ', '::',
            'trap -', 'finish;', 'Log-Failure', 'Get-Process', 'Start-Sleep', 'FILE_DESCRIPTION', 'FILE_NAME')):
        return False
    if re.fullmatch(r'[\w./#:@+*?=\-]+', literal) and not re.fullmatch(r'[A-Z][a-z]+', literal):
        return False
    if re.search(r'[{}]', literal):
        return False
    if re.match(r'^\s*(?:if\s*\[|then\b|fi\b|done\b|exit \d|sleep\s+\d|mkdir\b|chmod\b|set -|exec |cp |mv |rm |kill |while )', text):
        return False
    if '\n' in text and (re.search(r'^\s*(?:# |//|class |try:|from |if |\[)', text, re.M)
                         or text.count('{') > 8):
        return False
    if re.fullmatch(r'[\w./*?\-]+\.(?:py|json|png|svg|js|css|md|txt|so|dll|exe|ttf|ttc)', text):
        return False
    return True


def python_messages(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    excluded = set()
    for block in ast.walk(tree):
        if isinstance(block, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if block.body and isinstance(block.body[0], ast.Expr):
                excluded.add(id(block.body[0].value))
        if isinstance(block, ast.JoinedStr):
            excluded.update(id(part) for part in ast.walk(block) if part is not block)
    for node in ast.walk(tree):
        if id(node) in excluded:
            continue
        if isinstance(node, ast.JoinedStr):
            pieces, index = [], 0
            for part in node.values:
                if isinstance(part, ast.Constant):
                    pieces.append(part.value)
                else:
                    message = ast.unparse(part.value) in ('error', 'str(error)', 'reason', 'message', 'error.message')
                    pieces.append('{'+('message' if message else 'arg')+str(index)+'}')
                    index += 1
            text = ''.join(pieces)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        else:
            continue
        text = normalize_fields(text)
        if is_message(text) or path.name == 'parameter_help_diagrams.py' and re.fullmatch(r'[A-Za-z-]{3,}', text):
            yield text


def javascript_messages(path):
    # Scan lexical strings, including nested expressions in template literals.
    # Comments and regex literals do not contribute source messages.
    source = path.read_text(encoding='utf-8')
    index = 0
    while index < len(source):
        if source.startswith('//', index):
            end = source.find('\n', index)
            index = len(source) if end < 0 else end + 1
            continue
        if source.startswith('/*', index):
            end = source.find('*/', index+2)
            index = len(source) if end < 0 else end+2
            continue
        quote = source[index]
        if quote not in "'\"`":
            index += 1
            continue
        index += 1
        pieces, number = [], 0
        while index < len(source):
            char = source[index]
            if char == '\\' and index+1 < len(source):
                escape = source[index+1]
                pieces.append({'n':'\n','t':'\t','r':'\r'}.get(escape, escape))
                index += 2
            elif char == quote:
                index += 1
                break
            elif quote == '`' and source.startswith('${', index):
                depth, index = 1, index+2
                start = index
                inner_quote = None
                while index < len(source) and depth:
                    current = source[index]
                    if current == '\\':
                        index += 2
                        continue
                    if inner_quote:
                        if current == inner_quote:
                            inner_quote = None
                    elif current in "'\"`":
                        inner_quote = current
                    elif current == '{':
                        depth += 1
                    elif current == '}':
                        depth -= 1
                    index += 1
                expression = source[start:index-1].strip()
                pieces.append('{'+('message' if expression in ('error', 'error.message', 'reason', 'message') else 'arg')+str(number)+'}')
                number += 1
            else:
                pieces.append(char)
                index += 1
        text = ''.join(pieces)
        if is_message(text):
            yield text


class HTMLMessages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.messages = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.ignored += 1
        for key, value in attrs:
            if key in ('title', 'aria-label', 'placeholder') and value and is_message(value):
                self.messages.append(value)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.ignored = max(0, self.ignored-1)

    def handle_data(self, data):
        if not self.ignored and is_message(data.strip()):
            self.messages.append(data.strip())


def inventory():
    messages = {}
    # Backend exceptions/notes can reach UI dialogs; include their public source
    # text while keeping canonical serialized output and APIs in English.
    for path in sorted((ROOT/'src').glob('*.py')):
        if path.name in ('ui_language.py', 'ratiolab_mcp.py', 'ratiolab_cli.py'):
            continue
        for text in python_messages(path):
            messages.setdefault(text, set()).add(str(path.relative_to(ROOT)))
    for path in sorted((ROOT/'webapp').glob('*.js')):
        if path.name == 'ui-language.js':
            continue
        for text in javascript_messages(path):
            messages.setdefault(text, set()).add(str(path.relative_to(ROOT)))
    parser = HTMLMessages()
    parser.feed((ROOT/'webapp/index.html').read_text())
    for text in parser.messages:
        messages.setdefault(text, set()).add('webapp/index.html')
    return {text: sorted(paths) for text, paths in sorted(messages.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path)
    args = parser.parse_args()
    messages = inventory()
    if args.inventory:
        args.inventory.write_text(json.dumps(messages, ensure_ascii=False, indent=2)+'\n')
    catalog = json.loads((ROOT/'src/ratiolab_resources/ui-translations.json').read_text())
    missing = {code:[text for text in messages if text not in translations]
               for code, translations in catalog['translations'].items()}
    print(json.dumps({code:len(values) for code, values in missing.items()}))
    return int(any(missing.values()))


if __name__ == '__main__':
    raise SystemExit(main())
