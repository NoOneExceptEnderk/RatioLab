#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Required native/Wasm regressions, shared by local development and CI."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
CORE=(
    'test_kernel_gate',
    'test_geometry_error_budget',
    'test_total_error_budget','test_helical_total_error_budget',
    'test_fine_sampling',
    'test_rust_kernel','test_rust_new_families','test_rust_wolfrom','test_surface_accuracy','test_precise_numbers',
    'test_engine_reuse','test_collision_reuse','test_surface_snapshots',
    'test_bulk_geometry','test_engine_report_regressions','test_geometry_quality','test_model_precision',
    'test_internal_pair_correction','test_cylindrical_validation',
    'test_tooth_profiles','test_tooth_thickness','test_tooth_tips','test_engineering',
    'test_motion','test_motion_rates','test_stl_export',
    'test_parallel_multistage','test_rack_geometry','test_project_document','test_backlash_solver',
    'test_webapp_project_import',
)
GUI=('test_geometry_quality_gui','test_geometry_refresh_gui','test_window_remap_gui',
     'test_precise_numbers_gui','test_backlash_ui','test_parallel_multistage_gui','test_rack_gui',
     'test_bevel_pair_gui','test_hypoid_gui','test_face_gears_gui','test_tooth_tips_gui',
     'test_model_precision_gui','test_settings_gui','test_custom_themes_gui',
     'test_keyboard_shortcuts_gui','test_mouse_navigation_gui','test_phase_slider_gui',
     'test_header_layout_gui','test_text_rendering_gui')


def preflight():
    from rust_geometry import call
    args=dict(teeth=24,module='2.00000000000000000001')
    native=call('cylindrical_dimensions',args)
    if native['values']['pitch_radius_mm']!='24.00000000000000000012':
        raise RuntimeError('Native exact-source geometry preflight failed.')
    node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
    if not node:raise RuntimeError('Node.js is required; Wasm coverage cannot be skipped.')
    os.environ['RATIOLAB_NODE']=node
    wasm=ROOT/'target/wasm32-unknown-unknown/release/ratiolab_geometry.wasm'
    if not wasm.is_file():raise RuntimeError('Build the required Wasm kernel before testing.')
    with tempfile.TemporaryDirectory(prefix='ratiolab-kernel-preflight-') as folder:
        request=Path(folder)/'requests.json'
        request.write_text(json.dumps([dict(operation='cylindrical_dimensions',parameters=args)]))
        completed=subprocess.run([node,str(ROOT/'tests/rust_wasm_protocol.mjs'),str(ROOT),str(request)],
            check=True,capture_output=True,text=True,timeout=60)
        result=json.loads(completed.stdout)
    if len(result)!=1 or not result[0].get('ok') or result[0]['result']!=native:
        raise RuntimeError('The actual Wasm exact-source result disagrees with native.')
    return dict(native=True,wasm=True,node=node)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui',action='store_true',help='Require the display-backed GTK/GL regression suite.')
    parser.add_argument('--report',type=Path,help='Write execution evidence, including skips and failures.')
    parser.add_argument('--tests',nargs='+',help='Run an explicitly labelled custom subset instead of the required suite.')
    args=parser.parse_args(argv)
    if args.report:args.report=args.report.resolve()
    sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
    os.chdir(ROOT)
    started=time.monotonic()
    record=dict(suite='custom' if args.tests else 'gui' if args.gui else 'core',
                modules=list(args.tests or (GUI if args.gui else CORE)),preflight=None)
    try:
        record['preflight']=preflight()
        with tempfile.TemporaryDirectory(prefix='ratiolab-kernel-profile-') as profile:
            profile_root=Path(profile)
            isolated={key:str(profile_root/name) for key,name in (
                ('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),
                ('APPDATA','roaming'),('LOCALAPPDATA','local'))}
            isolated['RATIOLAB_UPDATE_CHECK']='0'
            with patch.dict(os.environ,isolated):
                if args.gui and not args.tests:
                    # GTK application/timer state and native chooser callbacks
                    # outlive a test's destroyed application. Isolate every case,
                    # so retiring one application cannot create dialogs in the
                    # next case's process. Keep the original assertions intact.
                    def cases(suite):
                        for item in suite:
                            if isinstance(item, unittest.TestSuite):
                                yield from cases(item)
                            else:
                                yield item.id()
                    selected=list(cases(unittest.defaultTestLoader.loadTestsFromNames(record['modules'])))
                    children=[]
                    for index, test in enumerate(selected):
                        output=profile_root/('case-'+str(index)+'.json')
                        child=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--gui',
                            '--tests',test,'--report',str(output)])
                        evidence=json.loads(output.read_text()) if output.is_file() else dict(successful=False,errors=1)
                        children.append(dict(module=test.split('.')[0],test=test,returncode=child.returncode,result=evidence))
                    record.update(children=children,
                        tests=sum(c['result'].get('tests',0) for c in children),
                        failures=sum(c['result'].get('failures',0) for c in children),
                        errors=sum(c['result'].get('errors',0) for c in children),
                        skips=[dict(module=c['module'],**skip) for c in children for skip in c['result'].get('skips',[])],
                        successful=bool(children) and all(c['returncode']==0 and c['result'].get('successful') for c in children))
                else:
                    suite=unittest.defaultTestLoader.loadTestsFromNames(record['modules'])
                    result=unittest.TextTestRunner(verbosity=2).run(suite)
                    record.update(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                        skips=[dict(test=str(test),reason=reason) for test,reason in result.skipped],
                        successful=result.wasSuccessful() and not result.skipped and result.testsRun>0)
    except Exception as error:
        record.update(successful=False,error=f'{type(error).__name__}: {error}')
        print(record['error'],file=sys.stderr)
    record['seconds']=time.monotonic()-started
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(record,indent=2)+'\n')
    if record.get('skips'):print('Required kernel coverage was skipped; check failed.',file=sys.stderr)
    return 0 if record['successful'] else 1


if __name__=='__main__':raise SystemExit(main())
