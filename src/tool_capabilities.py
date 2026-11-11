# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Shared presentation capabilities, derived from generated construction metadata."""


def gauge_components(design):
    if design is None:
        return []
    return [i for i, part in enumerate(design.parts)
            if (g := part.profile_metadata.get('tooth_profile', {}).get('measurement_geometry'))
            and g.get('helix_angle_abs_deg') == 0]


def backlash_supported(design):
    return bool(design is not None and design.family == 'parallel'
                and design.values.get('variant') in ('spur', 'helical', 'double')
                and len(design.analysis.get('meshes', [])) == 1
                and not design.analysis['meshes'][0].get('internal'))


def capabilities(design):
    from combination_search import FAMILIES
    from backlash_solver import adjustment_limits
    ready = design is not None
    gauges = gauge_components(design)
    return {
        'components': dict(available=ready, reason='Select, isolate, measure and export components.' if ready else 'Generate a valid model first.'),
        'search': dict(available=ready and design.family in FAMILIES,
                       reason='Compare finite combinations for ratio and size.' if ready and design.family in FAMILIES else 'Choose a supported reducer with a single input/output ratio.'),
        'interference': dict(available=ready, reason='Inspect sampled component clearances over motion.' if ready else 'Generate a valid model first.'),
        'metrology': dict(available=bool(gauges), components=gauges,
                          reason='Theoretical gauge dimensions and usable tooth spans.' if gauges else 'Requires a generated external or internal spur involute component.'),
        'backlash': dict(available=backlash_supported(design), limits=adjustment_limits(design) if backlash_supported(design) else None,
                         reason='Propose centre distance for a target working backlash.' if backlash_supported(design) else 'Requires one external parallel gear pair; multistage trains are not supported.'),
    }
