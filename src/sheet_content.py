# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Shared A4 worksheet content for the native and browser renderers."""
from component_sheets import COMPANY_FIELDS, PART_FIELDS
from ui_language import catalog, translate


def output_language(language):
    if not isinstance(language, str) or language not in catalog()['languages']:
        raise ValueError('Unsupported component sheet language.')
    return language


class SheetText:
    def t(self, message):
        """Translate application-owned messages only; never company/project data."""
        return translate(message,self.language)

    def labels(self, *messages):
        return tuple(self.t(message) for message in messages)

    def characteristic(self, row):
        return self.t(row['label']) if row['id'].startswith('auto:') else row['label']

    def method(self, row):
        if row['id']=='auto:span':return self.t(row['method'])
        if row['id']=='auto:gauges':
            from component_sheets import number
            gauge=self.report['profile']['over_gauges']
            kind=self.t(gauge['gauge_type'].capitalize())
            arrangement=self.t(gauge['dimension_kind'].capitalize())
            return f"{kind}; {self.t('Diameter')} {number(gauge['gauge_diameter_mm'])} mm; {arrangement}"
        return row['method']


def context(doc, report):
    rows = [(doc.t(label), report['company'].get(key, '')) for key,label in COMPANY_FIELDS.items()]
    rows += [(doc.t('Project'), report['project'] or doc.t('Untitled')), (doc.t('Source component'), f"{report['source_position']:03d} | {report['source_name']} | {report['family']}"),
             (doc.t('Document revision / geometry'), report['document_revision']+' / '+report['fingerprint'][:16])]
    doc.table(doc.labels('Identification', 'Value'), rows, (1,3))


def production_content(doc, report):
    context(doc, report)
    if report['purchased']:doc.paragraph(doc.t('Purchased/catalog component: complete supplier and drawing references; manufacturing operations are not generated.'))
    doc.heading(doc.t('Company specifications'))
    doc.table(doc.labels('Field', 'Company entry'), [(doc.t(label), report['fields'].get(key, '')) for key,label in PART_FIELDS.items()
        if key not in ('operations', 'notes')], (1,3))
    doc.heading(doc.t('Nominal component data'))
    rows = [(doc.characteristic(r), r['nominal']+' '+r['unit']) for r in report['checks'] if r['id'].startswith('auto:')]
    rows += [(doc.t(label),value) for label,value in report['nominal']]
    if rows:doc.table(doc.labels('Characteristic', 'Nominal value'), rows, (2,1))
    else:doc.paragraph(doc.t('No automatic inspection dimensions are available for this construction. Use the approved company drawing.'))
    doc.reference_profile()
    for key in ('operations', 'notes'):
        doc.heading(doc.t(PART_FIELDS[key]))
        doc.paragraph(report['fields'].get(key) or '________________________________________________________________________________\n________________________________________________________________________________')
    doc.paragraph(doc.t('Production release / date / signature: __________________________________________________'))
    doc.paragraph(doc.t('Nominal geometry is not a released manufacturing drawing. Material, process, tolerances and production approval are defined by the company. Surface interpolation settings are not manufacturing tolerances.'), 8)


def inspection_content(doc, report):
    context(doc, report)
    doc.paragraph(doc.t('Absolute limits in the indicated unit. Blank limits mean acceptance is undefined. Results and disposition are recorded by the inspector; no automatic pass/fail or certificate is generated.'))
    doc.paragraph(doc.t('Sample / serial number: __________________  Date: ______________  Inspector: __________________'))
    for i, row in enumerate(report['checks'], 1):
        # Keep ordinary characteristics together, including their title,
        # contact setup and reading cells. Long company text can paginate.
        doc.space(230)
        doc.heading(f"{i:02d} | {doc.characteristic(row)}")
        doc.table(doc.labels('Nominal', 'Minimum', 'Maximum', 'Unit'),
            [(row['nominal'], row['lower'], row['upper'], row['unit'])], (1,1,1,.6))
        doc.table(doc.labels('Setup', 'Specification'), [(doc.t('Method / contact setup'), doc.method(row)),
            (doc.t('Instrument / ID'), row['instrument']), (doc.t('Datum / drawing reference'), row['datum'])], (1,3))
        doc.table(doc.labels('Reading 1', 'Reading 2', 'Reading 3', 'Disposition / notes'), [('', '', '', '')], (1,1,1,2))
    if not report['checks']:doc.paragraph(doc.t('No characteristics defined. Complete the inspection plan against the company drawing.'))
    disposition = doc.t('Overall disposition: __________________  Reviewed by / date: ______________________________')
    scope = doc.t('Gear measurements are theoretical nominal values for supported constructions. Verify instrument access and contact setup against the approved drawing. This sheet does not establish gear quality grade, strength or standards conformity.')
    doc.keep_text(doc.t('Review'), ((disposition,9),(scope,8)))
    doc.heading(doc.t('Review'))
    doc.paragraph(disposition)
    doc.paragraph(scope, 8)


class PagePlan(SheetText):
    def __init__(self, title, report):
        self.language = output_language(report['language'])
        self.report = report
        self.title = self.t(title)
        self.operations = []

    def space(self, height):
        self.operations.append(('space', height))

    def heading(self, text):
        self.operations.append(('heading', text))

    def paragraph(self, text, size=9):
        self.operations.append(('paragraph', text, size))

    def table(self, headings, rows, ratios):
        self.operations.append(('table', headings, rows, ratios))

    def reference_profile(self):
        if self.report['outline']:
            self.operations.append(('profile', self.t('Profile reference (local XY, first section; not a dimensioned drawing)'),
                                    [self.report['outline'], *self.report['holes']]))

    def keep_text(self, heading, blocks):
        self.operations.append(('keep_text', heading, blocks))

    def payload(self):
        return dict(title=self.title, footer=self.t('RatioLab | Nominal model data + company specifications'),
                    operations=self.operations)


def document_plans(report):
    production = PagePlan('Component production sheet', report)
    inspection = PagePlan('Component inspection sheet', report)
    production_content(production, report)
    inspection_content(inspection, report)
    return dict(production=production.payload(), inspection=inspection.payload())
