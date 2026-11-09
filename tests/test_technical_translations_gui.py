# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK help/report localization without changing the engineering document."""
from copy import deepcopy
import unittest
from test_settings import DesktopLanguageTests


class DesktopTechnicalTranslationTests(unittest.TestCase):
    setUpClass = DesktopLanguageTests.setUpClass
    setUp = DesktopLanguageTests.setUp
    close_apps = DesktopLanguageTests.close_apps
    launch = DesktopLanguageTests.launch

    def test_open_help_and_reports_follow_language_without_touching_input_or_model(self):
        from gi.repository import Gtk
        from ui_language import catalog, translate
        from parameter_help_ui import effect_sections
        from test_interference_gui import pump, wait_until
        a = self.launch()
        original = deepcopy(a.project_snapshot())
        token = a.document.token
        owner = a.parameter_help
        binding = owner.bindings['module']
        owner.open(binding,pinned=True)
        self.assertIsNotNone(owner.popover)
        owner.diagram_expander.set_expanded(True)
        source_help = owner.help_for(binding)
        window = Gtk.Window(application=a,transient_for=a.win)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.set_child(body)
        report = Gtk.TextView(editable=False)
        report._ratiolab_localize_report = True
        source = 'NOMINAL CALCULATION REPORT · SOLIDCRAFT REDUCERS\nNormal module [mm]\nAt -2.50000000001e+12 rpm input'
        report.get_buffer().set_text(source);body.append(report)
        editor = Gtk.TextView(editable=True)
        editor._ratiolab_localize_report = True
        editor.get_buffer().set_text(source);body.append(editor)
        window.present();pump(.1)
        def contents(view):
            buffer=view.get_buffer()
            return buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True)
        def labels(widget):
            if isinstance(widget,Gtk.Label):yield widget
            child=widget.get_first_child()
            while child:
                yield from labels(child);child=child.get_next_sibling()
        for code in (*catalog()['languages'],'en'):
            a.language.change(code);pump(.06)
            with self.subTest(language=code):
                self.assertEqual(contents(report),translate(source,code))
                self.assertEqual(contents(editor),source)
                effect = next(label for label in labels(owner.body) if label.has_css_class('help-effect'))
                self.assertEqual(effect.get_text(),effect_sections(translate(source_help.effect,code))[0])
                self.assertEqual(owner.diagram_legend.get_visible(),code!='en')
                self.assertEqual(a.project_snapshot(),original)
                self.assertEqual(a.document.token,token)
        a.language.change('it')
        report.get_buffer().set_text('Centre distance bounds are reversed.')
        self.assertTrue(wait_until(lambda: contents(report)==translate('Centre distance bounds are reversed.','it'),2))
        a.language.change('en')
        self.assertEqual(contents(report),'Centre distance bounds are reversed.')
        window.destroy();owner.close()


if __name__ == '__main__':
    unittest.main()
