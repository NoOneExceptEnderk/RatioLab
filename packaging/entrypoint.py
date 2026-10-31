# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Frozen entrypoint: explicit reports keep stdout separate from diagnostics."""
import contextlib
import os
from pathlib import Path
import sys
import traceback


def main():
    args = sys.argv[1:]
    if '--mcp' in args:
        if sys.stdin is None or sys.stdout is None:
            if sys.stderr is not None:
                print('Use the RatioLab-MCP console companion for agent tools.', file=sys.stderr)
            return 2
        from ratiolab_cli import main as run
        return run(args)
    report = None
    explicit_report = '--report' in args
    if explicit_report:
        index = args.index('--report')
        if index+1 >= len(args):
            raise ValueError('--report requires an output filename')
        report = Path(args[index+1]).expanduser().resolve()
        del args[index:index+2]
    elif sys.stdout is None or sys.stderr is None:
        from app_paths import data_dir
        report = data_dir()/'logs/ratiolab.log'
    if report is None:
        from ratiolab_cli import main as run
        return run(args)
    report.parent.mkdir(parents=True, exist_ok=True)
    mode = 'a' if not explicit_report and not args else 'w'
    with contextlib.ExitStack() as streams:
        output = streams.enter_context(report.open(mode, encoding='utf-8', buffering=1))
        errors = (streams.enter_context(report.with_suffix('.stderr.log').open(
            'w', encoding='utf-8', buffering=1)) if explicit_report else output)
        streams.enter_context(contextlib.redirect_stdout(output))
        streams.enter_context(contextlib.redirect_stderr(errors))
        check_callbacks = explicit_report and any(flag in args for flag in (
            '--diagnose', '--diagnose-gui', '--self-test', '--self-test-gui'))
        callback_failed = False
        original_hook = sys.excepthook
        def report_callback_exception(kind, error, trace):
            nonlocal callback_failed
            callback_failed = True
            original_hook(kind, error, trace)
        try:
            if check_callbacks:
                sys.excepthook = report_callback_exception
            # Import after redirection: binding/import warnings are diagnostics,
            # too, and must not prefix an otherwise successful JSON report.
            from ratiolab_cli import main as run
            result = run(args)
            return 1 if callback_failed and result == 0 else result
        except Exception:
            traceback.print_exc()
            return 1
        finally:
            if check_callbacks:
                sys.excepthook = original_hook


if __name__ == '__main__':
    raise SystemExit(main())
