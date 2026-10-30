# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GUI navigation and actions; geometry and kinematics remain in their modules."""
from pathlib import Path
import json
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, Gdk
CATALOG = {'spur': ('Spur gear', 'A single gear: choose the tooth count, module and bore.'), 'helical': ('Helical gear', 'A single gear with an adjustable helix angle.'), 'double': ('Double helical gear', 'Two opposing helices, joined or separated by a groove.'), 'planetary': ('Planetary gearbox', 'Sun, planets and ring gear. One or two reduction stages.'), 'cycloidal': ('Cycloidal reducer', 'Eccentric discs and rollers, with one or two discs.'), 'harmonic': ('Strain wave reducer', 'A flexible gear with prescribed wave deformation and a generated matching ring.'), 'worm': ('Worm and wheel', 'Perpendicular axes with a wheel generated from the selected ZA or ZI screw.'), 'parallel': ('Parallel shaft reducer', 'A gear pair with input and output shafts.'), 'internal': ('Internal gear reducer', 'A pinion inside an internal gear, with fixed axes.')}
ADVANCED = {'pressure', 'backlash', 'profile_shift', 'addendum', 'dedendum', 'clearance', 'assembly_clearance', 'output_clearance', 'profile_tolerance', 'wave_clearance', 'wave_factor'}
CATALOG['differential'] = ('Bevel differential', 'Spherical involute gears: wrist with two inputs or classic carrier input with two side outputs.')

def searchable_dropdown(labels):
    """Filter displayed names while keeping selection indices in the full model."""
    dropdown = Gtk.DropDown.new_from_strings(labels)
    dropdown.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, 'string'))
    dropdown.set_search_match_mode(Gtk.StringFilterMatchMode.SUBSTRING)
    dropdown.set_enable_search(True)
    return dropdown

def _numeric_parts(value):
    import re
    return re.fullmatch(r'([+-]?)(?:(\d+)(?:[.,](\d+))?|[.,](\d+))([eE][+-]?\d+)?', str(value).strip())


def normalized_numeric_text(value, *, low=None, high=None, integer=False):
    """Remove redundant zeros without rounding any explicitly entered digits."""
    from math import isfinite
    original = str(value)
    match = _numeric_parts(original)
    if not match:
        return original
    number = float(original.strip().replace(',', '.'))
    if (not isfinite(number) or low is not None and number < low
            or high is not None and number > high or integer and not number.is_integer()):
        return original
    sign, whole, fraction, leading_fraction, exponent = match.groups()
    whole = (whole or '0').lstrip('0') or '0'
    fraction = (fraction or leading_fraction or '').rstrip('0')
    if whole == '0' and not fraction:
        return '0'
    result = ('-' if sign == '-' else '') + whole + ('.' + fraction if fraction else '')
    if exponent:
        power = exponent[1:]
        negative = power.startswith('-')
        power = power.lstrip('+-').lstrip('0')
        if power:
            result += 'e' + ('-' if negative else '') + power
    return result


def roundtrip_text(value, digits=6):
    """Compact automatic values; retain tiny nonzero values in scientific form."""
    value = float(value)
    result = format(value, f'.{digits}f')
    if value and float(result) == 0:
        result = format(value, f'.{digits}e')
    return normalized_numeric_text(result)


def _track_numeric_entry(widget):
    if getattr(widget, '_numeric_tracking', False):
        return
    widget._numeric_tracking = True
    def edited(entry):
        if not getattr(entry, '_numeric_setting', False):
            entry._numeric_exact = None
            entry._numeric_typed_text = entry.get_text()
    widget.connect('changed', edited)


def numeric_is_automatic(widget):
    """Whether the visible text represents a separately preserved exact value."""
    return (getattr(widget, '_numeric_exact', None) is not None
            and (getattr(widget, '_numeric_setting', False)
                 or widget.get_text() == getattr(widget, '_numeric_display', None)))


def numeric_value(widget):
    """Read the exact automatic value or the complete, unrounded user input."""
    if numeric_is_automatic(widget):
        return widget._numeric_exact
    return float(widget.get_text().strip().replace(',', '.'))


def numeric_snapshot_text(widget):
    """Keep automatic display rounding out of project history and recovery."""
    return repr(widget._numeric_exact) if numeric_is_automatic(widget) else widget.get_text()


