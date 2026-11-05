# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GUI navigation and actions; geometry and kinematics remain in their modules."""
from parallel_multistage import VARIANTS as PARALLEL_MULTISTAGE_VARIANTS
from pathlib import Path
import json
import weakref
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, Gdk, Pango, GLib
CATALOG = {'spur': ('Spur gear', 'A single gear: choose the tooth count, module and bore.'), 'helical': ('Helical gear', 'A single gear with an adjustable helix angle.'), 'double': ('Double helical gear', 'Two opposing helices, joined or separated by a groove.'), 'planetary': ('Planetary gearbox', 'Sun, planets and ring gear. One or two reduction stages.'), 'cycloidal': ('Cycloidal reducer', 'Eccentric discs and rollers, with one or two discs.'), 'harmonic': ('Strain wave reducer', 'A flexible gear with prescribed wave deformation and a generated matching ring.'), 'worm': ('Worm and wheel', 'Perpendicular axes with a wheel generated from the selected ZA or ZI screw.'), 'parallel': ('Parallel shaft reducer', 'One, two or three reduction stages with parallel shafts.'), 'internal': ('Internal gear reducer', 'A pinion inside an internal gear, with fixed axes.')}
ADVANCED = {'pressure', 'backlash', 'profile_shift', 'addendum', 'dedendum', 'clearance', 'assembly_clearance', 'face_addendum', 'output_clearance', 'profile_tolerance', 'wave_clearance', 'wave_factor'}
CATALOG['differential'] = ('Bevel differential', 'Spherical involute gears: wrist with two inputs or classic carrier input with two side outputs.')
CATALOG['wolfrom'] = ('Wolfrom / 3K reducer', 'Sun input, first ring fixed, second ring output. Two rigidly joined planet rims.')
CATALOG['bevel'] = ('Bevel gear pair', 'Straight, spiral or circular Zerol-style tooth traces on 90° shafts. Custom spherical involute flanks, independent bores and reversible ports.')
CATALOG['rack'] = ('Rack and pinion','Finite linear rack with spur, helical or double-helical teeth and a matching pinion. Shared motion and export geometry.')
CATALOG['face'] = ('Face gear pair','Generated face wheel with 90° shaft directions and adjustable offset. Spur, helical or joined/separated double-helical pinion.')
CATALOG['hypoid'] = ('Hypoid gear pair', 'Offset 90° shafts with a pinion generated from a custom spiral master wheel. Supported offset up to 6% of reference cone distance; geometry limits are checked.')

def searchable_dropdown(labels):
    """Filter displayed names while keeping selection indices in the full model."""
    dropdown = choice_dropdown(labels)
    dropdown.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, 'string'))
    dropdown.set_search_match_mode(Gtk.StringFilterMatchMode.SUBSTRING)
    dropdown.set_enable_search(True)
    return dropdown

def choice_dropdown(labels):
    """Create a native selection control with the shared plain-list presentation."""
    return compact_dropdown(Gtk.DropDown.new_from_strings(labels))

def _descendants(widget):
    child = widget.get_first_child()
    while child:
        yield child
        yield from _descendants(child)
        child = child.get_next_sibling()

def _place_choice_popup(dropdown, popup):
    if not dropdown or not popup or not popup.get_mapped():
        return False
    root = dropdown.get_root()
    if root is None:
        return False
    ok, bounds = dropdown.compute_bounds(root)
    if not ok:
        return False
    # Keep GTK's model, search and keyboard navigation. Only constrain the
    # native list and its anchor, instead of replacing it with a second model.
    available = max(32, int(root.get_height() - bounds.get_y() - bounds.get_height() - 18))
    for child in _descendants(popup):
        if isinstance(child, Gtk.ScrolledWindow):
            child.set_min_content_height(0)
            child.set_max_content_height(max(32, min(320, available - (42 if dropdown.get_enable_search() else 0))))
            child.set_propagate_natural_height(True)
    popup.set_position(Gtk.PositionType.BOTTOM)
    popup.set_has_arrow(False)
    popup.set_offset(0, 5)
    rect = Gdk.Rectangle()
    rect.width, rect.height = dropdown.get_width(), dropdown.get_height()
    popup.set_pointing_to(rect)
    popup.present()
    return False

