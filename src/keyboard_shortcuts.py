# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Validated desktop key maps and focus-scoped viewport sequences."""
from copy import deepcopy
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app_paths


COMMANDS = {
    'new': 'New project', 'open': 'Open project…', 'save': 'Save',
    'save-as': 'Save As…', 'undo': 'Undo', 'redo': 'Redo', 'export': 'Export',
    'close': 'Close', 'settings': 'Settings', 'view-fit': 'Fit model',
    'view-iso': 'Isometric view', 'view-front': 'Front', 'view-back': 'Back',
    'view-left': 'Left', 'view-right': 'Right', 'view-top': 'Top', 'view-bottom': 'Bottom',
}
DEFAULTS = {
    'new': ['<Control>n'], 'open': ['<Control>o'], 'save': ['<Control>s'],
    'save-as': ['<Control><Shift>s'], 'undo': ['<Control>z'],
    'redo': ['<Control><Shift>z', '<Control>y'], 'close': ['<Control>w'],
    'export': ['<Control>e'], 'settings': ['<Control>comma'],
    'view-fit': ['f'], 'view-iso': ['Home'], 'view-front': ['1'],
    'view-back': ['2'], 'view-right': ['3'], 'view-left': ['4'],
    'view-top': ['5'], 'view-bottom': ['6'],
}
PRESETS = {'ratiolab': 'RatioLab', 'freecad': 'FreeCAD', 'fusion': 'Fusion',
           'solidworks': 'SOLIDWORKS', 'inventor': 'Inventor', 'solidcraft': 'SolidCraft'}
_ORTHOGRAPHIC = {'view-'+name: ['<Control>'+str(index)] for index, name in
                 enumerate(('front', 'back', 'left', 'right', 'top', 'bottom', 'iso'), 1)}
_OVERRIDES = {
    'ratiolab': {},
    'freecad': {'view-fit': ['v f'], 'view-iso': ['0'], 'view-front': ['1'],
                'view-top': ['2'], 'view-right': ['3'], 'view-back': ['4'],
                'view-bottom': ['5'], 'view-left': ['6'], 'redo': ['<Control>y']},
    'fusion': {'view-fit': ['F6'], 'redo': ['<Control>y']},
    'solidworks': dict(_ORTHOGRAPHIC, **{'view-fit': ['f'], 'redo': ['<Control>y']}),
    'inventor': {'view-fit': ['Home'], 'view-iso': ['F6'], 'redo': ['<Control>y']},
    'solidcraft': dict(_ORTHOGRAPHIC, **{'view-fit': ['F6'], 'redo': ['<Control>y']}),
}
MODIFIERS = (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK |
             Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.META_MASK)
MODIFIER_KEYS = {Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
                 Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Meta_L, Gdk.KEY_Meta_R,
                 Gdk.KEY_Super_L, Gdk.KEY_Super_R, Gdk.KEY_Caps_Lock, Gdk.KEY_ISO_Level3_Shift}
_RESERVED = {'Escape', 'Tab', 'ISO_Left_Tab', 'Return', 'KP_Enter', 'space',
             'BackSpace', 'Delete', 'Left', 'Right', 'Up', 'Down', 'F1',
             '<Alt>F4', '<Control>c', '<Control>x', '<Control>v', '<Control>a',
             '<Alt>1', '<Alt>2', '<Alt>3'}


class BindingError(ValueError):
    def __init__(self, message, command=None):
        super().__init__(message)
        self.command = command


def stroke(key, state):
    return Gtk.accelerator_name(Gdk.keyval_to_lower(key), state & MODIFIERS)


def normalize(sequence):
    if not isinstance(sequence, str) or not sequence or len(sequence) > 100:
        raise BindingError('Choose a valid shortcut.')
    parts = sequence.split()
    if not 1 <= len(parts) <= 2:
        raise BindingError('Use one key combination or a sequence of two keys.')
    normalized = []
    for part in parts:
        valid, key, modifiers = Gtk.accelerator_parse(part)
        if (not valid or not key or key in MODIFIER_KEYS or modifiers & ~MODIFIERS
                or Gdk.keyval_to_lower(key) != key):
            raise BindingError('Choose a valid shortcut.')
        name = stroke(key, modifiers)
        # Keep editing/navigation and contextual help available in every preset.
        if (name in _RESERVED or key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Escape,
                                         Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_F1)
                or modifiers and key in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down,
                                          Gdk.KEY_BackSpace, Gdk.KEY_Delete)):
            raise BindingError('This shortcut is reserved for text editing, navigation or help.')
        normalized.append(name)
    return ' '.join(normalized)


def validate(bindings, edited=None):
    if not isinstance(bindings, dict) or set(bindings) != set(COMMANDS):
        raise BindingError('Invalid shortcut configuration.')
    result, used = {command: [] for command in bindings}, []
    for command in [name for name in bindings if name != edited]+([edited] if edited in bindings else []):
        values = bindings[command]
        if not isinstance(values, list) or len(values) > 2:
            raise BindingError('Choose a valid shortcut.')
        result[command] = []
        for value in values:
            value = normalize(value)
            parts = tuple(value.split())
            if not command.startswith('view-'):
                _, key, modifiers = Gtk.accelerator_parse(parts[0])
                if len(parts) != 1 or not (modifiers & ~Gdk.ModifierType.SHIFT_MASK or Gdk.KEY_F2 <= key <= Gdk.KEY_F35):
                    raise BindingError('Use Ctrl, Alt or a function key for project commands.')
            for other, occupied in used:
                if parts == occupied or parts[:len(occupied)] == occupied or occupied[:len(parts)] == parts:
                    raise BindingError('This shortcut conflicts with {message0}.', other)
            result[command].append(value)
            used.append((command, parts))
    return result