def set_numeric_value(widget, value):
    """Display an automatic value while preserving its exact numeric backing."""
    _track_numeric_entry(widget)
    value = float(value)
    typed = getattr(widget, '_numeric_typed_text', None)
    if typed is not None:
        try:
            if float(typed.strip().replace(',', '.')) == value:
                widget._numeric_setting = True
                try:
                    if isinstance(widget, Gtk.SpinButton):
                        widget.set_value(value)
                finally:
                    widget._numeric_setting = False
                return  # Refreshes must not replace a deliberate precise edit.
        except ValueError:
            pass
    shown = roundtrip_text(value)
    widget._numeric_exact, widget._numeric_display = value, shown
    widget._numeric_typed_text = None
    widget._numeric_setting = True
    try:
        if isinstance(widget, Gtk.SpinButton):
            widget.set_value(value)
        if widget.get_text() != shown:
            widget.set_text(shown)
    finally:
        widget._numeric_setting = False


def _set_explicit_numeric_text(widget, compact):
    # GTK emits an empty changed event before the replacement. Observers must
    # still see the same numeric value during this purely cosmetic rewrite.
    widget._numeric_exact = float(compact.replace(',', '.'))
    widget._numeric_display = compact
    widget._numeric_setting = True
    try:
        widget.set_text(compact)
    finally:
        widget._numeric_setting = False
        widget._numeric_exact = None
        widget._numeric_typed_text = compact


def _normalize_numeric_entry(widget, *, low=None, high=None, integer=False):
    if numeric_is_automatic(widget):
        return
    original = widget.get_text()
    compact = normalized_numeric_text(original, low=low, high=high, integer=integer)
    if compact != original:
        _set_explicit_numeric_text(widget, compact)


def bind_numeric_entry(widget, *, low=None, high=None, integer=False):
    """Normalize a scalar entry only on Enter or focus loss, never while typing."""
    _track_numeric_entry(widget)
    def commit(*args):
        _normalize_numeric_entry(widget, low=low, high=high, integer=integer)
    widget.connect('activate', commit)
    focus = Gtk.EventControllerFocus()
    focus.connect('leave', commit)
    widget.add_controller(focus)


def bind_numeric_spin(widget, *, low=None, high=None, integer=False, app=None):
    """Preserve exact typed and automatic values across GTK's native updates."""
    from math import isfinite
    _track_numeric_entry(widget)
    adjustment = widget.get_adjustment()
    low = adjustment.get_lower() if low is None else low
    high = adjustment.get_upper() if high is None else high
    widget.set_update_policy(Gtk.SpinButtonUpdatePolicy.IF_VALID)
    last = [widget.get_value()]
    committing = [False]
    def output(spin):
        current = spin.get_value()
        previous, last[0] = last[0], current
        if (not committing[0] and not getattr(spin, '_numeric_setting', False)
                and not (app and app.building) and current != previous):
            set_numeric_value(spin, current)
        return True
    def input_value(spin, unused):
        # GTK's default parser rounds to set_digits(). Parse ourselves and reject
        # that native conversion, leaving invalid/incomplete text untouched.
        original = spin.get_text()
        compact = normalized_numeric_text(original, low=low, high=high, integer=integer)
        try:
            number = numeric_value(spin)
            complete = _numeric_parts(original) is not None
            if (not complete or not isfinite(number) or low is not None and number < low
                    or high is not None and number > high or integer and not number.is_integer()):
                return Gtk.INPUT_ERROR
        except ValueError:
            return Gtk.INPUT_ERROR
        committing[0] = True
        try:
            spin.set_value(number)
            if not numeric_is_automatic(spin) and compact != original:
                _set_explicit_numeric_text(spin, compact)
        finally:
            committing[0] = False
        return Gtk.INPUT_ERROR
    widget.connect('input', input_value)
    widget.connect('output', output)
    widget.connect('activate', lambda spin: spin.update())


def text(value, style='muted'):
    widget = Gtk.Label(label=value, xalign=0, wrap=True, css_classes=[style])
    widget.set_max_width_chars(40)
    return widget

