# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Validated appearance preferences, independent of GTK and geometry."""
import json
import re

MODES = ('dark', 'light')
PRESETS = {'ratiolab': 'RatioLab', 'slate': 'Slate', 'nord': 'Nord', 'warm': 'Warm'}
MAX_THEME_BYTES = 128 * 1024
INTERFACE_ROLES = {'window': 'Window background', 'surface': 'Panels and buttons',
                   'input': 'Input fields', 'text': 'Primary text', 'muted': 'Secondary text',
                   'accent': 'Accent color', 'line': 'Borders and dividers'}
VIEW_ROLES = {'background': 'View background', 'grid': 'Grid color',
              'axes': 'Orientation labels', 'selection': 'Selection color'}
BASE_PALETTES = {'dark': {'window': '#1d2229',
          'text': '#e9eef4',
          'muted': '#acb9c9',
          'accent': '#7cc8c8',
          'on_accent': '#102a2c',
          'line': '#38414d',
          'surface': '#242b34',
          'hover': '#303a46',
          'focus': '#9bd8d8',
          'field_label': '#dce4ed',
          'input': '#151b22',
          'active': '#29343e',
          'selected': '#30434a',
          'preview': '#11161d',
          'preview_state': '#253642',
          'preview_text': '#cde4e8',
          'preview_line': '#405465',
          'error_bg': '#382623',
          'error': '#ffb1a5',
          'error_line': '#9b6257',
          'number': '#f0f6fb',
          'warning_bg': '#302a20',
          'warning_line': '#504534',
          'invalid_line': '#704940',
          'warning': '#efbf79',
          'derived': '#27313b',
          'field_error': '#f1a596',
          'io_line': '#718499',
          'io_input': '#e9a45d',
          'io_output': '#74c8a4',
          'io_result': '#addbdd',
          'status': '#a9cdbb',
          'trough': '#3c4754',
          'slider': '#d2dce6'},
 'light': {'window': '#f7f9fa',
           'text': '#263846',
           'muted': '#627380',
           'accent': '#aa633d',
           'on_accent': '#ffffff',
           'line': '#d6dfe5',
           'surface': '#ffffff',
           'hover': '#eef3f5',
           'focus': '#a15b35',
           'field_label': '#354c5b',
           'input': '#ffffff',
           'active': '#e9eef1',
           'selected': '#ead8cb',
           'preview': '#e9eef1',
           'preview_state': '#f7f9fa',
           'preview_text': '#425565',
           'preview_line': '#bbcbd5',
           'error_bg': '#fbe9e5',
           'error': '#9b362b',
           'error_line': '#bc7368',
           'number': '#122638',
           'warning_bg': '#f8edda',
           'warning_line': '#d7b98d',
           'invalid_line': '#bc7368',
           'warning': '#805518',
           'derived': '#edf2f5',
           'field_error': '#9b362b',
           'io_line': '#718499',
           'io_input': '#a15b35',
           'io_output': '#28775b',
           'io_result': '#466777',
           'status': '#37694f',
           'trough': '#c6d2da',
           'slider': '#263846'}}
BASE_PREVIEW = {'dark': {'background': (0.065, 0.085, 0.115),
          'grid': (0.12, 0.16, 0.205),
          'axes': (0.76, 0.84, 0.9),
          'selection': (1.0, 0.78, 0.18)},
 'light': {'background': (0.9137254901960784, 0.9333333333333333, 0.9450980392156862),
           'grid': (0.7450980392156863, 0.796078431372549, 0.8313725490196079),
           'axes': (0.25882352941176473, 0.3333333333333333, 0.396078431372549),
           'selection': (0.72, 0.36, 0.14)}}

