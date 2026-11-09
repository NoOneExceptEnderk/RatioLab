# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Preset contracts and invalid key maps must not replace a working configuration."""
from copy import deepcopy
import unittest
import keyboard_shortcuts as keys


class ShortcutMapTests(unittest.TestCase):
    def test_documented_cad_view_bindings_and_sequence(self):
        self.assertEqual(keys.preset_bindings('freecad')['view-fit'], ['v f'])
        self.assertEqual(keys.preset_bindings('freecad')['view-top'], ['2'])
        self.assertEqual(keys.preset_bindings('fusion')['view-fit'], ['F6'])
        self.assertEqual(keys.preset_bindings('inventor')['view-iso'], ['F6'])
        self.assertEqual(keys.preset_bindings('inventor')['view-fit'], ['Home'])
        for preset in ('solidworks', 'solidcraft'):
            self.assertEqual(keys.preset_bindings(preset)['view-left'], ['<Control>3'])
            self.assertEqual(keys.preset_bindings(preset)['view-iso'], ['<Control>7'])
        self.assertEqual(keys.preset_bindings('solidcraft')['view-fit'], ['F6'])
        self.assertEqual(keys.preset_bindings('solidworks')['view-fit'], ['f'])

    def test_conflicts_include_aliases_and_sequence_prefixes(self):
        for command, value in [('save', '<Control>y'), ('view-front', 'v'), ('view-front', 'v f')]:
            bindings = keys.preset_bindings('freecad')
            before = deepcopy(bindings)
            bindings[command] = [value]
            with self.subTest(command=command, value=value), self.assertRaises(keys.BindingError) as error:
                keys.validate(bindings, edited=command)
            self.assertIn(error.exception.command, ('redo', 'view-fit'))
            self.assertEqual(before, keys.preset_bindings('freecad'))

    def test_reserved_keys_and_unmodified_project_keys_are_rejected(self):
        for key in ('Escape', 'F1', 'Tab', '<Control>v', '<Alt>2', '<Alt>F4', 's', 'v f', 'NoSuchKey'):
            with self.subTest(key=key), self.assertRaises(keys.BindingError):
                bindings = keys.preset_bindings('ratiolab')
                bindings['save'] = [key]
                keys.validate(bindings)

    def test_corrupt_or_incomplete_preference_falls_back_without_partial_conflicts(self):
        valid = dict(version=1, preset='fusion', bindings=keys.preset_bindings('fusion'))
        self.assertEqual(keys.configuration(valid), valid)
        for bad in (None, [], dict(valid, version=True), dict(valid, preset='unknown'), dict(valid, preset=[]),
                    dict(valid, bindings={'save': ['<Control>s']}),
                    dict(valid, bindings=dict(valid['bindings'], save=['<Control>z']))):
            with self.subTest(bad=bad):
                result = keys.configuration(bad)
                self.assertEqual(result['preset'], 'ratiolab')
                self.assertEqual(result['bindings'], keys.preset_bindings('ratiolab'))

    def test_disabled_action_and_two_key_view_sequence_round_trip(self):
        bindings = keys.preset_bindings('ratiolab')
        bindings['save'] = []
        bindings['view-fit'] = ['<Control>k f']
        result = keys.configuration(dict(version=1, preset='ratiolab', bindings=bindings))
        self.assertEqual(result['bindings']['save'], [])
        self.assertEqual(result['bindings']['view-fit'], ['<Control>k f'])


if __name__ == '__main__':unittest.main()
