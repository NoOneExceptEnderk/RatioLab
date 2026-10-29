#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK 4 desktop companion with a local 3D preview and automatic geometry refresh."""
import json
from pathlib import Path
from datetime import datetime
import threading
import traceback
import sys
import app_paths
app_paths.prepare_native_runtime()
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib, Gdk, Gio
app_paths.require_gtk_version(Gtk)
from geometry import FAMILIES,SPECS,VARIANTS,INTEGER,get_specs,defaults,generate,is_double,DOUBLE_STYLES,HARMONIC_OUTPUTS
from connection import Client,connect_or_launch
import fusion_connection
from preview3d import Preview3D
from catalog import BEARINGS,MODES,FITS,SUPPORTED
import bom
import stl_export
import cad_export
import profile_export
import package_export
import io_controls
import motion_controls
import gui_workflow
import result_controls
import workspace_ui
from project_ui import ProjectActions
from kinematics import options as io_options,default as io_default,TRIPLES as IO_TRIPLES
import hardware_catalog as hw

BASE=app_paths.SOURCE_ROOT
GLib.set_application_name('RatioLab')
GENERATED=app_paths.default_output_dir()
LABELS=[gui_workflow.CATALOG.get(key,(label,''))[0] for key,label in FAMILIES.items()]

class ReducerApp(ProjectActions, Gtk.Application):
    def __init__(self):
        super().__init__(application_id=app_paths.APP_ID)
        self.values={};self.design=None;self.family='parallel';self.busy=False;self.pending=0;self.building=False;self.variant_model_family=None;self.last_valid_family=None;self.connected=False;self.fusion_connected=False
    def do_activate(self):
        if hasattr(self,'win'):self.win.present();return
        self.BASE=BASE;self.output_dir=GENERATED;self.file_buttons=[];self.reset_values=None
        self.output_dir=app_paths.saved_output_dir(legacy_root=BASE)
        self.families = FAMILIES
        workspace_ui.build(self, LABELS)
        self.make_fields()
        self.update_playback_bar()
        self.init_projects()
        if self.design:self.components.refreshed(self.design)
        self.win.present()
        GLib.timeout_add(500, self.check_graphics)
    def select_view(self,name):
        self.canvas.view(name)
    def on_view_changed(self,canvas,name):
        for key,button in self.view_buttons.items():button.set_active(key==name)
    def connect_cad(self):
        try:result=connect_or_launch(self.output_dir)
        except Exception:
            GLib.idle_add(self.set_connection,False);raise
        GLib.idle_add(self.set_connection,True)
        return result
    def set_connection(self,connected):
        self.connected=connected
        self.cad_hint.set_text('Adds a new group to the open CAD document.' if connected else 'Launches or connects to SolidCraft and adds a new group.')
        self.connection_label.set_text('● Connected' if connected else '● Disconnected')
        if connected:self.connection_label.add_css_class('connected')
        else:self.connection_label.remove_css_class('connected')
        return False
    def set_fusion_connection(self,status=None):
        self.fusion_connected=status is not None
        label=self.fusion_connection_label
        if status is None:
            label.set_text('○ Disconnected')
            label.remove_css_class('connected')
            self.fusion_hint.set_text(fusion_connection.START_HELP+' Transfers STEP solids with RatioLab parameter metadata; Fusion timeline features are not regenerated.')
        else:
            document=status.get('document')
            label.set_text('● Connected · '+(document['name'] if document else 'no design document'))
            label.add_css_class('connected')
            self.fusion_hint.set_text('Adds a new group of STEP solids to the active Fusion design. RatioLab parameters are stored as metadata. '+('' if document else 'Open a design document first.'))
        return False
    def install_fusion_addin(self):
        try:
            path=fusion_connection.install_addin()
        finally:
            GLib.idle_add(self.set_fusion_connection,None,priority=GLib.PRIORITY_DEFAULT)
        return f'Fusion add-in installed in {path}. Stop and restart RatioLabBridge if it was already running. '+fusion_connection.START_HELP
    def connect_fusion(self):
        try:
            with fusion_connection.Client() as client:status=client.status()
        except Exception:
            GLib.idle_add(self.set_fusion_connection,None,priority=GLib.PRIORITY_DEFAULT)
            raise
        GLib.idle_add(self.set_fusion_connection,status,priority=GLib.PRIORITY_DEFAULT)
        return 'Fusion connected. '+('Active design: '+status['document']['name'] if status['document'] else 'Open a design document before creating the model.')
    def update_metrics(self,design):
        result_controls.update(self,design)
    def check_graphics(self):
        error=self.canvas.failure or self.canvas.get_error()
        if error:self.status_text(f'3D preview unavailable: {error}')
        return False
    def status_text(self,text):
        self.status.set_text(text)
        self.status.set_tooltip_text(text)
    def read_values(self):
        self.error_field=None
        result=dict(self.values.get(self.family,{}))
        result.update(getattr(self,"option_values",{}))
        for key,spin in self.inputs.items():
            try:result[key]=float(spin.get_text().strip().replace(',','.'))
            except ValueError:
                self.error_field=key;spin.add_css_class('field-error');raise ValueError('Complete the numeric value: '+self.input_labels[key])
            else:spin.remove_css_class('field-error')
        if hasattr(self,'motion_rpm'):
            from math import isfinite
            try:
                rpm=float(self.motion_speed_text.get_text().strip().replace(',','.'))
                low,high=self.motion_rate_limits
                if not isfinite(rpm) or not low<=rpm<=high:raise ValueError()
            except ValueError:
                self.error_field='input_rpm';raise ValueError('Complete a valid input speed.')
            result['input_rpm']=rpm
            self.motion_input_invalid=False
            self.motion_rpm=rpm
        if self.family in VARIANTS:result['variant']=list(VARIANTS[self.family])[self.variant_selector.get_selected()]
        return result
    def change_variant(self,*args):
        if self.building:return
        self.remember();self.make_fields()
    def change_view_options(self,*args):
        if not hasattr(self,'view_options'):return
        self.canvas.set_options(*(self.view_options[k].get_active() for k in ['support','housing','exploded','section']))
        self.hidden_hint.set_visible(bool(self.canvas.scene and not self.canvas.scene.parts))
    def remember(self):
        if hasattr(self,'inputs'):self.collect_fields()
    def rebuild_options(self, changes):
        self.remember()
        self.values[self.family].update(changes)
        for key in changes:self.raw_edits.get(self.family,{}).pop(key,None)
        self.make_fields()
    def change_family(self,*args):
        if self.building:return
        self.remember();self.family=list(FAMILIES)[self.selector.get_selected()];self.make_fields()
    def make_fields(self):
        self.building=True
        self.hardware_warning_labels={}
        advanced_open=getattr(self,'advanced_expander',None) and self.advanced_expander.get_expanded()
        gui_workflow.preserve_scroll(self)
        if self.pending:GLib.source_remove(self.pending);self.pending=0
        for key in ('geometry','bearings','hardware','loads','housing'):
            body=self.sections[key][1];child=body.get_first_child()
            while child:
                nxt=child.get_next_sibling();body.remove(child);child=nxt
        self.advanced_expander=Gtk.Expander(label='Advanced · profile & clearances')
        self.advanced_expander.set_expanded(bool(advanced_open));self.advanced_fields=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);self.advanced_expander.set_child(self.advanced_fields)
        field_target=self.sections['geometry'][1]
        values=self.values.get(self.family,defaults(self.family));variants=VARIANTS.get(self.family,{})
        self.variant_box.set_visible(bool(variants))
        if self.variant_model_family!=self.family:
            self.variant_model_family=self.family
            self.variant_selector.set_model(Gtk.StringList.new(list(variants.values()) or ['Standard']))
        variant=values.get('variant',next(iter(variants),None))
        selected=list(variants).index(variant) if variant in variants else 0
        if self.variant_selector.get_selected()!=selected:self.variant_selector.set_selected(selected)
        self.inputs={};self.input_labels={};self.input_pages={};self.field_values=values;self.option_values={k:values[k] for k in ('bearing_mode','bearing','fit','hardware_mode','hardware_screw','hardware_shim','hardware_retaining','hardware_keys','hardware_bolts','hardware_shims','double_style','harmonic_output','io_scheme','io_scheme2','eccentric_design') if k in values}
        def choice(key,label,choices,default,target=None):
            target=target or field_target
            target.append(Gtk.Label(label=label,xalign=0,css_classes=['field-label']))
            dropdown=Gtk.DropDown.new_from_strings(list(choices.values()))
            keys=list(choices);dropdown.set_selected(keys.index(values.get(key,default)))
            self.option_values[key]=values.get(key,default)
            def change(widget,*args):
                if self.building:return
                current=self.collect_fields()
                current[key]=keys[widget.get_selected()]
                if key=='hardware_mode' and self.family in ('parallel','internal'):current['hardware_bolts']=False
                if key=='eccentric_design':
                    if current[key]=='fdm_bolted':
                        from printed_shaft import SUPPORTED_SCHEMES
                        current.update(bearing_mode='manual',hardware_mode='none')
                        if current.get('io_scheme') not in SUPPORTED_SCHEMES:current['io_scheme']=SUPPORTED_SCHEMES[0]
                changes={k:v for k,v in current.items() if k not in self.inputs and k!='input_rpm'}
                self.rebuild_options(changes)
            dropdown.connect('notify::selected',change);target.append(dropdown)
            return dropdown
        double=is_double(self.family,variant)
        while (child:=self.eccentric_design_box.get_first_child()):self.eccentric_design_box.remove(child)
        self.eccentric_design_box.set_visible(self.family=='cycloidal')
        if self.family=='cycloidal':
            from printed_shaft import DESIGNS
            self.eccentric_design_selector=choice('eccentric_design','Eccentric shaft construction',DESIGNS,'standard',self.eccentric_design_box)
        printed=self.family=='cycloidal' and self.option_values.get('eccentric_design')=='fdm_bolted'
        if printed:
            self.eccentric_design_box.append(gui_workflow.text('6804 seat: Ø32 mm + allowance; disc ≥14.7 mm. Apply the preset only to replace shaft/disc dimensions.'))
            preset=Gtk.Button(label='Apply compatible FDM dimensions')
            preset.set_tooltip_text('Sets input shaft Ø17 mm, bearing seat Ø32.2 mm, disc thickness 16 mm and the default two-bolt clearances. Other main dimensions are preserved.')
            def apply_printed_preset(*args):
                from printed_shaft import PRESET
                self.rebuild_options(PRESET)
            preset.connect('clicked',apply_printed_preset);self.eccentric_design_box.append(preset)
            self.printed_preset_button=preset
        if double and self.family!='double':choice('double_style','Double helix construction',DOUBLE_STYLES,'joined' if values.get('gap',1)==0 else 'separated')
        io_controls.build(self,values,variant,choice)
        self.sections['bearings'][0].set_visible(True)
        field_target=self.sections['bearings'][1]
        if self.family in SUPPORTED and not printed:
            modes=dict(MODES)
            if self.family in ('parallel','internal'):modes.pop('gear')
            choice('bearing_mode','Standard fit',modes,'manual')
            if self.family in ('parallel','internal'):
                from pair_assembly import GEAR_REASON
                disabled=Gtk.Button(label='Bearing in bore · unavailable');disabled.set_sensitive(False);field_target.append(disabled)
                field_target.append(Gtk.Label(label=GEAR_REASON+(' Catalog support covers the pinion shaft only; ring output is not supported.' if self.family=='internal' else ''),xalign=0,wrap=True))
            if self.option_values.get('bearing_mode')!='manual':
                choice('bearing','NSK bearing · d × D × B',{k:b.label for k,b in BEARINGS.items()},'608' if self.family=='cycloidal' else '626')
                choice('fit','Seat dimensions',FITS,'nominal')
                b=BEARINGS[self.option_values['bearing']]
                link=Gtk.LinkButton.new_with_label(b.url,'Official NSK datasheet ↗')
                link.connect('activate-link',lambda button:gui_workflow.open_link(self,button.get_uri()))
                field_target.append(link)
                field_target.append(Gtk.Label(label='Linked dimensions are shown after calculation. Assembly options add available retainers.',xalign=0,wrap=True,css_classes=['muted']))
        else:
            from pair_assembly import STUDY_REASON,PRINT_REASON
            disabled=Gtk.Button(label='Automatic bearing catalog · unavailable');disabled.set_sensitive(False);field_target.append(disabled)
            field_target.append(Gtk.Label(label=PRINT_REASON if printed else STUDY_REASON,xalign=0,wrap=True))
        self.sections['hardware'][0].set_visible(True)
        field_target=self.sections['hardware'][1]
        if self.family in hw.SUPPORTED and not printed:
            choice('hardware_mode','Hardware and assembly',hw.MODES,'none')
            if self.option_values['hardware_mode']=='standard':
                for key,label in [('retaining','Retaining rings and grooves'),('keys','Compatible keys and keyways'),('bolts','Flange screws, nuts and holes'),('shims','Shims and spacers')]:
                    name='hardware_'+key;check=Gtk.CheckButton(label=label);default=False if self.family in ('parallel','internal') and key=='bolts' else True;check.set_active(values.get(name,default));self.option_values[name]=values.get(name,default)
                    if self.family in ('parallel','internal') and key=='bolts':
                        from pair_assembly import BOLT_REASON
                        check.set_sensitive(False);check.set_tooltip_text(BOLT_REASON)
                    def toggled(widget,key=name):
                        if self.building:return
                        self.rebuild_options({key:widget.get_active()})
                    check.connect('toggled',toggled);field_target.append(check)
                    if self.family in ('parallel','internal'):
                        from pair_assembly import hardware_warnings
                        warning=hardware_warnings(self.family,values).get(key)
                        note=Gtk.Label(label=warning or '',xalign=0,wrap=True,css_classes=['muted']);note.set_visible(bool(warning));field_target.append(note);self.hardware_warning_labels[key]=note
                fastener=choice('hardware_screw','Flange fasteners',{k:k for k in hw.FASTENERS},'M3')
                if self.family in ('parallel','internal'):
                    from pair_assembly import BOLT_REASON
                    fastener.set_sensitive(False);field_target.append(Gtk.Label(label=BOLT_REASON,xalign=0,wrap=True))
                choice('hardware_shim','DIN 988 shim thickness',hw.SHIM_THICKNESSES,'.5')
                field_target.append(Gtk.Label(label='Automatic dimensions and quantities; remaining connections are listed in the BOM.',xalign=0,wrap=True,css_classes=['muted']))
        else:
            from pair_assembly import STUDY_REASON,PRINT_REASON
            disabled=Gtk.Button(label='Automatic hardware · unavailable');disabled.set_sensitive(False);field_target.append(disabled)
            field_target.append(Gtk.Label(label=PRINT_REASON if printed else STUDY_REASON,xalign=0,wrap=True))
        specs=get_specs(self.family,variant,self.option_values.get('double_style'))
        if self.option_values.get('bearing_mode','manual')!='manual':
            specs+=[('shoulder','Minimum axial margin [mm]',1,.5,5,.5)]
            if self.option_values.get('fit')=='custom':specs+=[('seat_allowance','Seat diameter allowance [mm]',0,-.08,.8,.01),('shaft_allowance','Shaft diameter allowance [mm]',0,-.8,.08,.01)]
        motion_controls.configure(self,values,specs)
        gui_workflow.geometry_groups(self, specs)
        gui_workflow.update_family(self)
        self.restore_raw_fields()
        self.building=False
        if self.family!=self.last_valid_family:self.canvas.view('iso')
        generated=self.refresh()
        self.project_changed()
        # Option rebuilds record after normalization; bind to the resulting
        # revision only when this very rebuild generated valid geometry.
        if generated and hasattr(self,'components'):self.components.refreshed(self.design)
    def changed(self,*args):
        if self.building:
            return
        if args and ',' in args[0].get_text():
            widget = args[0]
            position = widget.get_position()
            widget.set_text(widget.get_text().replace(',', '.'))
            widget.set_position(position)
            return
        key=next((key for key,w in self.inputs.items() if args and w is args[0]),'input_rpm')
        self.project_changed((self.family,key))
        self.send_btn.set_sensitive(False)
        self.fusion_send_btn.set_sensitive(False)
        self.export_menu.set_sensitive(False)
        self.empty.set_text('Geometry out of date · updating…')
        self.empty.remove_css_class('invalid')
        self.empty.set_visible(True)
        self.metric_cards.set_sensitive(False)
        if args:
            self.canvas.invalidate_motion()
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(80, self.auto_refresh)

    def auto_refresh(self):
        self.pending = 0
        self.refresh()
        return False

    def refresh(self):
        if self.pending:
            GLib.source_remove(self.pending)
            self.pending = 0
        reconcile_token=self.project_reconcile_token()
        try:
            values = self.read_values()
            design = generate(self.family, values)
            self.canvas.set_design(design)
            self.design = design
            if getattr(self,'hardware_warning_labels',None):
                from pair_assembly import hardware_warnings
                warnings=hardware_warnings(self.family,design.values)
                for key,note in self.hardware_warning_labels.items():note.set_text(warnings.get(key,''));note.set_visible(key in warnings)
            self.values[self.family] = values
            linked = set()
            mode = values.get('bearing_mode', 'manual')
            if mode != 'manual':
                if self.family in ('spur', 'helical', 'double'):
                    linked = {'bore'}
                elif self.family in ('parallel','internal'):
                    linked = {'bore','output_bore'} if self.family=='parallel' else {'bore'}
                elif self.family == 'planetary' and mode == 'shaft':
                    linked = {'bore'}
                elif self.family == 'cycloidal':
                    linked = {'bore'} if mode == 'gear' else {'input_shaft', 'output_shaft'}
            printed = (self.family == 'cycloidal'
                       and design.values.get('eccentric_design') == 'fdm_bolted')
            if printed:
                linked.add('bore')
            self.building = True
            for key, spin in self.inputs.items():
                if key in design.values and (mode != 'manual' or printed and key == 'bore'):
                    spin.set_value(design.values[key])
                    spin.set_text(gui_workflow.roundtrip_text(design.values[key],spin.get_digits()))
                spin.set_sensitive(key not in linked)
                if key in linked:
                    spin.add_css_class('derived')
                    source = 'printed shaft bearing seat' if printed and key=='bore' else 'NSK '+str(design.values.get('bearing', ''))+' and selected fit'
                    spin.set_tooltip_text('Linked to '+source+'. Change its source in Assembly.')
                    if key in self.linked_notes:
                        box, note = self.linked_notes[key];note.set_text('Linked to '+source);box.set_visible(True)
                else:
                    spin.remove_css_class('derived')
                    spin.set_tooltip_text(self.input_labels[key])
                    if key in self.linked_notes:self.linked_notes[key][0].set_visible(False)
            self.building = False
            for key, label in self.geometry_derived.items():
                value = (design.values['sun'] + 2*design.values['planet']
                         if key=='planets' else design.values['pins']-1)
                label.set_text(str(int(value)))
            io_controls.update(self, design)
            purchases = sum(row['quantity'] for row in bom.build(design)['rows']
                            if row['category'] == 'PURCHASE')
            self.metric_cards.set_sensitive(True)
            self.update_metrics(design)
            self.metrics.set_text('\n'.join(design.metrics))
            self.bom_summary.set_text(
                f'{len(design.parts)} components'
                + (f' · {purchases} to purchase' if purchases else '')
            )
            self.bom_summary.set_tooltip_text(f'BOM: {purchases} components to purchase')
            self.notes.set_text('\n\n'.join(design.notes))
            gui_workflow.update_geometry_warning(self, design)
            self.hidden_hint.set_visible(bool(self.canvas.scene and not self.canvas.scene.parts))
            self.last_valid_family = self.family
            self.parameter_error.set_visible(False)
            for feedback in self.field_feedback.values():feedback.set_visible(False)
            self.error_reveal.set_visible(False)
            self.export_menu.set_sensitive(not self.busy)
            self.empty.set_visible(False)
            self.empty.remove_css_class('invalid')
            self.send_btn.set_sensitive(not self.busy)
            self.fusion_send_btn.set_sensitive(not self.busy)
            self.live_label.set_text('✓ Geometry generated')
            self.status.remove_css_class('error')
            if not self.busy:
                self.status_text('✓ Geometry generated')
            self.reconcile_project(reconcile_token)
            self.interference.refreshed(design)
            self.combination_search.refreshed(design)
            self.components.refreshed(design)
            return True
        except Exception as e:
            self.building = False
            self.design = None
            self.components.invalidate('Invalid configuration · selection cleared')
            self.interference.invalidate('Invalid configuration · check blocked')
            self.combination_search.invalidate('Invalid configuration · search blocked')
            self.export_menu.set_sensitive(False)
            self.fusion_send_btn.set_sensitive(False)
            io_controls.update(self, None)
            if self.last_valid_family != self.family:
                self.canvas.set_design(None)
            self.canvas.invalidate_motion()
            retained = self.canvas.design is not None
            self.empty.set_text('! Last valid model · parameters do not match'
                                if retained else 'Invalid configuration')
            self.empty.set_visible(True)
            gui_workflow.show_parameter_error(self, str(e))
            self.warning_bar.set_visible(True)
            self.warning_bar.add_css_class('invalid')
            self.warning_details.set_visible(False)
            self.study.set_text('! Export blocked · preview and results show the last valid configuration.' if retained else '! Export blocked · correct the configuration.')
            self.study.set_visible(True)
            self.study.set_tooltip_text(str(e))
            self.empty.add_css_class('invalid')
            self.hidden_hint.set_visible(False)
            self.metric_cards.set_sensitive(False)
            for label in self.geometry_derived.values():label.set_text('—')
            self.metrics.set_text('Results out of date · ' + str(e))
            self.send_btn.set_sensitive(False)
            self.live_label.set_text('● Update required')
            self.status.add_css_class('error')
            self.status_text('! Invalid configuration · export blocked')
            return False

    def reset_defaults(self,*args):
        if self.busy:return
        self.project_changed();self.document.barrier()
        self.values[self.family]=defaults(self.family);self.raw_edits[self.family]={}
        self.make_fields();self.undo_reset.set_visible(True)
        self.status_text('Default parameters restored. Use Undo to restore your edits.')
    def undo_defaults(self,*args):
        self.undo_project();self.undo_reset.set_visible(False)
    def export(self,*args):
        if self.busy or not self.refresh(): return
        try:
            target=self.output_dir/f'{self.family}-{datetime.now():%Y%m%d-%H%M%S-%f}.package'
            design=self.design;config=self.config()
            captured=threading.Event();preview={}
            def capture_done(data,error):
                preview.update(data=data,error=error);captured.set()
            self.canvas.reset_motion()
            self.view_options['exploded'].set_active(False)
            self.view_options['section'].set_active(False)
            self.canvas.capture_png(capture_done)
            def work():
                if not captured.wait(30):
                    GLib.idle_add(setattr,self.canvas,'capture_callback',None)
                    raise RuntimeError('Preview capture timed out; no complete package was published.')
                if preview['error']:raise RuntimeError(f'Preview capture failed: {preview["error"]}')
                package_export.export(design,config,target,preview['data'])
                return f'Complete STEP, STL, SVG/DXF, configuration, CAD script, preview and reports package saved: {target}'
            self.background(work)
        except Exception as e:self.status_text(str(e))
    def export_step(self,*args):
        if self.busy or not self.refresh():return
        design=self.design
        target=self.output_dir/f'{self.family}-{datetime.now():%Y%m%d-%H%M%S-%f}.step-export'
        def work():
            folder,metadata=cad_export.export(design,target)
            return f'STEP in millimetres: assembly and {len(metadata)} components saved in {folder}'
        self.background(work)
    def export_profiles(self,*args):
        if self.busy or not self.refresh():return
        design=self.design
        target=self.output_dir/f'{self.family}-{datetime.now():%Y%m%d-%H%M%S-%f}.profiles-export'
        def work():
            folder,metadata=profile_export.export(design,target)
            return f'SVG/DXF in millimetres saved in {folder} · see profiles.json: helical/deformed sections are not extrusion profiles'
        self.background(work)
    def export_stl(self,*args):
        if self.busy or not self.refresh():return
        design=self.design
        stem=self.output_dir/f'{self.family}-{datetime.now():%Y%m%d-%H%M%S-%f}'
        def work():
            self.output_dir.mkdir(parents=True,exist_ok=True)
            assembly,parts=stl_export.export(design,stem)
            return f'STL in millimetres: {assembly.name} and {len(parts)} components in {stem.name}.stl-parts · folder {self.output_dir}'
        self.background(work)
    def show_bom(self,*args):
        if not self.refresh():return
        return gui_workflow.show_report(self,'Bill of materials',bom.as_text(bom.build(self.design)))
    def show_calculations(self,*args):
        if not self.refresh():return
        from engineering import report_text
        return gui_workflow.show_report(self,'Nominal calculation report',report_text(self.design))
    def export_bom(self,*args):
        if not self.refresh():return
        try:
            self.output_dir.mkdir(parents=True,exist_ok=True);stem=self.output_dir/f'{self.family}-{datetime.now():%Y%m%d-%H%M%S-%f}'
            bom.export(self.design,stem);self.status_text(f'BOM TXT, CSV and JSON saved in {self.output_dir}')
        except Exception as e:self.status_text(str(e))
    def background(self,work):
        if self.busy:return
        self.busy=True;self.spinner.start();self.update_playback_bar()
        self.components.update()
        self.send_btn.set_sensitive(False); self.connect_btn.set_sensitive(False); self.selector.set_sensitive(False); self.fields.set_sensitive(False);self.variant_selector.set_sensitive(False);self.motion_button.set_sensitive(False);self.io_frame.set_sensitive(False)
        self.fusion_install_btn.set_sensitive(False);self.fusion_connect_btn.set_sensitive(False);self.fusion_send_btn.set_sensitive(False);self.export_menu.set_sensitive(False)
        for button in self.file_buttons: button.set_sensitive(False)
        self.status_text('Operation in progress… please wait.');self.live_label.set_text('● Working')
        def run():
            try: result=work(); failed=False;message=result if isinstance(result,str) else 'Model created in SolidCraft. Save it from CAD as .solidcraft or export it as STEP.'
            except Exception as e:
                failed=True;message=str(e); traceback.print_exc()
            # Keep short completion callbacks responsive when animations keep the loop busy.
            GLib.idle_add(done,message,failed,priority=GLib.PRIORITY_DEFAULT)
        def done(message,failed):
            if failed:self.status.add_css_class('error')
            else:self.status.remove_css_class('error')
            self.busy=False;self.spinner.stop();self.update_playback_bar()
            self.components.update()
            for button in self.file_buttons: button.set_sensitive(True)
            self.fusion_install_btn.set_sensitive(True);self.fusion_connect_btn.set_sensitive(True);self.fusion_send_btn.set_sensitive(self.design is not None)
            self.connect_btn.set_sensitive(True); self.selector.set_sensitive(True); self.fields.set_sensitive(True);self.variant_selector.set_sensitive(True);self.motion_button.set_sensitive(True);self.io_frame.set_sensitive(True);self.live_label.set_text('● Live update'); self.send_btn.set_sensitive(self.design is not None); self.export_menu.set_sensitive(self.design is not None); self.status_text(message); self.update_document(); return False
        threading.Thread(target=run,daemon=True).start()
    def send(self,*args):
        if self.busy or not self.refresh():return
        design=self.design
        visible_roles={'gear'}
        if self.canvas.show_support:visible_roles.add('support')
        if self.canvas.show_housing:visible_roles.add('housing')
        # A new unique group on every send, even if the preview is unchanged.
        def work():
            self.connect_cad()
            self.output_dir.mkdir(parents=True,exist_ok=True)
            stem=f'{design.family}-{design.token}'
            (self.output_dir/(stem+'.config.json')).write_text(json.dumps({'format':'solidcraft-riduttori/1','family':design.family,'parameters':design.values},indent=2),encoding='utf-8')
            assets=self.output_dir/(stem+'.assets');design.prepare_assets(assets)
            (self.output_dir/(stem+'.script.json')).write_text(json.dumps({'commands':design.commands(assets)},indent=2),encoding='utf-8')
            bom.export(design,self.output_dir/stem)
            with Client() as c:
                GLib.idle_add(self.set_connection,True)
                result=c.insert(design,visible_roles=visible_roles,asset_dir=assets)
                try:c.execute('assembly.bom',component=f'Reducers_{design.family}_{design.token}',path=str(self.output_dir/(stem+'.solidcraft-bom.csv')),format='csv')
                except Exception as error:return f'Model created. BOM TXT/CSV/JSON saved in {self.output_dir}. Native CSV export failed: {error}. Do not send the model again.'
                return f'Model created in SolidCraft. BOM TXT, CSV, JSON and native CSV saved in {self.output_dir}. Save the document from CAD.'
        self.background(work)
    def send_fusion(self,*args):
        if self.busy or not self.refresh():return
        design=self.design
        output_dir=self.output_dir
        visible_roles={'gear'}
        if self.canvas.show_support:visible_roles.add('support')
        if self.canvas.show_housing:visible_roles.add('housing')
        def work():
            try:
                with fusion_connection.Client() as client:
                    result=client.insert(design,output_dir,visible_roles)
                    # Query again after import: active documents can change in
                    # Fusion while RatioLab's worker is preparing STEP files.
                    try:status=client.status()
                    except Exception:
                        GLib.idle_add(self.set_fusion_connection,None,priority=GLib.PRIORITY_DEFAULT)
                    else:GLib.idle_add(self.set_fusion_connection,status,priority=GLib.PRIORITY_DEFAULT)
            except Exception:
                GLib.idle_add(self.set_fusion_connection,None,priority=GLib.PRIORITY_DEFAULT)
                raise
            return f"Model created in Fusion as STEP solids. Save the Fusion document. Package, BOM and RatioLab parameters saved in {result['package_path']}."
        self.background(work)


def main(argv=None):
    return ReducerApp().run(sys.argv if argv is None else argv)


if __name__=='__main__':
    raise SystemExit(main())
