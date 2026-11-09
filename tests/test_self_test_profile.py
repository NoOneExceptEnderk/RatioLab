# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Self-test profiles must not rewrite C's environment after native diagnosis."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app_paths
import ratiolab_checks
import ratiolab_cli


PROFILE_KEYS = ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'APPDATA', 'LOCALAPPDATA')


class SelfTestProfileTests(unittest.TestCase):
    def test_post_diagnosis_failure_never_mutates_c_environment_and_restores_mapping(self):
        original = os.environ
        before = dict(original)
        home = Path.home()
        diagnosed = False

        def diagnose(gui=False):
            nonlocal diagnosed
            self.assertFalse(gui)
            diagnosed = True
            return {'runtime': 'fixture'}

        def forbidden_environment_write(*args):
            self.assertTrue(diagnosed)
            raise AssertionError('C environment mutation after native diagnosis')

        def interrupted_geometry(*args):
            self.assertTrue(diagnosed)
            self.assertIsNot(os.environ, original)
            self.assertNotEqual(Path.home(), home)
            self.assertTrue((app_paths.config_dir()/app_paths.PREFERENCES_FILENAME).is_file())
            raise RuntimeError('controlled geometry failure inside isolated profile')

        with (patch.object(ratiolab_cli, 'diagnose', side_effect=diagnose),
              patch('geometry.generate', side_effect=interrupted_geometry),
              patch.object(os, 'putenv', side_effect=forbidden_environment_write) as putenv,
              patch.object(os, 'unsetenv', side_effect=forbidden_environment_write) as unsetenv):
            with self.assertRaisesRegex(RuntimeError, 'controlled geometry failure'):
                ratiolab_checks.self_test()
            self.assertIs(os.environ, original)
            self.assertEqual(dict(os.environ), before)
            self.assertEqual(Path.home(), home)
            putenv.assert_not_called()
            unsetenv.assert_not_called()

    def test_real_headless_exports_stay_in_temporary_python_profile_for_each_path_policy(self):
        original_features = ratiolab_checks._features_check
        # POSIX libc getenv observes C's environment independently of os.environ.
        # Logical Windows/macOS path-policy cases below are not native API tests.
        native_getenv = None
        if os.name == 'posix':
            native_getenv = ctypes.CDLL(None).getenv
            native_getenv.argtypes = [ctypes.c_char_p]
            native_getenv.restype = ctypes.c_char_p
        native_before = ({name: native_getenv(name.encode()) for name in PROFILE_KEYS}
                         if native_getenv else None)
        native_platform = sys.platform
        for system in ('linux', 'win32', 'darwin'):
            with self.subTest(path_policy=system), tempfile.TemporaryDirectory() as temporary:
                user = Path(temporary)/'existing user'
                user.mkdir()
                user_environment = dict(os.environ, **{
                    key: str(user/key.lower()) for key in PROFILE_KEYS})
                observed = []
                # Simulate path policies without changing the Rust library's host ABI.
                with (patch.object(os, 'environ', user_environment),
                      patch.object(Path, 'home', return_value=user),
                      patch.object(app_paths, 'sys', SimpleNamespace(**{**vars(sys), 'platform': system}))):
                    self.assertEqual(sys.platform, native_platform)
                    preferences = app_paths.config_dir()/app_paths.PREFERENCES_FILENAME
                    preferences.parent.mkdir(parents=True)
                    preferences.write_text('{"theme":"light","output_dir":"user choice"}\n')
                    project = app_paths.default_output_dir()/'existing-project.config.json'
                    project.parent.mkdir(parents=True, exist_ok=True)
                    project.write_bytes(b'preserve existing project\n')
                    preserved = {path.relative_to(user): path.read_bytes()
                                 for path in user.rglob('*') if path.is_file()}
                    environment_before = dict(user_environment)

                    def inspect_features(output, design):
                        profile = Path.home()
                        self.assertNotEqual(profile, user)
                        self.assertIsNot(os.environ, user_environment)
                        self.assertTrue(output.is_relative_to(profile))
                        self.assertTrue(app_paths.config_dir().is_relative_to(profile))
                        self.assertTrue(app_paths.default_output_dir().is_relative_to(profile))
                        self.assertTrue((app_paths.config_dir()/app_paths.PREFERENCES_FILENAME).is_file())
                        self.assertEqual(app_paths.saved_output_dir(), output)
                        self.assertEqual(json.loads((output/'self-test.config.json').read_text())['family'], 'helical')
                        self.assertTrue(list(output.glob('*.stl')))
                        self.assertTrue(list(app_paths.default_output_dir().rglob('*.step')))
                        if native_getenv:
                            self.assertEqual({name: native_getenv(name.encode()) for name in PROFILE_KEYS}, native_before)
                        # A Python-only temporary edit must also disappear on exit.
                        os.environ['RATIOLAB_SELF_TEST_ONLY'] = 'isolated'
                        observed.append(profile)
                        return original_features(output, design)

                    with (patch.object(ratiolab_cli, 'diagnose', return_value={'runtime': 'fixture'}),
                          patch.object(ratiolab_checks, '_features_check', side_effect=inspect_features),
                          patch.object(os, 'putenv', side_effect=AssertionError('Unexpected putenv')) as putenv,
                          patch.object(os, 'unsetenv', side_effect=AssertionError('Unexpected unsetenv')) as unsetenv,
                          patch.object(subprocess, 'Popen', side_effect=AssertionError('Headless self-test launched a child')) as child):
                        result = ratiolab_checks.self_test()
                    self.assertEqual(result['self_test'], 'passed')
                    self.assertEqual(result['families'], 15)
                    self.assertEqual(len(result['features']), 6)
                    self.assertTrue(all(value == 'passed' for value in result['features'].values()))
                    self.assertEqual(len(observed), 1)
                    self.assertFalse(observed[0].exists())
                    self.assertIs(os.environ, user_environment)
                    self.assertEqual(user_environment, environment_before)
                    self.assertEqual(Path.home(), user)
                    self.assertEqual({path.relative_to(user): path.read_bytes()
                                      for path in user.rglob('*') if path.is_file()}, preserved)
                    putenv.assert_not_called()
                    unsetenv.assert_not_called()
                    child.assert_not_called()


if __name__ == '__main__':
    unittest.main()
