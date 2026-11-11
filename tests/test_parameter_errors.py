# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Constraint identities, transport and recovery, without interpreting prose."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from geometry import validate, generate
from parameter_errors import ParameterError, EngineFailure, field_context, from_kernel, record, compact, SHORT
from rust_geometry import call, call_geometry


class ParameterErrorTests(unittest.TestCase):
    def test_short_ui_messages_preserve_limits_and_all_nine_languages(self):
        from ui_language import catalog, translate
        for value,expected in [('11','Too large. Maximum: 10.'),('0','Too small. Minimum: 0.1.')]:
            with self.assertRaises(ParameterError) as caught:validate('spur',dict(module=value))
            self.assertEqual(compact(caught.exception,'module'),expected)
        with self.assertRaises(ParameterError) as caught:generate('parallel',dict(pinion=80,wheel=60))
        error=caught.exception
        self.assertEqual(compact(error,'pinion'),'Too large. Maximum: 59.')
        self.assertEqual(compact(error,'wheel'),'Too small. Minimum: 81.')
        self.assertEqual(error.record()['field_messages']['pinion'],compact(error,'pinion'))
        with self.assertRaises(ParameterError) as caught:validate('spur',dict(bore=80))
        bound=caught.exception.limits['bore']['upper']
        self.assertIn('Below:',compact(caught.exception,'bore'))
        with self.assertRaises(ParameterError):validate('spur',dict(bore=bound))
        self.assertLess(len(compact(caught.exception,'bore')),len(str(caught.exception)))
        strings=set(SHORT.values())|{'Too large. Below: {value}.','Too large. Maximum: {value}.',
            'Too small. Above: {value}.','Too small. Minimum: {value}.','Allowed: {arg1}–{arg2}.'}
        for code,messages in catalog()['translations'].items():
            for source in strings:
                self.assertIn(source,messages,(code,source))
            translated=translate('Too large. Maximum: 59.',code)
            self.assertIn('59',translated)
            if code!='en':self.assertNotEqual(translated,'Too large. Maximum: 59.')
        self.assertEqual(translate(compact(error,'pinion'),'it'),'Troppo grande. Massimo: 59.')

    def test_numeric_fields_and_kinds_across_every_family(self):
        from geometry import FAMILIES, get_specs
        for family in FAMILIES:
            key = get_specs(family)[0][0]
            for value in (True, 'abc', float('inf'), None):
                with self.subTest(family=family, value=value):
                    with self.assertRaises(ParameterError) as caught:
                        validate(family, {key:value})
                    self.assertEqual(caught.exception.fields, (key,))
                    self.assertEqual(caught.exception.kind, 'input')

    def test_constraints_keep_the_actual_stage_and_shared_fields(self):
        cases = [
            ('spur', dict(bore=80), 'bore.root', {'bore','module','teeth'}),
            ('spur', dict(module=.1,bore=0,backlash=.15), 'backlash.module', {'backlash','module'}),
            ('double', dict(gap=9,width=10,variant='separated'), 'groove.width', {'gap','width'}),
            ('planetary', dict(sun=19), 'planetary.spacing', {'sun','planet','planets'}),
            ('planetary', dict(variant='two_stage',sun2=19), 'planetary.spacing', {'sun2','planet2','planets'}),
            ('harmonic', dict(teeth=61), 'harmonic.even_teeth', {'teeth'}),
            ('harmonic', dict(module=1,wall=4,bore=50), 'harmonic.wall', {'wall','bore','module','teeth'}),
        ]
        for family,values,constraint,fields in cases:
            with self.subTest(family=family,values=values):
                with self.assertRaises(ParameterError) as caught:validate(family,values)
                error = caught.exception
                self.assertEqual(error.constraint,constraint)
                self.assertTrue(fields <= set(error.fields))
                self.assertTrue(error.remedy or constraint=='harmonic.even_teeth')
                if 'sun2' in fields:self.assertNotIn('sun',error.fields)

    def test_rust_native_json_and_binary_diagnostics(self):
        with self.assertRaises(ParameterError) as caught:
            call('cycloid_profile',dict(n=16,radius=40,eccentricity=3,pin=3))
        self.assertEqual(caught.exception.constraint,'cycloidal.eccentricity')
        self.assertEqual(set(caught.exception.fields),{'eccentricity','n','radius'})
        for family,values,constraint,fields in [
            ('cycloidal',dict(eccentric=3),'cycloidal.eccentricity',{'eccentric','pins','radius'}),
            ('harmonic',dict(diaphragm=4,cup_length=4),'harmonic.diaphragm',{'diaphragm','cup_length'}),
            ('worm',dict(bore=30),'worm.bore_root',{'bore','diameter','module'}),
            ('parallel',dict(variant='two_stage',pinion2=80,wheel2=30),'parallel.reduction',{'pinion2','wheel2'}),
        ]:
            with self.subTest(family=family):
                with self.assertRaises(ParameterError) as caught:generate(family,values)
                self.assertEqual(caught.exception.constraint,constraint)
                self.assertEqual(set(caught.exception.fields),fields)

    def test_messages_do_not_control_identity_and_internal_failures_stay_distinct(self):
        for message in ('unrelated text', 'testo italiano', '任意文字'):
            error=ParameterError('test.rule',('a','b'),message,'change dimensions')
            self.assertEqual(from_kernel(error.record()).fields,('a','b'))
            self.assertEqual(from_kernel(json.dumps(error.record())).constraint,'test.rule')
            with self.assertRaises(ParameterError) as caught:
                with field_context(dict(a='second_a',b='second_b')):raise error
            self.assertEqual(caught.exception.fields,('second_a','second_b'))
        self.assertEqual(record(ValueError('eccentric bore: test'))['fields'],[])
        self.assertIsInstance(from_kernel(dict(code='internal_error',message='panic')),EngineFailure)
        self.assertEqual(record(KeyError('broken invariant'))['kind'],'internal')

    def test_bridge_serializes_diagnostics_and_preserves_internal_failure_kind(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge as bridge
        result=json.loads(bridge.dispatch('generate',json.dumps(dict(family='planetary',parameters=dict(sun=19)))))
        self.assertFalse(result['ok'])
        self.assertEqual(set(result['error']['fields']),{'sun','planet','planets'})
        self.assertTrue(result['error']['remedy'])
        with patch.object(bridge._engine,'call',side_effect=KeyError('invariant')):
            result=json.loads(bridge.dispatch('generate','{}'))
        self.assertEqual(result['error']['kind'],'internal')
        self.assertEqual(result['error']['fields'],[])

    def test_wasm_uses_the_same_structured_failure_contract(self):
        root=Path(__file__).resolve().parents[1]
        requests=[dict(operation='cycloid_profile',parameters=dict(n=16,radius=40,eccentricity=3,pin=3)),
                  dict(binary=True,operation='construction_harmonic',parameters=dict(values=validate('harmonic',dict(diaphragm=4,cup_length=4))))]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'requests.json';path.write_text(json.dumps(requests))
            result=subprocess.run(['node',str(root/'tests/rust_wasm_protocol.mjs'),str(root),str(path)],check=True,capture_output=True,text=True)
        plain,binary=json.loads(result.stdout)
        self.assertEqual(plain['error']['constraint'],'cycloidal.eccentricity')
        error=from_kernel(bytes(binary[1:]).decode())
        self.assertEqual(error.constraint,'harmonic.diaphragm')
        self.assertEqual(set(error.fields),{'diaphragm','cup_length'})


if __name__=='__main__':unittest.main()
