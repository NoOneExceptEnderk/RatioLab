# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nonmodal, illustrated parameter guides for the live GTK controls."""
from dataclasses import replace
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
from parameter_help import Help, lookup, OPTION_LABELS, CHECK_LABELS
from parameter_help_diagrams import draw_diagram, diagram_kind

HOVER_DELAY_MS = 250
LEAVE_DELAY_MS = 220
SECTION_KEY = "__model_dimensions__"


class Binding:
    def __init__(self, owner, label, control, key, row):
        self.owner, self.label, self.control, self.key, self.row = owner, label, control, key, row
        # Keep the existing private activation handle for binding consumers,
        # but expose help through the parameter hover target and F1 only.
        from workspace_ui import workspace_glyph
        self.button = Gtk.Button(visible=False)
        self.button.set_valign(Gtk.Align.CENTER)
        self.glyph = workspace_glyph('help', self.button)
        self.glyph.set_content_width(14)
        self.glyph.set_content_height(14)
        self.glyph.set_halign(Gtk.Align.CENTER)
        self.glyph.set_valign(Gtk.Align.CENTER)
        self.button.set_child(self.glyph)
        self.button.add_css_class('flat')
        self.button.add_css_class('parameter-help-trigger')
        self.button.set_tooltip_text('Explain this parameter · F1')
        self.button.update_property([Gtk.AccessibleProperty.LABEL], ['Explain '+label.get_text()])
        self.button_activation = 'explicit'
        self.button_events = Gtk.EventControllerLegacy()
        self.button_events.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.button_events.connect('event', self.button_event)
        self.button.add_controller(self.button_events)
        self.button.connect('clicked', self.button_clicked)
        row.insert_child_after(self.button, label)
        label.add_css_class('parameter-help-label')
        label.set_tooltip_text(None)
        if control is not label:
            label.set_mnemonic_widget(control)
        self.over_row = self.over_control = False
        self.row_motion = Gtk.EventControllerMotion()
        self.row_motion.connect('enter', self.row_enter)
        self.row_motion.connect('leave', self.row_leave)
        row.add_controller(self.row_motion)
        # Controls may live below their caption (choice fields). Include those
        # too, without intercepting any edit or selection event.
        self.motion = Gtk.EventControllerMotion()
        self.motion.connect('enter', self.control_enter)
        self.motion.connect('leave', self.control_leave)
        if control is not label:
            control.add_controller(self.motion)
        self.key_controllers = []
        for widget in dict.fromkeys((control, self.button)):
            keys = Gtk.EventControllerKey()
            keys.connect('key-pressed', self.key_pressed)
            widget.add_controller(keys)
            self.key_controllers.append(keys)
            focus = Gtk.EventControllerFocus()
            def departed(*_):
                popup = owner.popover
                def check():
                    if owner.popover is not popup or owner.active is not self or owner.activation != 'explicit':
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

    def button_event(self, controller, event):
        kind = event.get_event_type() if event is not None else None
        if kind in (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE):
            self.button_activation = 'pointer'
        elif kind in (Gdk.EventType.KEY_PRESS, Gdk.EventType.TOUCH_BEGIN, Gdk.EventType.TOUCH_END):
            self.button_activation = 'explicit'
        return False

    def button_clicked(self, *_):
        activation, self.button_activation = self.button_activation, 'explicit'
        self.owner.open(self, activation=activation)

    def row_enter(self, *_):
        self.over_row = True
        self.owner.enter(self)

    def row_leave(self, *_):
        self.over_row = False
        if not self.over_control:
            self.owner.unsuppress(self)
        if self.owner.active is self or self.owner.pending is self:
            self.owner.leave()

    @property
    def hovered(self):
        return self.over_row or self.over_control

    def control_enter(self, *_):
        self.over_control = True
        self.owner.enter(self)

    def control_leave(self, *_):
        self.over_control = False
        if not self.over_row:
            self.owner.unsuppress(self)
            if self.owner.active is self or self.owner.pending is self:
                self.owner.leave()

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
            self.owner.close(dismissed=True)
            return True
        return False

    def open(self):
        self.owner.open(self, activation='explicit')


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
        self.pending = None
        self.over_popup = False
        self.activation = 'pointer'
        self.suppressed = None
        self.section_binding = None
        self.return_focus = None
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
.parameter-help { background: transparent; }
.parameter-help > contents { background: alpha(@rl_surface, 0.89); background-image: none; border: 1px solid @rl_line;
 border-radius: 10px; padding: 0; box-shadow: inset 0 0 0 1px @rl_line, 0 10px 30px alpha(#11161d, 0.33); }
.parameter-help .help-header { padding: 12px; border-bottom: 1px solid @rl_line; }
.parameter-help .help-family { color: @rl_muted; font-size: %gpx; }
.parameter-help .help-title { color: @rl_text; font-weight: 700; font-size: %gpx; }
.parameter-help .help-value { color: @rl_accent; background: @rl_selected; border-radius: 5px;
 padding: 3px 7px; font-size: %gpx; font-variant-numeric: tabular-nums; }
.parameter-help .help-meaning, .parameter-help .help-effect,
.parameter-help .help-details { color: @rl_text; font-size: %gpx; }
.parameter-help .help-caption { color: @rl_muted; font-size: %gpx; }
.parameter-help .help-subtitle { color: @rl_muted; font-weight: 600; font-size: %gpx; }
.parameter-help .help-footer { padding: 8px 12px; border-top: 1px solid @rl_line; }
.parameter-help .help-footnote { color: @rl_muted; font-size: %gpx; }
.parameter-help button { min-height: 22px; min-width: 20px; padding: 3px;
 background: transparent; border-color: transparent; font-size: %gpx; }
.parameter-help button:hover { background: @rl_hover; }
.parameter-help button:checked { background: @rl_selected; color: @rl_text; border-color: @rl_accent; }
.parameter-help expander > title { padding: 2px 0; color: @rl_muted; font-size: %gpx; }
.reducers .parameter-help-trigger { min-height: 14px; min-width: 14px; padding: 0;
 background: transparent; border: 0; border-radius: 0;
 font-size: 10px; font-weight: 500; color: @rl_muted; opacity: 0.72; }
.parameter-help-trigger:hover, .parameter-help-trigger:focus-visible { opacity: 1; }
.parameter-help-label:hover { color: @rl_accent; text-decoration: underline; }
''' % tuple(x*scale for x in (11,14,11,12,11,11,11,12,12))).encode())

    def values(self):
        values = dict(getattr(self.app, 'field_values', {}))
        design = getattr(self.app,'design',None)
        if design is not None and design.family == self.app.family:
            values.update(design.values)
        values.update(getattr(self.app,'option_values',{}))
        return values

    def help_for(self, binding):
        if binding.key == SECTION_KEY:
            return Help('Model & dimensions',
                        'Choose a gear or reducer family, then its available variant.',
                        'Set dimensions in the grouped controls and inspect the model and results. '
                        'Advanced groups expose the additional geometry and assembly options supported by the selected model.',
                        'text', '')
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
        if self.section_binding:
            self.all_bindings.append(self.section_binding)

    def bind_section(self, label, row=None, *, control=None):
        """Attach the same guide to the model-and-dimensions heading."""
        self.section_binding = self.bind(label, control or label, SECTION_KEY, row)
        return self.section_binding

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
        self.pending = None
        for attr in ('timer', 'leave_timer'):
            value = getattr(self, attr)
            if value:
                GLib.source_remove(value)
                setattr(self, attr, 0)

    def unsuppress(self, binding):
        if self.suppressed is binding:
            self.suppressed = None

    def enter(self, binding):
        self.cancel_timers()
        if not getattr(self.app, 'workspace_preferences', {}).get('hover_help', True):
            return
        if self.active is binding or self.suppressed is binding:
            return
        if self.active and self.activation == 'explicit':
            return
        self.pending = binding
        def show():
            self.timer = 0
            self.pending = None
            self.open(binding)
            return GLib.SOURCE_REMOVE
        self.timer = GLib.timeout_add(HOVER_DELAY_MS, show)

    def leave(self):
        self.pending = None
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if not self.active or self.activation != 'pointer':
            return
        if self.leave_timer:
            GLib.source_remove(self.leave_timer)
        def hide():
            self.leave_timer = 0
            binding = self.active
            # A pointer-opened card never becomes pinned by focusing Expand.
            # Keyboard/touch activation remains available without a pointer.
            if binding and not self.over_popup and not binding.hovered:
                self.close()
            return GLib.SOURCE_REMOVE
        self.leave_timer = GLib.timeout_add(LEAVE_DELAY_MS, hide)

    def popup_enter(self, *_):
        self.over_popup = True
        if self.leave_timer:
            GLib.source_remove(self.leave_timer)
            self.leave_timer = 0

    def popup_leave(self, *_):
        self.over_popup = False
        self.leave()

    def close(self, dismissed=False):
        self.cancel_timers()
        binding, popup = self.active, self.popover
        if dismissed:
            self.suppressed = binding if binding and binding.hovered else None
        root = binding.control.get_root() if binding else None
        focus = root.get_focus() if root else None
        # Restore focus only if it is inside the dismissed guide. Merely
        # hovering or leaving must never steal focus from a text edit.
        restore = bool(focus and popup and (focus is popup or focus.is_ancestor(popup)))
        self.active = self.popover = None
        self.over_popup = False
        self.activation = 'pointer'
        if popup:
            popup.popdown()
            popup.unparent()
        target = self.return_focus
        self.return_focus = None
        if restore:
            if target is not None and target.get_mapped():
                target.grab_focus()
            elif binding.button.get_mapped():
                binding.button.grab_focus()

    @staticmethod
    def _text(value, css, *, selectable=False):
        label = Gtk.Label(label=value, xalign=0, wrap=True, selectable=selectable, css_classes=[css])
        label.set_max_width_chars(48)
        return label

    def open(self, binding, pinned=False, activation=None):
        if not binding.label.get_mapped():
            return
        from geometry import FAMILIES
        from gi.repository import Pango
        self.close()
        root = binding.control.get_root()
        self.return_focus = root.get_focus() if root else None
        self.active = binding
        self.activation = activation or ('explicit' if pinned else 'pointer')
        help = self.help_for(binding)
        popup = Gtk.Popover(css_classes=['parameter-help'])
        popup.set_autohide(False)
        popup.set_has_arrow(False)
        popup.set_parent(binding.row)
        self.popover = popup
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, css_classes=['help-header'])
        top = Gtk.Box(spacing=6)
        family = Gtk.Label(label=FAMILIES[self.app.family].split(' · ')[0], xalign=0,
                           hexpand=True, ellipsize=Pango.EllipsizeMode.END, css_classes=['help-family'])
        top.append(family)
        close = Gtk.Button.new_from_icon_name('window-close-symbolic')
        close.set_tooltip_text('Close guide · Escape')
        close.update_property([Gtk.AccessibleProperty.LABEL], ['Close parameter guide'])
        close.connect('clicked', lambda _: self.close(dismissed=True))
        self.close_button = close
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
            setter(12)
        self.drawing = Gtk.DrawingArea(css_classes=['help-diagram'])
        self.drawing.set_halign(Gtk.Align.START)
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
            if self.popover is not popup:
                return
            expanded = expander.get_expanded()
            expander.set_label('Diagram' if expanded else 'Show diagram')
            # A closed expander must not retain the drawing's minimum width.
            self.drawing.set_visible(expanded and illustrated)
            self._popup_geometry = None
        self.diagram_expander.connect('notify::expanded',diagram_changed)
        self.body.append(self.diagram_expander)
        section = binding.key == SECTION_KEY
        if section:
            self.body.append(self._text('CHOOSE MODEL', 'help-subtitle'))
        self.body.append(self._text(help.meaning, 'help-meaning', selectable=True))
        self.body.append(self._text('SET DIMENSIONS' if section else 'WHAT CHANGES', 'help-subtitle'))
        summary, detail = effect_sections(help.effect)
        self.body.append(self._text(summary, 'help-effect', selectable=True))
        self.details = Gtk.Expander(label='Model and limits' if binding.key == 'worm_static_friction' else 'Geometry and dependencies')
        self.details.set_child(self._text(detail, 'help-details', selectable=True))
        self.details.set_visible(bool(detail) and not section)
        if section:
            self.body.append(self._text('ADVANCED OPTIONS', 'help-subtitle'))
            self.body.append(self._text(detail, 'help-details', selectable=True))
        self.details.connect('notify::expanded', lambda *_: setattr(self, '_popup_geometry', None))
        self.body.append(self.details)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_child(self.body)
        card.append(self.scroll)
        self.footer = Gtk.Box(spacing=8, css_classes=['help-footer'])
        self.footer.append(Gtk.Label(label='Choose · adjust · preview' if binding.key == SECTION_KEY else 'Static contact model' if binding.key == 'worm_static_friction' else 'Schematic · not to scale', xalign=0,
                                    hexpand=True, css_classes=['help-footnote']))
        self.footer_hint = Gtk.Label(label='Esc to close',
                                    css_classes=['help-footnote'])
        self.footer.append(self.footer_hint)
        card.append(self.footer)
        popup.set_child(card)
        motion = Gtk.EventControllerMotion()
        motion.connect('enter', lambda *_: self.popup_enter() if self.popover is popup else None)
        motion.connect('leave', lambda *_: self.popup_leave() if self.popover is popup else None)
        self.popup_motion = motion
        popup.add_controller(motion)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed',lambda _,key,*args: (self.close(dismissed=True) or True) if key==Gdk.KEY_Escape else False)
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
                         (self.close(dismissed=True) or True) if key==Gdk.KEY_Escape and self.active else False)
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
        width = round(min((390 if expanded else 286)*scale,max(220,rw-56)))
        sidebar = getattr(self.app, "parameter_panel", None)
        sidebar_ok, sidebar_bounds = sidebar.compute_bounds(root) if sidebar else (False, None)
        edge = (sidebar_bounds.get_x()+sidebar_bounds.get_width()
                if sidebar_ok and binding.row.is_ancestor(sidebar)
                else bounds.get_x()+bounds.get_width())
        right = rw-edge-24
        left = bounds.get_x()-24
        rect = Gdk.Rectangle()
        if right>=width or left>=width:
            popup.set_position(Gtk.PositionType.RIGHT if right>=width else Gtk.PositionType.LEFT)
            # Reserve room for the native shadow as well as visible content.
            rect.x = round(edge-bounds.get_x()+10) if right>=width else 0
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
        diagram_width = round(360*scale)
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
        owner.bind(app.variant_caption, app.variant_selector, 'variant')
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
