# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Localize rendered GTK labels without replacing canonical dropdown models."""
from gi.repository import Gtk, GLib, Pango
import app_paths
from ui_language import catalog, translate


class Controller:
    def __init__(self, app):
        self.app = app
        self.language = app.workspace_preferences['language']
        self.bindings = {}
        self.handlers = {}
        self.writing = False
        self.choices = {}
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        for setter in (body.set_margin_start, body.set_margin_end, body.set_margin_top, body.set_margin_bottom):
            setter(8)
        group = None
        for code, name in catalog()['languages'].items():
            choice = Gtk.CheckButton(label=name)
            choice._ratiolab_no_translate = True
            if group is not None:
                choice.set_group(group)
            else:
                group = choice
            choice.set_active(code == self.language)
            choice.connect('toggled', lambda widget, code=code: self.change(code) if widget.get_active() else None)
            self.choices[code] = choice
            body.append(choice)
        self.error = Gtk.Label(label='Changed for this session. Could not save preference.',
                               visible=False, wrap=True, max_width_chars=30, css_classes=['error'])
        body.append(self.error)
        app.language_popover.set_child(body)
        self.refresh()
        # Newly generated parameter rows and dropdown popup labels join the same
        # presentation bindings. No geometry refresh or selection signals involved.
        self.timer = GLib.timeout_add(150, self.refresh)
        app.win.connect('unrealize', self.stop)

    def stop(self, *_):
        if self.timer:
            if GLib.MainContext.default().find_source_by_id(self.timer):
                GLib.source_remove(self.timer)
            self.timer = None
        for widget, handlers in self.handlers.items():
            for handler in handlers:
                widget.disconnect(handler)
        self.handlers.clear()
        self.bindings.clear()

    def change(self, code):
        if code not in catalog()['languages']:
            raise ValueError('Unsupported interface language')
        self.language = code
        self.app.workspace_preferences['language'] = code
        for key, choice in self.choices.items():
            if choice.get_active() != (key == code):
                choice.set_active(key == code)
        self.refresh()
        try:
            app_paths.save_preferences(legacy_root=self.app.BASE, language=code)
            self.error.set_visible(False)
        except OSError:
            self.error.set_visible(True)

    def _changed(self, widget, spec):
        if self.writing or widget not in self.bindings:
            return
        sources = self.bindings.get(widget, {})
        value = widget.get_property(spec.name)
        if spec.name not in sources or value != sources[spec.name][1]:
            sources[spec.name] = (value, value)
        self._render(widget, spec.name)

    def _render(self, widget, prop):
        source, previous = self.bindings[widget][prop]
        value = translate(source, self.language)
        self.writing = True
        try:
            if widget.get_property(prop) != value:
                widget.set_property(prop, value)
            self.bindings[widget][prop] = (source, value)
        finally:
            self.writing = False

    def refresh(self):
        app = self.app
        if self.language == 'en':
            app.win.remove_css_class('localized-ui')
        else:
            app.win.add_css_class('localized-ui')
        excluded = {getattr(app, name, None) for name in ('project_title', 'document_label', 'output_label')}
        seen = set()
        def walk(widget, skip=False):
            try:
                visit(widget, skip)
            except RuntimeError as error:
                # GTK can retire a transient native popup during label/layout
                # notifications. Discard only that disposed widget, not the
                # recurring discovery source or unrelated exceptions.
                if 'not initialized' not in str(error):
                    raise

        def visit(widget, skip):
            seen.add(widget)
            skip = skip or widget in excluded or getattr(widget, '_ratiolab_no_translate', False)
            # Editable text, user filenames and report contents are never messages.
            skip = skip or isinstance(widget, (Gtk.Entry, Gtk.TextView, Gtk.FileChooserWidget))
            if not skip:
                properties = []
                if isinstance(widget, Gtk.Window) and widget is not app.win:
                    properties.append('title')
                if isinstance(widget, Gtk.Label):
                    properties.append('label')
                    if widget.has_css_class('field-label'):
                        widget.set_wrap(True)
                        widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                        widget.set_width_chars(1)
                if widget.get_tooltip_text():
                    properties.append('tooltip-text')
                sources = self.bindings.setdefault(widget, {}) if properties else {}
                for prop in properties:
                    if prop not in sources:
                        value = widget.get_property(prop)
                        sources[prop] = (value, value)
                        self.handlers.setdefault(widget, []).append(widget.connect('notify::'+prop, self._changed))
                    self._render(widget, prop)
            child = widget.get_first_child()
            while child:
                # Read the sibling before updating labels: a notification may
                # unparent/destroy the current popup synchronously.
                following = child.get_next_sibling()
                walk(child, skip)
                child = following
        for window in app.get_windows():
            walk(window)
        for widget in set(self.bindings) - seen:
            for handler in self.handlers.pop(widget, []):
                try:
                    widget.disconnect(handler)
                except RuntimeError as error:
                    if 'not initialized' not in str(error):
                        raise
            del self.bindings[widget]
        return True
