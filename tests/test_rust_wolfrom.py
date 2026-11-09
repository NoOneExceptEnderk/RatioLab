# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent normal-system oracle and retained source/project/target contracts."""
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from geometry import generate
from precise_numbers import SOURCE_KEY
from rust_geometry import call

ROOT=Path(__file__).resolve().parents[1]
MODULE='0.50000000000000000001'
ANGLE='20.00000000000000000001'


def center_oracle(module, angle):
    # Separate decimal Taylor evaluation; no Rust helpers or binary64 trig.
    with localcontext() as context:
        context.prec=90
        pi=Decimal('3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534')
        x=Decimal(angle)*pi/180
        term=total=Decimal(1)
        for n in range(1,100):
            term *= -x*x/Decimal((2*n-1)*(2*n))
            total += term
        value=Decimal(module)*90/(2*total)
        return format(value.quantize(Decimal('1e-20')),'.20f')


class RustWolfromTests(unittest.TestCase):
    def test_rate_edit_reuses_validated_integer_counts_from_gtk_float_values(self):
        from motion import update_operating_rates
        design=generate('wolfrom',dict(variant='helical'))
        values={key:float(value) if type(value) is int else value for key,value in design.values.items()}
        values['input_rpm']=-600
        updated=update_operating_rates(design,values)
        self.assertEqual(updated.analysis['kinematics']['rates_rpm']['output'],-1)
        for key in ('sun','planet','planet2','output_ring','planets'):
            self.assertIs(type(updated.values[key]),int)
        self.assertIs(updated.parts[0].outer,design.parts[0].outer)
        self.assertEqual(design.values['input_rpm'],600)

    def requests(self):
        return [dict(module=MODULE,sun=18,planet=72,planet2=59,output_ring=135,
                     helix=angle,rpm='600.00000000000000000001')
                for angle in ('0','20','-20','35','-35',ANGLE)]

    def test_normal_interaxis_matches_independent_decimal_oracle(self):
        for args in self.requests():
            with self.subTest(angle=args['helix']):
                result=call('wolfrom_dimensions',args)
                self.assertTrue(result['precision']['agreement'])
                values=result['values']
                self.assertEqual(values['center_distance_mm'],center_oracle(MODULE,args['helix']))
                self.assertEqual(values['signed_ratio'],'600.00000000000000000000')
                self.assertEqual(values['module2_mm'],'0.59210526315789473685')
        for angle in ('90','-90','NaN'):
            with self.subTest(angle=angle),self.assertRaises(ValueError):
                call('wolfrom_dimensions',dict(self.requests()[0],helix=angle))

    def test_actual_wasm_preserves_all_checked_analytic_digits(self):
        requests=[dict(operation='wolfrom_dimensions',parameters=a) for a in self.requests()]
        node=os.environ['RATIOLAB_NODE']
        with TemporaryDirectory() as directory:
            path=Path(directory)/'requests.json';path.write_text(json.dumps(requests))
            child=subprocess.run([node,str(ROOT/'tests/rust_wasm_protocol.mjs'),str(ROOT),str(path)],
                                 check=True,capture_output=True,text=True,timeout=60)
        results=json.loads(child.stdout)
        self.assertEqual(len(results),len(requests))
        for request,result in zip(requests,results):
            self.assertTrue(result['ok'],result)
            self.assertEqual(result['result'],call(request['operation'],request['parameters']))

    def test_legacy_and_new_projects_keep_exact_sources_quality_and_parts(self):
        sys.path.insert(0,str(ROOT/'webapp'))
        import engine_bridge as web
        quality=dict(preview_mm=.1,export_mm=.005)
        for variant,style in (('spur',None),('helical',None),('double','joined'),('double','separated')):
            parameters=dict(variant=variant,module=float(MODULE),**{SOURCE_KEY:{'module':MODULE}})
            if variant!='spur':
                parameters.update(helix=float(ANGLE))
                parameters[SOURCE_KEY]['helix']=ANGLE
            if style:parameters.update(double_style=style)
            with self.subTest(variant=variant,style=style):
                expected=generate('wolfrom',parameters,quality=quality)
                project=dict(format=web.PROJECT_FORMAT,family='wolfrom',parameters=parameters,quality=quality)
                engine=web.Engine();loaded=engine.call('import_project',dict(project=project))
                self.assertEqual(loaded['ignored_parameters'],[])
                self.assertEqual(engine.design.parts,expected.parts)
                saved=engine.call('project',dict(design_id=loaded['design_id']))['project']
                self.assertEqual(saved['quality'],quality)
                self.assertEqual(saved['parameters'][SOURCE_KEY],parameters[SOURCE_KEY])
                restored=web.Engine()
                restored.call('import_project',dict(project=json.loads(json.dumps(saved))))
                self.assertEqual(restored.design.parts,expected.parts)
                self.assertEqual(restored.design.analysis['wolfrom']['analytic_values']['center_distance_mm'],
                                 center_oracle(MODULE,ANGLE if variant!='spur' else '0'))


if __name__=='__main__':unittest.main()
