# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Single viewport transport bar and a speed-adjustment popover."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk
from math import log1p, expm1, isfinite, copysign
from gui_workflow import (set_numeric_value, numeric_value,
                          _track_numeric_entry, _normalize_numeric_entry)


def scale_rpm(value):
    return copysign(log1p(abs(value)), value)


def unscale_rpm(value):
    return copysign(expm1(abs(value)), value)


def install(app, container):
    row = Gtk.Box(spacing=9)
    container.append(row)
    play = Gtk.Button(label='Start motion')
    app.motion_play = app.quick_play = play
    row.append(play)
    def toggle(_):
        if not app.canvas.motion_playing and app.view_options['exploded'].get_active():
            app.view_options['exploded'].set_active(False)
        app.canvas.set_motion_playing(not app.canvas.motion_playing)
    play.connect('clicked', toggle)
    caption = Gtk.Label(label='Input speed', css_classes=['muted'])
    app.motion_caption = caption
    row.append(caption)
    entry = Gtk.Entry(css_classes=['motion-rate'])
    entry.set_enable_undo(False)
    _track_numeric_entry(entry)
    entry.set_width_chars(8)
    entry.set_max_width_chars(10)
    entry.set_alignment(1)
    entry.set_input_purpose(Gtk.InputPurpose.NUMBER)
    entry.set_tooltip_text('Precise input speed. Press Enter or leave the field to apply; decimals and decimal commas are accepted.')
    row.append(entry)
    app.motion_speed_text = entry
    unit = Gtk.Label(label='rpm', css_classes=['muted'])
    app.motion_unit = unit
    row.append(unit)
    button = Gtk.MenuButton(label='Adjust')
    app.motion_button = button
    row.append(button)
    popup = Gtk.Popover(css_classes=['motion-palette'])
    button.set_popover(popup)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.set_size_request(290, -1)
    content.append(Gtk.Label(label='Input speed · progressive scale', xalign=0, css_classes=['step-title']))
    slider_row = Gtk.Box(spacing=8)
    content.append(slider_row)
    slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, log1p(100000), .01)
    slider.set_draw_value(False)
    slider.set_hexpand(True)
    app.motion_speed = slider
    info = Gtk.Label(xalign=0, wrap=True, css_classes=['muted'])
    info.set_max_width_chars(34)
    content.append(info)
    app.motion_info = info
    popup.set_child(content)
    reset = Gtk.Button(label='Initial pose')
    app.motion_reset = reset
    row.append(reset)
    reset.connect('clicked', lambda _: app.canvas.reset_motion())
    status = Gtk.Label(xalign=1, hexpand=True, css_classes=['muted'])
    row.append(status)
    app.playback_hint = status
    error = Gtk.Label(xalign=0, wrap=True, css_classes=['motion-input-error'])
    error.set_visible(False)
    container.append(error)
    app.motion_rate_error = error
    app.motion_rate_editing = False
    app.motion_input_invalid = False
    drag_time = None
    drag_group = None
    def show_value(value):
        app.motion_syncing = True
        set_numeric_value(entry, value)
        app.motion_syncing = False
    def apply_rate(value):
        low, high = getattr(app, 'motion_rate_limits', (0, 100000))
        if not isfinite(value) or not low <= value <= high:
            raise ValueError(f'Enter a value between {low:g} and {high:g} {unit.get_text()}.')
        app.motion_rate_editing = False
        app.motion_input_invalid = False
        entry.remove_css_class('field-error')
        error.set_visible(False)
        app.motion_syncing = True
        slider.set_value(scale_rpm(value))
        app.motion_syncing = False
        show_value(value)
        if hasattr(app, 'motion_rpm'):
            app.motion_rpm = value
            app.apply_motion_rate(drag_group or (app.family, 'input_rpm'),now=drag_time)
        else:
            app.canvas.set_motion_speed(value / 12)
    def commit(*args):
        if not app.motion_rate_editing:
            return
        try:
            try:
                value = numeric_value(entry)
            except ValueError:
                raise ValueError('Enter a valid number, for example 125.5.')
            low, high = getattr(app, 'motion_rate_limits', (0, 100000))
            _normalize_numeric_entry(entry, low=low, high=high)
            apply_rate(value)
        except ValueError as exc:
            app.motion_input_invalid = True
            app.error_field = 'input_rpm'
            entry.add_css_class('field-error')
            error.set_text(str(exc))
            error.set_visible(True)
            for name in ('export_menu','send_btn','fusion_send_btn'):
                action=getattr(app,name,None)
                if action is not None:action.set_sensitive(False)
    app.commit_motion_rate = commit
    def editing(*args):
        if not getattr(app, 'motion_syncing', False):
            app.motion_rate_editing = True
            if not app.building:
                app.project_changed((app.family, 'input_rpm'))
    entry.connect('changed', editing)
    entry.connect('activate', commit)
    focus = Gtk.EventControllerFocus()
    focus.connect('leave', commit)
    entry.add_controller(focus)
    slider.connect('value-changed', lambda w: apply_rate(round(unscale_rpm(w.get_value())))
                   if not getattr(app, 'motion_syncing', False) else None)
    def begin_drag(*args):
        nonlocal drag_time, drag_group
        drag_time = GLib.get_monotonic_time()/1000000
        drag_group = (app.family, 'input_rpm', object())
        if hasattr(app,'document'):app.document.barrier()
    def end_drag(*args):
        nonlocal drag_time, drag_group
        active=drag_group is not None
        drag_time = drag_group = None
        if not active:return
        if hasattr(app,'document'):app.document.barrier()
        if hasattr(app,'flush_motion_document'):app.flush_motion_document()
    popup.connect('closed',end_drag)
    # Observe the sequence without competing with the scale's own drag gesture.
    # A GestureClick can be cancelled as soon as that gesture claims the drag.
    events = Gtk.EventControllerLegacy()
    events.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    def slider_event(controller,event):
        event=event or controller.get_current_event()
        if event is None:return False
        kind=event.get_event_type()
        if kind in (Gdk.EventType.BUTTON_PRESS,Gdk.EventType.TOUCH_BEGIN):begin_drag()
        elif kind in (Gdk.EventType.BUTTON_RELEASE,Gdk.EventType.TOUCH_END,Gdk.EventType.TOUCH_CANCEL,Gdk.EventType.GRAB_BROKEN):end_drag()
        return False
    events.connect('event',slider_event)
    slider.add_controller(events)
    app.begin_motion_rate_drag = begin_drag
    app.end_motion_rate_drag = end_drag
    def dispose(*args):
        nonlocal drag_time, drag_group
        drag_time = drag_group = None
        if getattr(app,'motion_document_pending',0):
            GLib.source_remove(app.motion_document_pending)
            app.motion_document_pending=0
    container.connect('unrealize',dispose)
    for title, delta in [('−1', -1), ('+1', 1)]:
        step = Gtk.Button(label=title)
        step.set_tooltip_text(f'Change input speed by {delta:+d} rpm')
        step.connect('clicked', lambda _, d=delta: apply_rate(max(app.motion_rate_limits[0],
            min(app.motion_rate_limits[1], (app.motion_rpm if hasattr(app, 'motion_rpm')
                else 12*app.canvas.motion_speed) + d))))
        slider_row.append(step)
        if delta < 0:
            slider_row.append(slider)
    def update(*args):
        c = app.canvas
        plan = c.motion_plan
        available = bool(plan and plan.supported and c.motion_valid and not c.failure and not app.busy)
        play.set_sensitive(available)
        reset.set_sensitive(c.design is not None and not app.busy)
        entry.set_sensitive(not app.busy)
        slider.set_sensitive(not app.busy)
        play.set_label('Pause' if c.motion_playing else 'Resume motion' if c.motion_enabled and c.motion_phase else 'Start motion')
        status.set_text('Playing' if c.motion_playing else '' if available else 'Animation unavailable')
        if not app.motion_rate_editing:
            show_value(app.motion_rpm if hasattr(app, 'motion_rpm') else 12*c.motion_speed)
        info.set_text('Correct the parameters to restart the animation.' if not c.motion_valid
                      else plan.message if plan else 'Choose a model to see its motion.')
    app.canvas.connect('motion-state', update)
    app.update_motion_controls = app.update_playback_bar = update
    update()