def preset_bindings(preset):
    if preset not in PRESETS:
        raise BindingError('Unknown shortcut preset.')
    result = deepcopy(DEFAULTS)
    result.update(deepcopy(_OVERRIDES[preset]))
    return validate(result)


def configuration(data):
    """Reject a malformed key map as a whole; partial recovery can create conflicts."""
    fallback = dict(version=1, preset='ratiolab', bindings=preset_bindings('ratiolab'))
    if (not isinstance(data, dict) or type(data.get('version')) is not int
            or data.get('version') != 1 or not isinstance(data.get('preset'), str)
            or data.get('preset') not in PRESETS):
        return fallback
    try:
        return dict(version=1, preset=data['preset'], bindings=validate(data['bindings']))
    except (BindingError, KeyError, TypeError):
        return fallback


def label(values):
    return ' / '.join(', '.join(Gtk.accelerator_get_label(*Gtk.accelerator_parse(part)[1:])
                              for part in value.split()) for value in values)


class Controller:
    def __init__(self, app):
        self.app = app
        self.config = configuration(app_paths.load_preferences(legacy_root=app.BASE).get('keyboard_shortcuts'))
        app.workspace_preferences['keyboard_shortcuts'] = deepcopy(self.config)
        self.listeners = []
        self.pending = ()
        self.timer = 0
        self.recording = False
        self.history = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL,
                                              propagation_phase=Gtk.PropagationPhase.CAPTURE)
        app.win.add_controller(self.history)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._key_pressed)
        app.win.add_controller(keys)
        app.win.connect('notify::focus-widget', lambda *_: self.cancel_sequence())
        app.win.connect('unrealize', lambda *_: self.cancel_sequence())
        app.canvas.keyboard_shortcuts = self
        app.canvas.set_mouse_navigation(app.workspace_preferences['mouse_navigation'])
        for command in COMMANDS:
            if command.startswith('view-'):
                action = Gio.SimpleAction.new(command, None)
                action.connect('activate', lambda *_, name=command[5:]: self.view(name))
                app.add_action(action)
        self.rebuild()

    def view(self, name):
        if name == 'fit':
            from workspace_ui import fit_camera
            fit_camera(self.app)
        else:
            self.app.select_view(name)

    def rebuild(self):
        self.cancel_sequence()
        for shortcut in getattr(self.app, 'history_shortcuts', []):
            self.history.remove_shortcut(shortcut)
        self.app.history_shortcuts = []
        for command, values in self.config['bindings'].items():
            if command.startswith('view-'):
                continue
            self.app.set_accels_for_action('app.'+command, [] if self.recording else values)
            if command in ('undo', 'redo') and not self.recording:
                for value in values:
                    shortcut = Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(value),
                                                Gtk.NamedAction.new('app.'+command))
                    self.history.add_shortcut(shortcut)
                    self.app.history_shortcuts.append(shortcut)
        for command, attr in [('undo', 'undo_button'), ('redo', 'redo_button'), ('settings', 'settings_button')]:
            button = getattr(self.app, attr, None)
            if button:
                button.set_tooltip_text(COMMANDS[command]+'\n'+(label(self.config['bindings'][command]) or 'Not assigned'))
        for listener in tuple(self.listeners):
            listener()

    def change(self, bindings, preset=None, edited=None, mouse_profile=None):
        bindings = validate(bindings, edited=edited)
        if mouse_profile is not None:
            self.app.canvas.set_mouse_navigation(mouse_profile)
            self.app.workspace_preferences['mouse_navigation'] = self.app.canvas.mouse_navigation
        self.config = dict(version=1, preset=preset or self.config['preset'], bindings=bindings)
        self.rebuild()
        from workspace_ui import save_ui_preference
        save_ui_preference(self.app, keyboard_shortcuts=deepcopy(self.config))

    def assign(self, command, values):
        bindings = deepcopy(self.config['bindings'])
        bindings[command] = values
        self.change(bindings, edited=command)

    def select_preset(self, preset):
        self.change(preset_bindings(preset), preset, mouse_profile=preset)

    def select_mouse_profile(self, profile):
        from workspace_ui import save_ui_preference
        self.app.canvas.set_mouse_navigation(profile)
        save_ui_preference(self.app, mouse_navigation=self.app.canvas.mouse_navigation)
        self.rebuild()

    def cancel_sequence(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        self.pending = ()

    def _expired(self):
        self.timer = 0
        self.pending = ()
        return GLib.SOURCE_REMOVE

    def _key_pressed(self, _, key, keycode, state):
        focus = self.app.win.get_focus()
        if self.recording or focus not in (self.app.canvas, getattr(self.app, 'navigation_cube', None)):
            self.cancel_sequence()
            return False
        return self.view_key(key, state)

    def view_key(self, key, state):
        if self.recording:
            return False
        value = stroke(key, state)
        candidate = self.pending+(value,)
        self.cancel_sequence()
        for attempt in (candidate, (value,)) if len(candidate) > 1 else (candidate,):
            prefixes = False
            for command, values in self.config['bindings'].items():
                if not command.startswith('view-'):
                    continue
                for sequence in values:
                    parts = tuple(sequence.split())
                    if parts == attempt:
                        self.app.activate_action(command, None)
                        return True
                    prefixes = prefixes or parts[:len(attempt)] == attempt
            if prefixes:
                self.pending = attempt
                self.timer = GLib.timeout_add(1200, self._expired)
                return True
        return False
