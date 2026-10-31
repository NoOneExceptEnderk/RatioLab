# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Try installed GUI/GL on a native runner; only explicit display/GL absence is optional.

An initialized renderer must pass the full workspace test. Missing reports,
crashes, timeouts, shader failures and other application errors remain failures.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

EXPECTED_FAMILIES = frozenset(('spur', 'helical', 'double', 'planetary', 'cycloidal',
                             'harmonic', 'worm', 'parallel', 'internal', 'differential', 'wolfrom'))


def _run_workspace(command, report):
    """Preserve a native stack on macOS when the workspace exceeds its deadline."""
    process = subprocess.Popen(command)
    try:
        returncode = process.wait(timeout=180)
    except subprocess.TimeoutExpired:
        try:
            if sys.platform == 'darwin':
                # Sample before killing: a Python traceback cannot show a Cocoa
                # or graphics-driver wait inside a frozen application.
                sample = Path(report).with_suffix('.sample.txt')
                log = sample.with_suffix('.log')
                try:
                    result = subprocess.run(
                        ['/usr/bin/sample', str(process.pid), '1', '-file', str(sample)],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, timeout=10, check=False)
                    log.write_text(result.stdout or '', encoding='utf-8')
                except (OSError, subprocess.TimeoutExpired) as error:
                    log.write_text(str(error), encoding='utf-8')
        finally:
            process.kill()
            process.wait(timeout=10)
        raise
    subprocess.CompletedProcess(command, returncode).check_returncode()


def check(executable, folder, require=False):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    diagnostic = folder/'gui-diagnostic.json'
    errors = diagnostic.with_suffix('.stderr.log')
    # A failed new process must not inherit a previous probe's capability reason.
    diagnostic.unlink(missing_ok=True)
    errors.unlink(missing_ok=True)
    probe = subprocess.run([str(executable), '--diagnose-gui', '--report', str(diagnostic)],
                           timeout=90, check=False)
    text = diagnostic.read_text(encoding='utf-8')
    if probe.returncode:
        if errors.is_file():
            text += errors.read_text(encoding='utf-8')
        # These are capability errors from the display/GL context, not renderer
        # errors. Keep the exact diagnostic available in the uploaded report.
        absent = ('RatioLab runtime check failed: A graphical desktop session is required for --diagnose-gui',
                  'RatioLab runtime check failed: gdk-gl-error-quark: No GL implementation is available',
                  'RatioLab runtime check failed: gdk-gl-error-quark: Unable to create a GL context')
        # Recognize one complete CLI error only. Mixed warnings, traceback or
        # successful JSON must not turn an application failure into a missing GPU.
        message = text.strip()
        capability_absent = message in absent or any(
            re.fullmatch(re.escape(reason)+r' \([0-9]+\)', message) for reason in absent[1:])
        if probe.returncode != 1 or require or not capability_absent:
            raise RuntimeError(f'Installed GUI diagnostic failed ({probe.returncode}): {text}')
        result = dict(gui='unavailable_on_runner', reason=text, exit_code=probe.returncode)
    else:
        runtime = json.loads(text)
        if not runtime.get('bundled') or runtime.get('preview') != 'rendered':
            raise RuntimeError('Installed GUI probe did not prove the bundled renderer')
        report = folder/'gui-workspace.json'
        _run_workspace([str(executable), '--self-test-gui', '--report', str(report)], report)
        workspace = json.loads(report.read_text(encoding='utf-8'))
        previews = workspace.get('preview_families', [])
        if (workspace.get('self_test') != 'passed' or workspace.get('workspace_export') != 'passed'
                or len(workspace.get('features', {})) != 6
                or not isinstance(previews, list) or not all(isinstance(v, str) for v in previews)
                or len(previews) != len(EXPECTED_FAMILIES) or set(previews) != EXPECTED_FAMILIES
                or any(v != 'passed' for v in workspace['features'].values())):
            raise RuntimeError('Installed GUI workspace/features check failed')
        result = dict(gui='passed', runtime=runtime, workspace=workspace)
    (folder/'gui-result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--require', action='store_true')
    args = parser.parse_args()
    check(args.executable.resolve(), args.folder, args.require)
