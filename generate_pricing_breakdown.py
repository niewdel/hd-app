"""
HD Hauling & Grading - Pricing Breakdown PDF Generator

Internal confidential document showing cost breakdown for proposals.
Shows materials, labor, trucking, markup per line item.
Styled to match the proposal PDF (same header, info block, fonts).
"""
import json, sys, os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable, KeepTogether)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas as pdfcanvas

RED     = colors.HexColor('#CC0000')
BLACK   = colors.HexColor('#111111')
WHITE   = colors.HexColor('#FFFFFF')
LGRAY   = colors.HexColor('#F4F4F4')
MGRAY   = colors.HexColor('#CCCCCC')
DGRAY   = colors.HexColor('#555555')
TBLBORD = colors.HexColor('#CCCCCC')
ROWALT  = colors.HexColor('#F8F8F8')
COLHDR  = colors.HexColor('#3A3A3A')

W, H    = letter
_DIR    = os.path.dirname(os.path.abspath(__file__))
LOGO    = os.path.join(_DIR, 'hd_logo.png')
if not os.path.exists(LOGO):
    LOGO = os.path.join(_DIR, 'hd_logo_cropped.png')
LM = RM = 0.5 * inch
TM = 1.05 * inch
BM = 0.6  * inch


class PBCanvas(pdfcanvas.Canvas):
    """Custom canvas with header/footer matching the proposal PDF."""
    def __init__(self, *args, **kwargs):
        self._date = kwargs.pop('date_str', '')
        self._doc_number = kwargs.pop('doc_number', '')
        super().__init__(*args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for i, state in enumerate(self._pages):
            self.__dict__.update(state)
            self._page_index = i + 1
            self._page_total = total
            self._draw_header()
            self._draw_footer()
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_header(self):
        self.saveState()
        if os.path.exists(LOGO):
            self.drawImage(LOGO, LM, H - 0.82*inch, width=1.25*inch, height=0.52*inch,
                           preserveAspectRatio=True, mask='auto')
        self.setFont('Helvetica-Bold', 17)
        self.setFillColor(BLACK)
        self.drawRightString(W - RM, H - 0.52*inch, 'PRICING BREAKDOWN')
        # Doc number
        right_y = H - 0.70*inch
        if self._doc_number:
            self.setFont('Helvetica-Bold', 9)
            self.setFillColor(RED)
            self.drawRightString(W - RM, right_y, self._doc_number)
            right_y -= 0.14*inch
        self.setFont('Helvetica', 9)
        self.setFillColor(DGRAY)
        self.drawRightString(W - RM, right_y, self._date)
        # Divider line
        self.setStrokeColor(BLACK)
        self.setLineWidth(1.0)
        self.line(LM, H - 0.88*inch, W - RM, H - 0.88*inch)
        self.restoreState()

    def _draw_footer(self):
        self.saveState()
        self.setFont('Helvetica-Bold', 7)
        self.setFillColor(RED)
        self.drawCentredString(W / 2, BM * 0.65, 'CONFIDENTIAL \u2014 INTERNAL USE ONLY')
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#AAAAAA'))
        self.drawCentredString(W / 2, BM * 0.35, f'Page {self._page_index} of {self._page_total}')
        self.restoreState()


def canvas_maker(date_str, doc_number=''):
    class _C(PBCanvas):
        def __init__(self, *a, **kw):
            kw['date_str'] = date_str
            kw['doc_number'] = doc_number
            super().__init__(*a, **kw)
    return _C


def _fi(n):
    return '{:,}'.format(round(n))


def _info_block(data):
    """Simple single-line info block with pipe separators."""
    lbl_s = ParagraphStyle('lbl', fontName='Helvetica-Bold', fontSize=8, textColor=BLACK)
    val_s = ParagraphStyle('val', fontName='Helvetica', fontSize=8, textColor=DGRAY, leading=11)

    proj_name = data.get('project_name', '')
    client = data.get('client_name', '')
    address = data.get('address', '')
    sender = data.get('sender_name', '')
    date_str = data.get('date', '')
    doc_num = data.get('document_number', '')

    info_parts = []
    if proj_name: info_parts.append(f'<b>Project:</b> {proj_name}')
    if doc_num: info_parts.append(f'<b>No:</b> {doc_num}')
    if client: info_parts.append(f'<b>Client:</b> {client}')
    if address: info_parts.append(f'<b>Address:</b> {address}')
    if sender: info_parts.append(f'<b>Prepared by:</b> {sender}')
    if date_str: info_parts.append(f'<b>Date:</b> {date_str}')

    if not info_parts:
        return Spacer(1, 0.01*inch)

    info_text = '&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;'.join(info_parts)
    return Paragraph(info_text, ParagraphStyle('info', fontName='Helvetica', fontSize=9,
                                                textColor=DGRAY, leading=14))


def _section_banner(text, cw):
    """Red section banner."""
    sec_s = ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=10, textColor=WHITE, alignment=TA_CENTER)
    ban = Table([[Paragraph(text, sec_s)]], colWidths=[cw])
    ban.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), RED),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    return ban


