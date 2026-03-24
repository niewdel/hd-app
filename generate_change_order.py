"""
HD Hauling & Grading - Change Order PDF Generator
Matches proposal PDF formatting (HDCanvas header, info_block, bid-table style, signature block).
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

# ── Brand colours ────────────────────────────────────────────────────────────
RED     = colors.HexColor('#CC0000')
BLACK   = colors.HexColor('#111111')
WHITE   = colors.HexColor('#FFFFFF')
LGRAY   = colors.HexColor('#F4F4F4')
MGRAY   = colors.HexColor('#CCCCCC')
DGRAY   = colors.HexColor('#555555')
TBLBORD = colors.HexColor('#CCCCCC')
ROWALT  = colors.HexColor('#EEEEEE')
GREEN   = colors.HexColor('#27500A')
DRED    = colors.HexColor('#A32D2D')

# ── Page geometry ────────────────────────────────────────────────────────────
W, H = letter
_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(_DIR, 'hd_logo.png')
if not os.path.exists(LOGO):
    LOGO = os.path.join(_DIR, 'hd_logo_cropped.png')
LM = RM = 0.5 * inch
TM = 1.05 * inch
BM = 0.6  * inch


def fi(n):
    """Format a number as $X,XXX.XX (without the dollar sign)."""
    return '{:,.2f}'.format(n)


def S():
    """Shared paragraph styles."""
    return {
        'info_lbl':   ParagraphStyle('il',  fontName='Helvetica-Bold', fontSize=8,  textColor=BLACK),
        'info_val':   ParagraphStyle('iv',  fontName='Helvetica',      fontSize=8,  textColor=DGRAY, leading=11),
        'item_name':  ParagraphStyle('in2', fontName='Helvetica-Bold', fontSize=9,  textColor=BLACK, leading=12),
        'cell':       ParagraphStyle('c',   fontName='Helvetica',      fontSize=9,  textColor=BLACK, alignment=TA_RIGHT),
        'cell_b':     ParagraphStyle('cb',  fontName='Helvetica-Bold', fontSize=9,  textColor=BLACK, alignment=TA_RIGHT),
        'cell_l':     ParagraphStyle('cl',  fontName='Helvetica',      fontSize=9,  textColor=BLACK, alignment=TA_LEFT),
        'body':       ParagraphStyle('bd',  fontName='Helvetica',      fontSize=9,  textColor=DGRAY, leading=13),
        'section':    ParagraphStyle('sc',  fontName='Helvetica-Bold', fontSize=10, textColor=RED),
        'notice':     ParagraphStyle('no',  fontName='Helvetica-Oblique', fontSize=8, textColor=DGRAY, alignment=TA_CENTER, leading=13),
    }


# ── HDCanvas — repeating header + page numbers on every page ─────────────────

class HDCanvas(pdfcanvas.Canvas):
    """Custom canvas that draws the HD header and page numbers on every page."""
    def __init__(self, *args, **kwargs):
        self._co_number = kwargs.pop('co_number', 1)
        self._date_str  = kwargs.pop('date_str', '')
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
        # Logo top-left
        if os.path.exists(LOGO):
            self.drawImage(LOGO, LM, H - 0.82 * inch,
                           width=1.25 * inch, height=0.52 * inch,
                           preserveAspectRatio=True, mask='auto')
        # "CHANGE ORDER #X" top-right
        self.setFont('Helvetica-Bold', 19)
        self.setFillColor(BLACK)
        self.drawRightString(W - RM, H - 0.52 * inch,
                             f'CHANGE ORDER #{self._co_number}')
        # Date below that
        self.setFont('Helvetica', 9)
        self.setFillColor(DGRAY)
        self.drawRightString(W - RM, H - 0.70 * inch, self._date_str)
        # Horizontal rule
        self.setStrokeColor(BLACK)
        self.setLineWidth(1.0)
        self.line(LM, H - 0.88 * inch, W - RM, H - 0.88 * inch)
        self.restoreState()

    def _draw_footer(self):
        self.saveState()
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#AAAAAA'))
        self.drawCentredString(W / 2, BM * 0.45,
                               f'Page {self._page_index} of {self._page_total}')
        self.restoreState()


def canvas_maker(co_number, date_str):
    class _C(HDCanvas):
        def __init__(self, *a, **kw):
            kw['co_number'] = co_number
            kw['date_str']  = date_str
            super().__init__(*a, **kw)
    return _C


# ── Info block (3-column, matches proposal) ──────────────────────────────────

def info_block(data, st):
    FW = W - inch

    title_s  = ParagraphStyle('c_t',  fontName='Helvetica-Bold', fontSize=11,
                               textColor=BLACK, leading=14)
    addr_s   = ParagraphStyle('c_a',  fontName='Helvetica',      fontSize=8,
                               textColor=DGRAY, leading=11)
    date_s   = ParagraphStyle('c_d',  fontName='Helvetica-Bold', fontSize=8,
                               textColor=RED,   leading=11)
    sec_s    = ParagraphStyle('c_sec',fontName='Helvetica-Bold', fontSize=7,
                               textColor=RED,   leading=9, spaceAfter=2)
    name_s   = ParagraphStyle('c_n',  fontName='Helvetica-Bold', fontSize=9,
                               textColor=BLACK, leading=12)
    detail_s = ParagraphStyle('c_det',fontName='Helvetica',      fontSize=8,
                               textColor=DGRAY, leading=11)

    proj_cell = [
        Paragraph(data.get('project_name', ''), title_s),
        Paragraph(data.get('address', ''), addr_s),
        Spacer(1, 3),
        Paragraph(data.get('date', ''), date_s),
    ]

    by_cell = [
        Paragraph('ISSUED BY', sec_s),
        Paragraph(data.get('sender_name', ''), name_s),
        Paragraph(data.get('sender_email', ''), detail_s),
        Paragraph(data.get('sender_phone', ''), detail_s),
    ]

    for_cell = [
        Paragraph('ISSUED TO', sec_s),
        Paragraph(data.get('client_name', ''), name_s),
        Paragraph(data.get('client_email', ''), detail_s),
        Paragraph(data.get('client_phone', ''), detail_s),
    ]

    cw_proj = FW * 0.42
    cw_by   = FW * 0.27
    cw_for  = FW * 0.31

    wrapper = Table([[proj_cell, by_cell, for_cell]],
                    colWidths=[cw_proj, cw_by, cw_for], hAlign='LEFT')
    wrapper.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (0, -1),  0),
        ('LEFTPADDING',   (1, 0), (-1, -1), 14),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('LINEBEFORE',    (1, 0), (1, -1),  1.0, MGRAY),
        ('LINEBEFORE',    (2, 0), (2, -1),  1.0, MGRAY),
        ('LINEABOVE',     (0, 0), (-1, 0),  1.0, BLACK),
        ('LINEBELOW',     (0, -1),(-1, -1), 1.0, MGRAY),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND',    (0, 0), (-1, -1), WHITE),
    ]))
    return wrapper


# ── Original contract info ───────────────────────────────────────────────────

def original_contract_block(data, st):
    cw = W - inch
    orig_date = data.get('orig_contract_date', '')
    orig_amt  = data.get('orig_contract_amount', 0)

    lbl_s = ParagraphStyle('ocl', fontName='Helvetica-Bold', fontSize=8,
                            textColor=DGRAY, leading=11)
    val_s = ParagraphStyle('ocv', fontName='Helvetica', fontSize=9,
                            textColor=BLACK, leading=12)

    rows = [
        [Paragraph('ORIGINAL CONTRACT DATE', lbl_s), Paragraph(orig_date, val_s),
         Paragraph('ORIGINAL CONTRACT AMOUNT', lbl_s), Paragraph('$' + fi(orig_amt), val_s)],
    ]
    t = Table(rows, colWidths=[cw * 0.22, cw * 0.28, cw * 0.26, cw * 0.24])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LGRAY),
        ('BOX',           (0, 0), (-1, -1), 0.5, TBLBORD),
        ('LINEBEFORE',    (2, 0), (2, -1),  0.3, TBLBORD),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (-1, 0),(-1, -1), 8),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


# ── Description block (red left-border) ─────────────────────────────────────

def description_block(text, st):
    if not text:
        return []
    cw = W - inch
    hdr = Table([[Paragraph('DESCRIPTION OF CHANGE', st['section'])]], colWidths=[cw])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#F6F6F6')),
        ('LINEBEFORE',    (0, 0), (0, -1),  4, RED),
        ('LINEBELOW',     (0, 0), (-1, -1), 0.5, TBLBORD),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
    ]))
    body_s = ParagraphStyle('desc_body', fontName='Helvetica', fontSize=9,
                             textColor=DGRAY, leading=13)
    body = Table([[Paragraph(text, body_s)]], colWidths=[cw])
    body.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.5, TBLBORD),
        ('BACKGROUND',    (0, 0), (-1, -1), WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    return [hdr, body]


# ── Line items table (bid-table style) ───────────────────────────────────────

def items_table(items, st):
    if not items:
        return []
    cw = W - inch

    ban_s = ParagraphStyle('ban', fontName='Helvetica-Bold', fontSize=10,
                            textColor=WHITE, alignment=TA_CENTER)
    ch_l  = ParagraphStyle('chl', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE)
    ch_r  = ParagraphStyle('chr', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_RIGHT)
    ch_c  = ParagraphStyle('chc', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_CENTER)

    rows = [
        # Red banner row (will be spanned)
        [Paragraph('Change Order Items', ban_s), '', '', '', '', ''],
        # Dark column header row
        [Paragraph('Type', ch_c), Paragraph('Description', ch_l),
         Paragraph('Qty', ch_r), Paragraph('Unit', ch_c),
         Paragraph('Unit Price', ch_r), Paragraph('Subtotal', ch_r)],
    ]

    col_w = [cw * 0.10, cw * 0.38, cw * 0.10, cw * 0.10, cw * 0.16, cw * 0.16]

    for item in items:
        t = item.get('type', 'add')
        type_color = GREEN if t == 'add' else DRED if t == 'deduct' else DGRAY
        type_label = 'ADD' if t == 'add' else 'DEDUCT' if t == 'deduct' else 'NO COST'
        sub = item.get('subtotal', 0)
        sub_str   = '--' if t == 'nocost' else ('$' + fi(sub))
        price_str = '--' if t == 'nocost' else ('$' + fi(item.get('price', 0)))

        rows.append([
            Paragraph(f'<b>{type_label}</b>',
                      ParagraphStyle('ty', fontName='Helvetica-Bold', fontSize=8,
                                     textColor=type_color, alignment=TA_CENTER)),
            Paragraph(item.get('description', ''), st['cell_l']),
            Paragraph(str(item.get('qty', 1)), st['cell']),
            Paragraph(item.get('unit', 'LS'),
                      ParagraphStyle('uc', fontName='Helvetica', fontSize=9,
                                     textColor=BLACK, alignment=TA_CENTER)),
            Paragraph(price_str, st['cell']),
            Paragraph(sub_str,   st['cell_b']),
        ])

    col_hdr_h = 0.28 * inch
    row_heights = [None, col_hdr_h] + [None] * (len(rows) - 2)

    t = Table(rows, colWidths=col_w, rowHeights=row_heights, repeatRows=2)
    ts = [
        # Red banner
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), RED),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        # Dark column header
        ('BACKGROUND',    (0, 1), (-1, 1), colors.HexColor('#4A4A4A')),
        ('TOPPADDING',    (0, 1), (-1, 1), 7),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 7),
        ('LEFTPADDING',   (0, 1), (0, 1),  8),
        ('RIGHTPADDING',  (-1, 1),(-1, 1), 8),
        # Data rows
        ('TOPPADDING',    (0, 2), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 2), (-1, -1), 4),
        ('LEFTPADDING',   (0, 2), (0, -1),  8),
        ('RIGHTPADDING',  (-1, 2),(-1, -1), 8),
        ('LINEBELOW',     (0, 2), (-1, -1), 0.3, TBLBORD),
        # Global
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (2, 0), (-1, -1), 'RIGHT'),
        ('ALIGN',         (0, 0), (0, -1),  'CENTER'),
        ('ALIGN',         (3, 0), (3, -1),  'CENTER'),
        ('BOX',           (0, 0), (-1, -1), 0.5, TBLBORD),
    ]
    # Alternating row backgrounds
    for i in range(2, len(rows)):
        if i % 2 == 0:
            ts.append(('BACKGROUND', (0, i), (-1, i), ROWALT))
    t.setStyle(TableStyle(ts))
    return [t]


# ── Cost summary ─────────────────────────────────────────────────────────────

def cost_summary(data, st):
    cw = W - inch
    orig_amt     = data.get('orig_contract_amount', 0)
    add_total    = data.get('add_total', 0)
    deduct_total = data.get('deduct_total', 0)
    revised      = data.get('revised_total', orig_amt)

    lbl_s = ParagraphStyle('csl', fontName='Helvetica', fontSize=9, textColor=DGRAY)
    val_s = ParagraphStyle('csv', fontName='Helvetica', fontSize=9, textColor=BLACK, alignment=TA_RIGHT)

    sum_data = [
        [Paragraph('Original Contract Amount', lbl_s),
         Paragraph('$' + fi(orig_amt), val_s)],
        [Paragraph('This Change Order (Add)',
                   ParagraphStyle('ga', fontName='Helvetica', fontSize=9, textColor=GREEN)),
         Paragraph('+$' + fi(add_total),
                   ParagraphStyle('gv', fontName='Helvetica', fontSize=9, textColor=GREEN, alignment=TA_RIGHT))],
        [Paragraph('This Change Order (Deduct)',
                   ParagraphStyle('ra', fontName='Helvetica', fontSize=9, textColor=DRED)),
         Paragraph('-$' + fi(deduct_total),
                   ParagraphStyle('rv', fontName='Helvetica', fontSize=9, textColor=DRED, alignment=TA_RIGHT))],
    ]
    sum_tbl = Table(sum_data, colWidths=[cw * 0.6, cw * 0.4])
    sum_tbl.setStyle(TableStyle([
        ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('LINEBELOW',     (0, -1),(-1, -1), 0.5, TBLBORD),
    ]))

    # Revised total row (matches proposal CONTRACT TOTAL style)
    tot_lbl = ParagraphStyle('tl', fontName='Helvetica-Bold', fontSize=11,
                              textColor=BLACK, leading=11)
    tot_val = ParagraphStyle('tv', fontName='Helvetica-Bold', fontSize=11,
                              textColor=BLACK, leading=11, alignment=TA_RIGHT)
    tot_row = Table([[Paragraph('REVISED CONTRACT TOTAL', tot_lbl),
                      Paragraph('$' + fi(revised), tot_val)]],
                    colWidths=[cw * 0.60, cw * 0.40],
                    rowHeights=[0.44 * inch])
    tot_row.setStyle(TableStyle([
        ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND',    (0, 0), (-1, -1), LGRAY),
        ('LINEABOVE',     (0, 0), (-1, 0),  1, TBLBORD),
        ('LINEBELOW',     (0, -1),(-1, -1), 2, RED),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))

    return [sum_tbl, tot_row]


# ── Signature block (bilateral, matches proposal) ───────────────────────────

def signature_block(data, st):
    cw = W - inch
    client      = data.get('client_name', '')
    orig_date   = data.get('orig_contract_date', '')

    # Authorization language
    auth_text = (
        'This Change Order is hereby incorporated into and made part of the original Agreement '
        'dated ' + orig_date + ' between HD Hauling &amp; Grading ("Contractor") and '
        + client + ' ("Customer"). All terms and conditions of the original Agreement remain '
        'in full force and effect. Work described herein shall not commence until this Change '
        'Order has been executed by both parties.'
    )

    body_s   = ParagraphStyle('sb',  fontName='Helvetica',      fontSize=9,
                               textColor=BLACK, leading=14)
    body_b_s = ParagraphStyle('sbb', fontName='Helvetica-Bold', fontSize=9,
                               textColor=BLACK, leading=14)

    sig_data = [
        [Paragraph('<b>HD Hauling &amp; Grading</b>', body_b_s),
         Paragraph('<b>Client / Authorized Representative</b>', body_b_s)],
        [Paragraph('Authorized Signature: ___________________________', body_s),
         Paragraph('Authorized Signature: ___________________________', body_s)],
        [Paragraph('Printed Name: _________________________________', body_s),
         Paragraph('Printed Name: _________________________________', body_s)],
        [Paragraph('Title: _________________________________________', body_s),
         Paragraph('Title: _________________________________________', body_s)],
        [Paragraph('Date: __________________________________________', body_s),
         Paragraph('Date: __________________________________________', body_s)],
    ]
    sig_tbl = Table(sig_data, colWidths=[cw / 2, cw / 2])
    sig_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (-1, 0),(-1, -1), 4),
        ('LINEABOVE',     (0, 0), (-1, 0),  1, TBLBORD),
        ('LINEBELOW',     (0, -1),(-1, -1), 1, TBLBORD),
    ]))

    return [
        Paragraph(auth_text, st['notice']),
        Spacer(1, 0.18 * inch),
        sig_tbl,
    ]


# ── Main build ───────────────────────────────────────────────────────────────

def build(data, out_path):
    st = S()
    co_num   = data.get('co_number', 1)
    date_str = data.get('date', '')

    doc = SimpleDocTemplate(
        out_path,
        pagesize=letter,
        title=f'Change Order #{co_num}',
        author='HD Hauling & Grading',
        leftMargin=LM, rightMargin=RM,
        topMargin=TM,  bottomMargin=BM,
    )

    story = []

    # 1. Info block (project / issued by / issued to)
    story.append(info_block(data, st))
    story.append(Spacer(1, 0.14 * inch))

    # 2. Original contract info
    story.append(original_contract_block(data, st))
    story.append(Spacer(1, 0.14 * inch))

    # 3. Description of change
    desc_elems = description_block(data.get('description', ''), st)
    if desc_elems:
        story.extend(desc_elems)
        story.append(Spacer(1, 0.14 * inch))

    # 4. Line items table
    items_elems = items_table(data.get('line_items', []), st)
    if items_elems:
        story.extend(items_elems)
        story.append(Spacer(1, 0.08 * inch))

    # 5. Cost summary + revised total
    story.extend(cost_summary(data, st))
    story.append(Spacer(1, 0.25 * inch))

    # 6. Signature block
    story.append(KeepTogether(signature_block(data, st)))

    # Build with custom canvas for headers + page numbers
    doc.build(story, canvasmaker=canvas_maker(co_num, date_str))


if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    out  = sys.argv[2] if len(sys.argv) > 2 else '/tmp/change_order.pdf'
    build(data, out)
    print('OK:', out)
