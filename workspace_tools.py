"""Workspace tool dock: shared presentation, independent controller lifetimes."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject, Gdk


def details(parent, title, child):
    expander = Gtk.Expander(label=title)
    if isinstance(child, str):
        child = Gtk.Label(label=child, xalign=0, wrap=True, selectable=True,
                          css_classes=['muted'], max_width_chars=34)
    expander.set_child(child)
    parent.append(expander)
    return expander


def actions(parent):
    flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=5,
                       row_spacing=5, homogeneous=False, max_children_per_line=3)
    parent.append(flow)
    # Controllers use append, just as they do for a Box.
    return flow


class Panel(Gtk.Box):
    __gsignals__ = {'close-request': (GObject.SignalFlags.RUN_LAST, bool, ())}

    def __init__(self, dock, key):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.dock, self.key = dock, key
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(self.scroll)

    def set_child(self, child):
        self.scroll.set_child(child)

    def pin(self, *widgets):
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=['sidebar-actions'])
        for widget in widgets:
            parent = widget.get_parent()
            if parent:
                parent.remove(widget)
            bar.append(widget)
        self.append(bar)

    def present(self):
        self.dock.show(self.key)

    def close(self):
        if not self.emit('close-request'):
            self.destroy()

    def destroy(self):
        self.dock.remove(self)


class Dock:
    def __init__(self, app, paned, toolbar):
        self.app, self.paned = app, paned
        self.controllers, self.panels, self.tabs = {}, {}, {}
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['tool-dock'])
        self.box.set_size_request(360, -1)
        self.box.set_visible(False)
        paned.set_end_child(self.box)
        head = Gtk.Box(spacing=3, css_classes=['tool-nav'])
        self.box.append(head)
        for key, title in [('components', 'Components'), ('search', 'Search'), ('interference', 'Check')]:
            button = Gtk.ToggleButton(label=title)
            if self.tabs:
                button.set_group(next(iter(self.tabs.values())))
            button.connect('clicked', lambda b, k=key: self.controllers[k].open() if b.get_active() else None)
            head.append(button)
            self.tabs[key] = button
        close = Gtk.Button(icon_name='window-close-symbolic', css_classes=['flat'])
        close.set_tooltip_text('Close this tool · Escape')
        close.connect('clicked', lambda _: self.close_current())
        head.append(close)
        self.stack = Gtk.Stack(vexpand=True)
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        self.box.append(self.stack)
        self.menu = Gtk.MenuButton(label='Tools')
        toolbar.append(self.menu)
        self.popup = Gtk.Popover()
        self.menu.set_popover(self.popup)
        self.commands = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.popup.set_child(self.commands)
        self.active = None
        shortcuts = Gtk.ShortcutController()
        shortcuts.set_scope(Gtk.ShortcutScope.LOCAL)
        for keyval, modifiers, callback in [
            (Gdk.KEY_Escape, Gdk.ModifierType(0), self.close_current),
            (Gdk.KEY_1, Gdk.ModifierType.ALT_MASK, lambda: self.controllers['components'].open()),
            (Gdk.KEY_2, Gdk.ModifierType.ALT_MASK, lambda: self.controllers['search'].open()),
            (Gdk.KEY_3, Gdk.ModifierType.ALT_MASK, lambda: self.controllers['interference'].open())]:
            shortcuts.add_shortcut(Gtk.Shortcut.new(Gtk.KeyvalTrigger.new(keyval, modifiers),
                Gtk.CallbackAction.new(lambda *_, fn=callback: (fn(), True)[1])))
        app.win.add_controller(shortcuts)

    def register(self, key, controller):
        self.controllers[key] = controller
        self.commands.append(controller.button)
        controller.button.connect('clicked', lambda _: self.popup.popdown())
        if not controller.button.get_tooltip_text():
            controller.button.set_tooltip_text(controller.summary.get_text())

    def panel(self, key):
        panel = Panel(self, key)
        self.panels[key] = panel
        self.stack.add_named(panel, key)
        return panel

    def show(self, key):
        was_visible = self.box.get_visible()
        self.active = key
        self.box.set_visible(True)
        self.stack.set_visible_child_name(key)
        # set_active only emits toggled, so no recursive open/present.
        self.tabs[key].set_active(True)
        width = self.paned.get_width()
        if not was_visible:
            self.paned.set_position(max(240, width - getattr(self,'last_width',390)))

    def remove(self, panel):
        if self.panels.get(panel.key) is not panel:
            return
        if self.box.get_visible():self.last_width=max(360,self.box.get_width())
        self.stack.remove(panel)
        del self.panels[panel.key]
        if self.active == panel.key:
            self.active = None
            self.box.set_visible(False)
            self.tabs[panel.key].set_active(False)
            self.menu.grab_focus()

    def close_current(self):
        panel = self.panels.get(self.active)
        if panel:
            panel.close()
