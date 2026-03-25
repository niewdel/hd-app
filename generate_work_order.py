"""
HD Hauling & Grading - Crew Work Order PDF Generator

Generates a crew-facing work order from a saved proposal.
Shows materials, quantities, and scope — NO PRICING of any kind.
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
DGRAY   = colors.HexColor('#555555')
TBLBORD = colors.HexColor('#CCCCCC')
ROWALT  = colors.HexColor('#EEEEEE')
COLHDR  = colors.HexColor('#3A3A3A')

W, H    = letter
_DIR    = os.path.dirname(os.path.abspath(__file__))
LOGO    = os.path.join(_DIR, 'hd_logo.png')
if not os.path.exists(LOGO):
    LOGO = os.path.join(_DIR, 'hd_logo_cropped.png')
LM = RM = 0.5 * inch
TM = 1.05 * inch
BM = 0.6  * inch


def S():
    """Build paragraph style dict."""
    return {
        'info_lbl':   ParagraphStyle('il',  fontName='Helvetica-Bold', fontSize=8,   textColor=BLACK),
        'info_val':   ParagraphStyle('iv',  fontName='Helvetica',      fontSize=8,   textColor=DGRAY, leading=11),
        'item_name':  ParagraphStyle('in2', fontName='Helvetica-Bold', fontSize=9,   textColor=BLACK, leading=12),
        'item_desc':  ParagraphStyle('id',  fontName='Helvetica',      fontSize=8,   textColor=DGRAY, leading=11),
        'cell':       ParagraphStyle('c',   fontName='Helvetica',      fontSize=9,   textColor=BLACK, alignment=TA_RIGHT),
        'cell_c':     ParagraphStyle('cc',  fontName='Helvetica',      fontSize=9,   textColor=BLACK, alignment=TA_CENTER),
        'cell_l':     ParagraphStyle('cl',  fontName='Helvetica',      fontSize=9,   textColor=BLACK, alignment=TA_LEFT),
        'cell_b':     ParagraphStyle('cb',  fontName='Helvetica-Bold', fontSize=9,   textColor=BLACK, alignment=TA_RIGHT),
        'notes_body': ParagraphStyle('nb',  fontName='Helvetica',      fontSize=9,   textColor=DGRAY, leading=13),
        'section':    ParagraphStyle('sc',  fontName='Helvetica-Bold', fontSize=10,  textColor=WHITE, alignment=TA_CENTER),
        'sign_lbl':   ParagraphStyle('sl',  fontName='Helvetica',      fontSize=9,   textColor=BLACK, leading=18),
        'footer':     ParagraphStyle('ft',  fontName='Helvetica-Bold', fontSize=7,   textColor=DGRAY, alignment=TA_CENTER),
    }


# ---------------------------------------------------------------------------
# HDCanvas — draws header + footer on every page (except first gets it too)
# ---------------------------------------------------------------------------

class WOCanvas(pdfcanvas.Canvas):
    """Custom canvas that draws the header/footer on every page."""
    def __init__(self, *args, **kwargs):
        self._date = kwargs.pop('date_str', '')
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
        self.setFont('Helvetica-Bold', 19)
        self.setFillColor(BLACK)
        self.drawRightString(W - RM, H - 0.52*inch, 'WORK ORDER')
        self.setFont('Helvetica', 9)
        self.setFillColor(DGRAY)
        self.drawRightString(W - RM, H - 0.70*inch, self._date)
        self.setStrokeColor(BLACK)
        self.setLineWidth(1.0)
        self.line(LM, H - 0.88*inch, W - RM, H - 0.88*inch)
        self.restoreState()

    def _draw_footer(self):
        self.saveState()
        # "INTERNAL USE ONLY" notice
        self.setFont('Helvetica-Bold', 7)
        self.setFillColor(DGRAY)
        self.drawCentredString(W / 2, BM * 0.65, 'INTERNAL USE ONLY \u2014 NOT FOR DISTRIBUTION')
        # Page numbers
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#AAAAAA'))
        self.drawCentredString(W / 2, BM * 0.35, f'Page {self._page_index} of {self._page_total}')
        self.restoreState()


def canvas_maker(date_str):
    class _C(WOCanvas):
        def __init__(self, *a, **kw):
            kw['date_str'] = date_str
            super().__init__(*a, **kw)
    return _C


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_qty(v):
    """Format quantity — drop decimal if whole number."""
    if v == int(v):
        return '{:,}'.format(int(v))
    return '{:,.2f}'.format(v)


def _section_banner(text, cw):
    """Red banner with white centered text."""
    tbl = Table(
        [[Paragraph(text, ParagraphStyle('sb', fontName='Helvetica-Bold', fontSize=10,
                                          textColor=WHITE, alignment=TA_CENTER))]],
        colWidths=[cw]
    )
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), RED),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
    ]))
    return tbl


# ---------------------------------------------------------------------------
# build()
# ---------------------------------------------------------------------------

def build(data, out_path):
    st = S()
    cw = W - LM - RM  # content width

    date_str = data.get('date', '')

    doc = SimpleDocTemplate(
        out_path, pagesize=letter,
        title='Work Order - ' + data.get('project_name', ''),
        author='HD Hauling & Grading',
        leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM
    )

    story = []

    # ------------------------------------------------------------------
    # 1. Project Info block — 3-column layout
    # ------------------------------------------------------------------
    proj_name  = data.get('project_name', '')
    address    = data.get('address', '')
    city_state = data.get('city_state', '')
    client     = data.get('client_name', '')
    sender     = data.get('sender_name', '')
    phone      = data.get('sender_phone', '')

    addr_lines = address
    if city_state:
        addr_lines += '<br/>' + city_state

    left_col = [
        Paragraph('<b>PROJECT</b>', st['info_lbl']),
        Paragraph(proj_name, st['info_val']),
        Spacer(1, 4),
        Paragraph(addr_lines, st['info_val']),
    ]
    onsite_contact = data.get('onsite_contact', '')
    onsite_phone   = data.get('onsite_phone', '')
    mid_col = [
        Paragraph('<b>FOREMAN</b>', st['info_lbl']),
        Paragraph('_______________________________', st['info_val']),
        Spacer(1, 4),
        Paragraph('<b>PHONE</b>', st['info_lbl']),
        Paragraph('_______________________________', st['info_val']),
    ]
    if onsite_contact:
        mid_col.append(Spacer(1, 4))
        mid_col.append(Paragraph('<b>ON-SITE CONTACT</b>', st['info_lbl']))
        mid_col.append(Paragraph(onsite_contact + ('  ' + onsite_phone if onsite_phone else ''), st['info_val']))
    right_col = [
        Paragraph('<b>DATE</b>', st['info_lbl']),
        Paragraph(date_str, st['info_val']),
    ]
    if client:
        right_col.append(Spacer(1, 4))
        right_col.append(Paragraph('<b>CLIENT</b>', st['info_lbl']))
        right_col.append(Paragraph(client, st['info_val']))
    if sender:
        right_col.append(Spacer(1, 4))
        right_col.append(Paragraph('<b>ISSUED BY</b>', st['info_lbl']))
        right_col.append(Paragraph(sender + ('  ' + phone if phone else ''), st['info_val']))

    info_tbl = Table([[left_col, mid_col, right_col]], colWidths=[cw * 0.38, cw * 0.32, cw * 0.30])
    info_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('LINEBELOW',     (0, 0), (-1, -1), 0.5, TBLBORD),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.15 * inch))

    # ------------------------------------------------------------------
    # 2. Scope of Work table — NO price columns
    # ------------------------------------------------------------------
    line_items = data.get('line_items', [])
    if line_items:
        story.append(_section_banner('Scope of Work', cw))
        story.append(Spacer(1, 2))

        col_w = [cw * 0.06, cw * 0.34, cw * 0.36, cw * 0.12, cw * 0.12]
        th = ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_CENTER)
        tbl_data = [[
            Paragraph('#',           th),
            Paragraph('ITEM',        ParagraphStyle('th2', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_LEFT)),
            Paragraph('DESCRIPTION', ParagraphStyle('th3', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_LEFT)),
            Paragraph('QTY',         th),
            Paragraph('UNIT',        th),
        ]]

        for idx, item in enumerate(line_items, 1):
            name = item.get('name', '')
            desc = item.get('description', '')
            qty  = item.get('qty', 0)
            unit = item.get('unit', '')
            tbl_data.append([
                Paragraph(str(idx), st['cell_c']),
                Paragraph(name, st['item_name']),
                Paragraph(desc, st['item_desc']),
                Paragraph(_fmt_qty(qty), st['cell']),
                Paragraph(unit, st['cell_c']),
            ])

        scope_tbl = Table(tbl_data, colWidths=col_w, repeatRows=1)
        scope_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  COLHDR),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [WHITE, LGRAY]),
            ('GRID',          (0, 0), (-1, -1), 0.5, TBLBORD),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ]))
        story.append(scope_tbl)

        # Totals summary line (quantities only)
        total_tons = data.get('total_tons', 0)
        total_sf   = data.get('total_sf', 0)
        total_sy   = data.get('total_sy', 0)
        qty_parts = []
        if total_tons:
            qty_parts.append(f'{_fmt_qty(total_tons)} Tons')
        if total_sf:
            qty_parts.append(f'{_fmt_qty(total_sf)} SF')
        if total_sy:
            qty_parts.append(f'{_fmt_qty(total_sy)} SY')
        if qty_parts:
            summary_text = '&nbsp;&nbsp;|&nbsp;&nbsp;'.join(qty_parts)
            story.append(Spacer(1, 4))
            story.append(Table(
                [[Paragraph(f'<b>Totals:</b>&nbsp;&nbsp;{summary_text}',
                            ParagraphStyle('qt', fontName='Helvetica', fontSize=9,
                                           textColor=DGRAY, alignment=TA_RIGHT))]],
                colWidths=[cw]
            ))
        story.append(Spacer(1, 0.2 * inch))

    # ------------------------------------------------------------------
    # 3. Materials Summary — from sections data
    # ------------------------------------------------------------------
    sections = data.get('sections', [])
    mat_rows = []
    for sec in sections:
        layers = sec.get('layers', [])
        sec_name = sec.get('name', '')
        for layer in layers:
            mat_type = layer.get('material', layer.get('mat', ''))
            depth    = layer.get('depth', '')
            tons     = layer.get('tons', layer.get('tonnage', 0))
            if mat_type:
                mat_rows.append({
                    'section': sec_name,
                    'material': mat_type,
                    'depth': depth,
                    'tons': tons,
                })

    if mat_rows:
        story.append(_section_banner('Materials Summary', cw))
        story.append(Spacer(1, 2))

        th = ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_CENTER)
        mat_col_w = [cw * 0.30, cw * 0.30, cw * 0.15, cw * 0.25]
        mat_tbl_data = [[
            Paragraph('SECTION',   ParagraphStyle('th2', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_LEFT)),
            Paragraph('MATERIAL',  ParagraphStyle('th3', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_LEFT)),
            Paragraph('DEPTH',     th),
            Paragraph('EST. TONS', th),
        ]]

        total_mat_tons = 0
        for row in mat_rows:
            t = row['tons']
            try:
                t = float(t)
            except (ValueError, TypeError):
                t = 0
            total_mat_tons += t
            depth_str = str(row['depth']) + '"' if row['depth'] else ''
            mat_tbl_data.append([
                Paragraph(row['section'], st['cell_l']),
                Paragraph(row['material'], st['item_name']),
                Paragraph(depth_str, st['cell_c']),
                Paragraph(_fmt_qty(t) if t else '', st['cell']),
            ])

        # Total row
        mat_tbl_data.append([
            Paragraph('', st['cell_l']),
            Paragraph('<b>TOTAL</b>', ParagraphStyle('mt', fontName='Helvetica-Bold', fontSize=9, textColor=BLACK, alignment=TA_LEFT)),
            Paragraph('', st['cell_c']),
            Paragraph('<b>' + _fmt_qty(total_mat_tons) + '</b>', st['cell_b']),
        ])

        mat_tbl = Table(mat_tbl_data, colWidths=mat_col_w, repeatRows=1)
        mat_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  COLHDR),
            ('ROWBACKGROUNDS',(0, 1), (-1, -2), [WHITE, LGRAY]),
            ('BACKGROUND',    (0, -1),(-1, -1), LGRAY),
            ('GRID',          (0, 0), (-1, -1), 0.5, TBLBORD),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
            ('LINEABOVE',     (0, -1),(-1, -1), 1, BLACK),
        ]))
        story.append(mat_tbl)
        story.append(Spacer(1, 0.2 * inch))

    # ------------------------------------------------------------------
    # 4. Project Notes
    # ------------------------------------------------------------------
    notes = data.get('notes', '')
    if notes:
        story.append(_section_banner('Project Notes', cw))
        story.append(Spacer(1, 2))
        notes_box = Table(
            [[Paragraph(notes.replace('\n', '<br/>'), st['notes_body'])]],
            colWidths=[cw]
        )
        notes_box.setStyle(TableStyle([
            ('BOX',           (0, 0), (-1, -1), 0.5, TBLBORD),
            ('BACKGROUND',    (0, 0), (-1, -1), LGRAY),
            ('TOPPADDING',    (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ]))
        story.append(notes_box)
        story.append(Spacer(1, 0.25 * inch))

    # ------------------------------------------------------------------
    # 5. Crew Sign-Off
    # ------------------------------------------------------------------
    story.append(_section_banner('Crew Sign-Off', cw))
    story.append(Spacer(1, 6))

    line = '________________________________________'
    short_line = '______________________'

    signoff_data = [
        [Paragraph('<b>Foreman Signature:</b> ' + line, st['sign_lbl']),
         Paragraph('<b>Date:</b> ' + short_line, st['sign_lbl'])],
        [Paragraph('<b>Crew Members Present:</b>', st['sign_lbl']),
         Paragraph('', st['sign_lbl'])],
        [Paragraph('1. ' + line, st['sign_lbl']),
         Paragraph('2. ' + line, st['sign_lbl'])],
        [Paragraph('3. ' + line, st['sign_lbl']),
         Paragraph('4. ' + line, st['sign_lbl'])],
        [Paragraph('5. ' + line, st['sign_lbl']),
         Paragraph('6. ' + line, st['sign_lbl'])],
    ]

    signoff_tbl = Table(signoff_data, colWidths=[cw * 0.5, cw * 0.5])
    signoff_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    story.append(signoff_tbl)
    story.append(Spacer(1, 0.15 * inch))

    # Work completed line
    completed_data = [
        [Paragraph('<b>\u2610&nbsp;&nbsp;Work Completed</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
                   '<b>Date Completed:</b> ' + short_line + '&nbsp;&nbsp;&nbsp;&nbsp;'
                   '<b>Foreman Initials:</b> __________',
                   ParagraphStyle('wc', fontName='Helvetica', fontSize=10, textColor=BLACK))]
    ]
    completed_tbl = Table(completed_data, colWidths=[cw])
    completed_tbl.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 1, BLACK),
        ('BACKGROUND',    (0, 0), (-1, -1), LGRAY),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
    ]))
    story.append(completed_tbl)

    # ------------------------------------------------------------------
    # Build PDF
    # ------------------------------------------------------------------
    doc.build(story, canvasmaker=canvas_maker(date_str))


if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    out  = sys.argv[2] if len(sys.argv) > 2 else '/tmp/work_order.pdf'
    build(data, out)
    print('OK:', out)
