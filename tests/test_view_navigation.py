# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Camera inverse, 26 cube snaps and screen-space pan invariants."""
import itertools
from math import sqrt
import unittest
from view_navigation import orientation, rotate, pan_delta, cube_patches, hit_cube
from component_geometry import project, ray


class NavigationMathTests(unittest.TestCase):
    def test_all_26_snap_directions_face_camera(self):
        for d in itertools.product((-1,0,1),repeat=3):
            if not any(d):continue
            with self.subTest(direction=d):
                q=rotate(d,*orientation(d))
                self.assertAlmostEqual(q[0],0);self.assertAlmostEqual(q[1],0)
                self.assertAlmostEqual(q[2],sqrt(sum(v*v for v in d)))

    def test_visible_cube_tiles_pick_their_face_edge_or_corner(self):
        for yaw,tilt in ((-.61,-.96),(0,0),(0,-1.5707963267948966),(2,-2.5)):
            patches=cube_patches(yaw,tilt)
            self.assertTrue(patches)
            for _,polygon,direction,*_ in patches:
                x=sum(v[0] for v in polygon)/4;y=sum(v[1] for v in polygon)/4
                self.assertEqual(hit_cube(patches,x,y),direction)
            self.assertIsNone(hit_cube(patches,0,0))

    def test_pan_matches_pixel_drag_at_all_aspects_and_scales(self):
        point=(7,4,9);center=(0,0,0);radius=70
        for width,height,zoom,yaw,tilt in itertools.product((300,1200),(250,850),(.25,1,8),(0,-.61),(0,-.96,-1.5707963267948966)):
            before=project(point,center,radius,zoom,yaw,tilt,width,height)
            delta=pan_delta(47,-23,radius,zoom,width,height,yaw,tilt)
            after=project(point,delta,radius,zoom,yaw,tilt,width,height)
            self.assertAlmostEqual(after[0]-before[0],47)
            self.assertAlmostEqual(after[1]-before[1],-23)
            origin,direction=ray(*after,delta,radius,zoom,yaw,tilt,width,height)
            # The projected point lies on the same inverse camera ray.
            distance=sum((point[i]-origin[i])*direction[i] for i in range(3))
            for i in range(3):self.assertAlmostEqual(origin[i]+direction[i]*distance,point[i])


if __name__=='__main__':unittest.main()
