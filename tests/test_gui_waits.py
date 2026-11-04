# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GUI waits must observe readiness even when the GLib queue stays busy."""
import unittest
from itertools import count
from unittest.mock import Mock, patch
from test_parallel_multistage_gui import wait_until


class GuiWaitTests(unittest.TestCase):
    def test_completed_work_is_observed_before_draining_another_ready_event(self):
        context = Mock()
        context.pending.return_value = True
        context.iteration.side_effect = [None, AssertionError('Readiness was starved by event draining')]
        with patch('test_parallel_multistage_gui.GLib.MainContext.default', return_value=context):
            wait_until(lambda: context.iteration.call_count == 1)
        context.iteration.assert_called_once_with(False)

    def test_unfinished_work_still_has_a_deadline(self):
        context = Mock()
        with patch('test_parallel_multistage_gui.GLib.MainContext.default', return_value=context), \
             patch('test_parallel_multistage_gui.time.monotonic', side_effect=count(0., .01).__next__), \
             patch('test_parallel_multistage_gui.time.sleep'):
            with self.assertRaisesRegex(AssertionError, 'timed out'):
                wait_until(lambda: False, timeout=.05)

    def test_pumps_respect_their_budget_with_a_continuously_ready_queue(self):
        import importlib
        for name in ('test_interference_gui','test_workspace_ui','test_fusion_gui'):
            with self.subTest(helper=name):
                module = importlib.import_module(name)
                context = Mock()
                context.pending.return_value = True
                context.iteration.side_effect = [None, AssertionError('Pump ignored its elapsed budget')]
                clock = iter((0., .01, .1, .2))
                with patch.object(module.GLib.MainContext, 'default', return_value=context), \
                     patch.object(module.time, 'monotonic', side_effect=clock.__next__), \
                     patch.object(module.time, 'sleep'):
                    module.pump(.04)
                context.iteration.assert_called_once_with(False)
