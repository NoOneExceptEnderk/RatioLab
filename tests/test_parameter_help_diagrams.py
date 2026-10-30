# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Headless technical drawing coverage, dimensions and annotation layout."""
import math
import unittest

import cairo
from parameter_help import coverage_rows, lookup
from parameter_help_diagrams import (diagram_kind, draw_diagram, gear_outline,
                                     pressure_contact_geometry)


def render(family, key, *, values=None, width=360, height=220):
    surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height)
    context=cairo.Context(surface)
    info=draw_diagram(None,context,width,height,lookup(family,key),
                      key=key,family=family,values=values)
    surface.flush()
    return surface,info


class ParameterHelpDiagramTests(unittest.TestCase):
    def test_every_illustrated_live_control_has_unclipped_nonoverlapping_labels(self):
        checked=set()
        for row in coverage_rows():
            for key in row['parameters']+row['options']:
                pair=(row['family'],key)
                if pair in checked:continue
                checked.add(pair)
                with self.subTest(family=pair[0],key=key):
                    _,info=render(*pair)
                    if info.kind=='text':
                        self.assertFalse(info.labels)
                        continue
                    self.assertTrue(info.labels)
                    for label in info.labels:
                        self.assertGreaterEqual(label.x,7,label.text)
                        self.assertGreaterEqual(label.y,5,label.text)
                        self.assertLessEqual(label.x+label.width,353,label.text)
                        self.assertLessEqual(label.y+label.height,215,label.text)
                    for index,a in enumerate(info.labels):
                        for b in info.labels[index+1:]:
                            x=min(a.x+a.width,b.x+b.width)-max(a.x,b.x)
                            y=min(a.y+a.height,b.y+b.height)-max(a.y,b.y)
                            self.assertFalse(x>2 and y>2,(a.text,b.text))

    def test_selected_cycloidal_quantities_produce_distinct_active_features(self):
        keys=('radius','pin_radius','eccentric','output_radius','output_pin','output_clearance','clearance','pins','output_count')
        drawings=[]
        for key in keys:
            surface,info=render('cycloidal',key)
            raw=bytes(surface.get_data())
            drawings.append(raw)
            # BGRA32 on the supported little-endian build: the selected orange
            # dimension/feature must occupy visible pixels, not only a caption.
            orange=sum(raw[i+2]>180 and raw[i+1]<155 and raw[i]<100
                       for i in range(0,len(raw),4))
            self.assertGreater(orange,30,key)
        self.assertEqual(len(set(drawings)),len(keys))

    def test_family_reference_planes_and_structural_variants_dispatch_separately(self):
        self.assertEqual(diagram_kind('spur','module'),'module')
        self.assertEqual(diagram_kind('worm','module'),'worm')
        self.assertEqual(diagram_kind('differential','module'),'cone')
        self.assertEqual(diagram_kind('harmonic','width'),'cup')
        self.assertEqual(diagram_kind('parallel','center_extra'),'centre_distance')
        self.assertEqual(diagram_kind('cycloidal','print_bolt_pitch'),'printed_bolts')
        _,single=render('helical','helix')
        _,double=render('planetary','helix',values={'variant':'two_stage_double'})
        joined,_=render('double','double_style',values={'variant':'joined'})
        separated,_=render('double','double_style',values={'variant':'separated'})
        self.assertEqual(single.kind,'helix')
        self.assertEqual(double.kind,'double_helix')
        self.assertNotEqual(bytes(joined.get_data()),bytes(separated.get_data()))

    def test_text_only_options_do_not_paint_unrelated_geometry(self):
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,360,220)
        context=cairo.Context(surface)
        context.set_source_rgb(.15,.25,.35);context.paint();surface.flush()
        before=bytes(surface.get_data())
        for key in ('variant','hardware_keys','hardware_retaining','configuration','ratio_mode'):
            result=draw_diagram(None,context,360,220,lookup('differential',key),
                                key=key,family='differential')
            self.assertEqual(result.kind,'text')
            surface.flush()
            self.assertEqual(bytes(surface.get_data()),before)

    def test_contact_normal_is_perpendicular_to_flank_tangent(self):
        contact,normal,tangent=pressure_contact_geometry()
        self.assertEqual(contact[1],118.)
        self.assertAlmostEqual(sum(a*b for a,b in zip(normal,tangent)),0.,places=14)
        self.assertAlmostEqual(math.hypot(*normal),1.,places=14)
        self.assertAlmostEqual(math.hypot(*tangent),1.,places=14)

    def test_worm_axial_section_distinguishes_straight_za_from_zi(self):
        za,_=render('worm','pressure',values={'variant':'za'})
        zi,_=render('worm','pressure',values={'variant':'zi'})
        self.assertNotEqual(bytes(za.get_data()),bytes(zi.get_data()))

    def test_gear_silhouette_scales_without_changing_count(self):
        small=gear_outline(0,0,35,16)
        large=gear_outline(0,0,57,16)
        self.assertEqual(len(small),len(large))
        self.assertEqual(len(small)%16,0)
        for a,b in zip(small,large):
            self.assertAlmostEqual(a[0]*57/35,b[0],places=10)
            self.assertAlmostEqual(a[1]*57/35,b[1],places=10)
        self.assertAlmostEqual(small[0][0],small[-1][0],places=10)
        self.assertAlmostEqual(small[0][1],small[-1][1],places=10)

    def test_renderer_restores_context_and_does_not_paint_outside_viewport(self):
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,600,400)
        context=cairo.Context(surface)
        context.set_source_rgb(.1,.2,.3);context.paint()
        surface.flush();before=bytes(surface.get_data())
        context.translate(70,50)
        context.set_line_width(7)
        matrix=context.get_matrix()
        draw_diagram(None,context,360,220,lookup('spur','module'),key='module',family='spur')
        self.assertEqual(tuple(context.get_matrix()),tuple(matrix))
        self.assertEqual(context.get_line_width(),7)
        surface.flush();data=bytes(surface.get_data());stride=surface.get_stride()
        for y in range(400):
            if y<50 or y>=270:
                self.assertEqual(data[y*stride:(y+1)*stride],before[y*stride:(y+1)*stride])
            else:
                self.assertEqual(data[y*stride:y*stride+70*4],before[y*stride:y*stride+70*4])
                self.assertEqual(data[y*stride+430*4:(y+1)*stride],before[y*stride+430*4:(y+1)*stride])
        # A nonmatching viewport preserves aspect ratio and annotation geometry.
        _,wide=render('spur','width',width=540,height=220)
        _,normal=render('spur','width')
        self.assertEqual(wide.labels,normal.labels)


if __name__=='__main__':
    unittest.main()
