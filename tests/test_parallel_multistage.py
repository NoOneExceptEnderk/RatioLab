# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent shaft equations, folded layouts and shared export contracts."""
from fractions import Fraction
from math import cos, sin, pi, hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest
from zipfile import ZipFile
from io import BytesIO

from geometry import generate, validate, get_specs
from motion import build_plan, update_operating_rates, transform
from solid_geometry import signature
from combination_search import search, Settings, estimated_ratio, variables
from interference import expected_interface


class ParallelMultistageTests(unittest.TestCase):
    def test_independent_fraction_benchmarks_and_reversal(self):
        for variant, teeth in [('two_stage', [(20,60),(20,80)]),
                               ('three_stage', [(20,60),(20,80),(20,60)])]:
            expected = [Fraction(1500)]
            for pinion, wheel in teeth:
                expected.append(-expected[-1]*Fraction(pinion, wheel))
            for io in ('forward','reverse'):
                d = generate('parallel', dict(variant=variant, io_scheme=io,
                                             input_rpm=float(expected[-1]) if io == 'reverse' else 1500))
                self.assertEqual(d.analysis['kinematics']['shaft_rates_rpm'], list(map(float,expected)))
                ratio = float(expected[0]/expected[-1])
                self.assertAlmostEqual(d.analysis['signed_ratio'], 1/ratio if io == 'reverse' else ratio)
                self.assertEqual(d.analysis['signed_ratio'], estimated_ratio('parallel', d.values))

    def test_zero_negative_and_noninteger_rpm_have_rigid_compounds(self):
        for rpm in (0., -31.1234567890123, 1500.):
            d = generate('parallel', dict(variant='three_stage',input_rpm=rpm,layout_angle2=90,layout_angle3=-45))
            plan = build_plan(d)
            for shaft in range(4):
                members = [i for i,p in enumerate(d.parts) if p.port['shaft'] == shaft]
                for phase in (0., .7, 200.):
                    self.assertTrue(all(plan.matrix(i,phase) == plan.matrix(members[0],phase) for i in members))
                if not rpm:
                    self.assertEqual(plan.matrix(members[0],1.),plan.matrix(members[0],0.))

    def test_two_turns_are_relative_and_axes_remain_parallel(self):
        d = generate('parallel', dict(variant='three_stage',layout_angle2=90,layout_angle3=-90))
        expected = [(0.,0.),(80.,0.),(80.,100.),(180.,100.)]
        for actual, wanted in zip(d.analysis['parallel_train']['shaft_centers_mm'], expected):
            for a,b in zip(actual,wanted):self.assertAlmostEqual(a,b)
        self.assertTrue(all(not p.frame and not p.axis_x for p in d.parts))
        for sign in (-1,1):
            mirrored=generate('parallel',dict(variant='two_stage',layout_angle2=sign*90))
            c=mirrored.analysis['parallel_train']['shaft_centers_mm'][2]
            self.assertAlmostEqual(c[0],80)
            self.assertAlmostEqual(c[1],sign*100)

    def test_tooth_phase_relation_holds_on_every_folded_pair_through_motion(self):
        d = generate('parallel',dict(variant='three_stage',layout_angle2=73,layout_angle3=-31))
        speeds=d.analysis['kinematics']['shaft_rates_rpm']
        for s,q in enumerate(d.analysis['meshes'],1):
            a,b = [p for p in d.parts if p.port.get('stage')==s]
            theta=d.analysis['parallel_train']['centre_line_angles_rad'][s-1]
            for seconds in (0.,.17,13.):
                phase1=a.profile_metadata['parallel_train']['initial_tooth_phase_rad']+speeds[s-1]*seconds*2*pi/60
                phase2=b.profile_metadata['parallel_train']['initial_tooth_phase_rad']+speeds[s]*seconds*2*pi/60
                residual=q['z1']*phase1+q['z2']*phase2-(q['z1']+q['z2'])*theta-pi*(q['z2']+1)
                self.assertAlmostEqual(sin(residual),0,places=9)
                self.assertAlmostEqual(cos(residual),1,places=9)

    def test_independent_contour_probes_and_wrong_clocking_negative_control(self):
        # Ray casting uses the actual sampled contours, not the phase metadata.
        def inside(x,y,poly):
            hit=False
            for a,b in zip(poly,poly[1:]+poly[:1]):
                if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
                    hit=not hit
            return hit
        def overlap(loops,parts,tips):
            return any(inside(x,y,loops[b]) for a,b in ((0,1),(1,0)) for x,y in loops[a]
                       if hypot(x-parts[b].center[0],y-parts[b].center[1])<tips[b]-1e-9)
        for turn in (0,73,-90):
            d=generate('parallel',dict(variant='three_stage',layout_angle2=turn,layout_angle3=-31))
            plan=build_plan(d)
            for stage in range(1,4):
                ids=[i for i,p in enumerate(d.parts) if p.port.get('stage')==stage]
                parts=[d.parts[i] for i in ids]
                tips=[d.analysis['meshes'][stage-1][key]['tip_radius'] for key in ('gear1','gear2')]
                for phase in (0,.17,.71,1.8,4.2):
                    loops=[[transform(plan.matrix(i,phase),(x+p.center[0],y+p.center[1],p.z))[:2]
                            for x,y in p.outer] for i,p in zip(ids,parts)]
                    self.assertFalse(overlap(loops,parts,tips),(turn,stage,phase))
                # Half a wheel tooth deliberately destroys the solved engagement.
                phase=pi/d.analysis['meshes'][stage-1]['z2']
                cx,cy=parts[1].center
                loops[1]=[(cx+(x-cx)*cos(phase)-(y-cy)*sin(phase),
                           cy+(x-cx)*sin(phase)+(y-cy)*cos(phase)) for x,y in loops[1]]
                self.assertTrue(overlap(loops,parts,tips),'Wrong-clocking negative control missed')

    def test_module_width_and_bores_are_independent_and_hubs_connect_faces(self):
        d=generate('parallel',dict(variant='three_stage',module2=2.3,width2=15,module3=3,width3=7,
                                  intermediate_bore1=7,intermediate_bore2=9,stage_gap=4))
        levels=d.analysis['parallel_train']['stage_levels_mm']
        self.assertEqual(levels,[(0.,10.),(14.,29.),(33.,40.)])
        for shaft in (1,2):
            hub=next(p for p in d.parts if p.name==f'Compound_{shaft}_Hub')
            self.assertEqual(hub.z,levels[shaft-1][1])
            self.assertEqual(hub.z+hub.width,levels[shaft][0])
            owned=[p for p in d.parts if p.port['shaft']==shaft]
            self.assertEqual(len({p.port['rigid_group'] for p in owned}),1)
            self.assertTrue(all(signature(p)['volume_mm3']>0 for p in owned))

    def test_fold_rejected_by_actual_envelopes_not_angle_blacklist(self):
        with self.assertRaisesRegex(ValueError,'swept-envelope clearance'):
            generate('parallel',dict(variant='two_stage',layout_angle2=180))
        # Removing shaft overhang makes the separate axial levels safe at the same turn.
        d=generate('parallel',dict(variant='two_stage',layout_angle2=180,shaft_extension=0))
        self.assertAlmostEqual(d.analysis['parallel_train']['shaft_centers_mm'][-1][0],-20)
        with self.assertRaisesRegex(ValueError,'S2_Wheel and Shaft_4'):
            generate('parallel',dict(variant='three_stage',module3=2))

    def test_invalid_stage_counts_dimensions_and_hub_are_rejected(self):
        cases=[dict(pinion3=20.5),dict(module2=float('nan')),dict(layout_angle2=True),
               dict(layout_angle2=181),dict(layout_angle3=-181),dict(wheel3=20),
               dict(bore=0),dict(output_bore=0),dict(intermediate_bore1=40),dict(hub_wall=20),
               dict(stage_gap=0),dict(backlash2=1,module2=.1),dict(width3=float('inf'))]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                generate('parallel',dict(variant='three_stage',**change))
        for option in (dict(bearing_mode='shaft'),dict(hardware_mode='standard')):
            with self.assertRaisesRegex(ValueError,'single-stage pairs only'):
                generate('parallel',dict(variant='two_stage',**option))

    def test_speed_only_update_retains_surfaces_and_pose_for_every_shaft(self):
        d=generate('parallel',dict(variant='three_stage',layout_angle2=60))
        old=build_plan(d)
        for rpm in (0,-23.1234567890123,4000):
            updated=update_operating_rates(d,dict(d.values,input_rpm=rpm))
            plan=build_plan(updated,previous=old,phase=1.23)
            self.assertIs(d.analysis['parallel_train'],updated.analysis['parallel_train'])
            for i,(a,b) in enumerate(zip(d.parts,updated.parts)):
                self.assertIs(a.outer,b.outer)
                for x,y in zip(old.matrix(i,1.23),plan.matrix(i,1.23)):self.assertAlmostEqual(x,y,places=10)
            self.assertEqual(d.values['input_rpm'],1500)
            self.assertEqual(updated.analysis['output']['rpm'],rpm/-36)

    def test_finite_search_varies_later_stages_with_total_ratio_and_locked_turns(self):
        base=dict(variant='two_stage',layout_angle2=67)
        result=search('parallel',base,{'wheel2':[60,80]},Settings(target=12,tolerance_percent=0,max_seconds=30))
        self.assertTrue(result.complete)
        self.assertEqual(len(result.proposals),1)
        self.assertEqual(result.proposals[0].values['wheel2'],80)
        self.assertEqual(result.proposals[0].values['layout_angle2'],67)
        keys={s[0] for s in variables('parallel',generate('parallel',dict(variant='three_stage')).values)}
        self.assertTrue({'pinion3','wheel3','module3','width3'}<=keys)

    def test_interference_interfaces_distinguish_compounds_and_different_stages(self):
        d=generate('parallel',dict(variant='two_stage'))
        ids={p.name:i for i,p in enumerate(d.parts)}
        self.assertIn('Same rigid',expected_interface(d,ids['S1_Wheel'],ids['S2_Pinion']))
        self.assertIn('Constructed gear mesh',expected_interface(d,ids['S1_Pinion'],ids['S1_Wheel']))
        self.assertEqual(expected_interface(d,ids['S1_Pinion'],ids['S2_Wheel']),'')

    def test_every_solid_has_closed_surfaces_and_actual_exports(self):
        import cad_export,stl_export,profile_export,bom
        from selected_export import subset
        for variant in ('two_stage','three_stage'):
            d=generate('parallel',dict(variant=variant,layout_angle2=45))
            self.assertTrue(all(signature(p)['volume_mm3']>0 for p in d.parts))
            with TemporaryDirectory() as tmp:
                folder=Path(tmp)
                cad_export.write_files(d,folder)
                stl_export.export(d,folder/'model')
                profile_export.write_files(d,folder)
                bom.export(d,folder/'model')
                text=(folder/'model.bom.txt').read_text()
                self.assertIn('Shaft 3: +125 rpm',text)
                for suffix in ('.step','.stl','.svg','.dxf'):
                    self.assertTrue(any(p.stat().st_size>100 for p in folder.rglob('*'+suffix)),suffix)
            chosen=subset(d,[1,2,7])
            self.assertEqual(len(chosen.parts),3)
            self.assertEqual([p.port for p in chosen.parts],[d.parts[i].port for i in (1,2,7)])


class BrowserMultistageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge
        cls.web=engine_bridge

    def test_separate_selectors_use_only_existing_variant_values(self):
        from geometry import VARIANTS
        for variant in VARIANTS['parallel']:
            stage_count=tooth_count=3
            s=self.web.schema('parallel',dict(variant=variant))
            stage,tooth=s['parallel_selectors']
            self.assertEqual([stage['key'],tooth['key']],['stage_count','tooth_type'])
            self.assertEqual(len(stage['choices']),stage_count)
            self.assertEqual(len(tooth['choices']),tooth_count)
            for control in (stage,tooth):
                self.assertEqual(control['option_key'],'variant')
                self.assertEqual(control['value'],variant)
                self.assertIn(variant,[c['value'] for c in control['choices']])
                self.assertTrue(control['help'])
            self.assertNotIn('stage_count',[o['key'] for o in s['options']])
        self.assertNotIn('parallel_selectors',self.web.schema('internal'))

    def test_schema_exposes_active_stages_help_and_end_shaft_ports(self):
        for variant,last in (('two_stage',3),('three_stage',4)):
            s=self.web.schema('parallel',dict(variant=variant))
            fields={f['key']:f for f in s['fields']}
            self.assertIn('layout_angle2',fields)
            self.assertEqual('layout_angle3' in fields,last==4)
            self.assertTrue(all(f['help'] for f in fields.values()))
            self.assertEqual(fields['pinion3' if last==4 else 'pinion2']['type'],'integer')
            self.assertFalse(s['bearing_supported'])
            self.assertFalse(s['hardware_supported'])
            io=next(f for f in s['options'] if f['key']=='io_scheme')
            self.assertIn(f'shaft {last}',io['choices'][0]['label'])

    def test_failed_fold_preserves_worker_design_buffers_and_source_id(self):
        e=self.web.Engine()
        result=e.call('generate',dict(family='parallel',parameters=dict(variant='two_stage',layout_angle2=90)))
        old,plan,buffers,identity=e.design,e.plan,list(e.buffers),e.design_id
        with self.assertRaisesRegex(ValueError,'swept-envelope'):
            e.call('generate',dict(family='parallel',parameters=dict(variant='two_stage',layout_angle2=180)))
        self.assertIs(e.design,old)
        self.assertIs(e.plan,plan)
        self.assertEqual(e.design_id,identity)
        self.assertEqual(e.buffers,buffers)
        self.assertEqual(e.call('project',dict(design_id=result['design_id']))['project']['parameters'],old.values)

    def test_project_and_selected_export_roundtrip_and_rates(self):
        e=self.web.Engine()
        values=dict(variant='three_stage',layout_angle2=73.1234567890123,layout_angle3=-40,intermediate_bore1=7)
        r=e.call('generate',dict(family='parallel',parameters=values))
        project=e.call('project',dict(design_id=r['design_id']))['project']
        imported=self.web.Engine()
        out=imported.call('import_project',dict(project=json.loads(json.dumps(project))))
        self.assertEqual(out['values'],e.design.values)
        self.assertEqual(out['analysis'],e.design.analysis)
        exported=imported.call('export',dict(design_id=out['design_id'],kind='step',indices=[0,1,2]))
        with ZipFile(BytesIO(imported.buffers[exported['buffer']])) as z:
            self.assertEqual(len([s for s in z.namelist() if s.startswith('step-parts/') and s.endswith('.step')]),3)
        rate=imported.call('rates',dict(design_id=out['design_id'],phase=.7,rpm_patch=dict(input_rpm=31.1234567890123)))
        self.assertAlmostEqual(imported.design.analysis['output']['rpm'],31.1234567890123/-36)


if __name__=='__main__':unittest.main()
