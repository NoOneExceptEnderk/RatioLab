# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Latest-only tooth-detail preparation and a reversible viewport focus."""
from dataclasses import dataclass
from math import isfinite
from gi.repository import Gtk, GLib
from geometry_refresh import LatestOnly
from rust_geometry import control_scope
from tooth_tip_preview import member_for_field, component_index, prepare, prepare_component, supported
from motion import SPEED_KEYS


@dataclass(frozen=True)
class Request:
    design: object
    field: str
    document_identity: str
    component_name: str = None
    scene: object = None
    visible_indices: tuple = None


def prepare_detail(request, current):
    def check():
        if not current():
            raise RuntimeError('Tooth detail superseded')
    with control_scope(check):
        check()
        options=dict(base_scene=request.scene,visible_indices=request.visible_indices)
        if request.component_name is not None:
            index=next(i for i,p in enumerate(request.design.parts) if p.name==request.component_name)
            return prepare_component(request.design,index,**options)
        return prepare(request.design, request.field,**options)


class Controller:
    def __init__(self, app):
        self.app = app
        self.field = self.document_identity = None
        self.component_name = None
        self.waiting = False
        self.step_inputs = {}
        self.worker = LatestOnly(prepare_detail,
            lambda callback, *args: GLib.idle_add(callback, *args), self.completed)
        self.reset_camera=Gtk.Button(label='reset cam',halign=Gtk.Align.START,valign=Gtk.Align.START,
            margin_start=12,margin_top=12,visible=False)
        self.reset_camera.connect('clicked',lambda *_:app.canvas.reset_tooth_camera())
        app.preview_overlay.add_overlay(self.reset_camera)
        app.canvas.tooth_detail_closed = self.closed
        app.win.connect('unrealize', lambda *_: self.worker.close())

    def step_control(self, spin, field, default):
        """Change only this field's UI increment, never its physical value."""
        from gui_workflow import normalized_numeric_text
        from workspace_ui import save_ui_preference
        app = self.app
        key = app.family+':'+field
        limit = spin.get_adjustment().get_upper()-spin.get_adjustment().get_lower()
        stored = app.workspace_preferences['tooth_tip_steps'].get(key, default)
        applied = stored if 0 < stored <= limit else default
        spin._minimum_search_step = default
        spin.set_increments(applied, 10*applied)
        entry = Gtk.Entry(hexpand=True, width_chars=3, max_width_chars=8,
                          input_purpose=Gtk.InputPurpose.NUMBER,
                          css_classes=['parameter-input', 'tooth-step'])
        entry.set_text(str(applied))
        entry.set_tooltip_text('Step size')
        self.step_inputs[field] = entry
        def parse():
            try:
                value = float(entry.get_text().strip().replace(',', '.'))
                if isfinite(value) and 0 < value <= limit:
                    return value
            except ValueError:
                pass
            return None
        def changed(*_):
            nonlocal applied
            value = parse()
            if value is None:
                entry.add_css_class('field-error')
                entry.set_tooltip_text('Enter a finite step greater than zero and no larger than the field range.')
                return
            entry.remove_css_class('field-error')
            entry.set_tooltip_text('Step size')
            if value != applied:
                applied = value
                spin.set_increments(value, 10*value)
        def commit(*_):
            changed()
            value = parse()
            if value is None:
                return
            compact = normalized_numeric_text(entry.get_text(), low=0, high=limit)
            if compact != entry.get_text():
                entry.set_text(compact)
            current = app.workspace_preferences['tooth_tip_steps']
            if current.get(key) != value:
                save_ui_preference(app, tooth_tip_steps={**current, key: value})
        entry.connect('changed', changed)
        entry.connect('activate', commit)
        focus = Gtk.EventControllerFocus()
        focus.connect('leave', commit)
        entry.add_controller(focus)
        return entry

    def bind(self, spin, field):
        if member_for_field(self.app.family, self.app.field_values.get('variant'), field) is None:
            return
        focus = Gtk.EventControllerFocus()
        focus.connect('enter', lambda *_: self.focus(field))
        spin.add_controller(focus)

    def focus(self, field):
        app = self.app
        if app.building or getattr(app, 'project_restoring', False):
            return
        same=(self.component_name is None and self.document_identity==app.document.token[0]
            and self.field is not None and member_for_field(app.family,app.field_values.get('variant'),self.field)
                ==member_for_field(app.family,app.field_values.get('variant'),field))
        self.field = field
        self.component_name = None
        self.document_identity = app.document.token[0]
        self.reset_camera.set_visible(True)
        if same and app.canvas.tooth_detail is not None and not self.waiting:return
        self.refreshed()

    def focus_component(self,index):
        app=self.app
        if app.building or app.design is None or not 0<=index<len(app.design.parts) or not supported(app.design.parts[index]):
            return
        self.field=None;self.component_name=app.design.parts[index].name
        self.reset_camera.set_visible(False)
        self.document_identity=app.document.token[0]
        self.refreshed()

    def edited(self, field):
        app = self.app
        # A completed numeric search must not reopen a session closed with Home.
        # Entering a real tip field starts the session through its focus handler.
        if self.component_name is None and self.field is None:return
        tip_member=member_for_field(app.family, app.field_values.get('variant'), field)
        self.worker.invalidate()
        if tip_member is not None:
            self.field=field;self.component_name=None
            self.reset_camera.set_visible(True)
        self.document_identity = app.document.token[0]
        self.waiting = True
        self.reset_camera.set_sensitive(self.has_current_target())

    def refreshed(self):
        app = self.app
        if self.field is None and self.component_name is None:
            return
        if self.document_identity != app.document.token[0]:
            self.close()
            return
        if app.design is None or app.pending:
            return
        self.waiting = True
        self.reset_camera.set_sensitive(self.has_current_target())
        self.worker.submit(Request(app.design,self.field,self.document_identity,self.component_name,
                                   app.canvas.scene,self.visible_indices()))

    def has_current_target(self):
        # A focus-out commit can start a refresh during a Reset mouse press.
        # Its existing camera target remains usable for this same component.
        app=self.app
        detail=app.canvas.tooth_detail
        if detail is None or app.design is None or self.field is None:return False
        try:index=component_index(app.design,self.field)
        except (ValueError,StopIteration):return False
        return app.design.parts[index].name==detail.part_name

    def visible_indices(self):
        canvas=self.app.canvas
        return tuple(p.source_index for p in canvas.scene.parts
                     if canvas.isolated_indices is None or p.source_index in canvas.isolated_indices)

    def completed(self, request, detail, error):
        app = self.app
        if (not getattr(app, 'project_alive', False)
                or request.document_identity != app.document.token[0]
                or request.design is not app.design or request.field != self.field
                or request.component_name!=self.component_name):
            return
        if request.scene is not app.canvas.scene or request.visible_indices!=self.visible_indices():
            self.refreshed();return
        self.waiting = False
        if error is not None:
            self.close()
            app.status_text('Removed-material preview unavailable')
            app.status.set_tooltip_text(str(error))
            return
        app.canvas.show_tooth_detail(detail)
        self.reset_camera.set_sensitive(True)

    def invalid(self):
        self.worker.invalidate()
        self.waiting = False

    def closed(self):
        self.worker.invalidate()
        self.field = self.document_identity = None
        self.component_name = None
        self.waiting = False
        self.reset_camera.set_visible(False)

    def close(self):
        self.closed()
        self.app.canvas.clear_tooth_detail()
