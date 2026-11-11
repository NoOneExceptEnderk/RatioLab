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


def localize_native_dialog(dialog, language):
    """Translate portal-facing captions at creation, leaving file data untouched."""
    for prop in ('title', 'accept-label', 'cancel-label'):
        value = dialog.get_property(prop)
        if value:
            dialog.set_property(prop, translate(value, language))
    return dialog


_PLACEHOLDER = re.compile(r'\{(value|arg\d+|message\d+)\}')


@lru_cache(maxsize=16)
def _templates(language):
    buckets = {}
    for source, target in catalog()['translations'].get(language, {}).items():
        fields = list(_PLACEHOLDER.finditer(source))
        if not fields or not re.search(r'[A-Za-z]{3}', _PLACEHOLDER.sub('', source)):
            continue
        chunks, names, position = [], [], 0
        for field in fields:
            chunks.append(re.escape(source[position:field.start()]))
            name = field[1]
            if name in names:
                chunks.append(r'(?P='+name+')')
            else:
                names.append(name)
                chunks.append(r'(?P<'+name+'>'+ (r'[+−\-0-9.,eE]+' if name == 'value' else r'.*?') +')')
            position = field.end()
        chunks.append(re.escape(source[position:]))
        prefix = source[:fields[0].start()]
        entry = (prefix, re.compile(''.join(chunks), re.DOTALL), target, len(_PLACEHOLDER.sub('', source)))
        buckets.setdefault(prefix[:1], []).append(entry)
    for entries in buckets.values():
        entries.sort(key=lambda item: (len(item[0]), item[3]), reverse=True)
    return buckets


@lru_cache(maxsize=8192)
def translate(text, language='en'):
    """Translate known UI labels, preserving surrounding symbols and engineering units.

    Dynamic substitutions remain byte-for-byte unchanged. This function is only
    for presentation; it must not be used on serialized data or editable text.
    """
    if not text:
        return text
    messages = catalog()['translations'].get(language, {})
    if text in messages:
        return messages[text]
    templates = _templates(language)
    for prefix, pattern, target, _ in (*templates.get(text[:1], ()), *templates.get('', ())):
        if prefix and not text.startswith(prefix):
            continue
        match = pattern.fullmatch(text)
        if match:
            # One substitution pass: a user value containing braces cannot be
            # interpreted as another placeholder in the translated message.
            return _PLACEHOLDER.sub(lambda field: translate(match[field[1]], language)
                                    if field[1].startswith('message') else match[field[1]], target)
    core = text.strip()
    if not core:
        return text
    if core != text:
        return text[:len(text)-len(text.lstrip())] + translate(core, language) + text[len(text.rstrip()):]
    if '\n' in core:
        return '\n'.join(translate(line, language) for line in core.split('\n'))
    if core[:1].islower() and core.capitalize() in messages:
        return messages[core.capitalize()]
    for prefix in ('☀ ', '☾ ', '文 ', 'A↔ ', '◐ ', '✓ ', '‹ ', '○ ', '● ', '- ', '• '):
        if core.startswith(prefix):
            return prefix + translate(core[len(prefix):], language)
    for suffix in ('…', '...', ':'):
        if core.endswith(suffix):
            return translate(core[:-len(suffix)], language) + suffix
    # Captions retain units and every digit exactly as provided by the engine.
    unit = re.fullmatch(r'(.+?)( (?:· |\[)(?:mm|°|rpm|N|N.m|N·m|%)(?:\])?)', core)
    if unit:
        return translate(unit[1], language) + unit[2]
    for delimiter in (' / ', ' → ', ' · ', '\u2009·\u2009'):
        if delimiter in core:
            return delimiter.join(translate(part, language) for part in core.split(delimiter))
    for prefix in ('Connect ', 'Create in ', 'Import in '):
        if core.startswith(prefix) and core[len(prefix):] in ('SolidCraft', 'Fusion', 'Autodesk Fusion'):
            return translate(prefix.strip(), language) + ' ' + core[len(prefix):]
    return text