def install_sections(app, left):
    app.page_buttons = {}
    nav = Gtk.Box(spacing=2, css_classes=['page-nav'])
    app.section_nav = nav
    left.append(nav)
    app.fields = Gtk.Stack(vexpand=True)
    app.fields.set_hhomogeneous(False)
    app.fields.set_vhomogeneous(False)
    app.pages, app.page_scrolls = {}, {}
    for key, title in [('geometry','Dimensions'), ('motion','Motion'), ('assembly','Assembly')]:
        button = Gtk.ToggleButton(label=title, hexpand=True)
        if app.page_buttons:
            button.set_group(next(iter(app.page_buttons.values())))
        button.connect('clicked', lambda _, key=key: show_page(app, key))
        nav.append(button)
        app.page_buttons[key] = button
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=['parameter-scroll'])
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(body)
        app.fields.add_named(scroll, key)
        app.pages[key], app.page_scrolls[key] = body, scroll
        # A pending layout restoration must yield to a real user gesture.
        events = Gtk.EventControllerLegacy()
        events.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def user_navigation(controller, event):
            if event is None:
                return False
            if event.get_event_type() in (Gdk.EventType.SCROLL, Gdk.EventType.BUTTON_PRESS,
                                         Gdk.EventType.TOUCH_BEGIN, Gdk.EventType.KEY_PRESS):
                app.panel_revision = getattr(app,'panel_revision',0) + 1
                app._scroll_restore_positions = None
            return False
        events.connect('event', user_navigation)
        scroll.add_controller(events)
    app.parameter_error = text('', 'error')
    app.parameter_error.set_margin_start(18)
    app.parameter_error.set_margin_end(18)
    app.parameter_error.set_visible(False)
    left.append(app.parameter_error)
    left.append(app.fields)
    app.sections = {}
    app.io_frame = Gtk.Expander(label='Drive connections', expanded=True)
    app.io_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    for key, title, page, expanded in [
        ('geometry','Main geometry','geometry',True),
        ('io','Drive connections','motion',True),
        ('loads','Nominal operating loads','motion',False),
        ('bearings','Bearings & fits','assembly',True),
        ('hardware','Standard hardware','assembly',False),
        ('housing','Housing & flanges','assembly',True),
    ]:
        section = (app.io_frame if key=='io' else Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                   if key=='geometry' else Gtk.Expander(label=title, expanded=expanded))
        body = app.io_box if key=='io' else Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        if key=='geometry':
            section.append(body)
        else:
            section.set_child(body)
        app.pages[page].append(section)
        app.sections[key] = (section, body)
    app.eccentric_design_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    app.eccentric_section = Gtk.Expander(label='Eccentric shaft construction')
    app.eccentric_section.set_child(app.eccentric_design_box)
    app.pages['assembly'].append(app.eccentric_section)
    app.motion_help = text('Set speed and playback in the motion bar beside the preview.')
    app.pages['motion'].append(app.motion_help)
    app.load_help = text('Nominal torque and forces use these operating assumptions. They are not allowable loads.')
    app.sections['loads'][1].append(app.load_help)
    app.mount_help = text('Linked dimensions are read-only. Change the selected bearing or fit to edit their source.')
    app.pages['assembly'].append(app.mount_help)
    app.page_buttons['geometry'].set_active(True)
    app.fields.set_visible_child_name('geometry')


def install_cad(app):
    app.cad_menu = Gtk.MenuButton(label='CAD integrations')
    popup = Gtk.Popover()
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    body.set_size_request(315, -1)
    body.append(text('SolidCraft', 'step-title'))
    app.connection_label = text('○ Disconnected')
    body.append(app.connection_label)
    app.connect_btn = Gtk.Button(label='Connect SolidCraft')
    app.connect_btn.connect('clicked', lambda _: app.background(app.connect_cad))
    body.append(app.connect_btn)
    app.send_btn = Gtk.Button(label='Create in SolidCraft')
    app.send_btn.connect('clicked', lambda _: (popup.popdown(), app.send()))
    app.send_btn.set_tooltip_text('Add a new group to the active CAD document. Sending again creates another group.')
    body.append(app.send_btn)
    app.cad_hint = text('Connect or launch SolidCraft, then add a new group to the active document.')
    body.append(app.cad_hint)
    body.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
    body.append(text('Autodesk Fusion', 'step-title'))
    app.fusion_connection_label = text('○ Disconnected')
    body.append(app.fusion_connection_label)
    app.fusion_install_btn = Gtk.Button(label='Install Fusion add-in')
    app.fusion_install_btn.connect('clicked', lambda _: app.background(app.install_fusion_addin))
    body.append(app.fusion_install_btn)
    app.fusion_connect_btn = Gtk.Button(label='Connect / check Fusion')
    app.fusion_connect_btn.connect('clicked', lambda _: app.background(app.connect_fusion))
    body.append(app.fusion_connect_btn)
    app.fusion_send_btn = Gtk.Button(label='Create in Fusion')
    app.fusion_send_btn.connect('clicked', lambda _: (popup.popdown(), app.send_fusion()))
    app.fusion_send_btn.set_tooltip_text('Import STEP solids into a new group in the active Fusion document. Each send creates another group.')
    body.append(app.fusion_send_btn)
    app.fusion_hint = text('Install the add-in, then in Fusion open Utilities > Scripts and Add-Ins > Add-Ins and run RatioLabBridge. Transfers STEP solids with RatioLab parameters as metadata; Fusion timeline features are not regenerated.')
    body.append(app.fusion_hint)
    popup.set_child(body)
    app.cad_menu.set_popover(popup)


