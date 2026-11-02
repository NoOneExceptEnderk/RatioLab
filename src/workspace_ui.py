# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Technical workspace composition. Geometry and file operations live in app.py."""
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, Pango
import gui_workflow
import motion_controls
from preview3d import Preview3D
from math import cos, sin, hypot, atan2, pi

# Colors are shared by the workspace, its dialogs and popovers. The light
# palette follows the preserved initial web theme without changing the layout.
THEMES = ('dark', 'light')
_PALETTES = {
    'dark': {
        'window': '#1d2229',
        'text': '#e9eef4',
        'muted': '#acb9c9',
        'accent': '#7cc8c8',
        'on_accent': '#102a2c',
        'line': '#38414d',
        'surface': '#242b34',
        'hover': '#303a46',
        'focus': '#9bd8d8',
        'field_label': '#dce4ed',
        'input': '#151b22',
        'active': '#29343e',
        'selected': '#30434a',
        'preview': '#11161d',
        'preview_state': '#253642',
        'preview_text': '#cde4e8',
        'preview_line': '#405465',
        'error_bg': '#382623',
        'error': '#ffb1a5',
        'error_line': '#9b6257',
        'number': '#f0f6fb',
        'warning_bg': '#302a20',
        'warning_line': '#504534',
        'invalid_line': '#704940',
        'warning': '#efbf79',
        'derived': '#27313b',
        'field_error': '#f1a596',
        'io_line': '#718499',
        'io_input': '#e9a45d',
        'io_output': '#74c8a4',
        'io_result': '#addbdd',
        'status': '#a9cdbb',
        'trough': '#3c4754',
        'slider': '#d2dce6',
    },
    'light': {
        'window': '#f7f9fa',
        'text': '#263846',
        'muted': '#627380',
        'accent': '#aa633d',
        'on_accent': '#ffffff',
        'line': '#d6dfe5',
        'surface': '#ffffff',
        'hover': '#eef3f5',
        'focus': '#a15b35',
        'field_label': '#354c5b',
        'input': '#ffffff',
        'active': '#e9eef1',
        'selected': '#ead8cb',
        'preview': '#e9eef1',
        'preview_state': '#f7f9fa',
        'preview_text': '#425565',
        'preview_line': '#bbcbd5',
        'error_bg': '#fbe9e5',
        'error': '#9b362b',
        'error_line': '#bc7368',
        'number': '#122638',
        'warning_bg': '#f8edda',
        'warning_line': '#d7b98d',
        'invalid_line': '#bc7368',
        'warning': '#805518',
        'derived': '#edf2f5',
        'field_error': '#9b362b',
        'io_line': '#718499',
        'io_input': '#a15b35',
        'io_output': '#28775b',
        'io_result': '#466777',
        'status': '#37694f',
        'trough': '#c6d2da',
        'slider': '#263846',
    },
}

