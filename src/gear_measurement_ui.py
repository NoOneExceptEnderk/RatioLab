# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only, revision-bound theoretical gear gauge queries."""
from copy import deepcopy
from datetime import datetime
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from gear_measurement import default_gauge, measurement_query, measurement_query_text, export_measurement
from project_document import equivalent
from gui_workflow import bind_numeric_entry, numeric_value, set_numeric_value


class Controller:
    def __init__(self, app, container):
        self.app = app
        self.window = self.snapshot = self.revision = self.design = self.result = None
        self.indices = []
        self.syncing = False
        self.alive = True
        self.summary = Gtk.Label(label='Theoretical balls / rollers on external or internal spur profiles')
        self.button = Gtk.Button(label='Gear metrology…')
        self.button.connect('clicked', lambda _: self.open())
        container.register('gear_measurement', self)
        app.win.connect('unrealize', lambda *_: self.close())

    def current(self):
        app = self.app
        return (self.alive and getattr(app, 'project_alive', False) and
                self.revision is not None and app.document.token == self.revision and
                app.design is self.design and not app.pending and not app.busy and
                equivalent(app.project_snapshot(), self.snapshot))

    def invalidate(self, message='Document changed · run a new measurement'):
        self.result = None
        self.snapshot = self.revision = self.design = None
        if self.window:
            self.report.get_buffer().set_text(message)
            self.run_button.set_sensitive(False)
            self.save_button.set_sensitive(False)

    def changed(self, snapshot):
        if self.snapshot is not None and not equivalent(snapshot, self.snapshot):
            self.invalidate('Parameters changed · measurement cleared, including incomplete edits')

    def refreshed(self, design):
        if not hasattr(self.app, 'document'):
            return
        snapshot = self.app.project_snapshot()
        if self.revision != self.app.document.token or not equivalent(snapshot, self.snapshot):
            self.invalidate()
        self.snapshot = deepcopy(snapshot)
        self.revision = self.app.document.token
        self.design = design
        if self.window:
            self.populate()

    def close(self):
        self.alive = False
        self.invalidate('Measurement closed')
        if self.window:
            self.window.destroy()
            self.window = None

    def window_closed(self, *_):
        self.result = None
        self.window = None
        return False

    def open(self):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.Window(title='Gear metrology · theoretical balls / rollers', transient_for=self.app.win,
                                 default_width=720, default_height=600)
        self.window.add_css_class('reducers')
        self.window.connect('close-request', self.window_closed)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_start=16, margin_end=16, margin_top=16, margin_bottom=16)
        self.window.set_child(box)
        box.append(Gtk.Label(label='Select a generated cylindrical gear and a gauge diameter. This query does not change the project.',
                             wrap=True, xalign=0))
        self.parts = Gtk.DropDown.new_from_strings([])
        box.append(self.parts)
        self.parts.connect('notify::selected', lambda *_: self.part_changed())
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(label='Gauge diameter [mm]'))
        self.diameter = Gtk.Entry(hexpand=True, input_purpose=Gtk.InputPurpose.NUMBER)
        bind_numeric_entry(self.diameter, low=0)
        self.diameter.connect('changed', lambda *_: self.request_changed())
        row.append(self.diameter)
        self.gauge = Gtk.DropDown.new_from_strings(['Balls', 'Axial rollers'])
        self.gauge.connect('notify::selected', lambda *_: self.request_changed())
        row.append(self.gauge)
        box.append(row)
        reset = Gtk.Button(label='Use theoretical diameter near reference contact')
        reset.connect('clicked', lambda _: self.default_diameter())
        box.append(reset)
        box.append(Gtk.Label(label='External/internal spur only. Balls touch at points; rollers touch along axial lines. Helical and double-helical measurements are unsupported.', wrap=True, xalign=0))
        self.report = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(self.report)
        box.append(scroll)
        buttons = Gtk.Box(spacing=8)
        self.run_button = Gtk.Button(label='Calculate', css_classes=['primary'])
        self.run_button.connect('clicked', lambda _: self.calculate())
        buttons.append(self.run_button)
        self.save_button = Gtk.Button(label='Export selected report · TXT + JSON')
        self.save_button.connect('clicked', lambda _: self.export())
        buttons.append(self.save_button)
        box.append(buttons)
        self.save_button.set_sensitive(False)
        self.populate()
        self.window.present()

    def populate(self):
        from gi.repository import Gtk
        self.syncing = True
        previous = self.indices[self.parts.get_selected()] if self.parts.get_selected() < len(self.indices) else None
        self.indices = []
        if self.current() and self.design.family in ('spur', 'helical', 'double', 'parallel', 'internal', 'planetary'):
            self.indices = [i for i, p in enumerate(self.design.parts)
                            if 'measurement_geometry' in p.profile_metadata.get('tooth_profile', {})]
        self.parts.set_model(Gtk.StringList.new([f'{i+1:03d} · {self.design.parts[i].name}' for i in self.indices]))
        if previous in self.indices:
            self.parts.set_selected(self.indices.index(previous))
        self.syncing = False
        self.run_button.set_sensitive(bool(self.indices))
        if previous not in self.indices:
            self.default_diameter()
        if not self.indices:
            self.request_changed('No current cylindrical involute gear · select a supported family and finish parameter edits.')

    def selected_index(self):
        selected = self.parts.get_selected()
        return self.indices[selected] if selected < len(self.indices) else None

    def part_changed(self):
        if not self.syncing:
            self.default_diameter()

    def default_diameter(self):
        if self.syncing:
            return
        index = self.selected_index()
        self.diameter.set_text('')
        if index is not None and self.current():
            profile = self.design.parts[index].profile_metadata['tooth_profile']
            result = default_gauge(profile['measurement_geometry'])
            if result['status'] == 'ok':
                set_numeric_value(self.diameter, result['gauge_diameter_mm'])
        self.request_changed()

    def request_changed(self, message='Gauge request changed · click Calculate'):
        if self.syncing or not self.window:
            return
        self.result = None
        self.save_button.set_sensitive(False)
        self.report.get_buffer().set_text(message)

    def calculate(self):
        if not self.current() or self.selected_index() is None:
            self.invalidate('Current parameters are unavailable or changed · regenerate the model first')
            return
        try:
            diameter = numeric_value(self.diameter)
            query = measurement_query(self.design, self.selected_index(), diameter,
                                      'roller' if self.gauge.get_selected() else 'ball', self.revision)
        except ValueError as error:
            self.request_changed('Invalid measurement: '+str(error))
            return
        self.result = query
        self.report.get_buffer().set_text(measurement_query_text(query))
        self.save_button.set_sensitive(True)

    def export(self):
        if not self.current() or self.result is None:
            self.invalidate('Document changed · calculate again before export')
            return
        target = self.app.output_dir/f'gear-measurement-{datetime.now():%Y%m%d-%H%M%S-%f}'
        try:
            export_measurement(deepcopy(self.result), target)
        except (OSError, ValueError) as error:
            self.app.status_text('Measurement export failed: '+str(error))
            return
        self.app.status_text('Selected theoretical measurement · TXT + JSON · '+str(target))