def preserve_scroll(app):
    """Keep positions through GTK's measure/allocate and expander animations."""
    current = {k: w.get_vadjustment().get_value() for k,w in app.page_scrolls.items()}
    pending = getattr(app, '_scroll_restore_positions', None)
    positions = dict(pending or current)
    if pending:
        for key,value in current.items():
            adj = app.page_scrolls[key].get_vadjustment()
            limit = max(adj.get_lower(),adj.get_upper()-adj.get_page_size())
            # Positive movement beyond the old request cannot be a clamp.
            # Preserve a new position inside the range too, but retain an old
            # request while GTK temporarily clamps it at a smaller boundary.
            if value > 0 and (value > positions[key] or value < limit-1):
                positions[key] = value
    app._scroll_restore_positions = positions
    app.panel_revision = getattr(app, 'panel_revision', 0) + 1
    revision = app.panel_revision
    frames = 0
    def restore(widget, clock):
        nonlocal frames
        if revision != app.panel_revision:
            return False
        frames += 1
        for key, value in positions.items():
            adj = app.page_scrolls[key].get_vadjustment()
            adj.set_value(min(value, max(adj.get_lower(), adj.get_upper()-adj.get_page_size())))
        # Tick callbacks precede layout. Retain the request across subsequent
        # allocations, including the expander's short reveal transition.
        if frames >= 12:
            app._scroll_restore_positions = None
            return False
        return True
    app.win.add_tick_callback(restore)