def _install_choice_popup(dropdown):
    control = weakref.ref(dropdown)
    for popup in _descendants(dropdown):
        if not isinstance(popup, Gtk.Popover):
            continue
        popup.add_css_class('choice-popover')
        popup.set_position(Gtk.PositionType.BOTTOM)
        popup.set_has_arrow(False)
        popup._choice_idle = 0
        def place(popover):
            popover._choice_idle = 0
            return _place_choice_popup(control(), popover)
        def mapped(popover, place=place):
            if not popover._choice_idle:
                popover._choice_idle = GLib.idle_add(place, popover)
        def unmapped(popover):
            if popover._choice_idle:
                GLib.source_remove(popover._choice_idle)
                popover._choice_idle = 0
        popup.connect('map', mapped)
        popup.connect('unmap', unmapped)

def compact_dropdown(dropdown):
    """Keep full choices in the popup while fitting the selected sidebar value."""
    if getattr(dropdown, '_plain_choice', False):
        return dropdown
    dropdown._plain_choice = True
    factory = Gtk.SignalListItemFactory()
    def setup(_, item):
        item.set_child(Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                 max_width_chars=20, width_chars=1))
    factory.connect('setup', setup)
    factory.connect('bind', lambda _, item: item.get_child().set_text(item.get_item().get_string()))
    dropdown.set_factory(factory)
    listing = Gtk.SignalListItemFactory()
    def setup_choice(_, item):
        row = Gtk.Box(spacing=8, css_classes=['choice-row'])
        label = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                          max_width_chars=32, width_chars=1, hexpand=True)
        tick = Gtk.Label(label='✓', width_chars=1, css_classes=['choice-tick'])
        row.append(label); row.append(tick)
        item.set_child(row)
    listing.connect('setup', setup_choice)
    listing.connect('bind', lambda _, item: item.get_child().get_first_child().set_text(item.get_item().get_string()))
    dropdown.set_list_factory(listing)
    dropdown.set_hexpand(True)
    _install_choice_popup(dropdown)
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
    app.fields = Gtk.Stack(vexpand=True)
    app.fields.set_hhomogeneous(False)
    app.fields.set_vhomogeneous(False)
    app.pages, app.page_scrolls = {}, {}
    for key, title in [('geometry','Dimensions'), ('motion','Motion'), ('assembly','Assembly')]:
        button = Gtk.ToggleButton(label=title, hexpand=True)
        if key=='geometry':button.add_css_class('dimensions-tab')
        if key=='assembly':button.add_css_class('assembly-tab')
        if app.page_buttons:
            button.set_group(next(iter(app.page_buttons.values())))
        button.connect('clicked', lambda _, key=key: show_page(app, key))
        nav.append(button)
        button.get_child().set_wrap(True)
        button.get_child().set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        button.get_child().set_width_chars(1)
        app.page_buttons[key] = button
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=['parameter-scroll']+(['motion-sidebar'] if key=='motion' else []))
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
    left.append(nav)
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
            section.get_label_widget().set_wrap(True)
            if page=='motion':section.get_label_widget().add_css_class('motion-section-title')
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
    app.active_cad = None
    app.fusion_has_document = False
    app.cad_split = Gtk.Box(css_classes=['linked', 'cad-split'])
    app.cad_action = Gtk.Button(label='CAD Connections')
    app.cad_menu = Gtk.MenuButton(icon_name='pan-down-symbolic')
    app.cad_menu.set_tooltip_text('Choose and connect a CAD')
    app.cad_split.append(app.cad_action)
    app.cad_split.append(app.cad_menu)
    popup = Gtk.Popover(css_classes=['cad-popover'])
    popup.set_has_arrow(False)
    popup.set_halign(Gtk.Align.END)
    popup.set_offset(0,8)
    app.cad_popup_open=False
    stack=Gtk.Stack(hhomogeneous=False,vhomogeneous=False)
    stack.set_size_request(266,-1)
    app.cad_stack=stack
    card_view=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        vscrollbar_policy=Gtk.PolicyType.NEVER,min_content_width=266,max_content_width=266,
        propagate_natural_width=True,propagate_natural_height=True)
    app.cad_card_view=card_view
    card_view.set_child(stack)
    popup.set_child(card_view)
    compact=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0)
    compact.append(Gtk.Label(label='CAD Connections',xalign=0,css_classes=['cad-menu-title']))
    app.cad_compact_buttons={};app.cad_compact_status={}
    app.cad_pending_connection=None
    app.cad_connection_rows=[]
    for key,name in (('fusion','Autodesk Fusion'),('solidcraft','SolidCraft')):
        row=Gtk.Box(spacing=9,css_classes=['cad-connection-row'])
        info=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,hexpand=True)
        info.append(Gtk.Label(label=name,xalign=0,wrap=True,width_chars=1,max_width_chars=20,css_classes=['cad-connection-name']))
        status=Gtk.Label(label='Not connected',xalign=0,wrap=True,width_chars=1,max_width_chars=24,css_classes=['cad-connection-status'])
        info.append(status);row.append(info)
        connect=Gtk.Button(label='Connect',valign=Gtk.Align.CENTER)
        connect.update_property([Gtk.AccessibleProperty.LABEL],['Connect '+name])
        connect.connect('clicked',lambda _,key=key:_cad_compact_connect(app,key))
        row.append(connect);compact.append(row)
        app.cad_compact_buttons[key]=connect;app.cad_compact_status[key]=status
        app.cad_connection_rows.append(row)
    footer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,css_classes=['cad-menu-footer'])
    app.cad_setup_button=Gtk.Button(css_classes=['flat'])
    app.cad_setup_button.update_property([Gtk.AccessibleProperty.LABEL],['Setup & connection status'])
    footer_content=Gtk.Box(spacing=6)
    from workspace_ui import workspace_glyph
    icon=workspace_glyph('settings',app.cad_setup_button)
    icon.set_valign(Gtk.Align.CENTER);icon.set_can_target(False)
    footer_content.append(icon);app.cad_setup_button.workspace_icon=icon
    app.cad_setup_caption=Gtk.Label(label='Setup & connection status',xalign=0,wrap=True,hexpand=True,width_chars=1)
    footer_content.append(app.cad_setup_caption)
    app.cad_setup_button.set_child(footer_content)
    footer.append(app.cad_setup_button);compact.append(footer)
    stack.add_named(compact,'compact')
    setup=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9,css_classes=['cad-setup'])
    app.cad_back_button=Gtk.Button(label='Back',halign=Gtk.Align.START,css_classes=['flat'])
    setup.append(app.cad_back_button)
    stack.add_named(setup,'setup')
    def show_setup(*_):
        stack.set_visible_child_name('setup')
        app.cad_back_button.grab_focus()
        app.cad_fit()
    def show_compact(*_):
        stack.set_visible_child_name('compact')
        app.cad_setup_button.grab_focus()
        app.cad_fit()
    app.cad_setup_button.connect('clicked',show_setup)
    app.cad_back_button.connect('clicked',show_compact)
    def dismissed(*_):
        app.cad_popup_open=False
        stack.set_visible_child_name('compact')
    popup.connect('closed',dismissed)
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
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
    solidcraft_details = Gtk.Expander(label='Connection details')
    solidcraft_details.set_child(app.cad_hint)
    solidcraft_details.get_label_widget().set_wrap(True)
    body.append(solidcraft_details)
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
    fusion_details = Gtk.Expander(label='Fusion bridge setup and details')
    fusion_setup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    fusion_setup.append(app.fusion_hint)
    fusion_details.set_child(fusion_setup)
    fusion_details.get_label_widget().set_wrap(True)
    body.append(fusion_details)
    cad_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    max_content_height=420, propagate_natural_height=True)
    cad_scroll.set_child(body)
    setup.append(cad_scroll)
    for label in (app.connection_label,app.fusion_connection_label,app.cad_hint,app.fusion_hint):
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    app.cad_setup_scroll=cad_scroll
    def setup_height(*_):
        cad_scroll.set_max_content_height(max(150,min(420,app.win.get_height()-180)))
    def fit_card(*_):
        # The width-constrained viewport must request the wrapped page height,
        # rather than the shorter height of its unconstrained natural width.
        padding=app.cad_setup_button.get_style_context().get_padding()
        border=app.cad_setup_button.get_style_context().get_border()
        caption_width=max(1,266-padding.left-padding.right-border.left-border.right
                          -footer_content.get_spacing()-icon.measure(Gtk.Orientation.HORIZONTAL,-1)[1])
        caption_height=app.cad_setup_caption.measure(Gtk.Orientation.VERTICAL,caption_width)[1]
        footer_content.set_size_request(-1,caption_height)
        page=stack.get_visible_child()
        changed=False
        if page:
            height=page.measure(Gtk.Orientation.VERTICAL,266)[1]
            changed=card_view.get_size_request()!=(266,height)
            if changed:card_view.set_size_request(266,height)
        if changed and popup.get_visible() and app.cad_popup_open:popup.present()
    app.cad_fit=fit_card
    popup.connect('show',lambda *_:setattr(app,'cad_popup_open',True))
    popup.connect('show',setup_height)
    popup.connect('show',fit_card)
    stack.connect('notify::visible-child-name',fit_card)
    paint_watch=[None,0]
    def stop_paint_watch(*_):
        if paint_watch[0] and paint_watch[1]:paint_watch[0].disconnect(paint_watch[1])
        paint_watch[:]=[None,0]
    def watch_paint(*_):
        stop_paint_watch()
        clock=popup.get_frame_clock()
        if clock:
            paint_watch[:]=[clock,clock.connect('after-paint',fit_card)]
    # Hidden popover styles can settle only when mapped. Recheck after paint;
    # unchanged requests do not queue more frames, and unmap removes the hook.
    popup.connect('map',watch_paint)
    popup.connect('unmap',stop_paint_watch)
    app.cad_menu.set_popover(popup)
    stack.set_visible_child_name('compact')
    def primary(_):
        if app.busy:return
        if app.active_cad == 'fusion' and app.fusion_connected:
            app.send_fusion()
        elif app.active_cad == 'solidcraft' and app.connected:
            app.send()
        else:
            app.cad_menu.popup()
    app.cad_action.connect('clicked', primary)
    for control in (app.send_btn,app.fusion_send_btn,app.connect_btn,app.fusion_connect_btn):
        control.connect('notify::sensitive',lambda *_:sync_cad_action(app))
    for label in (app.connection_label,app.fusion_connection_label):
        label.connect('notify::label',lambda *_:_sync_cad_compact(app))
    sync_cad_action(app)


