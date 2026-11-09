# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Browsing is isolated; accepting a variant is one undoable document edit."""
from copy import deepcopy
from pathlib import Path
import os, shutil, subprocess, unittest
import test_workspace_theme_preferences as fixtures
from test_workspace_theme_preferences import pump, wait_until
from geometry import FAMILIES, VARIANTS
from model_catalog_ui import Catalog


class ModelCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WorkspaceThemePreferencesTests.setUpClass()

    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def test_browse_cancel_and_apply_preserve_document_and_history(self):
        a=self.launch()
        self.assertTrue(wait_until(lambda:a.design and not a.pending and not a._geometry_waiting))
        before=deepcopy(a.project_snapshot());token=a.document.token
        picker=Catalog(a);a.model_catalog=picker;picker.window.present();pump(.2)
        self.assertEqual(set(picker.cards),set(FAMILIES))
        for family in FAMILIES:
            picker.choose(family);pump(.01)
            self.assertEqual(a.project_snapshot(),before)
        a.language.change('it');picker.search.set_text('cicloidale');picker.filter()
        self.assertTrue(picker.cards['cycloidal'].get_parent().get_visible())
        self.assertFalse(picker.cards['parallel'].get_parent().get_visible())
        picker.window.close();pump(.1)
        self.assertEqual(a.project_snapshot(),before);self.assertEqual(a.document.token,token)
        picker=Catalog(a);a.model_catalog=picker
        picker.choose('parallel','two_stage_helical');picker.commit();pump(.2)
        self.assertEqual(a.family,'parallel')
        self.assertEqual(a.read_values()['variant'],'two_stage_helical')
        self.assertNotEqual(a.document.token,token)
        a.undo_project();pump(.2)
        self.assertEqual(a.project_snapshot(),before)

    def test_all_variant_choices_have_real_assets_and_complete_models(self):
        a=self.launch();picker=Catalog(a);a.model_catalog=picker
        for family in FAMILIES:
            for variant in VARIANTS.get(family,{None:'Standard'}):
                picker.choose(family,variant)
                self.assertEqual(picker.variant,variant)
            self.assertTrue((Path(__file__).resolve().parents[1]/'src/ratiolab_resources/model-catalog'/f'{family}.png').is_file())
        picker.window.close()

    def test_live_language_changes_translate_placeholders_without_editing_input(self):
        from gi.repository import Gtk
        from ui_language import catalog, translate
        a = self.launch()
        before = deepcopy(a.project_snapshot())
        picker = Catalog(a); a.model_catalog = picker
        picker.window.present(); pump(.2)
        entry = Gtk.Entry(placeholder_text='Project name')
        entry.set_text('Tools')
        picker.detail.append(entry)
        picker.search.set_text('bevel-20-40.config.json')
        for code in (*catalog()['languages'], 'en'):
            a.language.change(code); pump(.02)
            with self.subTest(language=code):
                self.assertEqual(picker.search.get_placeholder_text(), translate('Search models…', code))
                self.assertEqual(entry.get_placeholder_text(), translate('Project name', code))
                self.assertEqual(entry.get_text(), 'Tools')
                self.assertEqual(picker.search.get_text(), 'bevel-20-40.config.json')
                self.assertEqual(a.project_snapshot(), before)
        picker.window.close()

    def test_separated_face_variant_initializes_a_real_groove(self):
        a=self.launch();picker=Catalog(a);a.model_catalog=picker
        picker.choose('face','double_helical');picker.extra['double_style']='separated'
        picker.commit();pump(.2)
        self.assertEqual(a.family,'face')
        self.assertEqual(a.read_values()['double_style'],'separated')
        self.assertGreater(a.read_values()['gap'],0)
        self.assertTrue(wait_until(lambda:a.design and a.design.family=='face' and not a._geometry_waiting))


class BrowserCatalogTests(unittest.TestCase):
    def test_all_catalog_silhouettes_are_centred_and_unclipped(self):
        import cairo
        root=Path(__file__).resolve().parents[1]/'src/ratiolab_resources/model-catalog'
        for family in FAMILIES:
            with self.subTest(family=family):
                surface=cairo.ImageSurface.create_from_png(str(root/f'{family}.png'))
                self.assertEqual((surface.get_width(),surface.get_height()),(480,320))
                surface.flush();raw=bytes(surface.get_data());stride=surface.get_stride();background=raw[:3]
                xmin,ymin,xmax,ymax=480,320,-1,-1
                for y in range(320):
                    for x in range(480):
                        offset=y*stride+4*x
                        if max(abs(raw[offset+c]-background[c]) for c in range(3))>10:
                            xmin=min(xmin,x);xmax=max(xmax,x);ymin=min(ymin,y);ymax=max(ymax,y)
                self.assertGreater(xmax,xmin);self.assertGreater(ymax,ymin)
                self.assertLessEqual(abs((xmin+xmax)/2-239.5),1)
                self.assertLessEqual(abs((ymin+ymax)/2-159.5),1)
                self.assertGreaterEqual(min(xmin,ymin,479-xmax,319-ymax),24)

    def test_variants_precision_and_single_history_transaction(self):
        node=os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required')
        result=subprocess.run([node,'--experimental-vm-modules',str(Path(__file__).with_name('webapp_model_catalog.mjs'))],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