def geometry_groups(app, specs):
    """Assign geometric fields to stable, family-specific groups."""
    from geometry import INTEGER
    from parameter_help_ui import controller
    help_controller = controller(app)
    help_controller.reset()
    import re
    groups = {}
    def group(key, title):
        if key not in groups:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9, css_classes=['parameter-group'])
            box.append(text(title, 'parameter-heading'))
            app.sections['geometry'][1].append(box)
            groups[key] = box
        return groups[key]
    # Render groups in a useful order, independent of the generator's spec order.
    main_order = ('teeth','side_teeth','output_teeth','sun','planet','planets','sun2','planet2','pinion','wheel',
                  'pins','radius','pin_radius','eccentric','module','width','spiral_angle','width2','disc_gap','helix','gap')
    order = {key: i for i, key in enumerate(main_order)}
    specs = sorted(specs, key=lambda s: order.get(s[0], len(order)))
    app.field_feedback, app.linked_notes, app.field_containers = {}, {}, {}
    app.geometry_derived = {}
    app.geometry_group_boxes = groups
    load_box = app.sections['loads'][1]
    app.load_help = text('Based on operating inputs and assumed efficiency. These are not allowable loads.')
    load_box.append(app.load_help)
    inactive=set()
    if app.family=='differential':
        from differential_wrist import inactive_fields
        inactive=inactive_fields(dict(app.field_values,**app.option_values))
    for key, label, default, low, high, step in specs:
        if key in inactive or key=='input_rpm' or app.family=='differential' and key=='spiral_hand' or (key.startswith('print_') and app.option_values.get('eccentric_design')!='fdm_bolted'):
            continue
        page = 'geometry'
        if key in ('input_b_rpm','output_difference_rpm'):
            target, page = app.io_box, 'motion'
        elif key in ('input_torque','efficiency','pull_force'):
            target, page = load_box, 'motion'
        elif key in ('shoulder','seat_allowance','shaft_allowance'):
            target, page = app.sections['bearings'][1], 'assembly'
        elif key in ('plate','housing_wall','rim','stage_gap','carrier_bolt_diameter','spider_pin_diameter','spider_clearance') or key.startswith('print_'):
            target, page = app.sections['housing'][1], 'assembly'
        elif key in ADVANCED:
            target = app.advanced_fields
        elif key in ('bore','output_bore','wheel_bore','input_shaft','output_shaft','shaft_extension','journal_length','journal_diameter','output_extension','passage_diameter'):
            target = group('shafts', 'Shafts & bores')
        elif key in ('output_count','output_radius','output_pin','flange_radius','bolt_count','bolt_diameter'):
            target = group('output', 'Output connection')
        else:
            target = group('main', 'Disc & rollers' if app.family=='cycloidal' else 'Main geometry')
        unit_match = re.search(r'\[([^]]+)\]', label)
        caption = re.sub(r'\s*\[[^]]+\]', '', label).split(' (')[0]
        unit = unit_match.group(1) if unit_match else ''
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row = Gtk.Box(spacing=7)
        name = Gtk.Label(label=caption, xalign=0, wrap=True, hexpand=True, css_classes=['field-label'])
        name.set_max_width_chars(20)
        row.append(name)
        spin = Gtk.SpinButton.new_with_range(low, high, step)
        value = app.field_values.get(key, default)
        from decimal import Decimal
        decimals = max(0, -Decimal(str(value)).as_tuple().exponent)
        spin.set_digits(0 if key in INTEGER else min(12, max(2, decimals)))
        spin.set_numeric(False)
        spin.set_enable_undo(False)
        spin.set_value(value)
        spin.set_width_chars(6)
        spin.set_max_width_chars(8)
        spin.set_alignment(1)
        spin.set_tooltip_text(label)
        bind_numeric_spin(spin, low=low, high=high, integer=key in INTEGER, app=app)
        set_numeric_value(spin, value)
        spin.connect('value-changed', app.changed)
        spin.connect('changed', app.changed)
        name.set_mnemonic_widget(spin)
        row.append(spin)
        units = Gtk.Label(label=unit, xalign=0, css_classes=['muted'])
        units.set_width_chars(3)
        row.append(units)
        help_controller.bind(name, spin, key, row)
        container.append(row)
        feedback = text('', 'error')
        feedback.set_visible(False)
        container.append(feedback)
        app.field_feedback[key] = feedback
        if key in ('bore','input_shaft','output_shaft') or app.family=='differential' and key=='output_teeth':
            linked = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            note = text('')
            linked.append(note)
            origin = Gtk.Button(label='Change source…', css_classes=['flat'])
            origin.connect('clicked', lambda _, key=key: reveal_source(app, key))
            linked.append(origin)
            linked.set_visible(False)
            container.append(linked)
            app.linked_notes[key] = (linked, note)
        target.append(container)
        if key in ('planets', 'pins'):
            derived = Gtk.Box(spacing=8)
            title = 'Ring teeth · derived' if key=='planets' else 'Disc lobes · derived'
            derived.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=['muted']))
            value_label = Gtk.Label(selectable=True, xalign=1, css_classes=['derived-output'])
            value_label.set_tooltip_text('Calculated from the current tooth counts; edit the source geometry above.')
            derived.append(value_label)
            target.append(derived)
            app.geometry_derived[key] = value_label
        app.inputs[key], app.input_labels[key], app.input_pages[key] = spin, label, page
        app.field_containers[key] = container
        if app.family=='differential' and key=='output_teeth' and app.option_values.get('ratio_mode','custom')!='custom':spin.set_sensitive(False)
    for key in ('main', 'output', 'shafts'):
        if key in groups:
            parent = app.sections['geometry'][1]
            parent.remove(groups[key])
            parent.append(groups[key])
    if app.advanced_fields.get_first_child():
        app.sections['geometry'][1].append(app.advanced_expander)
    app.sections['housing'][0].set_visible(app.sections['housing'][1].get_first_child() is not None)
    app.sections['loads'][0].set_visible(any(k in app.inputs for k in ('input_torque','efficiency','pull_force')))


def reveal_source(app, key):
    if app.family=='differential' and key=='output_teeth':
        show_page(app,'geometry')
        app.differential_selectors['ratio_mode'].grab_focus()
        return
    show_page(app, 'assembly')
    printed = app.option_values.get('eccentric_design')=='fdm_bolted'
    section = app.eccentric_section if printed else app.sections['bearings'][0]
    section.set_expanded(True)
    section.grab_focus()


