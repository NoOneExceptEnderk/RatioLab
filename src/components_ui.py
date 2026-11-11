# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Geometry-bound selection and revision-bound measurement; view-only operations."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from math import pi
import re
from threading import Event
import gi
gi.require_version('Gtk','4.0')
from gi.repository import GLib, Gtk
from project_document import equivalent
from motion import SPEED_KEYS, same_geometry
from workspace_tools import actions, details
import component_geometry as geometry
import selected_export
from export_feedback import ExportResult


def component_title(part):
    """Readable presentation only; source names and indices remain authoritative."""
    name=part.name;stage=re.match(r'^S(\d+)_(.*)$',name)
    if stage:name=stage.group(2)
    qualifier=re.search(r'_(envelope|generated|prescribed)$',name)
    if qualifier:name=name[:qualifier.start()]
    compound=re.fullmatch(r'Compound_(\d+)_(rim(\d+)|hub)',name)
    if compound:
        title=f'Compound planet {compound.group(1)} · '+(f'rim {compound.group(3)}' if compound.group(3) else 'hub')
    else:
        def words(value):
            tokens=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',value.replace('_',' ')).split()
            return ' '.join(token if token.isupper() else token.lower() for token in tokens)
        prefixes={'Generator_wave':'wave generator','Disc_cycloidal':'cycloidal disc',
            'Bearing_eccentric':'eccentric bearing','Bearing_planetcarrier':'planet carrier bearing',
            'Shaft_input':'input shaft','Shaft_output':'output shaft','Flange_output':'output flange',
            'Pin_output':'output pin','Ring_output':'output ring','Ring_fixed':'fixed ring',
            'Sun_input':'input sun','Pinion_input':'input pinion'}
        title=words(name)
        for prefix,replacement in prefixes.items():
            if name==prefix or name.startswith(prefix+'_'):
                title=replacement+(' '+words(name[len(prefix)+1:]) if name!=prefix else '');break
        if title.endswith((' lower',' upper')):
            body,position=title.rsplit(' ',1);title=position+' '+body
        title=title[:1].upper()+title[1:]
    if qualifier:title+=' · '+qualifier.group(1)
    layer=part.port.get('layer')
    if type(layer) is int:title+=f' · layer {layer}'
    return (f'Stage {stage.group(1)} · ' if stage else '')+title


def selection_snapshot(snapshot):
    """Bind selection to geometry; operating edits still invalidate measurements."""
    snapshot=deepcopy(snapshot)
    snapshot.pop('quality',None)
    snapshot.pop('component_sheets',None)
    for section in ('values','raw'):
        fields=snapshot.get(section,{}).get(snapshot.get('family'),{})
        for key in SPEED_KEYS:fields.pop(key,None)
    return snapshot


def label(text=''):
    return Gtk.Label(label=text,xalign=0,wrap=True,selectable=False)