_CSS_TEMPLATE = '''
window.reducers { background: @rl_window; color: @rl_text; font-size: 14px; }
/* Native themes can set foregrounds on child nodes (notably spinbutton text).
   Reset those nodes to inheritance before applying our semantic colors. */
.reducers * { color: inherit; }
.reducers button:disabled, .reducers entry:disabled, .reducers spinbutton:disabled,
.reducers dropdown:disabled, .reducers checkbutton:disabled, .reducers textview:disabled { color: @rl_muted; }
.reducers selection { background: @rl_accent; color: @rl_on_accent; }
.reducers checkbutton check { background: @rl_input; border-color: @rl_line; box-shadow: none; }
.reducers checkbutton check:checked { background: @rl_accent; color: @rl_on_accent; border-color: @rl_accent; }
.reducers checkbutton:focus-visible check { outline: 2px solid @rl_focus; outline-offset: 1px; }
.reducers separator { background: @rl_line; }
.reducers paned > separator { background: @rl_line; background-image: none; box-shadow: none; border: 0; padding: 0; margin: 0; min-width: 1px; min-height: 1px; }
.reducers headerbar { background: @rl_window; border-bottom: 1px solid @rl_line; box-shadow: none; min-height: 48px; }
.reducers headerbar windowcontrols button { background: transparent; border: 0; box-shadow: none; }
.reducers button { background: @rl_surface; color: @rl_text; border: 1px solid @rl_line; border-radius: 5px; box-shadow: none; min-height: 28px; padding: 4px 10px; }
.reducers button:hover { background: @rl_hover; }
.reducers button.flat { background: transparent; border-color: transparent; }
.reducers button:focus-visible, .reducers entry:focus, .reducers spinbutton:focus-within { outline: 2px solid @rl_focus; outline-offset: 1px; }
.reducers button:disabled { opacity: 0.5; }
 .reducers .studio-header { min-height: 60px; padding: 0 15px; border-bottom: 1px solid @rl_line; background: @rl_window; }
.reducers .studio-header button { font-size: 14px; line-height: 1.45em; min-height: 20px; padding: 6px 9px; }
.reducers .studio-header menubutton > button { font-size: 14px; }
.reducers .studio-project > button { background: transparent; border-color: transparent; }
.reducers .studio-header windowcontrols button { background: transparent; border: 0; box-shadow: none; min-height: 28px; padding: 4px; }
.reducers .brand-name { font-weight: 500; }
.reducers .studio-header .document-name { font-weight: 400; }
.reducers .studio-header .muted { font-size: 11px; }
.reducers .studio-toolbar { padding: 7px 12px; border-bottom: 1px solid @rl_line; }
.reducers .studio-toolbar button { border-color: transparent; font-size: 14px; min-height: 24px; padding: 4px 9px; }
.reducers .family-chip { color: @rl_muted; font-size: 11px; line-height: 1.45em; padding: 3px 6px; margin-left: 7px; border: 1px solid @rl_line; border-radius: 4px; }
.reducers .eyebrow { color: @rl_muted; font-size: 11px; letter-spacing: 1px; padding-bottom: 3px; }
.reducers .sidebar dropdown > button { font-size: 12px; line-height: 1.45em; min-height: 24px; padding: 3px 7px; }
.reducers .sidebar spinbutton { font-size: 12px; line-height: 1.45em; }
.reducers .sidebar spinbutton.parameter-input { min-height: 32px; }
.reducers .sidebar spinbutton.parameter-input button { min-width: 12px; padding: 0; }
.reducers .sidebar spinbutton.parameter-input text { padding-left: 9px; padding-right: 23px; }
.reducers .sidebar spinbutton.parameter-input:focus-within text { padding-right: 19px; }
.reducers .sidebar .parameter-heading { font-size: 12px; font-weight: 400; }
.reducers .sidebar button.model-restore { font-size: 12px; line-height: 1.45em; }
.reducers .sidebar .field-label { line-height: 1.45em; }
.reducers .sidebar .geometry-disclosure > box > title label { line-height: 1.45em; }
.reducers .sidebar .geometry-disclosure > box > title { line-height: 1.45em; padding: 11px 0; font-size: 12px; font-weight: 400; border-top: 1px solid @rl_line; border-radius: 0; }
.reducers .sidebar .geometry-disclosure > box > title > expander { min-width: 10px; min-height: 10px; -gtk-icon-size: 10px; }
.reducers .sidebar .geometry-disclosure { margin-top: 13px; }
.reducers .sidebar .primary-geometry { padding-bottom: 2px; }
.reducers .model-picker .step-title { font-weight: 500; line-height: 1.45em; }
.reducers .parameter-pair { padding-bottom: 0; }
.reducers .sidebar { background: @rl_window; }
.reducers .model-picker { padding: 6px 14px 0; }
.reducers .model-picker .field-label { line-height: 1.15em; }
.reducers .model-picker dropdown > button { min-height: 18px; padding: 1px 7px; }
.reducers .field-label { color: @rl_muted; font-size: 12px; }
.reducers .muted, .reducers .result-title, .reducers .result-detail { color: @rl_muted; font-size: 12px; }
.reducers .step-title, .reducers .parameter-heading { font-weight: 600; font-size: 14px; }
.reducers .action-title { font-weight: 600; color: @rl_text; }
.reducers dropdown > button { background: @rl_input; border: 1px solid @rl_line; border-radius: 4px; min-height: 31px; padding: 3px 8px; }
.reducers spinbutton { background: @rl_input; border: 1px solid @rl_line; border-radius: 4px; min-height: 30px; }
.reducers spinbutton button { background: transparent; border: 0; min-width: 16px; padding: 2px; }
.reducers entry { background: @rl_input; color: @rl_text; border: 1px solid @rl_line; border-radius: 4px; min-height: 30px; }
.reducers .page-nav { padding: 7px 14px; border-bottom: 1px solid @rl_line; }
.reducers .page-nav button { background: transparent; border-color: transparent; padding: 4px 3px; font-size: 12px; min-width: 42px; }
.reducers .theme-control { padding: 0 7px; }
.reducers switch.theme-switch { min-width: 32px; min-height: 16px; padding: 2px; border-radius: 12px; border: 1px solid @rl_line; background: @rl_trough; }
.reducers switch.theme-switch:checked { background: @rl_accent; border-color: @rl_accent; }
.reducers switch.theme-switch slider { min-width: 14px; min-height: 14px; margin: 0; border-radius: 50%; background: #ffffff; border: 0; box-shadow: none; }
.reducers.localized-ui .page-nav button { font-size: 11px; }
.reducers .page-nav button.dimensions-tab { min-width: 72px; }
.reducers .page-nav button.assembly-tab { min-width: 59px; }
.reducers .page-nav button:checked { background: @rl_active; box-shadow: inset 0 -2px @rl_accent; }
.reducers .parameter-scroll { padding: 4px 14px 12px; }
.reducers .parameter-group { padding-bottom: 12px; }
.reducers .sidebar-actions { padding: 9px 12px; border-top: 1px solid @rl_line; }
.reducers .sidebar-actions button { font-size: 12px; }
.reducers expander > title { padding: 9px 0; font-weight: 500; font-size: 13px; }
.reducers button.primary, .reducers menubutton.primary > button { background: @rl_accent; color: @rl_on_accent; border-color: @rl_accent; font-weight: 600; }
.reducers .viewbar { padding: 0; background: transparent; border: 0; }
.reducers .viewbar button { min-height: 24px; font-size: 14px; padding: 4px 10px; }
.reducers .viewbar button:checked { background: @rl_selected; border-color: @rl_accent; }
.reducers .viewbar button:checked, .reducers .viewbar button:checked label { color: @rl_accent; }
.reducers .viewbar checkbutton { font-size: 12px; }
.reducers .preview-frame { background: @rl_preview; }
.reducers .preview-state { background: @rl_preview_state; color: @rl_preview_text; border: 1px solid @rl_preview_line; border-radius: 4px; padding: 5px 9px; font-size: 12px; }
.reducers .preview-state.invalid { background: @rl_error_bg; color: @rl_error; border-color: @rl_error_line; }
.reducers .playback-bar { padding: 6px 14px; border-top: 1px solid @rl_line; border-bottom: 1px solid @rl_line; }
.reducers .playback-bar button { font-size: 14px; line-height: 1.45em; min-height: 20px; padding: 6px 9px; }
.reducers .playback-bar > box > label { font-size: 11px; line-height: 1.45em; }
.reducers .playback-bar.enlarged-transport button { padding-top: 3px; padding-bottom: 3px; }
.reducers .playback-bar.compact-transport { padding-top: 0; padding-bottom: 0; }
.reducers .playback-bar.compact-transport button.motion-connections { font-size: 12px; }
.reducers .playback-bar entry { font-size: 12px; line-height: 1.45em; min-height: 18px; padding: 5px 7px; }
.reducers .playback-bar entry { font-variant-numeric: tabular-nums; }
.reducers .results-strip { background: @rl_surface; border-top: 1px solid @rl_line; padding: 10px 18px; }
.reducers .metric-card { padding: 0 20px; background: transparent; border-radius: 0; border-left: 1px solid @rl_line; }
.reducers .results-strip flowboxchild:first-child .metric-card { padding-left: 0; border-left: 0; }
.reducers .result-number { color: @rl_number; font-size: 28px; font-weight: 500; line-height: 1.2em; }
.reducers .result-small { color: @rl_number; font-size: 20px; font-weight: 500; }
.reducers .result-unit { color: @rl_muted; font-size: 15px; }
.reducers .result-title { font-size: 13px; line-height: 1.45em; margin-bottom: 0; }
.reducers .result-detail { font-size: 11px; line-height: 1.45em; margin-top: 0; }
.reducers .results-strip > flowboxchild { padding: 0; }
.reducers .metric-card:disabled { opacity: 0.5; }
.reducers .warning-bar { background: @rl_warning_bg; border-top: 1px solid @rl_warning_line; padding: 7px 14px; }
.reducers .warning-bar.invalid { background: @rl_error_bg; border-color: @rl_invalid_line; }
.reducers .warning-bar.invalid .study { color: @rl_error; }
.reducers .study { color: @rl_warning; font-size: 12px; }
.reducers .error { color: @rl_error; font-size: 12px; }
.reducers .derived { background: @rl_derived; }
.reducers .derived-output { background: @rl_input; border: 1px solid @rl_line; border-left: 2px solid @rl_accent; border-radius: 4px; padding: 4px 8px; font-size: 16px; min-width: 42px; }
.reducers .field-error { border-color: @rl_field_error; }
.reducers .field-feedback { padding: 2px 0 3px; }
.reducers .io-role { padding: 6px 7px; background: @rl_surface; border-left: 2px solid @rl_io_line; }
.reducers .io-input { border-left-color: @rl_io_input; }
.reducers .io-output { border-left-color: @rl_io_output; }
.reducers .io-value { font-weight: 500; }
.reducers .io-result { color: @rl_io_result; font-size: 12px; }
.reducers .footer { padding: 8px 15px; border-top: 1px solid @rl_line; }
.reducers .footer button { font-size: 12px; }
.reducers .status { color: @rl_status; font-size: 12px; }
.reducers .status.error { color: @rl_error; }
.reducers .connected { color: @rl_status; }
.reducers .motion-input-error { color: @rl_error; font-size: 12px; }
.reducers popover > contents { background: @rl_window; color: @rl_text; border: 1px solid @rl_line; border-radius: 7px; padding: 12px; }
.reducers popover list, .reducers popover listview { background: @rl_input; color: @rl_text; }
.reducers popover row:selected { background: @rl_selected; color: @rl_text; }
.reducers popover row:hover, .reducers popover modelbutton:hover { background: @rl_hover; }
.reducers progressbar trough { background: @rl_trough; }
.reducers progressbar progress { background: @rl_accent; border-color: @rl_accent; }
.reducers .tool-dock, .reducers .view-panel { background: alpha(@rl_surface, 0.89); border: 1px solid @rl_line; border-radius: 10px; }
.reducers .view-panel { padding: 10px; }
.reducers .cad-split { border-spacing: 0; border: 1px solid @rl_line; border-radius: 6px; background: @rl_surface; }
.reducers .studio-header .cad-split button { font-size: 12px; line-height: 1.45em; min-height: 18px; padding: 7px 9px; border: 0; border-radius: 0; background: transparent; }
.reducers .studio-header .cad-split menubutton > button { border-left: 1px solid @rl_line; padding: 7px; }
.reducers .studio-header .cad-split button:hover { background: @rl_hover; }
.reducers .cad-popover > contents { background: @rl_surface; border: 1px solid @rl_line; border-radius: 9px; padding: 12px; }
.reducers .cad-popover .cad-menu-title { font-size: 14px; font-weight: 500; line-height: 1.45em; margin-bottom: 3px; }
.reducers .cad-popover .cad-connection-row { padding: 10px 0; border-top: 1px solid @rl_line; }
.reducers .cad-popover .cad-connection-name { font-size: 14px; line-height: 1.45em; }
.reducers .cad-popover .cad-connection-status { font-size: 11px; line-height: 1.45em; color: @rl_muted; }
.reducers .cad-popover .cad-connected { color: @rl_accent; }
.reducers .cad-popover.cad-popover button { font-size: 12px; line-height: 1.45em; min-height: 18px; padding: 6px 9px; border: 1px solid @rl_line; border-radius: 6px; background: transparent; }
.reducers .cad-popover .cad-connection-row button { font-size: 14px; }
.reducers .cad-popover button.flat { border-color: transparent; }
.reducers .cad-popover button:hover { background: @rl_hover; }
.reducers .cad-popover .cad-menu-footer { padding-top: 8px; border-top: 1px solid @rl_line; }
.reducers .cad-popover .cad-menu-footer button { padding: 6px 3px; }
.reducers .tool-nav { padding: 13px 14px; border-bottom: 1px solid @rl_line; }
.reducers .tool-nav button { padding: 3px 7px; font-size: 12px; }
.reducers .overlay-category { color: @rl_muted; font-size: 11px; }
.reducers .tool-nav .step-title { font-size: 14px; font-weight: 500; }
.reducers .tool-chooser button { background: transparent; border: 0; min-height: 20px; padding: 10px; font-size: 14px; line-height: 1.45em; }
.reducers .tool-chooser button:hover { background: @rl_active; }
.reducers .tool-nav button:checked { border-color: @rl_accent; background: @rl_selected; }
.reducers .tool-dock list { background: @rl_input; border: 1px solid @rl_line; border-radius: 4px; }
.reducers .tool-dock row { padding: 8px; border-bottom: 1px solid @rl_line; }
.reducers .tool-dock row:selected { background: @rl_selected; color: @rl_text; }
.reducers textview text { background: @rl_input; color: @rl_text; }
.reducers .tool-dock flowboxchild { padding: 0; }
.reducers .tool-dock .sidebar-actions { padding: 3px 12px; }
.reducers.enlarged-text .results-strip { padding-top: 10px; padding-bottom: 10px; }
.reducers .measurement { background: @rl_input; border: 1px solid @rl_line; border-radius: 5px; padding: 10px; font-variant-numeric: tabular-nums; }
.reducers .document-name { font-weight: 600; }
.reducers .playback-bar scale { padding: 4px 0; min-height: 18px; }
.reducers .playback-bar scale trough { min-height: 4px; background: @rl_trough; border: 0; box-shadow: none; }
.reducers .playback-bar scale highlight { background: @rl_accent; border-color: @rl_accent; box-shadow: none; }
.reducers .playback-bar scale slider { min-width: 18px; min-height: 18px; margin: -7px 0; padding: 0; background: @rl_accent; border-color: @rl_accent; box-shadow: none; }
.reducers .explode-control scale trough { min-height: 4px; background: @rl_trough; border-color: @rl_trough; box-shadow: none; }
.reducers .explode-control scale highlight { background: @rl_accent; border-color: @rl_accent; box-shadow: none; }
.reducers .explode-control scale slider { min-width: 18px; min-height: 18px; margin: -7px 0; padding: 0; background: @rl_slider; border-color: @rl_slider; box-shadow: none; }
'''