def show_parameter_error(app, message):
    """Use a field when the generator identifies one; leave shared errors explicit."""
    key = getattr(app, 'error_field', None)
    if key not in app.inputs and key!='input_rpm':
        lower = message.lower()
        if 'equally spaced' in lower:
            key = 'sun'
            message += ' Choose sun / planet teeth compatible with the selected planet count.'
        elif 'eccentric' in lower or 'eccessiva' in lower:
            key = 'eccentric'
            if 'eccessiva' in lower:
                message = ('Eccentricity is too large: eccentricity × roller count / pitch radius '
                           'must be below 0.90. Reduce eccentricity or increase the pitch radius.')
        else:
            key = next((k for k, label in app.input_labels.items()
                        if lower.startswith(label.lower()+':') or lower.startswith(k.lower()+':')), None)
    app.error_field = key
    for field, feedback in app.field_feedback.items():
        active = field==key
        feedback.set_visible(active)
        if active:
            feedback.set_text(message)
            app.inputs[field].add_css_class('field-error')
        else:
            app.inputs[field].remove_css_class('field-error')
    app.parameter_error.set_text(message)
    app.parameter_error.set_visible(key not in app.inputs and key!='input_rpm')
    app.error_reveal.set_visible(key in app.inputs or key=='input_rpm')

def show_page(app, key):
    app.fields.set_visible_child_name(key)
    app.page_buttons[key].set_active(True)

def reveal_error(app):
    key = getattr(app, 'error_field', None)
    if key=='input_rpm':
        app.motion_speed_text.grab_focus()
        return
    if key not in app.inputs:
        return
    show_page(app, app.input_pages.get(key, 'geometry'))
    if key in ADVANCED:
        app.advanced_expander.set_expanded(True)
    page = app.input_pages.get(key, 'geometry')
    if page == 'assembly':
        for section, _ in app.sections.values():
            if section.is_ancestor(app.pages['assembly']):
                section.set_expanded(True)
    app.inputs[key].grab_focus()

def update_family(app):
    from parameter_help_ui import bind_options
    bind_options(app)
    description = CATALOG[app.family][1]
    app.selector.set_tooltip_text(description)
    # Construction notices are decided from the generated model below.
    app.family_hint.set_text('')
    app.family_hint.set_visible(False)
    app.eccentric_section.set_visible(app.family=='cycloidal')
    from catalog import SUPPORTED
    printed=app.family=='cycloidal' and app.option_values.get('eccentric_design')=='fdm_bolted'
    enabled=app.family in SUPPORTED and not printed
    message='Linked dimensions update automatically.' if enabled else 'Automatic catalog unavailable for this construction. See the disabled controls and reasons below; adjust the dedicated geometry and interfaces.'
    if app.family=='internal':message='Linked catalog dimensions cover the pinion shaft only. The ring output needs a dedicated annular support.'
    app.mount_help.set_text(message)
    if app.family == 'differential':
        app.motion_help.set_text('Direct carrier input drives two side outputs. B−A is a prescribed speed boundary, not a second motor or load-based speed split.' if app.option_values.get('configuration')=='classic' else 'External belts, pulleys and motors are added later in your CAD. The output has two motions; no single reduction ratio or output torque is calculated.')
    elif not app.io_frame.get_visible():
        app.motion_help.set_text('This is a single gear. Use Start motion in the motion bar to see it rotate and set speed and torque.')
    else:
        app.motion_help.set_text('Connect the motor to the input and the load to the output.')


def construction_notice(design):
    """Keep unverified construction visible without branding whole families as studies."""
    if design.family == 'worm':
        verified = design.analysis.get('wheel_geometry', {}).get('conjugate') is True
    elif design.family == 'differential':
        verified = design.analysis.get('bevel', {}).get('conjugacy_verified') is True
    elif design.family == 'harmonic':
        verified = design.analysis.get('wave_mapping', {}).get('conjugate') is True
    else:
        return ''
    return '' if verified else 'Tooth conjugacy has not been verified for this construction.'


def update_geometry_warning(app, design):
    from engineering import geometry_warnings

    warnings = geometry_warnings(design)
    notice = construction_notice(design)
    message = ('Geometry warning: ' + warnings[0] + ' See the calculation report.'
               if warnings else notice)
    app.study.set_text(message)
    app.study.set_visible(bool(message))
    if hasattr(app, 'family_hint'):
        app.family_hint.set_text(notice)
        app.family_hint.set_visible(bool(notice))
    if hasattr(app, 'warning_bar'):
        app.warning_bar.remove_css_class('invalid')
        app.warning_bar.set_visible(bool(message))
        app.warning_details.set_visible(True)
        app.warning_details.set_tooltip_text(message)
        app.study.set_tooltip_text(message)