def sync_cad_action(app):
    """Present the selected successful connection; preserve backend readiness."""
    if not hasattr(app, 'cad_action'):return
    active = app.active_cad
    if active == 'fusion' and not app.fusion_connected:active = None
    if active == 'solidcraft' and not app.connected:active = None
    app.active_cad = active
    label = {'fusion': 'Import in Fusion', 'solidcraft': 'Import in SolidCraft'}.get(active, 'CAD Connections')
    app.cad_action.set_label(label)
    ready = (app.fusion_send_btn.get_sensitive() and app.fusion_has_document if active == 'fusion' else
             app.send_btn.get_sensitive() if active == 'solidcraft' else True)
    app.cad_action.set_sensitive(not app.busy and ready)
    app.cad_menu.set_sensitive(not app.busy)
    _sync_cad_compact(app)


def _cad_compact_connect(app,key):
    """Select a known connection or invoke its unchanged explicit connect action."""
    if app.busy:return
    connected=app.fusion_connected if key=='fusion' else app.connected
    if connected and app.active_cad!=key and not(key=='fusion' and not app.fusion_has_document):
        app.active_cad=key
        sync_cad_action(app)
        return
    control=app.fusion_connect_btn if key=='fusion' else app.connect_btn
    if not control.get_sensitive():return
    control.emit('clicked')
    if app.busy:app.cad_pending_connection=key
    _sync_cad_compact(app)


