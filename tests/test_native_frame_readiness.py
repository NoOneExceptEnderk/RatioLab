# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native readiness requires a completed canvas render at its current size."""
from types import SimpleNamespace
from itertools import count
import unittest
from unittest.mock import Mock, patch
from ratiolab_checks import _wait_for_frame
from preview3d import Preview3D


def wait_for_frame(canvas, context):
    # Model elapsed time independently of the host scheduler and load.
    with patch('ratiolab_checks.time.monotonic', side_effect=count(0., .01).__next__), \
         patch('ratiolab_checks.time.sleep'):
        _wait_for_frame(canvas, context)


class NativeFrameReadinessTests(unittest.TestCase):
    def test_completed_canvas_does_not_require_another_global_frame_number(self):
        clock = Mock(); clock.get_frame_counter.return_value = 7
        canvas = Mock(dirty=False, gl=True, render_serial=1, render_size=(320,280))
        canvas.get_frame_clock.return_value = clock
        canvas.get_width.return_value = 320; canvas.get_height.return_value = 280
        canvas.get_scale_factor.return_value = 1
        canvas.get_mapped.return_value = True
        def dispatch(blocking):
            canvas.render_serial += 1
            clock.connect.call_args.args[1](clock)
        context = Mock(); context.iteration.side_effect = dispatch
        wait_for_frame(canvas, context)
        canvas.queue_render.assert_called_once()
        clock.disconnect.assert_called_once()

    def test_other_paints_and_old_viewport_size_do_not_satisfy_readiness(self):
        clock = Mock(); clock.get_frame_counter.side_effect = [7,8,9,10]
        canvas = Mock(dirty=False, gl=True, render_serial=1, render_size=(320,280))
        canvas.get_frame_clock.return_value = clock
        canvas.get_width.return_value = 640; canvas.get_height.return_value = 480
        canvas.get_scale_factor.return_value = 1; canvas.get_mapped.return_value = True
        context = Mock()
        def dispatch(blocking):
            count = context.iteration.call_count
            if count >= 2: canvas.render_serial += 1
            if count >= 3: canvas.render_size = (640,480)
            clock.connect.call_args.args[1](clock)
        context.iteration.side_effect = dispatch
        wait_for_frame(canvas, context)
        self.assertEqual(context.iteration.call_count, 3)

    def test_capture_before_allocation_waits_for_native_render(self):
        callback = Mock()
        canvas = SimpleNamespace(failure=None, gl=object(), scene=object(),
            get_error=lambda:None, get_width=lambda:0, get_height=lambda:0,
            make_current=Mock(), attach_buffers=Mock(), on_render=Mock(), queue_render=Mock())
        Preview3D.capture_png(canvas, callback)
        canvas.attach_buffers.assert_not_called()
        canvas.on_render.assert_not_called()
        canvas.queue_render.assert_called_once()
        self.assertIs(canvas.capture_callback, callback)
