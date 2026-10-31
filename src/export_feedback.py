# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Persistent feedback for completed standalone exports, independent of geometry."""
from dataclasses import dataclass
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Pango
import external_programs


@dataclass(frozen=True)
class ExportResult:
    kind: str
    outputs: tuple[Path,...]
    message: str

    @property
    def folder(self):
        return self.outputs[0].parent


class Controller:
    def __init__(self,app,container):
        self.app=app;self.result=None;self.latest=False
        self.box=Gtk.Box(spacing=12,css_classes=['footer'],visible=False)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,hexpand=True)
        self.box.append(text)
        self.description=Gtk.Label(xalign=0,selectable=True,ellipsize=Pango.EllipsizeMode.MIDDLE,
                                   max_width_chars=75,css_classes=['action-title'])
        self.destination=Gtk.Label(xalign=0,selectable=True,ellipsize=Pango.EllipsizeMode.MIDDLE,
                                   max_width_chars=75,css_classes=['muted'])
        self.notice=Gtk.Label(xalign=0,wrap=True,max_width_chars=75,visible=False)
        for label in (self.description,self.destination,self.notice):text.append(label)
        self.open_button=Gtk.Button(label='Open folder',valign=Gtk.Align.CENTER)
        self.open_button.connect('clicked',self.open_folder);self.box.append(self.open_button)
        self.dismiss_button=Gtk.Button(label='Dismiss',valign=Gtk.Align.CENTER)
        self.dismiss_button.set_tooltip_text('Dismiss export feedback')
        self.dismiss_button.connect('clicked',lambda _:self.dismiss());self.box.append(self.dismiss_button)
        container.append(self.box)

    def show_result(self):
        result=self.result
        self.open_button.set_visible(result is not None)
        self.destination.set_visible(result is not None)
        if result is not None:
            self.description.remove_css_class('error')
            extra=len(result.outputs)-1
            name=result.outputs[0].name+(f' + {extra} related '+('output' if extra==1 else 'outputs') if extra else '')
            self.description.set_text(f'{"Export complete" if self.latest else "Last export"} · {result.kind} · {name}')
            self.description.set_tooltip_text('\n'.join(str(path) for path in result.outputs))
            self.destination.set_text(str(result.folder));self.destination.set_tooltip_text(str(result.folder))
        self.box.set_visible(True)

    def set_notice(self,text,error=False):
        self.notice.set_text(text);self.notice.set_visible(bool(text))
        if error:self.notice.add_css_class('error')
        else:self.notice.remove_css_class('error')

    def begin(self):
        self.latest=False
        self.description.remove_css_class('error')
        if self.result is None:self.description.set_text('Export in progress…')
        self.set_notice('Export in progress…' if self.result else '')
        self.show_result()

    def completed(self,result):
        self.result=result;self.latest=True
        self.set_notice('');self.show_result()

    def failed(self,message,cancelled=False):
        self.latest=False
        title='Export cancelled' if cancelled else 'Export failed'
        if self.result is None:
            self.description.set_text(title)
            if not cancelled:self.description.add_css_class('error')
        self.set_notice((title+(': '+message if message else '')) if self.result else message,error=not cancelled)
        self.show_result()

    def dismiss(self):
        self.result=None;self.latest=False;self.set_notice('');self.box.set_visible(False)

    def open_folder(self,*_):
        if self.result is None:return
        try:
            folder=self.result.folder
            if not folder.is_dir():raise FileNotFoundError(f'The export folder is no longer available: {folder}')
            opened=external_programs.open_folder(folder,self.app.win.get_display().get_app_launch_context())
            if opened is False:raise RuntimeError('The system did not accept the folder request.')
        except Exception as error:self.set_notice(f'Could not open the folder: {error}',error=True)
        else:self.set_notice('')
