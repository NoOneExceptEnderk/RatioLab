# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Revision-bound component inspection; view operations never enter history."""
from copy import deepcopy
from datetime import datetime
from math import pi
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from project_document import equivalent
from workspace_tools import actions, details
import component_geometry as geometry
import selected_export


def label(text=''):
    return Gtk.Label(label=text,xalign=0,wrap=True,selectable=False)


class Controller:
    def __init__(self,app,container):
        self.app=app;self.window=None;self.snapshot=None;self.revision=None;self.selected=();self.saved_filters=None;self.points=[];self.cache={};self.syncing=False;self.pose=None;self.alive=True
        self.button=Gtk.Button(label='Components / measure…');self.button.connect('clicked',lambda _:self.open())
        self.summary=label('Click a visible surface to select · Ctrl/Shift adds');self.summary.set_hexpand(True)
        self.markers=Gtk.DrawingArea(hexpand=True,vexpand=True);self.markers.set_can_target(False);self.markers.set_draw_func(self.draw);app.preview_overlay.add_overlay(self.markers)
        container.register('components', self)
        self.summary.connect('notify::label',lambda w,*_:app.status_text(w.get_text()) if 'unavailable' in w.get_text().lower() else None)
        app.canvas.connect('component-click',lambda *args:self.clicked(*args) if app.pick_mode.get_selected()!=0 else None)
        app.canvas.connect('view-changed',lambda *_:self.markers.queue_draw())
        app.canvas.connect('display-state',self.display_changed)
        app.canvas.connect('motion-state',self.display_changed)
        app.canvas.connect('inspection-state',self.inspection_changed)
        app.win.connect('unrealize',lambda *_:self.close())

    def current(self):
        app=self.app
        return self.alive and getattr(app,'project_alive',False) and self.revision is not None and hasattr(app,'document') and self.revision==app.document.token and self.snapshot is not None and equivalent(app.project_snapshot(),self.snapshot) and app.design is not None

    def changed(self,snapshot):
        if self.snapshot is not None and not equivalent(snapshot,self.snapshot):self.invalidate('Model changed · selection cleared')

    def refreshed(self,design):
        app=self.app
        if not hasattr(app,'document'):return
        snapshot=app.project_snapshot()
        if self.revision!=app.document.token or (self.snapshot is not None and not equivalent(self.snapshot,snapshot)):
            self.invalidate('Select components from this revision')
        self.revision=app.document.token;self.snapshot=deepcopy(snapshot)
        self.cache={}
        self.populate();self.update()

    def invalidate(self,message='Document replaced · selection cleared'):
        self.restore();self.selected=();self.points=[];self.cache={};self.revision=None;self.snapshot=None
        self.app.canvas.selected_indices=();self.app.canvas.queue_render();self.markers.queue_draw()
        self.summary.set_text(message)
        if self.window:self.populate();self.update()

    def close(self):
        self.invalidate();self.alive=False
        if self.window:self.window.destroy();self.window=None

    def open(self):
        if self.window:self.window.present();return
        if hasattr(self.app,'document') and self.app.design and self.revision is None:self.refreshed(self.app.design)
        win=self.app.tools.panel('components')
        self.window=win;body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9,margin_start=14,margin_end=14,margin_top=14,margin_bottom=14);win.set_child(body)
        body.append(self.summary)
        self.inspector_stack=Gtk.Stack();self.inspector_stack.set_hhomogeneous(False);self.inspector_stack.set_vhomogeneous(False)
        tabs=Gtk.StackSwitcher(stack=self.inspector_stack);body.append(tabs);body.append(self.inspector_stack)
        parts_body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9)
        measure_body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9)
        self.inspector_stack.add_titled(parts_body,'parts','Parts')
        self.inspector_stack.add_titled(measure_body,'measure','Measure')
        body=parts_body
        self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE);self.list.connect('selected-rows-changed',self.rows_changed)
        scroll=Gtk.ScrolledWindow(vexpand=True);scroll.set_min_content_height(150);scroll.set_child(self.list);body.append(scroll)
        buttons=actions(body)
        self.isolate_button=Gtk.Button(label='Isolate');self.isolate_button.connect('clicked',lambda _:self.isolate());buttons.append(self.isolate_button)
        self.restore_button=Gtk.Button(label='Restore view');self.restore_button.connect('clicked',lambda _:self.restore());buttons.append(self.restore_button)
        clear=Gtk.Button(label='Clear');clear.connect('clicked',lambda _:self.select(()));buttons.append(clear)
        self.detail=label();self.detail.set_selectable(True);detail_scroll=Gtk.ScrolledWindow(min_content_height=45,max_content_height=115,propagate_natural_height=True);detail_scroll.set_child(self.detail);details(body,'Nominal component bounds · mm',detail_scroll)
        measure_row=actions(measure_body)
        self.measure=Gtk.CheckButton(label='Measure surfaces')
        self.measure.connect('toggled',self.measure_mode_changed)
        self.inspector_stack.connect('notify::visible-child-name',lambda stack,*_:self.measure.set_active(stack.get_visible_child_name()=='measure'))
        measure_body.prepend(label('Pick point A, then point B on visible surfaces.'))
        reset=Gtk.Button(label='Clear points');reset.connect('clicked',lambda _:self.clear_points());measure_row.append(reset)
        nominal=Gtk.Button(label='Use nominal pose');nominal.connect('clicked',lambda _:self.nominal());measure_row.append(nominal)
        measure_body.append(label('Sampled surfaces · mm · first pick pauses motion.'))
        details(measure_body,'Measurement accuracy & pose','Straight point-to-point distance on preview/STL facets. Six decimals are display precision. No snapping, analytic diameter, closest-surface or CAD tolerance claim. Nominal bounds use world XYZ. Animated nonrigid flex/warp picking is unavailable: use nominal pose.')
        self.measure_text=label();self.measure_text.set_selectable(True);self.measure_text.add_css_class('measurement');measure_body.append(self.measure_text)
        body.append(Gtk.Separator());self.export_text=label();body.append(self.export_text)
        exports=actions(body);self.export_buttons=[]
        for kind,title in [('step','STEP'),('stl','STL'),('profiles','DXF / SVG'),('package','Package')]:
            b=Gtk.Button(label=title);b.connect('clicked',lambda _,k=kind:self.export(k));exports.append(b);self.export_buttons.append(b)
        win.connect('close-request',self.window_closed)
        self.populate();self.update();win.present();self.list.grab_focus()

    def measure_mode_changed(self, widget):
        self.clear_points()
        self.inspector_stack.set_visible_child_name('measure' if widget.get_active() else 'parts')
        if widget.get_active():self.app.pick_mode.set_selected(2)
        elif self.app.pick_mode.get_selected()==2:self.app.pick_mode.set_selected(1)

    def window_closed(self,*_):
        self.restore();self.clear_points();self.window=None
        if self.app.pick_mode.get_selected()==2:self.app.pick_mode.set_selected(1)
        return False

    def populate(self):
        if not self.window:return
        self.syncing=True
        while (child:=self.list.get_first_child()):self.list.remove(child)
        if self.app.design and self.revision is not None:
            visible=self.visible_indices()
            import bom
            for i,p in enumerate(self.app.design.parts):
                row=Gtk.ListBoxRow();row.source_index=i
                row.set_child(label(f'{i+1:03d} · {p.name} · {p.role} · {bom.part_info(p)["code"]}'+(' · hidden' if i not in visible else '')))
                self.list.append(row)
                if i in self.selected:self.list.select_row(row)
        self.syncing=False

    def rows_changed(self,*_):
        if not self.syncing:self.select(tuple(row.source_index for row in self.list.get_selected_rows()),False)

    def select(self,indices,sync=True):
        if not self.current():return
        self.selected=tuple(sorted(set(indices)));self.app.canvas.selected_indices=self.selected
        if self.saved_filters is not None:self.app.canvas.isolated_indices=self.selected
        self.app.canvas.queue_render()
        if sync:self.populate()
        self.update()

    def update(self):
        if hasattr(self.app,'update_export_scope'):self.app.update_export_scope()
        current=self.current();n=len(self.selected)
        if self.revision is not None:
            names=', '.join(f'{i+1:03d} {self.app.design.parts[i].name}' for i in self.selected[:2]) if current else ''
            if n>2:names+=f', +{n-2} more'
            self.summary.set_text(f'{n} selected'+(' · '+names if names else '')+(' · isolated' if self.saved_filters is not None else '')+' · Ctrl/Shift adds')
        if not self.window:return
        self.isolate_button.set_sensitive(current and n>0);self.restore_button.set_sensitive(self.saved_filters is not None)
        for button in self.export_buttons:button.set_sensitive(current and n>0 and not self.app.busy)
        descriptions=[]
        if current:
            for i in self.selected:
                p=self.app.design.parts[i];dims=geometry.dimensions(p)
                descriptions.append(f'{i+1:03d} {p.name} · nominal sampled XYZ bounds: '+ ' × '.join(f'{q:.6g}' for q in dims['size_mm'])+' mm'+f' · min {self.xyz(dims["min_mm"])} · max {self.xyz(dims["max_mm"])}')
        self.export_text.set_text(f'Export {n} selected components · nominal pose · includes hidden selections')
        self.detail.set_text('\n'.join(descriptions) or 'No current selection')
        if not self.points:self.measure_text.set_text('No measurement · click two visible surface points in Measure mode')

    @staticmethod
    def xyz(q):return '('+', '.join(f'{v:.6f}' for v in q)+') mm'

    def visible_indices(self):
        c=self.app.canvas
        return tuple(p.source_index for p in c.scene.parts if c.isolated_indices is None or p.source_index in c.isolated_indices) if c.scene else ()

    def isolate(self):
        if not self.current() or not self.selected:return
        app=self.app
        app.interference.restore_view()
        if self.saved_filters is None:self.saved_filters={k:w.get_active() for k,w in app.view_options.items()}
        app.canvas.isolated_indices=self.selected
        for key in ('support','housing'):app.view_options[key].set_active(True)
        self.populate();self.update();app.canvas.queue_render()

    def restore(self):
        saved=self.saved_filters;self.saved_filters=None;self.app.canvas.isolated_indices=None
        if saved:
            for key,value in saved.items():self.app.view_options[key].set_active(value)
        self.app.canvas.queue_render()
        if self.window:self.populate();self.update()

    def nominal(self):
        self.app.interference.restore_view();self.app.canvas.reset_motion();self.clear_points()
        for key in ('exploded','section'):self.app.view_options[key].set_active(False)

    def clear_points(self):
        self.points=[];self.pose=None;self.markers.queue_draw()
        if self.window:self.measure_text.set_text('No measurement · click two visible surface points in Measure mode')

    def pose_key(self):
        c=self.app.canvas
        return (c.motion_enabled,c.inspection_phase if c.inspection_phase is not None else c.motion_phase,c.exploded,c.section,c.motion_playing)

    def display_changed(self,*_):
        if self.points and (self.pose_key()!=self.pose or any(index not in self.visible_indices() for index,_ in self.points)):self.clear_points()
        self.populate();self.update();self.markers.queue_draw()

    def inspection_changed(self,*_):
        if self.app.canvas.inspection_phase is not None:self.restore()
        self.display_changed()

    def clicked(self,canvas,x,y,multiple=False):
        if not self.current() or self.app.busy:return
        if canvas.motion_playing:
            canvas.motion_phase=canvas.rendered_phase;canvas.set_motion_playing(False)
        plan=canvas.motion_plan if (canvas.motion_enabled or canvas.inspection_phase is not None) and not canvas.exploded else None
        if plan and (plan.flex or plan.warps):
            self.summary.set_text('Animated flex/warp surface picking unavailable · Components → Use nominal pose')
            if self.window:self.measure_text.set_text(self.summary.get_text())
            return
        if not canvas.scene:return
        phase=canvas.inspection_phase if canvas.inspection_phase is not None else canvas.motion_phase
        surfaces=[]
        try:
            for index in self.visible_indices():
                key=(index,canvas.exploded)
                if key not in self.cache:self.cache[key]=geometry.triangles(geometry.displayed_part(self.app.design,index,canvas.exploded))
                ts=self.cache[key]
                if plan:ts=geometry.posed(ts,plan,index,phase)
                surfaces.append((index,ts))
            s=canvas.scene
            origin,direction=geometry.ray(x,y,s.center,s.radius,canvas.zoom,canvas.yaw,canvas.tilt,canvas.get_width(),canvas.get_height())
            hit=geometry.pick(origin,direction,surfaces,s.center[1] if canvas.section else None,max_distance=8*s.radius)
        except (ValueError,ArithmeticError) as error:
            self.summary.set_text(f'Surface inspection unavailable: {error}');return
        measuring=self.window and self.measure.get_active()
        if not hit:
            if measuring:self.clear_points()
            elif not multiple:self.select(())
            return
        index,q,t=hit
        if measuring:
            if len(self.points)==2:self.clear_points()
            self.points.append((index,q));self.pose=self.pose_key()
            lines=[f'{"AB"[j]} · {i+1:03d} {self.app.design.parts[i].name} · XYZ {self.xyz(p)}' for j,(i,p) in enumerate(self.points)]
            if len(self.points)==2:lines.append(f'A–B straight distance: {geometry.distance(self.points[0][1],self.points[1][1]):.6f} mm')
            lines.append(('Displayed exploded pose' if canvas.exploded else 'Displayed motion / inspection pose' if plan else 'Nominal assembly pose')+f' · phase {phase*180/pi:.6g}° · sampled surfaces')
            self.measure_text.set_text('\n'.join(lines));self.markers.queue_draw()
        else:
            indices=set(self.selected) if multiple else set()
            if multiple and index in indices:indices.remove(index)
            else:indices.add(index)
            self.select(indices)

    def draw(self,area,cr,width,height):
        c=self.app.canvas
        if not self.points or not c.scene:return
        coords=[geometry.project(q,c.scene.center,c.scene.radius,c.zoom,c.yaw,c.tilt,width,height) for _,q in self.points]
        def stroke():
            cr.set_source_rgb(.035,.045,.06);cr.set_line_width(6);cr.stroke_preserve()
            cr.set_source_rgb(1,.92,.22);cr.set_line_width(2);cr.stroke()
        if len(coords)==2:cr.move_to(*coords[0]);cr.line_to(*coords[1]);stroke()
        for j,(x,y) in enumerate(coords):
            cr.arc(x,y,5,0,2*pi);stroke()
            cr.move_to(x+9,y-9);cr.set_font_size(16);cr.text_path('AB'[j])
            cr.set_source_rgb(.035,.045,.06);cr.set_line_width(4);cr.stroke_preserve()
            cr.set_source_rgb(1,.96,.5);cr.fill()

    def export(self,kind):
        app=self.app
        if app.busy or not self.current() or not self.selected:return
        token=self.revision;snapshot=deepcopy(self.snapshot);indices=self.selected
        # Refresh is allowed to reconcile normalization, but cannot substitute a
        # new document or silently reuse old indices after an edit.
        if not app.refresh() or not self.current() or self.revision!=token or not equivalent(snapshot,app.project_snapshot()):return
        design=deepcopy(app.design);config=deepcopy(app.config());png=None
        if kind=='package':
            canvas=app.canvas
            saved=dict(options={k:w.get_active() for k,w in app.view_options.items()},isolated=canvas.isolated_indices,
                enabled=canvas.motion_enabled,phase=canvas.motion_phase,plan=canvas.inspection_motion_plan or canvas.motion_plan,inspection=canvas.inspection_phase,inspection_indices=canvas.inspection_indices,playing=canvas.motion_playing,points=deepcopy(self.points),pose=self.pose,measurement=self.measure_text.get_text() if self.window else '')
            try:
                canvas.reset_motion()
                for key in ('support','housing'):app.view_options[key].set_active(True)
                for key in ('exploded','section'):app.view_options[key].set_active(False)
                canvas.isolated_indices=indices
                captured=[];canvas.capture_png(lambda data,error:captured.append((data,error)))
                if not captured or captured[0][1]:raise RuntimeError('Selected preview capture failed')
                png=captured[0][0]
            except Exception as error:app.status_text(str(error));return
            finally:
                for key,value in saved['options'].items():app.view_options[key].set_active(value)
                canvas.isolated_indices=saved['isolated'];canvas.motion_phase=saved['phase'];canvas.motion_enabled=saved['enabled'];canvas.motion_plan=saved['plan']
                if saved['inspection'] is not None:canvas.show_inspection(saved['inspection'],saved['inspection_indices'])
                if saved['playing']:canvas.set_motion_playing(True)
                self.points=saved['points'];self.pose=saved['pose']
                if self.window:self.measure_text.set_text(saved['measurement'])
                self.markers.queue_draw();canvas.queue_render()
        if not self.current() or self.revision!=token:return
        target=app.output_dir/f'{design.family}-{datetime.now():%Y%m%d-%H%M%S-%f}.selected-{kind}'
        def work():
            selected_export.export(design,indices,kind,target,config,png,token)
            return f'Selected components only · {len(indices)} source positions · nominal mm · {target}'
        app.background(work)
