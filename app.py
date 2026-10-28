#!/usr/bin/python3
"""Companion desktop GTK 4 con anteprima 3D locale e aggiornamento automatico."""
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
from preview3d import Preview3D
from catalog import BEARINGS,MODES,FITS,SUPPORTED
import bom
import stl_export
import io_controls
import motion_controls
import gui_workflow
import result_controls
import workspace_ui
from kinematics import options as io_options,default as io_default,TRIPLES as IO_TRIPLES
import hardware_catalog as hw

BASE=Path(__file__).resolve().parent
GLib.set_application_name('RatioLab')
GENERATED=app_paths.default_output_dir()
LABELS=[gui_workflow.CATALOG.get(key,(label,''))[0] for key,label in FAMILIES.items()]

class ReducerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=app_paths.APP_ID)
        self.values={};self.design=None;self.family='parallel';self.busy=False;self.pending=0;self.building=False;self.variant_model_family=None;self.last_valid_family=None;self.connected=False
    def do_activate(self):
        if hasattr(self,'win'):self.win.present();return
        self.BASE=BASE;self.output_dir=GENERATED;self.file_buttons=[];self.reset_values=None
        self.output_dir=app_paths.saved_output_dir(legacy_root=BASE)
        self.families = FAMILIES
        workspace_ui.build(self, LABELS)
        self.make_fields()
        self.update_playback_bar()
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
        if getattr(self, 'motion_input_invalid', False):
            self.error_field='input_rpm'
            raise ValueError('Input speed: '+self.motion_rate_error.get_text())
        result=dict(getattr(self,"option_values",{}))
        for key,spin in self.inputs.items():
            try:result[key]=float(spin.get_text().strip().replace(',','.'))
            except ValueError:
                self.error_field=key;spin.add_css_class('field-error');raise ValueError('Complete the numeric value: '+self.input_labels[key])
            else:spin.remove_css_class('field-error')
        if hasattr(self,'motion_rpm'):result['input_rpm']=self.motion_rpm
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
        if hasattr(self,'inputs'):
            try:self.values[self.family]=self.read_values()
            except ValueError:pass
    def change_family(self,*args):
        if self.building:return
        self.remember();self.family=list(FAMILIES)[self.selector.get_selected()];self.make_fields()
    def make_fields(self):
        self.building=True
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
                try:current=self.read_values()
                except ValueError:current=dict(values)
                current[key]=keys[widget.get_selected()]
                if key=='eccentric_design':
                    if current[key]=='fdm_bolted':
                        from printed_shaft import SUPPORTED_SCHEMES
                        current.update(bearing_mode='manual',hardware_mode='none')
                        if current.get('io_scheme') not in SUPPORTED_SCHEMES:current['io_scheme']=SUPPORTED_SCHEMES[0]
                self.values[self.family]=current;self.make_fields()
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
                current=self.read_values();current.update(PRESET)
                self.values[self.family]=current;self.make_fields()
            preset.connect('clicked',apply_printed_preset);self.eccentric_design_box.append(preset)
            self.printed_preset_button=preset
        if double and self.family!='double':choice('double_style','Double helix construction',DOUBLE_STYLES,'joined' if values.get('gap',1)==0 else 'separated')
        io_controls.build(self,values,variant,choice)
        self.sections['bearings'][0].set_visible(self.family in SUPPORTED and not printed)
        field_target=self.sections['bearings'][1]
        if self.family in SUPPORTED:
            choice('bearing_mode','Standard fit',MODES,'manual')
            if self.option_values.get('bearing_mode')!='manual':
                choice('bearing','NSK bearing · d × D × B',{k:b.label for k,b in BEARINGS.items()},'608' if self.family=='cycloidal' else '626')
                choice('fit','Seat dimensions',FITS,'nominal')
                b=BEARINGS[self.option_values['bearing']]
                link=Gtk.LinkButton.new_with_label(b.url,'Official NSK datasheet ↗')
                link.connect('activate-link',lambda button:gui_workflow.open_link(self,button.get_uri()))
                field_target.append(link)
                field_target.append(Gtk.Label(label='Linked dimensions are shown after calculation. Assembly options add available retainers.',xalign=0,wrap=True,css_classes=['muted']))
        self.sections['hardware'][0].set_visible(self.family in hw.SUPPORTED and not printed)
        field_target=self.sections['hardware'][1]
        if self.family in hw.SUPPORTED:
            choice('hardware_mode','Hardware and assembly',hw.MODES,'none')
            if self.option_values['hardware_mode']=='standard':
                for key,label in [('retaining','Retaining rings and grooves'),('keys','Compatible keys and keyways'),('bolts','Flange screws, nuts and holes'),('shims','Shims and spacers')]:
                    name='hardware_'+key;check=Gtk.CheckButton(label=label);check.set_active(values.get(name,True));self.option_values[name]=values.get(name,True)
                    def toggled(widget,key=name):
                        if self.building:return
                        try:current=self.read_values()
                        except ValueError:current=dict(values)
                        current[key]=widget.get_active();self.values[self.family]=current;self.make_fields()
                    check.connect('toggled',toggled);field_target.append(check)
                choice('hardware_screw','Flange fasteners',{k:k for k in hw.FASTENERS},'M3')
                choice('hardware_shim','DIN 988 shim thickness',hw.SHIM_THICKNESSES,'.5')
                field_target.append(Gtk.Label(label='Automatic dimensions and quantities; remaining connections are listed in the BOM.',xalign=0,wrap=True,css_classes=['muted']))
        specs=get_specs(self.family,variant,self.option_values.get('double_style'))
        if self.option_values.get('bearing_mode','manual')!='manual':
            specs+=[('shoulder','Minimum axial margin [mm]',1,.5,5,.5)]
            if self.option_values.get('fit')=='custom':specs+=[('seat_allowance','Seat diameter allowance [mm]',0,-.08,.8,.01),('shaft_allowance','Shaft diameter allowance [mm]',0,-.8,.08,.01)]
        motion_controls.configure(self,values,specs)
        gui_workflow.geometry_groups(self, specs)
        gui_workflow.update_family(self)
        self.building=False
        if self.family!=self.last_valid_family:self.canvas.view('iso')
        self.refresh()
    def changed(self,*args):
        if self.building:
            return
        if args and ',' in args[0].get_text():
            widget = args[0]
            position = widget.get_position()
            widget.set_text(widget.get_text().replace(',', '.'))
            widget.set_position(position)
            return
        self.send_btn.set_sensitive(False)
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
        try:
            values = self.read_values()
            design = generate(self.family, values)
            self.canvas.set_design(design)
            self.design = design
            self.values[self.family] = values
            linked = set()
            mode = values.get('bearing_mode', 'manual')
            if mode != 'manual':
                if self.family in ('spur', 'helical', 'double'):
                    linked = {'bore'}
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
            self.live_label.set_text('✓ Geometry generated')
            self.status.remove_css_class('error')
            if not self.busy:
                self.status_text('✓ Geometry generated')
            return True
        except Exception as e:
            self.building = False
            self.design = None
            self.export_menu.set_sensitive(False)
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
        try:self.reset_values=(self.family,self.read_values())
        except ValueError:self.reset_values=(self.family,dict(self.values.get(self.family,defaults(self.family))))
        self.values[self.family]=defaults(self.family);self.make_fields();self.undo_reset.set_visible(True);self.status_text('Default parameters restored. Use the button alongside to undo.')
    def undo_defaults(self,*args):
        if not self.reset_values:return
        family,values=self.reset_values;self.remember();self.selector.set_selected(list(FAMILIES).index(family));self.family=family;self.values[family]=values;self.make_fields();self.reset_values=None;self.undo_reset.set_visible(False)
    def save_dialog(self,*args):
        if self.busy or not self.refresh():return
        config=self.config()
        dialog=Gtk.FileChooserNative(title='Save model configuration',transient_for=self.win,action=Gtk.FileChooserAction.SAVE,accept_label='Save',cancel_label='Cancel')
        dialog.set_current_name(f'{self.family}.config.json')
        if self.output_dir.exists():dialog.set_current_folder(Gio.File.new_for_path(str(self.output_dir)))
        def response(d,r):
            if r==Gtk.ResponseType.ACCEPT:
                try:
                    path=Path(d.get_file().get_path());path.write_text(json.dumps(config,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');self.status_text(f'Configuration saved: {path}')
                except Exception as e:self.status_text(f'Configuration could not be saved: {e}')
            d.destroy()
        dialog.connect('response',response);dialog.show()
    def config(self):
        self.remember(); result={'format':'solidcraft-riduttori/1','family':self.family,'parameters':self.values[self.family]}
        return result
    def save_config(self,*args):
        if not self.refresh():return
        try:
            self.output_dir.mkdir(parents=True,exist_ok=True); path=self.output_dir/f'{self.family}-{datetime.now():%Y%m%d-%H%M%S-%f}.config.json'
            path.write_text(json.dumps(self.config(),indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); self.status_text(f'Configuration saved: {path}')
        except Exception as e:self.status_text(str(e))
    def load_config_data(self,obj):
        if obj.get('format')!='solidcraft-riduttori/1':raise ValueError('Unknown configuration format')
        family=obj['family']
        if family not in FAMILIES:raise ValueError('Unsupported reducer: '+str(family))
        checked=generate(family,obj['parameters']);self.remember()
        self.building=True
        self.selector.set_selected(list(FAMILIES).index(family));self.family=family;self.values[family]=checked.values;self.make_fields()

    def load_dialog(self,*args):
        dialog=Gtk.FileChooserNative(title='Open reducer configuration',transient_for=self.win,action=Gtk.FileChooserAction.OPEN,accept_label='Open',cancel_label='Cancel')
        f=Gtk.FileFilter(); f.set_name('JSON configurations'); f.add_pattern('*.json'); dialog.add_filter(f)
        def response(d,r):
            if r==Gtk.ResponseType.ACCEPT:
                try:
                    self.load_config_data(json.loads(Path(d.get_file().get_path()).read_text(encoding='utf-8')))
                except Exception as e:self.status_text(f'Configuration could not be loaded: {e}')
            d.destroy()
        dialog.connect('response',response); dialog.show()
    def export(self,*args):
        if self.busy or not self.refresh(): return
        try:
            self.output_dir.mkdir(parents=True,exist_ok=True); stem=f'{self.family}-{datetime.now():%Y%m%d-%H%M%S-%f}'
            design=self.design;config=self.config()
            self.canvas.reset_motion();self.canvas.save_png(self.output_dir/(stem+'.png'))
            def work():
                assets=self.output_dir/(stem+'.assets');design.prepare_assets(assets)
                path=self.output_dir/(stem+'.script.json');path.write_text(json.dumps({'commands':design.commands(assets)},indent=2)+'\n',encoding='utf-8')
                (self.output_dir/(stem+'.config.json')).write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
                stl_export.export(design,self.output_dir/stem);bom.export(design,self.output_dir/stem)
                return f'Script, configuration, assembly and component STL files, preview, BOM and calculations saved in {self.output_dir}'
            self.background(work)
        except Exception as e:self.status_text(str(e))
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
        self.send_btn.set_sensitive(False); self.connect_btn.set_sensitive(False); self.selector.set_sensitive(False); self.fields.set_sensitive(False);self.variant_selector.set_sensitive(False);self.motion_button.set_sensitive(False);self.io_frame.set_sensitive(False)
        for button in self.file_buttons: button.set_sensitive(False)
        self.status_text('Operation in progress… please wait.');self.live_label.set_text('● Working')
        def run():
            try: result=work(); failed=False;message=result if isinstance(result,str) else 'Model created in SolidCraft. Save it from CAD as .solidcraft or export it as STEP.'
            except Exception as e:
                failed=True;message=str(e); traceback.print_exc()
            GLib.idle_add(done,message,failed)
        def done(message,failed):
            if failed:self.status.add_css_class('error')
            else:self.status.remove_css_class('error')
            self.busy=False;self.spinner.stop();self.update_playback_bar()
            for button in self.file_buttons: button.set_sensitive(True)
            self.connect_btn.set_sensitive(True); self.selector.set_sensitive(True); self.fields.set_sensitive(True);self.variant_selector.set_sensitive(True);self.motion_button.set_sensitive(True);self.io_frame.set_sensitive(True);self.live_label.set_text('● Live update'); self.send_btn.set_sensitive(self.design is not None); self.export_menu.set_sensitive(self.design is not None); self.status_text(message); return False
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


def main(argv=None):
    return ReducerApp().run(sys.argv if argv is None else argv)


if __name__=='__main__':
    raise SystemExit(main())