def action(menu, title, description, callback):
    b = Gtk.Button()
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
    body.append(text(title, 'action-title'))
    body.append(text(description))
    b.set_child(body)
    b.connect('clicked', callback)
    menu.append(b)
    return b

def install_exports(app):
    app.export_menu = Gtk.MenuButton(label='Export…')
    app.export_menu.add_css_class('primary')
    popup = Gtk.Popover()
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    for setter in (body.set_margin_start, body.set_margin_end, body.set_margin_top, body.set_margin_bottom):
        setter(12)
    popup.set_child(body)
    scroll = Gtk.ScrolledWindow(max_content_height=620, propagate_natural_height=True)
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    popup.set_child(scroll)
    scroll.set_child(body)
    app.export_menu.set_popover(popup)
    body.append(text('Export scope', 'step-title'))
    app.export_scope = Gtk.DropDown.new_from_strings(['Complete assembly', 'Selected components'])
    body.append(app.export_scope)
    app.export_count = text('')
    body.append(app.export_count)
    body.append(text('Nominal assembly coordinates · visibility does not change scope.'))
    export_actions = []
    for kind, title, description, fn in [
        ('step', 'STEP for CAD', 'Combined model and component solids · mm.', app.export_step),
        ('stl', 'STL for 3D printing', 'Combined model and component meshes · mm.', app.export_stl),
        ('profiles', 'SVG / DXF profiles', 'Planar contours · deformed/helical parts are sections.', app.export_profiles),
        ('package', 'Export package', 'Geometry, preview, parameters, BOM and calculations.', app.export),
        ('bom', 'BOM and calculations', 'TXT, CSV and JSON · nominal source calculations.', app.export_bom)]:
        def run(_, kind=kind, fn=fn):
            popup.popdown()
            if app.export_scope.get_selected() == 1:
                app.components.export(kind)
            else:
                fn()
        b = action(body, title, description, run)
        export_actions.append((kind, b))
        app.file_buttons.append(b)
    def update_scope(*_):
        c = getattr(app, 'components', None)
        selected = c and c.current() and c.selected
        count = len(selected) if selected else 0
        total = len(app.design.parts) if app.design else 0
        subset = app.export_scope.get_selected() == 1
        app.export_count.set_text(f'{count} selected / {total} components · BOM included with geometry exports' if subset else f'All {total} components · complete assembly')
        for kind, button in export_actions:
            enabled = bool(app.design and not app.busy and (not subset or count and kind != 'bom'))
            button.set_sensitive(enabled)
            button.set_tooltip_text('Selected BOM is included in each selected geometry export or package.' if subset and kind=='bom'
                                    else 'Select current components in Tools → Components.' if subset and not count else None)
    app.update_export_scope = update_scope
    app.export_scope.connect('notify::selected', update_scope)
    popup.connect('show', update_scope)
    body.append(Gtk.Separator())
    body.append(text('Destination folder', 'field-label'))
    app.output_label = text(str(app.output_dir))
    body.append(app.output_label)
    folders = Gtk.Box(spacing=6)
    body.append(folders)
    choose = Gtk.Button(label='Change folder…')
    choose.connect('clicked', lambda _: choose_output(app))
    folders.append(choose)
    app.file_buttons.append(choose)
    open_button = Gtk.Button(label='Open folder')
    open_button.connect('clicked', lambda _: open_output(app))
    folders.append(open_button)
    app.file_buttons.append(app.export_menu)

def choose_output(app):
    dialog = Gtk.FileChooserNative(title='Where should exported files be saved?', transient_for=app.win, action=Gtk.FileChooserAction.SELECT_FOLDER, accept_label='Use this folder', cancel_label='Cancel')
    if app.output_dir.exists():
        dialog.set_current_folder(Gio.File.new_for_path(str(app.output_dir)))

    def response(d, r):
        if r == Gtk.ResponseType.ACCEPT:
            selected=d.get_file()
            local_path=selected.get_path() if selected else None
            if not local_path:
                app.status_text('No local destination folder selected.')
                d.destroy()
                return
            folder = Path(local_path)
            app.output_dir = folder
            app.output_label.set_text(str(folder))
            try:
                save_preference(app, output_dir=str(folder))
            except OSError as e:
                app.status_text(f'Folder set for this session: {folder}. Preference could not be saved: {e}')
            else:
                app.status_text(f'Future exports will be saved in {folder}')
        d.destroy()
    dialog.connect('response', response)
    dialog.show()

