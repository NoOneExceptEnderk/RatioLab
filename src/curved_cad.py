# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Opt-in cylindrical CAD prototypes with controlled C1 spline chains.

No additional CAD dependency is loaded by RatioLab. Independent OCCT reimport
is a development check, described in docs/technical/curved-cad-prototype.md.
The ordinary exporters retain their existing contract and representations.
"""
import json
from pathlib import Path

from cad_export import Writer
from export_transaction import directory, write_text
from geometry import CircleProfile, gear_part
from geometry_quality import project
from rust_geometry import call


def _reference(design):
    """Reject altered, keyed, assembled and unsupported geometry explicitly."""
    if design.family != 'spur' or len(design.parts) != 1:
        raise ValueError('Curved CAD prototype requires one external spur gear.')
    v = design.values
    from tooth_tips import parameters
    expected = gear_part('Gear', v['teeth'], v['module'], v['pressure'],
        v['backlash'], v['width'], v['bore'], shift=v['profile_shift'],
        ha=v['addendum'], hf=v['dedendum'], **parameters(v))
    part = design.parts[0]
    for name in ('outer', 'holes', 'width', 'z', 'center', 'twist', 'axis_x',
                 'double', 'gap', 'core_radius', 'internal', 'stations', 'mesh', 'frame'):
        if getattr(part, name) != getattr(expected, name):
            raise ValueError('Curved CAD prototype requires the unchanged, unplaced spur construction with a round bore.')
    for loop, original in zip(part.holes, expected.holes):
        # List equality alone does not compare the mutable provenance fields.
        if (not isinstance(loop, CircleProfile) or not loop.intact()
                or loop.center != (0, 0) or loop.radius != original.radius):
            raise ValueError('Curved CAD prototype requires an intact concentric circular bore.')
    return part, dict(z=v['teeth'], mt=v['module'], depth=v['module'],
        pressure=v['pressure'], normal_pressure=v['pressure'],
        backlash=v['backlash'], shift=v['profile_shift'],
        ha=v['addendum'], hf=v['dedendum'], **parameters(v))


class CurveWriter(Writer):
    @staticmethod
    def num(x):
        # Round-trip binary64 control coordinates; decimal places are not an
        # accuracy claim. Reader tolerances remain a separate measured quantity.
        value = format(float(x), '.17g')
        return value if '.' in value or 'e' in value else value + '.'

    def curve_edge(self, rows, z, patch):
        row = rows[0]
        coordinates = row['controls'] if row['kind'] == 'cubic' else row['endpoints']
        if row['kind'] == 'cubic':
            coordinates = patch['poles']
        points = [(*xy, z) for xy in coordinates]
        if row['kind'] == 'cubic':
            controls = self.refs([self.xyz('CARTESIAN_POINT', p) for p in points])
            knots = patch['knots']
            multiplicities = patch['multiplicities']
            curve = self.add("B_SPLINE_CURVE_WITH_KNOTS('',3," + controls
                + ',.UNSPECIFIED.,.F.,.U.,' + self.refs([str(m) for m in multiplicities])
                + ',' + self.refs([self.num(k) for k in knots]) + ',.UNSPECIFIED.)')
        else:
            curve = self.add("CIRCLE(''," + self.placement((0, 0, z), (0, 0, 1), (1, 0, 0))
                             + ',' + self.num(row['radius_mm']) + ')')
        edge = self.add("EDGE_CURVE(''," + self.vertex(points[0]) + ',' + self.vertex(points[-1]) + ',' + curve + ',.T.)')
        return edge, curve, points[0], points[-1]

    def curved_body(self, part, profile, patches):
        curves = profile['curves']
        groups = [curves[p['first_curve']:p['first_curve']+p['curve_count']] for p in patches]
        lower = [self.curve_edge(rows, 0., patch) for rows,patch in zip(groups,patches)]
        upper = [self.curve_edge(rows, part.width, patch) for rows,patch in zip(groups,patches)]
        faces = []
        vector = self.add("VECTOR(''," + self.xyz('DIRECTION', (0, 0, 1)) + ',1.)')
        for rows, low, high in zip(groups, lower, upper):
            row = rows[0]
            if row['kind'] == 'cubic':
                surface = self.add("SURFACE_OF_LINEAR_EXTRUSION(''," + low[1] + ',' + vector + ')')
            else:
                surface = self.add("CYLINDRICAL_SURFACE('',"
                    + self.placement((0, 0, 0), (0, 0, 1), (1, 0, 0)) + ',' + self.num(row['radius_mm']) + ')')
            edges = [self.oriented(low[0]), self.edge(low[3], high[3]),
                     self.oriented(high[0], False), self.edge(high[2], low[2])]
            bound = self.bound(edges)
            faces.append(self.add("ADVANCED_FACE('',(" + bound + '),' + surface + ',.T.)'))
        bottom = [self.bound([self.oriented(row[0], False) for row in reversed(lower)])]
        top = [self.bound([self.oriented(row[0]) for row in upper])]
        for hole in part.holes:
            radius = hole.radius
            low = self.circle((0, 0, 0), (0, 0, 1), (1, 0, 0), radius)
            high = self.circle((0, 0, part.width), (0, 0, 1), (1, 0, 0), radius)
            surface = self.add("CYLINDRICAL_SURFACE('',"
                + self.placement((0, 0, 0), (0, 0, 1), (1, 0, 0)) + ',' + self.num(radius) + ')')
            # Supply the exact periodic seam as a shared line. Leaving its
            # creation to the reader can introduce a fitted seam with a much
            # larger local tolerance than the actual circular walls.
            bounds = [self.bound([self.oriented(low, False),
                self.edge((radius, 0, 0), (radius, 0, part.width)),
                self.oriented(high), self.edge((radius, 0, part.width), (radius, 0, 0))])]
            faces.append(self.add("ADVANCED_FACE(''," + self.refs(bounds) + ',' + surface + ',.F.)'))
            bottom.append(self.bound([self.oriented(low)], False))
            top.append(self.bound([self.oriented(high, False)], False))
        for z, axis, bounds in ((0., (0, 0, -1), bottom), (part.width, (0, 0, 1), top)):
            surface = self.add("PLANE(''," + self.placement((0, 0, z), axis, (1, 0, 0)) + ')')
            faces.append(self.add("ADVANCED_FACE(''," + self.refs(bounds) + ',' + surface + ',.T.)'))
        shell = self.add("CLOSED_SHELL(''," + self.refs(faces) + ')')
        return self.add('MANIFOLD_SOLID_BREP(' + self.quote(part.name) + ',' + shell + ')')


def document(design, *, tolerance_mm=.001):
    """Return one opt-in cylindrical STEP and its actual approximation record.

    tolerance_mm controls continuous profile-to-cubic approximation. It does not
    replace quality.export_mm, describe machining or certify STEP-reader error.
    """
    if design.family in ('helical','internal'):
        from curved_cylindrical import document as cylindrical_document
        return cylindrical_document(design,tolerance_mm=tolerance_mm)
    part, parameters = _reference(design)
    profile = call('cad_spur_curves', dict(parameters, tolerance_mm=tolerance_mm))
    writer = CurveWriter()
    patches = profile.pop('cad_patches')
    solid = writer.curved_body(part, profile, patches)
    text = writer.finish([solid]).replace('RatioLab: sampled geometry with proven circular walls',
        'RatioLab curved spur prototype: analytic arcs and bounded cubic curves')
    metadata = dict(format='ratiolab.curved-cad-prototype/1', units='mm',
        component=part.name, coordinates='nominal gear coordinates',
        width_mm=float(part.width), bore_radius_mm=float(part.holes[0].radius) if part.holes else 0.,
        representation='cubic curves, exact circular arcs and extruded curved BRep faces',
        profile=profile, patches=[{k:p[k] for k in ('first_curve','curve_count')} for p in patches], step_uncertainty_mm=1e-7,
        reader_verification='not performed by the writer; use scripts/verify-curved-cad.py with independent OCCT',
        limitations='External spur prototype only. Curve approximation is evaluated in binary64. STEP reader tolerances and arithmetic roundoff are separate. This is not a cutter, contact, strength, manufacturing or general ISO conformity qualification.')
    return text, metadata


def export(design, target, *, tolerance_mm=.001):
    """Publish the prototype and provenance transactionally; never overwrite."""
    content, metadata = document(design, tolerance_mm=tolerance_mm)
    with directory(target) as staging:
        write_text(staging/'gear.step', content, encoding='ascii')
        write_text(staging/'curved-cad-info.json', json.dumps(metadata, indent=2, allow_nan=False)+'\n')
        write_text(staging/'project.config.json', json.dumps(project(design), indent=2, allow_nan=False)+'\n')
    return Path(target), metadata
