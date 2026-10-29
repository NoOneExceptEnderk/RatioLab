# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Logarithmic trace indexing and shared section/export invariants."""
from itertools import product
import json
from math import sin, cos, tan, log, atan2, hypot, radians, pi
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from geometry import generate, profile_sections, section_holes, circle_info
from differential_wrist import spiral_trace, TRACE_CHORD_TOLERANCE
from solid_geometry import signature, faces
from ratiolab_agent import AgentService
import cad_export
import stl_export


def angle_difference(a,b):
    value=atan2(a[1],a[0])-atan2(b[1],b[0])
    return atan2(sin(value),cos(value))


class DifferentialSpiralTests(unittest.TestCase):
    def test_reference_trace_has_the_requested_constant_tangent_angle(self):
        for hand,beta,delta in product((-1,1),(1,35,45),(radians(15),pi/4,radians(75))):
            for distance in (24,29,35):
                step=distance*1e-5
                derivative=(spiral_trace(distance+step,36,delta,beta,hand)-spiral_trace(distance-step,36,delta,beta,hand))/(2*step)
                self.assertAlmostEqual(distance*sin(delta)*derivative,hand*tan(radians(beta)),places=8)
            self.assertEqual(spiral_trace(36,36,delta,beta,hand),0)
        for r in (0,-1,37):
            with self.assertRaises(ValueError):spiral_trace(r,36,pi/4,35,1)

    def test_actual_rotated_profiles_have_matching_input_hands_and_cancel_both_mesh_phases(self):
        for hand,zs,zo in product((-1,1),(16,24),(25,60)):
            d=generate('differential',dict(variant='spiral',spiral_hand=hand,side_teeth=zs,output_teeth=zo,width=8))
            gears=d.parts[:3]
            levels=d.analysis['bevel']['cone_stations_mm']
            self.assertGreater(len(levels),2)
            for j,R in enumerate(levels):
                phases=[]
                for p in gears:
                    station=p.stations[j]
                    phases.append(angle_difference(station['outer'][0],p.outer[0]))
                    delta=radians(p.profile_metadata['bevel_profile']['pitch_cone_angle_deg'])
                    self.assertAlmostEqual((p.z+station['z'])/cos(delta),R,places=10)
                    self.assertTrue(all(circle_info(s['holes'][0]) is not None for s in p.stations))
                    self.assertEqual([s['holes'] for s in p.stations],[p.holes]*len(levels))
                self.assertAlmostEqual(phases[0],phases[1],places=12)
                self.assertAlmostEqual(zs*phases[0]+zo*phases[2],0,places=10)
                self.assertAlmostEqual(zs*phases[1]+zo*phases[2],0,places=10)
            for p in gears:self.assertGreater(signature(p)['volume_mm3'],0)

    def test_actual_linear_chords_track_the_exact_vertex_trace_below_the_stated_sampling_limit(self):
        for hand,beta,(zs,zo) in product((-1,1),(1,35,45),((24,24),(16,60),(60,16),(17,25))):
            outer=hypot(zs,zo)  # m=2, hence pitch radii equal tooth counts.
            d=generate('differential',dict(variant='spiral',spiral_hand=hand,spiral_angle=beta,side_teeth=zs,output_teeth=zo,width=min(25,outer/3)))
            distances=d.analysis['bevel']['cone_stations_mm']
            for p in d.parts[:3]:
                meta=p.profile_metadata['bevel_profile'];delta=radians(meta['pitch_cone_angle_deg'])
                local_hand=hand if p.name!='Bevel_output' else -hand
                indices={0,min(range(len(p.outer)),key=lambda i:hypot(*p.outer[i])),max(range(len(p.outer)),key=lambda i:hypot(*p.outer[i]))}
                for j,(r0,r1) in enumerate(zip(distances,distances[1:])):
                    for fraction in (.25,.5,.75):
                        R=r0+(r1-r0)*fraction
                        theta=local_hand*tan(radians(beta))/sin(delta)*log(R/outer)
                        for index in indices:
                            x,y=p.outer[index];scale=R/outer
                            exact=(scale*(x*cos(theta)-y*sin(theta)),scale*(x*sin(theta)+y*cos(theta)))
                            a=p.stations[j]['outer'][index];b=p.stations[j+1]['outer'][index]
                            chord=tuple(a[k]+fraction*(b[k]-a[k]) for k in range(2))
                            self.assertLessEqual(hypot(exact[0]-chord[0],exact[1]-chord[1]),TRACE_CHORD_TOLERANCE+1e-10,(hand,beta,zs,zo,p.name))

    def test_zero_angle_reproduces_straight_geometry_exactly_and_keeps_the_ideal_speed_map(self):
        for hand in (-1,1):
            for choices in ({},dict(output_interface='hollow',carrier_style='split',ratio_mode='spin_2_1')):
                straight=generate('differential',choices)
                zero=generate('differential',dict(choices,variant='spiral',spiral_angle=0,spiral_hand=hand))
                self.assertEqual(straight.analysis['kinematics'],zero.analysis['kinematics'])
                for a,b in zip(straight.parts,zero.parts):
                    self.assertEqual(profile_sections(a),profile_sections(b))
                    self.assertEqual(a.holes,b.holes)
                    self.assertEqual(faces(a),faces(b))
                self.assertEqual(len(zero.parts[0].stations),2)

    def test_both_hands_export_closed_shared_solids_and_keep_the_saved_spiral_parameters(self):
        for hand in (-1,1):
            d=generate('differential',dict(variant='spiral',spiral_hand=hand,output_interface='hollow',carrier_style='split'))
            with TemporaryDirectory() as folder:
                root=Path(folder)
                _,metadata=cad_export.export(d,root/'step')
                assembly,parts=stl_export.export(d,root/'model')
                self.assertEqual(len(metadata),20)
                self.assertEqual(len(parts),20)
                self.assertGreater(assembly.stat().st_size,84)
            restored=generate('differential',json.loads(json.dumps(d.values)))
            self.assertEqual(d.parts,restored.parts)
            self.assertTrue(d.analysis['bevel']['conjugacy_verified'])
            self.assertIn('Analytic working flanks',d.analysis['bevel']['verification_scope'])

    def test_spiral_mcp_discovery_and_config_fields_reject_invalid_angle_or_hand(self):
        with TemporaryDirectory() as folder:
            service=AgentService(Path(folder));self.addCleanup(service.close)
            details=service.discover('differential',variant='spiral')
            fields={f['name']:f for f in details['fields']}
            self.assertEqual(set(details['variants']),{'straight','spiral'})
            self.assertEqual(fields['spiral_angle']['minimum'],0)
            self.assertEqual(fields['spiral_hand']['step'],2)
            for values in (dict(spiral_hand=0),dict(spiral_hand=1.5),dict(spiral_angle=-1),dict(spiral_angle=46)):
                with self.assertRaises(ValueError):generate('differential',dict(values,variant='spiral'))
            created=service.project_create('differential',dict(variant='spiral',spiral_angle=27.5,spiral_hand=-1))
            service.project_save(created['handle'],created['revision'],'spiral.config.json')
            self.assertEqual(service.project_open('spiral.config.json')['parameters'],created['parameters'])


if __name__=='__main__':unittest.main()
