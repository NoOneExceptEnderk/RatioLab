# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Single viewport transport bar and a speed-adjustment popover."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk
from math import log1p, expm1, isfinite, copysign, degrees, radians
from gui_workflow import (set_numeric_value, numeric_value,
                          _track_numeric_entry, _normalize_numeric_entry)


def scale_rpm(value):
    return copysign(log1p(abs(value)), value)


def unscale_rpm(value):
    return copysign(expm1(abs(value)), value)


def install(app, container):
    app.motion_bar=container
    container.set_spacing(6)
    transport = Gtk.Box(spacing=7,css_classes=['motion-transport-row'])
    container.append(transport)
    row = Gtk.Box(spacing=7,css_classes=['motion-input-row'])
    container.append(row)
    play = Gtk.Button(label='Play',css_classes=['motion-play'])
    app.motion_play = app.quick_play = play
    transport.append(play)
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
    entry.set_width_chars(7)
    entry.set_max_width_chars(7)
    entry.set_alignment(1)
    entry.set_input_purpose(Gtk.InputPurpose.NUMBER)
    entry.set_tooltip_text('Precise input speed. Press Enter or leave the field to apply; decimals and decimal commas are accepted.')
    rate_display = Gtk.Stack(hhomogeneous=True, vhomogeneous=True)
    rate_display.add_named(entry, 'value')
    rate_preview = Gtk.Label(xalign=1, margin_end=9, width_chars=7)
    rate_display.add_named(rate_preview, 'preview')
    row.append(rate_display)
    app.motion_rate_preview = rate_preview
    app.motion_rate_display = rate_display
    app.motion_speed_text = entry
    unit = Gtk.Label(label='rpm', css_classes=['muted'])
    app.motion_unit = unit
    row.append(unit)
    button = Gtk.MenuButton(label='Rate info',css_classes=['motion-details-button'])
    app.motion_button = button
    popup = Gtk.Popover(css_classes=['motion-palette'])
    button.set_popover(popup)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.set_size_request(290, -1)
    content.append(Gtk.Label(label='Input speed · progressive scale', xalign=0, css_classes=['step-title']))
    slider_row = Gtk.Box(spacing=8)
    row.append(slider_row)
    slider_row.set_hexpand(True)
    slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, log1p(100000), .01)
    slider.set_draw_value(False)
    slider.set_valign(Gtk.Align.CENTER)
    slider.set_hexpand(True)
    app.motion_speed = slider
    slider.add_css_class('motion-scale')
    info = Gtk.Label(xalign=0, wrap=True, css_classes=['muted'])
    info.set_max_width_chars(34)
    content.append(info)
    app.motion_info = info
    popup.set_child(content)
    reset = Gtk.Button(label='Initial pose',css_classes=['flat'])
    app.motion_reset = reset
    transport.insert_child_after(reset,play)
    reset.connect('clicked', lambda _: app.canvas.reset_motion())
    status = Gtk.Label(xalign=1, css_classes=['muted'])
    transport.append(status)
    transport.append(button)
    app.playback_hint = status
    app.motion_phase_label = Gtk.Label(xalign=0, css_classes=['muted','motion-phase'])
    transport.insert_child_after(app.motion_phase_label,reset)
    phase = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 360, .1)
    phase.set_draw_value(False)
    phase.set_hexpand(True)
    phase.set_size_request(120, -1)
    phase.set_tooltip_text('Drag to pause and inspect the preview phase. RPM and project data stay unchanged.')
    phase.add_css_class('motion-phase-scale')
    transport.insert_child_after(phase, app.motion_phase_label)
    app.motion_phase = phase
    connections = Gtk.Button(label='I/O', css_classes=['flat','motion-connections'])
    connections.set_tooltip_text('I/O connections')
    app.motion_connections=connections
    connections.connect('clicked', lambda _: __import__('gui_workflow').show_page(app,'motion'))
    transport.append(connections)
    from workspace_ui import decorate_action
    decorate_action(play,'play',vector=True)
    decorate_action(reset,'reset',vector=True)
    decorate_action(connections,'io',vector=True)
    def play_icon(*_):
        play.workspace_icon.glyph_name='pause' if play.get_label()=='Pause' else 'play'
        play.workspace_icon.queue_draw()
    play.connect('notify::label',play_icon)
    def adaptive_spacing(*_):
        scale=app.text_size.get_selected()
        for name,active in (('enlarged-transport',scale>0),('compact-transport',scale==2)):
            if active:container.add_css_class(name)
            else:container.remove_css_class(name)
        container.set_spacing(4 if scale==2 else 6)
    app.text_size.connect('notify::selected',adaptive_spacing)
    adaptive_spacing()
    phase_text_time = [0]
    phase_syncing = False
    def show_phase(*_):
        now = GLib.get_monotonic_time()
        # Text layout need not run at the model's frame rate. Keep the model
        # on every display tick and refresh its readout at most ten times/s.
        if app.canvas.motion_playing and now-phase_text_time[0] < 100000:return True
        phase_text_time[0] = now
        text=(f"Rack travel · {app.canvas.motion_plan.matrix(1,app.canvas.motion_phase)[12]:+.3f} mm"
              if app.canvas.design and app.canvas.design.family=='rack' else f'Reference phase · {degrees(app.canvas.motion_phase)%360:.1f}°')
        if app.motion_phase_label.get_text()!=text:app.motion_phase_label.set_text(text)
        nonlocal phase_syncing
        if not phase_syncing:
            phase_syncing = True
            try:
                limits = app.canvas.motion_plan.phase_limits if app.canvas.motion_plan else None
                low, high = tuple(map(degrees, limits)) if limits and limits[1] > limits[0] else (0, 360)
                phase.set_range(low, high)
                value = degrees(app.canvas.motion_phase)
                phase.set_value(value if limits or 0 <= value <= 360 else value % 360)
            finally:phase_syncing = False
        return True
    def seek_phase(widget):
        nonlocal phase_syncing
        if phase_syncing:return
        target = radians(widget.get_value())
        phase_syncing = True
        try:app.canvas.seek_motion_phase(target)
        finally:phase_syncing = False
        phase_text_time[0] = 0
        show_phase()
    phase.connect('value-changed', seek_phase)
    def phase_accessibility(label, *_):
        text = label.get_text()
        phase.update_property([Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.VALUE_TEXT],
                              [text.split('·')[0].strip(), text])
    app.motion_phase_label.connect('notify::label', phase_accessibility)
    phase_tick=[0]
    def phase_watch(*_):
        phase_text_time[0] = 0
        if app.canvas.motion_playing and not phase_tick[0]:
            phase_tick[0]=app.motion_phase_label.add_tick_callback(show_phase)
        elif not app.canvas.motion_playing and phase_tick[0]:
            app.motion_phase_label.remove_tick_callback(phase_tick[0]);phase_tick[0]=0
        show_phase()
    app.canvas.connect('motion-state',phase_watch)
    app.motion_phase_label.connect('unrealize',lambda *_: app.motion_phase_label.remove_tick_callback(phase_tick[0]) if phase_tick[0] else None)
    show_phase()
    error = Gtk.Label(xalign=0, wrap=True, css_classes=['motion-input-error'])
    error.set_visible(False)
    container.append(error)
    app.motion_rate_error = error
    app.motion_rate_editing = False
    app.motion_input_invalid = False
    drag_time = None
    drag_group = None
    drag_source = None
    preview_value = None
    finish_source = 0
    finish_commit = True
    def show_value(value):
        app.motion_syncing = True
        set_numeric_value(entry, value)
        app.motion_syncing = False
    def apply_rate(value, *, sync_slider=True):
        low, high = getattr(app, 'motion_rate_limits', (0, 100000))
        if not isfinite(value) or not low <= value <= high:
            raise ValueError(f'Enter a value between {low:g} and {high:g} {unit.get_text()}.')
        app.motion_rate_editing = False
        app.motion_input_invalid = False
        entry.remove_css_class('field-error')
        error.set_visible(False)
        if sync_slider:
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
    def slider_changed(widget):
        if getattr(app, 'motion_syncing', False):return
        nonlocal preview_value, drag_source
        value = round(unscale_rpm(widget.get_value()))
        if drag_group is not None:
            if preview_value is None:
                drag_source = (app.family, app.document.token if hasattr(app, 'document') else None)
            preview_value = value
            rate_preview.set_text(str(value))
            rate_display.set_visible_child_name('preview')
            slider.update_property([Gtk.AccessibleProperty.VALUE_TEXT], [f'{value} rpm'])
            return
        # Keep the pointer's continuous position on the progressive scale.
        # Reapplying the rounded RPM here makes its thumb jump at low speeds.
        if (value != getattr(app, 'motion_rpm', None)
                or app.motion_rate_editing or app.motion_input_invalid):
            apply_rate(value, sync_slider=False)
    slider.connect('value-changed', slider_changed)
    def begin_drag(*args):
        nonlocal drag_time, drag_group
        if finish_source:end_drag(commit=finish_commit)
        if drag_group is not None:return
        if app.motion_rate_editing:commit()
        drag_time = GLib.get_monotonic_time()/1000000
        drag_group = (app.family, 'input_rpm', object())
        if hasattr(app,'document'):app.document.barrier()
    def end_drag(*args, commit=True):
        nonlocal drag_time, drag_group, drag_source, preview_value, finish_source
        if finish_source:
            GLib.source_remove(finish_source);finish_source=0
        active=drag_group is not None
        if not active:return
        source=(app.family,app.document.token if hasattr(app,'document') else None)
        value=preview_value
        accepted=False
        try:
            if (commit and value is not None and source==drag_source
                    and not app.building and not getattr(app,'project_restoring',False)):
                if value!=getattr(app,'motion_rpm',None) or app.motion_rate_editing or app.motion_input_invalid:
                    apply_rate(value,sync_slider=False)
                accepted=True
        finally:
            drag_time=drag_group=drag_source=preview_value=None
            rate_display.set_visible_child_name('value')
            if not accepted:
                app.motion_syncing=True
                try:slider.set_value(scale_rpm(app.motion_rpm if hasattr(app,'motion_rpm') else 12*app.canvas.motion_speed))
                finally:app.motion_syncing=False
            slider.update_property([Gtk.AccessibleProperty.VALUE_TEXT],
                                   [f'{app.motion_rpm if hasattr(app,"motion_rpm") else 12*app.canvas.motion_speed} rpm'])
        if hasattr(app,'document'):app.document.barrier()
        if hasattr(app,'flush_motion_document'):app.flush_motion_document()
    def cancel_drag(*args):end_drag(commit=False)
    def schedule_finish(commit=True):
        nonlocal finish_source, finish_commit
        finish_commit = commit and (finish_commit if finish_source else True)
        if finish_source:return
        def finish():
            nonlocal finish_source
            finish_source=0;end_drag(commit=finish_commit)
            return False
        # Let GtkScale process its final release value before confirming it.
        finish_source=GLib.idle_add(finish,priority=GLib.PRIORITY_DEFAULT)
    # Observe the sequence without competing with the scale's own drag gesture.
    # A GestureClick can be cancelled as soon as that gesture claims the drag.
    events = Gtk.EventControllerLegacy()
    events.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    def slider_event(controller,event):
        event=event or controller.get_current_event()
        if event is None:return False
        kind=event.get_event_type()
        if kind in (Gdk.EventType.BUTTON_PRESS,Gdk.EventType.TOUCH_BEGIN):begin_drag()
        elif kind in (Gdk.EventType.BUTTON_RELEASE,Gdk.EventType.TOUCH_END):schedule_finish()
        elif kind in (Gdk.EventType.TOUCH_CANCEL,Gdk.EventType.GRAB_BROKEN):schedule_finish(False)
        elif kind in (Gdk.EventType.KEY_PRESS,Gdk.EventType.KEY_RELEASE):
            key=event.get_keyval()
            if key in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Up,Gdk.KEY_Down,Gdk.KEY_Home,Gdk.KEY_End,Gdk.KEY_Page_Up,Gdk.KEY_Page_Down):
                if kind==Gdk.EventType.KEY_PRESS:begin_drag()
                else:schedule_finish()
            elif key==Gdk.KEY_Escape and kind==Gdk.EventType.KEY_PRESS:schedule_finish(False)
        return False
    events.connect('event',slider_event)
    slider.add_controller(events)
    slider_focus=Gtk.EventControllerFocus()
    slider_focus.connect('leave',lambda *_:schedule_finish())
    slider.add_controller(slider_focus)
    app.motion_rate_slider_focus=slider_focus
    app.begin_motion_rate_drag = begin_drag
    app.end_motion_rate_drag = end_drag
    app.cancel_motion_rate_drag = cancel_drag
    def dispose(*args):
        cancel_drag()
        if getattr(app,'motion_document_pending',0):
            GLib.source_remove(app.motion_document_pending)
            app.motion_document_pending=0
    container.connect('unrealize',dispose)
    for title, delta in [('−1', -1), ('+1', 1)]:
        step = Gtk.Button(label=title,css_classes=["flat","motion-step"])
        step.set_valign(Gtk.Align.CENTER)
        step.set_tooltip_text(f'Change input speed by {delta:+d} rpm')
        step.connect('clicked', lambda _, d=delta: apply_rate(max(app.motion_rate_limits[0],
            min(app.motion_rate_limits[1], (app.motion_rpm if hasattr(app, 'motion_rpm')
                else 12*app.canvas.motion_speed) + d))))
        row.insert_child_after(step,caption if delta<0 else rate_display)
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
        phase.set_sensitive(available and any(plan.coordinate_rates.values())
                            and (plan.phase_limits is None or plan.phase_limits[1] > plan.phase_limits[0]))
        play.set_label('Pause' if c.motion_playing else 'Play')
        if c.motion_playing:play.add_css_class('playing')
        else:play.remove_css_class('playing')
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
 if hasattr(app,'cancel_motion_rate_drag'):app.cancel_motion_rate_drag()
 app.motion_syncing=True;app.motion_rate_editing=False;app.motion_input_invalid=False;app.motion_speed_text.remove_css_class('field-error');app.motion_rate_error.set_visible(False)
 rpm_spec=next((s for s in specs if s[0]=='input_rpm'),None)
 speed=app.motion_speed;speed.clear_marks()
 if rpm_spec:
  _,_,default,low,high,_=rpm_spec;app.motion_rate_limits=(low,high);app.motion_unit.set_text('rpm');app.motion_rpm=values.get('input_rpm',default)
  app.motion_speed_text._numeric_typed_text=None
  set_numeric_value(app.motion_speed_text,app.motion_rpm)
  speed.set_range(scale_rpm(low),scale_rpm(high));speed.set_value(scale_rpm(app.motion_rpm))
  speed.update_property([Gtk.AccessibleProperty.VALUE_TEXT],[f'{app.motion_rpm} rpm'])
  classic=app.family=='differential' and values.get('configuration')=='classic'
  app.motion_caption.set_text('Carrier input speed' if classic else 'Input A speed' if app.family=='differential' else 'Input speed · stage 1' if app.family=='planetary' and values.get('variant') in ('two_stage','two_stage_double') else 'Sun input speed' if app.family=='wolfrom' else 'Input speed')
  speed.set_tooltip_text('Signed carrier RPM; prescribe the side-speed difference independently in Motion.' if classic else 'Signed input A RPM; set input B independently in Motion.' if app.family=='differential' else 'Signed sun input RPM · −100,000 to +100,000. Positive is counterclockwise viewed from +Z toward XY; reversing input reverses all moving members. Zero stops every member.' if app.family=='wolfrom' else 'Actual input RPM · progressive scale 0–100,000. Also updates calculations and configuration. Use the arrows to adjust.')
 app.motion_syncing=False
