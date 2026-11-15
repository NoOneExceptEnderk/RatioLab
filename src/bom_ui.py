# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native BOM window using a separate view of the current model."""
import traceback
from math import pi

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk, Pango

import bom
from geometry_refresh import LatestOnly
from preview3d import Preview3D, build_scene
from rust_geometry import control_scope


STATUS = {'buy': 'Buy', 'make': 'Make', 'define': 'Select part', 'interface': 'CAD interface'}


def label(text='', *, muted=False, wrap=True):
    result = Gtk.Label(label=text, xalign=0, wrap=wrap, selectable=False)
    if muted:
        result.add_css_class('muted')
    return result


def _prepare(design, current):
    class Closed(Exception):
        pass

    def check():
        if not current():
            raise Closed()

    with control_scope(check):
        view = bom.presentation(design)
        check()
        try:
            scene = build_scene(design, True, True, layout_explosion=False,
                                visible_indices=set(view['context_indices']))
        except (ValueError, RuntimeError, ArithmeticError):
            check()
            traceback.print_exc()
            scene = None
        check()
        return view, scene


class BomWindow:
    def __init__(self, app, design):
        self.app = app
        self.design = design
        self.rows = []
        self._by_index = {}

        self.window = window = Gtk.Window(title='Bill of materials', transient_for=app.win,
                                         application=app, modal=True, destroy_with_parent=True)
        window.set_default_size(1040, 675)
        window.add_css_class('reducers')
        window.add_css_class('bom-window')
        window.bom = self
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=14,
                       margin_end=14, margin_top=14, margin_bottom=12)
        window.set_child(body)
        self.heading = label('Preparing the bill of materials…')
        self.heading.add_css_class('heading')
        body.append(self.heading)

        content = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True, wide_handle=True)
        content.set_position(500)
        body.append(content)
        viewport = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        viewport.add_css_class('bom-preview-panel')
        content.set_start_child(viewport)
        self.legend = label(muted=True)
        viewport.append(self.legend)

        self.preview = Preview3D()
        self.preview.context_opacity = .15
        self.preview.set_size_request(300, 220)
        from theme_preferences import palette, rgb, viewport as viewport_palette
        theme = app.canvas.theme
        customization = app.workspace_preferences.get('theme_customizations')
        colors = dict(app.canvas.palette)
        if colors['selection'] == viewport_palette(theme, customization, customized=False)['selection']:
            colors['selection'] = rgb(palette(theme, customization)['accent'])
        self.preview.set_theme(theme, colors)
        self.preview.set_mouse_navigation(app.canvas.mouse_navigation)
        self.preview.zoom_speed = app.canvas.zoom_speed
        self.preview.rotation_speed = app.canvas.rotation_speed
        self.preview.invert_zoom = app.canvas.invert_zoom
        self.preview.update_property([Gtk.AccessibleProperty.LABEL], ['Bill of materials preview'])
        self.preview.connect('component-click', self._picked)
        self.preview.connect('realize', self._realized)
        preview_keyboard = Gtk.EventControllerKey()
        preview_keyboard.connect('key-pressed', self._preview_keyboard)
        self.preview.add_controller(preview_keyboard)
        self.preview.set_options(True, True, 0., False)
        viewport.append(self.preview)
        self.selected_name = label()
        self.selected_name.add_css_class('bom-count')
        viewport.append(self.selected_name)
        self.message = label(muted=True)
        viewport.append(self.message)

        table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        table.add_css_class('bom-table')
        content.set_end_child(table)
        title = Gtk.Box(spacing=9, css_classes=['bom-row-content', 'bom-table-heading'])
        name = label('Component', muted=True)
        name.set_hexpand(True)
        title.append(name)
        units = label('Qty', muted=True)
        units.set_xalign(1)
        units.set_size_request(38, -1)
        title.append(units)
        specification = label('Size / reference', muted=True)
        specification.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        specification.set_max_width_chars(16)
        self.specification_width = 164 if app.text_size.get_selected() == 0 else 210
        specification.set_size_request(self.specification_width, -1)
        title.append(specification)
        table.append(title)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False)
        self.list.connect('row-selected', self._row_selected)
        self.list.connect('row-activated', self._row_selected)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, min_content_width=285,
                                         hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll.set_child(self.list)
        table.append(self.scroll)
        self.empty = label('No extra parts specified for this configuration.', muted=True)
        self.empty.set_visible(False)
        table.append(self.empty)
        table.append(label('Dimensions are nominal.', muted=True))

        details = Gtk.Box(spacing=12, css_classes=['bom-details'])
        first = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        second = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True,
                         css_classes=['bom-cad'])
        details.append(first)
        details.append(second)
        self.group = label(muted=True)
        self.part = label()
        self.part.add_css_class('heading')
        self.count = label()
        self.count.add_css_class('bom-count')
        self.description = label()
        first.append(self.group)
        first.append(self.part)
        first.append(self.count)
        first.append(self.description)
        self.cad = label()
        second.append(label('To complete in CAD', muted=True))
        second.append(self.cad)
        body.append(details)
        self.requirements = Gtk.Expander(label='Assembly requirements', visible=False)
        self.requirement_scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=115,
                                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.requirements.set_child(self.requirement_scroll)
        body.append(self.requirements)

        footer = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        full = Gtk.Button(label='Full report')
        full.connect('clicked', self.full_report)
        download = Gtk.Button(label='Export…', css_classes=['primary'])
        download.connect('clicked', self._export)
        close = Gtk.Button(label='Close')
        close.connect('clicked', lambda *_: window.close())
        for button in (full, close, download):
            footer.append(button)
        body.append(footer)
        keyboard = Gtk.EventControllerKey()
        keyboard.connect('key-pressed', self._keyboard)
        window.add_controller(keyboard)
        self.worker = LatestOnly(_prepare, GLib.idle_add, self._loaded)
        window.connect('unrealize', self._closed)
        window.present()
        self.worker.submit(design)

    def _keyboard(self, _controller, key, _keycode, _state):
        if key != Gdk.KEY_Escape:
            return False
        self.window.close()
        return True

    def _preview_keyboard(self, _controller, key, _keycode, state):
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        p = self.preview
        if key == Gdk.KEY_Home:
            p.view('iso')
            return True
        if key not in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down,
                       Gdk.KEY_plus, Gdk.KEY_minus, Gdk.KEY_equal, Gdk.KEY_KP_Add, Gdk.KEY_KP_Subtract):
            return False
        p.cancel_camera_transition()
        p.yaw += .12 * ((key == Gdk.KEY_Right) - (key == Gdk.KEY_Left))
        p.tilt = max(-pi, min(pi, p.tilt + .12 * ((key == Gdk.KEY_Down) - (key == Gdk.KEY_Up))))
        if key in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            p.zoom = min(14., p.zoom * 1.15)
        elif key in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            p.zoom = max(.12, p.zoom / 1.15)
        p.queue_render()
        return True

    def _closed(self, *_):
        self.worker.close()
        if getattr(self.app, 'bom_window', None) is self.window:
            self.app.bom_window = None

    def _realized(self, *_):
        if self.preview.failure:
            self._note('The 3D preview is unavailable. The bill of materials remains usable.')

    def _note(self, message):
        self.message.set_label(message)

    def _loaded(self, _design, data, error):
        if error:
            self.heading.set_label('The bill of materials could not be opened.')
            self._note(str(error))
            traceback.print_exception(error)
            return
        view, scene = data
        self.view = view
        self.heading.set_label(' · '.join(part for part in (view['family_label'], view['variant']) if part))
        if scene is not None:
            self.preview.set_design(self.design, prepared_scene=scene)
        else:
            self.preview.set_visible(False)
            self._note('The 3D preview is unavailable. The bill of materials remains usable.')
        for item in view['rows']:
            row = self._append_row(item)
            for index in item['indices']:
                self._by_index[index] = row
        self.preview.pickable_indices = set(self._by_index)
        from ui_language import translate
        self.preview.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            [translate('Bill of materials preview', self.app.language.language),
             translate('Drag to rotate. Use the arrow keys to turn and plus or minus to zoom.', self.app.language.language)])
        self.empty.set_visible(not any(item['quantity'] is not None for item in view['rows']))
        if view['requirements']:
            requirements = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for requirement in view['requirements']:
                requirements.append(label(requirement))
            self.requirement_scroll.set_child(requirements)
            self.requirements.set_visible(True)
        if self.rows:
            self.list.select_row(self.rows[0])

    def _append_row(self, item):
        row = Gtk.ListBoxRow()
        row.bom_item = item
        box = Gtk.Box(spacing=9, css_classes=['bom-row-content'])
        component = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        component.append(label(item['label']))
        component.append(label(STATUS[item['status']], muted=True))
        box.append(component)
        quantity = label(str(item['quantity']) if item['quantity'] is not None else '—', wrap=False)
        quantity.set_xalign(1)
        quantity.set_size_request(38, -1)
        box.append(quantity)
        specification = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        specification.set_size_request(self.specification_width, -1)
        if item['code']:
            code = label(item['code'])
            code.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            code.set_max_width_chars(16)
            specification.append(code)
        dimensions = label(item['dimensions'], muted=bool(item['code']))
        dimensions.set_max_width_chars(16)
        dimensions.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        specification.append(dimensions)
        box.append(specification)
        row.set_child(box)
        # Leave the row's accessible name to its child labels so the status,
        # quantity and measure remain exposed as well as the component name.
        self.rows.append(row)
        self.list.append(row)
        return row


    def _row_selected(self, _list, row):
        if row is None:
            return
        item = row.bom_item
        self.preview.selected_indices = tuple(item['indices'])
        self.preview.queue_render()
        self.legend.set_label(item['group'])
        self.selected_name.set_label(item['label'])
        self.group.set_label(item['group'])
        self.part.set_label(item['label'])
        self.count.set_label(item['count_basis'])
        self.count.set_visible(bool(item['count_basis']))
        self.description.set_label(item['detail'])
        self.cad.set_label(item['cad'])

    def _picked(self, preview, x, y, _multiple):
        if not self.rows:
            return
        row = self._by_index.get(preview.pick_component(x, y))
        if row is None:
            return
        self.list.select_row(row)
        bounds = row.compute_bounds(self.list)
        if bounds[0]:
            rect, adjust = bounds[1], self.scroll.get_vadjustment()
            adjust.clamp_page(rect.get_y(), rect.get_y() + rect.get_height())

    def full_report(self, *_):
        from gui_workflow import show_report
        return show_report(self.app, 'Bill of materials', bom.as_text(bom.build(self.design)),
                           parent=self.window)

    def _export(self, *_):
        self.window.close()
        self.app.export_bom()


def show(app, design):
    current = getattr(app, 'bom_window', None)
    if current is not None:
        current.present()
        return current
    controller = BomWindow(app, design)
    app.bom_window = controller.window
    return controller.window
