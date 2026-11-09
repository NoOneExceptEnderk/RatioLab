# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Theme thumbnails, color controls and portable theme files for native Settings."""
import json
from math import cos, sin, pi
from pathlib import Path
from gi.repository import Gtk, Gdk
import theme_preferences as themes
import workspace_ui
from ui_language import translate


class ThemeEditor:
    def __init__(self, panel, page):
        self.panel, self.app = panel, panel.app
        self.updating = False
        self.active = True
        self.file_dialog = None
        self.file_page = None
        self.cards, self.previews, self.entries, self.pickers = {}, {}, {}, {}
        heading = Gtk.Box(spacing=12)
        heading.append(Gtk.Label(label='Theme presets', xalign=0, hexpand=True, css_classes=['step-title']))
        self.customized = panel._label('Custom colors', muted=True)
        heading.append(self.customized)
        page.append(heading)
        gallery = Gtk.Box(spacing=10)
        self.gallery = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                         vscrollbar_policy=Gtk.PolicyType.NEVER,
                                         min_content_height=135, hexpand=True)
        self.gallery.set_child(gallery)
        page.append(self.gallery)
        group = None
        for preset, name in [*themes.PRESETS.items(), ('custom', 'Imported theme')]:
            button = Gtk.ToggleButton(css_classes=['theme-card'])
            button.set_size_request(150, -1)
            if group is not None:button.set_group(group)
            else:group = button
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            sample = Gtk.DrawingArea(content_width=142, content_height=78)
            sample.set_draw_func(lambda area, cr, w, h, preset=preset: self.draw_sample(preset, cr, w, h))
            content.append(sample)
            title = Gtk.Label(label=name, wrap=True, max_width_chars=18)
            title._ratiolab_no_translate = True
            content.append(title)
            button.set_child(content)
            button.connect('toggled', lambda widget, preset=preset:
                           self.choose_preset(preset) if widget.get_active() and not self.updating else None)
            gallery.append(button)
            self.cards[preset], self.previews[preset] = button, sample
        actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                              min_children_per_line=1, max_children_per_line=3,
                              row_spacing=6, column_spacing=6)
        for title, callback in [('Import theme…', lambda *_: self.choose_file(False)),
                                 ('Export theme…', lambda *_: self.choose_file(True)),
                                 ('Restore preset colors', self.reset_colors)]:
            button = Gtk.Button(label=title)
            button.get_child().set_wrap(True)
            button.get_child().set_max_width_chars(22)
            button.connect('clicked', callback)
            actions.append(button)
        page.append(actions)
        self.error = panel._label('')
        self.error.add_css_class('error')
        self.error.set_visible(False)
        page.append(self.error)
        self.expanders = {}
        for name, title, roles in [('colors', 'Interface colors', themes.INTERFACE_ROLES),
                                    ('viewport', '3D view colors', themes.VIEW_ROLES)]:
            expander = Gtk.Expander(label=title, css_classes=['theme-colors'])
            rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            expander.set_child(rows)
            page.append(expander)
            self.expanders[name] = expander
            for key, label in roles.items():
                controls = Gtk.Box(spacing=7)
                dialog = Gtk.ColorDialog(title=label, modal=True, with_alpha=False)
                picker = Gtk.ColorDialogButton.new(dialog)
                picker.set_size_request(38, 30)
                picker.connect('notify::rgba', self.picked, name, key)
                controls.append(picker)
                entry = Gtk.Entry(width_chars=8, max_width_chars=8, max_length=7,
                                  css_classes=['theme-color-entry'])
                entry.connect('activate', lambda widget, name=name, key=key: self.entered(widget, name, key))
                focus = Gtk.EventControllerFocus()
                focus.connect('leave', lambda *_, entry=entry, name=name, key=key: self.entered(entry, name, key))
                entry.add_controller(focus)
                controls.append(entry)
                reset = Gtk.Button(label='↺', tooltip_text='Reset color', css_classes=['flat'])
                reset.connect('clicked', lambda *_, name=name, key=key: self.set_color(name, key, None))
                controls.append(reset)
                panel._row(rows, label, controls)
                caption = controls.get_parent().get_first_child()
                def accessible(widget, *_, picker=picker, entry=entry):
                    picker.get_dialog().set_title(widget.get_text())
                    for control in (picker, entry):
                        control.update_property([Gtk.AccessibleProperty.LABEL], [widget.get_text()])
                panel._watch(caption, 'notify::label', accessible)
                accessible(caption)
                self.entries[name, key], self.pickers[name, key] = entry, picker
        self.contrast = panel._label('', muted=True)
        page.append(self.contrast)
        self.refresh()

    @property
    def mode(self):
        return self.app.workspace_theme

    @property
    def config(self):
        return themes.normalize(self.app.workspace_preferences.get('theme_customizations'))

    def refresh(self, *_):
        if not self.active:return
        self.updating = True
        try:
            config, mode = self.config, self.mode
            preset = config['active'][mode]
            self.cards['custom'].set_visible(mode in config['imported'])
            imported = config['imported'].get(mode, {})
            self.cards['custom'].get_child().get_last_child().set_text(imported.get('name', 'Imported theme'))
            self.cards[preset].set_active(True)
            changed = config['overrides'].get(mode + ':' + preset, {})
            self.customized.set_visible(any(changed.get(key) for key in ('colors', 'viewport')))
            colors = themes.palette(mode, config)
            view = themes.viewport(mode, config)
            for (group, key), entry in self.entries.items():
                value = colors[key] if group == 'colors' else themes.hex_color(view[key])
                if not entry.has_focus():
                    entry.set_text(value.upper())
                    entry.remove_css_class('error')
                rgba = Gdk.RGBA()
                rgba.parse(value)
                self.pickers[group, key].set_rgba(rgba)
            ratio = themes.contrast(colors['text'], colors['window'])
            self.contrast.set_text(f'Text contrast: {ratio:.1f}:1')
            for area in self.previews.values():area.queue_draw()
        finally:self.updating = False

    def commit(self, config, mode=None):
        if not self.active:return
        self.app.workspace_preferences['theme_customizations'] = config
        target = themes.MODES.index(mode or self.mode)
        if self.app.theme_selector.get_selected() != target:
            self.app.theme_selector.set_selected(target)
        else:
            workspace_ui.apply_theme(self.app)
            workspace_ui.save_ui_preference(self.app, theme_customizations=config)
        self.error.set_visible(False)
        self.refresh()

    def choose_preset(self, preset):
        config = self.config
        config['active'][self.mode] = preset
        self.commit(config)

    def set_color(self, group, key, value):
        if self.updating or not self.active:return
        self.commit(themes.change_color(self.config, self.mode, group, key, value))

    def entered(self, entry, group, key):
        if self.updating or not self.active:return
        try:value = themes.color(entry.get_text())
        except ValueError as error:
            entry.add_css_class('error')
            self.show_error(str(error))
            return
        current = themes.palette(self.mode, self.config)[key] if group == 'colors' else themes.hex_color(themes.viewport(self.mode, self.config)[key])
        if value != current:self.set_color(group, key, value)
        entry.set_text(value.upper())
        entry.remove_css_class('error')

    def picked(self, picker, _, group, key):
        if not self.updating and self.active:
            rgba = picker.get_rgba()
            self.set_color(group, key, themes.hex_color((rgba.red, rgba.green, rgba.blue)))

    def reset_colors(self, *_):
        config = self.config
        config['overrides'].pop(self.mode + ':' + config['active'][self.mode], None)
        self.commit(config)

    def show_error(self, text):
        self.error.set_text(text)
        self.error.set_visible(True)
        self.app.language.refresh()

    def load_file(self, path):
        with Path(path).open('rb') as stream:payload = stream.read(themes.MAX_THEME_BYTES + 1)
        config, mode = themes.import_theme(payload, self.config)
        self.commit(config, mode)

    def save_file(self, path):
        Path(path).write_text(json.dumps(themes.export_theme(self.mode, self.config), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def choose_file(self, save):
        action = Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN
        if self.file_dialog is not None:
            if self.file_dialog.get_action() == action:
                self.panel.stack.set_visible_child_name('theme-file')
                return
            self.retire_file_dialog()
        language = self.app.language.language
        # Keep file selection in Settings. Creating and immediately retiring
        # nested chooser windows raced with Wayland focus callbacks on GTK 4.22.
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       css_classes=['settings-page'])
        page.append(Gtk.Label(label=translate('Export theme' if save else 'Import theme', language),
                              xalign=0, css_classes=['settings-page-title']))
        chooser = Gtk.FileChooserWidget(vexpand=True, hexpand=True, action=action,
                                        css_classes=['theme-file-chooser'])
        filter = Gtk.FileFilter(name=translate('RatioLab theme files', language))
        filter.add_pattern('*.json')
        chooser.add_filter(filter)
        if save:chooser.set_current_name('my-ratiolab-theme.json')
        page.append(chooser)
        actions = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=translate('Cancel', language))
        cancel.connect('clicked', lambda *_: self.retire_file_dialog())
        actions.append(cancel)
        accept = Gtk.Button(label=translate('Save' if save else 'Open', language), css_classes=['primary'])
        accept.connect('clicked', lambda *_: self.accept_file(save))
        actions.append(accept)
        page.append(actions)
        self.file_dialog, self.file_page = chooser, page
        self.panel.stack.add_named(page, 'theme-file')
        self.panel.stack.set_visible_child(page)

    def accept_file(self, save):
        try:
            selected = self.file_dialog.get_file()
            if selected is None:return
            path = selected.get_path()
            if not path:raise ValueError('Choose a local theme file.')
            if save:self.save_file(path)
            else:self.load_file(path)
        except ValueError as error:self.show_error(str(error))
        except OSError:self.show_error('Could not save theme file.' if save else 'Could not open theme file.')
        self.retire_file_dialog()

    def retire_file_dialog(self):
        page = self.file_page
        self.file_dialog = self.file_page = None
        if page is not None:
            if self.panel.stack.get_visible_child() is page:
                self.panel.stack.set_visible_child_name('appearance')
            self.panel.stack.remove(page)

    def close(self):
        if not self.active:return
        self.active = False
        # ColorDialogButton owns its asynchronous chooser, which otherwise
        # survives the Settings window. Cancel it before retiring the parent.
        for window in Gtk.Window.list_toplevels():
            if window.get_transient_for() is self.panel.dialog:
                window.close()
        self.retire_file_dialog()

    def draw_sample(self, preset, cr, width, height):
        colors = themes.palette(self.mode, self.config, preset)
        view = themes.viewport(self.mode, self.config, preset)
        def fill(key, x, y, w, h):
            cr.set_source_rgb(*themes.rgb(colors[key]));cr.rectangle(x, y, w, h);cr.fill()
        fill('window', 0, 0, width, height)
        fill('surface', 0, 0, width, 12)
        fill('surface', 0, 14, width * .23, height - 14)
        for y, size in [(21, .16), (31, .13), (41, .15)]:fill('muted', 5, y, width * size, 2)
        fill('accent', 5, 51, width * .14, 5)
        cr.set_source_rgb(*view['background']);cr.rectangle(width * .25, 14, width * .75, height - 14);cr.fill()
        cr.set_source_rgb(*view['grid']);cr.set_line_width(.6)
        for y in range(26, height, 12):cr.move_to(width * .26, y);cr.line_to(width, y)
        for x in range(int(width * .26), width, 14):cr.move_to(x, 14);cr.line_to(x, height)
        cr.stroke()
        for cx, cy, radius, shade in [(width * .58, height * .53, 18, 'accent'), (width * .81, height * .71, 12, 'muted')]:
            for i in range(48):
                angle = i * pi / 24
                r = radius * (.82 if i % 4 in (0, 3) else 1)
                point = (cx + r * cos(angle), cy + r * sin(angle))
                if i == 0:cr.move_to(*point)
                else:cr.line_to(*point)
            cr.close_path();cr.set_source_rgb(*themes.rgb(colors[shade]));cr.fill()
            cr.arc(cx, cy, radius * .32, 0, 2 * pi);cr.set_source_rgb(*view['background']);cr.fill()
