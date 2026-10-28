# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Check computed GTK colors, including internal editable text CSS nodes."""
import time
import unittest
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
from workspace_ui import CSS


def pump():
    end = time.monotonic() + .08
    context = GLib.MainContext.default()
    while time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(.005)


def descendants(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from descendants(child)
        child = child.get_next_sibling()


class WorkspaceThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')

    def setUp(self):
        self.display = Gdk.Display.get_default()
        self.providers = []
        # Model the native light theme's explicit child foreground. A dark
        # window color alone cannot override a value specified on this node.
        native = Gtk.CssProvider()
        native.load_from_data(b'spinbutton text, label { color: #000000; }')
        self.add_provider(native, Gtk.STYLE_PROVIDER_PRIORITY_THEME)
        style = Gtk.CssProvider()
        style.load_from_data(CSS)
        self.add_provider(style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Gtk.Window(css_classes=['reducers'])
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.window.set_child(self.box)

    def add_provider(self, provider, priority):
        Gtk.StyleContext.add_provider_for_display(self.display, provider, priority)
        self.providers.append(provider)

    def tearDown(self):
        self.window.destroy()
        for provider in self.providers:
            Gtk.StyleContext.remove_provider_for_display(self.display, provider)
        pump()

    def color(self, widget):
        color = widget.get_style_context().get_color()
        return color.red, color.green, color.blue

    def assert_color(self, widget, expected):
        for actual, component in zip(self.color(widget), expected):
            self.assertAlmostEqual(actual, component / 255, delta=.01)

    def show(self):
        self.window.present()
        pump()

    def test_editable_spinbutton_node_inherits_readable_foreground(self):
        spin = Gtk.SpinButton.new_with_range(0, 120, .01)
        spin.set_value(30)
        self.box.append(spin)
        self.show()
        text = next(w for w in descendants(spin) if w.get_css_name() == 'text')
        self.assert_color(text, (233, 238, 244))
        spin.set_sensitive(False)
        pump()
        self.assert_color(text, (172, 185, 201))

    def test_primary_button_children_and_semantic_labels_keep_their_colors(self):
        plain = Gtk.Label(label='Regular text')
        primary = Gtk.Button(label='Export', css_classes=['primary'])
        menu = Gtk.MenuButton(label='Export menu', css_classes=['primary'])
        muted = Gtk.Label(label='Secondary', css_classes=['muted'])
        error = Gtk.Label(label='Invalid', css_classes=['error'])
        warning = Gtk.Label(label='Warning', css_classes=['study'])
        for widget in (plain, primary, menu, muted, error, warning):
            self.box.append(widget)
        self.show()
        self.assert_color(plain, (233, 238, 244))
        for button in (primary, menu):
            label = next(w for w in descendants(button) if isinstance(w, Gtk.Label))
            self.assert_color(label, (16, 42, 44))
        self.assert_color(muted, (172, 185, 201))
        self.assert_color(error, (255, 177, 165))
        self.assert_color(warning, (239, 191, 121))

    def test_popover_and_list_rows_inherit_the_workspace_palette(self):
        menu = Gtk.MenuButton(label='Open')
        popup = Gtk.Popover()
        menu.set_popover(popup)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.set_child(content)
        label = Gtk.Label(label='Popover text')
        content.append(label)
        dock = Gtk.Box(css_classes=['tool-dock'])
        rows = Gtk.ListBox()
        row_label = Gtk.Label(label='Selected component')
        rows.append(row_label)
        dock.append(rows)
        self.box.append(menu)
        self.box.append(dock)
        self.show()
        popup.popup()
        rows.select_row(row_label.get_parent())
        pump()
        self.assert_color(label, (233, 238, 244))
        self.assert_color(row_label, (233, 238, 244))


if __name__ == '__main__':
    unittest.main()