_FAMILIES = {
    'slate': {
        'dark': ('#1b1d22','#24272d','#14161a','#eef2f7','#bac3cf','#94a3b8','#3a404a',
                 '#101216','#252a34','#b5bfce','#fbbf24'),
        'light': ('#f3f4f6','#ffffff','#ffffff','#263344','#667487','#475569','#cdd3dd',
                  '#e5e7eb','#c4ccd5','#526171','#cf640e')},
    'nord': {
        'dark': ('#2e3440','#3b4252','#242933','#eceff4','#b9c5d6','#88c0d0','#4c566a',
                 '#242933','#3b4252','#b4c7d8','#ebcb8b'),
        'light': ('#eceff4','#ffffff','#e5e9f0','#2e3440','#526178','#4c6f8c','#c7ceda',
                  '#e5e9f0','#c0c9d6','#4c566a','#a66128')},
    'warm': {
        'dark': ('#282321','#332b27','#211c1a','#f2e7db','#c8b7a4','#deac86','#514239',
                 '#1e1917','#41352d','#d2bca4','#e9ba79'),
        'light': ('#f8f4ee','#fffcf7','#fffefd','#3c2f28','#79685b','#a35b36','#dccfc1',
                  '#eee6db','#d1c0ad','#786252','#b85d26')},
}

# Match the orientation cube's existing labels; the old GL-only axes entry was unused.
BASE_PREVIEW['dark']['axes'] = (.87, .93, .95)
BASE_PREVIEW['light']['axes'] = (.15, .23, .28)


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', value.strip()):
        raise ValueError('Use a color in #RRGGBB format.')
    value = value.strip().lower()
    return '#' + ''.join(c * 2 for c in value[1:]) if len(value) == 4 else value


def rgb(value):
    value = color(value)
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


def hex_color(values):
    return '#' + ''.join(f'{round(min(1, max(0, v)) * 255):02x}' for v in values)


def mix(first, second, amount):
    return hex_color(tuple(a * (1 - amount) + b * amount for a, b in zip(rgb(first), rgb(second))))


def luminance(value):
    return sum(weight * (v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4)
               for weight, v in zip((.2126, .7152, .0722), rgb(value)))


def contrast(first, second):
    a, b = sorted((luminance(first), luminance(second)))
    return (b + .05) / (a + .05)


def _related(palette):
    accent, text, surface = (palette[k] for k in ('accent', 'text', 'surface'))
    palette.update(on_accent=max(('#000000', '#ffffff'), key=lambda c: contrast(c, accent)),
                   focus=mix(accent, text, .2), hover=mix(surface, text, .07),
                   active=mix(surface, accent, .08), selected=mix(surface, accent, .22),
                   field_label=text, number=text, derived=mix(surface, accent, .06),
                   io_input=accent, io_result=mix(accent, text, .35),
                   trough=palette['line'], slider=text,
                   preview_state=surface, preview_text=text, preview_line=palette['line'])
    return palette


def defaults():
    return {'version': 1, 'active': dict.fromkeys(MODES, 'ratiolab'), 'overrides': {}, 'imported': {}}


def _colors(raw, allowed, strict=False):
    if not isinstance(raw, dict):
        if strict:raise ValueError('Invalid theme colors.')
        return {}
    result = {}
    for key, value in raw.items():
        if key not in allowed:
            if strict:raise ValueError('Unknown theme color.')
            continue
        try:result[key] = color(value)
        except ValueError:
            if strict:raise
    return result


def normalize(raw):
    result = defaults()
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw['version'] != 1:
        return result
    imported = raw.get('imported', {})
    if isinstance(imported, dict):
        for mode in MODES:
            item = imported.get(mode)
            if not isinstance(item, dict):continue
            name = item.get('name', 'Imported theme')
            if not isinstance(name, str) or not name.strip() or any(ord(c) < 32 for c in name):name = 'Imported theme'
            result['imported'][mode] = dict(name=name[:80],
                colors=_colors(item.get('colors', {}), BASE_PALETTES[mode]),
                viewport=_colors(item.get('viewport', {}), VIEW_ROLES))
    overrides = raw.get('overrides', {})
    if isinstance(overrides, dict):
        for mode in MODES:
            for preset in (*PRESETS, 'custom'):
                item = overrides.get(mode + ':' + preset)
                if isinstance(item, dict):
                    result['overrides'][mode + ':' + preset] = dict(
                        colors=_colors(item.get('colors', {}), BASE_PALETTES[mode]),
                        viewport=_colors(item.get('viewport', {}), VIEW_ROLES))
    active = raw.get('active', {})
    if isinstance(active, dict):
        for mode in MODES:
            value = active.get(mode)
            if isinstance(value, str) and (value in PRESETS or value == 'custom' and mode in result['imported']):
                result['active'][mode] = value
    return result


