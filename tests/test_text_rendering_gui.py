# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Font pixels must fit the bounds GTK uses to invalidate changed text."""
from io import BytesIO
import math
import sys
import unittest
import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Graphene, Pango
import test_workspace_theme_preferences as fixtures


class TextRenderingTests(unittest.TestCase):
    setUpClass = fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux font rendering')
    def test_changed_label_glyphs_fit_the_declared_damage_bounds(self):
        settings = Gtk.Settings.get_default()
        if settings.find_property('gtk-font-rendering'):
            settings.set_property('gtk-font-rendering', Gtk.FontRendering.AUTOMATIC)
        app = self.launch()
        app.settings.present()
        label = app.settings.mouse_hint
        renderer = app.win.get_renderer()
        color = Gdk.RGBA()
        color.parse('#aebac8')
        before = app.project_snapshot()
        texts = [
            'Maiusc + trascinamento centrale: ruota · trascinamento centrale: sposta · rotella: zoom',
            'Sensibilità · iàèéîü',
        ]
        for text in texts:
            for size in (12, 13, 14, 15, 17.5, 18):
                layout = label.create_pango_layout(text)
                font = Pango.FontDescription.from_string('DejaVu Sans')
                font.set_absolute_size(round(size * Pango.SCALE))
                layout.set_font_description(font)
                for offset in (0, .125, .25, .375, .5, .625, .75, .875):
                    with self.subTest(text=text, size=size, offset=offset):
                        snapshot = Gtk.Snapshot()
                        point = Graphene.Point()
                        point.init(.25, offset)
                        snapshot.translate(point)
                        snapshot.append_layout(layout, color)
                        node = snapshot.to_node()
                        bounds = node.get_bounds()
                        left, top = math.floor(bounds.get_x()), math.floor(bounds.get_y())
                        right = math.ceil(bounds.get_x() + bounds.get_width())
                        bottom = math.ceil(bounds.get_y() + bounds.get_height())
                        viewport = Graphene.Rect()
                        viewport.init(left - 3, top - 3, right - left + 6, bottom - top + 6)
                        texture = renderer.render_texture(node, viewport)
                        pixels = cairo.ImageSurface.create_from_png(
                            BytesIO(texture.save_to_png_bytes().get_data()))
                        self.assertEqual(pixels.get_format(), cairo.FORMAT_ARGB32)
                        pixels.flush()
                        raw = pixels.get_data()
                        width, height, stride = pixels.get_width(), pixels.get_height(), pixels.get_stride()
                        alpha = 3 if sys.byteorder == 'little' else 0
                        # Significant pixels outside this rectangle survive a
                        # later partial redraw, becoming stray dots. Allow only
                        # negligible alpha quantization at the raster boundary.
                        for y in range(height):
                            xs = range(width) if y < 3 or y >= height - 3 else (*range(3), *range(width - 3, width))
                            self.assertTrue(all(raw[y * stride + x * 4 + alpha] <= 8 for x in xs))
        self.assertEqual(app.project_snapshot(), before)
        self.assertFalse(app.document.dirty)


if __name__ == '__main__':
    unittest.main()
