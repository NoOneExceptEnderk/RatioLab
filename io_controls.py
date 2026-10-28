"""Controlli GTK per scegliere i members fisici senza decifrare le permutazioni."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from kinematics import TRIPLES, options, default
MEMBER_HELP = {'sun': 'Central gear.', 'carrier': 'Support carrying the planet gears.', 'ring': 'Outer ring gear / housing.', 'eccentric': 'Shaft with an eccentric driving the discs.', 'output': 'Flange connected to the disc output pins.', 'wave': 'Generator that deforms the flexible gear.', 'flex': 'Flexible gear.', 'circular': 'Rigid ring gear.', 'input': 'First stage pinion.', 'case': 'Outer reducer housing.', 'cam': 'Cam driving the rollers.', 'cage': 'Cage carrying the rollers.'}

def label(text, style='muted'):
    p = Gtk.Label(label=text, xalign=0, wrap=True, css_classes=[style])
    p.set_max_width_chars(38)
    return p

def row(box, title, value, style):
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    b.add_css_class('io-role')
    b.add_css_class(style)
    b.append(label(title, 'field-label'))
    b.append(label(value, 'io-value'))
    box.append(b)

def build(app, values, variant, choice):
    box = app.io_box
    while (child := box.get_first_child()):
        box.remove(child)
    schemes = options(app.family)
    app.io_frame.set_visible(bool(schemes))
    app.io_selectors = {}
    app.io_role_selectors = {}
    app.io_mode_buttons = {}
    app.io_results = []
    if not schemes:
        return
    legacy = 'wave_circular_flex' if app.family == 'harmonic' and values.get('harmonic_output') == 'circular' else default(app.family)
    active = values.get('io_scheme', legacy)
    app.option_values['io_scheme'] = active

    def commit(changes):
        app.rebuild_options(changes)
    if app.family in TRIPLES:
        names = TRIPLES[app.family]
        two = app.family == 'planetary' and variant in ('two_stage', 'two_stage_double')
        printed = app.family == 'cycloidal' and values.get('eccentric_design') == 'fdm_bolted'
        for stage in range(1, 3 if two else 2):
            key = 'io_scheme' if stage == 1 else 'io_scheme2'
            scheme = values.get(key, active)
            app.option_values[key] = scheme
            source, target, fixed = scheme.split('_')
            frame = Gtk.Frame(label=f'Stage {stage}' if two else None)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            for setter in (body.set_margin_start, body.set_margin_end, body.set_margin_top, body.set_margin_bottom):
                setter(8)
            frame.set_child(body)
            box.append(frame)
            controls = {}
            for role, title, keys, selected, style in [('input', '1 · Motor', ['eccentric'] if printed else list(names), source, 'io-input'), ('output', '2 · Output', [m for m in names if m != source], target, 'io-output')]:
                group = Gtk.Box(spacing=8)
                group.add_css_class('io-role')
                group.add_css_class(style)
                caption = label(title, 'field-label')
                caption.set_width_chars(10)
                group.append(caption)
                dropdown = Gtk.DropDown.new_from_strings([names[k] for k in keys])
                dropdown.set_hexpand(True)
                dropdown.set_selected(keys.index(selected))
                dropdown.set_tooltip_text(MEMBER_HELP[selected])
                group.append(dropdown)
                body.append(group)

                def changed(widget, *args, key=key, role=role, keys=keys, source=source, target=target):
                    if app.building:
                        return
                    member = keys[widget.get_selected()]
                    a = member if role == 'input' else source
                    b = member if role == 'output' else target
                    if a == b:
                        b = next((m for m in names if m != a))
                    c = next((m for m in names if m not in (a, b)))
                    commit({key: '_'.join((a, b, c))})
                dropdown.connect('notify::selected', changed)
                controls[role] = dropdown
            app.io_role_selectors[key] = controls
            fixed_row = Gtk.Box(spacing=8)
            fixed_row.add_css_class('io-role')
            fixed_row.append(label('3 · Fixed to frame', 'field-label'))
            fixed_row.append(label(names[fixed], 'io-value'))
            fixed_row.set_tooltip_text('The third member stays fixed. To change it, choose a different input/output pair.')
            body.append(fixed_row)
            actions = Gtk.Box(spacing=6)
            body.append(actions)
            swap = Gtk.Button(label='Swap input and output')
            swap.connect('clicked', lambda _, key=key, a=source, b=target, c=fixed: commit({key: '_'.join((b, a, c))}))
            actions.append(swap)
            controls['swap'] = swap
            if printed:
                swap.set_sensitive(False)
                swap.set_tooltip_text('The FDM shaft uses eccentric input. Select the standard construction for other driving members.')
            result = label('', 'io-result')
            body.append(result)
            app.io_results.append((stage, result))
            if two and stage == 1:
                box.append(label('↓ Stage 1 output drives stage 2 input.', 'field-label'))
        if app.family in ('planetary', 'cycloidal') and any((app.option_values.get(k, default(app.family)) != default(app.family) for k in ('io_scheme', 'io_scheme2'))) and (values.get('bearing_mode', 'manual') != 'manual' or values.get('hardware_mode', 'none') != 'none'):
            box.append(label('This connection requires manual dimensions: automatic supports are defined for the default arrangement.', 'error'))
            manual = Gtk.Button(label='Use manual dimensions for this arrangement')
            manual.connect('clicked', lambda _: commit({'bearing_mode': 'manual', 'hardware_mode': 'none'}))
            box.append(manual)
    else:
        from kinematics import PAIRS
        a,b=PAIRS[app.family]
        titles = {'forward': f'{a} → {b}', 'reverse': f'{b} → {a}'}
        source, target = (a, b) if active == 'forward' else (b, a)
        help_text = 'Choose which side drives the transmission.'
        if app.family == 'worm' and active == 'reverse':
            help_text = 'Driving from the wheel is theoretical: the worm may not be backdrivable.'
        first = None
        for key in schemes:
            button = Gtk.CheckButton()
            button.set_child(label(titles[key], 'field-label'))
            if first:
                button.set_group(first)
            else:
                first = button
            button.set_active(key == active)

            def toggled(widget, key=key):
                if widget.get_active() and (not app.building):
                    commit({'io_scheme': key})
            button.connect('toggled', toggled)
            box.append(button)
            app.io_mode_buttons[key] = button
        row(box, 'Input · apply motion here', source, 'io-input')
        row(box, 'Output · connect the load here', target, 'io-output')
        box.append(label(help_text))
        result = label('', 'io-result')
        box.append(result)
        app.io_results.append((0, result))
    box.set_tooltip_text('Interfaces follow the selected arrangement and are visible when Supports is enabled in the preview.')
    reset = Gtk.Button(label='Reset default arrangement')
    reset.connect('clicked', lambda _: commit({'io_scheme': default(app.family), **({'io_scheme2': default(app.family)} if 'io_scheme2' in app.option_values else {})}))
    box.append(reset)
    app.io_frame.set_label('Drive · input and output')

def update(app, design):
    if design is None:
        for _, widget in app.io_results:
            widget.set_text('Result out of date · correct the parameters.')
        return
    stages = design.analysis.get('kinematics', {}).get('stage_results', [])
    for stage, widget in app.io_results:
        if stage:
            q = next((q for i, q in enumerate(stages, 1) if i == stage), None)
            if not q:
                continue
            ratio = q['signed_ratio']
            gain = abs(ratio)
            text = f'Reduces speed by a factor of {gain:.3g} times' if gain > 1 + 1e-09 else f'Increases speed by a factor of {1 / gain:.3g} times' if gain < 1 - 1e-09 else 'Same absolute speed'
            text += ' · ' + ('opposite direction' if ratio < 0 else 'same direction')
            widget.set_text(text + f"\nOutput: {q['rates_rpm'][q['output']]:+.2f} rpm")
        else:
            output=design.analysis.get('output')
            widget.set_text(f"Nominal output: {output['rpm']:+.2f} rpm" if output else 'Updated results below the preview.')
        if design.analysis.get('mount_interfaces'):
            widget.set_text(widget.get_text() + '\nHubs and flanges adapted to the arrangement.')
