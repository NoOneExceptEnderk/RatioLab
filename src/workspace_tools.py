# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Workspace tool dock: shared presentation, independent controller lifetimes."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject, Gdk, Pango


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


def status_actions(status, controls):
    """Keep actions and a concise actual status visible; full text stays in body."""
    row=Gtk.Box(spacing=6)
    controls.set_min_children_per_line(3)
    parent=controls.get_parent()
    if parent:parent.remove(controls)
    row.append(controls)
    badge=Gtk.Label(xalign=0,hexpand=True,ellipsize=Pango.EllipsizeMode.END,
                    width_chars=1,max_width_chars=14,css_classes=['muted'])
    def update(*_):
        badge.set_text(status.get_text())
        badge.set_tooltip_text(status.get_text())
    status.connect('notify::label',update)
    update();row.append(badge)
    return row,badge


class Panel(Gtk.Box):
    __gsignals__ = {'close-request': (GObject.SignalFlags.RUN_LAST, bool, ())}

    def __init__(self, dock, key):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.dock, self.key = dock, key
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(self.scroll)

    def set_child(self, child):
        self.body=child
        self.scroll.set_child(child)

    def pin(self, *widgets):
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=['sidebar-actions'])
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
        self.box.set_size_request(340, -1)
        self.box.set_visible(False)
        self.box.set_halign(Gtk.Align.END)
        self.box.set_valign(Gtk.Align.FILL)
        for side in ('start', 'end', 'top', 'bottom'):
            getattr(self.box, 'set_margin_'+side)(12)
        self.box.set_margin_top(60)
        app.preview_overlay.add_overlay(self.box)
        app.preview_overlay.set_measure_overlay(self.box, False)
        self.expanded=False;self.saved_layout=None;self.restore_clock=None;self.restore_frame=None
        self.restoring=False
        head = Gtk.Box(spacing=3, css_classes=['tool-nav'])
        self.box.append(head)
        self.back_button = Gtk.Button(label='All tools', css_classes=['flat'], visible=False)
        self.back_button.set_tooltip_text('Return to all tools without closing this form')
        self.back_button.connect('clicked', lambda _: self.show_chooser())
        self.title = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, css_classes=['step-title'])
        heading=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=1,hexpand=True)
        self.category=Gtk.Label(label='Tools',xalign=0,css_classes=['overlay-category'])
        heading.append(self.category)
        heading.append(self.title)
        head.append(heading)
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
        self.back_button.set_halign(Gtk.Align.START)
        self.back_button.set_margin_start(14)
        self.box.append(self.stack)
        self.menu = Gtk.ToggleButton(label='Tools')
        self.menu.set_tooltip_text('Open tools and reports in the preview')
        toolbar.append(self.menu)
        toolbar.append(self.expand_button)
        self.commands = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, css_classes=['tool-chooser'],
                                margin_start=14, margin_end=14, margin_top=14, margin_bottom=14)
        self.command_buttons=[]
        self.chooser = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.chooser.set_child(self.commands)
        self.stack.add_named(self.chooser, 'chooser')
        self.active = None
        self._syncing_menu = False
        self.menu.connect('toggled', self._menu_toggled)
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
        return max(340,self.box.get_width() or getattr(self,'last_width',390))

    def expand(self):
        if self.expanded or not self.box.get_visible() or self.active is None:return
        width=self.normal_width();self.finish_restore_frame()
        parents=(self.app.parameter_panel,self.app.canvas,self.app.workspace_extras)
        self.saved_layout=dict(visible=[(widget,widget.get_visible()) for widget in parents],
            positions=[(self.app.workspace_paned,self.app.workspace_paned.get_position()),
                       (self.paned,self.paned.get_position())])
        self.last_width=width;self.expanded=True
        for widget,_ in self.saved_layout['visible']:widget.set_visible(False)
        self.box.set_halign(Gtk.Align.FILL)
        self.box.set_size_request(-1, -1)
        self.expand_button.set_label('Restore workspace')

    def restore_workspace(self):
        if not self.expanded:return
        saved=self.saved_layout;self.saved_layout=None;self.expanded=False;self.restoring=True
        self.expand_button.set_label('Expand tool')
        self.box.set_halign(Gtk.Align.END)
        self.box.set_size_request(self.last_width, -1)
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

    def _command(self,button,icon):
        # Overlay the symbol without replacing GtkButton's label child/property.
        # Controllers and accessible clients retain the canonical action label.
        row=Gtk.Overlay()
        row.set_child(button)
        label=button.get_child()
        if isinstance(label,Gtk.Label):
            label.set_xalign(0);label.set_hexpand(True);label.set_margin_start(22)
        from workspace_ui import workspace_glyph
        symbol=workspace_glyph(icon,button)
        button.workspace_icon=symbol
        symbol.set_halign(Gtk.Align.START);symbol.set_valign(Gtk.Align.CENTER)
        symbol.set_margin_start(10);symbol.set_can_target(False)
        row.add_overlay(symbol)
        self.commands.append(row)
        self.command_buttons.append(button)

    def add_action(self, button):
        self._command(button,{'Bill of materials':'list','Calculation report':'report','Model notes':'notes'}[button.get_label()])
        button.connect('clicked', lambda _: self.hide())

    def _set_menu_active(self, active):
        self._syncing_menu = True
        try:self.menu.set_active(active)
        finally:self._syncing_menu = False

    def _menu_toggled(self, button):
        if self._syncing_menu:return
        if button.get_active():self.show_chooser()
        else:self.hide()

    def show_chooser(self):
        self.restore_workspace()
        self.app.view_menu.set_active(False)
        self.active = None
        self.stack.set_visible_child_name('chooser')
        self.title.set_text('Tools')
        self.back_button.set_visible(False)
        self.expand_button.set_visible(False)
        self.box.set_visible(True)
        self._set_menu_active(True)

    def hide(self):
        self.restore_workspace()
        self.box.set_visible(False)
        self.expand_button.set_visible(False)
        self._set_menu_active(False)

    def register(self, key, controller):
        self.controllers[key] = controller
        icon={'components':'list','search':'search','interference':'warning',
              'gear_measurement':'ruler','backlash':'backlash'}[key]
        self._command(controller.button,icon)
        if not controller.button.get_tooltip_text():
            controller.button.set_tooltip_text(controller.summary.get_text())

    def panel(self, key):
        panel = Panel(self, key)
        self.panels[key] = panel
        self.stack.add_named(panel, key)
        return panel

    def show(self, key):
        self.app.view_menu.set_active(False)
        self._set_menu_active(True)
        self.back_button.set_visible(True)
        body=self.panels[key].body
        parent=self.back_button.get_parent()
        if parent is not body:
            if parent:parent.remove(self.back_button)
            body.prepend(self.back_button)
        self.active = key
        self.box.set_visible(True)
        self.expand_button.set_visible(True)
        self.stack.set_visible_child_name(key)
        self.title.set_text(self.controllers[key].button.get_label().rstrip('…'))

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
            self.hide()
            self.back_button.set_visible(False)
            self.menu.grab_focus()

    def close_current(self):
        if self.app.view_panel.get_visible():
            self.app.view_menu.set_active(False)
            return
        if not self.box.get_visible():return
        if self.active is None:
            self.hide()
            self.menu.grab_focus()
            return
        panel = self.panels.get(self.active)
        if panel:
            self.restore_workspace()
            panel.close()
