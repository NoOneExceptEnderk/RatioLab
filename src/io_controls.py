# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK controls for selecting physical members without decoding permutations."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from kinematics import TRIPLES, options, default
from backdrivability import FRICTION_KEY, BackdrivabilityError, physical_inputs, enforce
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
    app.io_frame.set_label('Drive connections')
    while (child := box.get_first_child()):
        box.remove(child)
    schemes = options(app.family)
    app.io_frame.set_visible(bool(schemes))
    app.io_selectors = {}
    app.io_role_selectors = {}
    app.io_mode_buttons = {}
    app.io_results = []
    app.io_policy_note = None
    app.io_policy_error = None
    if app.family == 'wolfrom':
        app.io_frame.set_visible(True)
        app.io_frame.set_label('Fixed Wolfrom drive connections')
        app.option_values['io_scheme'] = 'sun_output_ring'
        row(box, 'Input · apply motion here', 'Sun', 'io-input')
        row(box, 'Fixed to frame', 'First ring', 'io-role')
        row(box, 'Output · connect the load here', 'Second ring · exposed annulus', 'io-output')
        box.append(label('The common carrier is free. Both planet rims are rigidly joined. This topology has no input/output swap.'))
        box.append(label('Positive rotation is counterclockwise viewed from +Z toward the XY plane. Physical backdrivability is not established.'))
        result = label('', 'io-result')
        box.append(result)
        app.io_results.append((0, result))
        return
    if app.family == 'differential':
        classic=values.get('configuration','wrist')=='classic'
        app.io_frame.set_visible(True)
        app.io_frame.set_label('Carrier input and two side outputs' if classic else 'Two independent inputs')
        box.append(label('Set carrier input C in the motion bar. Prescribe B−A below to explore the two outputs; this is a speed boundary condition, not another motor.' if classic else 'Input A is set in the motion bar. Set input B below. Both signs use the same world +X direction; the shafts face opposite sides.'))
        box.append(label('A=C−(B−A)/2 and B=C+(B−A)/2. All signs use world +X. Output split is not predicted from loads.' if classic else 'Equal speeds → carrier tilt. Opposing speeds → output spin. Other combinations move both axes.'))
        demos = Gtk.Box(spacing=5)
        choices=[('Equal',12,0),('A held',12,24),('Counterrotate',0,24)] if classic else [('Tilt', 12, 12), ('Spin', 12, -12), ('Combined', 12, 0)]
        for title, a, b in choices:
            button = Gtk.Button(label=title)
            button.set_tooltip_text(f'Prescribe carrier C / difference B−A = {a:+g} / {b:+g} rpm; A held is a speed boundary, not a differential lock.' if classic else f'Demonstrate with inputs A / B = {a:+g} / {b:+g} rpm.')
            button.connect('clicked', lambda _, a=a, b=b, classic=classic: app.rebuild_options({'input_rpm':a,'output_difference_rpm' if classic else 'input_b_rpm':b}))
            demos.append(button)
            app.io_mode_buttons[title.lower().replace(' ','_')] = button
        box.append(demos)
        result = label('', 'io-result')
        box.append(result)
        app.io_results.append((0, result))
        return
    if not schemes:
        return
    legacy = 'wave_circular_flex' if app.family == 'harmonic' and values.get('harmonic_output') == 'circular' else default(app.family)
    active = values.get('io_scheme', legacy)
    app.option_values['io_scheme'] = active

    rejection = label('', 'error')
    rejection.set_visible(False)
    box.append(rejection)
    app.io_policy_error = rejection

    def commit(changes, remove=()):
        # Validate the candidate before rebuild_options remembers it in history.
        try:
            enforce(app.family, policy_candidate(app, changes, remove))
        except BackdrivabilityError as error:
            rejection.set_text(str(error))
            rejection.set_visible(True)
            app.status_text(str(error))
            return False
        except (ValueError, TypeError, OverflowError):
            # Preserve the existing repair workflow for unrelated draft errors.
            pass
        if remove:
            app.remember()
            for key in remove:
                app.values[app.family].pop(key, None)
                app.option_values.pop(key, None)
            app.values[app.family].update(changes)
            app.make_fields()
        else:
            app.rebuild_options(changes)
        return True

    if app.family == 'worm':
        if FRICTION_KEY in values:
            app.option_values[FRICTION_KEY] = values[FRICTION_KEY]
        box.append(label('Static tooth friction coefficient μ (dimensionless)', 'field-label'))
        entry = Gtk.Entry()
        entry.set_placeholder_text('Unknown · no assumed value')
        entry.set_text(str(values.get(FRICTION_KEY, '')))
        entry.set_tooltip_text('Explicit static coefficient for the actual tooth contact and conditions. No material or lubrication value is inferred.')
        box.append(entry)
        buttons = Gtk.Box(spacing=5)
        apply = Gtk.Button(label='Apply coefficient')
        clear = Gtk.Button(label='Clear coefficient · unknown')
        def apply_friction(*args):
            try:
                coefficient = float(entry.get_text().strip().replace(',', '.'))
                physical_inputs('worm', {FRICTION_KEY: coefficient})
            except (ValueError, OverflowError):
                rejection.set_text('Enter a finite static tooth friction coefficient ≥ 0, or explicitly clear it as unknown.')
                rejection.set_visible(True)
                return
            commit({FRICTION_KEY: coefficient})
        apply.connect('clicked', apply_friction)
        entry.connect('activate', apply_friction)
        clear.connect('clicked', lambda _: commit({}, remove=(FRICTION_KEY,)))
        buttons.append(apply)
        buttons.append(clear)
        box.append(buttons)
        box.append(label('Clearing removes physical evidence: wheel-driven motion becomes an explicitly indeterminate ideal relation. It does not make a self-locking assembly backdrivable.'))
        app.io_friction_entry, app.io_friction_apply, app.io_friction_clear = entry, apply, clear
    if app.family in ('worm', 'harmonic'):
        app.io_policy_note = label('')
        box.append(app.io_policy_note)
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
        if app.family == 'worm':
            help_text = 'Wheel driving is screened with the lead angle, normal pressure angle and explicit static tooth friction. Reversing motor speed alone does not swap the driving member.'
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
                    if not commit({'io_scheme': key}):
                        app.building = True
                        try:
                            app.io_mode_buttons[active].set_active(True)
                        finally:
                            app.building = False
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
    if design is not None and getattr(app, 'io_policy_error', None) is not None:
        app.io_policy_error.set_visible(False)
    note = getattr(app, 'io_policy_note', None)
    if note is not None and design is not None:
        assessment = design.analysis.get('backdrivability', {})
        note.set_text(assessment.get('message', ''))
        note.set_visible(assessment.get('status') != 'not_evaluated')
    if design is None:
        for _, widget in app.io_results:
            widget.set_text('Result out of date · correct the parameters.')
        return
    if design.family == 'wolfrom':
        rates = design.analysis['kinematics']['rates_rpm']
        for _, widget in app.io_results:
            widget.set_text('Sun input: {sun:+.9g} rpm\nCommon carrier: {carrier:+.9g} rpm\nCompound spin: {planet:+.9g} rpm\nOutput ring: {output:+.9g} rpm\nFirst ring: 0 rpm · signs about +Z'.format(**rates))
        return
    if design.family == 'differential':
        q = design.analysis['kinematics']['rates_rpm']
        for _, widget in app.io_results:
            widget.set_text(f"Side output A / B: {q['side_a']:+.3g} / {q['side_b']:+.3g} rpm\nInternal spider spin: {q['spider_spin']:+.3g} rpm relative to carrier" if design.values.get('configuration')=='classic' else f"Carrier tilt: {q['carrier']:+.3g} rpm\nOutput spin relative to carrier: {q['output_spin']:+.3g} rpm")
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



