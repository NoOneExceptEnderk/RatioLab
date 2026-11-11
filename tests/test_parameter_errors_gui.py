# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK fields, language changes, valid recovery and incomplete drafts."""
from copy import deepcopy
import unittest
from parameter_errors import ParameterError
import gui_workflow
import test_tooth_tips_gui as fixtures
from test_interference_gui import pump, wait_until


class ParameterErrorGuiTests(unittest.TestCase):
    setUpClass = fixtures.ToothTipGuiTests.__dict__['setUpClass']
    setUp = fixtures.ToothTipGuiTests.setUp
    close_apps = fixtures.ToothTipGuiTests.close_apps
    launch = fixtures.ToothTipGuiTests.launch
    load = fixtures.ToothTipGuiTests.load

    def settle(self, app):
        self.assertTrue(wait_until(lambda:not app.pending and not app._geometry_waiting))

    def test_real_constraints_all_related_fields_and_valid_recovery(self):
        a = self.launch()
        for family,initial,key,bad,expected in [
            ('spur',{},'bore','80',{'bore','module','teeth'}),
            ('planetary',{},'sun','19',{'sun','planet','planets'}),
            ('planetary',dict(variant='two_stage'),'sun2','19',{'sun2','planet2','planets'}),
            ('cycloidal',{},'eccentric','3',{'eccentric','radius','pins'}),
            ('harmonic',{},'teeth','61',{'teeth'}),
            ('worm',{},'bore','30',{'bore','diameter','module'}),
        ]:
            with self.subTest(family=family,initial=initial):
                self.load(a,family,initial);self.settle(a)
                before=deepcopy(a.config());old=a.inputs[key].get_text();accepted=a.canvas.design
                a.inputs[key].set_text(bad);self.settle(a)
                self.assertFalse(a.export_menu.get_sensitive())
                self.assertIs(a.canvas.design,accepted)
                self.assertTrue(expected <= set(a.error_fields))
                if key=='sun2':self.assertNotIn('sun',a.error_fields)
                for field in expected:
                    self.assertTrue(a.inputs[field].has_css_class('field-error'),field)
                    self.assertTrue(a.field_feedback[field].get_visible(),field)
                identities=a.error_fields
                a.language.change('it');pump(.2)
                self.assertEqual(a.error_fields,identities)
                a.inputs[key].set_text(old);self.settle(a)
                self.assertTrue(a.export_menu.get_sensitive())
                self.assertEqual(a.config(),before)
                self.assertFalse(any(w.get_visible() for w in a.field_feedback.values()))
                a.language.change('en')

    def test_prose_independence_incomplete_draft_history_and_unknown_failure(self):
        a=self.launch();self.load(a,'spur');self.settle(a)
        for text in ('arbitrary message', 'eccentric bore: testo', '任意文字'):
            gui_workflow.show_parameter_error(a,ParameterError('test.rule',('width','module'),text))
            self.assertEqual(set(a.error_fields),{'width','module'})
            self.assertFalse(a.inputs['bore'].has_css_class('field-error'))
        gui_workflow.show_parameter_error(a,ValueError('bore: eccentric equally spaced'))
        self.assertEqual(a.error_fields,())
        self.assertTrue(a.parameter_error.get_visible())
        original=deepcopy(a.config())
        a.inputs['module'].set_text('-');self.settle(a)
        self.assertEqual(a.error_fields,('module',))
        self.assertEqual(a.inputs['module'].get_text(),'-')
        self.assertFalse(a.export_menu.get_sensitive())
        a.undo_project();self.settle(a)
        self.assertEqual(a.config(),original)
        self.assertTrue(a.export_menu.get_sensitive())
        a.redo_project();self.settle(a)
        self.assertEqual(a.inputs['module'].get_text(),'-')
        self.assertFalse(a.export_menu.get_sensitive())
        a.inputs['module'].set_text('2');self.settle(a)
        self.assertTrue(a.export_menu.get_sensitive())
        captured=[];a.canvas.capture_png(lambda data,error:captured.append((data,error)))
        self.assertTrue(wait_until(lambda:bool(captured)))
        self.assertIsNone(captured[0][1])
        self.assertTrue(captured[0][0].startswith(b'\x89PNG'))

    def test_concise_individual_limits_switch_language_without_editing_values(self):
        a=self.launch();self.load(a,'parallel');self.settle(a)
        a.inputs['pinion'].set_text('80');self.settle(a)
        self.assertEqual(a.field_feedback['pinion'].get_text(),'Too large. Maximum: 59.')
        self.assertEqual(a.field_feedback['wheel'].get_text(),'Too small. Minimum: 81.')
        a.language.change('it');pump(.2)
        self.assertEqual(a.field_feedback['pinion'].get_text(),'Troppo grande. Massimo: 59.')
        self.assertEqual(a.field_feedback['wheel'].get_text(),'Troppo piccolo. Minimo: 81.')
        self.assertEqual(a.inputs['pinion'].get_text(),'80')
        a.inputs['pinion'].set_text('20');self.settle(a)
        self.assertTrue(a.export_menu.get_sensitive())


if __name__=='__main__':unittest.main()