def open_output(app):
    try:
        app.output_dir.mkdir(parents=True, exist_ok=True)
        from external_programs import open_folder
        open_folder(app.output_dir, app.win.get_display().get_app_launch_context())
    except Exception as e:
        app.status_text(f'Could not open the folder: {e}')

def open_link(app, uri):
    try:
        from external_programs import launch_uri
        launch_uri(uri, app.win.get_display().get_app_launch_context())
    except Exception as e:
        app.status_text(f'Could not open the link: {e}')
    return True  # Suppress Gtk.LinkButton's default unsanitized launch handler.

def install_shortcuts(app):
    for name, accelerator, callback in [('new', '<Control>n', app.new_project), ('open', '<Control>o', app.load_dialog), ('save', '<Control>s', app.save_dialog), ('save-as', '<Control><Shift>s', app.save_as_dialog), ('undo', '<Control>z', app.undo_project), ('redo', '<Control><Shift>z', app.redo_project), ('close', '<Control>w', app.close_project), ('export', '<Control>e', lambda _: app.export_menu.popup())]:
        action = Gio.SimpleAction.new(name, None)
        action.connect('activate', lambda _, parameter, fn=callback: fn(None) if not app.busy else None)
        app.add_action(action)
        app.set_accels_for_action('app.' + name, [accelerator])
    # Capture history shortcuts before GtkEntry's local text editor can consume
    # Ctrl+Z. The document restores text, options and family in one operation.
    controller = Gtk.ShortcutController()
    controller.set_scope(Gtk.ShortcutScope.GLOBAL)
    controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    app.history_shortcuts = []
    for trigger, name in [('<Control>z', 'undo'), ('<Control><Shift>z', 'redo'), ('<Control>y', 'redo')]:
        shortcut = Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(trigger), Gtk.NamedAction.new('app.'+name))
        controller.add_shortcut(shortcut)
        app.history_shortcuts.append(shortcut)
    app.win.add_controller(controller)

def show_report(app, title, content):
    """Browsable report with text search, selection and copying."""
    win = Gtk.Window(title=title, transient_for=app.win, application=app)
    win.set_default_size(850, 650)
    win.add_css_class('reducers')
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for setter in (body.set_margin_start, body.set_margin_end, body.set_margin_top, body.set_margin_bottom):
        setter(14)
    win.set_child(body)
    bar = Gtk.Box(spacing=8)
    body.append(bar)
    search = Gtk.SearchEntry()
    search.set_placeholder_text('Search this document…')
    search.set_hexpand(True)
    bar.append(search)
    view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    view.set_left_margin(12)
    view.set_right_margin(12)
    view.set_top_margin(12)
    view.set_bottom_margin(12)
    buffer = view.get_buffer()
    buffer.set_text(content)
    status = text('')
    body.append(status)
    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_child(view)
    body.append(scroll)

    def find(direction=1, first=False):
        query = search.get_text()
        if not query:
            status.set_text('')
            buffer.select_range(buffer.get_start_iter(), buffer.get_start_iter())
            return
        selection = buffer.get_selection_bounds()
        start = buffer.get_start_iter() if first else selection[1 if direction > 0 else 0] if selection else buffer.get_start_iter()
        flags = Gtk.TextSearchFlags.CASE_INSENSITIVE
        found = start.forward_search(query, flags, None) if direction > 0 else start.backward_search(query, flags, None)
        if not found:
            start = buffer.get_start_iter() if direction > 0 else buffer.get_end_iter()
            found = start.forward_search(query, flags, None) if direction > 0 else start.backward_search(query, flags, None)
        if found:
            buffer.select_range(*found)
            view.scroll_to_iter(found[0], 0.15, False, 0, 0)
            status.set_text('Match selected')
        else:
            buffer.select_range(buffer.get_start_iter(), buffer.get_start_iter())
            status.set_text('No matches')
    for title, direction in [('Previous', -1), ('Next', 1)]:
        button = Gtk.Button(label=title)
        button.connect('clicked', lambda _, d=direction: find(d))
        bar.append(button)
    copy = Gtk.Button(label='Copy all')
    copy.connect('clicked', lambda _: (win.get_clipboard().set(content), status.set_text('Text copied')))
    bar.append(copy)
    search.connect('search-changed', lambda _: find(first=True))
    search.connect('activate', lambda _: find())
    win.report_search = search
    win.report_view = view
    win.report_status = status
    win.present()
    return win


def save_preference(app, **changes):
    from app_paths import save_preferences
    save_preferences(legacy_root=app.BASE, **changes)
