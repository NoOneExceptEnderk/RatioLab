# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK update badge and user-invoked notes. Workers never touch GTK widgets."""
import threading
import time
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib, Gio, Pango
import app_paths
from release_version import RELEASE_VERSION, CHANNEL
import updates


class Controller:
    def __init__(self,app,header,fetch=updates.fetch_releases,launch=None):
        self.app=app;self.fetch=fetch;self.launch=launch or self._launch
        self.alive=True;self.serial=0;self.inflight=False;self.timer=0;self.release=None;self.window=None
        self.displayed_release=None
        self.preferences=updates.Preferences(app_paths.config_dir()/'updates.json')
        self.button=Gtk.Button(visible=False,css_classes=['suggested-action'])
        self.badge_label=Gtk.Label(max_width_chars=27,ellipsize=Pango.EllipsizeMode.END)
        self.button.set_child(self.badge_label)
        self.button.set_tooltip_text('Read release notes and choose a download')
        self.button.connect('clicked',lambda *_:self.show())
        header.pack_end(self.button)
        app.win.connect('unrealize',lambda *_:self.close())
        app.connect('shutdown',lambda *_:self.close())

    def start(self):
        if updates.automatic_enabled():self.check()

    def close(self):
        self.alive=False;self.serial+=1
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if self.window:self.window.destroy();self.window=None

    def _schedule(self,seconds):
        if self.timer:GLib.source_remove(self.timer)
        def due():
            self.timer=0;self.check();return False
        self.timer=GLib.timeout_add_seconds(max(1,min(updates.DAY,int(seconds))),due)

    def check(self):
        if not self.alive or self.inflight or not updates.automatic_enabled():return
        wait=self.preferences.state.get('next_allowed',0)
        if isinstance(wait,(int,float)) and wait>time.time():
            self._schedule(wait-time.time());return
        self.serial+=1;serial=self.serial;self.inflight=True
        def work():
            release=None;delay=updates.DAY;success=False
            try:
                release=updates.select_release(self.fetch());success=True
            except updates.RetryAfter as error:delay=error.seconds
            except Exception:delay=updates.RETRY
            GLib.idle_add(self._complete,serial,release,delay,success)
        threading.Thread(target=work,name='RatioLab-update-check',daemon=True).start()

    def _complete(self,serial,release,delay,success):
        if not self.alive or serial!=self.serial:return False
        self.inflight=False
        # Persist rate-limit backoff, not a successful 24h delay: startup always checks.
        self.preferences.state['next_allowed']=0 if success else time.time()+delay
        self.preferences.save()
        if success:self.release=release
        self.refresh()
        if updates.automatic_enabled():self._schedule(delay)
        return False

    def refresh(self):
        visible=bool(self.release and self.preferences.visible(self.release))
        if visible:
            self.badge_label.set_text('Update to '+self.release.version)
            self.button.set_tooltip_text('Update to '+self.release.version+' · Read release notes and choose a download')
        self.button.set_visible(visible)

    def _launch(self,url):
        return Gio.AppInfo.launch_default_for_uri(url,None)

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
        if self.window is window:self.window=None;self.displayed_release=None

    def show(self):
        if not self.alive:return
        release=self.release
        if self.window:
            if self.displayed_release==release:self.window.present();return
            self.window.destroy()
        window=Gtk.Window(title='RatioLab · Release notes',transient_for=self.app.win,
                          application=self.app,default_width=670,default_height=560)
        self.window=window
        self.displayed_release=release
        window.add_css_class('reducers')
        window.connect('unrealize',self._window_closed)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,
                    margin_top=18,margin_bottom=18,margin_start=18,margin_end=18)
        window.set_child(box)
        title='Update to '+release.version if release else 'RatioLab '+RELEASE_VERSION
        box.append(Gtk.Label(label=title,xalign=0,css_classes=['title-2']))
        box.append(Gtk.Label(label=f'Current version: {RELEASE_VERSION} · {CHANNEL} channel',xalign=0))
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
        box.append(scroll)
        pages=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        scroll.set_child(pages)
        if release:
            pages.append(Gtk.Label(label='Published release notes',xalign=0,css_classes=['heading']))
            pages.append(Gtk.Label(label=release.notes or 'No published release notes.',xalign=0,
                                   wrap=True,selectable=True,natural_wrap_mode=Gtk.NaturalWrapMode.WORD))
        pages.append(Gtk.Label(label='Local changelog',
                               xalign=0,wrap=True,css_classes=['heading']))
        try:local=app_paths.resource_path('CHANGELOG.md').read_text(encoding='utf-8')
        except OSError:local='Local changelog is unavailable. See the project releases.'
        pages.append(Gtk.Label(label=local,xalign=0,wrap=True,selectable=True))
        row=Gtk.Box(spacing=8)
        box.append(row)
        launch_error=Gtk.Label(xalign=0,wrap=True,selectable=True,visible=False)
        if release:
            download=Gtk.Button(label='Download' if release.download!=release.url else 'Open release page',
                                css_classes=['suggested-action'])
            download.connect('clicked',lambda *_:self._open(release.download,launch_error))
            row.append(download)
            notes=Gtk.Button(label='Release page')
            notes.connect('clicked',lambda *_:self._open(release.url,launch_error));row.append(notes)
            for label,action in [('Skip this version','skip'),('Remind me later','remind')]:
                button=Gtk.Button(label=label)
                button.connect('clicked',lambda _,a=action,r=release,w=window:self._hide(a,r,w));row.append(button)
        else:
            button=Gtk.Button(label='Project releases')
            button.connect('clicked',lambda *_:self._open(updates.RELEASES_URL,launch_error));row.append(button)
        box.append(launch_error)
        box.append(Gtk.Label(label='Downloads open in your browser. Install the package yourself; your projects stay in place.',
                             xalign=0,wrap=True,css_classes=['muted']))
        window.present()
