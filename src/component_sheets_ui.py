# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Transactional company fields and printable sheets for one selected component."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import uuid
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
import component_sheets as sheets
from export_feedback import ExportResult


class Editor:
    def __init__(self, app, index):
        self.app = app
        self.index = index
        self.token = app.document.token
        self.design = app.design
        self.draft = sheets.draft(self.design, index, getattr(app, 'component_sheets', {}))
        self.checks = []
        self.dialog = Gtk.Dialog(title='Component production / inspection sheets', application=app,
            transient_for=app.win, destroy_with_parent=True, css_classes=['reducers'],
            modal=True, use_header_bar=False, default_width=900, default_height=680)
        app.project_dialog = self.dialog
        self.dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        self.dialog.add_button('Apply to project', Gtk.ResponseType.APPLY)
        self.dialog.add_button('Export PDFs', Gtk.ResponseType.ACCEPT)
        body = self.dialog.get_content_area()
        body.set_spacing(8)
        for setter in (body.set_margin_start, body.set_margin_end, body.set_margin_top, body.set_margin_bottom):setter(14)
        part = self.design.parts[index]
        title = Gtk.Label(label=f'{index+1:03d} · {part.name}', xalign=0, wrap=True)
        title._ratiolab_no_translate = True
        body.append(title)
        message = ('Geometry changed. Review the retained fields and limits, then Apply to bind them to this model.'
            if self.draft['stale'] else 'Company fields are saved in this project. Operations and acceptance limits are defined by your company.')
        body.append(Gtk.Label(label=message, xalign=0, wrap=True))
        stack = Gtk.Stack(vexpand=True)
        body.append(Gtk.StackSwitcher(stack=stack))
        body.append(stack)
        self.company_entries = {}
        self.part_entries = {}
        production = self.page(stack, 'production', 'Production')
        for key, label in sheets.COMPANY_FIELDS.items():
            self.company_entries[key] = self.entry(production, label, self.draft['company'].get(key, ''))
        production.append(Gtk.Separator())
        for key, label in sheets.PART_FIELDS.items():
            value = self.draft['fields'].get(key, '')
            self.part_entries[key] = self.entry(production, label, value, multiline=key in ('operations', 'notes'))
        inspection = self.page(stack, 'inspection', 'Inspection')
        inspection.append(Gtk.Label(label='Limits are absolute minimum / maximum values, not deviations. Leave them blank when undefined. PDF result cells are left blank for recording.', xalign=0, wrap=True))
        inspection.append(Gtk.Label(label='Automatic gauge dimensions use the theoretical default diameter. Instrument access and contact setup must be approved by the company.', xalign=0, wrap=True))
        self.check_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inspection.append(self.check_box)
        for row in self.draft['checks']:self.add_check(row, restoring=True)
        self.add_button = Gtk.Button(label='Add company characteristic')
        self.add_button.connect('clicked', lambda _: self.add_check(dict(id='custom:'+uuid.uuid4().hex,
            label='', nominal='', unit='mm', lower='', upper='', method='', instrument='', datum='')))
        inspection.append(self.add_button)
        self.error = Gtk.Label(xalign=0, wrap=True, css_classes=['error'])
        body.append(self.error)
        self.dialog.connect('response', self.response)
        self.dialog.connect('close-request', self.close_requested)
        self.dialog.connect('unrealize', self.retire)
        app.language.refresh()
        self.dialog.present()

    def page(self, stack, key, title):
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(content)
        stack.add_titled(scroll, key, title)
        return content

    def entry(self, body, title, value, multiline=False, editable=True):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        row.append(Gtk.Label(label=title, xalign=0, wrap=True))
        if not editable:
            widget = Gtk.Label(label=value, xalign=0, selectable=True, wrap=True)
            row.append(widget)
        elif multiline:
            widget = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, editable=editable)
            widget.get_buffer().set_text(value)
            scroll = Gtk.ScrolledWindow(min_content_height=90, hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroll.set_child(widget)
            row.append(scroll)
        else:
            widget = Gtk.Entry(text=value, editable=editable, hexpand=True)
            widget.set_max_length(4000)
            row.append(widget)
        # User data must never enter the interface translation catalog.
        widget._ratiolab_no_translate = True
        body.append(row)
        return widget

    @staticmethod
    def value(widget):
        if isinstance(widget, Gtk.TextView):
            buf = widget.get_buffer()
            return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        return widget.get_text()

    def add_check(self, row, restoring=False):
        # A new geometry can add automatic rows to a full saved plan. Display
        # every retained company row; validation asks for a smaller plan rather
        # than silently losing rows while constructing the editor.
        if not restoring and len(self.checks) >= sheets.MAX_CHECKS:
            if hasattr(self, 'error'):self.error.set_text('A sheet supports at most 40 inspection characteristics.')
            return
        automatic = row['id'].startswith('auto:')
        expander = Gtk.Expander(label=row['label'] if automatic else 'Company characteristic')
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=12)
        expander.set_child(content)
        entries = {}
        for key, label in [('label','Characteristic'), ('nominal','Nominal'), ('unit','Unit'),
                ('lower','Minimum (absolute)'), ('upper','Maximum (absolute)'), ('method','Method / contact setup'),
                ('instrument','Instrument / ID'), ('datum','Datum / drawing reference')]:
            fixed = automatic and (key in ('label', 'nominal', 'unit') or key == 'method' and bool(row['method']))
            entries[key] = self.entry(content, label, row[key], editable=not fixed)
            if fixed and key == 'label':entries[key]._ratiolab_no_translate = False
        record = (row['id'], entries, expander)
        self.checks.append(record)
        if not automatic:
            remove = Gtk.Button(label='Remove characteristic')
            def removed(_):
                self.checks.remove(record)
                self.check_box.remove(expander)
            remove.connect('clicked', removed)
            content.append(remove)
        self.check_box.append(expander)

    def current(self):
        a = self.app
        return (a.project_alive and a.document.token == self.token and a.design is self.design
            and not a.busy and not a.pending and not getattr(a, '_geometry_waiting', False))

    def commit(self):
        if not self.current():
            raise ValueError('The document changed. Close this editor and select the component again.')
        company = {k:self.value(w) for k, w in self.company_entries.items()}
        fields = {k:self.value(w) for k, w in self.part_entries.items()}
        checks = [dict(id=key, **{k:self.value(w) for k, w in entries.items()}) for key, entries, _ in self.checks]
        result = sheets.apply(self.design, self.index, getattr(self.app, 'component_sheets', {}), company, fields, checks)
        self.app.component_sheets = result
        self.app.project_changed()
        self.token = self.app.document.token
        self.app.components.refreshed(self.design)
        return result

    def response(self, dialog, code):
        if code not in (Gtk.ResponseType.APPLY, Gtk.ResponseType.ACCEPT):
            self.close()
            return
        try:
            metadata = self.commit()
            if code == Gtk.ResponseType.APPLY:
                self.close()
                return
            report = sheets.report(self.design, self.index, metadata,
                str(self.app.document.path) if self.app.document.path else '', self.app.document.revision)
        except (ValueError, TypeError) as error:
            self.error.set_text(str(error))
            return
        a = self.app
        target = Path(a.output_dir).absolute()/f'{a.family}-{datetime.now():%Y%m%d-%H%M%S-%f}.component-{self.index+1:03d}'
        report = deepcopy(report)
        language = a.language.language
        self.close()
        def work():
            from sheet_pdf import export
            folder = export(report, target, language=language)
            return ExportResult('Component PDFs', (folder/'production.pdf', folder/'inspection.pdf'),
                f'Production and inspection PDFs exported · {folder}')
        a.background(work, export_job=True)

    def close_requested(self, *_):
        self.close()
        return True

    def close(self):
        if self.app.project_dialog is self.dialog:self.app.project_dialog = None
        self.dialog.destroy()

    def retire(self, *_):
        if self.app.project_dialog is self.dialog:self.app.project_dialog = None


def open_editor(app, index):
    if app.project_dialog or app.busy:return None
    # Selection already belongs to the accepted design and current document.
    # A redundant refresh can rebuild its scene/parts and clear that selection
    # on first launch. Never regenerate geometry merely to edit company fields.
    if app.pending or getattr(app, '_geometry_waiting', False):return None
    if not app.components.current() or app.components.selected != (index,):return None
    return Editor(app, index)
