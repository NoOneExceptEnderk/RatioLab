# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Workspace preferences and an explicit project precision editor."""
from gi.repository import Gtk, Gdk, Gio, Pango
import gui_workflow
import workspace_ui
from ui_language import catalog
from keyboard_shortcuts import COMMANDS, PRESETS, BindingError, label, preset_bindings
from mouse_navigation import PROFILES, SUMMARIES


class Controller:
    def __init__(self, app):
        self.app = app
        self.dialog = None
        self.handlers = []
        app.win.connect('unrealize', self._parent_closed)

    def present(self, *_):
        if self.dialog is not None:
            self.dialog.present()
            return self.dialog
        app = self.app
        app.parameter_help.close()
        dialog = Gtk.Dialog(title='Settings', application=app, transient_for=app.win,
                            modal=True, destroy_with_parent=True, use_header_bar=False,
                            default_width=960, default_height=680,
                            css_classes=['reducers', 'settings-panel'])
        self.dialog = dialog
        self.capture = None
        header = Gtk.Box(spacing=12, css_classes=['settings-heading'])
        header.append(Gtk.Label(label='Settings', xalign=0, hexpand=True,
                                css_classes=['step-title']))
        close = Gtk.Button(label='×', tooltip_text='Close dialog', css_classes=['flat'])
        close.update_property([Gtk.AccessibleProperty.LABEL], ['Close dialog'])
        close.connect('clicked', lambda *_: dialog.response(Gtk.ResponseType.CLOSE))
        header.append(close)
        handle = Gtk.WindowHandle()
        handle.set_child(header)
        dialog.set_titlebar(handle)
        body = dialog.get_content_area()
        layout = Gtk.Box(spacing=0, vexpand=True)
        body.append(layout)
        tabs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5,
                       css_classes=['settings-tabs'])
        tabs.set_size_request(165, -1)
        tabs.set_hexpand(False)
        layout.append(tabs)
        self.stack = Gtk.Stack(vexpand=True)
        self.pages = {}
        self.tabs = {}
        group = None
        self.precision_loaded = False
        self.precision_apply = None
        for name, title in [('appearance', 'Appearance'), ('controls', 'Controls'), ('precision', 'Model precision'),
                            ('general', 'General')]:
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                           css_classes=['settings-page'])
            page.append(Gtk.Label(label=title, xalign=0, css_classes=['settings-page-title']))
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                        vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
            scroll.set_child(page)
            self.stack.add_named(scroll, name)
            self.pages[name] = page
            tab = Gtk.ToggleButton(label=title, hexpand=True)
            tab.get_child().set_xalign(0)
            tab.get_child().set_wrap(True)
            tab.get_child().set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            tab.get_child().set_width_chars(1)
            if group is not None:
                tab.set_group(group)
            else:
                group = tab
            tab.connect('toggled', lambda button, name=name:
                        self.stack.set_visible_child_name(name) if button.get_active() else None)
            tabs.append(tab)
            self.tabs[name] = tab
        self.tabs['appearance'].set_active(True)
        self.stack.set_hexpand(True)
        layout.append(self.stack)
        self._appearance()
        self._controls()
        self._general()
        self.stack.connect('notify::visible-child-name', self._page_changed)
        body.append(Gtk.Separator())
        footer = Gtk.Box(spacing=12, css_classes=['settings-footer'])
        self.footer = footer
        message = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        message.append(self._label('Preferences apply immediately. Model precision uses Apply.', muted=True))
        self.error = self._label('Changed for this session. Could not save preference.')
        self.error.add_css_class('error')
        message.append(self.error)
        footer.append(message)
        done = Gtk.Button(label='Close')
        done.connect('clicked', lambda *_: dialog.response(Gtk.ResponseType.CLOSE))
        footer.append(done)
        body.append(footer)
        self._watch(app.theme_error, 'notify::visible', self._refresh_error)
        self._watch(app.language.error, 'notify::visible', self._refresh_error)
        self._refresh_error()
        dialog.connect('response', self._response)
        dialog.connect('unrealize', self._retire)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        self.keys = keys
        keys.connect('key-pressed', self._key_pressed)
        dialog.add_controller(keys)
        app.language.refresh()
        dialog.present()
        self.tabs['appearance'].grab_focus()
        return dialog

    @staticmethod
    def _label(text, muted=False):
        return Gtk.Label(label=text, xalign=0, wrap=True, width_chars=1,
                         wrap_mode=Pango.WrapMode.WORD_CHAR,
                         css_classes=['muted'] if muted else [])

    def _row(self, page, title, control):
        row = Gtk.Box(spacing=18, css_classes=['settings-row'])
        label = self._label(title)
        label.set_hexpand(True)
        control.set_valign(Gtk.Align.CENTER)
        control.set_hexpand(False)
        label.connect('notify::label', lambda widget, *_:
                      control.update_property([Gtk.AccessibleProperty.LABEL], [widget.get_text()]))
        control.update_property([Gtk.AccessibleProperty.LABEL], [title])
        row.append(label)
        row.append(control)
        page.append(row)

    def _watch(self, widget, signal, callback):
        self.handlers.append((widget, widget.connect(signal, callback)))

    def _mirror_choice(self, source, labels):
        control = gui_workflow.choice_dropdown(labels)
        control.set_selected(source.get_selected())
        control.connect('notify::selected', lambda widget, *_:
                        source.set_selected(widget.get_selected()))
        self._watch(source, 'notify::selected', lambda widget, *_:
                    control.set_selected(widget.get_selected()))
        return control

    def _appearance(self):
        page = self.pages['appearance']
        self.theme = self._mirror_choice(self.app.theme_selector, ['Dark', 'Light'])
        self._row(page, 'Color mode', self.theme)
        from theme_editor_ui import ThemeEditor
        self.theme_editor = ThemeEditor(self, page)
        self._watch(self.app.theme_selector, 'notify::selected', self.theme_editor.refresh)
        page.append(Gtk.Separator())
        self.text_size = self._mirror_choice(self.app.text_size, ['100%', '125%', '150%'])
        self._row(page, 'Text size', self.text_size)

    def _controls(self):
        app = self.app
        page = self.pages['controls']
        page.append(Gtk.Label(label='Control preset', xalign=0, css_classes=['step-title']))
        presets = Gtk.Box(spacing=8)
        self.preset_codes = list(PRESETS)
        self.preset = gui_workflow.choice_dropdown(list(PRESETS.values()))
        self.preset._ratiolab_no_translate = True
        self.preset.set_selected(self.preset_codes.index(app.keyboard.config['preset']))
        presets.append(self.preset)
        self.preset_apply = Gtk.Button(label='Apply preset')
        self.preset_apply.connect('clicked', lambda *_: app.keyboard.select_preset(self.preset_codes[self.preset.get_selected()]))
        presets.append(self.preset_apply)
        page.append(presets)
        page.append(self._label('Apply a CAD preset to set keyboard and mouse controls. Sensitivity and zoom direction stay unchanged.', muted=True))
        page.append(Gtk.Separator())
        self.mouse_codes = list(PROFILES)
        self.mouse_navigation = gui_workflow.choice_dropdown(list(PROFILES.values()))
        self.mouse_navigation._ratiolab_no_translate = True
        self.mouse_navigation.set_selected(self.mouse_codes.index(app.workspace_preferences['mouse_navigation']))
        self.mouse_navigation.connect('notify::selected', self._mouse_profile_changed)
        self._row(page, 'Mouse navigation', self.mouse_navigation)
        self.mouse_hint = self._label(SUMMARIES[app.workspace_preferences['mouse_navigation']], muted=True)
        page.append(self.mouse_hint)
        self.mouse = {}
        for key, title in [('zoom_speed', 'Zoom sensitivity'),
                           ('rotation_speed', 'Orbit sensitivity')]:
            control = gui_workflow.choice_dropdown(['0.5×', '1×', '2×'])
            control.set_selected((.5, 1, 2).index(app.workspace_preferences[key]))
            control.connect('notify::selected', lambda widget, *_, key=key:
                            self._navigation(key, (.5, 1, 2)[widget.get_selected()]))
            self._row(page, title, control)
            self.mouse[key] = control
        self.invert_zoom = Gtk.Switch(active=app.workspace_preferences['invert_zoom'],
                                     css_classes=['theme-switch'])
        self.invert_zoom.connect('notify::active', lambda widget, *_:
                                 self._navigation('invert_zoom', widget.get_active()))
        self._row(page, 'Invert zoom direction', self.invert_zoom)
        page.append(Gtk.Separator())
        page.append(Gtk.Label(label='Keyboard shortcuts', xalign=0, css_classes=['step-title']))
        page.append(self._label('CAD presets adapt shared commands. Other keys keep RatioLab defaults. Applying a preset replaces your shortcuts.', muted=True))
        self.shortcut_error = self._label('')
        self.shortcut_error.add_css_class('error')
        self.shortcut_error.set_visible(False)
        page.append(self.shortcut_error)
        self.recorder_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.append(self.recorder_slot)
        shortcuts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                            css_classes=['settings-shortcuts'])
        page.append(shortcuts)
        self.shortcut_rows, self.shortcut_buttons = [], {}
        self.shortcut_containers = {}
        for command, title in COMMANDS.items():
            controls = Gtk.Box(spacing=6)
            button = Gtk.Button(css_classes=['shortcut-binding'])
            key_label = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, max_width_chars=24)
            key_label._ratiolab_no_translate = True
            button.set_child(key_label)
            button.connect('clicked', lambda *_, command=command: self.edit_shortcut(command))
            controls.append(button)
            reset = Gtk.Button(label='↺', tooltip_text='Reset this shortcut', css_classes=['flat'])
            reset.connect('clicked', lambda *_, command=command: self.reset_shortcut(command))
            controls.append(reset)
            self._row(shortcuts, title, controls)
            self.shortcut_rows.append(button)
            self.shortcut_buttons[command] = button
            self.shortcut_containers[command] = controls.get_parent()
        self.reset_all = Gtk.Button(label='Restore RatioLab controls', halign=Gtk.Align.START)
        self.reset_all.connect('clicked', lambda *_: app.keyboard.select_preset('ratiolab'))
        page.append(self.reset_all)
        page.append(self._label('View shortcuts work when the 3D preview or orientation cube has focus. Click the preview first.', muted=True))
        app.keyboard.listeners.append(self.refresh_shortcuts)
        self.refresh_shortcuts()

    def refresh_shortcuts(self):
        from ui_language import translate
        keyboard = self.app.keyboard
        self.preset.set_sensitive(not keyboard.recording)
        self.preset_apply.set_sensitive(not keyboard.recording)
        self.mouse_navigation.set_sensitive(not keyboard.recording)
        self.mouse_navigation.set_selected(self.mouse_codes.index(self.app.workspace_preferences['mouse_navigation']))
        self.mouse_hint.set_text(SUMMARIES[self.app.workspace_preferences['mouse_navigation']])
        self.reset_all.set_sensitive(not keyboard.recording)
        self.preset.set_selected(self.preset_codes.index(keyboard.config['preset']))
        language = self.app.language.language
        defaults = preset_bindings(keyboard.config['preset'])
        for command, button in self.shortcut_buttons.items():
            values = keyboard.config['bindings'][command]
            text = label(values)
            button.get_child().set_text(text or '—')
            button.set_tooltip_text('Change shortcut'+'\n'+text)
            button.update_property([Gtk.AccessibleProperty.LABEL], [translate(COMMANDS[command], language)+': '+(text or '—')])
            if values != defaults[command]:button.add_css_class('custom-binding')
            else:button.remove_css_class('custom-binding')
            self.shortcut_containers[command].set_sensitive(not keyboard.recording)
        self.shortcut_error.set_visible(False)

    def reset_shortcut(self, command):
        try:
            self.app.keyboard.assign(command, preset_bindings(self.app.keyboard.config['preset'])[command])
        except BindingError as error:
            self.show_shortcut_error(self.shortcut_error, error)

    def show_shortcut_error(self, widget, error):
        text = str(error)
        if error.command:
            text = text.replace('{message0}', COMMANDS[error.command])
        widget.set_text(text)
        widget.set_visible(True)
        self.app.language.refresh()

    def edit_shortcut(self, command):
        from shortcut_capture_ui import Recorder
        if self.capture is not None:
            self.capture.focus()
        else:
            self.tabs['controls'].set_active(True)
            self.capture = Recorder(self, command)

    def _navigation(self, key, value):
        setattr(self.app.canvas, key, value)
        workspace_ui.save_ui_preference(self.app, **{key: value})

    def _mouse_profile_changed(self, widget, *_):
        profile = self.mouse_codes[widget.get_selected()]
        if profile != self.app.workspace_preferences['mouse_navigation']:
            self.app.keyboard.select_mouse_profile(profile)

    def _general(self):
        app = self.app
        page = self.pages['general']
        self.language_codes = list(catalog()['languages'])
        self.language = gui_workflow.choice_dropdown(list(catalog()['languages'].values()))
        self.language._ratiolab_no_translate = True
        self.language.set_selected(self.language_codes.index(app.language.language))
        self.language.connect('notify::selected', lambda widget, *_:
                              app.language.change(self.language_codes[widget.get_selected()])
                              if self.language_codes[widget.get_selected()] != app.language.language else None)
        for code, choice in app.language.choices.items():
            self._watch(choice, 'toggled', lambda widget, code=code:
                        self.language.set_selected(self.language_codes.index(code))
                        if widget.get_active() else None)
            self._watch(choice, 'toggled', lambda widget: self.refresh_shortcuts() if widget.get_active() else None)
        self._row(page, 'Language', self.language)
        self.hover_help = Gtk.Switch(active=app.workspace_preferences['hover_help'],
                                    css_classes=['theme-switch'])
        self.hover_help.connect('notify::active', self._hover_changed)
        self._row(page, 'Show parameter help on hover', self.hover_help)
        page.append(self._label('Parameter guides remain available with F1 or the information button.', muted=True))
        page.append(Gtk.Separator())
        updates = Gtk.Button(label='Release notes and updates…', halign=Gtk.Align.START)
        updates.connect('clicked', self._updates)
        page.append(updates)

    def _page_changed(self, *_):
        selected = self.stack.get_visible_child_name() == 'precision'
        if self.precision_apply is not None:self.precision_apply.set_visible(selected)
        if not selected or self.precision_loaded:
            return
        from quality_ui import open_quality
        self.precision_loaded = True
        if open_quality(self.app, host=self.dialog, container=self.pages['precision']) is None:
            self.pages['precision'].append(self._label('Finish the current model operation and reopen Settings to edit precision.'))
        else:
            self.precision_apply = self.app.quality_apply_button
            self.precision_apply.get_parent().remove(self.precision_apply)
            self.precision_apply.set_valign(Gtk.Align.CENTER)
            self.footer.insert_child_after(self.precision_apply,self.footer.get_first_child())
        self.app.language.refresh()

    def _hover_changed(self, widget, *_):
        enabled = widget.get_active()
        if not enabled:
            self.app.parameter_help.cancel_timers()
            if self.app.parameter_help.activation == 'pointer':
                self.app.parameter_help.close()
        workspace_ui.save_ui_preference(self.app, hover_help=enabled)

    def _updates(self, *_):
        self.dialog.response(Gtk.ResponseType.CLOSE)
        self.app.updates.show(manual=True)

    def _refresh_error(self, *_):
        self.error.set_visible(self.app.theme_error.get_visible() or self.app.language.error.get_visible())

    def _response(self, dialog, *_):
        self.theme_editor.close()
        dialog.destroy()

    def _key_pressed(self, _, key, keycode, state):
        if self.capture is not None:
            return self.capture.key_pressed(_, key, keycode, state)
        from keyboard_shortcuts import stroke
        if key == Gdk.KEY_Escape and self.theme_editor.file_dialog is not None:
            self.theme_editor.retire_file_dialog()
            return True
        if key == Gdk.KEY_Escape or stroke(key, state) in self.app.keyboard.config['bindings']['close']:
            self.dialog.response(Gtk.ResponseType.CLOSE)
            return True
        return False

    def _retire(self, *_):
        self.theme_editor.close()
        self.app.keyboard.listeners.remove(self.refresh_shortcuts)
        if self.capture is not None:
            self.capture.close()
        for widget, handler in self.handlers:
            widget.disconnect(handler)
        self.handlers.clear()
        self.dialog = None

    def _parent_closed(self, *_):
        if self.dialog is not None:
            self.theme_editor.close()
            self.dialog.destroy()


def install(app):
    app.settings = Controller(app)
    action = Gio.SimpleAction.new('settings', None)
    action.connect('activate', app.settings.present)
    app.add_action(action)
    button = Gtk.Button(label='Settings', tooltip_text='Settings · Ctrl+,', css_classes=['flat'])
    button.set_action_name('app.settings')
    app.secondary_toolbar.append(button)
    workspace_ui.decorate_action(button, 'settings', vector=True)
    app.settings_button = button
    # Keep the existing focus-away alias pointing at a visible preferences action.
    app.appearance_button = button
    app.keyboard.rebuild()
