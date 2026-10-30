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

CSS = b'''
window.reducers { background: #1d2229; color: #e9eef4; font-size: 14px; }
/* Native themes can set foregrounds on child nodes (notably spinbutton text).
   Reset those nodes to inheritance before applying our semantic colors. */
.reducers * { color: inherit; }
.reducers button:disabled, .reducers entry:disabled, .reducers spinbutton:disabled,
.reducers dropdown:disabled, .reducers checkbutton:disabled, .reducers textview:disabled { color: #acb9c9; }
.reducers selection { background: #7cc8c8; color: #102a2c; }
.reducers headerbar { background: #1d2229; border-bottom: 1px solid #38414d; box-shadow: none; min-height: 48px; }
.reducers headerbar windowcontrols button { background: transparent; border: 0; box-shadow: none; }
.reducers button { background: #242b34; color: #e9eef4; border: 1px solid #38414d; border-radius: 5px; box-shadow: none; min-height: 28px; padding: 4px 10px; }
.reducers button:hover { background: #303a46; }
.reducers button.flat { background: transparent; border-color: transparent; }
.reducers button:focus-visible, .reducers entry:focus, .reducers spinbutton:focus-within { outline: 2px solid #9bd8d8; outline-offset: 1px; }
.reducers button:disabled { opacity: 0.5; }
.reducers .sidebar { background: #1d2229; }
.reducers .model-picker { padding: 18px; border-bottom: 1px solid #38414d; }
.reducers .field-label { color: #dce4ed; font-size: 13px; }
.reducers .muted, .reducers .result-title, .reducers .result-detail { color: #acb9c9; font-size: 12px; }
.reducers .step-title, .reducers .parameter-heading { font-weight: 600; font-size: 14px; }
.reducers .action-title { font-weight: 600; color: #e9eef4; }
.reducers dropdown > button { background: #151b22; border: 1px solid #38414d; border-radius: 4px; min-height: 31px; padding: 3px 8px; }
.reducers spinbutton { background: #151b22; border: 1px solid #38414d; border-radius: 4px; min-height: 30px; }
.reducers spinbutton button { background: transparent; border: 0; min-width: 16px; padding: 2px; }
.reducers entry { background: #151b22; color: #e9eef4; border: 1px solid #38414d; border-radius: 4px; min-height: 30px; }
.reducers .page-nav { padding: 7px 8px; border-bottom: 1px solid #38414d; }
.reducers .page-nav button { background: transparent; border-color: transparent; padding: 5px 9px; font-size: 12px; }
.reducers .page-nav button:checked { background: #29343e; box-shadow: inset 0 -2px #7cc8c8; }
.reducers .parameter-scroll { padding: 16px 18px; }
.reducers .parameter-group { padding-bottom: 12px; }
.reducers .sidebar-actions { padding: 9px 12px; border-top: 1px solid #38414d; }
.reducers .sidebar-actions button { font-size: 12px; }
.reducers expander > title { padding: 9px 0; font-weight: 500; font-size: 13px; }
.reducers button.primary, .reducers menubutton.primary > button { background: #7cc8c8; color: #102a2c; border-color: #7cc8c8; font-weight: 600; }
.reducers .viewbar { padding: 8px 14px; border-bottom: 1px solid #38414d; }
.reducers .viewbar button { min-height: 25px; font-size: 12px; padding: 3px 10px; }
.reducers .viewbar button:checked { background: #30434a; border-color: #7cc8c8; }
.reducers .viewbar checkbutton { font-size: 12px; }
.reducers .preview-frame { background: #11161d; }
.reducers .preview-state { background: #253642; color: #cde4e8; border: 1px solid #405465; border-radius: 4px; padding: 5px 9px; font-size: 12px; }
.reducers .preview-state.invalid { background: #382623; color: #ffb1a5; border-color: #9b6257; }
.reducers .playback-bar { padding: 9px 14px; border-top: 1px solid #38414d; border-bottom: 1px solid #38414d; }
.reducers .playback-bar button { font-size: 13px; }
.reducers .playback-bar entry { font-variant-numeric: tabular-nums; }
.reducers .results-strip { padding: 13px 17px; }
.reducers .metric-card { padding: 0 12px; background: transparent; border-radius: 0; }
.reducers .result-number { color: #f0f6fb; font-size: 25px; font-weight: 500; }
.reducers .result-small { color: #f0f6fb; font-size: 20px; font-weight: 500; }
.reducers .result-unit { color: #acb9c9; font-size: 12px; }
.reducers .result-title { font-size: 12px; }
.reducers .metric-card:disabled { opacity: 0.5; }
.reducers .warning-bar { background: #302a20; border-top: 1px solid #504534; padding: 7px 14px; }
.reducers .warning-bar.invalid { background: #382623; border-color: #704940; }
.reducers .warning-bar.invalid .study { color: #ffb1a5; }
.reducers .study { color: #efbf79; font-size: 12px; }
.reducers .error { color: #ffb1a5; font-size: 12px; }
.reducers .derived { background: #27313b; }
.reducers .derived-output { background: #151b22; border: 1px solid #38414d; border-left: 2px solid #7cc8c8; border-radius: 4px; padding: 4px 8px; font-size: 16px; min-width: 42px; }
.reducers .field-error { border-color: #f1a596; }
.reducers .field-feedback { padding: 2px 0 3px; }
.reducers .io-role { padding: 6px 7px; background: #242b34; border-left: 2px solid #718499; }
.reducers .io-input { border-left-color: #e9a45d; }
.reducers .io-output { border-left-color: #74c8a4; }
.reducers .io-value { font-weight: 500; }
.reducers .io-result { color: #addbdd; font-size: 12px; }
.reducers .footer { padding: 8px 15px; border-top: 1px solid #38414d; }
.reducers .footer button { font-size: 12px; }
.reducers .status { color: #a9cdbb; font-size: 12px; }
.reducers .status.error { color: #ffb1a5; }
.reducers .connected { color: #a9cdbb; }
.reducers .motion-input-error { color: #ffb1a5; font-size: 12px; }
.reducers popover > contents { background: #1d2229; color: #e9eef4; border: 1px solid #38414d; border-radius: 7px; padding: 12px; }
.reducers .tool-dock { background: #242b34; border-left: 1px solid #38414d; }
.reducers .tool-nav { padding: 7px; border-bottom: 1px solid #38414d; }
.reducers .tool-nav button { padding: 3px 7px; font-size: 12px; }
.reducers .tool-nav button:checked { border-color: #7cc8c8; background: #30434a; }
.reducers .tool-dock list { background: #151b22; border: 1px solid #38414d; border-radius: 4px; }
.reducers .tool-dock row { padding: 8px; border-bottom: 1px solid #38414d; }
.reducers .tool-dock row:selected { background: #30434a; color: #e9eef4; }
.reducers textview text { background: #151b22; color: #e9eef4; }
.reducers .tool-dock flowboxchild { padding: 0; }
.reducers .measurement { background: #151b22; border: 1px solid #38414d; border-radius: 5px; padding: 10px; font-variant-numeric: tabular-nums; }
.reducers .document-name { font-weight: 600; }
.reducers .motion-palette scale trough { min-height: 4px; background: #3c4754; }
.reducers .motion-palette scale highlight { background: #7cc8c8; }
.reducers .motion-palette scale slider { min-width: 18px; min-height: 18px; margin: -7px 0; padding: 0; background: #d2dce6; }
'''


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
        cr.set_source_rgb(.76, .84, .9)
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
    app.canvas.connect('view-changed', lambda *_: axes.queue_draw())
    overlay.add_overlay(axes)


