"""GTK finite search controller. Worker input and every callback belong to one revision."""
from copy import deepcopy
from math import isfinite
from pathlib import Path
from threading import Event, Thread
from time import monotonic
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio
from geometry import generate, INTEGER
from project_document import equivalent
from combination_search import FAMILIES, COUNT_KEYS, Settings, variables, parse_grid, search


def label(text):
    return Gtk.Label(label=text, xalign=0, wrap=True, selectable=True)


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
        row = Gtk.Box(spacing=8)
        container.append(row)
        self.button = Gtk.Button(label='Find combinations…')
        self.button.connect('clicked', lambda _: self.open())
        row.append(self.button)
        self.summary = label('Finite ratio and nominal envelope search')
        row.append(self.summary)
        app.win.connect('unrealize', lambda *_: self.close())

    def key(self, design):
        return (design.family, deepcopy(design.values)) if design else None

    def changed(self, snapshot):
        if self.snapshot is not None and not equivalent(snapshot, self.snapshot):
            self.invalidate('Model changed · search results are out of date')

    def refreshed(self, design):
        if self.design_key is not None and self.key(design) != self.design_key:
            self.invalidate('Geometry changed · run a new search')
        if self.window:
            self.run_button.set_sensitive(design is not None and self.cancel is None)

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
            self.run_button.set_sensitive(self.app.design is not None)

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
        win = Gtk.Window(title='Find geometric combinations', transient_for=self.app.win, default_width=1040, default_height=780)
        self.window = win
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        win.set_child(box)
        box.append(label('Search the selected assembly family. Ratio magnitude = |input speed / output speed|; direction uses the signed ratio and displayed member axes. Tolerance is relative percent.'))
        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        box.append(grid)
        self.fields = {}
        for n, (key, title, value) in enumerate((('target', 'Target ratio magnitude', '3'), ('tolerance', 'Tolerance ± [%]', '1'), ('x', 'Max X [mm]', '1000'), ('y', 'Max Y [mm]', '1000'), ('z', 'Max Z [mm]', '1000'), ('budget', 'Candidate budget [1–1000000]', '50000'), ('seconds', 'Time budget [s, ≤3600]', '30'))):
            grid.attach(label(title), (n % 4)*2, (n//4), 1, 1)
            entry = Gtk.Entry(text=value, width_chars=10)
            grid.attach(entry, (n % 4)*2+1, n//4, 1, 1)
            self.fields[key] = entry
            entry.connect('changed', lambda *_: self.request_changed())
        grid.attach(label('Direction'), 6, 1, 1, 1)
        self.direction = Gtk.DropDown.new_from_strings(['Either sign', 'Same (+)', 'Opposite (−)'])
        grid.attach(self.direction, 7, 1, 1, 1)
        self.direction.connect('notify::selected', lambda *_: self.request_changed())
        box.append(label('Nominal world XYZ extents of ALL generated components, supports, housing and hardware, including hidden parts; export pose, nominal sampled shared surface facets. STEP analytic circles may extend slightly beyond this bound. These limits do not bound motion sweep.'))
        self.scope = label('')
        box.append(self.scope)
        self.axes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_min_content_height(120)
        scroller.set_child(self.axes_box)
        box.append(scroller)
        actions = Gtk.Box(spacing=8)
        box.append(actions)
        self.reload_button = Gtk.Button(label='Use current model / reset grids')
        self.reload_button.connect('clicked', lambda _: self.populate())
        actions.append(self.reload_button)
        self.run_button = Gtk.Button(label='Search')
        self.run_button.connect('clicked', lambda _: self.start())
        actions.append(self.run_button)
        self.cancel_button = Gtk.Button(label='Cancel')
        self.cancel_button.connect('clicked', lambda _: self.stop())
        self.cancel_button.set_sensitive(False)
        actions.append(self.cancel_button)
        self.status = label(self.summary.get_text())
        box.append(self.status)
        self.progress = Gtk.ProgressBar()
        box.append(self.progress)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.connect('row-selected', self.selected)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_min_content_height(140)
        scroll.set_child(self.list)
        box.append(scroll)
        buttons = Gtk.Box(spacing=8)
        box.append(buttons)
        for title, delta in (('Previous 25', -1), ('Next 25', 1)):
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, d=delta: self.change_page(d))
            buttons.append(button)
        self.page_label = label('')
        buttons.append(self.page_label)
        self.apply_button = Gtk.Button(label='Apply selected · one Undo step')
        self.apply_button.connect('clicked', lambda _: self.apply_selected())
        self.apply_button.set_sensitive(False)
        buttons.append(self.apply_button)
        self.save_button = Gtk.Button(label='Save search report…')
        self.save_button.connect('clicked', lambda _: self.save())
        self.save_button.set_sensitive(False)
        buttons.append(self.save_button)
        self.report = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        report_scroll = Gtk.ScrolledWindow()
        report_scroll.set_min_content_height(100)
        report_scroll.set_child(self.report)
        box.append(report_scroll)
        def close(*_):
            self.invalidate('Search window closed')
            self.window = None
            return False
        win.connect('close-request', close)
        self.populate()
        win.present()

    def request_changed(self):
        if getattr(self, 'populating', False):
            return
        self.invalidate('Search request changed · run a new search')
        if self.window and hasattr(self, 'axes'):
            self.update_domain()

    def populate(self):
        if not self.window:
            return
        self.invalidate('Choose grids and run a finite search')
        self.populating = True
        while (child := self.axes_box.get_first_child()):
            self.axes_box.remove(child)
        self.axes = {}
        app = self.app
        app.project_changed()
        valid = app.refresh()
        self.form_key = (app.family, app.design.values.get('variant'), app.design.values.get('double_style')) if valid else None
        if not valid:
            self.scope.set_text('Invalid current configuration. Complete the numeric fields first.')
        elif app.family not in FAMILIES:
            self.scope.set_text('A single gear has no independent transmission ratio. Select a reducer assembly family.')
        else:
            values = app.design.values
            for key, title, _, lo, hi, step in variables(app.family, values):
                row = Gtk.Box(spacing=8)
                self.axes_box.append(row)
                locked = Gtk.CheckButton(label='Locked')
                locked.set_active(key not in COUNT_KEYS[app.family] or key == 'planets')
                row.append(locked)
                row.append(label(title+f' · current {values[key]:g} · allowed [{lo:g}, {hi:g}]'))
                value = values[key]
                if key in INTEGER:
                    delta = 4
                    stride = 2 if app.family == 'harmonic' and key == 'teeth' else 1
                    text = f'{max(lo, value-delta):g}:{min(hi, value+delta):g}:{stride:g}'
                else:
                    text = f'{value:.15g}'
                entry = Gtk.Entry(text=text, hexpand=True)
                entry.set_sensitive(not locked.get_active())
                row.append(entry)
                self.axes[key] = (locked, entry, value)
                def toggle(widget, e=entry):
                    e.set_sensitive(not widget.get_active())
                    self.request_changed()
                locked.connect('toggled', toggle)
                entry.connect('changed', lambda *_: self.request_changed())
            ratio = app.design.analysis['signed_ratio']
            self.fields['target'].set_text(f'{abs(ratio):.15g}')
        self.populating = False
        self.update_domain()

    def update_domain(self):
        app = self.app
        if app.design is None or app.family not in FAMILIES:
            self.run_button.set_sensitive(False)
            return
        try:
            axes = self.read_axes()
            from math import prod
            count = prod(map(len, axes.values()))
            self.scope.set_text(f'{app.family} / {app.design.values.get("variant", "standard")} · I/O {app.design.values.get("io_scheme", "fixed")}' + (f' / S2 {app.design.values["io_scheme2"]}' if 'io_scheme2' in app.design.values else '') + f' · {count:,} finite candidates before budgets. Unlocked grids: '+(', '.join(axes) or 'none (current model only)')+'. Use numbers separated by commas or inclusive low:high:step. All other parameters, variants, stages and I/O stay locked. Grids are discrete; no continuous/global optimum.')
            self.run_button.set_sensitive(self.cancel is None)
        except ValueError as error:
            self.scope.set_text(str(error))
            self.run_button.set_sensitive(False)

    def read_axes(self):
        return {key: parse_grid(entry.get_text()) for key, (locked, entry, _) in self.axes.items() if not locked.get_active()}

    def read_settings(self):
        def number(key):
            try:
                value = float(self.fields[key].get_text().strip())
            except ValueError:
                raise ValueError(f'{key}: complete a finite number.')
            if not isfinite(value):
                raise ValueError(f'{key}: complete a finite number.')
            return value
        budget = number('budget')
        if budget != int(budget):
            raise ValueError('Candidate budget must be an integer.')
        settings = Settings(target=number('target'), tolerance_percent=number('tolerance'), direction=('either', 'same', 'opposite')[self.direction.get_selected()], max_xyz=tuple(number(k) for k in ('x', 'y', 'z')), max_candidates=int(budget), max_seconds=number('seconds'))
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
            self.invalidate('A single gear has no independent transmission ratio. Select an assembly family.')
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
        self.thread.start()

    def current(self, serial):
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
            return False
        self.result = result
        message = ('Complete finite search' if result.complete else 'PARTIAL search · '+result.reason)+f' · {result.visited}/{result.total} candidates · {len(result.proposals)} retained proposals'
        if not result.proposals:
            message += ' · No results'
        self.summary.set_text(message)
        if self.window:
            self.status.set_text(message)
            self.progress.set_fraction(result.visited/result.total)
            self.run_button.set_sensitive(True)
            self.cancel_button.set_sensitive(False)
            self.save_button.set_sensitive(True)
            self.page = 0
            self.present_result()
        return False

    def clear_rows(self):
        while (child := self.list.get_first_child()):
            self.list.remove(child)
        self.page_label.set_text('')

    def present_result(self):
        if not self.window or self.result is None:
            return
        self.clear_rows()
        self.report.get_buffer().set_text(self.result.text())
        proposals = self.result.proposals
        start = self.page*25
        self.page_label.set_text(f'{start+1 if proposals else 0}–{min(len(proposals), start+25)} / {len(proposals)}')
        for proposal in proposals[start:start+25]:
            row = Gtk.ListBoxRow()
            row.proposal = proposal
            changes = ', '.join(f'{k}: {a} → {b}' for k, (a, b) in proposal.changes.items()) or 'Current parameters (no change)'
            row.set_child(label(f'i = {proposal.ratio:+.10g} · error {proposal.error_percent:.6g}% · nominal XYZ {" × ".join(f"{v:.6g}" for v in proposal.xyz)} mm\n{changes}'))
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
        dialog = Gtk.FileChooserNative(title='Save search report', transient_for=self.window, action=Gtk.FileChooserAction.SAVE, accept_label='Save', cancel_label='Cancel')
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
