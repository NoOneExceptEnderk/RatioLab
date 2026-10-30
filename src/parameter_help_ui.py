# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nonmodal, illustrated parameter guides for the live GTK controls."""
from dataclasses import replace
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
from parameter_help import lookup, OPTION_LABELS, CHECK_LABELS
from parameter_help_diagrams import draw_diagram, diagram_kind

HOVER_DELAY_MS = 550
LEAVE_DELAY_MS = 280


class Binding:
    def __init__(self, owner, label, control, key, row):
        self.owner, self.label, self.control, self.key, self.row = owner, label, control, key, row
        self.button = Gtk.Button.new_from_icon_name('dialog-information-symbolic')
        self.button.add_css_class('flat')
        self.button.add_css_class('parameter-help-trigger')
        self.button.set_tooltip_text('Explain this parameter · F1')
        self.button.update_property([Gtk.AccessibleProperty.LABEL], ['Explain '+label.get_text()])
        self.button.connect('clicked', lambda _: self.open())
        row.insert_child_after(self.button, label)
        label.add_css_class('parameter-help-label')
        label.set_tooltip_text(None)
        label.set_mnemonic_widget(control)
        row_motion = Gtk.EventControllerMotion()
        def row_enter(*_):
            if owner.active is self and owner.leave_timer:
                GLib.source_remove(owner.leave_timer)
                owner.leave_timer = 0
        row_motion.connect('enter', row_enter)
        row_motion.connect('leave', lambda *_: owner.leave() if owner.active is self else None)
        row.add_controller(row_motion)
        self.motion = Gtk.EventControllerMotion()
        self.motion.connect('enter', lambda *_: owner.enter(self))
        self.motion.connect('leave', lambda *_: owner.leave() if not row_motion.contains_pointer() else None)
        label.add_controller(self.motion)
        self.key_controllers = []
        for widget in (control, self.button):
            keys = Gtk.EventControllerKey()
            keys.connect('key-pressed', self.key_pressed)
            widget.add_controller(keys)
            self.key_controllers.append(keys)
            focus = Gtk.EventControllerFocus()
            def departed(*_):
                def check():
                    if owner.active is not self or not owner.pinned:
                        return GLib.SOURCE_REMOVE
                    root = control.get_root()
                    current = root.get_focus() if root else None
                    allowed = (control, self.button, owner.popover)
                    if not current or not any(w and (current is w or current.is_ancestor(w)) for w in allowed):
                        owner.close()
                    return GLib.SOURCE_REMOVE
                GLib.idle_add(check)
            focus.connect('leave', departed)
            widget.add_controller(focus)
        self.describe()

    def describe(self):
        help = self.owner.help_for(self)
        self.control.update_property([Gtk.AccessibleProperty.DESCRIPTION],
            [help.meaning+' '+help.effect+' Press F1 for illustrated help.'])
        self.button.update_property([Gtk.AccessibleProperty.LABEL], ['Explain '+self.label.get_text()])

    def key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_F1:
            self.open()
            return True
        if keyval == Gdk.KEY_Escape and self.owner.active is self:
            self.owner.close()
            return True
        return False

    def open(self):
        self.owner.open(self, pinned=True)


