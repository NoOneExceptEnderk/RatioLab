# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native File menu, using existing project commands and their enabled states."""
from gi.repository import Gio, GLib
from ui_language import translate


SECTIONS = (
    (('new', 'New project'), ('open', 'Open project…'), ('recent', 'Recent projects…')),
    (('save', 'Save'), ('save-as', 'Save As…')),
    (('reset-defaults', 'Reset defaults'), ('undo-reset', 'Undo reset')),
    (('updates', 'Release notes and updates…'),),
)


class Controller:
    def __init__(self, app):
        self.app = app
        self.model = Gio.Menu()
        self.language = None
        self.handlers = []
        self.actions = {}
        for command, button in app.file_command_buttons.items():
            action = app.lookup_action(command)
            if action is None:
                action = Gio.SimpleAction.new(command, None)
                action.connect('activate', lambda *_, button=button:
                               button.emit('clicked') if button.get_sensitive() else None)
                app.add_action(action)
            self.actions[command] = action
            def enabled(*_, command=command, button=button, action=action):
                action.set_enabled(button.get_sensitive() and
                                   (command != 'undo-reset' or button.get_visible()))
            for signal in ('notify::sensitive', 'notify::visible'):
                self.handlers.append((button, button.connect(signal, enabled)))
            enabled()
        app.file_menu.get_popover().set_menu_model(self.model)
        app.win.connect('unrealize', self.close)
        self.refresh_language(app.workspace_preferences['language'])

    def refresh_language(self, language):
        if language == self.language:
            return
        self.language = language
        self.model.remove_all()
        self.app.file_menu.set_label(translate('File', language))
        for rows in SECTIONS:
            section = Gio.Menu()
            for command, title in rows:
                item = Gio.MenuItem.new(translate(title, language), 'app.' + command)
                if command == 'undo-reset':
                    item.set_attribute_value('hidden-when', GLib.Variant('s', 'action-disabled'))
                section.append_item(item)
            self.model.append_section(None, section)

    def close(self, *_):
        for widget, handler in self.handlers:
            widget.disconnect(handler)
        self.handlers.clear()
