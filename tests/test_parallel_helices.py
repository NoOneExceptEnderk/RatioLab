# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent normal-system, axial phase and actual moving solid checks."""
from fractions import Fraction
from math import cos, sin, tan, atan, radians, degrees, pi, hypot
from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
from zipfile import ZipFile
import json
import sys
import unittest

from geometry import generate, validate, get_specs, profile_sections, VARIANTS
from parallel_multistage import count, tooth_type, selectors, variant_for, stage_key
from motion import build_plan, transform, rotation, update_operating_rates
from solid_geometry import signature
from stl_export import triangles
from collision_geometry import Surface, relation

NEW = ('two_stage_helical', 'three_stage_helical', 'two_stage_double', 'three_stage_double')


def cases():
    for variant in NEW:
        for style in (('joined','separated') if tooth_type(variant)=='double' else (None,)):
            yield dict(variant=variant, **({'double_style':style} if style else {}))


class ParallelHelicesTests(unittest.TestCase):
    def test_normal_system_reference_benchmark_and_independent_stage_hands(self):
        for options in cases():
            d=generate('parallel',dict(options,helix=15,helix2=-23,helix3=31,layout_angle2=73,layout_angle3=-31))
            self.assertAlmostEqual(2*d.analysis['meshes'][0]['gear1']['pitch_radius']*30/20,62.11657082460498,places=12)
            for stage,q in enumerate(d.analysis['meshes'],1):
                k=lambda key:d.values[stage_key(key,stage)]
                beta=radians(k('helix')); m=k('module'); zp=k('pinion');zw=k('wheel')
                self.assertAlmostEqual(q['center_distance_mm'],m*(zp+zw)/(2*cos(beta)),places=11)
                self.assertAlmostEqual(q['gear1']['alpha_t'],degrees(atan(tan(radians(k('pressure')))/cos(beta))),places=12)
                a,b=[p for p in d.parts if p.port.get('stage')==stage]
                self.assertAlmostEqual(radians(a.twist),k('width')*tan(beta)/(m*zp/(2*cos(beta))),places=12)
                self.assertAlmostEqual(zp*a.twist+zw*b.twist,0,places=11)
                self.assertEqual(q['pinion_helix_deg'],-q['wheel_helix_deg'])
                self.assertEqual(q['gear1']['beta'],-q['gear2']['beta'])
            expected=Fraction(1)
            for stage in range(1,count(d.values)+1):
                expected*=-Fraction(d.values[stage_key('wheel',stage)],d.values[stage_key('pinion',stage)])
            self.assertEqual(d.analysis['signed_ratio'],float(expected))

    def test_independent_selectors_preserve_other_axis_of_choice(self):
        for variant in VARIANTS['parallel']:
            stage,tooth=selectors(variant)
            self.assertEqual([c['value'] for c in stage['choices']], [variant_for(n,tooth_type(variant)) for n in (1,2,3)])
            self.assertEqual([c['value'] for c in tooth['choices']], [variant_for(count({'variant':variant}),t) for t in ('spur','helical','double')])

    def test_double_active_half_overlap_joined_seam_and_independent_grooves(self):
        for options in cases():
            if tooth_type(options['variant'])!='double':continue
            d=generate('parallel',dict(options,width=12,width2=14,width3=16,gap=1.2,gap2=2.3,gap3=3.4,helix=-20,helix2=24,helix3=-17))
            for stage,q in enumerate(d.analysis['meshes'],1):
                k=lambda key:d.values[stage_key(key,stage)]
                gap=0 if options['double_style']=='joined' else (1.2,2.3,3.4)[stage-1]
                self.assertEqual(k('gap'),gap)
                half=(k('width')-gap)/2
                self.assertAlmostEqual(q['contact_overlap'],half*abs(sin(radians(k('helix'))))/(pi*k('module')),places=12)
                a,b=[p for p in d.parts if p.port.get('stage')==stage]
                for p in (a,b):
                    self.assertTrue(p.double)
                    self.assertEqual(p.gap,gap)
                    sections=profile_sections(p)
                    if gap==0:
                        seam=[s for s in sections if abs(s[0]-p.width/2)<1e-12]
                        self.assertEqual(len(seam),1)
                        self.assertIs(seam[0][2],p.outer)
                        self.assertAlmostEqual(seam[0][1],p.twist/2)
                    self.assertGreater(signature(p)['volume_mm3'],0)

    def test_zero_helix_limit_preserves_spur_profiles_centres_and_motion(self):
        for options in cases():
            d=generate('parallel',dict(options,helix=0,helix2=0,helix3=0))
            old=generate('parallel',dict(variant='two_stage' if count(d.values)==2 else 'three_stage'))
            self.assertEqual(d.analysis['parallel_train'],old.analysis['parallel_train'])
            self.assertEqual([p.outer for p in d.parts],[p.outer for p in old.parts])
            self.assertEqual([p.twist for p in d.parts],[p.twist for p in old.parts])
            self.assertEqual([build_plan(d).matrix(i,.7) for i in range(len(d.parts))],[build_plan(old).matrix(i,.7) for i in range(len(old.parts))])

    def test_axial_section_phase_and_actual_contour_clearance_on_folded_stages(self):
        # Ray casting actual contours independently of the recorded tooth phase.
        def inside(x,y,poly):
            hit=False
            for a,b in zip(poly,poly[1:]+poly[:1]):
                if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
            return hit
        def overlap(loops,parts,tips):
            return any(inside(x,y,loops[b]) for a,b in ((0,1),(1,0)) for x,y in loops[a]
                       if hypot(x-parts[b].center[0],y-parts[b].center[1])<tips[b]-1e-9)
        for options in cases():
            d=generate('parallel',dict(options,helix=-25,helix2=18,helix3=-30,layout_angle2=73,layout_angle3=-31))
            plan=build_plan(d)
            for stage,q in enumerate(d.analysis['meshes'],1):
                ids=[i for i,p in enumerate(d.parts) if p.port.get('stage')==stage]
                parts=[d.parts[i] for i in ids]
                # Every emitted axial section includes seam and groove shoulders.
                sections=[profile_sections(p) for p in parts]
                # Sampling counts depend on each pitch radius. Compare at the
                # union of axial stations, interpolating each piecewise profile.
                def at(sections,z):
                    for j in range(len(sections)-1):
                        a,b=sections[j:j+2]
                        if a[0]-1e-12<=z<=b[0]+1e-12:
                            t=(z-a[0])/(b[0]-a[0])
                            outer=a[2] if a[2] is b[2] else [(x*(1-t)+u*t,y*(1-t)+v*t) for (x,y),(u,v) in zip(a[2],b[2])]
                            return z,a[1]*(1-t)+b[1]*t,outer
                    raise AssertionError(z)
                heights=sorted({s[0] for group in sections for s in group})
                tips=[q[k]['tip_radius'] for k in ('gear1','gear2')]
                for z in heights:
                    sa,sb=[at(group,z) for group in sections]
                    self.assertAlmostEqual(q['z1']*sa[1]+q['z2']*sb[1],0,places=10)
                    for phase in (0,.31,1.7):
                        loops=[]
                        for i,p,(z,angle,outer) in zip(ids,parts,(sa,sb)):
                            co,si=cos(radians(angle)),sin(radians(angle))
                            loops.append([transform(plan.matrix(i,phase),(x*co-y*si+p.center[0],x*si+y*co+p.center[1],z+p.z))[:2] for x,y in outer])
                        self.assertFalse(overlap(loops,parts,tips),(options,stage,sa[0],phase))
                # Wrong phase by half a wheel tooth at a full tooth section.
                loops=[]
                for i,p,(z,angle,outer) in zip(ids,parts,(sections[0][0],sections[1][0])):
                    loops.append([transform(plan.matrix(i,0),(x+p.center[0],y+p.center[1],z+p.z))[:2] for x,y in outer])
                cx,cy=parts[1].center;angle=pi/q['z2']
                loops[1]=[(cx+(x-cx)*cos(angle)-(y-cy)*sin(angle),cy+(x-cx)*sin(angle)+(y-cy)*cos(angle)) for x,y in loops[1]]
                self.assertTrue(overlap(loops,parts,tips))

    def test_shared_closed_solids_in_motion_and_wrong_phase_negative_control(self):
        for options in cases():
            d=generate('parallel',dict(options,helix=-22,helix2=27,helix3=-18,layout_angle2=73,layout_angle3=-31))
            plan=build_plan(d)
            ids=[i for i,p in enumerate(d.parts) if p.port.get('stage')==count(d.values)]
            meshes=[list(triangles(d.parts[i])) for i in ids]
            for fraction in (0,.37,.83):
                phase=2*pi/d.values['pinion']*fraction
                surfaces=[Surface([tuple(transform(plan.matrix(i,phase),p) for p in t) for t in mesh]) for i,mesh in zip(ids,meshes)]
                self.assertEqual(relation(*surfaces,1e-6)['kind'],'Separated',(options,fraction))
            wheel=d.parts[ids[1]];cx,cy=wheel.center
            angle=pi/d.analysis['meshes'][-1]['z2']
            wrong=Surface([tuple((cx+(p[0]-cx)*cos(angle)-(p[1]-cy)*sin(angle),cy+(p[0]-cx)*sin(angle)+(p[1]-cy)*cos(angle),p[2]) for p in t) for t in meshes[1]])
            self.assertEqual(relation(Surface(meshes[0]),wrong,1e-6)['kind'],'Intersection')

    def test_forward_reverse_signed_zero_and_rate_only_compound_surfaces(self):
        for options in cases():
            for io in ('forward','reverse'):
                d=generate('parallel',dict(options,io_scheme=io))
                parts=list(d.parts);original=build_plan(d)
                for rpm in (-31.1234567890123,0,27):
                    values=dict(d.values,input_rpm=rpm)
                    d=update_operating_rates(d,values)
                    plan=build_plan(d)
                    speed=d.analysis['kinematics']['shaft_rates_rpm']
                    self.assertAlmostEqual(speed[-1] if io=='reverse' else speed[0],rpm)
                    self.assertAlmostEqual(d.analysis['output']['rpm'],rpm/d.analysis['signed_ratio'])
                    self.assertTrue(all(a.outer is b.outer for a,b in zip(parts,d.parts)))
                    for shaft in range(count(d.values)+1):
                        ids=[i for i,p in enumerate(d.parts) if p.port['shaft']==shaft]
                        self.assertTrue(all(plan.matrix(i,.7)==plan.matrix(ids[0],.7) for i in ids))

    def test_invalid_each_stage_groove_helix_and_hardware_stay_rejected(self):
        for variant in NEW:
            n=count({'variant':variant})
            for stage in range(1,n+1):
                with self.assertRaises(ValueError):generate('parallel',dict(variant=variant,**{stage_key('helix',stage):36}))
                if tooth_type(variant)=='double':
                    for gap in (0,9.5):
                        with self.assertRaises(ValueError):generate('parallel',dict(variant=variant,double_style='separated',**{stage_key('gap',stage):gap}))
            with self.assertRaisesRegex(ValueError,'manual'):generate('parallel',dict(variant=variant,bearing_mode='shaft'))
            with self.assertRaisesRegex(ValueError,'swept-envelope'):generate('parallel',dict(variant=variant,layout_angle2=180))

    def test_worker_project_transactional_rejection_and_canonical_exports(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge as web
        for options in cases():
            values=dict(options,helix2=-23.1234567890123,gap2=2.1234567890123,layout_angle2=73)
            e=web.Engine();r=e.call('generate',dict(family='parallel',parameters=values))
            source=e.design;buffers=list(e.buffers)
            schema=web.schema('parallel',source.values)
            self.assertFalse(schema['bearing_supported']);self.assertFalse(schema['hardware_supported'])
            for field in schema['fields']:self.assertTrue(field['help'],field['key'])
            gaps={f['key'] for f in schema['fields'] if f['key'] in ('gap','gap2','gap3')}
            self.assertEqual(len(gaps),count(source.values) if options.get('double_style')=='separated' else 0)
            with self.assertRaisesRegex(ValueError,'swept-envelope'):e.call('generate',dict(family='parallel',parameters=dict(values,layout_angle2=180)))
            self.assertIs(e.design,source);self.assertEqual(e.buffers,buffers)
            project=e.call('project',dict(design_id=r['design_id']))['project']
            out=web.Engine();imported=out.call('import_project',dict(project=json.loads(json.dumps(project))))
            self.assertEqual(out.design.values,source.values)
            self.assertEqual(out.design.parts,source.parts)
            for kind in ('step','stl','profiles'):
                exported=out.call('export',dict(design_id=imported['design_id'],kind=kind,indices=[0,1]))
                with ZipFile(BytesIO(out.buffers[exported['buffer']])) as archive:self.assertTrue(archive.namelist())
            out.call('rates',dict(design_id=imported['design_id'],phase=.7,rpm_patch=dict(input_rpm=-31.1234567890123)))
            self.assertEqual(out.design.values['input_rpm'],-31.1234567890123)


if __name__=='__main__':unittest.main()
