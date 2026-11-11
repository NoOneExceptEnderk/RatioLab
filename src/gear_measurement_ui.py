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
from workspace_tools import actions, heading
from gui_workflow import choice_dropdown, bind_numeric_entry, numeric_value, numeric_snapshot_text, set_numeric_value


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
            self.result_summary.set_text(message)
            self.report_details.set_visible(False)
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
        self.draft = dict(key=self.draft_key(), part=self.selected_index(), diameter=numeric_snapshot_text(self.diameter),
                          gauge=self.gauge.get_selected())
        self.result = None
        self.window = None
        return False

    def draft_key(self):
        return (self.app.document.token[0], self.app.family, deepcopy(self.app.design.values) if self.app.design else None)

    def open(self):
        selected = getattr(self.app.components, 'selected', ())
        preferred = selected[0] if len(selected) == 1 else None
        if self.window:
            if preferred in self.indices:
                self.parts.set_selected(self.indices.index(preferred))
            self.window.present()
            return
        self.window = self.app.tools.panel('gear_measurement')
        self.window.connect('close-request', self.window_closed)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_start=16, margin_end=16, margin_top=16, margin_bottom=16)
        self.window.set_child(box)
        box.append(Gtk.Label(label='Select a generated cylindrical gear and a gauge diameter. This query does not change the project.',
                             wrap=True, xalign=0))
        heading(box, 'Model examined')
        self.parts = choice_dropdown([])
        box.append(self.parts)
        self.parts.connect('notify::selected', lambda *_: self.part_changed())
        self.component_summary = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.append(self.component_summary)
        self.result_summary = Gtk.Label(xalign=0, wrap=True, selectable=True)
        heading(box, 'Analysis settings')
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        row.append(Gtk.Label(label='Gauge diameter [mm]'))
        self.diameter = Gtk.Entry(hexpand=True, input_purpose=Gtk.InputPurpose.NUMBER)
        bind_numeric_entry(self.diameter, low=0)
        self.diameter.connect('changed', lambda *_: self.request_changed())
        row.append(self.diameter)
        self.gauge = choice_dropdown(['Balls', 'Axial rollers'])
        self.gauge.connect('notify::selected', lambda *_: self.request_changed())
        row.append(self.gauge)
        box.append(row)
        reset = Gtk.Button(label='Use theoretical gauge diameter')
        reset.connect('clicked', lambda _: self.default_diameter())
        box.append(reset)
        heading(box, 'Results')
        box.append(self.result_summary)
        span_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        span_box.append(Gtk.Label(label='Wildhaber span · number of teeth', xalign=0))
        self.spans = choice_dropdown([])
        self.spans.connect('notify::selected', lambda *_: self.span_changed())
        span_box.append(self.spans)
        self.span_summary = Gtk.Label(xalign=0, wrap=True, selectable=True)
        span_box.append(self.span_summary)
        span_details = Gtk.Expander(label='Tooth span measurement')
        span_details.set_child(span_box)
        box.append(span_details)
        box.append(Gtk.Label(label='External/internal spur only. Balls touch at points; rollers touch along axial lines. Helical and double-helical measurements are unsupported.', wrap=True, xalign=0))
        self.report = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.report._ratiolab_localize_report = True
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, min_content_height=170)
        scroll.set_child(self.report)
        self.report_details = Gtk.Expander(label='Full report')
        self.report_details.set_child(scroll)
        self.report_details.set_visible(False)
        box.append(self.report_details)
        buttons = actions(box)
        buttons.set_max_children_per_line(2)
        self.run_button = Gtk.Button(label='Calculate', css_classes=['primary'])
        self.run_button.connect('clicked', lambda _: self.calculate())
        buttons.append(self.run_button)
        self.save_button = Gtk.Button(label='Export report · TXT + JSON')
        self.save_button.connect('clicked', lambda _: self.export())
        buttons.append(self.save_button)
        self.window.pin(buttons)
        self.save_button.set_sensitive(False)
        self.populate()
        if preferred in self.indices:
            self.parts.set_selected(self.indices.index(preferred))
        draft = getattr(self, 'draft', None)
        if draft and draft['key'] == self.draft_key() and draft['part'] in self.indices and preferred in (None, draft['part']):
            self.parts.set_selected(self.indices.index(draft['part']))
            self.diameter.set_text(draft['diameter'])
            self.gauge.set_selected(draft['gauge'])
        self.window.present()

    def populate(self):
        from gi.repository import Gtk
        self.syncing = True
        previous = self.indices[self.parts.get_selected()] if self.parts.get_selected() < len(self.indices) else None
        self.indices = []
        if self.current():
            self.indices = [i for i, p in enumerate(self.design.parts)
                            if 'measurement_geometry' in p.profile_metadata.get('tooth_profile', {})]
        from components_ui import component_title
        self.parts.set_model(Gtk.StringList.new([f'{i+1:03d} · {component_title(self.design.parts[i])}' for i in self.indices]))
        if previous in self.indices:
            self.parts.set_selected(self.indices.index(previous))
        self.syncing = False
        self.run_button.set_sensitive(bool(self.indices))
        if previous not in self.indices:
            self.default_diameter()
        self.update_component()
        if not self.indices:
            reason = ('Requires a generated external or internal spur involute component.' if self.current()
                      else 'Generate a valid model first.')
            self.request_changed(reason)

    def selected_index(self):
        selected = self.parts.get_selected()
        return self.indices[selected] if selected < len(self.indices) else None

    def part_changed(self):
        if not self.syncing:
            self.default_diameter()
            self.update_component()

    def update_component(self):
        index = self.selected_index()
        from tool_capabilities import gauge_components
        supported = self.current() and index in gauge_components(self.design)
        self.run_button.set_sensitive(supported)
        if not supported:
            self.result_summary.set_text('Requires a generated external or internal spur involute component.')
        profile = self.design.parts[index].profile_metadata['tooth_profile'] if index is not None and self.current() else {}
        g = profile.get('measurement_geometry', {})
        self.component_summary.set_text(f"{g['teeth']} teeth · reference Ø {2*g['reference_radius_mm']:.6g} mm" if g else 'No current component')
        span = profile.get('wildhaber_span', {})
        self.span_rows = span.get('usable_spans', [])
        self.spans.set_model(Gtk.StringList.new([str(row['k']) for row in self.span_rows]))
        chosen = next((i for i, row in enumerate(self.span_rows) if row['k'] == span.get('recommended_k')), 0)
        self.spans.set_selected(chosen)
        self.spans.set_sensitive(bool(self.span_rows))
        self.span_changed()

    def span_changed(self):
        rows = getattr(self, 'span_rows', [])
        index = self.spans.get_selected()
        if index < len(rows):
            row = rows[index]
            self.span_summary.set_text(f"W{row['k']} = {row['span_mm']:.6f} mm\nContact R {row['contact_radius_mm']:.6f} mm · symmetric flat jaws")
        else:
            self.span_summary.set_text('No usable external spur span for this component.')

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
        self.report_details.set_visible(False)
        self.result_summary.set_text(message)

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
        self.report_details.set_visible(True)
        self.report.get_buffer().set_text(measurement_query_text(query))
        r = query['result']
        self.result_summary.set_text(f"{r['dimension_kind']}: {r['dimension_mm']:.6f} mm\nGauge Ø {r['gauge_diameter_mm']:.6f} mm · contact R {r['contact_radius_mm']:.6f} mm" if r['status'] == 'ok' else 'Measurement unavailable\n'+r['reason'])
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
