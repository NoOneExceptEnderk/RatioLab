# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK finite search controller. Worker input and every callback belong to one revision."""
from copy import deepcopy
from math import isfinite, prod
from pathlib import Path
from threading import Event, Thread
from time import monotonic
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio
from geometry import generate, INTEGER, FAMILIES as FAMILY_TITLES
from project_document import equivalent
from workspace_tools import actions, details
from combination_search import FAMILIES, COUNT_KEYS, Settings, variables, parse_grid, search


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
        self.button = Gtk.Button(label='Find combinations…')
        self.button.connect('clicked', lambda _: self.open())
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
            self.status.set_text('Family or variant changed · ranges and ratio reset to the current model. Review settings before Search.')
            return
        self.unavailable = ('Invalid current configuration. Complete the model numeric fields first.' if design is None else
                            'Ratio search requires a single fixed input/output ratio. Select a supported reducer assembly.' if design.family not in FAMILIES else None)
        if design is not None:
            self.update_context(design)
            for name, (locked, custom, _) in self.axes.items():
                value = design.values[name]
                self.axes[name] = (locked, custom, value)
                low, high = self.axis_controls[name]['bounds']
                self.axis_controls[name]['current'].set_text(f'Current: {value:g} · allowed {low:g}–{high:g}')
        self.update_domain()

    def update_context(self, design):
        values = design.values
        self.context.set_text(f'{FAMILY_TITLES[design.family]} · current variant and input/output connection stay fixed.')
        self.context.set_tooltip_text(f'{design.family} / {values.get("variant", "standard")} · I/O {values.get("io_scheme", "fixed")}' + (f' / stage 2 {values["io_scheme2"]}' if 'io_scheme2' in values else ''))

    def invalidate(self, message='Results out of date · run a new search'):
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

    def open(self):
        if self.window:
            self.window.present()
            return
        win = self.app.tools.panel('search')
        self.window = win
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        win.set_child(box)
        self.fields = {}
        self.field_errors = {}
        setup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.setup = details(box, 'Edit search settings', setup)
        self.setup.set_expanded(True)
        setup.append(label('1. Desired ratio'))
        setup.append(label('Ratio = |input speed / output speed|'))
        for key, title, value in (('target', 'Desired ratio', '3'), ('tolerance', 'Allowed error ± (%)', '1')):
            self.add_field(setup, key, title, value)
        self.ratio_hint = label('')
        setup.append(self.ratio_hint)
        setup.append(label('Output direction relative to input'))
        self.direction = Gtk.DropDown.new_from_strings(['Either direction', 'Same (+)', 'Opposite (−)'])
        setup.append(self.direction)
        self.direction.connect('notify::selected', lambda *_: self.request_changed())
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
        self.context = label('')
        setup.append(self.context)
        self.axes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        setup.append(self.axes_box)
        self.reload_button = Gtk.Button(label='Reset ranges & ratio to model')
        self.reload_button.connect('clicked', lambda _: self.populate())
        setup.append(self.reload_button)
        advanced = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.advanced = details(setup, 'Advanced · budgets & technical details', advanced)
        self.add_field(advanced, 'budget', 'Maximum candidates', '50000')
        self.add_field(advanced, 'seconds', 'Time limit (seconds)', '30')
        advanced.append(label('Finite local search, not a continuous or global optimum. All other dimensions, variants, stages and I/O stay fixed. Every proposal passes the generator; this is not an interference or strength check. Stop is cooperative: one generation or surface section may finish first.'))
        self.report = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        report_scroll = Gtk.ScrolledWindow()
        report_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        report_scroll.set_min_content_height(100)
        report_scroll.set_child(self.report)
        details(advanced, 'Full search report', report_scroll)
        self.scope = label('')
        self.status = label('Choose a ratio and ranges, then Search.')
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
        compare.append(label('3. Compare results'))
        self.empty = label('Search to compare generated proposals. Select one to review and apply.')
        compare.append(self.empty)
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
        buttons = actions(compare)
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
            self.invalidate('Search window closed')
            self.window = None
            return False
        win.connect('close-request', close)
        self.setup.connect('notify::expanded', lambda *_: self.update_step_view())
        self.populate()
        win.pin(self.scope, self.envelope_summary, self.status, self.progress, run_actions, compare)
        win.present()
        self.fields['target'].grab_focus()

    def numeric_entry(self, text):
        # Entry deliberately preserves incomplete/invalid edits; no focus-out rounding.
        return Gtk.Entry(text=text, width_chars=5, max_width_chars=8,
                         hexpand=True, input_purpose=Gtk.InputPurpose.NUMBER)

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

    def populate(self):
        if not self.window:
            return
        self.invalidate('Choose ranges, then Search to compare proposals')
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
            for key, title, _, lo, hi, step in specs:
                self.titles[key] = title
                value = values[key]
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                self.axes_box.append(row)
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
                mode = Gtk.DropDown.new_from_strings(['Range', 'Custom values (advanced)'])
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
                    entry = self.numeric_entry(f'{initial:.15g}')
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
            ratio = app.design.analysis['signed_ratio']
            self.fields['target'].set_text(f'{abs(ratio):.15g}')
        self.populating = False
        self.update_domain()

    def update_axis_view(self, key):
        c = self.axis_controls[key]
        custom = c['mode'].get_selected() == 1
        c['controls'].set_visible(not self.axes[key][0].get_active())
        c['ranges'].set_visible(not custom)
        c['custom'].set_visible(custom)
        c['hint'].set_visible(custom)

    def update_domain(self):
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
            target = float(self.fields['target'].get_text().strip())
            tolerance_percent = float(self.fields['tolerance'].get_text().strip())
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
                texts = [entry.get_text().strip() for entry in c['inputs']]
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
        titles = dict(target='Desired ratio', tolerance='Allowed error', x='Maximum X', y='Maximum Y', z='Maximum Z', budget='Maximum candidates', seconds='Time limit')
        limits = dict(target=(0, float('inf')), tolerance=(0, 100), x=(0, float('inf')), y=(0, float('inf')), z=(0, float('inf')), budget=(1, 1000000), seconds=(0, 3600))
        values, errors = {}, []
        for key, entry in self.fields.items():
            message = ''
            try:
                value = float(entry.get_text().strip())
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
            if any(self.field_errors[k].get_visible() for k in ('budget', 'seconds')):
                self.advanced.set_expanded(True)
            raise ValueError(errors[0])
        settings = Settings(target=values['target'], tolerance_percent=values['tolerance'], direction=('either', 'same', 'opposite')[self.direction.get_selected()], max_xyz=tuple(values[k] for k in ('x', 'y', 'z')), max_candidates=int(values['budget']), max_seconds=values['seconds'])
        settings.validate()
        return settings

    def start(self, settings=None, axes=None):
        if not self.alive or self.cancel is not None or not self.window:
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
            settings = settings or self.read_settings()
            settings.validate()
            axes = self.read_axes() if axes is None else deepcopy(axes)
        except ValueError as error:
            self.invalidate('Invalid search request: '+str(error))
            return
        self.invalidate('Searching…')
        self.compare.set_visible(True)
        self.empty.set_text('Generating proposals. Results appear when this run finishes; Cancel stops at the next cooperative boundary.')
        self.snapshot = deepcopy(app.project_snapshot())
        self.revision = app.document.token
        self.design_key = self.key(app.design)
        serial, revision = self.serial, self.revision
        base, family = deepcopy(app.design.values), app.family
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
                result = search(family, base, axes, settings, event, progress)
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
            return False
        self.result = result
        message = ('Complete finite search' if result.complete else 'PARTIAL search · '+result.reason)+f' · {result.visited}/{result.total} candidates · {len(result.proposals)} retained proposals'
        if not result.proposals:
            message += ' · No matching proposals. Review ratio, ranges and size limits, then Search again.'
        elif not result.complete:
            message += ' · Review ranges or raise Advanced budgets, then Search again for more coverage.'
        self.summary.set_text(message)
        if self.window:
            self.status.set_text(message)
            self.progress.set_fraction(result.visited/result.total)
            self.update_domain()
            self.cancel_button.set_sensitive(False)
            self.save_button.set_sensitive(True)
            self.page = 0
            self.present_result()
        return False

    def update_step_view(self):
        editing = self.setup.get_expanded()
        self.results_button.set_visible(editing and self.result is not None)
        self.compare.set_visible(not editing and (self.result is not None or self.cancel is not None))

    def clear_rows(self):
        self.update_step_view()
        while (child := self.list.get_first_child()):
            self.list.remove(child)
        self.page_label.set_text('')
        self.empty.set_visible(True)
        self.result_scroll.set_visible(False)
        self.pages.set_visible(False)
        self.empty.set_text('Search to compare generated proposals. Select one to review and apply.')
        for button in self.page_buttons:
            button.set_sensitive(False)

    def present_result(self):
        if not self.window or self.result is None:
            return
        self.clear_rows()
        self.report.get_buffer().set_text(self.result.text())
        proposals = self.result.proposals
        start = self.page*25
        self.empty.set_visible(not proposals)
        self.result_scroll.set_visible(bool(proposals))
        self.pages.set_visible(bool(proposals))
        self.empty.set_text('No matching proposals in the visited domain. Review ratio, ranges and size limits; for partial runs, review Advanced budgets.')
        self.page_buttons[0].set_sensitive(self.page > 0)
        self.page_buttons[1].set_sensitive(start+25 < len(proposals))
        self.page_label.set_text(f'{start+1 if proposals else 0}–{min(len(proposals), start+25)} / {len(proposals)}')
        for proposal in proposals[start:start+25]:
            row = Gtk.ListBoxRow()
            row.proposal = proposal
            changes = '\n'.join(f'{self.titles.get(k, k)}: {a:g} → {b:g}' for k, (a, b) in proposal.changes.items()) or 'Current parameters (no change)'
            if proposal.changes:
                changes = 'Current → Proposed\n' + changes
            rotation = 'Same rotation' if proposal.ratio > 0 else 'Opposite rotation'
            row.set_child(label(f'Ratio (input/output): {abs(proposal.ratio):.10g}:1\n{rotation} · error {proposal.error_percent:.6g}%\nOverall XYZ: {" × ".join(f"{v:.6g}" for v in proposal.xyz)} mm\n{changes}'))
            row.set_tooltip_text(f'Signed input/output ratio: {proposal.ratio:+.12g}. Direction uses the current member axes.')
            self.list.append(row)

    def change_page(self, delta):
        if self.result is not None:
            self.page = max(0, min(max(0, (len(self.result.proposals)-1)//25), self.page+delta))
            self.present_result()

    def selected(self, _, row):
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
            checked = generate(app.family, deepcopy(proposal.values))
            if checked.values != proposal.values:
                raise ValueError('Proposal normalization changed; run a new search.')
        except Exception as error:
            self.invalidate(f'Proposal cannot be applied: {error}')
            return False
        previous = deepcopy(app.project_snapshot())
        updated = deepcopy(previous)
        updated['values'][app.family].update(deepcopy(checked.values))
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
            return False
        app.document.record(app.project_snapshot())
        if hasattr(app,'components'):app.components.refreshed(app.design)
        app.undo_reset.set_visible(False)
        app.document.barrier()
        app.update_document()
        self.summary.set_text('Proposal applied · Undo restores the previous parameters')
        if self.window:
            self.status.set_text(self.summary.get_text())
        return True

    def save(self):
        if self.result is None or not self.current(self.serial):
            return
        text, serial = self.result.text(), self.serial
        dialog = Gtk.FileChooserNative(title='Save search report', transient_for=self.app.win, action=Gtk.FileChooserAction.SAVE, accept_label='Save', cancel_label='Cancel')
        dialog.set_current_name('combination-search.txt')
        def response(widget, code):
            file = widget.get_file() if code == Gtk.ResponseType.ACCEPT else None
            widget.destroy()
            if file and self.current(serial):
                try:
                    from export_transaction import write_text
                    write_text(Path(file.get_path()), text)
                    self.status.set_text('Search report saved')
                except (OSError, TypeError, ValueError) as error:
                    self.status.set_text(f'Report could not be saved: {error}')
        dialog.connect('response', response)
        dialog.show()
