"""Navigazione e azioni della GUI; non modifica geometria o cinematica."""
from pathlib import Path
import json
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio
CATALOG = {'spur': ('Spur gear', 'A single gear: choose the tooth count, module and bore.'), 'helical': ('Helical gear', 'A single gear with an adjustable helix angle.'), 'double': ('Double helical gear', 'Two opposing helices, joined or separated by a groove.'), 'planetary': ('Planetary gearbox', 'Sun, planets and ring gear. One or two reduction stages.'), 'cycloidal': ('Cycloidal reducer', 'Eccentric discs and rollers, with one or two discs.'), 'harmonic': ('Strain wave reducer', 'A flexible gear deformed by a wave generator. Concept model.'), 'worm': ('Worm and wheel', 'Transmission with perpendicular axes. Concept gear pair.'), 'parallel': ('Parallel shaft reducer', 'A gear pair with input and output shafts.'), 'internal': ('Internal gear reducer', 'A pinion inside an internal gear, with fixed axes.')}
ADVANCED = {'pressure', 'backlash', 'profile_shift', 'addendum', 'dedendum', 'clearance', 'assembly_clearance', 'output_clearance', 'profile_tolerance', 'wave_clearance', 'wave_factor'}

def searchable_dropdown(labels):
    """Filter displayed names while keeping selection indices in the full model."""
    dropdown = Gtk.DropDown.new_from_strings(labels)
    dropdown.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, 'string'))
    dropdown.set_search_match_mode(Gtk.StringFilterMatchMode.SUBSTRING)
    dropdown.set_enable_search(True)
    return dropdown

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
    popup.set_child(body)
    app.cad_menu.set_popover(popup)


def preserve_scroll(app):
    """Restore a rebuilt panel after GTK has measured its new contents."""
    positions = {k: w.get_vadjustment().get_value() for k, w in app.page_scrolls.items()}
    app.panel_revision = getattr(app, 'panel_revision', 0) + 1
    revision = app.panel_revision
    def restore(*args):
        if revision == app.panel_revision:
            for key, value in positions.items():
                adj = app.page_scrolls[key].get_vadjustment()
                adj.set_value(min(value, max(adj.get_lower(), adj.get_upper()-adj.get_page_size())))
        return False
    app.win.add_tick_callback(lambda *_: restore())


