# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""A4 component worksheets using the application's existing Cairo/Pango runtime.

No GTK/display or new runtime dependency is required. Tables split long cells
across pages; user text is always plain text, never interpreted as markup.
"""
from datetime import datetime, timezone
from collections import namedtuple
import json
from pathlib import Path
from component_sheets import COMPANY_FIELDS, PART_FIELDS
from export_transaction import directory
from ui_language import catalog, translate

TextLine = namedtuple('TextLine', 'layout line height')


def output_language(language):
    if not isinstance(language, str) or language not in catalog()['languages']:
        raise ValueError('Unsupported component sheet language.')
    return language


class Document:
    width, height, margin = 595.276, 841.89, 36
    line = 12

    def __init__(self, path, title, report):
        self.language = output_language(report.get('language', 'en'))
        title = self.t(title)
        import cairo
        import gi
        gi.require_version('Pango', '1.0')
        gi.require_version('PangoCairo', '1.0')
        from gi.repository import Pango, PangoCairo
        self.Pango, self.PangoCairo = Pango, PangoCairo
        self.surface = cairo.PDFSurface(str(path), self.width, self.height)
        self.surface.set_metadata(cairo.PDF_METADATA_TITLE, title)
        self.surface.set_metadata(cairo.PDF_METADATA_CREATOR, 'RatioLab')
        self.cr = cairo.Context(self.surface)
        self.title, self.report = title, report
        self.page = 0
        self.bottom = self.height-50
        self.content = self.width-2*self.margin
        self.footer_lines = self.lines(self.t('RatioLab | Nominal model data + company specifications'),self.content-75,7.5)
        footer_height = sum(max(self.line,line.height) for line in self.footer_lines)
        self.bottom = self.height-max(50,footer_height+22)
        self.new_page()

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

    def layout(self, text, width, size=9, bold=False):
        layout = self.PangoCairo.create_layout(self.cr)
        self.PangoCairo.context_set_resolution(layout.get_context(), 72)
        # Keep Tamil bases and vowel signs in one shaping font. Generic Sans
        # fallback can choose different fonts for the combining signs and emit
        # dotted circles even though Pango reports no unknown glyphs. This font
        # is already bundled, and also covers Tamil entered in company fields.
        family = 'Noto Sans Tamil, Sans' if any('\u0b80' <= c <= '\u0bff' for c in str(text)) else 'Sans'
        font = self.Pango.FontDescription.from_string(family)
        if bold:font.set_weight(self.Pango.Weight.BOLD)
        font.set_absolute_size(size*self.Pango.SCALE)
        layout.set_font_description(font)
        layout.set_width(int(width*self.Pango.SCALE))
        layout.set_wrap(self.Pango.WrapMode.WORD_CHAR)
        layout.set_text(str(text), -1)
        return layout

    def lines(self, text, width, size=9, bold=False):
        layout = self.layout(text, width, size, bold)
        # Keep the measured/shaped lines and their owning layout alive. Shaping
        # each extracted substring again can wrap a second time with bundled
        # font metrics, painting that extra line over the following PDF row.
        return [TextLine(layout, line, line.get_pixel_extents()[1].height)
                for line in layout.get_lines_readonly()]

    def draw_line(self, line, x, y, muted=False):
        logical = line.line.get_pixel_extents()[1]
        self.cr.set_source_rgb(*((.32,.37,.42) if muted else (.10,.14,.18)))
        self.cr.move_to(x-logical.x, y-logical.y)
        self.PangoCairo.show_layout_line(self.cr, line.line)

    def draw(self, text, x, y, width, size=9, bold=False, muted=False):
        self.cr.set_source_rgb(*((.32,.37,.42) if muted else (.10,.14,.18)))
        self.cr.move_to(x, y)
        self.PangoCairo.show_layout(self.cr, self.layout(text, width, size, bold))

    def footer(self):
        pages = self.lines(self.t(f'Page {self.page}'),70,8)
        height = max(sum(max(self.line,line.height) for line in lines) for lines in (self.footer_lines,pages))
        top = min(self.height-32,self.height-10-height)
        self.cr.set_source_rgb(.8,.83,.85)
        self.cr.set_line_width(.5)
        self.cr.move_to(self.margin, top-7)
        self.cr.line_to(self.width-self.margin, top-7)
        self.cr.stroke()
        for lines,x in ((self.footer_lines,self.margin),(pages,self.width-self.margin-70)):
            y=top
            for line in lines:
                self.draw_line(line,x,y,muted=True)
                y+=max(self.line,line.height)

    def new_page(self):
        if self.page:
            self.footer()
            self.cr.show_page()
        self.page += 1
        self.draw('RatioLab', self.margin, 26, self.content, 11, True)
        title_lines = self.lines(self.title,self.content,17,True)
        y=44
        for line in title_lines:
            self.draw_line(line,self.margin,y)
            y+=max(22,line.height)
        identity_top=y+3
        fields = self.report['fields']
        identity = f"{fields.get('code') or self.report['source_name']} | {self.t('Rev.')} {fields.get('revision') or self.t('Undefined')} | {self.t('Lot')} {fields.get('lot') or self.t('Undefined')}"
        identity_lines = self.lines(identity, self.content, 9)
        # Repeated identity must not consume a whole page for an unbounded code.
        if len(identity_lines) > 4:
            identity_lines = identity_lines[:3]+self.lines(self.t('(full identification in the document fields)'),self.content,9)
        step = max(self.line, *(line.height for line in identity_lines))
        for j, line in enumerate(identity_lines):self.draw_line(line, self.margin, identity_top+j*step)
        self.y = identity_top+len(identity_lines)*step+5

    def space(self, amount):
        if self.y+amount > self.bottom:self.new_page()

    def heading(self, title):
        lines = self.lines(title, self.content, 11, True)
        step = max(14, *(line.height for line in lines))
        self.space(min(28+step*len(lines), self.bottom-150))
        self.y += 8
        for line in lines:
            self.space(step)
            self.draw_line(line, self.margin, self.y)
            self.y += step
        self.y += 6

    def paragraph(self, text, size=9):
        for line in self.lines(text, self.content, size):
            step = max(self.line,line.height)
            self.space(step)
            self.draw_line(line, self.margin, self.y)
            self.y += step
        self.y += 5

    def table(self, headings, rows, fractions):
        widths = [self.content*f/sum(fractions) for f in fractions]
        def row(cells, header=False):
            wrapped = [self.lines(str(cell) if str(cell).strip() else '________________', width-12, 8.5, header)
                       for cell, width in zip(cells, widths)]
            count = max(map(len, wrapped))
            step = max(self.line, *(line.height for lines in wrapped for line in lines))
            offset = 0
            while offset < count:
                if self.y+step+8 > self.bottom:
                    self.new_page()
                    if not header:row(headings, True)
                capacity = max(1, int((self.bottom-self.y-8)//step))
                take = min(count-offset, capacity)
                height = take*step+8
                x = self.margin
                for lines, width in zip(wrapped, widths):
                    if header:
                        self.cr.set_source_rgb(.9,.94,.95)
                        self.cr.rectangle(x, self.y, width, height)
                        self.cr.fill()
                    self.cr.set_source_rgb(.75,.8,.82)
                    self.cr.set_line_width(.5)
                    self.cr.rectangle(x, self.y, width, height)
                    self.cr.stroke()
                    for j, line in enumerate(lines[offset:offset+take]):
                        self.draw_line(line, x+6, self.y+4+j*step)
                    x += width
                self.y += height
                offset += take
        row(headings, True)
        for cells in rows:row(cells)
        self.y += 3

    def reference_profile(self):
        outline = self.report['outline']
        if not outline:return
        caption=self.t('Profile reference (local XY, first section; not a dimensioned drawing)')
        caption_height=sum(max(self.line,line.height) for line in self.lines(caption,self.content,8))+5
        self.space(caption_height+100)
        self.paragraph(caption,8)
        # Use all stored points; no outline simplification or manufactured shape.
        loops = [outline]+self.report['holes']
        points = [q for loop in loops for q in loop]
        low = [min(q[i] for q in points) for i in (0,1)]
        high = [max(q[i] for q in points) for i in (0,1)]
        scale = min((self.content-20)/max(high[0]-low[0], 1e-9), 88/max(high[1]-low[1], 1e-9))
        center = [(a+b)/2 for a,b in zip(low,high)]
        self.cr.set_source_rgb(.13,.31,.37)
        self.cr.set_line_width(.65)
        for loop in loops:
            if not loop:continue
            for j, q in enumerate(loop):
                x = self.width/2+(q[0]-center[0])*scale
                y = self.y+44-(q[1]-center[1])*scale
                (self.cr.move_to if j == 0 else self.cr.line_to)(x, y)
            self.cr.close_path()
            self.cr.stroke()
        self.y += 100

    def finish(self):
        self.footer()
        self.surface.finish()


def context(doc, report):
    rows = [(doc.t(label), report['company'].get(key, '')) for key,label in COMPANY_FIELDS.items()]
    rows += [(doc.t('Project'), report['project'] or doc.t('Untitled')), (doc.t('Source component'), f"{report['source_position']:03d} | {report['source_name']} | {report['family']}"),
             (doc.t('Document revision / geometry'), report['document_revision']+' / '+report['fingerprint'][:16])]
    doc.table(doc.labels('Identification', 'Value'), rows, (1,3))


def production(report, path):
    doc = Document(path, 'Component production sheet', report)
    try:
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
    finally:doc.finish()


def inspection(report, path):
    doc = Document(path, 'Component inspection sheet', report)
    try:
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
        needed = 14+sum(max(14,line.height) for line in doc.lines(doc.t('Review'),doc.content,11,True))
        for text,size in ((disposition,9),(scope,8)):
            needed += 5+sum(max(doc.line,line.height) for line in doc.lines(text,doc.content,size))
        doc.space(needed)
        doc.heading(doc.t('Review'))
        doc.paragraph(disposition)
        doc.paragraph(scope, 8)
    finally:doc.finish()


def export(report, target, language='en'):
    """Publish both PDFs and their exact input snapshot as one transaction."""
    snapshot = dict(report, language=output_language(language), generated_at=datetime.now(timezone.utc).isoformat())
    with directory(target) as staging:
        production(snapshot, staging/'production.pdf')
        inspection(snapshot, staging/'inspection.pdf')
        (staging/'sheet-data.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return Path(target)
