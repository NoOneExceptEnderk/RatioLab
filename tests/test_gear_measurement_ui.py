# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed read-only gauge workflow and revision rejection."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module
from geometry import generate


def pump(duration=.08):
    end=time.monotonic()+duration
    context=GLib.MainContext.default()
    while time.monotonic()<end:
        while context.pending():context.iteration(False)
        time.sleep(.003)


class GearMeasurementUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.folder=TemporaryDirectory()
        root=Path(cls.folder.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')))
        cls.environment.start()
        cls.original_base,cls.original_generated=module.BASE,module.GENERATED
        module.BASE=root;module.GENERATED=root/'exports'
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.gaugtests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():window.destroy()
        module.BASE,module.GENERATED=cls.original_base,cls.original_generated
        cls.environment.stop();cls.folder.cleanup()

    def setUp(self):
        a=self.app
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'spur',
                            'parameters':generate('spur',{'module':1,'teeth':20,'backlash':0}).values})
        pump()
        a.gear_measurement.button.emit('clicked')
        pump()
        self.c=a.gear_measurement

    def tearDown(self):
        if self.c.window:self.c.window.close()
        pump(.02)

    def text(self):
        b=self.c.report.get_buffer()
        return b.get_text(b.get_start_iter(),b.get_end_iter(),True)

    def test_gauge_entry_trims_only_redundant_zeros(self):
        c = self.c
        c.diameter.set_text('0001.700000000')
        c.diameter.emit('activate')
        self.assertEqual(c.diameter.get_text(), '1.7')
        c.calculate()
        self.assertIsNotNone(c.result)
        c.diameter.set_text('001.712345678900')
        c.diameter.emit('activate')
        self.assertEqual(c.diameter.get_text(), '1.7123456789')
        c.calculate()
        self.assertIsNotNone(c.result)
        c.diameter.set_text('1e-')
        c.diameter.emit('activate')
        self.assertEqual(c.diameter.get_text(), '1e-')
        c.calculate()
        self.assertIsNone(c.result)

    def test_menu_query_gauge_changes_and_readonly_export(self):
        a,c=self.app,self.c
        self.assertIs(a.tools.controllers['gear_measurement'],c)
        self.assertTrue(c.window.get_visible())
        snapshot=a.project_snapshot();token=a.document.token;states=len(a.document.states)
        c.diameter.set_text('1.7');c.calculate()
        self.assertIn('22.294093',self.text())
        self.assertEqual(c.result['result']['gauge_type'],'ball')
        c.gauge.set_selected(1)
        self.assertIsNone(c.result);self.assertFalse(c.save_button.get_sensitive())
        c.calculate();self.assertEqual(c.result['result']['gauge_type'],'roller')
        c.export()
        reports=list(a.output_dir.glob('gear-measurement-*/measurement.json'))
        self.assertTrue(reports)
        self.assertEqual(a.project_snapshot(),snapshot)
        self.assertEqual(a.document.token,token);self.assertEqual(len(a.document.states),states)
        c.diameter.set_text('nan');c.calculate()
        self.assertIn('positive finite',self.text())
        self.assertFalse(c.save_button.get_sensitive())

    def test_raw_edit_and_replacement_reject_stale_result(self):
        a,c=self.app,self.c
        c.diameter.set_text('1.7');c.calculate();old=c.result
        self.assertIsNotNone(old)
        a.inputs['module'].set_text('-')
        a.project_changed(('spur','module'))
        self.assertIsNone(c.result)
        self.assertFalse(c.save_button.get_sensitive())
        c.export();self.assertIsNone(c.result)
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'spur',
                            'parameters':generate('spur',{'module':1,'teeth':20,'backlash':0}).values})
        pump()
        self.assertIsNone(c.result)
        c.diameter.set_text('1.7');c.calculate();self.assertIsNotNone(c.result)
        self.assertNotEqual(c.result['revision'],old['revision'])

    def test_internal_member_and_explicit_helical_unsupported(self):
        a,c=self.app,self.c
        for family in ('internal','helical'):
            a.load_config_data({'format':'solidcraft-riduttori/1','family':family,'parameters':generate(family).values})
            pump()
            if family=='internal':
                ring=next(j for j,i in enumerate(c.indices) if a.design.parts[i].profile_metadata['tooth_profile']['measurement_geometry']['internal'])
                c.parts.set_selected(ring);c.default_diameter();c.calculate()
                self.assertIn('between gauges',self.text())
                self.assertEqual(c.result['result']['status'],'ok')
            else:
                c.diameter.set_text('3.4');c.calculate()
                self.assertIn('3D contact',self.text())
                self.assertFalse(c.result['result']['supported'])

    def test_measurement_available_after_combination_proposal_apply(self):
        from combination_search import Settings
        a,c=self.app,self.c
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'parallel',
                            'parameters':generate('parallel').values})
        search=a.combination_search
        search.open()
        search.start(Settings(target=3.05,tolerance_percent=0),{'wheel':(61,)})
        deadline=time.monotonic()+10
        while search.cancel is not None and time.monotonic()<deadline:
            pump(.03)
        self.assertIsNotNone(search.result)
        self.assertTrue(search.result.proposals)
        self.assertTrue(search.apply(search.result.proposals[0]))
        self.assertTrue(c.current())
        c.default_diameter();c.calculate()
        self.assertIsNotNone(c.result)
        self.assertEqual(c.result['parameters']['wheel'],61)
        self.assertEqual(c.result['revision'],a.document.token)
        search.window.close()
