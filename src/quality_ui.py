# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Transactional representation settings; nominal construction is retained."""
from dataclasses import dataclass
from threading import Event
from gi.repository import Gtk, GLib
from geometry_quality import normalize, settings, with_quality
from geometry_refresh import LatestOnly


@dataclass(frozen=True)
class QualityRequest:
    candidate: object
    changed_preview: bool
    flags: tuple
    valid: object
    completed: object


def prepare_quality(request,current):
    """One app-owned worker; stale requests stop at existing kernel checks."""
    from precision_ui import Request, prepare
    if isinstance(request,Request):return prepare(request,current)
    from rust_geometry import control_scope
    class Superseded(Exception):pass
    def check():
        if not current() or not request.valid():raise Superseded()
    try:
        with control_scope(check):
            check()
            if request.changed_preview:
                from preview3d import build_scene
                scene=build_scene(request.candidate,*request.flags,frame_explosion=True)
            else:scene=None
            check()
            return (scene,)
    except Superseded:return None


def quality_worker(app):
    worker=getattr(app,'quality_worker',None)
    if worker is None:
        worker=LatestOnly(prepare_quality,GLib.idle_add,
            lambda request,result,error:request.completed(result,error))
        app.quality_worker=worker
        app.win.connect('unrealize',lambda *_:worker.close())
    return worker


def open_quality(app, *, host=None, container=None):
    if app.busy or app.project_dialog:
        return
    app.settle_project()
    if app.design is None:
        return
    embedded=host is not None
    dialog=host if embedded else Gtk.Dialog(title='Surface detail',transient_for=app.win,modal=True,
                                           destroy_with_parent=True,css_classes=['reducers'])
    if not embedded:
        dialog.set_default_size(720,660)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button('Apply',Gtk.ResponseType.APPLY)
    box=container if embedded else dialog.get_content_area()
    if not embedded:
        scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        for setter in (content.set_margin_start,content.set_margin_end,content.set_margin_top,content.set_margin_bottom):setter(16)
        scroll.set_child(content);box.append(scroll);box=content
    box.append(Gtk.Label(label='Saved with the current project. Preview and export can use different precision.',xalign=0,wrap=True))
    entries={}
    for key,title in [('preview_mm','Preview'),('export_mm','Export')]:
        entries[key]=Gtk.Entry(text=str(settings(app.design).get(key,'')),hexpand=True,
                               placeholder_text='Part default (normally 0.02 mm)')
    from precision_ui import Comparison
    comparison=Comparison(app,box,entries)
    app.quality_comparison=comparison
    box.append(Gtk.Label(label='Surface interpolation · millimetres',xalign=0))
    fields=Gtk.Grid(column_spacing=14,row_spacing=10)
    for row,(key,title) in enumerate((('preview_mm','Preview'),('export_mm','Export'))):
        fields.attach(Gtk.Label(label=title,xalign=0),0,row,1,1)
        fields.attach(entries[key],1,row,1,1)
    box.append(fields)
    error=Gtk.Label(xalign=0,wrap=True);error.add_css_class('error');box.append(error)
    apply_button=Gtk.Button(label='Apply',halign=Gtk.Align.START) if embedded else dialog.get_widget_for_response(Gtk.ResponseType.APPLY)
    if embedded:box.append(apply_button)
    app.quality_apply_button=apply_button
    app.project_dialog=dialog
    app.quality_dialog=dialog;app.quality_entries=entries
    preparing=False;closed=Event()
    worker=quality_worker(app)
    def finish():
        if closed.is_set():return
        closed.set()
        if app.project_dialog is dialog:app.project_dialog=None
        if app.quality_dialog is dialog:
            app.quality_dialog=None
            worker.invalidate()
        comparison.close()
        if not embedded:dialog.destroy()
    def response(_,code):
        nonlocal preparing
        if code!=Gtk.ResponseType.APPLY:finish();return
        if preparing:return
        try:
            value=normalize({key:float(entry.get_text().strip().replace(',','.'))
                             for key,entry in entries.items() if entry.get_text().strip()})
        except ValueError as caught:error.set_text(str(caught));return
        source=app.design;token=app.document.token
        candidate=with_quality(source,value)
        if value==settings(source):
            if not embedded:finish()
            return
        changed_preview=value.get('preview_mm')!=settings(source).get('preview_mm')
        comparison.pause()
        preparing=True;box.set_sensitive(False)
        apply_button.set_sensitive(False)
        error.set_text('Preparing preview…' if changed_preview else 'Applying export setting…')
        flags=(app.canvas.show_support,app.canvas.show_housing)
        def valid():
            return (not closed.is_set() and app.project_alive and
                app.document.token==token and app.design is source and
                flags==(app.canvas.show_support,app.canvas.show_housing))
        def completed(result,caught):
            nonlocal preparing
            if closed.is_set() or not app.project_alive or not dialog.get_visible():return False
            preparing=False;box.set_sensitive(True);apply_button.set_sensitive(True)
            comparison.paused=False
            comparison.schedule()
            if app.document.token!=token or app.design is not source:
                error.set_text('The model changed. Apply again to the current model.');return False
            if flags!=(app.canvas.show_support,app.canvas.show_housing):
                error.set_text('The preview changed. Apply again to the current view.');return False
            if caught:
                error.set_text(str(caught));return False
            if result is None:return False
            scene,=result
            selected=tuple(app.components.selected)
            app.quality=value
            app.apply_design(candidate,candidate.values,None,reuse_scene=not changed_preview,prepared_scene=scene)
            app.project_changed('surface-quality')
            app.components.refreshed(candidate)
            app.components.selected=selected;app.canvas.selected_indices=selected
            app.components.clear_points();app.components.cache={};app.components.update()
            if embedded:
                error.set_text('')
                comparison.refresh()
            else:finish()
            return False
        worker.submit(QualityRequest(candidate,changed_preview,flags,valid,completed))
    if embedded:apply_button.connect('clicked',lambda *_:response(dialog,Gtk.ResponseType.APPLY))
    else:dialog.connect('response',response)
    def close_dialog(*_):finish();return True
    if not embedded:dialog.connect('close-request',close_dialog)
    dialog.connect('unrealize',lambda *_:finish())
    if not embedded:
        app.language.refresh()
        dialog.present()
    return dialog
