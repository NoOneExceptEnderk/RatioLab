# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""User-controlled GTK updates. Network, verification and preparation use workers."""
import logging
from pathlib import Path
import threading
import time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio, Pango
import app_paths
import external_programs
from release_version import RELEASE_VERSION, CHANNEL
import updates
import update_download
import update_install


class Controller:
    def __init__(self, app, header, fetch=updates.fetch_releases, launch=None,
                 detect=update_install.detect_installation,
                 download=update_download.download_release,
                 prepare=update_install.prepare_install, cache=None):
        self.app=app;self.fetch=fetch;self.launch=launch or self._launch
        self.detect=detect;self.download=download;self.prepare=prepare
        self.cache=Path(cache) if cache else Path(GLib.get_user_cache_dir())/'ratiolab'/'updates'
        self.alive=True;self.serial=0;self.inflight=False;self.timer=0
        self.release=None;self.installation=None;self.window=None;self.displayed_release=None
        self.job_serial=0;self.cancel_event=None;self.downloading=False;self.prepared=None
        self.helper_timer=0;self.worker_running=False;self.install_pending=False
        self.status=updates.disabled_reason() or 'Choose Check now to look for updates.'
        self.job_status='';self.status_label=None;self.check_button=None
        self.preferences=updates.Preferences(app_paths.config_dir()/'updates.json')
        self.button=Gtk.Button(visible=False,css_classes=['suggested-action'])
        self.badge_label=Gtk.Label(max_width_chars=27,ellipsize=Pango.EllipsizeMode.END)
        self.button.set_child(self.badge_label)
        self.button.set_tooltip_text('Read release notes and choose an update')
        self.button.connect('clicked',lambda *_:self.show())
        header.pack_end(self.button)
        app.win.connect('unrealize',lambda *_:self.close())
        app.connect('shutdown',lambda *_:self.close())

    def automatic(self):
        return updates.automatic_enabled() and self.preferences.automatic

    def start(self):
        if self.automatic():self.check()

    def close(self):
        if not self.alive:return
        self.alive=False;self.serial+=1
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        self._cancel_job()
        if self.window:self.window.destroy();self.window=None

    def _schedule(self,seconds):
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if not self.alive or not self.automatic():return
        def due():
            self.timer=0;self.check();return False
        self.timer=GLib.timeout_add_seconds(max(1,min(updates.DAY,int(seconds))),due)

    def set_automatic(self,enabled):
        try:self.preferences.set_automatic(enabled)
        except (OSError,ValueError) as error:
            self.status=str(error)
            if self.window:self._build_window()
            return
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if self.automatic():self.check()
        self._update_status()

    def check(self,manual=False):
        if not self.alive:return
        reason=updates.disabled_reason()
        if reason:
            self.status=reason;self._update_status();return
        if not manual and not self.automatic():return
        if self.inflight:
            self.status='Checking for updates…';self._update_status();return
        wait=self.preferences.state.get('next_allowed',0)-time.time()
        if wait>0 and (not manual or self.preferences.state.get('backoff_reason')!='network'):
            self.status=f'Update checks are temporarily limited. Try again in {max(1,int(wait/60)+1)} minutes.'
            self._schedule(wait);self._update_status();return
        self.serial+=1;serial=self.serial;self.inflight=True
        self.status='Checking for updates…';self._update_status()
        def work():
            release=None;installation=None;delay=updates.DAY;error='';kind=''
            try:
                installation=self.detect()
                release=updates.select_release(self.fetch(),**installation.selection_target())
            except updates.RetryAfter as failure:
                delay=failure.seconds;kind='rate_limit'
                error=f'GitHub has limited update checks. Try again in {max(1,int(delay/60))} minutes.'
            except Exception as failure:
                delay=updates.RETRY;kind='network'
                error='Could not check for updates: '+str(failure)+'. You can retry with Check now.'
            GLib.idle_add(self._complete,serial,release,installation,delay,error,kind)
        threading.Thread(target=work,name='RatioLab-update-check',daemon=True).start()

    def _complete(self,serial,release,installation,delay,error,kind):
        if not self.alive or serial!=self.serial:return False
        self.inflight=False
        self.preferences.state['next_allowed']=time.time()+delay if error else 0
        self.preferences.state['backoff_reason']=kind;self.preferences.save()
        if not error:
            if release!=self.release:self._cancel_job()
            self.release=release;self.installation=installation
            self.status='Update to '+release.version+' is available.' if release else 'You are up to date.'
            if self.window:self._build_window()
        else:self.status=error
        self.refresh();self._update_status();self._schedule(delay)
        return False

    def refresh(self):
        if (self.prepared or self.cancel_event) and self.release!=self.displayed_release:self._cancel_job()
        visible=bool(self.release and self.preferences.visible(self.release))
        if visible:
            self.badge_label.set_text('Update to '+self.release.version)
            self.button.set_tooltip_text('Update to '+self.release.version+' · Read release notes and choose an update')
        self.button.set_visible(visible)

    def _launch(self,url):
        return external_programs.launch_uri(url,Gio.AppLaunchContext())

    def _open(self,url,error_label):
        try:
            if self.launch(url) is False:raise OSError('No browser accepted this link')
        except Exception as error:
            error_label.set_text('Could not open your browser: '+str(error)+'\nCopy this URL:\n'+url)
            error_label.set_visible(True)

    def _hide(self,action,release=None,window=None):
        release=release or self.release
        if action=='skip':self.preferences.skip(release)
        else:self.preferences.remind(release)
        self.refresh()
        target=window or self.window
        if target:target.destroy()

    def _window_closed(self,window):
        if self.window is window:
            self._cancel_job();self.window=None;self.displayed_release=None
            self.status_label=None;self.check_button=None

    def show(self,manual=False):
        if not self.alive:return
        if self.window and self.displayed_release!=self.release:self.window.destroy()
        if not self.window:
            self.window=Gtk.Window(title='RatioLab · Release notes and updates',transient_for=self.app.win,
                                   application=self.app,default_width=720,default_height=650)
            self.window.add_css_class('reducers')
            self.window.connect('unrealize',self._window_closed)
            self._build_window()
        self.window.present()
        if manual:self.check(manual=True)

    def _update_status(self):
        if self.status_label:
            self.status_label.set_text(self.status)
            self.check_button.set_sensitive(not self.inflight and not bool(updates.disabled_reason()))

    def _eligible(self):
        return bool(self.release and self.installation and self.installation.can_install
                    and self.release.asset_name and self.release.asset_size and self.release.checksums_url)

    def _build_window(self):
        window=self.window;release=self.release
        if self.displayed_release!=release:self._cancel_job()
        self.displayed_release=release
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,
                    margin_top=18,margin_bottom=18,margin_start=18,margin_end=18)
        window.set_child(box)
        title='Update to '+release.version if release else 'RatioLab '+RELEASE_VERSION
        box.append(Gtk.Label(label=title,xalign=0,css_classes=['title-2']))
        box.append(Gtk.Label(label=f'Current version: {RELEASE_VERSION} · {CHANNEL} channel',xalign=0))
        checks=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=10,row_spacing=8,
                           min_children_per_line=1,max_children_per_line=2);box.append(checks)
        self.check_button=Gtk.Button(label='Check now')
        self.check_button.connect('clicked',lambda *_:self.check(manual=True));checks.append(self.check_button)
        automatic=Gtk.CheckButton(label='Check for updates automatically',active=self.preferences.automatic)
        automatic.connect('toggled',lambda widget:self.set_automatic(widget.get_active()));checks.append(automatic)
        self.automatic_button=automatic
        self.status_label=Gtk.Label(xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,selectable=True);box.append(self.status_label)
        self._update_status()
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);box.append(scroll)
        pages=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);scroll.set_child(pages)
        if release:
            pages.append(Gtk.Label(label='Published release notes',xalign=0,css_classes=['heading']))
            pages.append(Gtk.Label(label=release.notes or 'No published release notes.',xalign=0,
                                   wrap=True,selectable=True,natural_wrap_mode=Gtk.NaturalWrapMode.WORD))
        pages.append(Gtk.Label(label='Local changelog',xalign=0,wrap=True,css_classes=['heading']))
        try:local=app_paths.resource_path('CHANGELOG.md').read_text(encoding='utf-8')
        except OSError:local='Local changelog is unavailable. See the project releases.'
        pages.append(Gtk.Label(label=local,xalign=0,wrap=True,selectable=True))
        self.job_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);box.append(self.job_box)
        self._job_widgets()
        row=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=8,row_spacing=8,
                        min_children_per_line=1,max_children_per_line=4);box.append(row)
        launch_error=Gtk.Label(xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,selectable=True,visible=False)
        if release:
            download=Gtk.Button(label='Download' if release.download!=release.url else 'Open release page')
            download.connect('clicked',lambda *_:self._open(release.download,launch_error));row.append(download)
            notes=Gtk.Button(label='Release page')
            notes.connect('clicked',lambda *_:self._open(release.url,launch_error));row.append(notes)
            for label,action in [('Skip this version','skip'),('Remind me later','remind')]:
                button=Gtk.Button(label=label)
                button.connect('clicked',lambda _,a=action,r=release,w=window:self._hide(a,r,w));row.append(button)
        else:
            button=Gtk.Button(label='Project releases')
            button.connect('clicked',lambda *_:self._open(updates.RELEASES_URL,launch_error));row.append(button)
        box.append(launch_error)
        explanation=self.installation.explanation if self.installation else 'Check now to detect update options for this installation.'
        if release and self.installation and self.installation.can_install and not self._eligible():
            explanation+=' This release has no supported package with SHA256SUMS metadata. Use Download for manual installation.'
        box.append(Gtk.Label(label=explanation,xalign=0,wrap=True,css_classes=['muted']))

    def _job_widgets(self):
        if not self.window:return
        child=self.job_box.get_first_child()
        while child:
            following=child.get_next_sibling();self.job_box.remove(child);child=following
        self.progress_bar=None;self.install_button=None
        if self.job_status:self.job_box.append(Gtk.Label(label=self.job_status,xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,selectable=True))
        if self.downloading:
            self.progress_bar=Gtk.ProgressBar(show_text=True);self.progress_bar.set_text('Downloading and verifying…')
            self.job_box.append(self.progress_bar)
        if self.prepared:
            prepared=self.prepared
            self.job_box.append(Gtk.Label(label='Verified package ready. '+str(prepared.command or ''),xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,selectable=True))
            button=Gtk.Button(label=prepared.action_label,css_classes=['suggested-action'])
            button.connect('clicked',lambda *_:self.install());self.job_box.append(button);self.install_button=button
            button.set_sensitive(not self.install_pending)
        elif not self.downloading and self._eligible():
            detail=('The verified update will close RatioLab and run Setup. Follow Setup to finish and restart.'
                    if self.installation.package_format=='setup.exe' else 'The verified update will close RatioLab, install and request a restart.') if self.installation.requires_exit else 'The verified package will open through your system installer.'
            self.job_box.append(Gtk.Label(label=detail,xalign=0,wrap=True))
            button=Gtk.Button(label='Update now',css_classes=['suggested-action'])
            button.set_sensitive(not self.worker_running)
            button.connect('clicked',lambda *_:self.begin_download());self.job_box.append(button)
        if self.downloading or self.prepared:
            cancel=Gtk.Button(label='Cancel');cancel.connect('clicked',lambda *_:self.cancel_download());self.job_box.append(cancel)

    @staticmethod
    def _disarm(prepared):
        if prepared:
            try:prepared.cancel()
            except Exception:
                logging.getLogger(__name__).exception('Could not disarm the update helper')

    def _cancel_job(self):
        self.job_serial+=1
        if self.helper_timer:GLib.source_remove(self.helper_timer);self.helper_timer=0
        if self.cancel_event:self.cancel_event.set()
        self._disarm(self.prepared)
        self.prepared=None;self.cancel_event=None;self.downloading=False;self.install_pending=False
        self.job_status=''

    def cancel_download(self):
        self._cancel_job();self.job_status='Update cancelled. You can prepare a fresh package.';self._job_widgets()

    def _current_job(self,serial,release):
        return self.alive and self.window is not None and serial==self.job_serial and release==self.release

    def begin_download(self):
        if self.worker_running or self.downloading or self.prepared or not self.window or not self._eligible():return
        self._cancel_job();self.downloading=True;self.worker_running=True
        serial=self.job_serial;release=self.release;installation=self.installation
        cancel=threading.Event();self.cancel_event=cancel
        self.job_status='Downloading the release package and verifying SHA-256…';self._job_widgets()
        def progress(received,total):GLib.idle_add(self._progress,serial,release,received,total)
        def work():
            verified=None;prepared=None;error=''
            try:
                verified=self.download(release,self.cache,cancel=cancel,progress=progress)
                if not cancel.is_set():prepared=self.prepare(verified,installation,directory=self.cache)
                if cancel.is_set() and prepared:self._disarm(prepared);prepared=None
            except Exception as failure:error=str(failure)
            finally:
                if verified:
                    try:verified.cleanup()
                    except Exception as failure:
                        if not error:error='Could not clean the download cache: '+str(failure)
            GLib.idle_add(self._download_complete,serial,release,prepared,error)
        threading.Thread(target=work,name='RatioLab-update-download',daemon=True).start()

    def _progress(self,serial,release,received,total):
        if self._current_job(serial,release) and self.progress_bar:
            if total:self.progress_bar.set_fraction(min(1,received/total))
            else:self.progress_bar.pulse()
            self.progress_bar.set_text(f'{received/1048576:.1f} MiB'+(f' / {total/1048576:.1f} MiB' if total else ''))
        return False

    def _download_complete(self,serial,release,prepared,error):
        self.worker_running=False
        if not self._current_job(serial,release):
            if prepared:self._disarm(prepared)
            if self.alive and self.window:self._job_widgets()
            return False
        self.downloading=False;self.cancel_event=None
        if error:
            if prepared:self._disarm(prepared)
            self.job_status='Update preparation failed: '+error
        elif prepared:
            self.prepared=prepared
            self.job_status='Package verified. Preparing the installation handoff.'
            self._monitor(prepared,serial,release)
        else:self.job_status='Update cancelled.'
        self._job_widgets()
        if self.prepared:self.install()
        return False

    def _monitor(self,prepared,serial,release):
        # status() is bounded and read-only; the helper alone performs the I/O.
        def poll():
            if not self._current_job(serial,release) or self.prepared is not prepared:
                self.helper_timer=0;return False
            try:status=prepared.status()
            except Exception as error:status='status unavailable: '+str(error)
            if status in ('ready','running'):return True
            self.helper_timer=0
            self._disarm(prepared);self.prepared=None;self.install_pending=False;self.job_serial+=1
            if status=='opened':
                detail='Package opened. Follow the system installer to complete the update.'
            elif status=='setup-completed':detail='Setup completed. Follow its completion instructions.'
            else:detail='Update helper stopped: '+status+'. Choose Update now to prepare a fresh package.'
            self.job_status=detail
            if status not in ('opened','setup-completed'):
                self.job_status+=' Log: '+str(prepared.log_path)+' Result: '+str(prepared.result_path)
            self._job_widgets();return False
        self.helper_timer=GLib.timeout_add(250,poll)

    def install(self):
        prepared=self.prepared
        if not prepared or self.install_pending:return
        serial=self.job_serial;release=self.release
        def current():return self._current_job(serial,release) and self.prepared is prepared
        def fail(error):
            self._disarm(prepared)
            if current():
                self.prepared=None;self.install_pending=False;self.job_serial+=1
                self.job_status='Could not start the update: '+str(error)+' Log: '+str(prepared.log_path)
                self._job_widgets()
        if not prepared.installation.requires_exit:
            try:prepared.launch()
            except Exception as error:fail(error);return
            self.install_pending=True;self.job_status='Opening the verified package through the system installer…'
            self._job_widgets();return
        if not callable(getattr(self.app,'protect_document',None)) or not callable(getattr(self.app,'finish_close_project',None)):
            fail('This window cannot safely close the current project.');return
        if getattr(self.app,'busy',False) or getattr(self.app,'project_dialog',None):
            fail('Finish the current operation before installing.');return
        # protect_document owns widget settlement, token checks and successful
        # Save/Discard. A cancelled/stale/failed answer never calls continuation.
        def accepted():
            if not current():return
            self.install_pending=True
            def arm():
                if not current():raise RuntimeError('The prepared update is no longer current')
                # Close auxiliary windows while the project remains usable if
                # one refuses to close. The updater closes with the main window.
                auxiliary=[window for window in self.app.get_windows()
                           if window is not self.app.win and window is not self.window]
                prepared.launch()
                # Normal main-window unrealize must not disarm this accepted job.
                self.prepared=None
                for window in auxiliary:
                    window.destroy()
                    if window.get_visible():raise RuntimeError('An application window could not be closed')
            try:
                if not self.app.finish_close_project(before_close=arm):
                    raise RuntimeError('The project could not be closed')
                self.app.quit()
            except Exception as error:
                self._disarm(prepared)
                if self.alive:
                    self.prepared=None;self.install_pending=False;self.job_serial+=1
                    self.job_status='Could not close for update: '+str(error)+' Log: '+str(prepared.log_path)
                    self._job_widgets()
        self.install_pending=True;self._job_widgets()
        def cancelled():
            self._disarm(prepared)
            if current():
                self._cancel_job()
                self.job_status='Update cancelled. Your project is still open. Choose Update now to retry.'
                self._job_widgets()
        try:self.app.protect_document(accepted,cancelled=cancelled)
        except Exception as error:fail(error)