def _sync_cad_compact(app):
    if not hasattr(app,'cad_compact_buttons'):return
    if not app.busy:app.cad_pending_connection=None
    for key,button in app.cad_compact_buttons.items():
        connected=app.fusion_connected if key=='fusion' else app.connected
        selected=connected and app.active_cad==key
        no_document=key=='fusion' and connected and not app.fusion_has_document
        pending=app.busy and app.cad_pending_connection==key
        status=app.cad_compact_status[key]
        message=('Connecting…' if pending else 'Connected · no active document' if no_document else
                 'Connected · selected' if selected else 'Connected' if connected else 'Not connected')
        status.set_text(message)
        detail=app.fusion_connection_label if key=='fusion' else app.connection_label
        status.set_tooltip_text(detail.get_text())
        status.update_property([Gtk.AccessibleProperty.DESCRIPTION],[detail.get_text()])
        if selected:status.add_css_class('cad-connected')
        else:status.remove_css_class('cad-connected')
        label='Connect' if pending else 'Check' if no_document else 'Connected' if selected else 'Select' if connected else 'Connect'
        button.set_label(label)
        if selected and not no_document:button.add_css_class('flat')
        else:button.remove_css_class('flat')
        control=app.fusion_connect_btn if key=='fusion' else app.connect_btn
        button.set_sensitive(not app.busy and control.get_sensitive() and not(selected and not no_document))
        button.update_property([Gtk.AccessibleProperty.LABEL],[label+' '+('Autodesk Fusion' if key=='fusion' else 'SolidCraft')])
    if hasattr(app,'cad_fit'):app.cad_fit()


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
    old_groups=getattr(app,'geometry_group_boxes',{})
    group_open={key:box._section.get_expanded() for key,box in old_groups.items() if hasattr(box,'_section')}
    groups = {}
    def group(key, title):
        if key not in groups:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9, css_classes=['parameter-group'])
            if key=='main':
                box.add_css_class('primary-geometry')
                box.set_spacing(11)
                app.sections['geometry'][1].append(box)
            else:
                disclosure=Gtk.Expander(label=title,expanded=group_open.get(key,True))
                disclosure.set_child(box)
                box._section=disclosure
                app.sections['geometry'][1].append(disclosure)
            groups[key] = box
        return groups[key]
    # Render groups in a useful order, independent of the generator's spec order.
    main_order = ('teeth','side_teeth','output_teeth','sun','planet','planets','sun2','planet2','output_ring','pinion','wheel',
                  'pins','radius','pin_radius','eccentric','module','width','spiral_angle','width2','layer_gap','disc_gap','helix','gap')
    if app.family == 'bevel':
        main_order = ('pinion','wheel','module','width','spiral_angle','trace_radius','spiral_hand')
    if app.family == 'face':
        main_order = ('pinion','wheel','module','width','offset','helix','radial_setting','gap')
    if app.family == 'rack':
        main_order = ('pinion','rack_teeth','module','width','helix','gap','base')
    if app.family == 'hypoid':
        main_order = ('pinion','wheel','module','offset','width','spiral_angle')
    multistage = app.family == 'parallel' and app.field_values.get('variant') in PARALLEL_MULTISTAGE_VARIANTS
    if multistage:
        main_order = tuple((key if stage == 1 else f'{key}{stage}')
                           for stage in (1,2,3)
                           for key in ('pinion','wheel','module','width','helix','gap','pressure','backlash','profile_shift','center_extra'))
    order = {key: i for i, key in enumerate(main_order)}
    specs = sorted(specs, key=lambda s: order.get(s[0], len(order)))
    app.sections['housing'][0].set_label('Shaft layout' if multistage else 'Housing & flanges')
    app.field_feedback, app.linked_notes, app.field_containers = {}, {}, {}
    app.input_geometry_groups = {}
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
        if app.family=='cycloidal' and key.startswith('eccentric_'):
            from printed_shaft import direct_field_active
            if not direct_field_active(key, app.option_values.get('eccentric_design')):continue
        if key in inactive or key=='input_rpm' or app.family=='differential' and key=='spiral_hand' or (key.startswith('print_') and app.option_values.get('eccentric_design')!='fdm_bolted'):
            continue
        page = 'geometry'
        if key in ('input_b_rpm','output_difference_rpm'):
            target, page = app.io_box, 'motion'
        elif key in ('input_torque','efficiency','pull_force'):
            target, page = load_box, 'motion'
        elif key in ('shoulder','seat_allowance','shaft_allowance'):
            target, page = app.sections['bearings'][1], 'assembly'
        elif app.family=='cycloidal' and key.startswith('eccentric_'):
            target, page = app.eccentric_design_box, 'assembly'
        elif multistage and (key.startswith('layout_angle') or key in ('stage_gap','hub_wall','assembly_clearance')):
            target, page = app.sections['housing'][1], 'assembly'
        elif multistage and re.fullmatch(r'(pinion|wheel|module|width|helix|gap|pressure|backlash|profile_shift|center_extra)([23]?)', key):
            stage = key[-1] if key[-1] in '23' else '1'
            target = group('stage'+stage, 'Stage '+stage)
        elif key in ('plate','housing_wall','rim','stage_gap','carrier_bolt_diameter','spider_pin_diameter','spider_clearance') or key.startswith('print_'):
            target, page = app.sections['housing'][1], 'assembly'
        elif key in ADVANCED or key=='center_extra':
            target = app.advanced_fields
        elif key.startswith('intermediate_bore'):
            target = group('shafts', 'Shafts & bores')
        elif key in ('bore','output_bore','wheel_bore','input_shaft','output_shaft','shaft_extension','journal_length','journal_diameter','output_extension','passage_diameter'):
            target = group('shafts', 'Shafts & bores')
        elif key in ('output_count','output_radius','output_pin','flange_radius','bolt_count','bolt_diameter'):
            target = group('output', 'Output connection')
        else:
            target = group('main', 'Disc & rollers' if app.family=='cycloidal' else 'Main geometry')
        unit_match = re.search(r'\[([^]]+)\]', label)
        caption = re.sub(r'\s*\[[^]]+\]', '', label).split(' (')[0]
        caption = {'pinion':'Pinion teeth', 'wheel':'Wheel teeth', 'module':'Module', 'width':'Face width'}.get(key,caption)
        unit = unit_match.group(1) if unit_match else ''
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True)
        row = Gtk.Box(spacing=3)
        name = Gtk.Label(label=caption+('\u2009·\u2009'+unit if unit else ''), xalign=0, wrap=True, hexpand=True, css_classes=['field-label'])
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
        spin.set_width_chars(3)
        spin.set_max_width_chars(8)
        spin.set_hexpand(True)
        spin.set_alignment(0)
        spin.add_css_class("parameter-input")
        # Keep the original spin control, range and key stepping. The compact
        # input surface reserves its right edge for the illustrated guide.
        child = spin.get_first_child()
        while child:
            if isinstance(child, Gtk.Button): child.set_visible(False)
            child = child.get_next_sibling()
        spin.set_tooltip_text(label + " · Use Up/Down to step")
        spin.update_property([Gtk.AccessibleProperty.LABEL],[label])
        bind_numeric_spin(spin, low=low, high=high, integer=key in INTEGER, app=app)
        set_numeric_value(spin, value)
        spin.connect('value-changed', app.changed)
        spin.connect('changed', app.changed)
        name.set_mnemonic_widget(spin)
        binding = help_controller.bind(name, spin, key, row)
        row.remove(binding.button)
        field = Gtk.Overlay()
        field.set_child(spin)
        binding.button.set_halign(Gtk.Align.END)
        binding.button.set_valign(Gtk.Align.CENTER)
        binding.button.set_margin_end(7)
        field.add_overlay(binding.button)
        # The icon and input form one hover source, including its right edge.
        spin.remove_controller(binding.motion)
        field.add_controller(binding.motion)
        steppers=[]
        child=spin.get_first_child()
        while child:
            if isinstance(child,Gtk.Button):steppers.append(child)
            child=child.get_next_sibling()
        def stepping_focus(controller, *, steppers=tuple(steppers), help_button=binding.button):
            focused=controller.contains_focus()
            for button in steppers:button.set_visible(focused)
            help_button.set_margin_end(33 if focused else 7)
        stepping=Gtk.EventControllerFocus()
        stepping.connect('enter',stepping_focus)
        stepping.connect('leave',stepping_focus)
        spin.add_controller(stepping)
        container.append(row)
        container.append(field)
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
            title = ('First ring teeth · fixed · derived' if app.family=='wolfrom' else 'Ring teeth · derived') if key=='planets' else 'Disc lobes · derived'
            derived.append(Gtk.Label(label=title, xalign=0, hexpand=True, wrap=True, css_classes=['muted']))
            value_label = Gtk.Label(selectable=True, xalign=1, css_classes=['derived-output'])
            value_label.set_tooltip_text('Calculated from the current tooth counts; edit the source geometry above.')
            derived.append(value_label)
            target.append(derived)
            app.geometry_derived[key] = value_label
        if app.family=='wolfrom' and key=='module':
            derived = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
            derived.append(Gtk.Label(label='Second layer module · derived [mm]', xalign=0, hexpand=True, wrap=True, css_classes=['muted']))
            value_label = Gtk.Label(selectable=True, xalign=1, css_classes=['derived-output'])
            value_label.set_wrap(True)
            value_label.set_wrap_mode(Pango.WrapMode.CHAR)
            value_label.set_halign(Gtk.Align.END)
            value_label.set_max_width_chars(16)
            value_label.set_tooltip_text('m2 = m1 × (S + P1) / (Ro − P2); common planet centre distance. Only the first layer module is editable.')
            derived.append(value_label)
            target.append(derived)
            app.geometry_derived['module2'] = value_label
        app.inputs[key], app.input_labels[key], app.input_pages[key] = spin, label, page
        app.field_containers[key] = container
        for group_key,group_box in groups.items():
            if target is group_box:app.input_geometry_groups[key]=group_key
        if app.family=='differential' and key=='output_teeth' and app.option_values.get('ratio_mode','custom')!='custom':spin.set_sensitive(False)
    parent=app.sections['geometry'][1]
    extra_open=bool(getattr(app,'extra_geometry_expander',None) and app.extra_geometry_expander.get_expanded())
    app.extra_geometry_expander=Gtk.Expander(label='All model parameters',expanded=extra_open,css_classes=['geometry-disclosure'])
    app.extra_geometry_expander.get_label_widget().set_wrap(True)
    extra_fields=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9)
    app.extra_geometry_expander.set_child(extra_fields)
    for key in ('output','shafts'):
        if key in groups:
            section=getattr(groups[key],'_section',groups[key])
            parent.remove(section)
            extra_fields.append(section)
    for first, second in [('pinion','wheel'),('sun','planet'),('sun2','planet2'),('module','width')]:
        one,two=app.field_containers.get(first),app.field_containers.get(second)
        if one is None or two is None or one.get_parent() is not two.get_parent():continue
        parent=one.get_parent();previous=one.get_prev_sibling()
        parent.remove(one);parent.remove(two)
        pair=Gtk.Grid(column_spacing=8,row_spacing=5,column_homogeneous=True,css_classes=['parameter-pair'])
        parent.insert_child_after(pair,previous)
        # A shared grid row honors height-for-width wrapping; GtkSizeGroup
        # alone cannot equalize independently wrapped caption boxes.
        for column,container in enumerate((one,two)):
            caption_row=container.get_first_child()
            container.remove(caption_row)
            pair.attach(caption_row,column,0,1,1)
            pair.attach(container,column,1,1,1)
    if app.advanced_fields.get_first_child():
        app.advanced_expander.add_css_class('geometry-disclosure')
        app.advanced_expander.get_label_widget().set_wrap(True)
        restore=Gtk.Button(label='Restore model defaults',css_classes=['flat','model-restore'])
        restore.get_child().set_wrap(True)
        restore.set_tooltip_text('Restore defaults. Use Undo in the toolbar to restore your edits.')
        restore.connect('clicked',app.reset_defaults)
        app.advanced_fields.append(restore)
        app.sections['geometry'][1].append(app.advanced_expander)
    if multistage and app.advanced_fields.get_first_child() is None:
        restore=Gtk.Button(label='Restore model defaults',css_classes=['flat','model-restore'])
        restore.get_child().set_wrap(True)
        restore.set_tooltip_text('Restore defaults. Use Undo in the toolbar to restore your edits.')
        restore.connect('clicked',app.reset_defaults)
        extra_fields.append(restore)
    if extra_fields.get_first_child():
        app.sections['geometry'][1].append(app.extra_geometry_expander)
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
    if key in ADVANCED or key=='center_extra':
        app.advanced_expander.set_expanded(True)
    group=getattr(app,'input_geometry_groups',{}).get(key)
    if group and group!='main':
        app.extra_geometry_expander.set_expanded(True)
        app.geometry_group_boxes[group]._section.set_expanded(True)
    page = app.input_pages.get(key, 'geometry')
    if page == 'assembly':
        for section, _ in app.sections.values():
            if section.is_ancestor(app.pages['assembly']):
                section.set_expanded(True)
    parent=app.inputs[key].get_parent()
    while parent is not None and parent is not app.fields:
        if isinstance(parent,Gtk.Expander):parent.set_expanded(True)
        parent=parent.get_parent()
    app.inputs[key].grab_focus()

