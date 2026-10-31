# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
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
        self.expanded=False;self.saved_layout=None;self.restore_clock=None;self.restore_frame=None
        self.restoring=False
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
        self.close_button=close
        # Use the existing toolbar so a text action does not reduce the compact
        # dock's useful height or widen its navigation row at enlarged fonts.
        self.expand_button=Gtk.Button(label='Expand tool',css_classes=['flat'],visible=False)
        self.expand_button.set_tooltip_text('Give this tool the workspace area; restore to return to the model.')
        self.expand_button.connect('clicked',lambda _:self.restore_workspace() if self.expanded else self.expand())
        self.stack = Gtk.Stack(vexpand=True)
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        self.box.append(self.stack)
        self.menu = Gtk.MenuButton(label='Tools')
        toolbar.append(self.menu)
        toolbar.append(self.expand_button)
        self.popup = Gtk.Popover()
        self.menu.set_popover(self.popup)
        self.commands = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.popup.set_child(self.commands)
        self.active = None
        shortcuts = Gtk.ShortcutController()
        self.shortcuts=shortcuts
        shortcuts.set_scope(Gtk.ShortcutScope.LOCAL)
        for keyval, modifiers, callback in [
            (Gdk.KEY_Escape, Gdk.ModifierType(0), self.close_current),
            (Gdk.KEY_1, Gdk.ModifierType.ALT_MASK, lambda: self.controllers['components'].open()),
            (Gdk.KEY_2, Gdk.ModifierType.ALT_MASK, lambda: self.controllers['search'].open()),
            (Gdk.KEY_3, Gdk.ModifierType.ALT_MASK, lambda: self.controllers['interference'].open())]:
            shortcuts.add_shortcut(Gtk.Shortcut.new(Gtk.KeyvalTrigger.new(keyval, modifiers),
                Gtk.CallbackAction.new(lambda *_, fn=callback: (fn(), True)[1])))
        app.win.add_controller(shortcuts)
        app.win.connect('unrealize',lambda *_:self.finish_restore_frame())

    def normal_width(self):
        # Restore and Close can happen before GTK has allocated the restored
        # children. Never remember the full expanded allocation as dock width.
        if self.restoring:return self.last_width
        return max(360,self.box.get_width() or getattr(self,'last_width',390))

    def expand(self):
        if self.expanded or not self.box.get_visible() or self.active is None:return
        width=self.normal_width();self.finish_restore_frame()
        parents=(self.app.parameter_panel,self.app.preview_overlay,self.app.workspace_extras)
        self.saved_layout=dict(visible=[(widget,widget.get_visible()) for widget in parents],
            positions=[(self.app.workspace_paned,self.app.workspace_paned.get_position()),
                       (self.paned,self.paned.get_position())])
        self.last_width=width;self.expanded=True
        for widget,_ in self.saved_layout['visible']:widget.set_visible(False)
        self.expand_button.set_label('Restore workspace')

    def restore_workspace(self):
        if not self.expanded:return
        saved=self.saved_layout;self.saved_layout=None;self.expanded=False;self.restoring=True
        self.expand_button.set_label('Expand tool')
        for widget,visible in saved['visible']:widget.set_visible(visible)
        for paned,position in saved['positions']:paned.set_position(position)
        # after-paint follows GTK allocation, unlike an idle callback that may
        # run while the expanded sizes are still current.
        self.restore_clock=self.app.win.get_frame_clock()
        if self.restore_clock is not None:
            self.restore_frame=self.restore_clock.connect('after-paint',self.finish_restore_frame)
            self.app.win.queue_draw()

    def finish_restore_frame(self,*_):
        if self.restore_frame is not None:
            self.restore_clock.disconnect(self.restore_frame)
        self.restore_frame=None;self.restore_clock=None;self.restoring=False

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
        self.expand_button.set_visible(True)
        self.stack.set_visible_child_name(key)
        # set_active only emits toggled, so no recursive open/present.
        self.tabs[key].set_active(True)
        width = self.paned.get_width()
        if not was_visible:
            self.paned.set_position(max(240, width - getattr(self,'last_width',390)))

    def remove(self, panel):
        if self.panels.get(panel.key) is not panel:
            return
        if self.active==panel.key:
            if self.expanded:self.restore_workspace()
            if self.box.get_visible():self.last_width=self.normal_width()
        self.stack.remove(panel)
        del self.panels[panel.key]
        if self.active == panel.key:
            self.active = None
            self.box.set_visible(False)
            self.expand_button.set_visible(False)
            self.tabs[panel.key].set_active(False)
            self.menu.grab_focus()

    def close_current(self):
        panel = self.panels.get(self.active)
        if panel:
            self.restore_workspace()
            panel.close()
