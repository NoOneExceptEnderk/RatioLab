# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Paper orientation, rolled navigation and real foreground triangle clipping."""
from math import cos, sin, sqrt, pi
import itertools
import unittest

from geometry import Part, generate
from tooth_tip_preview import _plane, supported
from component_geometry import project,ray
from view_navigation import (plane_axes,paper_orientation,rotate,pan_delta,
                            bounds_in_front,triangle_in_front,cube_patches,hit_cube)


def rigid(v):
    # Independent Rodrigues rotation around a non-cardinal world axis.
    axis=(1/sqrt(14),2/sqrt(14),3/sqrt(14));c,s=cos(.73),sin(.73)
    cross=(axis[1]*v[2]-axis[2]*v[1],axis[2]*v[0]-axis[0]*v[2],axis[0]*v[1]-axis[1]*v[0])
    dot=sum(a*b for a,b in zip(axis,v))
    return tuple(c*x+s*y+(1-c)*dot*z for x,y,z in zip(v,cross,axis))


class ToothViewGeometryTests(unittest.TestCase):
    def vector(self,a,b):
        for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=10)

    def test_all_rotated_planes_are_normal_to_camera_and_local_up_is_vertical(self):
        for n in itertools.product((-1,0,1),repeat=3):
            if not any(n):continue
            up=(0,0,1) if n[:2]!=(0,0) else (0,1,0)
            for transform in (lambda p:p,rigid):
                _,u,normal=plane_axes(transform(n),transform(up))
                angles=paper_orientation(normal,u)
                self.vector(rotate(normal,*angles),(0,0,1))
                self.vector(rotate(u,*angles),(0,1,0))

    def test_real_differential_axes_and_legacy_x_axis_do_not_use_world_z(self):
        d=generate('differential')
        for part,expected in zip(d.parts[:3],((1,0,0),(-1,0,0),(0,0,1))):
            self.assertTrue(supported(part))
            normal,up=_plane(part,(0,1))
            self.vector(normal,expected)
            self.vector(rotate(normal,*paper_orientation(normal,up)),(0,0,1))
        part=Part('Turned gear',[(1,0),(0,1),(-1,0)],axis_x=True)
        self.vector(_plane(part,(0,1))[0],(1,0,0))
        frame=((13,-7,21),rigid((1,0,0)),rigid((0,1,0)),rigid((0,0,1)))
        part=Part('Oblique gear',[(1,0),(0,1),(-1,0)],frame=frame)
        self.vector(_plane(part,(0,1))[0],rigid((0,0,1)))

    def test_rolled_pan_projection_and_inverse_ray_agree_at_all_aspects(self):
        p=(7,4,9);center=(0,0,0)
        for w,h,roll in itertools.product((300,1200),(250,850),(-pi,-1.2,.3,pi/2)):
            yaw,tilt=-.61,-.96
            before=project(p,center,70,1.7,yaw,tilt,w,h,roll)
            delta=pan_delta(47,-23,70,1.7,w,h,yaw,tilt,roll)
            after=project(p,delta,70,1.7,yaw,tilt,w,h,roll)
            self.assertAlmostEqual(after[0]-before[0],47)
            self.assertAlmostEqual(after[1]-before[1],-23)
            origin,direction=ray(*after,delta,70,1.7,yaw,tilt,w,h,roll)
            distance=sum((p[i]-origin[i])*direction[i] for i in range(3))
            self.vector(tuple(origin[i]+distance*direction[i] for i in range(3)),p)

    def test_foreground_clipping_handles_crossing_triangles_and_rejects_back_and_sides(self):
        axes=plane_axes((0,0,1),(0,1,0));target=(0,0,0)
        cases=[([(-.5,-.5,2),(.5,-.5,2),(0,.5,2)],True),
            ([(-.5,-.5,-2),(.5,-.5,-2),(0,.5,-2)],False),
            ([(3,0,2),(4,0,2),(3,1,2)],False),
            ([(-10,-10,2),(10,-10,2),(0,10,2)],True),
            ([(-1,-1,0),(1,-1,0),(0,1,0)],False),
            ([(0,-1,-2),(0,1,2),(0,-1,2)],False),
            ([(-2,-2,-1),(2,-2,2),(0,2,2)],True)]
        for triangle,expected in cases:
            self.assertEqual(triangle_in_front(triangle,target,axes,1),expected)
            shift=(13,-7,21)
            moved=[tuple(a+b for a,b in zip(rigid(q),shift)) for q in triangle]
            moved_axes=tuple(rigid(q) for q in axes)
            self.assertEqual(triangle_in_front(moved,shift,moved_axes,1),expected)
        self.assertFalse(bounds_in_front(((-1,-1,-3),(1,1,-2)),target,axes,1))
        self.assertTrue(bounds_in_front(((-10,-10,1),(10,10,2)),target,axes,1))

    def test_navigation_cube_hit_regions_follow_roll(self):
        for roll in (-1.2,0,.7,pi):
            patches=cube_patches(-.61,-.96,roll=roll)
            for _,polygon,direction,*_ in patches:
                x=sum(q[0] for q in polygon)/4;y=sum(q[1] for q in polygon)/4
                self.assertEqual(hit_cube(patches,x,y),direction)


if __name__=='__main__':unittest.main()