class StatusLabel(Gtk.Label):
    """Full text remains accessible; a tooltip is useful only after ellipsis."""
    def do_query_tooltip(self,x,y,keyboard_mode,tooltip):
        if self.get_layout().is_ellipsized():
            tooltip.set_text(self.get_text())
            return True
        return False


def workspace_glyph(name, color_source):
    """Self-contained outline symbols, available in frozen builds without themes."""
    area=Gtk.DrawingArea(content_width=16,content_height=16)
    area.glyph_name=name
    def draw(widget,cr,width,height):
        name=widget.glyph_name
        color_widget=color_source.get_first_child() if isinstance(color_source,Gtk.MenuButton) else color_source
        color=color_widget.get_style_context().get_color()
        alpha=color.alpha*(.5 if name in ("undo","redo","folder","plug","download") and not color_source.get_sensitive() else 1)
        cr.set_source_rgba(color.red,color.green,color.blue,alpha)
        cr.scale(width/24,height/24)
        cr.set_line_width(2)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        def line(x1,y1,x2,y2):
            cr.move_to(x1,y1);cr.line_to(x2,y2)
        def arc(radius,x,y,large=False,sweep=True):
            # SVG circular endpoint arc, used by the reference outline paths.
            start_x,start_y=cr.get_current_point()
            dx,dy=(start_x-x)/2,(start_y-y)/2
            square=dx*dx+dy*dy
            radius=max(radius,square**.5)
            factor=(max(0,(radius*radius-square)/square))**.5
            if large==sweep:factor=-factor
            cx,cy=(start_x+x)/2+factor*dy,(start_y+y)/2-factor*dx
            first,last=atan2(start_y-cy,start_x-cx),atan2(y-cy,x-cx)
            if sweep:
                while last<first:last+=2*pi
                cr.arc(cx,cy,radius,first,last)
            else:
                while last>first:last-=2*pi
                cr.arc_negative(cx,cy,radius,first,last)
        if name=='globe':
            cr.arc(12,12,10,0,2*pi)
            cr.new_sub_path()
            cr.save();cr.translate(12,12);cr.scale(.45,1);cr.arc(0,0,10,0,2*pi);cr.restore()
            line(2,12,22,12)
        elif name=='sliders':
            for coords in ((3,4,10,4),(14,4,21,4),(3,12,8,12),(12,12,21,12),
                           (3,20,12,20),(16,20,21,20),(14,2,14,6),(8,10,8,14),(16,18,16,22)):
                line(*coords)
        elif name=='wrench':
            cr.move_to(14.7,6.3)
            cr.curve_to(14.31,6.69,14.31,7.31,14.7,7.7)
            cr.line_to(16.3,9.3)
            cr.curve_to(16.69,9.69,17.31,9.69,17.7,9.3)
            cr.line_to(21.47,5.53)
            cr.curve_to(23.01,9.93,17.93,15.01,13.53,13.47)
            cr.line_to(6.62,20.38)
            cr.curve_to(5.79,21.21,4.45,21.21,3.62,20.38)
            cr.curve_to(2.79,19.55,2.79,18.21,3.62,17.38)
            cr.line_to(10.53,10.47)
            cr.curve_to(8.99,6.07,14.07,.99,18.47,2.53)
            cr.close_path()
        elif name in ('undo','redo'):
            if name=='redo':cr.translate(24,0);cr.scale(-1,1)
            cr.move_to(8,4);cr.line_to(3,9);cr.line_to(8,14)
            cr.move_to(3,9);cr.line_to(14,9)
            arc(6,14,21)
        elif name=='folder':
            cr.move_to(3,7);cr.line_to(3,5);cr.line_to(9,5);cr.line_to(11,7);cr.line_to(20,7);cr.line_to(20,9)
            cr.move_to(3,9);cr.line_to(22,9);cr.line_to(19,20);cr.line_to(2,20);cr.close_path()
        elif name=='plug':
            line(8,3,10,7);line(16,3,14,7)
            cr.move_to(6,7);cr.line_to(18,7);cr.line_to(18,11)
            arc(6,6,11)
            cr.close_path()
            line(12,17,12,21)
        elif name=='download':
            line(12,3,12,15)
            cr.move_to(8,11);cr.line_to(12,15);cr.line_to(16,11)
            cr.move_to(4,16);cr.line_to(4,21);cr.line_to(20,21);cr.line_to(20,16)
        elif name=='list':
            for y in (5,12,19):
                cr.rectangle(3,y-1,2,2);line(9,y,21,y)
        elif name=='search':
            cr.arc(10,10,6,0,2*pi);line(15,15,21,21)
        elif name=='warning':
            cr.move_to(12,3);cr.line_to(22,21);cr.line_to(2,21);cr.close_path()
            line(12,9,12,14);line(12,17,12,17.1)
        elif name=='ruler':
            cr.move_to(3,17);cr.line_to(17,3);cr.line_to(21,7);cr.line_to(7,21);cr.close_path()
            for coords in ((8,12,11,15),(12,8,15,11),(16,4,19,7)):line(*coords)
        elif name=='backlash':
            line(3,5,3,19);line(21,5,21,19);line(7,12,17,12)
            cr.move_to(10,9);cr.line_to(7,12);cr.line_to(10,15)
            cr.move_to(14,9);cr.line_to(17,12);cr.line_to(14,15)
        elif name=='report':
            cr.move_to(14,3);cr.line_to(5,3);cr.line_to(5,21);cr.line_to(19,21);cr.line_to(19,8);cr.close_path()
            cr.move_to(14,3);cr.line_to(14,8);cr.line_to(19,8)
            line(8,12,16,12);line(8,16,14,16)
        elif name=='notes':
            cr.arc(12,12,9,0,2*pi);line(12,11,12,17);line(12,7,12,7.1)
        elif name=='play':
            cr.move_to(7,4);cr.line_to(20,12);cr.line_to(7,20);cr.close_path()
        elif name=='pause':
            cr.rectangle(6,4,4,16);cr.rectangle(14,4,4,16)
        elif name=='reset':
            cr.move_to(3,10);cr.line_to(3,4);cr.line_to(9,4)
            cr.move_to(3,4);cr.curve_to(8,-1,20,3,21,11);cr.curve_to(22,20,9,24,4,16)
        elif name=='io':
            line(3,7,21,7);line(3,17,21,17)
            cr.move_to(17,3);cr.line_to(21,7);cr.line_to(17,11)
            cr.move_to(7,13);cr.line_to(3,17);cr.line_to(7,21)
        elif name=='settings':
            line(20,7,11,7);line(14,17,5,17)
            cr.new_sub_path();cr.arc(17,17,3,0,2*pi)
            cr.new_sub_path();cr.arc(7,7,3,0,2*pi)
        elif name=='help':
            cr.arc(12,12,10,0,2*pi)
            cr.new_sub_path()
            cr.move_to(9.09,9)
            arc(3,14.92,10)
            cr.curve_to(14.92,12,11.92,13,11.92,13)
            line(11.92,17,11.93,17)
        elif name=='gear':
            for i in range(32):
                angle=-pi/2+i*pi/16
                radius=10 if i%4<2 else 7.5
                x,y=12+radius*cos(angle),12+radius*sin(angle)
                if i==0:cr.move_to(x,y)
                else:cr.line_to(x,y)
            cr.close_path()
            cr.new_sub_path();cr.arc(12,12,3,0,2*pi)
        elif name=='appearance':
            line(12,2,12,4)
            cr.move_to(13,8.129)
            arc(6,5.873,11,large=True)
            arc(4,13,8.129,sweep=False)
            cr.close_path()
            line(19,3,17.5,4.5)
            line(20,10,22,10)
        cr.stroke()
    area.set_draw_func(draw)
    return area


