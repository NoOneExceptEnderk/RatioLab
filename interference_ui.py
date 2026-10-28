"""Revision-bound GTK controller. Analysis worker never accesses widgets."""
from copy import deepcopy
from dataclasses import asdict
from math import pi
from pathlib import Path
from threading import Thread, Event
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib, Gio
from project_document import equivalent
from workspace_tools import actions, details
from interference import analyze, Settings


def label(text):
    w=Gtk.Label(label=text,xalign=0,wrap=True,selectable=False);return w


class Controller:
    def __init__(self,app,container):
        self.app=app;self.serial=0;self.cancel=None;self.thread=None;self.result=None;self.snapshot=None;self.design_key=None;self.alive=True;self.window=None;self.saved_view=None;self.page=0;self.revision=None
        self.button=Gtk.Button(label='Check interference…')
        self.button.set_tooltip_text('Discrete 3D surface distance and interference check over the full labelled kinematic period')
        self.button.connect('clicked',lambda _:self.open())
        self.summary=Gtk.Label(label='Not checked',xalign=0,hexpand=True)
        container.register('interference',self)
        self.inspection_bar=Gtk.Box(spacing=8,halign=Gtk.Align.START,valign=Gtk.Align.START,margin_top=15,margin_start=15,css_classes=['playback-bar'])
        self.inspection_label=Gtk.Label()
        self.inspection_bar.append(self.inspection_label)
        restore=Gtk.Button(label='Restore preview');restore.connect('clicked',lambda _:self.restore_view());self.inspection_bar.append(restore)
        app.preview_overlay.add_overlay(self.inspection_bar);self.inspection_bar.set_visible(False)
        def inspection_state(*_):
            phase=app.canvas.inspection_phase
            self.inspection_bar.set_visible(phase is not None)
            if phase is not None:self.inspection_label.set_text(f'Inspection · phase {phase*180/pi:.6g}°')
        app.canvas.connect('inspection-state',inspection_state)
        app.win.connect('unrealize',lambda *_:self.close())

    def key(self,design):return (design.family,deepcopy(design.values)) if design else None

    def changed(self,snapshot):
        if self.snapshot is not None and not equivalent(snapshot,self.snapshot):self.invalidate('Model changed · run a new check')

    def refreshed(self,design):
        key=self.key(design)
        if self.design_key is not None and key!=self.design_key:self.invalidate('Geometry changed · run a new check')
        if hasattr(self,'run_button'):self.run_button.set_sensitive(design is not None and self.cancel is None)

    def invalidate(self,message='Results out of date · run a new check'):
        self.serial+=1
        if self.cancel:self.cancel.set()
        self.cancel=None;self.result=None;self.snapshot=None;self.design_key=None
        self.restore_view();self.summary.set_text(message)
        if self.window:
            self.coverage.set_visible(False)
            self.status.set_text(message);self.report.get_buffer().set_text(message);self.clear_rows()
            self.cancel_button.set_sensitive(False);self.run_button.set_sensitive(self.app.design is not None)
            self.save_button.set_sensitive(False)

    def close(self):
        self.invalidate('Check closed');self.alive=False
        if self.window:self.window.destroy();self.window=None

    def open(self):
        if self.window:self.window.present();return
        win=self.app.tools.panel('interference')
        self.window=win
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_top=14,margin_bottom=14,margin_start=14,margin_end=14);win.set_child(box)
        box.append(label('Check all components, including hidden supports and housing. Distances use shared preview/STL facets in mm. Discrete sampling can miss collisions between poses.'))
        controls=Gtk.Grid(column_spacing=8,row_spacing=8);self.setup=details(box,'Check settings',controls);self.setup.set_expanded(True)
        controls.attach(label('Phase step [°]'),0,0,1,1);self.step=Gtk.SpinButton.new_with_range(.1,180,.5);self.step.set_digits(1);self.step.set_value(30);controls.attach(self.step,1,0,1,1)
        controls.attach(label('Boundary tolerance [mm]'),0,1,1,1);self.tolerance=Gtk.SpinButton.new_with_range(.000001,1,.001);self.tolerance.set_digits(6);self.tolerance.set_value(.01);controls.attach(self.tolerance,1,1,1,1)
        controls.attach(label('Time limit [s]'),0,2,1,1);self.seconds=Gtk.SpinButton.new_with_range(1,3600,10);self.seconds.set_value(120);controls.attach(self.seconds,1,2,1,1)
        buttons=actions(box)
        self.run_button=Gtk.Button(label='Check cycle');self.run_button.connect('clicked',lambda _:self.start());buttons.append(self.run_button)
        self.cancel_button=Gtk.Button(label='Cancel');self.cancel_button.connect('clicked',lambda _:self.stop());buttons.append(self.cancel_button)
        self.cancel_button.set_sensitive(self.cancel is not None);self.run_button.set_sensitive(self.cancel is None)
        run_actions=buttons
        self.coverage=label('');self.coverage.set_visible(False);box.append(self.coverage)
        self.status=label(self.summary.get_text());box.append(self.status)
        self.progress=Gtk.ProgressBar();box.append(self.progress)
        box.append(label('Select a finding to show its phase: orange / magenta parts. Boundary contact / unresolved is a potential interference, even at an expected interface.'))
        self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE);self.list.connect('row-selected',self.selected)
        scroll=Gtk.ScrolledWindow(vexpand=True);scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);scroll.set_min_content_height(180);scroll.set_child(self.list);box.append(scroll)
        buttons=actions(box)
        previous=Gtk.Button(label='Previous');previous.connect('clicked',lambda _:self.change_page(-1));buttons.append(previous)
        following=Gtk.Button(label='Next');following.connect('clicked',lambda _:self.change_page(1));buttons.append(following)
        self.page_label=label('');buttons.append(self.page_label)
        restore=Gtk.Button(label='Restore preview');restore.connect('clicked',lambda _:self.restore_view());buttons.append(restore)
        self.save_button=Gtk.Button(label='Save report…');self.save_button.connect('clicked',lambda _:self.save());buttons.append(self.save_button);self.save_button.set_sensitive(self.result is not None)
        self.report=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR);self.report.set_cursor_visible(False)
        report_scroll=Gtk.ScrolledWindow();report_scroll.set_min_content_height(150);report_scroll.set_child(self.report);details(box,'Full interference report',report_scroll)
        def close(*_):
            self.restore_view()
            if self.cancel:self.stop()
            self.window=None
            return False
        win.connect('close-request',close)
        if self.result:self.present_result()
        win.pin(self.coverage,self.status,self.progress,run_actions)
        self.tolerance.set_width_chars(11)
        win.present()
        self.run_button.grab_focus()

    def clear_rows(self):
        while (child:=self.list.get_first_child()):self.list.remove(child)
        self.page_label.set_text('')

    def start(self,settings=None):
        if not self.alive or self.cancel is not None:return
        if self.thread is not None and self.thread.is_alive():
            self.summary.set_text('Previous check is stopping · try again shortly');return
        app=self.app
        # Settle debounce and normalization BEFORE capturing the actual revision.
        app.project_changed()
        if not app.refresh():
            self.invalidate('Invalid configuration · check blocked');return
        self.invalidate('Preparing check…')
        self.snapshot=deepcopy(app.project_snapshot());self.design_key=self.key(app.design)
        design=deepcopy(app.design);revision=app.document.token;self.revision=revision;serial=self.serial
        settings=settings or Settings(step_degrees=self.step.get_value(),tolerance_mm=self.tolerance.get_value(),max_seconds=self.seconds.get_value())
        if self.window:self.setup.set_expanded(False)
        event=Event();self.cancel=event
        self.run_button.set_sensitive(False);self.cancel_button.set_sensitive(True)
        last=[0.]
        def progress(message,fraction):
            # At most ~10 UI notifications/sec; don't queue one idle per pair.
            from time import monotonic
            now=monotonic()
            if now-last[0]>=.1 or fraction==1:
                last[0]=now;GLib.idle_add(self.progress_update,serial,message,fraction)
        def worker():
            try:
                result=analyze(design,settings,event,progress);result.revision=revision;error=None
            except Exception as exc:result=None;error=f'Check failed: {type(exc).__name__}: {exc}'
            GLib.idle_add(self.finished,serial,result,error)
        self.thread=Thread(target=worker,name='RatioLab interference',daemon=True);self.thread.start()

    def current(self,serial):
        return self.alive and serial==self.serial and self.app.document.token==self.revision and self.snapshot is not None and equivalent(self.app.project_snapshot(),self.snapshot) and self.app.design is not None

    def progress_update(self,serial,message,fraction):
        if self.current(serial):
            self.summary.set_text(message)
            if self.window:self.status.set_text(message);self.progress.set_fraction(fraction)
        return False

    def stop(self):
        if self.cancel:
            self.cancel.set();self.summary.set_text('Cancelling…')
            if self.window:self.status.set_text('Cancelling…');self.cancel_button.set_sensitive(False)

    def finished(self,serial,result,error):
        if not self.current(serial):return False
        self.cancel=None
        if error:
            self.invalidate(error);return False
        self.result=result
        problems=sum(r['kind']!='Separated' for r in result.rows)
        message=('Sampled coverage complete' if result.coverage_complete else 'INCOMPLETE check')+f' · {problems} potential interference/contact classes · {result.completed_poses} poses'
        self.summary.set_text(message)
        if self.window:
            self.run_button.set_sensitive(True);self.cancel_button.set_sensitive(False);self.save_button.set_sensitive(True)
            self.status.set_text(message);self.progress.set_fraction(1 if result.coverage_complete else result.completed_poses/max(1,result.planned_poses));self.page=0;self.present_result()
        return False

    def present_result(self):
        if not self.window or not self.result:return
        result=self.result
        self.coverage.set_text(('Complete sampled coverage' if result.coverage_complete else 'INCOMPLETE coverage')+f' · {result.completed_poses}/{result.planned_poses} poses · step ≤ {result.settings["step_degrees"]:g}°')
        self.coverage.set_visible(True)
        self.clear_rows();self.report.get_buffer().set_text(self.result.text())
        rows=self.result.rows;start=self.page*100
        self.page_label.set_text(f'{start+1 if rows else 0}–{min(len(rows),start+100)} / {len(rows)} classes')
        for result in rows[start:start+100]:
            row=Gtk.ListBoxRow();row.finding=result
            expected=' · expected interface candidate' if result['expected'] else ''
            text=f'{result["index_a"]+1} {result["part_a"]} ↔ {result["index_b"]+1} {result["part_b"]}\n{result["kind"]}{expected} · surface {result["distance"]:.6g} mm · phase {result["phase_degrees"]:.6g}° · {result["samples"]} samples'
            row.set_child(label(text));self.list.append(row)

    def change_page(self,delta):
        if self.result:self.page=max(0,min((len(self.result.rows)-1)//100,self.page+delta));self.present_result()

    def selected(self,_,row):
        if row is None or not self.result or not self.current(self.serial):return
        app=self.app
        if hasattr(app,'components'):app.components.restore();app.components.clear_points()
        if self.saved_view is None:
            self.saved_view={k:w.get_active() for k,w in app.view_options.items()}
        for key in ('exploded','section'):app.view_options[key].set_active(False)
        for key in ('support','housing'):app.view_options[key].set_active(True)
        result=row.finding
        app.canvas.show_inspection(result['phase_degrees']*pi/180,(result['index_a'],result['index_b']))
        self.status.set_text(f'Inspection phase {result["phase_degrees"]:.6g}° · {result["part_a"]} (orange) / {result["part_b"]} (magenta).')

    def restore_view(self):
        self.app.canvas.clear_inspection()
        saved=self.saved_view;self.saved_view=None
        if saved:
            for key,value in saved.items():self.app.view_options[key].set_active(value)

    def save(self):
        if not self.result or not self.current(self.serial):return
        text=self.result.text();serial=self.serial
        dialog=Gtk.FileChooserNative(title='Save interference report',transient_for=self.app.win,action=Gtk.FileChooserAction.SAVE,accept_label='Save',cancel_label='Cancel');dialog.set_current_name('interference.txt')
        def response(widget,code):
            file=widget.get_file() if code==Gtk.ResponseType.ACCEPT else None;widget.destroy()
            if file and self.current(serial):
                try:
                    from export_transaction import write_text
                    write_text(Path(file.get_path()),text);self.status.set_text('Interference report saved')
                except (OSError,TypeError,ValueError) as exc:self.status.set_text(f'Report could not be saved: {exc}')
        dialog.connect('response',response);dialog.show()