def geometry_groups(app, specs):
    """Assign geometric fields to stable, family-specific groups."""
    from geometry import INTEGER
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
    main_order = ('teeth','sun','planet','planets','sun2','planet2','pinion','wheel',
                  'pins','radius','pin_radius','eccentric','module','width','width2','disc_gap','helix','gap')
    order = {key: i for i, key in enumerate(main_order)}
    specs = sorted(specs, key=lambda s: order.get(s[0], len(order)))
    app.field_feedback, app.linked_notes, app.field_containers = {}, {}, {}
    app.geometry_derived = {}
    app.geometry_group_boxes = groups
    load_box = app.sections['loads'][1]
    app.load_help = text('Based on operating inputs and assumed efficiency. These are not allowable loads.')
    load_box.append(app.load_help)
    for key, label, default, low, high, step in specs:
        if key=='input_rpm' or (key.startswith('print_') and app.option_values.get('eccentric_design')!='fdm_bolted'):
            continue
        page = 'geometry'
        if key in ('input_torque','efficiency','pull_force'):
            target, page = load_box, 'motion'
        elif key in ('shoulder','seat_allowance','shaft_allowance'):
            target, page = app.sections['bearings'][1], 'assembly'
        elif key in ('plate','housing_wall','rim','stage_gap') or key.startswith('print_'):
            target, page = app.sections['housing'][1], 'assembly'
        elif key in ADVANCED:
            target = app.advanced_fields
        elif key in ('bore','output_bore','wheel_bore','input_shaft','output_shaft','shaft_extension','journal_length','journal_diameter'):
            target = group('shafts', 'Shafts & bores')
        elif key in ('output_count','output_radius','output_pin'):
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
        name.set_tooltip_text(label)
        row.append(name)
        spin = Gtk.SpinButton.new_with_range(low, high, step)
        value = app.field_values.get(key, default)
        decimals = len(f'{value:.6f}'.rstrip('0').partition('.')[2])
        spin.set_digits(0 if key in INTEGER else max(2, decimals))
        spin.set_numeric(False)
        spin.set_value(value)
        spin.set_width_chars(6)
        spin.set_max_width_chars(8)
        spin.set_alignment(1)
        spin.set_tooltip_text(label)
        def preserve_invalid_text(widget, low=low, high=high):
            # GTK normally replaces an invalid entry on focus loss. Keep the
            # user's text so validation can explain it instead of silently
            # substituting the previous or clamped value.
            if app.building:
                return False
            try:
                from math import isfinite
                number = float(widget.get_text().strip().replace(',', '.'))
                return not isfinite(number) or not low <= number <= high
            except ValueError:
                return True
        spin.connect('output', preserve_invalid_text)
        spin.connect('value-changed', app.changed)
        spin.connect('changed', app.changed)
        name.set_mnemonic_widget(spin)
        row.append(spin)
        units = Gtk.Label(label=unit, xalign=0, css_classes=['muted'])
        units.set_width_chars(3)
        row.append(units)
        container.append(row)
        feedback = text('', 'error')
        feedback.set_visible(False)
        container.append(feedback)
        app.field_feedback[key] = feedback
        if key in ('bore','input_shaft','output_shaft'):
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
            value_label = Gtk.Label(selectable=True, css_classes=['field-label'])
            derived.append(value_label)
            target.append(derived)
            app.geometry_derived[key] = value_label
        app.inputs[key], app.input_labels[key], app.input_pages[key] = spin, label, page
        app.field_containers[key] = container
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
    description = CATALOG[app.family][1]
    app.selector.set_tooltip_text(description)
    app.family_hint.set_text('Geometric study · illustrative profiles')
    app.family_hint.set_visible(app.family in ('harmonic', 'worm'))
    app.eccentric_section.set_visible(app.family=='cycloidal')
    enabled = app.sections['bearings'][0].get_visible() or app.sections['hardware'][0].get_visible()
    app.mount_help.set_text('Linked dimensions update automatically.' if enabled else 'This family does not use the automatic catalog. Adjust flanges, shafts and clearances in Dimensions; interfaces follow the choices in Motion.')
    if not app.io_frame.get_visible():
        app.motion_help.set_text('This is a single gear. Use Start motion in the motion bar to see it rotate and set speed and torque.')
    else:
        app.motion_help.set_text('Connect the motor to the input and the load to the output.')


def update_geometry_warning(app, design):
    from engineering import geometry_warnings

    warnings = geometry_warnings(design)
    study = design.family in ('harmonic', 'worm')
    if study:
        message = 'Concept model · profiles are not conjugate'
    elif warnings:
        message = 'Geometry warning: ' + warnings[0] + ' See the calculation report.'
    else:
        message = ''
    app.study.set_text(message)
    app.study.set_visible(study or bool(warnings))
    if hasattr(app, 'warning_bar'):
        app.warning_bar.remove_css_class('invalid')
        app.warning_bar.set_visible(study or bool(warnings))
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
    app.export_menu.set_popover(popup)
    for title, description, fn in [('STL for 3D printing', 'Complete assembly and one file per component.', app.export_stl), ('Complete package', 'STL, CAD script, preview, parameters, BOM and calculations.', app.export), ('BOM and calculations', 'TXT, CSV and JSON for components and nominal calculations.', app.export_bom)]:
        b = action(body, title, description, lambda _, fn=fn: (popup.popdown(), fn()))
        app.file_buttons.append(b)
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
            folder = Path(d.get_file().get_path())
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
    for name, accelerator, callback in [('open', '<Control>o', app.load_dialog), ('save', '<Control>s', app.save_dialog), ('export', '<Control>e', lambda _: app.export_menu.popup())]:
        action = Gio.SimpleAction.new(name, None)
        action.connect('activate', lambda _, parameter, fn=callback: fn(None) if not app.busy else None)
        app.add_action(action)
        app.set_accels_for_action('app.' + name, [accelerator])

def show_report(app, title, content):
    """Report consultabile con ricerca, selezione e copia del testo."""
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