def palette(mode, config=None, preset=None, *, customized=True):
    mode = mode if mode in MODES else 'dark'
    config = normalize(config)
    preset = preset or config['active'][mode]
    result = BASE_PALETTES[mode].copy()
    if preset in _FAMILIES:
        result.update(zip(INTERFACE_ROLES, _FAMILIES[preset][mode][:7]))
        _related(result)
        result['preview'] = _FAMILIES[preset][mode][7]
    elif preset == 'custom':
        imported = config['imported'].get(mode, {}).get('colors', {})
        if any(k in imported for k in INTERFACE_ROLES):
            result.update({k: v for k, v in imported.items() if k in INTERFACE_ROLES})
            _related(result)
        result.update(imported)
    override = config['overrides'].get(mode + ':' + preset, {}).get('colors', {}) if customized else {}
    if any(k in override for k in INTERFACE_ROLES):
        result.update({k: v for k, v in override.items() if k in INTERFACE_ROLES})
        _related(result)
    result.update(override)
    return result


def viewport(mode, config=None, preset=None, *, customized=True):
    mode = mode if mode in MODES else 'dark'
    config = normalize(config)
    preset = preset or config['active'][mode]
    result = BASE_PREVIEW[mode].copy()
    if preset in _FAMILIES:
        result.update((k, rgb(v)) for k, v in zip(VIEW_ROLES, _FAMILIES[preset][mode][7:]))
    elif preset == 'custom':
        result.update((k, rgb(v)) for k, v in config['imported'].get(mode, {}).get('viewport', {}).items())
    if customized:
        result.update((k, rgb(v)) for k, v in config['overrides'].get(mode + ':' + preset, {}).get('viewport', {}).items())
    return result


def change_color(config, mode, group, key, value):
    result = normalize(config)
    allowed = BASE_PALETTES[mode] if group == 'colors' else VIEW_ROLES if group == 'viewport' else {}
    if key not in allowed:raise ValueError('Unknown theme color.')
    slot = mode + ':' + result['active'][mode]
    entry = result['overrides'].setdefault(slot, {'colors': {}, 'viewport': {}})
    if value is None:entry[group].pop(key, None)
    else:entry[group][key] = color(value)
    return result


def export_theme(mode, config):
    config = normalize(config)
    preset = config['active'][mode]
    name = config['imported'].get(mode, {}).get('name', 'Imported theme') if preset == 'custom' else PRESETS[preset]
    return {'format': 'ratiolab-theme/1', 'name': name, 'mode': mode,
            'colors': palette(mode, config), 'viewport': {k: hex_color(v) for k, v in viewport(mode, config).items()}}


def import_theme(document, config):
    if isinstance(document, (str, bytes)):
        if len(document.encode('utf-8') if isinstance(document, str) else document) > MAX_THEME_BYTES:
            raise ValueError('Theme file is too large.')
        try:document = json.loads(document)
        except (ValueError, UnicodeError):raise ValueError('Not a RatioLab theme file.') from None
    if not isinstance(document, dict) or document.get('format') != 'ratiolab-theme/1':
        raise ValueError('Not a RatioLab theme file.')
    if set(document) - {'format', 'name', 'mode', 'colors', 'viewport'}:
        raise ValueError('Unknown theme field.')
    mode = document.get('mode')
    if not isinstance(mode, str) or mode not in MODES:raise ValueError('Invalid theme mode.')
    name = document.get('name', 'Imported theme')
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Invalid theme name.')
    colors = _colors(document.get('colors', {}), BASE_PALETTES[mode], strict=True)
    view = _colors(document.get('viewport', {}), VIEW_ROLES, strict=True)
    if not colors and not view:raise ValueError('Invalid theme colors.')
    result = normalize(config)
    result['imported'][mode] = dict(name=name.strip(), colors=colors, viewport=view)
    result['overrides'].pop(mode + ':custom', None)
    result['active'][mode] = 'custom'
    return result, mode
