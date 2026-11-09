# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Portable theme validation, isolation and independent preset customizations."""
from copy import deepcopy
import json
import unittest
import app_paths
import theme_preferences as themes


class ThemePreferenceTests(unittest.TestCase):
    def test_defaults_preserve_original_palettes_and_do_not_alias_preferences(self):
        for mode in themes.MODES:
            self.assertEqual(themes.palette(mode), themes.BASE_PALETTES[mode])
            self.assertEqual(themes.viewport(mode), themes.BASE_PREVIEW[mode])
        first, second = app_paths.ui_preferences({}), app_paths.ui_preferences({})
        first['theme_customizations']['active']['dark'] = 'nord'
        self.assertEqual(second['theme_customizations'], themes.defaults())
        self.assertEqual(app_paths.UI_DEFAULTS['theme_customizations'], themes.defaults())

    def test_all_presets_resolve_complete_palettes_and_readable_accent_labels(self):
        for mode in themes.MODES:
            for preset in themes.PRESETS:
                config = themes.defaults();config['active'][mode] = preset
                palette = themes.palette(mode, config)
                self.assertEqual(set(palette), set(themes.BASE_PALETTES[mode]))
                self.assertTrue(all(themes.color(value) == value for value in palette.values()))
                self.assertGreaterEqual(themes.contrast(palette['accent'], palette['on_accent']), 4.5)
                self.assertEqual(set(themes.viewport(mode, config)), set(themes.VIEW_ROLES))

    def test_preset_and_mode_switches_retain_independent_edits(self):
        config = themes.change_color(themes.defaults(), 'dark', 'colors', 'accent', '#123456')
        config['active']['dark'] = 'nord'
        config = themes.change_color(config, 'dark', 'colors', 'accent', '#abcdef')
        config = themes.change_color(config, 'light', 'viewport', 'background', '#fedcba')
        self.assertEqual(themes.palette('dark', config)['accent'], '#abcdef')
        config['active']['dark'] = 'ratiolab'
        self.assertEqual(themes.palette('dark', config)['accent'], '#123456')
        self.assertEqual(themes.hex_color(themes.viewport('light', config)['background']), '#fedcba')
        reset = themes.change_color(config, 'dark', 'colors', 'accent', None)
        self.assertEqual(themes.palette('dark', reset)['accent'], themes.BASE_PALETTES['dark']['accent'])
        self.assertEqual(themes.palette('dark', config)['accent'], '#123456')

    def test_theme_file_roundtrip_preserves_colors_and_imported_baseline(self):
        config = themes.defaults();config['active']['light'] = 'warm'
        config = themes.change_color(config, 'light', 'colors', 'accent', '#112233')
        document = themes.export_theme('light', config)
        restored, mode = themes.import_theme(json.dumps(document), themes.defaults())
        self.assertEqual(mode, 'light')
        self.assertEqual(themes.palette(mode, restored), themes.palette(mode, config))
        self.assertEqual(themes.export_theme(mode, restored)['viewport'], document['viewport'])
        edited = themes.change_color(restored, mode, 'colors', 'accent', '#456789')
        edited['overrides'].pop('light:custom')
        self.assertEqual(themes.palette(mode, edited), document['colors'])

    def test_invalid_import_is_atomic_and_cannot_inject_css(self):
        original = themes.change_color(themes.defaults(), 'dark', 'colors', 'accent', '#123456')
        before = deepcopy(original)
        valid = themes.export_theme('dark', original)
        bad = [None, [], {}, 'broken', b'\xff', {'format': 'project/1'},
               dict(valid, mode=[]), dict(valid, name='\n'), dict(valid, extra='bad'),
               dict(valid, colors={'text': '#fff; color: red'}), dict(valid, colors={'unknown': '#fff'}),
               dict(valid, viewport={'background': [0, 0, 0]}), ' ' * (themes.MAX_THEME_BYTES + 1)]
        for document in bad:
            with self.subTest(document=str(document)[:100]), self.assertRaises(ValueError):
                themes.import_theme(document, original)
            self.assertEqual(original, before)

    def test_corrupt_saved_values_fall_back_without_affecting_other_preferences(self):
        for invalid in (None, [], True, {'version': True}, {'version': 99}):
            result = app_paths.ui_preferences(dict(theme_customizations=invalid, theme='light', zoom_speed=2))
            self.assertEqual(result['theme_customizations'], themes.defaults())
            self.assertEqual(result['theme'], 'light');self.assertEqual(result['zoom_speed'], 2)
        raw = themes.defaults();raw['active']['dark'] = 'bad'
        raw['overrides']['dark:ratiolab'] = {'colors': {'accent': '#abc', 'text': 'garbage'}}
        result = themes.normalize(raw)
        self.assertEqual(result['active']['dark'], 'ratiolab')
        self.assertEqual(themes.palette('dark', result)['accent'], '#aabbcc')
        self.assertEqual(themes.palette('dark', result)['text'], themes.BASE_PALETTES['dark']['text'])


if __name__ == '__main__':unittest.main()
