"""Try installed GUI/GL on a native runner; only explicit display/GL absence is optional.

An initialized renderer must pass the full workspace test. Missing reports,
crashes, timeouts, shader failures and other application errors remain failures.
"""
import argparse
import json
from pathlib import Path
import subprocess


def check(executable, folder, require=False):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    diagnostic = folder/'gui-diagnostic.json'
    probe = subprocess.run([str(executable), '--diagnose-gui', '--report', str(diagnostic)],
                           timeout=90, check=False)
    text = diagnostic.read_text(encoding='utf-8')
    if probe.returncode:
        # These are capability errors from the display/GL context, not renderer
        # errors. Keep the exact diagnostic available in the uploaded report.
        absent = ('RatioLab runtime check failed: A graphical desktop session is required for --diagnose-gui',
                  'gdk-gl-error-quark: No GL implementation is available',
                  'gdk-gl-error-quark: Unable to create a GL context')
        if probe.returncode != 1 or require or not any(reason in text for reason in absent):
            raise RuntimeError(f'Installed GUI diagnostic failed ({probe.returncode}): {text}')
        result = dict(gui='unavailable_on_runner', reason=text, exit_code=probe.returncode)
    else:
        runtime = json.loads(text)
        if not runtime.get('bundled') or runtime.get('preview') != 'rendered':
            raise RuntimeError('Installed GUI probe did not prove the bundled renderer')
        report = folder/'gui-workspace.json'
        subprocess.run([str(executable), '--self-test-gui', '--report', str(report)],
                       timeout=180, check=True)
        workspace = json.loads(report.read_text(encoding='utf-8'))
        if (workspace.get('self_test') != 'passed' or workspace.get('workspace_export') != 'passed'
                or len(workspace.get('features', {})) != 6
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