def decorate_action(button, icon_name, *, vector=False):
    """Add a native symbolic icon while preserving the action and label API."""
    parent=button.get_parent()
    previous=button.get_prev_sibling()
    parent.remove(button)
    wrapper=Gtk.Overlay()
    wrapper.set_child(button)
    image=workspace_glyph(icon_name,button) if vector else Gtk.Image.new_from_icon_name(icon_name)
    if not vector:image.set_pixel_size(14)
    button.workspace_icon=image
    image.set_halign(Gtk.Align.START)
    image.set_valign(Gtk.Align.CENTER)
    image.set_margin_start(10)
    image.set_can_target(False)
    wrapper.add_overlay(image)
    def inset(widget):
        if isinstance(widget,Gtk.Label) and widget.get_text()==button.get_label():
            widget.set_margin_start(22 if vector else 20)
            return True
        child=widget.get_first_child()
        while child:
            if inset(child):return True
            child=child.get_next_sibling()
        return False
    inset(button)
    image.set_sensitive(button.get_sensitive())
    button.connect('notify::sensitive',lambda *_: image.set_sensitive(button.get_sensitive()))
    if vector:button.connect('state-flags-changed',lambda *_: image.queue_draw())
    wrapper.set_visible(button.get_visible())
    button.connect('notify::visible',lambda *_: wrapper.set_visible(button.get_visible()))
    parent.insert_child_after(wrapper,previous)
    return wrapper


