# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Fine defaults, independent triangle witnesses and explicit resource failures."""
from collections import Counter
from dataclasses import replace
from math import cos,sin,radians,hypot,sqrt
import ctypes,json,os,shutil,struct,subprocess,tempfile,unittest
from pathlib import Path
from geometry import generate,profile_sections
from geometry_quality import representation
from preview3d import build_scene
from rust_surfaces import clear_surface_cache
from solid_geometry import sampling_report,rings,section_loops
from stl_export import write_stl
from test_surface_accuracy import ideal,triangle_weights
import rust_geometry as kernel


def deviation(part,sections,levels):
    maximum=0.
    for i,((za,aa,oa),(zb,ab,ob)) in enumerate(zip(sections,sections[1:])):
        original_a=section_loops(part,oa,za);original_b=section_loops(part,ob,zb)
        c,s=cos(radians(aa)),sin(radians(aa))
        for loop_index,(lower,upper) in enumerate(zip(levels[i],levels[i+1])):
            source_a=original_a[loop_index];source_b=original_b[loop_index];j=0;mapping=[]
            for index,q in enumerate(lower):
                x=q[0]-part.center[0];y=q[1]-part.center[1];xy=(x*c+y*s,-x*s+y*c)
                if index and hypot(xy[0]-source_a[(j+1)%len(source_a)][0],xy[1]-source_a[(j+1)%len(source_a)][1])<1e-9:j=(j+1)%len(source_a)
                a=source_a[j];b=source_a[(j+1)%len(source_a)];d=(b[0]-a[0],b[1]-a[1]);den=d[0]**2+d[1]**2
                u=((xy[0]-a[0])*d[0]+(xy[1]-a[1])*d[1])/den
                mapping.append((j,u))
            for k in range(0,len(lower),max(1,len(lower)//19)):
                end=(k+1)%len(lower);j,u0=mapping[k];j1,u1=mapping[end]
                if j1!=j:u1=1.
                a,b=source_a[j],source_a[(j+1)%len(source_a)]
                c0,d=source_b[j],source_b[(j+1)%len(source_b)]
                for t in (.17,.53,.89):
                    for u in (.23,.68):
                        triangle,weights=triangle_weights(u,t,part.alternate_diagonal)
                        if part.alternate_diagonal:triangles=[(lower[k],lower[end],upper[k]),(lower[end],upper[end],upper[k])]
                        else:triangles=[(lower[k],lower[end],upper[end]),(lower[k],upper[end],upper[k])]
                        actual=tuple(sum(weights[v]*triangles[triangle][v][axis] for v in range(3)) for axis in range(3))
                        xi=u0+u*(u1-u0)
                        xy=tuple((1-t)*(a[axis]+xi*(b[axis]-a[axis]))+t*(c0[axis]+xi*(d[axis]-c0[axis])) for axis in range(2))
                        wanted=ideal(part,xy,za+t*(zb-za),aa+t*(ab-aa))
                        maximum=max(maximum,sqrt(sum((x-y)**2 for x,y in zip(actual,wanted))))
    return maximum


class FineSamplingTests(unittest.TestCase):
    def tearDown(self):clear_surface_cache()

    def test_four_previous_default_rejections_meet_both_unchanged_budgets(self):
        for family,variant in [('planetary','double'),('planetary','two_stage_double'),('parallel','double'),('internal','double')]:
            with self.subTest(family=family,variant=variant):
                design=generate(family,dict(variant=variant),quality=dict(preview_mm=.005,export_mm=.005))
                for part in representation(design,'export').parts:
                    r=sampling_report(part)
                    if r['status']=='bounded':
                        self.assertLessEqual(r['interpolation_bound_mm'],.005)
                        self.assertLessEqual(r['side_faces_upper_bound'],250000)
                scene=build_scene(design)
                self.assertLessEqual(4*(len(scene.vertices)+len(scene.materials)),128*1024**2)
                self.assertGreater(len(scene.vertices),0)
                if variant=='two_stage_double':self.assertEqual(len(scene.materials),0)
                del scene;clear_surface_cache()

    def test_refined_triangles_match_the_same_continuous_reference_and_detect_damage(self):
        part=representation(generate('internal',dict(variant='double'),quality=dict(export_mm=.005)),'export').parts[0]
        report=sampling_report(part);self.assertIn('collinear_edge_refinement',report)
        sections=profile_sections(part);levels=rings(part)
        self.assertLessEqual(deviation(part,sections,levels),report['interpolation_bound_mm']+1e-9)
        damaged=[[[tuple((q[0],q[1],q[2]+.1)) for q in loop] for loop in level] for level in levels]
        self.assertGreater(deviation(part,sections,damaged),report['interpolation_bound_mm'])

    def test_fine_ring_stl_retains_closed_edge_pairs(self):
        part=representation(generate('internal',dict(variant='double'),quality=dict(export_mm=.005)),'export').parts[1]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ring.stl';write_stl(path,[part]);data=path.read_bytes()
        edges=Counter();degenerate=0
        for offset in range(84,len(data),50):
            a,b,c=[data[offset+12+i*12:offset+24+i*12] for i in range(3)]
            if a==b or b==c or c==a:degenerate+=1;continue
            for x,y in [(a,b),(b,c),(c,a)]:edges[x+y if x<y else y+x]+=1
        self.assertEqual(degenerate,0)
        self.assertTrue(edges);self.assertTrue(all(count==2 for count in edges.values()))

    def test_constant_material_protocol_requires_explicit_zero_fill_and_owned_vertices(self):
        meta=dict(format='ratiolab.preview-buffer/1',vertex_floats=12,material_floats=0,material_fill='zero',scene=dict(parts=[],grid=[0,2]))
        vertices=struct.pack('<12f',*range(12))
        encoded=json.dumps(meta).encode();packet=b'\0'+struct.pack('<I',len(encoded))+encoded+vertices
        source=ctypes.create_string_buffer(packet)
        native=kernel._native_preview(ctypes.addressof(source),len(packet),None)
        wasm=kernel._decode_preview(memoryview(packet)[1:])
        self.assertEqual(native[1].tobytes(),vertices);self.assertEqual(wasm[1].tobytes(),vertices)
        self.assertEqual(len(native[2]),0);self.assertEqual(len(wasm[2]),0)
        ctypes.memset(ctypes.addressof(source),0,len(packet));self.assertEqual(native[1].tobytes(),vertices)
        for fill in (None,'one',True):
            bad=dict(meta,material_fill=fill)
            with self.assertRaises(RuntimeError):kernel._preview_layout(bad,len(vertices))

    def test_impossible_target_keeps_its_explicit_failure(self):
        from test_surface_accuracy import fixture
        with self.assertRaisesRegex(ValueError,'budget|resolution'):
            sampling_report(fixture(double=True,gap=2.,core_radius=46.,surface_tolerance_mm=1e-30))

    def test_actual_wasm_fine_meshes_and_large_zero_material_packet(self):
        from component_geometry import displayed_part,explosion_offset
        from precise_numbers import transport
        from solid_geometry import kernel_part,PALETTE
        root=Path(__file__).resolve().parents[1]
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        self.assertTrue(node,'Node.js is required for actual Fine Wasm coverage')
        for family,variant in [('planetary','double'),('planetary','two_stage_double'),('parallel','double'),('internal','double')]:
            with self.subTest(family=family,variant=variant),tempfile.TemporaryDirectory() as folder:
                design=generate(family,dict(variant=variant),quality=dict(preview_mm=.005,export_mm=.005))
                parts=[]
                for index,source in enumerate(design.parts):
                    if source.role in ('support','housing'):continue
                    part=displayed_part(design,index,False);report=sampling_report(part)
                    normal=part.frame[3] if part.frame else ((1,0,0) if part.axis_x else (0,0,1))
                    color=PALETTE[index%len(PALETTE)] if part.color==(.35,.72,.9) else part.color
                    meta=dict(source_index=index,color=color,explosion=explosion_offset(design,index),
                        bottom_normal=tuple(-x for x in normal),top_normal=normal,
                        groove_sections=[],flexspline=False)
                    parts.append(dict(source=transport(kernel_part(part)),meta=meta,faces=report.get('side_faces_upper_bound')))
                scene=build_scene(design)
                fixture=dict(family=family,variant=variant,parts=parts,
                    vertex_floats=len(scene.vertices),material_floats=len(scene.materials))
                del scene;clear_surface_cache()
                path=Path(folder)/'input.json';path.write_text(json.dumps(fixture))
                child=subprocess.run([node,str(root/'tests/rust_fine_wasm.mjs'),str(root),str(path)],
                    capture_output=True,text=True,timeout=120)
                self.assertEqual(child.returncode,0,child.stderr)
                result=json.loads(child.stdout);self.assertTrue(result['actual_wasm'])
                self.assertLessEqual(result['preview_bytes'],128*1024**2)