class Controller:
    def __init__(self,app,container):
        self.app=app;self.window=None;self.snapshot=None;self.revision=None;self.selected=();self.saved_filters=None;self.points=[];self.cache={};self.syncing=False;self.pose=None;self.alive=True
        self.design=None;self.scene=None
        self.nominal_details={};self.list_state=None
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
        return self.alive and getattr(app,'project_alive',False) and self.revision is not None and hasattr(app,'document') and self.revision==app.document.token and self.snapshot is not None and equivalent(app.project_snapshot(),self.snapshot) and self.valid_indices(self.selected,app.design)

    def changed(self,snapshot):
        if self.snapshot is not None and not equivalent(snapshot,self.snapshot):
            if self.same_selection_snapshot(snapshot):
                self.clear_points();self.cache={}
            else:self.invalidate('Model changed · selection cleared')

    def same_selection_snapshot(self,snapshot):
        return (self.revision is not None and self.revision[0]==self.app.document.token[0]
                and self.snapshot is not None
                and equivalent(selection_snapshot(self.snapshot),selection_snapshot(snapshot)))

    def valid_indices(self,indices,design):
        return design is not None and all(type(i) is int and 0<=i<len(design.parts) for i in indices)

    def same_components(self,design):
        # Rate updates copy Parts to update their operating ports. The sampled
        # geometry and scene remain shared, retaining the same source indices.
        previous=self.design
        return bool(previous and design and same_geometry(previous,design.family,design.values)
                    and self.scene is not None and (self.scene is self.app.canvas.scene or getattr(previous,'quality',{})!=getattr(design,'quality',{}))
                    and len(previous.parts)==len(design.parts)
                    and all(a.name==b.name and a.role==b.role
                            and all(getattr(a,key) is getattr(b,key) for key in ('outer','holes','mesh','stations','frame'))
                            for a,b in zip(previous.parts,design.parts)))

    def refreshed(self,design):
        app=self.app
        if not hasattr(app,'document'):return
        if not self.same_components(design):self.nominal_details.clear()
        snapshot=app.project_snapshot()
        changed=self.revision!=app.document.token or (self.snapshot is not None and not equivalent(self.snapshot,snapshot))
        if not (self.same_selection_snapshot(snapshot) and self.same_components(design)
                and self.valid_indices(self.selected,design)):
            self.invalidate('Select components from this revision')
        elif changed:self.clear_points()
        self.revision=app.document.token;self.snapshot=deepcopy(snapshot)
        self.design=design;self.scene=app.canvas.scene
        self.cache={}
        self.populate();self.update()

    def invalidate(self,message='Document replaced · selection cleared'):
        self.nominal_details.clear()
        self.restore();self.selected=();self.points=[];self.cache={};self.revision=None;self.snapshot=None
        self.design=None;self.scene=None
        self.app.canvas.selected_indices=();self.app.canvas.queue_render();self.markers.queue_draw()
        self.summary.set_text(message)
        if self.window:self.populate();self.update()

    def close(self):
        self.invalidate();self.alive=False
        if self.window:self.window.destroy();self.window=None

    def open(self):
        if self.window:self.window.present();return
        self.list_state=None
        if hasattr(self.app,'document') and self.app.design and self.revision is None:self.refreshed(self.app.design)
        win=self.app.tools.panel('components')
        self.window=win;body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9,margin_start=14,margin_end=14,margin_top=14,margin_bottom=14);win.set_child(body)
        # The controller retains this label after its previous panel is removed.
        # Move it from that retired body before adding it to the new inspector.
        parent=self.summary.get_parent()
        if parent:parent.remove(self.summary)
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
        self.teeth_button=Gtk.Button(label='View teeth',tooltip_text='Select one supported gear to view its teeth.')
        self.teeth_button.connect('clicked',lambda _:self.view_teeth());buttons.append(self.teeth_button)
        self.metrology_button=Gtk.Button(label='Gear metrology…')
        self.metrology_button.connect('clicked',lambda _:self.app.gear_measurement.open())
        buttons.append(self.metrology_button)
        clear=Gtk.Button(label='Clear');clear.connect('clicked',lambda _:self.select(()));buttons.append(clear)
        self.detail=label();self.detail.set_selectable(True);detail_scroll=Gtk.ScrolledWindow(min_content_height=45,max_content_height=115,propagate_natural_height=True);detail_scroll.set_child(self.detail);details(body,'Component details · nominal bounds in mm',detail_scroll)
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
            b=Gtk.Button(label=title);b.connect('clicked',lambda _,k=kind:self.app.open_export(k, selected=True));exports.append(b);self.export_buttons.append(b)
        self.sheets_button=Gtk.Button(label='PDF sheets…',tooltip_text='Production / inspection sheets…')
        self.sheets_button.connect('clicked',lambda _:self.open_sheets())
        exports.append(self.sheets_button)
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
        visible=self.visible_indices()
        rows=tuple((p.name,p.role,component_title(p)) for p in self.app.design.parts) if self.app.design and self.revision is not None else ()
        state=(id(self.app.canvas.scene),visible,rows)
        if state==self.list_state:
            # Rate-only revisions retain component identity and the same
            # visible rows. Synchronize selection without replacing widgets.
            selected=tuple(row.source_index for row in self.list.get_selected_rows())
            if selected!=self.selected:
                self.syncing=True
                try:
                    self.list.unselect_all()
                    for index in self.selected:self.list.select_row(self.list.get_row_at_index(index))
                finally:self.syncing=False
            return
        self.list_state=state
        self.syncing=True
        while (child:=self.list.get_first_child()):self.list.remove(child)
        if self.app.design and self.revision is not None:
            for i,p in enumerate(self.app.design.parts):
                row=Gtk.ListBoxRow();row.source_index=i
                row.set_child(label(f'{i+1:03d} · {component_title(p)}'+(' · hidden' if i not in visible else '')))
                row.set_tooltip_text(f'Source name: {p.name}\nRole: {p.role}')
                self.list.append(row)
                if i in self.selected:self.list.select_row(row)
        self.syncing=False

    def rows_changed(self,*_):
        if not self.syncing:self.select(tuple(row.source_index for row in self.list.get_selected_rows()),False)

    def select(self,indices,sync=True):
        if not self.current():return
        indices=tuple(indices)
        if not self.valid_indices(indices,self.app.design):
            self.invalidate('Component unavailable · selection cleared');return
        self.selected=tuple(sorted(set(indices)));self.app.canvas.selected_indices=self.selected
        if self.saved_filters is not None:self.app.canvas.isolated_indices=self.selected
        self.app.canvas.queue_render()
        if sync:self.populate()
        self.update()

    def update(self):
        if hasattr(self.app,'update_export_scope'):self.app.update_export_scope()
        current=self.current();n=len(self.selected)
        if self.revision is not None:
            names=', '.join(f'{i+1:03d} {component_title(self.app.design.parts[i])}' for i in self.selected[:2]) if current else ''
            if n>2:names+=f', +{n-2} more'
            self.summary.set_text(f'{n} selected'+(' · '+names if names else '')+(' · isolated' if self.saved_filters is not None else '')+' · Ctrl/Shift adds')
        if not self.window:return
        self.isolate_button.set_sensitive(current and n>0);self.restore_button.set_sensitive(self.saved_filters is not None)
        for button in self.export_buttons:button.set_sensitive(current and n>0 and not self.app.busy)
        self.sheets_button.set_sensitive(current and n==1 and not self.app.busy)
        from tooth_tip_preview import supported
        self.teeth_button.set_sensitive(current and n==1 and not self.app.busy
            and supported(self.app.design.parts[self.selected[0]]))
        from tool_capabilities import gauge_components
        self.metrology_button.set_sensitive(current and n==1 and self.selected[0] in gauge_components(self.app.design) and not self.app.busy)
        self.sheets_button.set_tooltip_text('Production / inspection sheets…' if current and n==1 else 'Sheets require exactly one selected component.')
        descriptions=[]
        if current:
            import bom
            for i in self.selected:
                # Bounds/BOM identity describe nominal geometry, not RPM or
                # display pose. Keep at most one entry per current component;
                # refreshed()/invalidate() clear it when that geometry changes.
                if i not in self.nominal_details:
                    p=self.app.design.parts[i];dims=geometry.dimensions(p)
                    self.nominal_details[i]=f'{i+1:03d} {component_title(p)}\nSource name: {p.name} · role: {p.role} · BOM code: {bom.part_info(p)["code"]}\nNominal sampled XYZ bounds: '+ ' × '.join(f'{q:.6g}' for q in dims['size_mm'])+' mm'+f' · min {self.xyz(dims["min_mm"])} · max {self.xyz(dims["max_mm"])}'
                descriptions.append(self.nominal_details[i])
        self.export_text.set_text(f'Export {n} selected components · nominal pose · includes hidden selections')
        self.detail.set_text('\n'.join(descriptions) or 'No current selection')
        if not self.points:self.measure_text.set_text('No measurement · click two visible surface points in Measure mode')

    @staticmethod
    def xyz(q):return '('+', '.join(f'{v:.6f}' for v in q)+') mm'

    def open_sheets(self):
        if not self.current() or len(self.selected)!=1 or self.app.busy:return None
        from component_sheets_ui import open_editor
        return open_editor(self.app,self.selected[0])

    def visible_indices(self):
        c=self.app.canvas
        return tuple(p.source_index for p in c.scene.parts if c.isolated_indices is None or p.source_index in c.isolated_indices) if c.scene else ()

    def isolate(self):
        if not self.current() or not self.selected:return
        app=self.app
        app.interference.restore_view()
        if self.saved_filters is None:self.saved_filters=app.view_state()
        app.canvas.isolated_indices=self.selected
        for key in ('support','housing'):app.view_options[key].set_active(True)
        self.populate();self.update();app.canvas.queue_render()

    def restore(self):
        saved=self.saved_filters;self.saved_filters=None;self.app.canvas.isolated_indices=None
        if saved:self.app.restore_view_state(saved)
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
        # View filters may legitimately rebuild the scene without replacing the
        # bound design. A set_design handoff must be checked by refreshed().
        if self.design is not None and self.app.canvas.design is self.design:self.scene=self.app.canvas.scene
        # Only retain triangles for the current continuous placement, rather
        # than accumulating a full mesh for each slider stop.
        if self.cache and next(iter(self.cache))[1]!=self.app.canvas.exploded:self.cache={}
        visible=self.visible_indices()
        if self.points and (self.pose_key()!=self.pose or any(index not in visible for index,_ in self.points)):self.clear_points()
        # Explosion and phase do not change the nominal bounds or list labels.
        # Rebuilding those surfaces for every slider event defeats the cached
        # GPU scene, especially with several large components selected.
        state=(visible,self.selected,self.saved_filters is not None,self.revision)
        if state!=getattr(self,'display_list_state',None):
            self.display_list_state=state;self.populate();self.update()
        self.markers.queue_draw()

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
            origin,direction=geometry.ray(x,y,canvas.camera_center,s.radius,canvas.zoom,canvas.yaw,canvas.tilt,canvas.get_width(),canvas.get_height())
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
            if len(self.points)==2:
                a,b=self.points[0][1],self.points[1][1]
                lines.append(f'A–B straight distance: {geometry.distance(a,b):.6f} mm')
                lines.append('B − A · ΔXYZ: '+self.xyz(tuple(y-x for x,y in zip(a,b))))
            lines.append(('Displayed exploded pose' if canvas.exploded else 'Displayed motion / inspection pose' if plan else 'Nominal assembly pose')+f' · phase {phase*180/pi:.6g}° · sampled surfaces')
            self.measure_text.set_text('\n'.join(lines));self.markers.queue_draw()
        else:
            indices=set(self.selected) if multiple else set()
            if multiple and index in indices:indices.remove(index)
            else:indices.add(index)
            self.select(indices)

    def draw(self,area,cr,width,height):
        c=self.app.canvas
        if not self.points or not c.scene or c.tooth_detail is not None:return
        coords=[geometry.project(q,c.camera_center,c.scene.radius,c.zoom,c.yaw,c.tilt,width,height) for _,q in self.points]
        def stroke():
            cr.set_source_rgb(.035,.045,.06);cr.set_line_width(6);cr.stroke_preserve()
            cr.set_source_rgb(1,.92,.22);cr.set_line_width(2);cr.stroke()
        if len(coords)==2:cr.move_to(*coords[0]);cr.line_to(*coords[1]);stroke()
        for j,(x,y) in enumerate(coords):
            cr.arc(x,y,5,0,2*pi);stroke()
            cr.move_to(x+9,y-9);cr.set_font_size(16);cr.text_path('AB'[j])
            cr.set_source_rgb(.035,.045,.06);cr.set_line_width(4);cr.stroke_preserve()
            cr.set_source_rgb(1,.96,.5);cr.fill()

    def capture_export_preview(self, indices=None):
        """Capture exactly the export scope without changing the user's view state."""
        from preview3d import build_scene
        canvas=self.app.canvas
        # Do not emit view/motion signals: temporary export state must not clear
        # measurements, selection, tooth detail or the current camera session.
        keys=('scene','isolated_indices','motion_enabled','motion_phase','inspection_phase',
              'inspection_indices','exploded','section','tooth_detail','selected_indices')
        saved={key:getattr(canvas,key) for key in keys}
        try:
            canvas.scene=build_scene(self.app.design,True,True,frame_explosion=True)
            canvas.isolated_indices=indices
            canvas.motion_enabled=False;canvas.motion_phase=0.;canvas.inspection_phase=None
            canvas.inspection_indices=();canvas.selected_indices=();canvas.exploded=0.;canvas.section=False
            canvas.tooth_detail=None;canvas.dirty=True
            captured=[]
            canvas.capture_png(lambda data,error:captured.append((data,error)))
            if not captured:
                canvas.capture_callback=None
                raise RuntimeError('Preview is not ready. Try exporting again.')
            if captured[0][1]:raise RuntimeError(str(captured[0][1]))
            return captured[0][0]
        finally:
            for key,value in saved.items():setattr(canvas,key,value)
            canvas.dirty=True;canvas.queue_render()

    def export_with_preview(self, work, indices=None):
        """Capture on GTK's thread once the viewport has an allocation."""
        app = self.app
        canvas = app.canvas
        if canvas.get_width() > 0 and canvas.get_height() > 0:
            png = self.capture_export_preview(indices)
            app.background(lambda: work(png), export_job=True)
            return

        token = app.document.token
        design = app.design
        captured = Event()
        png = error = None

        def capture_when_allocated():
            nonlocal png, error
            if captured.is_set():
                return GLib.SOURCE_REMOVE
            try:
                if not self.alive or not app.project_alive or app.document.token != token or app.design is not design:
                    raise RuntimeError('The model changed before the preview could be captured.')
                if canvas.failure:
                    raise RuntimeError('3D preview unavailable')
                if canvas.get_width() <= 0 or canvas.get_height() <= 0:
                    return GLib.SOURCE_CONTINUE
                png = self.capture_export_preview(indices)
            except Exception as failure:
                error = failure
            captured.set()
            return GLib.SOURCE_REMOVE

        def wait_for_preview():
            if not captured.wait(30):
                captured.set()
                raise RuntimeError('Preview capture timed out. Try exporting again.')
            if error is not None:
                raise error
            return work(png)

        canvas.queue_render()
        GLib.timeout_add(16, capture_when_allocated)
        app.background(wait_for_preview, export_job=True)

    def export(self,kind):
        app=self.app
        if app.busy or not self.current() or not self.selected:return
        token=self.revision;snapshot=deepcopy(self.snapshot);indices=self.selected
        # Refresh is allowed to reconcile normalization, but cannot substitute a
        # new document or silently reuse old indices after an edit.
        if not app.refresh() or not self.current() or self.revision!=token or not equivalent(snapshot,app.project_snapshot()):
            app.export_feedback.failed('The selected components changed. Select current components before exporting.');return
        if not self.current() or self.revision!=token:return
        design=deepcopy(app.design);config=deepcopy(app.config())
        target=Path(app.output_dir).absolute()/f'{design.family}-{datetime.now():%Y%m%d-%H%M%S-%f}.selected-{kind}'
        def work(png=None):
            folder=selected_export.export(design,indices,kind,target,config,png,token)
            return ExportResult('Selected '+{'step':'STEP','stl':'STL','profiles':'SVG / DXF profiles','package':'package'}[kind],
                                (folder,),f'Selected components only · {len(indices)} source positions · nominal mm · {folder}')
        if kind=='package':
            try:self.export_with_preview(work,indices)
            except Exception as error:
                app.status_text(str(error));app.export_feedback.failed(str(error))
        else:app.background(work,export_job=True)
    def view_teeth(self):
        if not self.current() or len(self.selected)!=1 or self.app.busy:return
        self.app.tooth_tips.focus_component(self.selected[0])