def theme_css(theme='dark', text_scale=0):
    """Build one complete palette so scaling never restores a previous theme."""
    import re
    theme = theme if theme in THEMES else 'dark'
    factor = (1, 1.25, 1.5)[text_scale]
    definitions = ''.join(f'@define-color rl_{key} {value};\n'
                          for key, value in _PALETTES[theme].items())
    scaled = re.sub(r'font-size: (\d+)px',
                    lambda match: f'font-size: {int(match[1])*factor:g}px',
                    _CSS_TEMPLATE)
    return (definitions + scaled).encode('utf-8')


# Preserve the original public constant for consumers of the default dark style.
CSS = theme_css()


def apply_theme(app):
    """Apply display preferences without refreshing geometry or document state."""
    scale = app.text_size.get_selected() if hasattr(app, 'text_size') else 0
    if scale:app.win.add_css_class('enlarged-text')
    else:app.win.remove_css_class('enlarged-text')
    app.workspace_style.load_from_data(theme_css(app.workspace_theme, scale))
    if hasattr(app, 'canvas'):
        app.canvas.set_theme(app.workspace_theme)
    if hasattr(app, 'axes'):
        app.axes.queue_draw()


def change_theme(app, widget):
    from app_paths import save_preferences
    app.workspace_theme = THEMES[widget.get_selected()]
    app.theme_switch.set_active(app.workspace_theme == 'light')
    app.theme_switch.set_tooltip_text('Light' if app.workspace_theme == 'light' else 'Dark')
    app.workspace_preferences['theme'] = app.workspace_theme
    apply_theme(app)
    try:
        save_preferences(legacy_root=app.BASE, theme=app.workspace_theme)
        app.theme_error.set_visible(False)
    except OSError:
        # Keep the usable session preference even on a read-only user profile.
        app.theme_error.set_visible(True)
        app.status_text('Changed for this session. Could not save preference.')

def margins(widget, value):
    for setter in (widget.set_margin_start, widget.set_margin_end,
                   widget.set_margin_top, widget.set_margin_bottom):
        setter(value)


def install_axes(app, overlay):
    """Project the coordinate axes using the same orbit as the OpenGL view."""
    axes = Gtk.DrawingArea(width_request=86, height_request=86)
    axes.set_halign(Gtk.Align.END)
    axes.set_valign(Gtk.Align.END)
    axes.set_can_target(False)
    margins(axes, 12)
    def draw(widget, cr, width, height):
        cr.translate(width/2, height/2)
        cr.set_source_rgb(*app.canvas.palette['axes'])
        cr.set_line_width(1.4)
        cr.set_font_size(12)
        c, s = cos(app.canvas.yaw), sin(app.canvas.yaw)
        a, b = cos(app.canvas.tilt), sin(app.canvas.tilt)
        for name, (x, y, z) in zip('XYZ', ((1,0,0), (0,1,0), (0,0,1))):
            x, y = c*x-s*y, s*x+c*y
            x, y = 26*x, -26*(a*y-b*z)
            cr.move_to(0, 0)
            cr.line_to(x, y)
            cr.stroke()
            if hypot(x, y)>4:
                angle = atan2(y, x)
                for delta in (-.45, .45):
                    cr.move_to(x, y)
                    cr.line_to(x-5*cos(angle+delta), y-5*sin(angle+delta))
                cr.stroke()
            cr.move_to(x+4, y-4)
            cr.show_text(name)
    axes.set_draw_func(draw)
    app.axes = axes
    app.canvas.connect('view-changed', lambda *_: axes.queue_draw())
    overlay.add_overlay(axes)


