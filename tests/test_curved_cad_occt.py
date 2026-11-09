# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Optional independent CAD import/edit tests; OCCT is not a runtime dependency."""
import importlib.util
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

import curved_cad
from geometry import generate

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('occt_curved_cad_verifier',ROOT/'scripts/verify-curved-cad.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)


@unittest.skipUnless(importlib.util.find_spec('OCP'),'Independent OCP/OCCT verifier is optional.')
class CurvedCadOcctTests(unittest.TestCase):
    def test_knot_motion_is_measured_even_when_stored_surface_poles_do_not_move(self):
        from OCP.STEPControl import STEPControl_Reader
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_BSplineSurface
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        with TemporaryDirectory() as temporary:
            source=Path(temporary)/'source'
            _,info=curved_cad.export(generate('helical',dict(width=30,helix=35)),source)
            reader=STEPControl_Reader();reader.ReadFile(str(source/'gear.step'));reader.TransferRoots()
            rows=[info['profile']['curves'][0]];sweep=info['sweep'];it=TopExp_Explorer(reader.OneShape(),TopAbs_FACE);surface=None
            while it.More():
                face=TopoDS.Face(it.Current())
                if BRepAdaptor_Surface(face).GetType()==GeomAbs_BSplineSurface:
                    candidate=BRep_Tool.Surface_s(face)
                    if candidate.UDegree()==2 and verifier.reader_tensor_bound(candidate,rows,sweep)['bound_mm']<1e-9:
                        surface=candidate.Copy();break
                it.Next()
            self.assertIsNotNone(surface)
            self.assertGreater(surface.NbVKnots(),2)
            before=[(surface.Pole(i,j).X(),surface.Pole(i,j).Y(),surface.Pole(i,j).Z())
                for i in range(1,surface.NbUPoles()+1) for j in range(1,surface.NbVPoles()+1)]
            surface.SetVKnot(2,surface.VKnot(2)+.0001*(surface.VKnot(3)-surface.VKnot(2)))
            after=[(surface.Pole(i,j).X(),surface.Pole(i,j).Y(),surface.Pole(i,j).Z())
                for i in range(1,surface.NbUPoles()+1) for j in range(1,surface.NbVPoles()+1)]
            self.assertEqual(before,after)
            self.assertGreater(verifier.reader_tensor_bound(surface,rows,sweep)['bound_mm'],1e-9)

    def test_c1_curves_and_surfaces_support_the_strict_boolean_continuity_requirement(self):
        from OCP.STEPControl import STEPControl_Reader
        from OCP.BRepAdaptor import BRepAdaptor_Curve,BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_C0
        from OCP.TopAbs import TopAbs_EDGE,TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        for family,parameters in [('spur',{}),('helical',dict(width=30,helix=-35)),('internal',dict(variant='helical'))]:
            with self.subTest(family=family),TemporaryDirectory() as temporary:
                source=Path(temporary)/'source';curved_cad.export(generate(family,parameters),source)
                reader=STEPControl_Reader();reader.ReadFile(str(source/'gear.step'));reader.TransferRoots();shape=reader.OneShape()
                for kind,cast,adapt in [(TopAbs_EDGE,TopoDS.Edge,BRepAdaptor_Curve),(TopAbs_FACE,TopoDS.Face,BRepAdaptor_Surface)]:
                    it=TopExp_Explorer(shape,kind)
                    while it.More():
                        geometry=adapt(cast(it.Current()))
                        if kind==TopAbs_EDGE:self.assertNotEqual(geometry.Continuity(),GeomAbs_C0)
                        else:
                            self.assertNotEqual(geometry.UContinuity(),GeomAbs_C0)
                            self.assertNotEqual(geometry.VContinuity(),GeomAbs_C0)
                        it.Next()

    def test_helical_and_internal_sweeps_survive_import_rewrite_and_boolean_edit(self):
        for family,parameters in [('helical',dict(helix=-25)),('internal',dict(variant='helical'))]:
            with self.subTest(family=family),TemporaryDirectory() as temporary:
                root=Path(temporary);source=root/'source'
                curved_cad.export(generate(family,parameters),source)
                result=verifier.verify(source,root/'verified')
                self.assertEqual(result['status'],'VERIFIED_BOUNDED_CYLINDRICAL_CAD_PROTOTYPE')
                self.assertTrue(result['cad_edit']['valid'])
                self.assertLess(result['first_import']['sampled_interior_serialization_error_mm'],1e-9)

    def test_interior_surface_corruption_is_rejected_with_unchanged_boundaries(self):
        from OCP.STEPControl import STEPControl_Reader
        from OCP.BRepCheck import BRepCheck_Analyzer
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';output=root/'verified'
            curved_cad.export(generate('helical'),source)
            path=source/'gear.step';text=path.read_text()
            line=next(line for line in text.splitlines() if "=B_SPLINE_SURFACE_WITH_KNOTS('',3,3," in line)
            rows=re.findall(r'\((#\d+(?:,#\d+)*)\)',line)
            row=rows[len(rows)//2];points=re.findall(r'#\d+',row);control=points[len(points)//2]
            pattern=rf"({control}=CARTESIAN_POINT\('',\()([^,]+)(,[^\n]+)"
            text,count=re.subn(pattern,lambda m:m[1]+format(float(m[2])+.01,'.17g')+m[3],text,count=1)
            self.assertEqual(count,1);path.write_text(text)
            reader=STEPControl_Reader();reader.ReadFile(str(path));reader.TransferRoots()
            self.assertTrue(BRepCheck_Analyzer(reader.OneShape(),True,False,True).IsValid())
            with self.assertRaises(ValueError):verifier.verify(source,output)
            self.assertFalse(output.exists())

    def test_import_rewrite_and_edit_preserve_a_valid_curved_solid(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';output=root/'verified'
            curved_cad.export(generate('spur'),source)
            result=verifier.verify(source,output)
            self.assertEqual(result['status'],'VERIFIED_BOUNDED_CURVED_SPUR_PROTOTYPE')
            self.assertTrue(result['cad_edit']['valid'])
            self.assertLess(result['first_import']['sampled_serialization_error_mm'],1e-9)
            self.assertEqual(result['first_import']['solids'],1)
            self.assertEqual(result['occt_write_read']['solids'],1)
            self.assertEqual(json.loads((output/'verification.json').read_text())['source_step_sha256'],result['source_step_sha256'])

    def test_changed_curve_is_rejected_even_with_the_original_accuracy_record(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';output=root/'verified'
            curved_cad.export(generate('spur'),source)
            path=source/'gear.step';text=path.read_text()
            spline=re.search(r"B_SPLINE_CURVE_WITH_KNOTS\('',3,\(([^)]+)\)",text)
            control=re.findall(r'#\d+',spline[1])[1]
            expression=rf"({control}=CARTESIAN_POINT\('',\()([^,]+)(,[^\n]+)"
            text,count=re.subn(expression,lambda m:m[1]+format(float(m[2])+.1,'.17g')+m[3],text,count=1)
            self.assertEqual(count,1)
            path.write_text(text)
            with self.assertRaises(ValueError):verifier.verify(source,output)
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
