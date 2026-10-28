"""Frozen entrypoint: GUI launches log silently; CI can request a JSON report."""
import contextlib
import os
from pathlib import Path
import sys
import traceback


def main():
    from app_paths import data_dir
    from ratiolab_cli import main as run
    args = sys.argv[1:]
    if '--mcp' in args:
        if sys.stdin is None or sys.stdout is None:
            if sys.stderr is not None:
                print('Use the RatioLab-MCP console companion for agent tools.', file=sys.stderr)
            return 2
        return run(args)
    report = None
    if '--report' in args:
        index = args.index('--report')
        if index+1 >= len(args):
            raise ValueError('--report requires an output filename')
        report = Path(args[index+1]).expanduser().resolve()
        del args[index:index+2]
    elif sys.stdout is None or sys.stderr is None:
        report = data_dir()/'logs/ratiolab.log'
    if report is None:
        return run(args)
    report.parent.mkdir(parents=True, exist_ok=True)
    mode = 'a' if report.name == 'ratiolab.log' and not args else 'w'
    with report.open(mode, encoding='utf-8', buffering=1) as output, \
            contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            return run(args)
        except Exception:
            traceback.print_exc()
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
