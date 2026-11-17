# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Workspace preferences and an explicit project precision editor."""
from pathlib import Path
import subprocess
import threading
from gi.repository import Gtk, Gdk, Gio, GLib, Pango
import app_paths
import gui_workflow
import mcp_clients
import mcp_registration
import workspace_ui
from ui_language import catalog
from keyboard_shortcuts import COMMANDS, PRESETS, BindingError, label, preset_bindings
from mouse_navigation import PROFILES, SUMMARIES


class Controller:
    def __init__(self, app):
        self.app = app
        self.dialog = None
        self.handlers = []
        self.mcp_registering = False
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
        self.mcp_chooser = None
        self.mcp_folder_page = None
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
                            ('general', 'General'), ('mcp', 'MCP')]:
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                           css_classes=['settings-page'])
            page.append(Gtk.Label(label=title, xalign=0, css_classes=['settings-page-title']))
            if name == 'mcp':
                self.stack.add_named(page, name)
            else:
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
        self._mcp()
        body.append(Gtk.Separator())
        footer = Gtk.Box(spacing=12, css_classes=['settings-footer'])
        self.footer = footer
        message = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        self.preference_hint = self._label('Preferences apply immediately. Model precision uses Apply.', muted=True)
        message.append(self.preference_hint)
        self.error = self._label('Changed for this session. Could not save preference.')
        self.error.add_css_class('error')
        message.append(self.error)
        footer.append(message)
        done = Gtk.Button(label='Close')
        done.connect('clicked', lambda *_: dialog.response(Gtk.ResponseType.CLOSE))
        footer.append(done)
        body.append(footer)
        self.stack.connect('notify::visible-child-name', self._page_changed)
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

    def _mcp(self):
        page = self.pages['mcp']
        workspace = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=['mcp-workspace'])
        heading = Gtk.Box(spacing=8)
        heading.append(Gtk.Image.new_from_icon_name('folder-symbolic'))
        heading.append(Gtk.Label(label='MCP workspace', xalign=0, css_classes=['mcp-section']))
        workspace.append(heading)
        folder = Gtk.Box(spacing=10)
        self.mcp_path = Gtk.Entry(editable=False, hexpand=True, placeholder_text='No folder selected')
        self.mcp_path.update_property([Gtk.AccessibleProperty.LABEL], ['MCP workspace'])
        folder.append(self.mcp_path)
        self.mcp_browse = Gtk.Button(label='Change folder…')
        self.mcp_browse.connect('clicked', self._choose_mcp_workspace)
        folder.append(self.mcp_browse)
        workspace.append(folder)
        self.mcp_status = self._label('')
        self.mcp_status.add_css_class('error')
        self.mcp_status.connect('notify::label', lambda label, *_: label.set_visible(bool(label.get_text())))
        workspace.append(self.mcp_status)
        page.append(workspace)

        directory = Gtk.Box(spacing=12)
        directory.append(Gtk.Label(label='MCP clients', xalign=0, hexpand=True, css_classes=['mcp-section']))
        self.mcp_search = Gtk.SearchEntry(placeholder_text='Search clients', width_chars=16)
        self.mcp_search.connect('search-changed', self._filter_mcp_clients)
        directory.append(self.mcp_search)
        page.append(directory)

        self.mcp_copy = {}
        self.mcp_add = {}
        self.mcp_rows = {}
        self.mcp_feedback = {}
        clients = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['mcp-list'])
        for client, (name, filename, guide) in mcp_clients.CLIENTS.items():
            row = Gtk.Box(spacing=12, css_classes=['mcp-row'])
            title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True,
                            valign=Gtk.Align.CENTER)
            name_label = self._label(name)
            name_label.add_css_class('mcp-client-name')
            name_label._ratiolab_no_translate = True
            title.append(name_label)
            if filename:
                file_label = self._label(filename, muted=True)
                file_label.add_css_class('mcp-filename')
                file_label._ratiolab_no_translate = True
                title.append(file_label)
            feedback = self._label('', muted=True)
            feedback.set_visible(False)
            title.append(feedback)
            self.mcp_feedback[client] = feedback
            row.append(title)
            actions = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
            if guide:
                add = Gtk.Button(label='Add to client', css_classes=['mcp-add'])
                add.connect('clicked', self._add_mcp_config, client)
                self.mcp_add[client] = add
                actions.append(add)
                link = Gtk.LinkButton(uri=guide)
                self._mcp_icon_action(link, workspace_ui.workspace_glyph('setup-guide', link), 'Setup guide')
                link.connect('activate-link', lambda widget: gui_workflow.open_link(self.app, widget.get_uri()))
                actions.append(link)
            button = Gtk.Button()
            self._mcp_icon_action(button, Gtk.Image.new_from_icon_name('edit-copy-symbolic'), 'Copy configuration')
            button.connect('clicked', self._copy_mcp_config, client)
            actions.append(button)
            row.append(actions)
            clients.append(row)
            self.mcp_rows[client] = row
            self.mcp_copy[client] = button
        self.mcp_empty = self._label('No clients found', muted=True)
        self.mcp_empty.add_css_class('mcp-empty')
        self.mcp_empty.set_visible(False)
        clients.append(self.mcp_empty)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                    min_content_height=140, overlay_scrolling=False, vexpand=True,
                                    css_classes=['mcp-client-scroll'])
        scroll.set_child(clients)
        page.append(scroll)
        self._refresh_mcp()

    @staticmethod
    def _mcp_icon_action(button, icon_widget, title):
        button.add_css_class('flat')
        button.add_css_class('mcp-icon-action')
        icon_widget.set_can_target(False)
        button.set_child(icon_widget)
        button.set_tooltip_text(title)
        button.update_property([Gtk.AccessibleProperty.LABEL], [title])
        button.connect('notify::tooltip-text', lambda widget, *_:
                       widget.update_property([Gtk.AccessibleProperty.LABEL], [widget.get_tooltip_text()]))

    def _filter_mcp_clients(self, entry):
        query = entry.get_text().casefold().strip()
        any_visible = False
        for client, (name, filename, _) in mcp_clients.CLIENTS.items():
            visible = query in name.casefold() or query in filename.casefold()
            self.mcp_rows[client].set_visible(visible)
            any_visible |= visible
        self.mcp_empty.set_visible(not any_visible)

    def _mcp_feedback(self, client, message, error=False):
        label = self.mcp_feedback[client]
        if error:
            label.add_css_class('error')
        else:
            label.remove_css_class('error')
        label.set_text(message)
        label.set_visible(bool(message))
        self.app.language.refresh()

    def _refresh_mcp(self):
        workspace = self.app.workspace_preferences['mcp_workspace']
        self.mcp_path.set_text(workspace)
        self.mcp_path.set_tooltip_text(workspace or None)
        self.mcp_browse.set_label('Change folder…' if workspace else 'Choose folder…')
        if workspace:
            self.mcp_browse.remove_css_class('primary')
        else:
            self.mcp_browse.add_css_class('primary')
        config = app_paths.mcp_launch(workspace)
        for button in self.mcp_copy.values():
            button.set_sensitive(bool(workspace and config))
        for button in self.mcp_add.values():
            button.set_sensitive(bool(workspace and config and not self.mcp_registering))
            button.set_label('Add to client')
        self.mcp_status.set_text('' if config else 'RatioLab-MCP is unavailable.')
        self.mcp_status.set_visible(not config)

    def _choose_mcp_workspace(self, *_):
        self._choose_mcp_folder('MCP workspace', self.mcp_path.get_text(), self._mcp_workspace_selected)

    def _choose_mcp_folder(self, title, current, accept_folder):
        if self.mcp_chooser is not None:
            self._close_mcp_chooser()
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=['settings-page'])
        page.append(Gtk.Label(label=title, xalign=0, css_classes=['settings-page-title']))
        chooser = Gtk.FileChooserWidget(vexpand=True, hexpand=True,
                                        action=Gtk.FileChooserAction.SELECT_FOLDER)
        if current and Path(current).is_dir():
            chooser.set_current_folder(Gio.File.new_for_path(current))
        page.append(chooser)
        actions = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', self._close_mcp_chooser)
        actions.append(cancel)
        accept = Gtk.Button(label='Use this folder', css_classes=['primary'])
        accept.connect('clicked', self._mcp_folder_selected, accept_folder)
        actions.append(accept)
        page.append(actions)
        self.mcp_chooser, self.mcp_folder_page = chooser, page
        self.stack.add_named(page, 'mcp-folder')
        self.stack.set_visible_child(page)
        self.app.language.refresh()

    def _close_mcp_chooser(self, *_):
        page = self.mcp_folder_page
        self.mcp_chooser = self.mcp_folder_page = None
        self.stack.set_visible_child_name('mcp')
        self.stack.remove(page)
        self.mcp_browse.grab_focus()

    def _mcp_folder_selected(self, _, accept_folder):
        selected = self.mcp_chooser.get_file()
        path = selected.get_path() if selected else None
        self._close_mcp_chooser()
        if not path or not Path(path).is_absolute() or not Path(path).is_dir():
            self.mcp_status.set_text('No local destination folder selected.')
            return
        accept_folder(Path(path))

    def _mcp_workspace_selected(self, path):
        workspace_ui.save_ui_preference(self.app, mcp_workspace=str(path))
        for label in self.mcp_feedback.values():
            label.set_visible(False)
        self._refresh_mcp()

    def _add_mcp_config(self, _, client):
        workspace = self.mcp_path.get_text()
        if self.mcp_registering or not workspace:
            return
        config = app_paths.mcp_launch(workspace)
        if config is None:
            self._refresh_mcp()
            return
        if client == 'continue':
            self._choose_mcp_folder('Choose your Continue project folder', '',
                                    lambda project: self._register_mcp(client, config, project))
        else:
            self._register_mcp(client, config)

    def _register_mcp(self, client, config, project=None):
        dialog = self.dialog
        self.mcp_registering = True
        self._refresh_mcp()
        self.mcp_add[client].set_label('Adding…')
        self.mcp_feedback[client].set_visible(False)

        def finish(error):
            self.mcp_registering = False
            if self.dialog is not None:
                self._refresh_mcp()
            if self.dialog is dialog:
                if error:
                    self._mcp_feedback(client, error, error=True)
                else:
                    self.mcp_add[client].set_label('Added')
                    self._mcp_feedback(client, 'RatioLab added. Reload the client if needed.')
            return GLib.SOURCE_REMOVE

        def work():
            error = None
            try:
                mcp_registration.register(client, config, project=project)
            except mcp_registration.RegistrationError as problem:
                error = str(problem)
            except (OSError, ValueError, RecursionError, KeyError, subprocess.SubprocessError, GLib.Error):
                error = 'Could not update the client configuration.'
            GLib.idle_add(finish, error)

        threading.Thread(target=work, name='RatioLab MCP registration', daemon=True).start()

    def _copy_mcp_config(self, _, client):
        workspace = self.mcp_path.get_text()
        if not workspace:
            return
        config = app_paths.mcp_launch(workspace)
        if config is None:
            self._refresh_mcp()
            return
        self.dialog.get_clipboard().set(mcp_clients.configuration(client, config))
        self._mcp_feedback(client, 'Text copied')

    def _page_changed(self, *_):
        page = self.stack.get_visible_child_name()
        mcp_visible = page in ('mcp', 'mcp-folder')
        self.preference_hint.set_visible(not mcp_visible)
        if mcp_visible:
            self.dialog.add_css_class('mcp-settings-active')
        else:
            self.dialog.remove_css_class('mcp-settings-active')
        selected = page == 'precision'
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
        if key == Gdk.KEY_Escape and self.stack.get_visible_child_name() == 'mcp-folder':
            self._close_mcp_chooser()
            return True
        if key == Gdk.KEY_Escape and self.theme_editor.file_dialog is not None:
            self.theme_editor.retire_file_dialog()
            return True
        if key == Gdk.KEY_Escape or stroke(key, state) in self.app.keyboard.config['bindings']['close']:
            self.dialog.response(Gtk.ResponseType.CLOSE)
            return True
        return False

    def _retire(self, *_):
        page = self.mcp_folder_page
        self.mcp_chooser = self.mcp_folder_page = None
        if page is not None:
            self.stack.remove(page)
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