def effect_sections(effect):
    """Keep the first complete explanation visible and retain the full detail."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', effect)
    return sentences[0], ' '.join(sentences[1:])


class HelpController:
    """One nonmodal illustrated guide per app; inputs remain untouched."""
    def __init__(self, app):
        self.app = app
        self.bindings, self.all_bindings = {}, []
        self.active = self.popover = None
        self.timer = self.leave_timer = 0
        self.pinned = self.over_popup = False
        self.style = Gtk.CssProvider()
        self.style_scale = None
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.style,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        self._update_style(1)

    def _update_style(self, scale):
        if scale == self.style_scale:
            return
        self.style_scale = scale
        self.style.load_from_data(('''
.parameter-help > contents { background: #1d2630; border: 1px solid #49606c;
 border-radius: 11px; padding: 0; box-shadow: 0 8px 22px alpha(black, 0.28); }
.parameter-help .help-header { padding: 13px 16px 11px; border-bottom: 1px solid #344653; }
.parameter-help .help-family { color: #91acb9; font-size: %gpx; }
.parameter-help .help-title { color: #f2f5f7; font-weight: 700; font-size: %gpx; }
.parameter-help .help-value { color: #a9e2df; background: #283f49; border-radius: 5px;
 padding: 3px 7px; font-size: %gpx; font-variant-numeric: tabular-nums; }
.parameter-help .help-meaning, .parameter-help .help-effect,
.parameter-help .help-details { color: #d7e1e8; font-size: %gpx; }
.parameter-help .help-caption { color: #b0bfca; font-size: %gpx; }
.parameter-help .help-subtitle { color: #9cd9d3; font-weight: 600; font-size: %gpx; }
.parameter-help .help-footer { padding: 8px 16px; border-top: 1px solid #344653; }
.parameter-help .help-footnote { color: #9caebb; font-size: %gpx; }
.parameter-help button { min-height: 22px; min-width: 20px; padding: 2px 6px;
 background: transparent; border-color: transparent; font-size: %gpx; }
.parameter-help button:hover { background: #304753; }
.parameter-help button:checked { background: #304c55; color: #b9ece6; border-color: #568a90; }
.parameter-help expander > title { padding: 2px 0; color: #a9c7d3; font-size: %gpx; }
.parameter-help-trigger { min-height: 19px; min-width: 19px; padding: 2px;
 border-radius: 5px; opacity: 0.72; }
.parameter-help-trigger:hover, .parameter-help-trigger:focus-visible { opacity: 1; }
.parameter-help-label:hover { color: #a9e2df; text-decoration: underline; }
''' % tuple(x*scale for x in (10,17,12,13,11,11,10,10,12))).encode())

    def values(self):
        values = dict(getattr(self.app, 'field_values', {}))
        design = getattr(self.app,'design',None)
        if design is not None and design.family == self.app.family:
            values.update(design.values)
        values.update(getattr(self.app,'option_values',{}))
        return values

    def help_for(self, binding):
        result = lookup(self.app.family, binding.key, self.values())
        if self.app.family in ('spur', 'helical', 'double') and binding.key in ('input_rpm', 'input_torque'):
            result = replace(result, diagram='single_motion')
        return result

    def current_value(self, binding, help):
        """Read display text without committing, normalizing or validating a field."""
        from math import isfinite
        control = binding.control
        if isinstance(control, (Gtk.SpinButton, Gtk.Entry)):
            raw = control.get_text().strip()
            if (binding.key == 'worm_static_friction' and not raw
                    and binding.key not in getattr(self.app, 'option_values', {})
                    and binding.key not in getattr(self.app, 'values', {}).get(self.app.family, {})):
                return 'Not specified'
            try:
                if not isfinite(float(raw.replace(',', '.'))):
                    return 'Editing value'
            except ValueError:
                return 'Editing value'
            unit = help.title.rsplit(' · ', 1)[-1]
            return raw+(' '+unit if unit in ('mm','°','rpm','N·m','%') else '')
        if isinstance(control, Gtk.DropDown):
            item = control.get_selected_item()
            return item.get_string() if isinstance(item, Gtk.StringObject) else ''
        if isinstance(control, Gtk.CheckButton):
            return 'On' if control.get_active() else 'Off'
        return ''

    def reset(self):
        self.close()
        self.bindings, self.all_bindings = {}, []

    def bind(self, label, control, key, row=None):
        existing = getattr(label, '_parameter_help_binding', None)
        if existing:
            self.bindings[key] = existing
            self.all_bindings.append(existing)
            existing.describe()
            return existing
        row = row or label.get_parent()
        if row.get_orientation() == Gtk.Orientation.VERTICAL:
            previous = label.get_prev_sibling()
            wrapper = Gtk.Box(spacing=4)
            row.remove(label)
            row.insert_child_after(wrapper, previous)
            wrapper.append(label)
            label.set_hexpand(True)
            row = wrapper
        binding = Binding(self, label, control, key, row)
        label._parameter_help_binding = binding
        self.bindings[key] = binding
        self.all_bindings.append(binding)
        label.connect('unmap', lambda *_: self.close() if self.active is binding else None)
        return binding

    def cancel_timers(self):
        for attr in ('timer', 'leave_timer'):
            value = getattr(self, attr)
            if value:
                GLib.source_remove(value)
                setattr(self, attr, 0)

    def enter(self, binding):
        self.cancel_timers()
        if self.active is binding or self.pinned:
            return
        def show():
            self.timer = 0
            self.open(binding)
            return GLib.SOURCE_REMOVE
        self.timer = GLib.timeout_add(HOVER_DELAY_MS, show)

    def leave(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if self.pinned or not self.active:
            return
        if self.leave_timer:
            GLib.source_remove(self.leave_timer)
        def hide():
            self.leave_timer = 0
            if not self.over_popup:
                self.close()
            return GLib.SOURCE_REMOVE
        self.leave_timer = GLib.timeout_add(LEAVE_DELAY_MS, hide)

    def close(self):
        self.cancel_timers()
        self.active = None
        self.pinned = self.over_popup = False
        if self.popover:
            self.popover.popdown()
            self.popover.unparent()
            self.popover = None

    @staticmethod
    def _text(value, css, *, selectable=False):
        label = Gtk.Label(label=value, xalign=0, wrap=True, selectable=selectable, css_classes=[css])
        label.set_max_width_chars(48)
        return label

    def open(self, binding, pinned=False):
        if not binding.label.get_mapped():
            return
        from geometry import FAMILIES
        from gi.repository import Pango
        self.close()
        self.active, self.pinned = binding, pinned
        help = self.help_for(binding)
        popup = Gtk.Popover(css_classes=['parameter-help'])
        popup.set_autohide(False)
        popup.set_has_arrow(True)
        popup.set_parent(binding.row)
        self.popover = popup
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, css_classes=['help-header'])
        top = Gtk.Box(spacing=8)
        family = Gtk.Label(label=FAMILIES[self.app.family].split(' · ')[0], xalign=0,
                           hexpand=True, ellipsize=Pango.EllipsizeMode.END, css_classes=['help-family'])
        top.append(family)
        self.pin = Gtk.ToggleButton(label='Keep open')
        self.pin.set_active(pinned)
        self.pin.set_tooltip_text('Keep this guide open when the pointer moves away · F1')
        self.pin.update_property([Gtk.AccessibleProperty.LABEL], ['Keep parameter guide open'])
        def pin_changed(button):
            self.pinned = button.get_active()
            self.footer_hint.set_text('Esc to close' if self.pinned else 'F1 to keep open · Esc to close')
            if self.pinned:
                self.cancel_timers()
            elif not self.over_popup:
                self.leave()
        self.pin.connect('toggled', pin_changed)
        top.append(self.pin)
        close = Gtk.Button.new_from_icon_name('window-close-symbolic')
        close.set_tooltip_text('Close guide · Escape')
        close.update_property([Gtk.AccessibleProperty.LABEL], ['Close parameter guide'])
        close.connect('clicked', lambda _: self.close())
        top.append(close)
        self.header.append(top)
        title_row = Gtk.Box(spacing=10)
        title = help.title
        if title.rsplit(' · ',1)[-1] in ('mm','°','rpm','N·m','%'):
            title = title.rsplit(' · ',1)[0]
        self.title = self._text(title, 'help-title')
        self.title.set_hexpand(True)
        title_row.append(self.title)
        self.value_label = Gtk.Label(label=self.current_value(binding, help),
            ellipsize=Pango.EllipsizeMode.END, css_classes=['help-value'])
        self.value_label.set_max_width_chars(15)
        self.value_label.set_valign(Gtk.Align.CENTER)
        self.value_label.set_tooltip_text(self.current_value(binding, help))
        self.value_label.set_visible(bool(self.value_label.get_text()))
        title_row.append(self.value_label)
        self.header.append(title_row)
        card.append(self.header)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for setter in (self.body.set_margin_start,self.body.set_margin_end,
                       self.body.set_margin_top,self.body.set_margin_bottom):
            setter(16)
        self.drawing = Gtk.DrawingArea(css_classes=['help-diagram'])
        self.drawing.set_content_width(360)
        self.drawing.set_content_height(220)
        def draw(area, cr, width, height):
            draw_diagram(area, cr, width, height, help, key=binding.key,
                         family=self.app.family, values=self.values())
        self.drawing.set_draw_func(draw)
        self.drawing.update_property([Gtk.AccessibleProperty.LABEL], ['Diagram: '+help.dimension])
        illustrated = diagram_kind(self.app.family,binding.key,help) not in ('text','empty')
        self.drawing.set_visible(False)
        self.diagram_expander = Gtk.Expander(label='Show diagram')
        self.diagram_expander.set_child(self.drawing)
        self.diagram_expander.set_visible(illustrated)
        self.diagram_expander.set_tooltip_text('Open the illustrated explanation')
        def diagram_changed(expander, *_):
            expanded = expander.get_expanded()
            expander.set_label('Diagram' if expanded else 'Show diagram')
            # A closed expander must not retain the drawing's minimum width.
            self.drawing.set_visible(expanded and illustrated)
            self._popup_geometry = None
        self.diagram_expander.connect('notify::expanded',diagram_changed)
        self.body.append(self.diagram_expander)
        self.body.append(self._text(help.meaning, 'help-meaning', selectable=True))
        self.body.append(self._text('WHAT CHANGES', 'help-subtitle'))
        summary, detail = effect_sections(help.effect)
        self.body.append(self._text(summary, 'help-effect', selectable=True))
        self.details = Gtk.Expander(label='Model and limits' if binding.key == 'worm_static_friction' else 'Geometry and dependencies')
        self.details.set_child(self._text(detail, 'help-details', selectable=True))
        self.details.set_visible(bool(detail))
        self.details.connect('notify::expanded', lambda *_: setattr(self, '_popup_geometry', None))
        self.body.append(self.details)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_child(self.body)
        card.append(self.scroll)
        self.footer = Gtk.Box(spacing=8, css_classes=['help-footer'])
        self.footer.append(Gtk.Label(label='Static contact model' if binding.key == 'worm_static_friction' else 'Schematic · not to scale', xalign=0,
                                    hexpand=True, css_classes=['help-footnote']))
        self.footer_hint = Gtk.Label(label='Esc to close' if pinned else 'F1 to keep open · Esc to close',
                                    css_classes=['help-footnote'])
        self.footer.append(self.footer_hint)
        card.append(self.footer)
        popup.set_child(card)
        motion = Gtk.EventControllerMotion()
        def popup_enter(*_):
            self.over_popup = True
            if self.leave_timer:
                GLib.source_remove(self.leave_timer)
                self.leave_timer = 0
        def popup_leave(*_):
            self.over_popup = False
            self.leave()
        motion.connect('enter',popup_enter)
        motion.connect('leave',popup_leave)
        popup.add_controller(motion)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed',lambda _,key,*args: (self.close() or True) if key==Gdk.KEY_Escape else False)
        popup.add_controller(keys)
        self._popup_geometry = None
        self._size_popup(binding,popup)
        def resized(widget,clock):
            if self.popover is not popup:
                return GLib.SOURCE_REMOVE
            root = binding.row.get_root()
            if not root:
                return GLib.SOURCE_REMOVE
            ok,bounds = binding.row.compute_bounds(root)
            geometry = (root.get_width(),root.get_height(),bounds.get_x(),bounds.get_y(),
                bounds.get_width(),bounds.get_height(),self.app.text_size.get_selected(),
                self.header.get_height(),self.footer.get_height()) if ok else None
            value = self.current_value(binding,help)
            if value != self.value_label.get_text():
                self.value_label.set_text(value)
                self.value_label.set_tooltip_text(value)
                self.drawing.queue_draw()
            if geometry is not None and geometry != self._popup_geometry:
                self._size_popup(binding,popup)
            self._contain_popup(popup,root)
            return GLib.SOURCE_CONTINUE
        popup.add_tick_callback(resized)
        popup.popup()

    def _size_popup(self,binding,popup):
        root = binding.row.get_root()
        if not getattr(root,'_parameter_help_events',False):
            root._parameter_help_events = True
            events = Gtk.EventControllerLegacy()
            events.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            def outside(controller,event):
                if (self.active and event is not None and event.get_surface()==root.get_surface()
                    and event.get_event_type() in (Gdk.EventType.BUTTON_PRESS,Gdk.EventType.TOUCH_BEGIN)):
                    self.close()
                return False
            events.connect('event',outside)
            root.add_controller(events)
            keys = Gtk.EventControllerKey()
            keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            keys.connect('key-pressed',lambda _,key,*args:
                         (self.close() or True) if key==Gdk.KEY_Escape and self.active else False)
            root.add_controller(keys)
        ok,bounds = binding.row.compute_bounds(root)
        if not ok:
            return
        rw,rh = root.get_width(),root.get_height()
        scale = (1,1.25,1.5)[self.app.text_size.get_selected()]
        self._update_style(scale)
        self._popup_geometry = (rw,rh,bounds.get_x(),bounds.get_y(),bounds.get_width(),
                                bounds.get_height(),self.app.text_size.get_selected(),
                                self.header.get_height(),self.footer.get_height())
        expanded = self.diagram_expander.get_visible() and self.diagram_expander.get_expanded()
        width = int(min((390 if expanded else 320)*scale,max(220,rw-56)))
        right = rw-bounds.get_x()-bounds.get_width()-24
        left = bounds.get_x()-24
        rect = Gdk.Rectangle()
        if right>=width or left>=width:
            popup.set_position(Gtk.PositionType.RIGHT if right>=width else Gtk.PositionType.LEFT)
            # Reserve room for the native shadow as well as visible content.
            rect.x = binding.row.get_width()+12 if right>=width else -12
            rect.y = binding.row.get_height()//2
            available = rh-80
        else:
            below = rh-bounds.get_y()-bounds.get_height()-16
            above = bounds.get_y()-16
            popup.set_position(Gtk.PositionType.BOTTOM if below>=above else Gtk.PositionType.TOP)
            rect.x = binding.row.get_width()//2
            rect.y = binding.row.get_height() if below>=above else 0
            available = max(below,above)-16
        rect.width = rect.height = 1
        popup.set_pointing_to(rect)
        self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC if expanded else Gtk.PolicyType.NEVER,
                               Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_max_content_width(-1)
        self.scroll.set_min_content_width(-1)
        self.scroll.set_min_content_width(width)
        self.scroll.set_max_content_width(width)
        # With horizontal scrolling disabled, GTK can otherwise allocate a
        # narrower natural child width despite min-content-width, particularly
        # after the diagram was shown and hidden. Request the guide width too.
        self.scroll.set_size_request(width,-1)
        # Preserve the original readable figure scale when a narrow root needs
        # horizontal scrolling; compact mode contains no hidden minimum width.
        diagram_width = max(round(358*scale),width-32)
        self.drawing.set_content_width(diagram_width)
        self.drawing.set_content_height(round(diagram_width*220/360))
        header_height = max(self.header.get_height(),self.header.measure(Gtk.Orientation.VERTICAL,width)[1])
        footer_height = max(self.footer.get_height(),self.footer.measure(Gtk.Orientation.VERTICAL,width)[1])
        self.scroll.set_max_content_height(max(72,int(available-header_height-footer_height-20)))
        if popup.get_mapped():
            popup.present()

    def _contain_popup(self,popup,root):
        """Constrain the native surface, including shadows, to the app window."""
        surface = popup.get_surface()
        if not isinstance(surface,Gdk.Popup) or surface.get_parent()!=root.get_surface():
            return
        width,height = root.get_width(),root.get_height()
        pw,ph = surface.get_width(),surface.get_height()
        if not pw or not ph:
            return
        if ph>height-16:
            self.scroll.set_max_content_height(max(72,
                self.scroll.get_max_content_height()-(ph-height+16)))
            popup.present()
            return
        x,y = surface.get_position_x(),surface.get_position_y()
        dx = max(8-x,min(0,width-8-x-pw))
        dy = max(8-y,min(0,height-8-y-ph))
        if dx or dy:
            ox,oy = popup.get_offset()
            popup.set_offset(ox+dx,oy+dy)
            popup.present()


def controller(app):
    if not hasattr(app,'parameter_help'):
        app.parameter_help = HelpController(app)
    return app.parameter_help


def bind_options(app):
    """Bind only known choice labels in the exact sections built by app.py."""
    owner = controller(app)
    roots = [body for _, body in app.sections.values()]
    roots.append(app.eccentric_design_box)
    def visit(box):
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            if isinstance(child, Gtk.Label) and child.get_text() in OPTION_LABELS and isinstance(nxt, Gtk.DropDown):
                # Preserve the dropdown and its callbacks; replace only its label
                # by a label/info row in the same position.
                row = Gtk.Box(spacing=4)
                previous = child.get_prev_sibling()
                box.remove(child);box.insert_child_after(row, previous)
                row.append(child);child.set_hexpand(True)
                owner.bind(child, nxt, OPTION_LABELS[child.get_text()], row)
            elif isinstance(child, Gtk.CheckButton) and child.get_label() in CHECK_LABELS:
                # The checkbutton remains the selectable control. Its separate
                # caption exposes hover help without intercepting a toggle.
                key = CHECK_LABELS[child.get_label()]
                caption = Gtk.Label(label=child.get_label(), xalign=0, wrap=True, hexpand=True)
                row = Gtk.Box(spacing=4)
                child.set_child(row);row.append(caption)
                owner.bind(caption, child, key, row)
            elif isinstance(child, Gtk.Box):
                visit(child)
            child = nxt
    for root in roots:
        visit(root)
    if app.family == 'worm':
        entry = getattr(app, 'io_friction_entry', None)
        label = entry.get_prev_sibling() if entry is not None else None
        if isinstance(label, Gtk.Label):
            owner.bind(label, entry, 'worm_static_friction')
    # Stable direct refs for controls created outside the parameter sections.
    caption = app.motion_caption
    owner.bind(caption, app.motion_speed_text, 'input_rpm')
    if app.variant_box.get_visible():
        label = app.variant_box.get_first_child()
        if isinstance(label, Gtk.Box):
            label = label.get_first_child()
        if isinstance(label, Gtk.Label):
            owner.bind(label, app.variant_selector, 'variant')
    # Each triple-member stage has two captions plus a derived fixed member.
    for key, roles in getattr(app, 'io_role_selectors', {}).items():
        for role in ('input', 'output'):
            control = roles[role];row=control.get_parent();label=row.get_first_child()
            owner.bind(label, control, key, row)
    for button in getattr(app, 'io_mode_buttons', {}).values():
        if isinstance(button, Gtk.CheckButton):
            caption = button.get_child()
            if isinstance(caption, Gtk.Label):
                row=Gtk.Box(spacing=4);button.set_child(None);row.append(caption);button.set_child(row)
                owner.bind(caption, button, 'io_scheme', row)
