# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Minimum searches respect real geometry and nonmonotone field domains."""
from copy import deepcopy
import unittest
from empty_fields import minimum
from geometry import generate,get_specs
from view_navigation import camera_frame
from math import pi


class MinimumTests(unittest.TestCase):
    def test_actual_module_floor_and_active_chamfer_angle(self):
        for values,key,expected in (({},'module','0.302326'),({'semitopping_mm':.2},'semitopping_angle_deg','20.000001'),({},'backlash','0')):
            design=generate('spur',values);before=deepcopy(design.values)
            spec=next(s for s in get_specs('spur') if s[0]==key)
            value=minimum('spur',design.values,key,(spec[3],spec[4],spec[5]))
            self.assertEqual(value,expected)
            self.assertEqual(design.values,before)
            candidate=dict(before);candidate.pop('_decimal_inputs',None);candidate[key]=float(value)
            generate('spur',candidate)
            if key!='backlash':
                candidate[key]-=.000001
                with self.assertRaises(ValueError):generate('spur',candidate)

    def test_disconnected_integer_domain_is_scanned_in_order(self):
        seen=[]
        def accept(v):seen.append(v['z']);return v['z'] in (7,12)
        self.assertEqual(minimum('unused',{'z':12},'z',(2,30,1),accept=accept,integer=True),'7')
        self.assertEqual(seen,[2,3,4,5,6,7])

    def test_cancellation_limits_and_no_false_minimum(self):
        with self.assertRaisesRegex(ValueError,'limit'):
            minimum('unused',{'z':20},'z',(1,100,1),accept=lambda v:False,max_candidates=3)
        def stop():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            minimum('unused',{'z':20},'z',(1,100,1),check=stop)

    def test_simultaneous_module_and_bore_blanks_use_the_final_other_values(self):
        from empty_fields import prepare,Request
        d=generate('spur')
        specs={s[0]:(s[3],s[4],s[5]) for s in get_specs('spur')}
        request=Request('spur',d.values,tuple((k,specs[k]) for k in ('module','bore')),None,{})
        result=prepare(request,lambda:True)
        self.assertEqual(float(result['bore']),0)
        self.assertEqual(float(result['module']),.214286)

    def test_camera_endpoints_wrap_and_positive_scale(self):
        a=(pi-.1,0.,0.,1.,(0,0,0),30.)
        b=(-pi+.1,-1.,.5,2.,(4,8,12),4.)
        self.assertEqual(camera_frame(a,b,0),a);self.assertEqual(camera_frame(a,b,1),b)
        middle=camera_frame(a,b,.5)
        self.assertAlmostEqual(middle[0],pi)
        self.assertEqual(middle[4],(2,4,6))
        self.assertGreater(middle[3],0);self.assertGreater(middle[5],0)