WORM_DIMENSIONS = ('module', 'starts', 'diameter', 'pressure')


def policy_candidate(app, changes=None, remove=()):
    """Read physical evidence independently of unrelated incomplete text fields."""
    from geometry import defaults, get_specs
    from gui_workflow import numeric_value
    from math import isfinite
    values = dict(defaults(app.family))
    values.update(app.values.get(app.family, {}))
    values.update(app.option_values)
    if app.family == 'worm':
        for name in WORM_DIMENSIONS:
            if name in app.inputs:
                values[name] = numeric_value(app.inputs[name])
    values.update(changes or {})
    for name in remove:
        values.pop(name, None)
    if app.family == 'worm':
        for name, title, _, low, high, _ in get_specs('worm', values.get('variant')):
            if name in WORM_DIMENSIONS:
                value = values[name]
                if (type(value) not in (int, float) or not isfinite(value)
                        or not low <= value <= high or name == 'starts' and value != int(value)):
                    raise ValueError(title + ': complete a valid physical dimension.')
    return values


def _same_explicit(values, previous, name):
    return ((name in values) == (name in previous) and
            (name not in values or type(values[name]) is type(previous[name])
             and values[name] == previous[name]))


def _restore_evaluated_number(app, name, widget, previous):
    from gui_workflow import set_numeric_value, _set_explicit_numeric_text
    raw, automatic, raw_matches = None, False, False
    saved = getattr(app, 'document', None)
    snapshot = saved.current if saved is not None else {}
    sources = [(app.raw_edits, app.automatic_edits)]
    if snapshot.get('family') == app.family:
        sources.append((snapshot.get('raw', {}), snapshot.get('automatic', {})))
    for raw_fields, automatic_fields in sources:
        text = raw_fields.get(app.family, {}).get(name)
        try:
            if text is not None and float(text.strip().replace(',', '.')) == previous:
                raw, raw_matches = text, True
                automatic = name in automatic_fields.get(app.family, [])
                break
        except (ValueError, TypeError):
            pass
    set_numeric_value(widget, previous)
    if raw_matches and not automatic:
        _set_explicit_numeric_text(widget, raw)
    app.values[app.family][name] = previous
    if raw_matches:
        app.raw_edits.setdefault(app.family, {})[name] = raw
    else:
        app.raw_edits.get(app.family, {}).pop(name, None)
    automatic_fields = set(app.automatic_edits.get(app.family, []))
    if automatic or not raw_matches:
        automatic_fields.add(name)
    else:
        automatic_fields.discard(name)
    app.automatic_edits[app.family] = sorted(automatic_fields)


