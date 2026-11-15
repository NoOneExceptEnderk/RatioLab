# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK finite search controller. Worker input and every callback belong to one revision."""
from copy import deepcopy
from math import isfinite, prod
from pathlib import Path
from sys import float_info
from threading import Event, Thread
from time import monotonic
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio
from geometry import generate, INTEGER, VARIANTS
from project_document import equivalent
from ratio_display import ratio_parts
from workspace_tools import actions, details, heading, model_text
from combination_search import (FAMILIES, COUNT_KEYS, Settings, exceeds_quick_limit, matches, nominal_bounds,
                                nominal_diameter, parse_grid, search, variables)
from quick_combination_search import (RADIAL, TEETH, available_variants, bearing_modes, fixed_connection,
                                      parse_ratio, quick_search, QuickResult, size_text, stage_count, variant_teeth)
from gui_workflow import choice_dropdown, bind_numeric_entry, numeric_value, numeric_snapshot_text, set_numeric_value


def label(text):
    return Gtk.Label(label=text, xalign=0, wrap=True, selectable=False, max_width_chars=32)


class Controller:
    def __init__(self, app, container):
        self.app = app
        self.serial = 0
        self.thread = None
        self.cancel = None
        self.result = None
        self.snapshot = None
        self.revision = None
        self.design_key = None
        self.window = None
        self.alive = True
        self.page = 0
        self.form_key = None
        self.title = 'Find combinations'
        self.quick = False
        self.quick_timer = 0
        self.summary = label('Finite ratio and nominal envelope search')
        container.register('search', self)
        app.win.connect('unrealize', lambda *_: self.close())

    def key(self, design):
        return (design.family, deepcopy(design.values)) if design else None

    def changed(self, snapshot):
        if self.snapshot is not None and not equivalent(snapshot, self.snapshot):
            self.invalidate('Model changed · search results are out of date')

    def refreshed(self, design):
        if self.design_key is not None and self.key(design) != self.design_key:
            self.invalidate('Geometry changed · run a new search')
        if not self.window or not hasattr(self, 'axes') or getattr(self, 'populating', False):
            return
        key = (design.family, design.values.get('variant'), design.values.get('double_style')) if design else None
        if design is not None and key != self.form_key:
            self.populate()
            message = ('Model changed · review the quick search settings' if self.quick else
                       'Family or variant changed · ranges and ratio reset to the current model. Review settings before Search.')
            self.status.set_text(message)
            return
        self.unavailable = ('Invalid current configuration. Complete the model numeric fields first.' if design is None else
                            'Ratio search requires a single fixed input/output ratio. Select a supported reducer assembly.' if design.family not in FAMILIES else None)
        if design is None:
            self.context.set_text(model_text(None))
        else:
            self.update_context(design)
            for name, (locked, custom, _) in self.axes.items():
                value = design.values[name]
                self.axes[name] = (locked, custom, value)
                low, high = self.axis_controls[name]['bounds']
                self.axis_controls[name]['current'].set_text(f'Current: {value:g} · allowed {low:g}–{high:g}')
        self.sync_construction(design)
        self.update_domain()

    def update_context(self, design):
        values = design.values
        ratio = design.analysis.get('signed_ratio')
        context = model_text(design)
        if ratio is not None:
            context += '\nRatio (input/output): ' + ''.join(ratio_parts(ratio, 10))
        self.context.set_text(context)
        self.context.set_tooltip_text(f'{design.family} / {values.get("variant", "standard")} · I/O {values.get("io_scheme", "fixed")}' + (f' / stage 2 {values["io_scheme2"]}' if 'io_scheme2' in values else ''))

    def invalidate(self, message='Results out of date · run a new search'):
        if self.quick_timer:
            GLib.source_remove(self.quick_timer)
            self.quick_timer = 0
        self.serial += 1
        if self.cancel is not None:
            self.cancel.set()
        self.cancel = None
        self.result = None
        self.snapshot = None
        self.design_key = None
        self.summary.set_text(message)
        if self.window:
            self.status.set_text(message)
            self.selection_summary.set_text(message)
            self.report.get_buffer().set_text(message)
            self.clear_rows()
            self.apply_button.set_sensitive(False)
            self.save_button.set_sensitive(False)
            self.cancel_button.set_sensitive(False)
            self.run_button.set_sensitive(False)

    def close(self):
        self.invalidate('Search closed')
        self.alive = False
        if self.window:
            self.window.destroy()
            self.window = None

    def open(self, quick=None):
        if self.window:
            self.window.present()
            if quick is not None:
                self.set_mode(quick)
                self.focus_target()
            return
        self.quick = bool(quick)
        self.preview = None
        self.preview_watch = None
        win = self.app.tools.panel('search')
        self.window = win
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        win.set_child(box)
        win.connect('map', lambda *_: self.sync_preview_visibility())
        win.connect('unmap', lambda *_: self.sync_preview_visibility())
        self.fields = {}
        self.field_errors = {}
        self.context_heading = heading(box, 'Model examined')
        self.context = label(model_text(self.app.design))
        box.append(self.context)
        self.install_quick(box)
        setup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.setup = details(box, 'Edit search settings', setup)
        self.setup.set_expanded(True)
        setup.append(label('1. Desired ratio'))
        setup.append(label('Ratio = |input speed / output speed|'))
        setup.append(label('For 1:3, enter about 0.333333. Choose the rotation direction separately.'))
        for key, title, value in (('target', 'Desired ratio', '3'), ('tolerance', 'Allowed error ± (%)', '1')):
            self.add_field(setup, key, title, value)
        self.ratio_hint = label('')
        setup.append(self.ratio_hint)
        setup.append(label('Output direction relative to input'))
        self.direction = choice_dropdown(['Either direction', 'Same (+)', 'Opposite (−)'])
        setup.append(self.direction)
        self.direction.connect('notify::selected', lambda *_: self.request_changed())
        setup.append(label('Compare results by'))
        self.ranking = choice_dropdown(['Closest ratio', 'Smallest envelope', 'Highest usable contact ratio'])
        self.ranking.connect('notify::selected', lambda *_: self.request_changed())
        setup.append(self.ranking)
        setup.append(label('Direction uses the current input/output members and their displayed axes.'))
        self.envelope_summary = label('')
        setup.append(self.envelope_summary)
        envelope = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.envelope = details(setup, 'Overall size limits (mm)', envelope)
        for key in ('x', 'y', 'z'):
            self.add_field(envelope, key, f'Maximum {key.upper()} (mm)', '1000')
        envelope.append(label('All components, including hidden supports and housing; world XYZ in the export pose. Sampled preview/STL surfaces, not a motion sweep. Analytic STEP circles may extend slightly beyond these bounds.'))
        setup.append(label('2. Parameters to explore'))
        setup.append(label('Choose Vary, then set From, To and Step. Counts start near the current model; other dimensions stay fixed.'))
        self.axes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        setup.append(self.axes_box)
        self.reload_button = Gtk.Button(label='Reset ranges & ratio to model')
        self.reload_button.connect('clicked', lambda _: self.populate())
        setup.append(self.reload_button)
        advanced = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.advanced = details(setup, 'Advanced · budgets & technical details', advanced)
        self.add_field(advanced, 'contact', 'Minimum usable contact ratio (0 = no filter)', '0')
        self.add_field(advanced, 'budget', 'Maximum candidates', '50000')
        self.add_field(advanced, 'seconds', 'Time limit (seconds)', '30')
        advanced.append(label('Finite local search, not a continuous or global optimum. All other dimensions, variants, stages and I/O stay fixed. Every proposal passes the generator; this is not an interference or strength check. Stop is cooperative: one generation or surface section may finish first.'))
        self.report = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.report._ratiolab_localize_report = True
        report_scroll = Gtk.ScrolledWindow()
        report_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        report_scroll.set_min_content_height(100)
        report_scroll.set_child(self.report)
        self.scope = label('')
        setup.append(self.scope)
        self.status = label('Choose a ratio, then Search.' if self.quick else 'Choose a ratio and ranges, then Search.')
        self.progress = Gtk.ProgressBar()
        buttons = actions(box)
        self.run_button = Gtk.Button(label='Search')
        self.run_button.connect('clicked', lambda _: self.start())
        buttons.append(self.run_button)
        self.cancel_button = Gtk.Button(label='Cancel')
        self.cancel_button.connect('clicked', lambda _: self.stop())
        self.cancel_button.set_sensitive(False)
        buttons.append(self.cancel_button)
        self.results_button = Gtk.Button(label='Results')
        self.results_button.connect('clicked', lambda _: self.setup.set_expanded(False))
        self.results_button.set_visible(False)
        buttons.append(self.results_button)
        run_actions = buttons
        compare = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.compare = compare
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.connect('row-selected', self.selected)
        self.result_scroll = Gtk.ScrolledWindow()
        self.result_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.result_scroll.set_min_content_height(110)
        self.result_scroll.set_max_content_height(190)
        self.result_scroll.set_propagate_natural_height(True)
        self.result_scroll.set_child(self.list)
        compare.append(self.result_scroll)
        pages = Gtk.Box(spacing=5)
        self.page_buttons = []
        for title, delta in (('Prev', -1), ('Next', 1)):
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, d=delta: self.change_page(d))
            pages.append(button)
            self.page_buttons.append(button)
        self.page_label = label('')
        self.page_label.set_hexpand(True)
        pages.append(self.page_label)
        compare.append(pages)
        self.pages = pages
        self.selection_summary = label('Select a proposal to compare it with the current model.')
        compare.append(self.selection_summary)
        self.selection_summary.set_visible(False)
        self.preview_inline = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, visible=False)
        self.preview_inline.append(label('Proposal preview'))
        compare.prepend(self.preview_inline)
        self.preview_error = label('')
        self.preview_error.set_visible(False)
        compare.prepend(self.preview_error)
        self.quick_outcome = label('')
        self.quick_outcome.set_visible(False)
        self.quick_outcome.add_css_class('search-proposal-summary')
        box.append(self.quick_outcome)
        buttons = actions(box)
        self.apply_button = Gtk.Button(label='Apply selected')
        self.apply_button.connect('clicked', lambda _: self.apply_selected())
        self.apply_button.set_sensitive(False)
        self.apply_button.set_tooltip_text('Apply this candidate as one Undo step')
        self.apply_button.add_css_class('primary')
        buttons.append(self.apply_button)
        self.save_button = Gtk.Button(label='Save report…')
        self.save_button.connect('clicked', lambda _: self.save())
        self.save_button.set_sensitive(False)
        buttons.append(self.save_button)
        def close(*_):
            self.quick_draft = (self.construction_key, {k: e.get_text() for k, e in self.quick_fields.items()},
                                {k: self.choice(k) for k in self.quick_choices},
                                self.construction_details.get_expanded())
            self.draft = dict(identity=self.app.document.token[0], key=self.form_key,
                fields={key: numeric_snapshot_text(entry) for key, entry in self.fields.items()},
                direction=self.direction.get_selected(), ranking=self.ranking.get_selected(),
                axes={key: dict(locked=controls[0].get_active(), mode=self.axis_controls[key]['mode'].get_selected(),
                    inputs=[numeric_snapshot_text(entry) for entry in self.axis_controls[key]['inputs']],
                    custom=controls[1].get_text()) for key, controls in self.axes.items()})
            self.invalidate('Search window closed')
            self.window = None
            return False
        win.connect('close-request', close)
        self.setup.connect('notify::expanded', lambda *_: self.update_step_view())
        self.result_heading = heading(box, 'Results')
        box.append(self.status)
        box.append(compare)
        self.report_details = details(box, 'Full search report', report_scroll)
        self.report_details.set_visible(False)
        self.populate()
        draft = getattr(self, 'draft', None)
        if draft and draft['identity'] == self.app.document.token[0] and draft['key'] == self.form_key:
            self.populating = True
            try:
                for key, value in draft['fields'].items():
                    self.fields[key].set_text(value)
                self.direction.set_selected(draft['direction'])
                self.ranking.set_selected(draft['ranking'])
                for key, row in draft['axes'].items():
                    if key not in self.axes:
                        continue
                    self.axes[key][0].set_active(row['locked'])
                    self.axes[key][1].set_text(row['custom'])
                    self.axis_controls[key]['mode'].set_selected(row['mode'])
                    for entry, value in zip(self.axis_controls[key]['inputs'], row['inputs']):
                        entry.set_text(value)
                    self.update_axis_view(key)
            finally:
                self.populating = False
            self.update_domain()
        from workspace_tools import status_actions
        status_row,self.status_badge=status_actions(self.status,run_actions)
        win.pin(self.quick_outcome, status_row, buttons, self.progress)
        draft = getattr(self, 'quick_draft', None)
        if draft and draft[0] == self.construction_key:
            _, fields, choices, expanded = draft
            self.populating = True
            try:
                for key, value in fields.items():
                    self.quick_fields[key].set_text(value)
                for key, value in choices.items():
                    if key in self.quick_choices and value in self.quick_choices[key][0]:
                        keys, control = self.quick_choices[key]
                        control.set_selected(keys.index(value))
                self.construction_details.set_expanded(expanded)
            finally:
                self.populating = False
        self.set_mode(self.quick)
        win.present()
        self.focus_target()
        self.app.language.refresh()

    def focus_target(self):
        entry = self.quick_fields['target'] if self.quick else self.fields['target']
        if not self.quick:
            self.setup.set_expanded(True)
        entry.grab_focus()
        entry.select_region(0, -1)

    def set_mode(self, quick):
        if quick != self.quick:
            self.quick = quick
            self.invalidate('Search settings changed · run a new search')
        self.quick_box.set_visible(quick)
        self.setup.set_visible(not quick)
        self.context_heading.set_visible(not quick)
        self.context.set_visible(not quick)
        self.result_heading.set_visible(not quick)
        self.status.set_visible(not quick)
        self.mode_button.set_label('Advanced search…' if quick else 'Quick search…')
        self.apply_button.set_label('Apply proposal' if quick else 'Apply selected')
        self.update_step_view()
        self.update_domain()

    def install_quick(self, box):
        self.quick_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        box.append(self.quick_box)
        self.quick_fields, self.quick_rows = {}, {}
        for key, title in (('target', 'Target ratio'), ('diameter', 'Maximum diameter (mm)'),
                           ('x', 'Maximum X (mm)'), ('y', 'Maximum Y (mm)')):
            row = Gtk.Box(spacing=7)
            caption = label(title)
            caption.set_hexpand(True)
            row.append(caption)
            entry = Gtk.Entry(width_chars=8, max_width_chars=10, max_length=64)
            entry.set_placeholder_text('e.g. 5:1' if key == 'target' else 'Optional')
            entry.update_property([Gtk.AccessibleProperty.LABEL], [title])
            entry.connect('changed', lambda *_: self.request_changed())
            entry.connect('activate', lambda *_: self.start() if self.run_button.get_sensitive() else None)
            row.append(entry)
            self.quick_box.append(row)
            self.quick_rows[key] = row
            self.quick_fields[key] = entry
        self.construction_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.construction_details = details(self.quick_box, 'Construction', self.construction_box)
        self.quick_error = label('')
        self.quick_error.add_css_class('error')
        self.quick_box.append(self.quick_error)
        self.quick_choices = {}
        self.construction_draft = {}
        self.construction_key = None
        self.mode_button = Gtk.Button(css_classes=['flat'], halign=Gtk.Align.START)
        def switch(*_):
            self.set_mode(not self.quick)
            self.focus_target()
        self.mode_button.connect('clicked', switch)
        box.append(self.mode_button)

    def add_choice(self, box, key, title, choices, selected, changed):
        caption = label(title)
        caption.add_css_class('field-label')
        box.append(caption)
        keys = tuple(choices)
        control = choice_dropdown(list(choices.values()))
        control.update_property([Gtk.AccessibleProperty.LABEL], [title])
        control.set_selected(keys.index(selected) if selected in choices else 0)
        box.append(control)
        self.quick_choices[key] = keys, control
        control.connect('notify::selected', changed)

    def choice(self, key, default=None):
        if key in self.quick_choices:
            keys, control = self.quick_choices[key]
            return keys[control.get_selected()]
        return default

    def sync_construction(self, design):
        base = design.values if design else {}
        family = design.family if design else None
        key = family, self.app.document.token[0], tuple(base.get(k) for k in (
            'variant', 'io_scheme', 'io_scheme2', 'bearing_mode', 'bearing',
            'input_shaft_profile', 'output_shaft_profile', 'eccentric_design'))
        if key == self.construction_key:
            return
        changed_family = self.construction_key is None or key[:2] != self.construction_key[:2]
        changed_variant = self.construction_key is not None and key[2][0] != self.construction_key[2][0]
        self.construction_key = key
        self.populating = True
        try:
            while (child := self.construction_box.get_first_child()):
                self.construction_box.remove(child)
            self.quick_choices.clear()
            self.construction_draft.clear()
            available = family in FAMILIES
            for name, row in self.quick_rows.items():
                row.set_visible(name == 'target' or available and ((name == 'diameter') == (family in RADIAL)))
                if changed_family:
                    self.quick_fields[name].set_text('')
            self.construction_details.set_visible(available)
            if available:
                ratio = abs(design.analysis['signed_ratio'])
                if changed_family or changed_variant:
                    self.quick_fields['target'].set_text(format(ratio, '.15g'))
                self.variant_choices(family, base)
                self.connection_choices(family, base)
        finally:
            self.populating = False

    def variant_choices(self, family, base):
        box = self.construction_box
        self.construction_options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        def changed(*_):
            self.connection_choices(family, base)
            self.request_changed()
            self.app.language.refresh()
        variants = available_variants(family, base['variant'])
        if family in ('parallel', 'planetary'):
            stages = {stage_count(family, variant) for variant in variants}
            self.add_choice(box, 'stages', 'Number of stages',
                            {None: 'Automatic', **{n: str(n) for n in sorted(stages)}},
                            stage_count(family, base['variant']), changed)
        if family in ('planetary', 'parallel', 'internal', 'wolfrom'):
            self.add_choice(box, 'teeth', 'Tooth type', {None: 'Automatic', **TEETH},
                            variant_teeth(family, base['variant']), changed)
        elif family == 'cycloidal':
            self.add_choice(box, 'variant', 'Cycloidal discs', {None: 'Automatic', **variants},
                            base['variant'], changed)
        elif len(variants) > 1:
            self.add_choice(box, 'variant', 'Tooth type', {None: 'Automatic', **variants},
                            base['variant'], changed)
        box.append(self.construction_options)

    def selected_variants(self, family, base):
        return tuple(variant for variant in available_variants(family, base['variant'])
                     if self.choice('variant') in (None, variant)
                     and self.choice('stages') in (None, stage_count(family, variant))
                     and self.choice('teeth') in (None, variant_teeth(family, variant)))

    def connection_choices(self, family, base):
        from catalog import BEARINGS, MODES
        from shaft_connections import PORT_LABELS, PROFILES, profile_key, targets
        box = self.construction_options
        variants = self.selected_variants(family, base)
        candidates = [dict(base, variant=v) for v in variants]
        keys = ('bearing_mode', 'bearing', 'input_shaft_profile', 'output_shaft_profile')
        self.construction_draft.update({k: self.choice(k) for k in keys if k in self.quick_choices})
        previous = {k: self.construction_draft.get(k, base.get(k)) for k in keys}
        while (child := box.get_first_child()):
            box.remove(child)
        for key in keys:
            self.quick_choices.pop(key, None)
        if not variants:
            return
        modes = {k: title for k, title in MODES.items()
                 if any(k in bearing_modes(family, values) for values in candidates)}
        mode = previous['bearing_mode'] if previous['bearing_mode'] in modes else 'manual'
        if len(modes) > 1:
            def mode_changed(*_):
                self.connection_choices(family, base)
                self.request_changed()
                self.app.language.refresh()
            self.add_choice(box, 'bearing_mode', 'Catalog ball bearings', modes, mode, mode_changed)
            if mode != 'manual':
                self.add_choice(box, 'bearing', 'NSK bearing',
                                {code: b.label for code, b in BEARINGS.items()}, previous['bearing'],
                                lambda *_: self.request_changed())
        elif base.get('eccentric_design') == 'fdm_bolted':
            box.append(label('Fixed bearings · NSK 6804'))
        for port in ('input', 'output'):
            key = profile_key(port)
            if any(port in targets(family, values) for values in candidates):
                self.add_choice(box, key, PORT_LABELS[port], PROFILES, previous[key],
                                lambda *_: self.request_changed())
            else:
                box.append(label(PORT_LABELS[port]))
                box.append(label(fixed_connection(family, base, port)))

    def read_quick(self):
        target, direction = parse_ratio(self.quick_fields['target'].get_text())
        design = self.app.design
        variants = self.selected_variants(design.family, design.values)
        if not variants:
            raise ValueError('Two-stage planetary reducers support spur or double-helical teeth.')
        limits = {}
        for key in ('diameter', 'x', 'y'):
            if not self.quick_rows[key].get_visible():
                continue
            text = self.quick_fields[key].get_text().strip().replace(',', '.')
            if not text:
                continue
            try:
                number = float(text)
                if not isfinite(number) or number <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError('Enter a positive size in mm.') from None
            limits[key] = number
        settings = Settings(target=target, direction=direction,
                            max_xyz=(limits.get('x', float_info.max), limits.get('y', float_info.max), float_info.max),
                            max_candidates=80, max_seconds=15, max_results=12)
        options = {k: self.choice(k) for k in ('bearing_mode', 'bearing', 'input_shaft_profile',
                                               'output_shaft_profile') if k in self.quick_choices}
        return settings, variants, options, limits.get('diameter')

    def sync_preview_visibility(self):
        active = bool(self.preview and self.window and self.window.get_mapped())
        if active:
            self.place_preview()
            if self.preview_watch is None:
                clock = self.window.get_frame_clock()
                if clock is not None:
                    self.preview_watch = clock, clock.connect('after-paint', self.place_preview)
        else:
            self.app.search_preview.set_visible(False)
            self.preview_inline.set_visible(False)
            if self.preview_watch:
                clock, handler = self.preview_watch
                clock.disconnect(handler)
                self.preview_watch = None

    def place_preview(self, *_):
        dock = self.app.tools
        overlay = self.app.search_preview
        inset = (dock.box.get_width() or dock.normal_width()) + dock.box.get_margin_end()
        in_workspace = not dock.expanded and self.app.preview_overlay.get_width() - inset >= 120
        if overlay.get_margin_end() != inset:
            overlay.set_margin_end(inset)
        parent = overlay if in_workspace else self.preview_inline
        if self.preview.get_parent() is not parent:
            self.detach_preview(self.preview)
            if in_workspace:
                overlay.set_child(self.preview)
            else:
                self.preview_inline.append(self.preview)
            self.preview.set_size_request(1, 1 if in_workspace else 160)
        healthy = self.preview.get_error() is None and not self.preview.failure
        overlay.set_visible(in_workspace and healthy)
        self.preview_inline.set_visible(not in_workspace and healthy)

    def detach_preview(self, view):
        parent = view.get_parent()
        if parent is self.app.search_preview:
            parent.set_child(None)
        elif parent is self.preview_inline:
            parent.remove(view)

    def clear_preview(self):
        view, self.preview = self.preview, None
        self.sync_preview_visibility()
        if view is not None:
            self.detach_preview(view)
        self.preview_error.set_visible(False)

    def preview_proposal(self, proposal):
        self.clear_preview()
        try:
            from preview3d import Preview3D
            design = generate(self.app.family, deepcopy(proposal.values), quality=self.app.design.quality)
            view = Preview3D()
            view.set_size_request(1, 1)
            view.show_support = True
            view.set_theme(self.app.canvas.theme, self.app.canvas.palette)
            view.set_design(design)
            self.preview = view
            self.app.search_preview_caption.set_text('Proposal preview · ' + ''.join(ratio_parts(proposal.ratio, 8)))
            view.connect('realize', self.preview_failed)
            self.sync_preview_visibility()
        except (ValueError, RuntimeError) as error:
            self.preview_error.set_text(f'Proposal preview unavailable: {error}')
            self.preview_error.set_visible(True)

    def preview_failed(self, view):
        error = view.get_error()
        if error or view.failure:
            message = error.message if error else view.failure
            self.preview_error.set_text(f'Proposal preview unavailable: {message}')
            self.preview_error.set_visible(True)

    def numeric_entry(self, text):
        entry = Gtk.Entry(width_chars=5, max_width_chars=8,
                          hexpand=True, input_purpose=Gtk.InputPurpose.NUMBER)
        bind_numeric_entry(entry)
        set_numeric_value(entry, float(text))
        return entry

    def add_field(self, parent, key, title, value):
        row = Gtk.Box(spacing=6)
        row.append(label(title))
        entry = self.numeric_entry(value)
        row.append(entry)
        parent.append(row)
        error = label('')
        error.add_css_class('error')
        error.set_visible(False)
        parent.append(error)
        self.fields[key] = entry
        self.field_errors[key] = error
        entry.connect('changed', lambda *_: self.request_changed())

    def request_changed(self):
        if getattr(self, 'populating', False):
            return
        self.invalidate('Search request changed · review inputs, then Search')
        if self.window and hasattr(self, 'axes'):
            self.update_domain()
            if self.quick and self.run_button.get_sensitive():
                self.quick_timer = GLib.timeout_add(500, self.run_quick_draft)

    def run_quick_draft(self):
        if self.window and self.window.get_mapped() and self.quick and self.run_button.get_sensitive():
            if self.thread is not None and self.thread.is_alive():
                return True
            self.quick_timer = 0
            self.start()
        self.quick_timer = 0
        return False

    def populate(self):
        if not self.window:
            return
        self.invalidate('Choose a ratio to compare proposals' if self.quick else
                        'Choose ranges, then Search to compare proposals')
        self.setup.set_expanded(True)
        self.populating = True
        while (child := self.axes_box.get_first_child()):
            self.axes_box.remove(child)
        self.axes = {}
        self.axis_controls = {}
        self.titles = {}
        app = self.app
        app.project_changed()
        valid = app.refresh()
        self.form_key = (app.family, app.design.values.get('variant'), app.design.values.get('double_style')) if valid else None
        self.unavailable = None
        if not valid:
            self.unavailable = 'Invalid current configuration. Complete the model numeric fields first.'
        elif app.family not in FAMILIES:
            self.unavailable = 'Ratio search requires a single fixed input/output ratio. Select a supported reducer assembly.'
        else:
            values = app.design.values
            self.update_context(app.design)
            specs = variables(app.family, values)
            specs.sort(key=lambda spec: spec[0] not in COUNT_KEYS[app.family] or spec[0] == 'planets')
            more = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            more_expander = Gtk.Expander(label='More dimensions')
            more_expander.set_child(more)
            for key, title, _, lo, hi, step in specs:
                if values.get('io_scheme') == 'reverse':
                    title = {'Input pinion teeth': 'Pinion teeth', 'Driven wheel teeth': 'Wheel teeth'}.get(title, title)
                self.titles[key] = title
                value = values[key]
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                (self.axes_box if key in COUNT_KEYS[app.family] else more).append(row)
                row.append(label(title))
                current = label(f'Current: {value:g} · allowed {lo:g}–{hi:g}')
                row.append(current)
                choice = Gtk.Box(spacing=10)
                locked = Gtk.CheckButton(label='Keep current')
                vary = Gtk.CheckButton(label='Vary')
                vary.set_group(locked)
                locked.set_active(key not in COUNT_KEYS[app.family] or key == 'planets')
                vary.set_active(not locked.get_active())
                choice.append(locked)
                choice.append(vary)
                row.append(choice)
                controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row.append(controls)
                mode = choice_dropdown(['Range', 'Custom values (advanced)'])
                controls.append(mode)
                ranges = Gtk.Box(spacing=4, homogeneous=True)
                controls.append(ranges)
                low, high, stride = value, value, step
                if key in INTEGER:
                    low, high = max(lo, value-4), min(hi, value+4)
                    stride = 2 if app.family == 'harmonic' and key == 'teeth' else 1
                inputs = []
                for caption, initial in (('From', low), ('To', high), ('Step', stride)):
                    column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                    column.append(label(caption))
                    entry = self.numeric_entry(initial)
                    entry.set_tooltip_text(title + ' · ' + caption)
                    column.append(entry)
                    ranges.append(column)
                    inputs.append(entry)
                    entry.connect('changed', lambda *_: self.request_changed())
                custom = Gtk.Entry(text=f'{low:.15g}:{high:.15g}:{stride:.15g}', width_chars=8, max_width_chars=12, hexpand=True)
                custom.set_placeholder_text('e.g. 18, 20, 24 or 18:24:2')
                custom.set_tooltip_text('Explicit comma-separated values or inclusive low:high:step. Switching modes preserves both drafts.')
                controls.append(custom)
                hint = label('Custom values: comma-separated numbers or low:high:step. Each mode keeps its own values.')
                controls.append(hint)
                error = label('')
                error.add_css_class('error')
                row.append(error)
                self.axes[key] = (locked, custom, value)
                self.axis_controls[key] = dict(title=title, bounds=(lo, hi), mode=mode, ranges=ranges,
                                               inputs=inputs, custom=custom, hint=hint, error=error, current=current,
                                               controls=controls, vary=vary)
                def toggle(*_, k=key):
                    self.update_axis_view(k)
                    self.request_changed()
                locked.connect('toggled', toggle)
                mode.connect('notify::selected', toggle)
                def custom_changed(_, k=key):
                    # Preserve the old controller's programmatic custom-entry interface.
                    if not self.populating:
                        self.axis_controls[k]['mode'].set_selected(1)
                        self.request_changed()
                custom.connect('changed', custom_changed)
                self.update_axis_view(key)
            self.axes_box.append(more_expander)
            ratio = app.design.analysis['signed_ratio']
            set_numeric_value(self.fields['target'], abs(ratio))
        self.populating = False
        self.sync_construction(app.design if valid else None)
        self.update_domain()

    def update_axis_view(self, key):
        c = self.axis_controls[key]
        custom = c['mode'].get_selected() == 1
        c['controls'].set_visible(not self.axes[key][0].get_active())
        c['ranges'].set_visible(not custom)
        c['custom'].set_visible(custom)
        c['hint'].set_visible(custom)

    def update_domain(self):
        if self.quick:
            error = self.unavailable
            if not error:
                try:
                    self.read_quick()
                except ValueError as exc:
                    error = str(exc)
            self.quick_error.set_text(error or '')
            self.quick_error.set_visible(bool(error))
            self.run_button.set_sensitive(not error and self.cancel is None)
            return
        if self.unavailable:
            self.scope.set_text(self.unavailable)
            self.run_button.set_sensitive(False)
            return
        errors = []
        try:
            self.read_settings()
        except ValueError as error:
            errors.append(str(error))
        try:
            target = numeric_value(self.fields['target'])
            tolerance_percent = numeric_value(self.fields['tolerance'])
            Settings(target=target, tolerance_percent=tolerance_percent).validate()
            tolerance = tolerance_percent / 100
            low, high = target*(1-tolerance), target*(1+tolerance)
            interval = f'{low:.6g}–{high:.6g}' if isfinite(high) else f'≥ {low:.6g} (upper bound exceeds display range)'
            output = 1000/target
            example = f'1,000 rpm input → {output:.6g} rpm output magnitude.' if isfinite(output) else 'Output speed magnitude = input speed ÷ ratio.'
            self.ratio_hint.set_text(f'Accepted |ratio|: {interval}. {example}')
        except ValueError:
            self.ratio_hint.set_text('Enter a positive desired ratio and an error from 0 to less than 100%.')
        self.envelope_summary.set_text('Size limits · XYZ ≤ ' + ' × '.join(self.fields[k].get_text() for k in ('x', 'y', 'z')) + ' mm')
        axes = {}
        for key in self.axes:
            control = self.axis_controls[key]
            message = ''
            if not self.axes[key][0].get_active():
                try:
                    axes[key] = self.read_axis(key)
                except ValueError as error:
                    message = str(error)
                    errors.append(message)
            control['error'].set_text(message)
            control['error'].set_visible(bool(message))
        count = prod(map(len, axes.values()))
        self.scope.set_text(('Fix: ' + errors[0] if errors else f'{count:,} finite candidates · {len(axes)} parameters vary'))
        self.run_button.set_sensitive(not errors and self.cancel is None and self.app.design is not None)

    def read_axis(self, key):
        c = self.axis_controls[key]
        try:
            if c['mode'].get_selected() == 1:
                values = parse_grid(c['custom'].get_text())
            else:
                texts = [numeric_snapshot_text(entry).strip() for entry in c['inputs']]
                # Range fields each accept one number, never a grid/list expression.
                numbers = [float(text) for text in texts]
                if not all(map(isfinite, numbers)):
                    raise ValueError('Use finite numbers for From, To and Step.')
                low, high, stride = numbers
                if high < low or stride <= 0:
                    raise ValueError('To must be at least From; Step must be positive.')
                if key in INTEGER and any(n != int(n) for n in numbers):
                    raise ValueError('Use whole numbers for this count, including Step.')
                values = parse_grid(':'.join(texts))
            lo, hi = c['bounds']
            if any(not lo <= v <= hi for v in values):
                raise ValueError(f'Values must be within {lo:g}–{hi:g}.')
            if key in INTEGER and any(v != int(v) for v in values):
                raise ValueError('Use whole numbers for this count.')
            return values
        except (ValueError, OverflowError) as error:
            message = str(error)
            if message.startswith('could not convert'):
                message = 'Enter finite numbers; use From, To and Step or an explicit custom list.'
            raise ValueError(f'{c["title"]}: {message}') from error

    def read_axes(self):
        return {key: self.read_axis(key) for key, (locked, _, _) in self.axes.items() if not locked.get_active()}

    def read_settings(self):
        titles = dict(target='Desired ratio', tolerance='Allowed error', x='Maximum X', y='Maximum Y', z='Maximum Z', budget='Maximum candidates', seconds='Time limit', contact='Minimum usable contact ratio')
        limits = dict(target=(0, float('inf')), tolerance=(0, 100), x=(0, float('inf')), y=(0, float('inf')), z=(0, float('inf')), budget=(1, 1000000), seconds=(0, 3600), contact=(0, float('inf')))
        values, errors = {}, []
        for key, entry in self.fields.items():
            message = ''
            try:
                value = numeric_value(entry)
                if not isfinite(value):
                    raise ValueError('Enter a finite number.')
                low, high = limits[key]
                if value < low or value > high or (key in ('target', 'x', 'y', 'z', 'seconds') and value == 0) or (key == 'tolerance' and value == 100):
                    raise ValueError({'target': 'Enter a ratio greater than zero.', 'tolerance': 'Use 0 to less than 100%.', 'budget': 'Use 1–1,000,000 candidates.', 'seconds': 'Use more than 0, up to 3,600 seconds.'}.get(key, 'Enter a positive size in mm.'))
                if key == 'budget' and value != int(value):
                    raise ValueError('Use a whole number of candidates.')
                values[key] = value
            except (ValueError, OverflowError) as error:
                message = str(error) if str(error) and not str(error).startswith('could not convert') else 'Enter a finite number.'
                errors.append(f'{titles[key]}: {message}')
            self.field_errors[key].set_text(message)
            self.field_errors[key].set_visible(bool(message))
            if message:
                entry.add_css_class('error')
            else:
                entry.remove_css_class('error')
        if errors:
            self.setup.set_expanded(True)
            if any(self.field_errors[k].get_visible() for k in ('x', 'y', 'z')):
                self.envelope.set_expanded(True)
            if any(self.field_errors[k].get_visible() for k in ('budget', 'seconds', 'contact')):
                self.advanced.set_expanded(True)
            raise ValueError(errors[0])
        ranking = ('ratio', 'compact', 'contact')[self.ranking.get_selected()]
        if (ranking == 'contact' or values['contact'] > 0) and self.app.family not in ('parallel', 'internal', 'planetary'):
            raise ValueError('Usable profile contact comparison requires cylindrical parallel, internal or planetary meshes.')
        settings = Settings(target=values['target'], tolerance_percent=values['tolerance'], direction=('either', 'same', 'opposite')[self.direction.get_selected()], max_xyz=tuple(values[k] for k in ('x', 'y', 'z')), max_candidates=int(values['budget']), max_seconds=values['seconds'], ranking=ranking, min_profile_contact=values['contact'])
        settings.validate()
        return settings

    def start(self, settings=None, axes=None):
        if not self.alive or self.app.busy or self.cancel is not None or not self.window:
            return
        if self.thread is not None and self.thread.is_alive():
            self.status.set_text('Previous search is stopping · try again shortly')
            return
        app = self.app
        app.project_changed()
        if not app.refresh():
            self.invalidate('Invalid current configuration · search blocked')
            return
        if app.family not in FAMILIES:
            self.invalidate('Ratio search requires a single fixed input/output ratio. Select a supported reducer assembly.')
            return
        key = (app.family, app.design.values.get('variant'), app.design.values.get('double_style'))
        if key != self.form_key:
            self.populate()
            self.status.set_text('Family or variant changed · grids reset; review them before Search')
            return
        try:
            if self.quick and (settings is not None or axes is not None):
                self.set_mode(False)
            quick = self.quick
            if quick:
                settings, variants, options, diameter = self.read_quick()
            else:
                settings = settings or self.read_settings()
                settings.validate()
                axes = self.read_axes() if axes is None else deepcopy(axes)
        except ValueError as error:
            self.invalidate('Invalid search request: '+str(error))
            return
        self.invalidate('Searching…')
        self.snapshot = deepcopy(app.project_snapshot())
        self.revision = app.document.token
        self.design_key = self.key(app.design)
        serial, revision = self.serial, self.revision
        base, family, quality = deepcopy(app.design.values), app.family, deepcopy(app.design.quality)
        event = Event()
        self.cancel = event
        self.run_button.set_sensitive(False)
        self.cancel_button.set_sensitive(True)
        self.progress.set_fraction(0)
        last = [0.]
        def progress(message, fraction):
            now = monotonic()
            if now-last[0] >= .1 or fraction == 1:
                last[0] = now
                GLib.idle_add(self.progress_update, serial, message, fraction)
        def worker():
            try:
                if quick:
                    result = quick_search(family, base, variants, options, settings, diameter, event, progress,
                                          quality=quality)
                else:
                    result = search(family, base, axes, settings, event, progress, quality=quality)
                result.revision = revision
                error = None
            except Exception as exc:
                result, error = None, f'Search failed: {type(exc).__name__}: {exc}'
            GLib.idle_add(self.finished, serial, result, error)
        self.thread = Thread(target=worker, name='RatioLab combinations', daemon=True)
        self.setup.set_expanded(False)
        self.thread.start()

    def current(self, serial):
        # Cancellation is cooperative: an old worker can finish after a new run.
        # Check both document history and raw fields still awaiting normalization.
        app = self.app
        return (self.alive and app.project_alive and serial == self.serial and self.snapshot is not None and app.document.token == self.revision and app.design is not None and equivalent(app.project_snapshot(), self.snapshot))

    def progress_update(self, serial, message, fraction):
        if self.current(serial):
            self.summary.set_text(message)
            if self.window:
                self.status.set_text(message)
                self.quick_outcome.set_visible(False)
                self.progress.set_fraction(fraction)
        return False

    def stop(self):
        if self.cancel is not None:
            self.cancel.set()
            self.summary.set_text('Cancelling search…')
            if self.window:
                self.status.set_text('Cancelling search…')
                self.cancel_button.set_sensitive(False)

    def finished(self, serial, result, error):
        if not self.current(serial):
            return False
        self.cancel = None
        if error:
            self.invalidate(error)
            self.update_domain()
            if self.quick:
                self.quick_outcome.set_text(error)
                self.quick_outcome.set_visible(True)
            return False
        self.result = result
        outcome = 'Complete finite search' if result.complete else 'PARTIAL search'
        if result.reason == 'cancelled':
            outcome = 'Search cancelled'
        message = f'{outcome}\n{result.visited}/{result.total} candidates · {len(result.proposals)} retained proposals'
        if result.reason and result.reason != 'cancelled':
            message += '\n' + result.reason
        if not result.proposals:
            if not result.complete:
                message += '\nNo proposals found in the candidates visited so far.'
            elif isinstance(result, QuickResult):
                message += '\nNo matching proposals.'
            else:
                message += '\nNo matching proposals. Review ratio, ranges and size limits.'
        if isinstance(result, QuickResult):
            if not result.proposals and result.reason != 'cancelled':
                if result.exclusions.get('size limits'):
                    message += '\nGenerated candidates exceeded the size limit.'
                if result.geometry_errors:
                    message += '\n' + next(iter(result.geometry_errors))
                if result.complete and not result.total:
                    message += '\nNo tooth counts in the automatic ranges matched the ratio and construction.'
            message += f'\nAutomatic ranges · ±{result.settings.tolerance_percent:g}% ratio'
            if not result.complete and result.reason != 'cancelled':
                message += '\nUse Advanced search for wider coverage.'
        elif not result.complete and result.reason != 'cancelled':
            message += '\nReview ranges or raise Advanced budgets, then Search again for more coverage.'
        self.summary.set_text(message)
        if self.window:
            self.status.set_text(message)
            self.progress.set_fraction(result.visited/result.total if result.total else float(result.complete))
            self.update_domain()
            self.cancel_button.set_sensitive(False)
            self.save_button.set_sensitive(True)
            self.page = 0
            self.present_result()
            if isinstance(result, QuickResult) and not result.proposals:
                feedback = message.split('\n', 2)[2]
                self.quick_outcome.set_text(feedback)
                self.quick_outcome.set_visible(True)
        return False

    def update_step_view(self):
        editing = not self.quick and self.setup.get_expanded()
        self.results_button.set_visible(editing and self.result is not None)
        self.compare.set_visible(not editing and bool(self.result and self.result.proposals))
        self.report_details.set_visible(self.result is not None)

    def clear_rows(self):
        self.update_step_view()
        self.clear_preview()
        while (child := self.list.get_first_child()):
            self.list.remove(child)
        self.page_label.set_text('')
        self.selection_summary.set_visible(False)
        self.quick_outcome.set_visible(False)
        self.result_scroll.set_visible(False)
        self.pages.set_visible(False)
        for button in self.page_buttons:
            button.set_sensitive(False)

    def present_result(self):
        if not self.window or self.result is None:
            return
        self.clear_rows()
        self.report.get_buffer().set_text(self.result.text())
        self.selection_summary.set_text('Select a proposal to compare it with the current model.')
        self.selection_summary.set_visible(not self.quick and bool(self.result.proposals))
        proposals = self.result.proposals
        start = self.page*25
        self.result_scroll.set_visible(bool(proposals))
        self.pages.set_visible(len(proposals) > 25)
        self.page_buttons[0].set_sensitive(self.page > 0)
        self.page_buttons[1].set_sensitive(start+25 < len(proposals))
        self.page_label.set_text(f'{start+1 if proposals else 0}–{min(len(proposals), start+25)} / {len(proposals)}')
        for proposal in proposals[start:start+25]:
            magnitude = ''.join(ratio_parts(proposal.ratio, 10, signed=False))
            row = Gtk.ListBoxRow()
            row.proposal = proposal
            rotation = 'Same rotation' if proposal.ratio > 0 else 'Opposite rotation'
            contact = proposal.comparison.get('min_profile_contact')
            quality = f'Usable contact ratio: {contact:.6g}' if contact is not None else 'Usable contact ratio: unavailable'
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            content.append(label(f'Ratio (input/output): {magnitude}'))
            line=Gtk.Box(spacing=4);line.append(label(rotation));line.append(label(f'· error {proposal.error_percent:.6g}%'));content.append(line)
            if self.quick:
                content.append(label(size_text(self.app.family, proposal)))
                content.append(label(VARIANTS[self.app.family][proposal.values['variant']]))
                specs = {spec[0]: spec[1] for spec in variables(self.app.family, proposal.values)}
                counts = [f'{specs[k]} {proposal.values[k]}' for k in COUNT_KEYS[self.app.family]
                          if k in specs]
                content.append(label(' · '.join(counts)))
                if proposal.values.get('bearing_mode', 'manual') != 'manual':
                    content.append(label(f"NSK {proposal.values['bearing']}"))
            else:
                content.append(label(f'Overall XYZ: {" × ".join(f"{v:.6g}" for v in proposal.xyz)} mm'))
                content.append(label(quality))
                if proposal.changes:
                    content.append(label('Current → Proposed'))
                    for key,(old,new) in proposal.changes.items():
                        line=Gtk.Box(spacing=4);line.append(label(self.titles.get(key,key)+':'));line.append(label(f'{old:.10g} → {new:.10g}'));content.append(line)
                else:
                    content.append(label('Current parameters (no change)'))
            row.set_child(content)
            signed_ratio = ''.join(ratio_parts(proposal.ratio, 12))
            row.set_tooltip_text(f'Signed input/output ratio: {signed_ratio}. Direction uses the current member axes.')
            self.list.append(row)
        if self.quick and proposals:
            self.list.select_row(self.list.get_row_at_index(0))

    def change_page(self, delta):
        if self.result is not None:
            self.page = max(0, min(max(0, (len(self.result.proposals)-1)//25), self.page+delta))
            self.present_result()

    def selected(self, _, row):
        if row is None:
            self.clear_preview()
            self.quick_outcome.set_visible(False)
        elif self.quick:
            proposal = row.proposal
            ratio = ''.join(ratio_parts(proposal.ratio, 8))
            self.quick_outcome.set_text(f'{ratio}   ·   {size_text(self.app.family, proposal)}')
            self.quick_outcome.set_visible(True)
            self.preview_proposal(proposal)
        else:
            c = row.proposal.comparison
            contact = c.get('min_profile_contact')
            contact_text = f'{contact:.6g}' if contact is not None else 'unavailable'
            self.selection_summary.set_text(f"Usable contact ratio: {contact_text} · Geometry warnings: {c.get('warning_count', 0)}. Apply changes parameters; run an interference check separately.")
        self.apply_button.set_sensitive(row is not None and bool(row.proposal.changes) and self.result is not None and self.current(self.serial))

    def apply_selected(self):
        row = self.list.get_selected_row()
        if row is None:
            return False
        return self.apply(row.proposal)

    def apply(self, proposal):
        app = self.app
        # Snapshot catches edits even if their signal/record is still pending.
        if app.busy or self.result is None or not self.current(self.serial) or not any(proposal is p for p in self.result.proposals):
            return False
        if not proposal.changes:
            return False
        try:
            checked = generate(app.family, deepcopy(proposal.values), quality=app.design.quality)
            if checked.values != proposal.values:
                raise ValueError('Proposal normalization changed; run a new search.')
            settings = self.result.settings
            minimum, maximum = nominal_bounds(checked)
            if (not matches(checked.analysis['signed_ratio'], settings)
                    or checked.analysis['signed_ratio'] != proposal.ratio
                    or (minimum, maximum) != (proposal.minimum, proposal.maximum)):
                raise ValueError('Proposal geometry changed; run a new search.')
            limit = getattr(self.result, 'max_diameter', None)
            if limit is not None and exceeds_quick_limit(nominal_diameter(checked), limit):
                raise ValueError('Fresh candidate exceeds the maximum diameter.')
            threshold = settings.min_profile_contact
            if threshold > 0:
                contacts = [m.get('profile_contact_total') for m in checked.analysis.get('meshes', [])]
                if not contacts or any(v is None or v < threshold for v in contacts):
                    raise ValueError('Fresh candidate does not meet the usable contact ratio limit.')
        except Exception as error:
            self.invalidate(f'Proposal cannot be applied: {error}')
            self.update_domain()
            if self.quick:
                self.quick_outcome.set_text(self.status.get_text())
                self.quick_outcome.set_visible(True)
            return False
        previous = deepcopy(app.project_snapshot())
        updated = deepcopy(previous)
        from precise_numbers import SOURCE_KEY
        target_values = updated['values'][app.family]
        target_values.pop(SOURCE_KEY, None)
        target_values.update(deepcopy(checked.values))
        for key in proposal.changes:
            updated['raw'].setdefault(app.family, {}).pop(key, None)
        app.document.barrier()
        try:
            # This rebuild invalidates search/interference before touching widgets;
            # project_restoring suppresses records/reconcile inside make_fields.
            app.restore_project_snapshot(updated)
            if app.design is None or app.design.values != checked.values:
                raise ValueError('The rebuilt model differs from the validated proposal.')
        except Exception as error:
            app.restore_project_snapshot(previous)
            self.summary.set_text(f'Proposal not applied: {error}')
            if self.window:
                self.status.set_text(self.summary.get_text())
                if self.quick:
                    self.quick_outcome.set_text(self.summary.get_text())
                    self.quick_outcome.set_visible(True)
            return False
        app.document.record(app.project_snapshot())
        if hasattr(app,'components'):app.components.refreshed(app.design)
        if hasattr(app,'gear_measurement'):app.gear_measurement.refreshed(app.design)
        app.undo_reset.set_visible(False)
        app.document.barrier()
        app.update_document()
        self.summary.set_text('Proposal applied · Undo restores the previous parameters')
        if self.window:
            self.status.set_text(self.summary.get_text())
            if self.quick:
                self.quick_outcome.set_text(self.summary.get_text())
                self.quick_outcome.set_visible(True)
        return True

    def save(self):
        if self.result is None or not self.current(self.serial):
            return
        text, serial = self.result.text(), self.serial
        dialog = Gtk.FileChooserNative(title='Save search report', transient_for=self.app.win, action=Gtk.FileChooserAction.SAVE, accept_label='Save', cancel_label='Cancel')
        from ui_language import localize_native_dialog
        localize_native_dialog(dialog, self.app.language.language)
        dialog.set_current_name('combination-search.txt')
        def response(widget, code):
            file = widget.get_file() if code == Gtk.ResponseType.ACCEPT else None
            widget.destroy()
            if file and self.current(serial):
                try:
                    from export_transaction import write_text
                    write_text(Path(file.get_path()), text)
                    self.app.status_text('Search report saved')
                except (OSError, TypeError, ValueError) as error:
                    self.app.status_text(f'Report could not be saved: {error}')
        dialog.connect('response', response)
        dialog.show()
