# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK controls for selecting physical members without decoding permutations."""
from parallel_multistage import VARIANTS as PARALLEL_MULTISTAGE_VARIANTS
import gi
from parallel_multistage import VARIANTS as PARALLEL_MULTISTAGE_VARIANTS
gi.require_version('Gtk', '4.0')
from gui_workflow import choice_dropdown
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

def speed_readout(box):
    result=label('', 'drive-result-value');result.set_wrap(False)
    body=Gtk.Box(spacing=4,css_classes=['drive-result'])
    caption=label('Nominal output','drive-result-title');caption.set_hexpand(True)
    unit=label('rpm','drive-result-unit')
    for widget in (caption,result,unit):widget.set_valign(Gtk.Align.BASELINE);body.append(widget)
    box.append(body)
    return result


def build(app, values, variant, choice):
    box = app.io_box
    box.remove_css_class('direct-drive-body')
    box.set_spacing(8)
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
    if app.family == 'wolfrom':
        app.io_frame.set_visible(True)
        app.io_frame.set_label('Fixed Wolfrom drive connections')
        app.io_frame.get_label_widget().set_wrap(True)
        app.option_values['io_scheme'] = 'sun_output_ring'
        row(box, 'Input · apply motion here', 'Sun', 'io-input')
        row(box, 'Fixed to frame', 'First ring', 'io-fixed')
        row(box, 'Output · connect the load here', 'Second ring · exposed annulus', 'io-output')
        details=Gtk.Expander(label='Motion details',css_classes=['motion-notes'])
        detail=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7)
        details.set_child(detail)
        detail.append(label('The common carrier is free. Both planet rims are rigidly joined. This topology has no input/output swap.'))
        detail.append(label('Positive rotation is counterclockwise viewed from +Z toward the XY plane. Physical backdrivability is not established.'))
        result = label('', 'io-result')
        detail.append(result)
        app.io_results.append((0, result))
        app.io_results.append((0,speed_readout(box)))
        box.append(details)
        return
    if app.family == 'differential':
        classic=values.get('configuration','wrist')=='classic'
        app.io_frame.set_visible(True)
        app.io_frame.set_label('Carrier input and two side outputs' if classic else 'Two independent inputs')
        app.io_frame.get_label_widget().set_wrap(True)
        box.append(label('Set carrier input C in the motion bar. Prescribe B−A below to explore the two outputs; this is a speed boundary condition, not another motor.' if classic else 'Input A is set in the motion bar. Set input B below. Both signs use the same world +X direction; the shafts face opposite sides.'))
        details = Gtk.Expander(label='Motion details',css_classes=['motion-notes'])
        details.set_child(label('A=C−(B−A)/2 and B=C+(B−A)/2. All signs use world +X. Output split is not predicted from loads.' if classic else 'Equal speeds → carrier tilt. Opposing speeds → output spin. Other combinations move both axes.'))
        demos = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=4,row_spacing=4,min_children_per_line=1,max_children_per_line=3,css_classes=['motion-demos'])
        choices=[('Equal',12,0),('A held',12,24),('Counterrotate',0,24)] if classic else [('Tilt', 12, 12), ('Spin', 12, -12), ('Combined', 12, 0)]
        for title, a, b in choices:
            button = Gtk.Button(label=title)
            button.get_child().set_wrap(True)
            button.set_tooltip_text(f'Prescribe carrier C / difference B−A = {a:+g} / {b:+g} rpm; A held is a speed boundary, not a differential lock.' if classic else f'Demonstrate with inputs A / B = {a:+g} / {b:+g} rpm.')
            button.connect('clicked', lambda _, a=a, b=b, classic=classic: app.rebuild_options({'input_rpm':a,'output_difference_rpm' if classic else 'input_b_rpm':b}))
            demos.append(button)
            app.io_mode_buttons[title.lower().replace(' ','_')] = button
        box.append(demos)
        result = label('', 'io-result')
        box.append(result)
        app.io_results.append((0, result))
        box.append(details)
        return
    if not schemes:
        return
    legacy = 'wave_circular_flex' if app.family == 'harmonic' and values.get('harmonic_output') == 'circular' else default(app.family)
    active = values.get('io_scheme', legacy)
    app.option_values['io_scheme'] = active

    if app.family == 'worm':
        app.io_frame.set_label('Drive · input and output')
        row(box, 'Input', 'Worm', 'io-input')
        row(box, 'Output', 'Wheel', 'io-output')
        app.io_results.append((0, speed_readout(box)))
        return

    commit = app.rebuild_options
    if app.family == 'harmonic':
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
            frame = Gtk.Frame(label=f'Stage {stage}' if two else None,css_classes=['io-stage'])
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            for setter in (body.set_margin_start, body.set_margin_end, body.set_margin_top, body.set_margin_bottom):
                setter(8)
            frame.set_child(body)
            box.append(frame)
            controls = {}
            for role, title, keys, selected, style in [('input', 'Input', ['eccentric'] if printed else list(names), source, 'io-input'), ('output', 'Output', [m for m in names if m != source], target, 'io-output')]:
                group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
                group.add_css_class('io-role')
                group.add_css_class(style)
                caption = label(title, 'field-label')
                caption.set_wrap(False)
                group.append(caption)
                dropdown = choice_dropdown([names[k] for k in keys])
                dropdown.set_hexpand(True)
                dropdown.update_property([Gtk.AccessibleProperty.LABEL],[f'Stage {stage} '+title])
                caption.set_mnemonic_widget(dropdown)
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
            fixed_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,css_classes=['io-role','io-fixed'])
            fixed_row.append(label('Fixed to frame', 'field-label'))
            fixed_row.append(label(names[fixed], 'io-value'))
            fixed_row.set_tooltip_text('The third member stays fixed. To change it, choose a different input/output pair.')
            body.append(fixed_row)
            actions = Gtk.Box(spacing=6)
            body.append(actions)
            swap = Gtk.Button(label='Swap input and output',css_classes=['flat','io-swap'])
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
        if app.family == 'parallel' and variant in PARALLEL_MULTISTAGE_VARIANTS:
            from parallel_multistage import count
            a, b = 'Shaft 1', f'Shaft {count(values)+1}'
        titles = {'forward': f'{a} → {b}', 'reverse': f'{b} → {a}'}
        source, target = (a, b) if active == 'forward' else (b, a)
        help_text = 'Choose which side drives the transmission.'
        if app.family in ('bevel','hypoid','face'):
            help_text = 'Positive speeds use right-hand rotation about pinion world +X and wheel world +Z. Swapping roles preserves the physical gears and bores.'
        box.add_css_class('direct-drive-body')
        box.set_spacing(11)
        box.append(label('Choose the driving member','drive-caption'))
        cards=Gtk.Box(spacing=8,homogeneous=True,css_classes=['drive-member-cards'])
        box.append(cards)
        card_state={}
        first = None
        for key, member in (('forward',a),('reverse',b)):
            button = Gtk.CheckButton(hexpand=True,css_classes=['drive-member-card'])
            button.set_direction(Gtk.TextDirection.RTL)
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9,hexpand=True)
            content.set_direction(Gtk.TextDirection.LTR)
            title=label(member,'drive-member-name');title.set_width_chars(1)
            content.append(title)
            role=label('Input' if key==active else 'Output','drive-member-role')
            hint=label('Motor' if key==active else 'Load','drive-member-hint')
            roles_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=2)
            roles_box.append(role);roles_box.append(hint);content.append(roles_box)
            for text in (title,role,hint):text.set_direction(Gtk.TextDirection.LTR)
            button.set_child(content)
            check=button.get_first_child()
            if check is not content:
                check.set_valign(Gtk.Align.START);check.set_margin_top(2)
            button.set_tooltip_text(titles[key])
            if first:
                button.set_group(first)
            else:
                first = button
            button.set_active(key == active)

            def toggled(widget, key=key):
                if widget.get_active() and (not app.building):
                    commit({'io_scheme': key})
            button.connect('toggled', toggled)
            def roles(widget,*_,role=role,hint=hint,key=key):
                role.set_text('Input' if widget.get_active() else 'Output')
                hint.set_text('Motor' if widget.get_active() else 'Load')
                if widget.get_active() and 'direction' in card_state:card_state['direction'].set_text(titles[key])
            button.connect('notify::active',roles)
            cards.append(button)
            app.io_mode_buttons[key] = button
        direction=label(titles[active],'drive-direction')
        card_state['direction']=direction
        direction.set_halign(Gtk.Align.CENTER);box.append(direction)
        if app.family in ('bevel','hypoid','face'):box.append(label(help_text))
        if app.family=='parallel' and variant in PARALLEL_MULTISTAGE_VARIANTS:
            result=label('','io-result')
            box.append(result)
        else:
            result=label('','drive-result-value')
            result.set_wrap(False)
            result_row=Gtk.Box(spacing=4,css_classes=['drive-result'])
            caption=label('Nominal output','drive-result-title');caption.set_hexpand(True)
            for widget in (caption,result):widget.set_valign(Gtk.Align.BASELINE)
            unit=label('rpm','drive-result-unit');unit.set_valign(Gtk.Align.BASELINE)
            result_row.append(caption);result_row.append(result);result_row.append(unit)
            box.append(result_row)
        app.io_results.append((0, result))
    box.set_tooltip_text('Interfaces follow the selected arrangement and are visible when Supports is enabled in the preview.')
    paired=app.family not in TRIPLES
    reset = Gtk.Button(label='Reset arrangement' if paired else 'Reset default arrangement',css_classes=['flat','drive-reset'] if paired else [])
    reset.get_child().set_wrap(True)
    if paired:
        from workspace_ui import workspace_glyph
        reset_body=Gtk.Box(spacing=6,halign=Gtk.Align.CENTER)
        reset_body.append(workspace_glyph('reset',reset));reset_body.append(Gtk.Label(label='Reset arrangement'))
        reset.set_child(reset_body)
    reset.connect('clicked', lambda _: commit({'io_scheme': default(app.family), **({'io_scheme2': default(app.family)} if 'io_scheme2' in app.option_values else {})}))
    box.append(reset)
    app.io_frame.set_label('Drive · input and output')
    app.io_frame.get_label_widget().set_wrap(True)

