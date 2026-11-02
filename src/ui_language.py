# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Presentation-only UI messages shared with the browser. Never localize model data."""
import json
import re
from functools import lru_cache


@lru_cache(maxsize=1)
def catalog():
    from app_paths import resource_path
    return json.loads(resource_path('ui-translations.json').read_text(encoding='utf-8'))


def translate(text, language='en'):
    """Translate known UI labels, preserving surrounding symbols and engineering units.

    Uncatalogued technical prose intentionally falls back to its English source.
    This function is only for presentation; it must not be used on serialized data.
    """
    if not text or language == 'en':
        return text
    messages = catalog()['translations'].get(language, {})
    if text in messages:
        return messages[text]
    for source, target in messages.items():
        if '{value}' in source:
            pattern = re.escape(source).replace(r'\{value\}', r'([+−\-0-9.,eE]+)')
            match = re.fullmatch(pattern, text)
            if match:
                return target.replace('{value}', match[1])
    core = text.strip()
    if not core:
        return text
    if core != text:
        return text[:len(text)-len(text.lstrip())] + translate(core, language) + text[len(text.rstrip()):]
    for prefix in ('☀ ', '☾ ', '文 ', 'A↔ ', '◐ ', '✓ ', '‹ ', '○ ', '● '):
        if core.startswith(prefix):
            return prefix + translate(core[len(prefix):], language)
    for suffix in ('…', '...', ':'):
        if core.endswith(suffix):
            return translate(core[:-len(suffix)], language) + suffix
    # Captions retain units and every digit exactly as provided by the engine.
    unit = re.fullmatch(r'(.+?)( (?:· |\[)(?:mm|°|rpm|N|N.m|N·m|%)(?:\])?)', core)
    if unit:
        return translate(unit[1], language) + unit[2]
    for delimiter in (' / ', ' · ', '\u2009·\u2009'):
        if delimiter in core:
            return delimiter.join(translate(part, language) for part in core.split(delimiter))
    for prefix in ('Connect ', 'Create in ', 'Import in '):
        if core.startswith(prefix) and core[len(prefix):] in ('SolidCraft', 'Fusion', 'Autodesk Fusion'):
            return translate(prefix.strip(), language) + ' ' + core[len(prefix):]
    return text