def build(app, labels):
    from app_paths import APP_ID, resource_path, load_preferences
    brand_dir = resource_path('branding')
    # A flat PNG lookup has no registered sizes, so GTK cannot populate native
    # window icons. Keep a standard hicolor theme for source, wheels and bundles.
    Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(resource_path('icons')))
    Gtk.Window.set_default_icon_name(APP_ID)
    app.win = Gtk.ApplicationWindow(application=app, title='RatioLab · Gears & reducers')
    app.win.set_icon_name(APP_ID)
    app.win.add_css_class('reducers')
    app.win.set_default_size(1600, 1000)
    provider = Gtk.CssProvider()
    saved_theme = load_preferences(legacy_root=app.BASE).get('theme', 'dark')
    app.workspace_theme = saved_theme if saved_theme in THEMES else 'dark'
    provider.load_from_data(theme_css(app.workspace_theme))
    app.workspace_style = provider
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    app.win.set_child(root)
    header = Gtk.Box(spacing=12, css_classes=['studio-header'])
    header_handle = Gtk.WindowHandle()
    header_handle.set_child(header)
    brand = Gtk.Box(spacing=8)
    logo = Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(str(brand_dir/'ratiolab-icon.png'))))
    logo.set_pixel_size(20)
    brand.append(logo)
    brand.append(Gtk.Label(label='RatioLab', css_classes=['brand-name']))
    header.append(brand)
    title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
    app.project_title = Gtk.Label(label='Untitled', xalign=0, max_width_chars=28, ellipsize=Pango.EllipsizeMode.MIDDLE, css_classes=['document-name'])
    def project_caption(label, *_):
        value = label.get_text()
        if value.startswith('RatioLab · '):label.set_text(value[len('RatioLab · '):])
    app.project_title.connect('notify::label', project_caption)
    title_box.append(app.project_title)
    app.document_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE,
                                  max_width_chars=40, css_classes=['muted'])
    title_box.append(app.document_label)
    header.append(title_box)
    project_menu = Gtk.MenuButton(label='Project', css_classes=['flat','studio-project'])
    project_menu.set_tooltip_text('Project files and recent documents')
    project_popup = Gtk.Popover()
    project_menu.set_popover(project_popup)
    app.project_menu = project_menu
    commands = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    project_popup.set_child(commands)
    for title, callback in [('New project', app.new_project), ('Open project…', app.load_dialog),
                            ('Save', app.save_dialog), ('Save As…', app.save_as_dialog),
                            ('Recent projects…', app.show_recent)]:
        button = Gtk.Button(label=title)
        button.connect('clicked', lambda b, fn=callback: (project_popup.popdown(), fn(b)))
        commands.append(button)
        app.file_buttons.append(button)
    header.append(project_menu)
    # Existing header consumers pack actions from right to left. Keep that
    # contract while letting the project name use the available flexible space.
    def pack_header_action(widget):
        widget.set_valign(Gtk.Align.CENTER)
        anchor=project_menu
        while anchor.get_parent() is not header:anchor=anchor.get_parent()
        header.insert_child_after(widget, anchor)
    header.pack_end = pack_header_action
    gui_workflow.install_exports(app)
    app.export_menu.set_label("Export")
    header.pack_end(app.export_menu)
    gui_workflow.install_cad(app)
    app.cad_split.set_overflow(Gtk.Overflow.HIDDEN)
    header.pack_end(app.cad_split)
    from update_ui import Controller
    app.updates = Controller(app, header)
    release_notes = Gtk.Button(label='Release notes and updates…')
    release_notes.connect('clicked', lambda *_: (project_popup.popdown(), app.updates.show(manual=True)))
    commands.append(release_notes)
    window_controls = Gtk.WindowControls(side=Gtk.PackType.END)
    header.append(window_controls)
    child=header.get_first_child()
    while child:
        child.set_valign(Gtk.Align.CENTER)
        child=child.get_next_sibling()
    decorate_action(project_menu,'folder',vector=True)
    decorate_action(app.cad_action,'plug',vector=True)
    decorate_action(app.export_menu,'download',vector=True)
    app.win.set_titlebar(header_handle)
    secondary = Gtk.Box(spacing=3, css_classes=['studio-toolbar'])
    app.secondary_toolbar = secondary
    root.append(secondary)
    for icon, title, name, callback, hint in [
            ('edit-undo-symbolic', 'Undo', 'undo_button', app.undo_project, 'Undo · Ctrl+Z'),
            ('edit-redo-symbolic', 'Redo', 'redo_button', app.redo_project, 'Redo · Ctrl+Shift+Z / Ctrl+Y')]:
        button = Gtk.Button(label=title, css_classes=['flat'])
        button.set_tooltip_text(hint)
        button.connect('clicked', callback)
        secondary.append(button)
        setattr(app, name, button)
    app.family_chip = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, max_width_chars=45, css_classes=['family-chip'])
    app.family_chip.set_valign(Gtk.Align.CENTER)
    secondary.append(app.family_chip)
    secondary.append(Gtk.Box(hexpand=True))
    theme_control = Gtk.Box(spacing=7, css_classes=['theme-control'])
    theme_control.set_valign(Gtk.Align.CENTER)
    theme_icon = Gtk.Label(label='◐')
    theme_icon.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)
    theme_control.append(theme_icon)
    app.theme_caption = Gtk.Label(label='Theme')
    theme_control.append(app.theme_caption)
    app.theme_switch = Gtk.Switch(active=app.workspace_theme == 'light', css_classes=['theme-switch'])
    app.theme_switch.set_valign(Gtk.Align.CENTER)
    app.theme_switch.update_property([Gtk.AccessibleProperty.LABEL], ['Theme'])
    app.theme_caption.connect('notify::label', lambda label, *_:
        app.theme_switch.update_property([Gtk.AccessibleProperty.LABEL], [label.get_text()]))
    app.theme_switch.set_tooltip_text('Light' if app.workspace_theme == 'light' else 'Dark')
    theme_control.append(app.theme_switch)
    secondary.append(theme_control)
    # Compatibility alias used to move focus away from an edited parameter.
    app.appearance_button = app.theme_switch
    app.language_menu = Gtk.MenuButton(label='Language', css_classes=['flat'])
    app.language_popover = Gtk.Popover()
    app.language_menu.set_popover(app.language_popover)
    secondary.append(app.language_menu)
    decorate_action(app.language_menu,'globe',vector=True)
    for button,icon in ((app.undo_button,'undo'), (app.redo_button,'redo')):
        decorate_action(button,icon,vector=True)
    content = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
    content.set_wide_handle(False)
    content.set_position(230)
    content.set_shrink_start_child(False)
    content.set_shrink_end_child(False)
    content.set_resize_start_child(False)
    content.set_vexpand(True)
    app.workspace_paned = content
    root.append(content)
    left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['sidebar'])
    app.parameter_panel = left
    left.set_size_request(230, -1)
    content.set_start_child(left)
    picker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, css_classes=['model-picker'])
    left.append(picker)
    app.model_picker = picker
    app.model_dimensions_heading_row = Gtk.Box(spacing=6)
    app.model_dimensions_heading = gui_workflow.text('Family', 'field-label')
    app.model_dimensions_heading.set_hexpand(True)
    app.model_dimensions_heading_row.append(app.model_dimensions_heading)
    picker.append(app.model_dimensions_heading_row)
    from parameter_help_ui import controller as help_controller
    help_controller(app).bind_section(app.model_dimensions_heading, app.model_dimensions_heading_row)
    model_field=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=1)
    picker.append(model_field)
    app.selector = gui_workflow.searchable_dropdown(labels)
    app.selector.set_selected(list(app.families).index(app.family))
    app.selector.connect('notify::selected', app.change_family)
    model_field.append(app.selector)
    app.family_hint = gui_workflow.text('', 'study')
    app.family_hint.set_visible(False)
    picker.append(app.family_hint)
    app.variant_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    app.variant_box.set_margin_top(2)
    app.variant_caption = gui_workflow.text('Tooth type', 'field-label')
    app.variant_box.append(app.variant_caption)
    app.variant_selector = Gtk.DropDown.new_from_strings(['Standard'])
    gui_workflow.compact_dropdown(app.variant_selector)
    app.variant_selector.connect('notify::selected', app.change_variant)
    app.variant_box.append(app.variant_selector)
    picker.append(app.variant_box)
    gui_workflow.install_sections(app, left)
    reset_row = Gtk.Box(spacing=5, css_classes=['sidebar-actions'])
    app.reset_button = Gtk.Button(label='Reset defaults', css_classes=['flat'])
    app.reset_button.connect('clicked', app.reset_defaults)
    app.reset_button.set_tooltip_text('Restore defaults for this model. Undo reset is available afterwards.')
    app.file_buttons.append(app.reset_button)
    commands.append(app.reset_button)
    app.undo_reset = Gtk.Button(label='Undo reset', css_classes=['flat'])
    app.undo_reset.set_visible(False)
    app.undo_reset.connect('clicked', app.undo_defaults)
    app.file_buttons.append(app.undo_reset)
    commands.append(app.undo_reset)
    right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    right.set_hexpand(True)
    content.set_end_child(right)
    toolbar = Gtk.Box(spacing=6, css_classes=['viewbar'])
    app.preview_toolbar = toolbar
    toolbar.set_halign(Gtk.Align.END)
    toolbar.set_valign(Gtk.Align.START)
    margins(toolbar, 13)
    app.canvas = Preview3D()
    app.canvas.set_size_request(320,250)
    app.canvas.set_theme(app.workspace_theme)
    app.view_buttons = {}
    views = Gtk.Box(spacing=4)
    for title, key in [('3D', 'iso'), ('Top', 'top'), ('Front', 'front')]:
        button = Gtk.ToggleButton(label=title)
        if app.view_buttons:
            button.set_group(next(iter(app.view_buttons.values())))
        button.connect('clicked', lambda _, v=key: app.select_view(v))
        views.append(button)
        app.view_buttons[key] = button
    app.view_buttons['iso'].set_active(True)
    app.canvas.connect('view-changed', app.on_view_changed)
    fit = Gtk.Button(label='Fit')
    fit.set_tooltip_text('Fit model and restore the isometric view')
    fit.connect('clicked', lambda _: app.select_view('iso'))
    views.append(fit)
    toolbar.append(Gtk.Box(hexpand=True))
    app.pick_mode = Gtk.DropDown.new_from_strings(['Navigate', 'Select', 'Measure'])
    app.pick_mode.set_selected(1)
    app.pick_mode.set_tooltip_text('Navigate: orbit and zoom. Select: click surfaces; Ctrl/Shift adds. Measure: pick two surface points.')
    visibility = Gtk.ToggleButton(label='View')
    app.view_menu = visibility
    toolbar.append(visibility)
    view_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['view-panel'], visible=False)
    view_panel.set_size_request(340, -1)
    view_panel.set_halign(Gtk.Align.END)
    view_panel.set_valign(Gtk.Align.FILL)
    margins(view_panel, 12)
    view_panel.set_margin_top(60)
    view_head = Gtk.Box(spacing=8)
    view_heading=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=1,hexpand=True)
    view_heading.append(Gtk.Label(label='View',xalign=0,css_classes=['overlay-category']))
    view_heading.append(Gtk.Label(label='View', xalign=0, css_classes=['step-title']))
    view_head.append(view_heading)
    close_view = Gtk.Button(icon_name='window-close-symbolic', css_classes=['flat'])
    close_view.set_tooltip_text('Close View · Escape')
    close_view.connect('clicked', lambda _: visibility.set_active(False))
    view_head.append(close_view)
    view_panel.append(view_head)
    view_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    view_panel.append(view_scroll)
    view_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
    view_scroll.set_child(view_body)
    app.view_panel = view_panel
    view_body.append(Gtk.Label(label='Camera', xalign=0, css_classes=['muted']))
    view_body.append(views)
    view_body.append(Gtk.Label(label='Interaction', xalign=0, css_classes=['muted']))
    view_body.append(app.pick_mode)
    # Keep the existing theme preference API behind the direct on/off control.
    app.theme_selector = Gtk.DropDown.new_from_strings(['Dark', 'Light'])
    app.theme_selector.set_selected(THEMES.index(app.workspace_theme))
    app.theme_error = Gtk.Label(label='Changed for this session. Could not save preference.', visible=False)
    app.theme_selector.connect('notify::selected', lambda widget, *_: change_theme(app, widget))
    app.theme_switch.connect('notify::active', lambda widget, *_:
                             app.theme_selector.set_selected(1 if widget.get_active() else 0))
    # Preserve the saved text scale; the cancelled Settings screen is not exposed.
    app.text_size = Gtk.DropDown.new_from_strings(['100%', '125%', '150%'])
    app.text_size.set_selected((1, 1.25, 1.5).index(app.workspace_preferences['text_scale']))
    app.text_size.connect('notify::selected', lambda *_: apply_theme(app))

    app.view_options = {}
    for key, title in [('support','Supports'), ('housing','Housing'), ('exploded','Exploded'), ('section','Section')]:
        check = Gtk.CheckButton(label=title)
        check.set_tooltip_text('Preview only. Export always uses nominal coordinates and its explicit component scope.')
        check.connect('toggled', app.change_view_options)
        # Keep the old binary API for existing integrations. The continuous
        # slider below is the only visible explosion control.
        if key!='exploded':view_body.append(check)
        app.view_options[key] = check
    view_body.append(Gtk.Separator())
    explode_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,css_classes=['explode-control'])
    explode_title=Gtk.Label(label='Explode',xalign=0)
    explode_box.append(explode_title)
    app.explode_slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0.,1.,.01)
    app.explode_slider.set_digits(2)
    app.explode_slider.set_draw_value(True)
    app.explode_slider.set_size_request(220,-1)
    app.explode_slider.set_hexpand(True)
    app.explode_slider.update_property([Gtk.AccessibleProperty.LABEL],['Explode'])
    app.explode_slider.set_tooltip_text('Preview only · assembled 0 to fully exploded 1. Pauses motion. Exports use nominal coordinates.')
    app.explode_slider.connect('value-changed',app.change_view_options)
    explode_box.append(app.explode_slider)
    explode_box.append(Gtk.Label(label='Preview only · nominal export coordinates',xalign=0,wrap=True,max_width_chars=30,css_classes=['muted']))
    view_body.append(explode_box)
    app.canvas.connect('display-state',lambda *_:app.sync_explosion_control())
    overlay = Gtk.Overlay(css_classes=['preview-frame'])
    overlay.set_child(app.canvas)
    overlay.set_vexpand(True)
    app.viewport_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
    app.viewport_paned.set_start_child(overlay)
    app.viewport_paned.set_shrink_start_child(False)
    app.viewport_paned.set_shrink_end_child(False)
    app.viewport_paned.set_resize_start_child(True)
    right.append(app.viewport_paned)
    app.preview_overlay = overlay
    overlay.add_overlay(view_panel)
    overlay.set_measure_overlay(view_panel, False)
    from workspace_tools import Dock
    app.tools = Dock(app, app.viewport_paned, toolbar)
    decorate_action(visibility,"sliders",vector=True)
    decorate_action(app.tools.menu,"wrench",vector=True)
    def toggle_view(button):
        if button.get_active():
            app.tools.hide()
        view_panel.set_visible(button.get_active())
    visibility.connect('toggled', toggle_view)
    app.empty = Gtk.Label(label='Generating geometry…', css_classes=['preview-state'])
    app.empty.set_halign(Gtk.Align.START)
    app.empty.set_valign(Gtk.Align.START)
    margins(app.empty, 15)
    overlay.add_overlay(app.empty)
    app.hidden_hint = Gtk.Label(label='No visible components · enable Supports or Housing',
                               wrap=True, css_classes=['muted'])
    app.hidden_hint.set_halign(Gtk.Align.CENTER)
    app.hidden_hint.set_valign(Gtk.Align.CENTER)
    app.hidden_hint.set_visible(False)
    overlay.add_overlay(app.hidden_hint)
    install_axes(app, overlay)
    # Keep tools above decorative axes and preview hints.
    for panel in (view_panel, app.tools.box):
        overlay.remove_overlay(panel)
        overlay.add_overlay(panel)
        overlay.set_measure_overlay(panel, False)
    overlay.add_overlay(toolbar)
    overlay.set_measure_overlay(toolbar, False)
    app.workspace_extras = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    right.append(app.workspace_extras)
    playback = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['playback-bar'])
    motion_controls.install(app, playback)
    from interference_ui import Controller
    app.interference = Controller(app, app.tools)
    from combination_search_ui import Controller as SearchController
    app.combination_search = SearchController(app, app.tools)
    from components_ui import Controller as ComponentsController
    app.components = ComponentsController(app, app.tools)
    from gear_measurement_ui import Controller as MeasurementController
    app.gear_measurement = MeasurementController(app, app.tools)
    from backlash_ui import Controller as BacklashController
    app.backlash = BacklashController(app, app.tools)
    # Keep controller construction order for dependencies; present the approved
    # tool order using the same existing action rows and handlers.
    for tool in ('components','search','interference','gear_measurement','backlash'):
        row=app.tools.controllers[tool].button.get_parent()
        app.tools.commands.remove(row)
        app.tools.commands.append(row)
    def pick_mode_changed(*_):
        mode = app.pick_mode.get_selected()
        if mode == 2:
            app.components.open()
        if app.components.window:
            app.components.measure.set_active(mode == 2)
    app.pick_mode.connect('notify::selected', pick_mode_changed)
    app.metric_cards = Gtk.FlowBox(css_classes=['results-strip'])
    app.metric_cards.set_selection_mode(Gtk.SelectionMode.NONE)
    app.metric_cards.set_column_spacing(0)
    app.metric_cards.set_min_children_per_line(3)
    app.metric_cards.set_max_children_per_line(3)
    app.metric_cards.set_homogeneous(True)
    app.workspace_extras.append(app.metric_cards)
    app.workspace_extras.append(playback)
    warning = Gtk.Box(spacing=10, css_classes=['warning-bar'])
    app.warning_bar = warning
    app.study = Gtk.Label(xalign=0, wrap=True, hexpand=True, css_classes=['study'])
    app.study.set_lines(2)
    app.study.set_max_width_chars(85)
    warning.append(app.study)
    details = Gtk.Button(label='Details', css_classes=['flat'])
    details.connect('clicked', app.show_calculations)
    warning.append(details)
    app.warning_details = details
    app.error_reveal = Gtk.Button(label='Go to field', css_classes=['flat'])
    app.error_reveal.connect('clicked', lambda _: gui_workflow.reveal_error(app))
    app.error_reveal.set_visible(False)
    warning.append(app.error_reveal)
    app.workspace_extras.append(warning)
    # Full text stays available through reports and notes, rather than occupying
    # a second permanent results area below the viewport.
    app.metrics = Gtk.Label(selectable=True)
    app.notes = Gtk.Label(selectable=True)
    app.full_results_expander = Gtk.Expander()
    app.results_title = Gtk.Label(label='Results')
    from export_feedback import Controller as ExportFeedback
    app.export_feedback = ExportFeedback(app,root)
    footer = Gtk.Box(spacing=12, css_classes=['footer'])
    app.spinner = Gtk.Spinner()
    footer.append(app.spinner)
    app.status = StatusLabel(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, css_classes=['status'])
    footer.append(app.status)
    app.bom_summary = Gtk.Label(css_classes=['muted'])
    footer.append(app.bom_summary)
    app.live_label = Gtk.Label(label='✓ Geometry generated', css_classes=['muted'])
    # Kept as a state label for status/tooltips; no redundant live-update badge.
    for title, fn in [('Bill of materials', app.show_bom), ('Calculation report', app.show_calculations),
                      ('Model notes', lambda _: gui_workflow.show_report(app, 'Model notes', app.notes.get_text()))]:
        b = Gtk.Button(label=title, css_classes=['flat'])
        b.connect('clicked', fn)
        app.tools.add_action(b)
        app.file_buttons.append(b)
    root.append(footer)
    gui_workflow.install_shortcuts(app)
