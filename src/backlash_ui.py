# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Revision-bound asynchronous backlash proposals and deliberate document Apply."""
from copy import deepcopy
from datetime import datetime
from threading import Event, Thread
from time import monotonic
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from backlash_solver import solve, revalidate, export_proposal
from interference import Settings
from gui_workflow import bind_numeric_entry, bind_numeric_spin, numeric_value, set_numeric_value


class Controller:
    def __init__(self, app, container):
        self.app = app
        self.window = self.snapshot = self.revision = self.source_design = self.result = None
        self.thread = self.cancel = None
        self.serial = 0
        self.alive = True
        self.summary = Gtk.Label(label='Solve working transverse backlash by changing external-pair centre distance')
        self.button = Gtk.Button(label='Solve working backlash…')
        self.button.connect('clicked', lambda _: self.open())
        container.register('backlash', self)
        app.win.connect('unrealize', lambda *_: self.close())

    def supported(self):
        d = self.app.design
        return d is not None and d.family == 'parallel'

    def current(self, serial):
        app = self.app
        # Exact raw text as well as identity/revision: even incomplete edits invalidate.
        return (self.alive and self.window is not None and app.project_alive and
                serial == self.serial and self.snapshot is not None and
                app.document.token == self.revision and app.design is self.source_design and
                not app.pending and not app.busy and app.project_snapshot() == self.snapshot)

    def invalidate(self, message='Document changed · calculate a new proposal'):
        self.serial += 1
        if self.cancel is not None:
            self.cancel.set()
        self.cancel = None
        self.result = self.snapshot = self.revision = self.source_design = None
        self.summary.set_text(message)
        if self.window:
            self.preview.reset_motion()
            self.preview.set_design(None)
            self.report.get_buffer().set_text(message)
            self.apply_button.set_sensitive(False)
            self.save_button.set_sensitive(False)
            self.cancel_button.set_sensitive(False)
            self.run_button.set_sensitive(self.supported() and not self.app.busy)
            self.progress.set_fraction(0)

    def changed(self, snapshot):
        if self.snapshot is not None and snapshot != self.snapshot:
            self.invalidate('Parameters changed · proposal cleared, including incomplete edits')

    def refreshed(self, design):
        if self.source_design is not None and (design is not self.source_design or
                self.revision != self.app.document.token or self.app.project_snapshot() != self.snapshot):
            self.invalidate()
        if self.window:
            self.context.set_text(self.context_text())
            self.run_button.set_sensitive(self.supported() and self.cancel is None and not self.app.busy)

    def context_text(self):
        if not self.supported():
            return 'Select a parallel external pair. Internal, planetary and individual gears do not support this adjustment.'
        mesh = self.app.design.analysis['meshes'][0]
        return (f'Current centre {mesh["center_distance_mm"]:.9g} mm · working transverse backlash '
                f'{mesh["working_pair_backlash_mm"]:.9g} mm · {self.app.design.values["variant"]}')

    def close(self):
        self.invalidate('Backlash tool closed')
        self.alive = False
        if self.window:
            self.window.destroy()
            self.window = None

    def window_closed(self, *_):
        self.invalidate('Backlash window closed')
        self.window = None
        return False

    def open(self):
        if self.window:
            self.window.present()
            return
        from preview3d import Preview3D
        self.window = Gtk.Window(title='Working backlash · centre distance proposal', transient_for=self.app.win,
                                 default_width=850, default_height=760)
        self.window.add_css_class('reducers')
        self.window.connect('close-request', self.window_closed)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_start=14, margin_end=14, margin_top=14, margin_bottom=14)
        self.window.set_child(box)
        box.append(Gtk.Label(label='Preview an exact centre-distance solution. The project changes only when you click Apply.', wrap=True, xalign=0))
        self.context = Gtk.Label(label=self.context_text(), wrap=True, xalign=0)
        box.append(self.context)
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(label='Desired working transverse tangential backlash [mm]', wrap=True, xalign=0))
        initial = self.app.design.analysis['meshes'][0]['working_pair_backlash_mm'] if self.supported() else .3
        self.target = Gtk.Entry(hexpand=True, input_purpose=Gtk.InputPurpose.NUMBER)
        bind_numeric_entry(self.target, low=0)
        set_numeric_value(self.target, initial)
        self.target.connect('changed', lambda *_: self.invalidate('Target changed · calculate a new proposal'))
        row.append(self.target)
        box.append(row)
        advanced = Gtk.Expander(label='Discrete interference settings · complete sampled coverage required for Apply')
        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        advanced.set_child(settings)
        controls = Gtk.Box(spacing=8)
        self.step = Gtk.SpinButton.new_with_range(.1, 180, 5)
        self.step.set_value(30)
        self.seconds = Gtk.SpinButton.new_with_range(1, 3600, 5)
        self.seconds.set_value(60)
        self.poses = Gtk.SpinButton.new_with_range(1, 10000, 100)
        self.poses.set_value(721)
        for field in (self.step, self.seconds, self.poses):
            bind_numeric_spin(field, integer=field is self.poses)
            set_numeric_value(field, field.get_value())
        for title, field in [('Step ≤ [deg]', self.step), ('Time limit [s]', self.seconds), ('Pose limit', self.poses)]:
            controls.append(Gtk.Label(label=title))
            controls.append(field)
            field.connect('value-changed', lambda *_: self.invalidate('Check settings changed · calculate a new proposal'))
        settings.append(controls)
        settings.append(Gtk.Label(label='Boundary tolerance 0.01 mm; limits 128 parts / 300,000 triangles. Stop is cooperative. Same-member boundary contacts remain unresolved; intersections always block Apply. Sparse samples do not prove continuous clearance.', wrap=True, xalign=0))
        box.append(advanced)
        self.preview = Preview3D()
        self.preview.set_size_request(-1, 210)
        self.preview.set_vexpand(True)
        box.append(self.preview)
        box.append(Gtk.Label(label='Proposed geometry only · independent static view; your project view and motion are preserved.', wrap=True, xalign=0))
        self.report = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, min_content_height=170)
        scroll.set_child(self.report)
        box.append(scroll)
        self.progress = Gtk.ProgressBar()
        box.append(self.progress)
        buttons = Gtk.Box(spacing=8)
        self.run_button = Gtk.Button(label='Calculate & preview')
        self.run_button.connect('clicked', lambda _: self.start())
        self.cancel_button = Gtk.Button(label='Cancel / clear preview')
        self.cancel_button.connect('clicked', lambda _: self.stop())
        self.apply_button = Gtk.Button(label='Apply centre distance', css_classes=['primary'])
        self.apply_button.connect('clicked', lambda _: self.apply())
        self.save_button = Gtk.Button(label='Export TXT + JSON')
        self.save_button.connect('clicked', lambda _: self.export())
        for button in (self.run_button, self.cancel_button, self.apply_button, self.save_button):
            buttons.append(button)
        box.append(buttons)
        self.invalidate('Review the target and sampling settings, then Calculate & preview.')
        self.window.present()
        self.target.grab_focus()

    def stop(self):
        self.invalidate('Cancelled · preview cleared; a running geometry operation stops at its next cooperative boundary')

    def start(self, settings=None):
        if not self.alive or not self.window or self.app.busy:
            return False
        if self.thread is not None and self.thread.is_alive():
            self.report.get_buffer().set_text('Previous operation is still stopping · try again shortly')
            return False
        app = self.app
        # Finish raw edits and all generator normalization before taking the snapshot.
        app.project_changed()
        if not app.refresh() or not self.supported():
            self.invalidate('Valid parallel external spur / helical / double-helical pair required')
            return False
        try:
            target = numeric_value(self.target)
            if settings is None:
                poses = numeric_value(self.poses)
                if not poses.is_integer():
                    raise ValueError('Pose limit must be a whole number.')
                settings = Settings(step_degrees=numeric_value(self.step), max_seconds=numeric_value(self.seconds),
                                    max_poses=int(poses))
            settings.validate()
        except ValueError as error:
            self.invalidate('Invalid request: '+str(error))
            return False
        self.invalidate('Generating and checking proposal…')
        self.snapshot = deepcopy(app.project_snapshot())
        self.revision = app.document.token
        self.source_design = app.design
        serial, revision, design = self.serial, self.revision, deepcopy(app.design)
        event = Event()
        self.cancel = event
        self.run_button.set_sensitive(False)
        self.cancel_button.set_sensitive(True)
        last = [0.]
        def progress(message, fraction):
            now = monotonic()
            if now-last[0] >= .15 or fraction == 1:
                last[0] = now
                GLib.idle_add(self.progress_update, serial, message, fraction)
        def worker():
            try:
                result = solve(design, target, settings, event, progress)
                result.revision = revision
                if result.interference is not None:
                    result.interference['revision'] = revision
                error = None
            except Exception as exc:
                result, error = None, f'Proposal failed: {type(exc).__name__}: {exc}'
            GLib.idle_add(self.finished, serial, result, error)
        self.thread = Thread(target=worker, name='RatioLab backlash inverse', daemon=True)
        self.thread.start()
        return True

    def progress_update(self, serial, message, fraction):
        if self.current(serial):
            self.summary.set_text(message)
            self.report.get_buffer().set_text(message)
            self.progress.set_fraction(fraction)
        return False

    def finished(self, serial, result, error):
        if not self.current(serial):
            if serial == self.serial and self.window and self.alive:
                self.invalidate('Document changed while checking · calculate a new proposal')
            return False
        self.cancel = None
        self.cancel_button.set_sensitive(True)
        self.run_button.set_sensitive(True)
        if error:
            self.invalidate(error)
            return False
        self.result = result
        self.summary.set_text(result.reason)
        self.report.get_buffer().set_text(result.text())
        self.progress.set_fraction(1 if result.interference and result.interference['coverage_complete'] else 0)
        if result.design is not None:
            self.preview.set_design(result.design)
            self.preview.view('iso')
        changed = result.values.get('center_extra') != result.source_values.get('center_extra')
        self.apply_button.set_sensitive(result.applicable and changed)
        self.save_button.set_sensitive(True)
        return False

    def apply(self):
        app = self.app
        result = self.result
        if (result is None or not self.current(self.serial) or not result.applicable or result.application != 'proposed' or
                result.values == result.source_values):
            return False
        try:
            checked = revalidate(result)
        except Exception as error:
            self.invalidate('Proposal cannot be applied: '+str(error))
            return False
        previous = deepcopy(app.project_snapshot())
        updated = deepcopy(previous)
        updated['values'][app.family].update(deepcopy(checked.values))
        updated['raw'].setdefault(app.family, {}).pop('center_extra', None)
        app.document.barrier()
        try:
            # Standard document restore invalidates every controller before widget mutation.
            app.restore_project_snapshot(updated)
            if app.design is None or app.design.values != checked.values:
                raise ValueError('Rebuilt model differs from the validated proposal.')
        except Exception as error:
            app.restore_project_snapshot(previous)
            self.summary.set_text('Proposal not applied: '+str(error))
            return False
        app.document.record(app.project_snapshot())
        app.components.refreshed(app.design)
        app.gear_measurement.refreshed(app.design)
        app.document.barrier()
        app.undo_reset.set_visible(False)
        app.update_document()
        # Keep the audit query available against the new applied revision. Another edit
        # invalidates it; it cannot be applied twice. Other-family drafts/path/clean persist.
        result.application = 'applied'
        result.applied_revision = app.document.token
        self.result = result
        self.snapshot = deepcopy(app.project_snapshot())
        self.revision = app.document.token
        self.source_design = app.design
        self.report.get_buffer().set_text(result.text())
        self.summary.set_text('Centre distance applied · one Undo restores previous parameters')
        self.apply_button.set_sensitive(False)
        self.save_button.set_sensitive(True)
        self.context.set_text(self.context_text())
        return True

    def export(self):
        if self.result is None or not self.current(self.serial):
            self.invalidate('Document changed · calculate again before export')
            return False
        target = self.app.output_dir/f'backlash-proposal-{datetime.now():%Y%m%d-%H%M%S-%f}'
        try:
            export_proposal(self.result, target)
        except (OSError, ValueError) as error:
            self.app.status_text('Backlash export failed: '+str(error))
            return False
        self.app.status_text('Backlash proposal · TXT + JSON · '+str(target))
        return True