def reject_forbidden_edit(app, key=None):
    """Refuse a known violation before history/design mutation.

    A single-field edit restores that field. A direct refresh restores all
    changed physical evidence as one batch. Unrelated fields and drafts remain
    untouched, and incomplete physical dimensions retain the normal error path.
    """
    if key is not None and key not in WORM_DIMENSIONS:
        return False
    if app.family != 'worm' or app.design is None or app.design.family != app.family:
        return False
    try:
        candidate = policy_candidate(app)
        coefficient_changed = not _same_explicit(candidate, app.design.values, FRICTION_KEY)
        arrangement_changed = candidate['io_scheme'] != app.design.values['io_scheme']
        if (not coefficient_changed and not arrangement_changed and
                all(candidate[name] == app.design.values[name] for name in WORM_DIMENSIONS)):
            return False
        enforce(app.family, candidate)
    except BackdrivabilityError as error:
        from gui_workflow import numeric_value
        was_building = app.building
        app.building = True
        try:
            for name in WORM_DIMENSIONS:
                if (key is None or name == key) and name in app.inputs:
                    previous = app.design.values[name]
                    if numeric_value(app.inputs[name]) != previous:
                        _restore_evaluated_number(app, name, app.inputs[name], previous)
            if key is None:
                # Restore changed evidence as one batch. Unapplied coefficient
                # text and unchanged numeric formatting are independent drafts.
                for store in (app.option_values, app.values[app.family]):
                    if arrangement_changed:
                        store['io_scheme'] = app.design.values['io_scheme']
                    if coefficient_changed:
                        if FRICTION_KEY in app.design.values:
                            store[FRICTION_KEY] = app.design.values[FRICTION_KEY]
                        else:
                            store.pop(FRICTION_KEY, None)
                if arrangement_changed:
                    for scheme, button in app.io_mode_buttons.items():
                        button.set_active(scheme == app.design.values['io_scheme'])
                entry = getattr(app, 'io_friction_entry', None)
                if coefficient_changed and entry is not None:
                    entry.set_text(str(app.design.values.get(FRICTION_KEY, '')))
                previous_rpm = app.design.values['input_rpm']
                if getattr(app, 'motion_rpm', previous_rpm) != previous_rpm:
                    from motion_controls import scale_rpm
                    was_syncing = getattr(app, 'motion_syncing', False)
                    app.motion_syncing = True
                    try:
                        _restore_evaluated_number(app, 'input_rpm', app.motion_speed_text, previous_rpm)
                        app.motion_rpm = previous_rpm
                        app.motion_speed.set_value(scale_rpm(previous_rpm))
                        app.motion_rate_editing = False
                        app.motion_input_invalid = False
                        app.motion_speed_text.remove_css_class('field-error')
                        app.motion_rate_error.set_visible(False)
                    finally:
                        app.motion_syncing = was_syncing
        finally:
            app.building = was_building
        note = getattr(app, 'io_policy_error', None)
        if note is not None:
            note.set_text(str(error))
            note.set_visible(True)
        app.status_text(str(error))
        return True
    except (ValueError, TypeError, OverflowError):
        return False
    return False


def defer_empty_physical_text(app, key):
    """Let GTK finish a text replacement before recording its empty signal.

    A genuinely cleared field re-enters the ordinary change handler at idle;
    a completed replacement or a refused candidate quietly cancels the replay.
    """
    if (app.family != 'worm' or key not in WORM_DIMENSIONS
            or getattr(app, '_io_replaying_empty', False)):
        return False
    widget = app.inputs.get(key)
    if widget is None or widget.get_text() != '':
        return False
    from gi.repository import GLib
    family = app.family
    document = getattr(app, 'document', None)
    token = document.token if document is not None else None
    def replay():
        current = getattr(app, 'document', None)
        if (app.family != family or app.inputs.get(key) is not widget
                or widget.get_text() != '' or app.building
                or (current.token if current is not None else None) != token):
            return False
        app._io_replaying_empty = True
        try:
            app.changed(widget)
        finally:
            app._io_replaying_empty = False
        return False
    # This is a deferred input event, not background work: ordinary idle
    # priority can starve behind continuously ready layout/render sources.
    # GTK finishes a synchronous text replacement before this callback runs.
    GLib.idle_add(replay, priority=GLib.PRIORITY_DEFAULT)
    return True