def configure(app,values,specs):
 """Bind the single RPM control to the saved input, including loaded configs."""
 if hasattr(app,'end_motion_rate_drag'):app.end_motion_rate_drag()
 app.motion_syncing=True;app.motion_rate_editing=False;app.motion_input_invalid=False;app.motion_speed_text.remove_css_class('field-error');app.motion_rate_error.set_visible(False)
 rpm_spec=next((s for s in specs if s[0]=='input_rpm'),None)
 speed=app.motion_speed;speed.clear_marks()
 if rpm_spec:
  _,_,default,low,high,_=rpm_spec;app.motion_rate_limits=(low,high);app.motion_unit.set_text('rpm');app.motion_rpm=values.get('input_rpm',default)
  app.motion_speed_text._numeric_typed_text=None
  set_numeric_value(app.motion_speed_text,app.motion_rpm)
  speed.set_range(scale_rpm(low),scale_rpm(high));speed.set_value(scale_rpm(app.motion_rpm))
  for rpm in (-100000,0,100000):
   if low<=rpm<=high:speed.add_mark(scale_rpm(rpm),Gtk.PositionType.BOTTOM,'−100k' if rpm==-100000 else '100k' if rpm==100000 else str(rpm))
  classic=app.family=='differential' and values.get('configuration')=='classic'
  app.motion_caption.set_text('Carrier input speed' if classic else 'Input A speed' if app.family=='differential' else 'Input speed · stage 1' if app.family=='planetary' and values.get('variant') in ('two_stage','two_stage_double') else 'Sun input speed' if app.family=='wolfrom' else 'Input speed')
  speed.set_tooltip_text('Signed carrier RPM; prescribe the side-speed difference independently in Motion.' if classic else 'Signed input A RPM; set input B independently in Motion.' if app.family=='differential' else 'Signed sun input RPM · −100,000 to +100,000. Positive is counterclockwise viewed from +Z toward XY; reversing input reverses all moving members. Zero stops every member.' if app.family=='wolfrom' else 'Actual input RPM · progressive scale 0–100,000. Also updates calculations and configuration. Use the arrows to adjust.')
 app.motion_syncing=False
