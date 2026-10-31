# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded Markdown-to-plain-text release notes; never interpret markup or links."""
import html
import re

MAX_NOTES = 100000
_HEADING = re.compile(r'^\s*(#{1,6})\s+(.+?)\s*#*\s*$')
_VERSION = re.compile(r'^\[?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?(?:\]|\s|$)')


def plain_text(markdown, *, history=False):
    """Format readable paragraphs and bullets, excluding development sections.

    Local history starts at the first numbered version. Published release notes
    may have their own preamble. Every result is plain text for a non-markup GTK
    label: links retain their caption but have no executable or clickable URI.
    """
    if not isinstance(markdown, str):
        return ''
    result = []
    paragraph = []
    hidden_level = 0
    included = not history
    fenced = False

    def flush():
        if paragraph:
            result.append(' '.join(paragraph))
            paragraph.clear()

    for raw in markdown[:MAX_NOTES].splitlines():
        heading = _HEADING.match(raw)
        if heading:
            level, title = len(heading[1]), heading[2]
            if re.match(r'^\[?unreleased(?:\]|\s|$|\()', title, re.IGNORECASE):
                flush()
                hidden_level = level
                continue
            if hidden_level and level <= hidden_level:
                hidden_level = 0
            if not hidden_level and _VERSION.match(title):
                included = True
        if hidden_level or not included:
            continue
        line = raw.strip()
        if line.startswith(('```', '~~~')):
            flush()
            fenced = not fenced
            continue
        if not line or re.fullmatch(r'[-*_]{3,}', line):
            flush()
            continue
        if re.match(r'^\[[^\]]+\]:\s*\S+', line):
            continue
        line = re.sub(r'!?\[([^\]]*)\]\([^\n)]*\)', r'\1', line)
        line = re.sub(r'\[([^\]]+)\]\[[^\]]*\]', r'\1', line)
        line = re.sub(r'<[^>\n]*>', '', line)
        line = html.unescape(line)
        line = ''.join(c for c in line if c >= ' ' and c != '\x7f')
        line = re.sub(r'(?<!\\)(\*\*|__|~~|`)', '', line)
        line = re.sub(r'(?<!\w)[*_]([^*_]+)[*_](?!\w)', r'\1', line)
        line = re.sub(r'\\([\\`*_{}\[\]()#+.!>-])', r'\1', line)
        if heading:
            flush()
            result.append(re.sub(r'^#{1,6}\s+', '', line).strip())
        elif re.match(r'^[-*+]\s+', line):
            flush()
            paragraph.append('• '+re.sub(r'^[-*+]\s+', '', line))
        elif line.startswith('|'):
            flush()
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            if not all(re.fullmatch(r':?-+:?', cell) for cell in cells):
                result.append(' · '.join(cells))
        elif fenced or re.match(r'^\d+[.)]\s+', line):
            flush()
            result.append(line)
        else:
            paragraph.append(line)
    flush()
    return '\n\n'.join(result)