def update(app, design):
    note = getattr(app, 'io_policy_note', None)
    if note is not None and design is not None:
        assessment = design.analysis.get('backdrivability', {})
        note.set_text(assessment.get('message', ''))
        note.set_visible(assessment.get('status') != 'not_evaluated')
    if design is None:
        for _, widget in app.io_results:
            if widget.has_css_class('drive-result-value'):
                widget.set_text('—');widget.set_tooltip_text('Result out of date · correct the parameters.')
            else:widget.set_text('Result out of date · correct the parameters.')
        return
    if design.family == 'wolfrom':
        rates = design.analysis['kinematics']['rates_rpm']
        for _, widget in app.io_results:
            if widget.has_css_class('drive-result-value'):
                rpm=rates['output'];widget.set_text(f'{rpm:.2f}' if .005<=abs(rpm)<1e7 or rpm==0 else f'{rpm:.2e}')
                widget.set_tooltip_text(None)
                continue
            widget.set_text('Sun input: {sun:+.9g} rpm\nCommon carrier: {carrier:+.9g} rpm\nCompound spin: {planet:+.9g} rpm\nOutput ring: {output:+.9g} rpm\nFirst ring: 0 rpm · signs about +Z'.format(**rates))
        return
    if design.family == 'differential':
        q = design.analysis['kinematics']['rates_rpm']
        for _, widget in app.io_results:
            widget.set_text(f"Side output A / B: {q['side_a']:+.3g} / {q['side_b']:+.3g} rpm\nInternal spider spin: {q['spider_spin']:+.3g} rpm relative to carrier" if design.values.get('configuration')=='classic' else f"Carrier tilt: {q['carrier']:+.3g} rpm\nOutput spin relative to carrier: {q['output_spin']:+.3g} rpm")
        return
    if design.family == 'parallel' and design.values.get('variant') in PARALLEL_MULTISTAGE_VARIANTS:
        rates = design.analysis['kinematics']['shaft_rates_rpm']
        for _, widget in app.io_results:
            widget.set_text('\n'.join(f'Shaft {i+1}: {rpm:+.9g} rpm' for i, rpm in enumerate(rates)))
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
            if widget.has_css_class('drive-result-value'):
                rpm=output['rpm'] if output else None
                widget.set_text('—' if rpm is None else f'{rpm:.2f}' if .005<=abs(rpm)<1e7 or rpm==0 else f'{rpm:.2e}')
                widget.set_tooltip_text(None)
            else:widget.set_text(f"Nominal output: {output['rpm']:+.2f} rpm" if output else 'Updated results below the preview.')
        if design.analysis.get('mount_interfaces'):
            if widget.has_css_class('drive-result-value'):widget.set_tooltip_text('Hubs and flanges adapted to the arrangement.')
            else:widget.set_text(widget.get_text() + '\nHubs and flanges adapted to the arrangement.')