def _make_table(rows, cols, cw):
    """Build a styled data table with header row and alternating row colors."""
    tbl = Table(rows, colWidths=cols)
    ts = [
        ('BACKGROUND', (0,0), (-1,0), COLHDR),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('TOPPADDING', (0,0), (-1,0), 5),
        ('BOTTOMPADDING', (0,0), (-1,0), 5),
        ('TOPPADDING', (0,1), (-1,-1), 3),
        ('BOTTOMPADDING', (0,1), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,1), (-1,-1), 0.3, TBLBORD),
        ('BOX', (0,0), (-1,-1), 0.5, TBLBORD),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            ts.append(('BACKGROUND', (0,i), (-1,i), ROWALT))
    tbl.setStyle(TableStyle(ts))
    return tbl


def build(data, out_path):
    cw = W - LM - RM
    date_str = data.get('date', '')
    doc_number = data.get('document_number', '')

    doc = SimpleDocTemplate(
        out_path, pagesize=letter,
        title='Pricing Breakdown',
        author='HD Hauling & Grading',
        leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM
    )

    story = []

    # Use short single-line text styles to prevent wrapping
    hdr_s = ParagraphStyle('hdr', fontName='Helvetica-Bold', fontSize=7, textColor=WHITE, leading=9)
    hdr_r = ParagraphStyle('hdrr', fontName='Helvetica-Bold', fontSize=7, textColor=WHITE, alignment=TA_RIGHT, leading=9)
    cell_s = ParagraphStyle('cell', fontName='Helvetica', fontSize=7.5, textColor=BLACK, alignment=TA_RIGHT, leading=10)
    cell_l = ParagraphStyle('celll', fontName='Helvetica', fontSize=7.5, textColor=BLACK, leading=10)
    cell_b = ParagraphStyle('cellb', fontName='Helvetica-Bold', fontSize=7.5, textColor=BLACK, alignment=TA_RIGHT, leading=10)
    name_s = ParagraphStyle('name', fontName='Helvetica-Bold', fontSize=7.5, textColor=BLACK, leading=10)

    # ── Info Block (matches proposal) ──
    story.append(_info_block(data))
    story.append(Spacer(1, 0.15*inch))

    # ── Asphalt & Stone Breakdown ──
    items = data.get('asphalt_items', [])
    if items:
        story.append(_section_banner('ASPHALT BREAKDOWN', cw))

        cols = [cw*0.20, cw*0.06, cw*0.05, cw*0.07, cw*0.06, cw*0.10, cw*0.10, cw*0.10, cw*0.10, cw*0.08, cw*0.08]
        rows = [[
            Paragraph('ITEM', hdr_s), Paragraph('SY', hdr_r), Paragraph('D"', hdr_r),
            Paragraph('TONS', hdr_r), Paragraph('DAYS', hdr_r),
            Paragraph('MATERIAL', hdr_r), Paragraph('LABOR', hdr_r),
            Paragraph('TRUCKING', hdr_r), Paragraph('BID', hdr_r),
            Paragraph('$/TON', hdr_r), Paragraph('MU%', hdr_r)
        ]]
        for item in items:
            cost = item.get('material', 0) + item.get('labor', 0) + item.get('trucking', 0)
            mu = ((item.get('bid', 0) - cost) / cost * 100) if cost > 0 else 0
            ppt = item.get('bid', 0) / item.get('tons', 1) if item.get('tons', 0) > 0 else 0
            rows.append([
                Paragraph(item.get('name', ''), name_s),
                Paragraph(_fi(item.get('sy', 0)), cell_s),
                Paragraph(str(item.get('depth', '')) + '"', cell_s),
                Paragraph(_fi(item.get('tons', 0)), cell_s),
                Paragraph(str(item.get('days', 0)), cell_s),
                Paragraph('$' + _fi(item.get('material', 0)), cell_s),
                Paragraph('$' + _fi(item.get('labor', 0)), cell_s),
                Paragraph('$' + _fi(item.get('trucking', 0)), cell_s),
                Paragraph('$' + _fi(item.get('bid', 0)), cell_b),
                Paragraph('$' + f"{ppt:.0f}", cell_s),
                Paragraph(f"{mu:.1f}%", cell_s),
            ])

        story.append(_make_table(rows, cols, cw))
        story.append(Spacer(1, 0.15*inch))

    # ── Concrete Breakdown ──
    conc_items = data.get('concrete_items', [])
    if conc_items:
        story.append(_section_banner('CONCRETE BREAKDOWN', cw))

        cols = [cw*0.26, cw*0.10, cw*0.08, cw*0.10, cw*0.13, cw*0.13, cw*0.12, cw*0.08]
        rows = [[
            Paragraph('ITEM', hdr_s), Paragraph('QTY', hdr_r), Paragraph('UNIT', hdr_r),
            Paragraph('CY', hdr_r), Paragraph('MATERIAL', hdr_r),
            Paragraph('LABOR', hdr_r), Paragraph('BID', hdr_r), Paragraph('MU%', hdr_r)
        ]]
        for item in conc_items:
            cost = item.get('material', 0) + item.get('labor', 0)
            mu = ((item.get('bid', 0) - cost) / cost * 100) if cost > 0 else 0
            rows.append([
                Paragraph(item.get('name', ''), name_s),
                Paragraph(_fi(item.get('qty', 0)), cell_s),
                Paragraph(item.get('unit', 'LF'), cell_s),
                Paragraph(f"{item.get('cy', 0):.1f}", cell_s),
                Paragraph('$' + _fi(item.get('material', 0)), cell_s),
                Paragraph('$' + _fi(item.get('labor', 0)), cell_s),
                Paragraph('$' + _fi(item.get('bid', 0)), cell_b),
                Paragraph(f"{mu:.1f}%", cell_s),
            ])

        story.append(_make_table(rows, cols, cw))
        story.append(Spacer(1, 0.15*inch))

    # ── Additional Items Breakdown ──
    extra_items = data.get('extra_items', [])
    if extra_items:
        story.append(_section_banner('ADDITIONAL ITEMS BREAKDOWN', cw))

        cols = [cw*0.26, cw*0.08, cw*0.08, cw*0.13, cw*0.13, cw*0.13, cw*0.12, cw*0.07]
        rows = [[
            Paragraph('ITEM', hdr_s), Paragraph('QTY', hdr_r), Paragraph('UNIT', hdr_r),
            Paragraph('MATERIAL', hdr_r), Paragraph('LABOR', hdr_r),
            Paragraph('BID $/UNIT', hdr_r), Paragraph('BID TOTAL', hdr_r), Paragraph('MU%', hdr_r)
        ]]
        for item in extra_items:
            mat = item.get('material', 0)
            labor = item.get('labor', 0)
            cost = mat + labor
            sub = item.get('subtotal', 0)
            mu = ((sub - cost) / cost * 100) if cost > 0 else 0
            rows.append([
                Paragraph(item.get('name', ''), name_s),
                Paragraph(str(item.get('qty', 0)), cell_s),
                Paragraph(item.get('unit', ''), cell_s),
                Paragraph('$' + _fi(mat) if mat > 0 else '-', cell_s),
                Paragraph('$' + _fi(labor) if labor > 0 else '-', cell_s),
                Paragraph('$' + f"{item.get('price', 0):,.2f}", cell_s),
                Paragraph('$' + _fi(sub), cell_b),
                Paragraph(f"{mu:.1f}%" if cost > 0 else '-', cell_s),
            ])

        story.append(_make_table(rows, cols, cw))
        story.append(Spacer(1, 0.15*inch))

    # ── Summary ──
    totals = data.get('totals', {})
    if totals:
        sum_s = ParagraphStyle('sum_l', fontName='Helvetica', fontSize=10, textColor=DGRAY)
        sum_b = ParagraphStyle('sum_r', fontName='Helvetica-Bold', fontSize=10, textColor=BLACK, alignment=TA_RIGHT)
        sum_hdr = ParagraphStyle('sum_h', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, alignment=TA_RIGHT)

        sum_rows = []
        if totals.get('material'):
            sum_rows.append([Paragraph('Materials', sum_s), Paragraph('$' + _fi(totals['material']), sum_b)])
        if totals.get('labor'):
            sum_rows.append([Paragraph('Labor', sum_s), Paragraph('$' + _fi(totals['labor']), sum_b)])
        if totals.get('trucking'):
            sum_rows.append([Paragraph('Trucking', sum_s), Paragraph('$' + _fi(totals['trucking']), sum_b)])
        if totals.get('mob_cost'):
            sum_rows.append([Paragraph('Mobilization Cost', sum_s), Paragraph('$' + _fi(totals['mob_cost']), sum_b)])
        cost = totals.get('cost', 0)
        if cost:
            sum_rows.append([Paragraph('Total Cost', sum_s), Paragraph('$' + _fi(cost), sum_b)])
        if totals.get('mobilization'):
            sum_rows.append([Paragraph('Mobilization (Bid)', sum_s), Paragraph('$' + _fi(totals['mobilization']), sum_b)])
        bid = totals.get('bid', 0)
        if bid:
            sum_rows.append([
                Paragraph('Bid Total', ParagraphStyle('bt', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK)),
                Paragraph('$' + _fi(bid), sum_hdr)
            ])
        markup = totals.get('markup_pct', 0)
        if markup:
            sum_rows.append([Paragraph('Markup', sum_s), Paragraph(f"{markup:.1f}%", sum_b)])
        profit = totals.get('profit', 0)
        if profit:
            profit_color = colors.HexColor('#27500A') if profit > 0 else RED
            sum_rows.append([
                Paragraph('Gross Profit', sum_s),
                Paragraph('$' + _fi(profit), ParagraphStyle('gp', fontName='Helvetica-Bold', fontSize=10,
                          textColor=profit_color, alignment=TA_RIGHT))
            ])

        if sum_rows:
            t = Table(sum_rows, colWidths=[cw*0.60, cw*0.40])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), LGRAY),
                ('BOX', (0,0), (-1,-1), 0.5, TBLBORD),
                ('LINEBELOW', (0,0), (-1,-2), 0.3, TBLBORD),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('LEFTPADDING', (0,0), (-1,-1), 12),
                ('RIGHTPADDING', (0,0), (-1,-1), 12),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            story.append(t)

    doc.build(story, canvasmaker=canvas_maker(date_str, doc_number))


if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else 'pricing_breakdown.pdf'
    build(data, out)
