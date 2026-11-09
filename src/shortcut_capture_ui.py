# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Capture keys without executing application commands while recording."""
from gi.repository import Gtk, Gdk
from keyboard_shortcuts import COMMANDS, MODIFIER_KEYS, BindingError, label, stroke


class Recorder:
    def __init__(self, panel, command):
        self.panel = panel
        self.command = command
        self.keyboard = panel.app.keyboard
        values = self.keyboard.config['bindings'][command]
        self.pending = values[0].split() if values else []
        self.first = True
        self.down = set()
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                       css_classes=['shortcut-recorder'])
        self.widget = body
        body.append(Gtk.Label(label=COMMANDS[command], xalign=0, css_classes=['step-title']))
        body.append(panel._label('Press the desired shortcut. Escape cancels.'))
        self.preview = Gtk.Label(css_classes=['recorded-shortcut'])
        self.preview._ratiolab_no_translate = True
        body.append(self.preview)
        self.sequence = Gtk.CheckButton(label='Sequence of two keys', active=len(self.pending) == 2)
        self.sequence.set_visible(command.startswith('view-'))
        self.sequence.connect('toggled', self._mode_changed)
        body.append(self.sequence)
        self.error = panel._label('')
        self.error.add_css_class('error')
        self.error.set_visible(False)
        body.append(self.error)
        buttons = Gtk.Box(spacing=8)
        body.append(buttons)
        clear = Gtk.Button(label='Clear shortcut')
        clear.connect('clicked', lambda *_: self.apply([]))
        buttons.append(clear)
        buttons.append(Gtk.Box(hexpand=True))
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_: self.close())
        self.cancel_button = cancel
        buttons.append(cancel)
        self.apply_button = Gtk.Button(label='Apply', css_classes=['primary'])
        self.apply_button.connect('clicked', lambda *_: self.apply([' '.join(self.pending)]))
        buttons.append(self.apply_button)
        self.keyboard.recording = True
        self.keyboard.rebuild()
        self.release_handler = panel.keys.connect('key-released', self.key_released)
        panel.recorder_slot.append(body)
        self.refresh()
        panel.app.language.refresh()
        self.focus()

    def focus(self):
        self.cancel_button.grab_focus()

    def _mode_changed(self, *_):
        self.pending = []
        self.first = True
        self.refresh()

    def refresh(self):
        self.preview.set_text(label([' '.join(self.pending)]) if self.pending else '—')
        required = 2 if self.sequence.get_active() else 1
        self.apply_button.set_sensitive(len(self.pending) == required)
        self.error.set_visible(False)

    def key_pressed(self, _, key, keycode, state):
        if key == Gdk.KEY_Escape:
            self.close()
            return True
        if key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            return False
        if key in MODIFIER_KEYS:
            return True
        token = keycode or key
        if token in self.down:
            return True
        self.down.add(token)
        if self.first or not self.sequence.get_active() or len(self.pending) == 2:
            self.pending = []
        self.first = False
        self.pending.append(stroke(key, state))
        self.refresh()
        return True

    def key_released(self, _, key, *args):
        self.down.discard((args[0] if args else 0) or key)

    def apply(self, values):
        try:
            self.keyboard.assign(self.command, values)
        except BindingError as error:
            self.panel.show_shortcut_error(self.error, error)
            return
        self.close()

    def close(self):
        self.panel.keys.disconnect(self.release_handler)
        self.panel.recorder_slot.remove(self.widget)
        self.panel.capture = None
        self.keyboard.recording = False
        self.keyboard.rebuild()
