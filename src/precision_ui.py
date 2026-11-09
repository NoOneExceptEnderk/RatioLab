# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Asynchronous, model-specific comparison of the existing surface presets."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from threading import Event
from gi.repository import Gtk, GLib, Pango
from geometry_quality import PRESETS, normalize, with_quality, deviation


def millimetres(value, *, bound=False):
    number = Decimal.from_float(value) if bound else Decimal(str(value))
    if bound and number:
        number = number.quantize(Decimal(1).scaleb(number.adjusted()-3), rounding=ROUND_CEILING)
    mm = format(number, 'f').rstrip('0').rstrip('.') if '.' in format(number, 'f') else format(number, 'f')
    microns = format(number*1000, 'f').rstrip('0').rstrip('.') if '.' in format(number*1000, 'f') else format(number*1000, 'f')
    return ('≤ ' if bound else '') + f'{mm} mm · {microns} µm'


@dataclass(frozen=True)
class Request:
    source: object
    rows: tuple
    valid: object
    completed: object


def prepare(request, current):
    from rust_geometry import control_scope
    class Superseded(Exception): pass
    def check():
        if not current() or not request.valid(): raise Superseded()
    results = {}
    cache = {}
    try:
        with control_scope(check):
            for key, quality, purpose in request.rows:
                check()
                # Presets and current selection often request the same surface.
                cache_key = (purpose, tuple(sorted(quality.items())))
                if cache_key not in cache:
                    try:
                        cache[cache_key] = deviation(with_quality(request.source, quality), purpose)
                    except ValueError as error:
                        check()
                        cache[cache_key] = dict(interpolation_mm=None, model_mm=None, error=str(error))
                results[key] = cache[cache_key]
            check()
        return results
    except Superseded:
        return None


def report_worker(app):
    # Bounds and preview preparation share the existing bounded worker/queue.
    from quality_ui import quality_worker
    return quality_worker(app)


class Comparison:
    def __init__(self, app, box, entries):
        self.app, self.entries = app, entries
        self.closed = Event()
        self.timer = 0
        self.paused = False
        self.worker = report_worker(app)
        self.result = None
        self.cells = {}
        self.buttons = {}
        box.append(Gtk.Label(label='Geometric deviation for the current model', xalign=0,
                             wrap=True, css_classes=['step-title']))
        grid = Gtk.Grid(column_spacing=14, row_spacing=12, column_homogeneous=True)
        box.append(grid)
        def label(text):
            return Gtk.Label(label=text, xalign=0, wrap=True, width_chars=1, hexpand=True)
        for column, text in enumerate(('Setting', 'Requested interpolation',
                                       'Sweep error bound', 'Complete model bound')):
            heading = label(text); heading.add_css_class('muted'); grid.attach(heading, column, 0, 1, 1)
        rows = [(name, millimetres(value)) for name, value in PRESETS]
        rows += [('Part default', '—'), ('Preview', '—'), ('Export', '—')]
        for row, (name, value) in enumerate(rows, 1):
            key = name
            presets = dict(PRESETS)
            if name in presets or name == 'Part default':
                button=Gtk.Button(label=name, valign=Gtk.Align.CENTER)
                button.get_child().set_wrap(True)
                button.get_child().set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                button.get_child().set_width_chars(1)
                button.set_tooltip_text('Use for preview and export')
                def select(*_,value=presets.get(name)):
                    for entry in entries.values():entry.set_text('' if value is None else str(value))
                button.connect('clicked',select)
                grid.attach(button,0,row,1,1);self.buttons[name]=button
            else:grid.attach(label(name),0,row,1,1)
            cells = [label(value), label('Calculating…'), label('Calculating…')]
            for column, cell in enumerate(cells, 1):
                grid.attach(cell, column, row, 1, 1)
            self.cells[key] = cells
        self.status = label('Calculating…'); self.status.add_css_class('muted'); box.append(self.status)
        details=Gtk.Expander(label='Precision limits')
        notes=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        details.set_child(notes);box.append(details)
        for text in (
            'Bounds are calculated for this model, in millimetres and micrometres. They describe geometric approximation, not elastic deformation.',
            'Sweep error is relative to sampled contours. Fixed tooth profiles and explicit meshes can limit accuracy even with Fine selected.',
            'Complete model bounds exclude screen rendering, file conversion and manufacturing. Not bounded means no verified complete bound is available; it does not mean zero error.'):
            note = label(text); note.add_css_class('muted'); notes.append(note)
        for entry in entries.values():
            entry.connect('changed', self.schedule)
        self.refresh()

    def schedule(self, *_):
        if self.paused or self.closed.is_set():return
        self.worker.invalidate()
        self.result = None
        for cells in self.cells.values():
            for cell in cells[1:]:cell.set_text('Calculating…')
        if self.timer:GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(250, self.refresh)

    def refresh(self):
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = 0
        if self.closed.is_set() or self.paused:return False
        source = self.app.design
        if source is None:return False
        try:
            quality = normalize({key:float(entry.get_text().strip().replace(',', '.'))
                for key, entry in self.entries.items() if entry.get_text().strip()})
        except ValueError:
            self.status.set_text('Enter positive interpolation values to calculate bounds.')
            for name in ('Preview', 'Export'):
                for cell in self.cells[name]:cell.set_text('—')
            return False
        rows = [(name, dict(preview_mm=value, export_mm=value), 'export') for name, value in PRESETS]
        rows += [('Part default', {}, 'export'), ('Preview', quality, 'preview'), ('Export', quality, 'export')]
        for name, key in (('Preview', 'preview_mm'), ('Export', 'export_mm')):
            self.cells[name][0].set_text(millimetres(quality[key]) if key in quality else 'Part default')
        self.status.set_text('Calculating…')
        def valid():return not self.closed.is_set() and self.app.project_alive and self.app.design is source
        def completed(result, error):
            if not valid():return False
            if error:
                self.status.set_text(str(error));return False
            if result is None:return False
            self.result = result
            for name, record in result.items():
                for cell, key in zip(self.cells[name][1:], ('interpolation_mm', 'model_mm')):
                    cell.set_text(millimetres(record[key], bound=True) if record[key] is not None else 'Not bounded')
                    cell.set_tooltip_text(record.get('error') or record.get('reason'))
            self.status.set_text('Bounds updated.')
            self.app.language.refresh()
            return False
        self.worker.submit(Request(source, tuple(rows), valid, completed))
        return False

    def pause(self):
        self.paused = True
        if self.timer:
            GLib.source_remove(self.timer);self.timer = 0
        self.worker.invalidate()

    def close(self):
        self.closed.set()
        if self.timer:
            GLib.source_remove(self.timer);self.timer = 0
        self.worker.invalidate()