def build(app, labels):
    from app_paths import APP_ID, resource_path
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
    provider.load_from_data(CSS)
    app.workspace_style = provider
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    app.win.set_child(root)
    header = Gtk.HeaderBar()
    brand = Gtk.Box(spacing=8)
    logo = Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(str(brand_dir/'ratiolab-icon.png'))))
    logo.set_pixel_size(28)
    brand.append(logo)
    title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    app.project_title = Gtk.Label(label='RatioLab', xalign=0, max_width_chars=28, ellipsize=Pango.EllipsizeMode.MIDDLE, css_classes=['document-name'])
    title_box.append(app.project_title)
    app.document_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE,
                                  max_width_chars=28, css_classes=['muted'])
    title_box.append(app.document_label)
    brand.append(title_box)
    header.set_title_widget(brand)
    for icon, title, callback in [('document-new-symbolic', 'New project · Ctrl+N', app.new_project),
                                   ('document-open-symbolic', 'Open project · Ctrl+O', app.load_dialog)]:
        button = Gtk.Button(icon_name=icon, css_classes=['flat'])
        button.set_tooltip_text(title)
        button.connect('clicked', callback)
        header.pack_start(button)
        app.file_buttons.append(button)
    save = Gtk.Button(label='Save', css_classes=['flat'])
    save.set_tooltip_text('Save project · Ctrl+S')
    save.connect('clicked', app.save_dialog)
    header.pack_start(save)
    app.file_buttons.append(save)
    project_menu = Gtk.MenuButton(icon_name='view-more-symbolic', css_classes=['flat'])
    project_menu.set_tooltip_text('Project · Save As and recent files')
    project_popup = Gtk.Popover()
    project_menu.set_popover(project_popup)
    commands = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    project_popup.set_child(commands)
    for title, callback in [('Save As…', app.save_as_dialog), ('Recent projects…', app.show_recent)]:
        button = Gtk.Button(label=title)
        button.connect('clicked', lambda b, fn=callback: (project_popup.popdown(), fn(b)))
        commands.append(button)
        app.file_buttons.append(button)
    header.pack_start(project_menu)
    for icon, name, callback, hint in [('edit-undo-symbolic', 'undo_button', app.undo_project, 'Undo · Ctrl+Z'),
                                       ('edit-redo-symbolic', 'redo_button', app.redo_project, 'Redo · Ctrl+Shift+Z / Ctrl+Y')]:
        button = Gtk.Button(icon_name=icon, css_classes=['flat'])
        button.connect('clicked', callback)
        button.set_tooltip_text(hint)
        header.pack_start(button)
        setattr(app, name, button)
    gui_workflow.install_exports(app)
    header.pack_end(app.export_menu)
    gui_workflow.install_cad(app)
    header.pack_end(app.cad_menu)
    from update_ui import Controller
    app.updates = Controller(app, header)
    release_notes = Gtk.Button(label='Release notes and updates…')
    release_notes.connect('clicked', lambda *_: (project_popup.popdown(), app.updates.show()))
    commands.append(release_notes)
    app.win.set_titlebar(header)
    content = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
    content.set_position(350)
    content.set_shrink_start_child(False)
    content.set_shrink_end_child(False)
    content.set_resize_start_child(False)
    content.set_vexpand(True)
    app.workspace_paned = content
    root.append(content)
    left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['sidebar'])
    left.set_size_request(310, -1)
    content.set_start_child(left)
    picker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7, css_classes=['model-picker'])
    left.append(picker)
    picker.append(gui_workflow.text('Generator family', 'field-label'))
    app.selector = gui_workflow.searchable_dropdown(labels)
    app.selector.set_selected(list(app.families).index(app.family))
    app.selector.connect('notify::selected', app.change_family)
    picker.append(app.selector)
    app.family_hint = gui_workflow.text('', 'study')
    app.family_hint.set_visible(False)
    picker.append(app.family_hint)
    app.variant_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    app.variant_box.append(gui_workflow.text('Variant', 'field-label'))
    app.variant_selector = Gtk.DropDown.new_from_strings(['Standard'])
    app.variant_selector.connect('notify::selected', app.change_variant)
    app.variant_box.append(app.variant_selector)
    picker.append(app.variant_box)
    gui_workflow.install_sections(app, left)
    reset_row = Gtk.Box(spacing=5, css_classes=['sidebar-actions'])
    app.reset_button = Gtk.Button(label='Reset defaults', css_classes=['flat'])
    app.reset_button.connect('clicked', app.reset_defaults)
    app.reset_button.set_tooltip_text('Restore defaults for this model. Undo reset is available afterwards.')
    app.file_buttons.append(app.reset_button)
    reset_row.append(app.reset_button)
    app.undo_reset = Gtk.Button(label='Undo reset', css_classes=['flat'])
    app.undo_reset.set_visible(False)
    app.undo_reset.connect('clicked', app.undo_defaults)
    app.file_buttons.append(app.undo_reset)
    reset_row.append(app.undo_reset)
    left.append(reset_row)
    right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    right.set_hexpand(True)
    content.set_end_child(right)
    toolbar = Gtk.Box(spacing=8, css_classes=['viewbar'])
    right.append(toolbar)
    app.canvas = Preview3D()
    app.view_buttons = {}
    views = Gtk.Box(spacing=4)
    toolbar.append(views)
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
    toolbar.append(app.pick_mode)
    visibility = Gtk.MenuButton(label='View')
    toolbar.append(visibility)
    popup = Gtk.Popover()
    visibility.set_popover(popup)
    view_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
    popup.set_child(view_body)
    view_body.append(Gtk.Label(label='Text size', xalign=0, css_classes=['muted']))
    app.text_size = Gtk.DropDown.new_from_strings(['100%', '125%', '150%'])
    view_body.append(app.text_size)
    def text_size_changed(widget, *_):
        import re
        factor = (1, 1.25, 1.5)[widget.get_selected()]
        scaled = re.sub(rb'font-size: (\d+)px', lambda m: f'font-size: {int(m[1])*factor:g}px'.encode(), CSS)
        app.workspace_style.load_from_data(scaled)
    app.text_size.connect('notify::selected', text_size_changed)
    view_body.append(Gtk.Separator())
    app.view_options = {}
    for key, title in [('support','Supports'), ('housing','Housing'), ('exploded','Exploded'), ('section','Section')]:
        check = Gtk.CheckButton(label=title)
        check.set_tooltip_text('Preview only. Export always uses nominal coordinates and its explicit component scope.')
        check.connect('toggled', app.change_view_options)
        view_body.append(check)
        app.view_options[key] = check
    overlay = Gtk.Overlay(css_classes=['preview-frame'])
    overlay.set_child(app.canvas)
    overlay.set_vexpand(True)
    app.viewport_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
    app.viewport_paned.set_start_child(overlay)
    app.viewport_paned.set_shrink_start_child(False)
    app.viewport_paned.set_shrink_end_child(False)
    app.viewport_paned.set_resize_start_child(True)
    right.append(app.viewport_paned)
    from workspace_tools import Dock
    app.tools = Dock(app, app.viewport_paned, toolbar)
    app.preview_overlay = overlay
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
    playback = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['playback-bar'])
    right.append(playback)
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
    def pick_mode_changed(*_):
        mode = app.pick_mode.get_selected()
        if mode == 2:
            app.components.open()
        if app.components.window:
            app.components.measure.set_active(mode == 2)
    app.pick_mode.connect('notify::selected', pick_mode_changed)
    app.metric_cards = Gtk.FlowBox(css_classes=['results-strip'])
    app.metric_cards.set_selection_mode(Gtk.SelectionMode.NONE)
    app.metric_cards.set_column_spacing(12)
    app.metric_cards.set_min_children_per_line(3)
    app.metric_cards.set_max_children_per_line(3)
    app.metric_cards.set_homogeneous(True)
    right.append(app.metric_cards)
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
    right.append(warning)
    # Full text stays available through reports and notes, rather than occupying
    # a second permanent results area below the viewport.
    app.metrics = Gtk.Label(selectable=True)
    app.notes = Gtk.Label(selectable=True)
    app.full_results_expander = Gtk.Expander()
    app.results_title = Gtk.Label(label='Results')
    footer = Gtk.Box(spacing=12, css_classes=['footer'])
    app.spinner = Gtk.Spinner()
    footer.append(app.spinner)
    app.status = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, css_classes=['status'])
    footer.append(app.status)
    app.bom_summary = Gtk.Label(css_classes=['muted'])
    footer.append(app.bom_summary)
    app.live_label = Gtk.Label(label='✓ Geometry generated', css_classes=['muted'])
    # Kept as a state label for status/tooltips; no redundant live-update badge.
    for title, fn in [('Bill of materials', app.show_bom), ('Calculation report', app.show_calculations),
                      ('Model notes', lambda _: gui_workflow.show_report(app, 'Model notes', app.notes.get_text()))]:
        b = Gtk.Button(label=title, css_classes=['flat'])
        b.connect('clicked', fn)
        footer.append(b)
        app.file_buttons.append(b)
    root.append(footer)
    gui_workflow.install_shortcuts(app)