def update_family(app):
    from parameter_help_ui import bind_options
    bind_options(app)
    description = CATALOG[app.family][1]
    variant=app.variant_selector.get_selected_item()
    suffix=variant.get_string() if variant else ''
    if app.family=='parallel':
        from parallel_multistage import count
        stages=count(app.field_values)
        suffix=f'{stages} stage'+('s' if stages!=1 else '')+' / '+suffix
    app.family_chip.set_text(CATALOG[app.family][0]+(' / '+suffix if suffix else ''))
    app.variant_caption.set_text('Tooth type' if app.family in ('parallel','internal','planetary','bevel','rack','face') else 'Variant')
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
    elif any(b.has_css_class('drive-member-card') for b in app.io_mode_buttons.values()):
        app.motion_help.set_text('Motor → input · Load → output')
    else:
        app.motion_help.set_text('Connect the motor to the input and the load to the output.')
    paired=any(b.has_css_class('drive-member-card') for b in app.io_mode_buttons.values())
    app.pages['motion'].set_spacing(0 if paired else 12)
    app.motion_help.set_margin_top(10 if paired else 0)
    if paired:
        app.motion_help.add_css_class('drive-footer')
        app.sections['loads'][0].add_css_class('direct-drive-loads')
    else:
        app.motion_help.remove_css_class('drive-footer')
        app.sections['loads'][0].remove_css_class('direct-drive-loads')


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
    app.export_scope = choice_dropdown(['Complete assembly', 'Selected components'])
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
    parent = app.win
    dialog = Gtk.FileChooserNative(title='Where should exported files be saved?', transient_for=parent, action=Gtk.FileChooserAction.SELECT_FOLDER, accept_label='Use this folder', cancel_label='Cancel')
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
