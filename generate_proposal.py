import json, sys, os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable, PageBreak, KeepTogether)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus.flowables import Flowable

RED     = colors.HexColor('#CC0000')
BLACK   = colors.HexColor('#000000')
WHITE   = colors.HexColor('#FFFFFF')
LGRAY   = colors.HexColor('#F4F4F4')
MGRAY   = colors.HexColor('#CCCCCC')
COLHDR  = colors.HexColor('#3A3A3A')
SECHDR  = colors.HexColor('#222222')
DGRAY   = colors.HexColor('#555555')
TBLBORD = colors.HexColor('#CCCCCC')
ROWALT  = colors.HexColor('#EEEEEE')

W, H    = letter
# Resolve logo path relative to this file so it works both locally and on Railway
_DIR    = os.path.dirname(os.path.abspath(__file__))
LOGO    = os.path.join(_DIR, 'hd_logo.png')
if not os.path.exists(LOGO):
    LOGO = os.path.join(_DIR, 'hd_logo_cropped.png')
LM = RM = 0.5 * inch
TM = 1.05 * inch
BM = 0.6  * inch

def S():
    return {
        'info_hdr':    ParagraphStyle('ih',  fontName='Helvetica-Bold', fontSize=8,   textColor=BLACK, alignment=TA_CENTER),
        'info_lbl':    ParagraphStyle('il',  fontName='Helvetica-Bold', fontSize=8,   textColor=BLACK),
        'info_val':    ParagraphStyle('iv',  fontName='Helvetica',      fontSize=8,   textColor=DGRAY, leading=11),
        'info_val_sm': ParagraphStyle('ivs', fontName='Helvetica',      fontSize=7,   textColor=DGRAY, leading=10),
        'notes_hdr':   ParagraphStyle('nh',  fontName='Helvetica-Bold', fontSize=10,  textColor=WHITE, alignment=TA_CENTER),
        'notes_body':  ParagraphStyle('nb',  fontName='Helvetica',      fontSize=9,   textColor=DGRAY, leading=13),

        'item_name':   ParagraphStyle('in2', fontName='Helvetica-Bold', fontSize=9,   textColor=BLACK, leading=12),
        'cell':        ParagraphStyle('c',   fontName='Helvetica',      fontSize=9,   textColor=BLACK, alignment=TA_RIGHT),
        'cell_b':      ParagraphStyle('cb',  fontName='Helvetica-Bold', fontSize=9,   textColor=BLACK, alignment=TA_RIGHT),
        'appr_hdr':    ParagraphStyle('ah',  fontName='Helvetica-Bold', fontSize=10,  textColor=WHITE),
        'appr_lbl':    ParagraphStyle('al',  fontName='Helvetica-Bold', fontSize=10,  textColor=BLACK),
        'appr_val':    ParagraphStyle('av',  fontName='Helvetica',      fontSize=9,   textColor=DGRAY),
        'tc_section':  ParagraphStyle('ts',  fontName='Helvetica-Bold', fontSize=9,   textColor=colors.HexColor('#CC0000')),
        'tc_body':     ParagraphStyle('tb',  fontName='Helvetica',      fontSize=8,   textColor=DGRAY, leading=14, spaceBefore=1, spaceAfter=5),
        'tc_bullet':   ParagraphStyle('tbul',fontName='Helvetica',      fontSize=8,   textColor=DGRAY, leading=14, leftIndent=16, bulletIndent=2, spaceBefore=1, spaceAfter=4),
    }

class HDCanvas(pdfcanvas.Canvas):
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
            self._page_total  = total
            if i > 0:
                self._draw_header()
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)
    def _draw_header(self):
        self.saveState()
        if os.path.exists(LOGO):
            self.drawImage(LOGO, LM, H - 0.82*inch, width=1.25*inch, height=0.52*inch,
                           preserveAspectRatio=True, mask='auto')
        self.setFont('Helvetica-Bold', 19)
        self.setFillColor(BLACK)
        self.drawRightString(W - RM, H - 0.52*inch, 'PROPOSAL & CONTRACT')
        self.setFont('Helvetica', 9)
        self.setFillColor(DGRAY)
        self.drawRightString(W - RM, H - 0.70*inch, self._date)
        self.setStrokeColor(BLACK)
        self.setLineWidth(1.0)
        self.line(LM, H - 0.88*inch, W - RM, H - 0.88*inch)
        # Page number bottom center
        total = len(self._pages)
        page_num = self._pages.index({k:v for k,v in self.__dict__.items()
                                       if k in self._pages[0]}) + 1 if False else None
        # simpler: derive from save order
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#AAAAAA'))
        self.drawCentredString(W / 2, BM * 0.45, f'Page {self._page_index} of {self._page_total}')
        self.restoreState()


def canvas_maker(date_str):
    class _C(HDCanvas):
        def __init__(self, *a, **kw):
            kw['date_str'] = date_str
            super().__init__(*a, **kw)
    return _C

class CoverPage(Flowable):
    def __init__(self, data):
        super().__init__()
        self.data = data
    def wrap(self, aw, ah):
        self._aw, self._ah = aw, ah
        return aw, ah
    def draw(self):
        c  = self.canv
        d  = self.data
        aw = self._aw
        ah = self._ah
        mid = (W / 2) - LM

        if os.path.exists(LOGO):
            lw = 5.04 * inch
            lh = 2.1  * inch
            c.drawImage(LOGO, mid - lw/2, ah * 0.50, width=lw, height=lh,
                        preserveAspectRatio=True, mask='auto')

        c.setFont('Helvetica-Bold', 26)
        c.setFillColor(BLACK)
        c.drawCentredString(mid, ah * 0.454, d.get('project_name', 'Proposal'))

        c.setStrokeColor(MGRAY)
        c.setLineWidth(0.75)
        c.line(mid - 2.6*inch, ah * 0.437, mid + 2.6*inch, ah * 0.437)

        # ~15% more spacing below divider before subtitle
        c.setFont('Helvetica', 18)
        c.setFillColor(DGRAY)
        c.drawCentredString(mid, ah * 0.408, 'Proposal & Contract')

        date_str = d.get('date', '')
        if date_str:
            c.setFont('Helvetica', 13)
            c.setFillColor(colors.HexColor('#999999'))
            # ~15% more spacing between subtitle and date
            c.drawCentredString(mid, ah * 0.384, date_str)

        fy = 0.55 * inch
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(BLACK)
        c.drawString(LM, fy + 0.58*inch, 'Prepared by:')
        c.setFont('Helvetica', 10)
        c.setFillColor(DGRAY)
        c.drawString(LM, fy + 0.36*inch, d.get('sender_name', ''))
        c.drawString(LM, fy + 0.16*inch, d.get('company', 'HD Hauling & Grading'))

        rx = aw * 0.55
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(BLACK)
        c.drawString(rx, fy + 0.58*inch, 'Prepared for:')
        c.setFont('Helvetica', 10)
        c.setFillColor(DGRAY)
        c.drawString(rx, fy + 0.36*inch, d.get('client_name', ''))
        c.drawString(rx, fy + 0.16*inch, d.get('client_company', ''))

def info_block(data, st):
    """Option C - single horizontal band, no boxes, subtle lines."""
    FW = W - inch
    title_s  = ParagraphStyle('c_t',   fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, leading=14)
    addr_s   = ParagraphStyle('c_a',   fontName='Helvetica',      fontSize=8,  textColor=DGRAY, leading=11)
    date_s   = ParagraphStyle('c_d',   fontName='Helvetica-Bold', fontSize=8,  textColor=RED,   leading=11)
    sec_s    = ParagraphStyle('c_sec', fontName='Helvetica-Bold', fontSize=7,  textColor=RED,   leading=9,  spaceAfter=2)
    name_s   = ParagraphStyle('c_n',   fontName='Helvetica-Bold', fontSize=9,  textColor=BLACK, leading=12)
    detail_s = ParagraphStyle('c_det', fontName='Helvetica',      fontSize=8,  textColor=DGRAY, leading=11)
    proj_cell = [
        Paragraph(data.get('project_name', ''), title_s),
        Paragraph(', '.join(filter(None, [data.get('address',''), data.get('city_state','')])), addr_s),
        Spacer(1, 3),
        Paragraph(data.get('date', ''), date_s),
    ]
    by_cell = [
        Paragraph('PREPARED BY', sec_s),
        Paragraph(data.get('sender_name',  ''), name_s),
        Paragraph(data.get('sender_email', ''), detail_s),
        Paragraph(data.get('sender_phone', ''), detail_s),
    ]
    for_cell = [
        Paragraph('PREPARED FOR', sec_s),
        Paragraph(data.get('client_name',  ''), name_s),
        Paragraph(data.get('client_email', ''), detail_s),
        Paragraph(data.get('client_phone', ''), detail_s),
    ]
    cw_proj = FW * 0.42
    cw_by   = FW * 0.27
    cw_for  = FW * 0.31
    wrapper = Table([[proj_cell, by_cell, for_cell]], colWidths=[cw_proj, cw_by, cw_for], hAlign='LEFT')
    wrapper.setStyle(TableStyle([
        ('TOPPADDING',    (0,0),(-1,-1), 10),
        ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ('LEFTPADDING',   (0,0),(0,-1),  0),
        ('LEFTPADDING',   (1,0),(-1,-1), 14),
        ('RIGHTPADDING',  (0,0),(-1,-1), 6),
        ('LINEBEFORE',    (1,0),(1,-1),  1.0, MGRAY),
        ('LINEBEFORE',    (2,0),(2,-1),  1.0, MGRAY),
        ('LINEABOVE',     (0,0),(-1,0),  1.0, BLACK),
        ('LINEBELOW',     (0,-1),(-1,-1),1.0, MGRAY),
        ('VALIGN',        (0,0),(-1,-1), 'TOP'),
        ('BACKGROUND',    (0,0),(-1,-1), WHITE),
    ]))
    return wrapper

def notes_block(text, st):
    body_text = (text or '').strip()
    if not body_text:
        return []
    notes_s = ParagraphStyle('nb2', fontName='Helvetica', fontSize=9,
                              textColor=DGRAY, leading=13)
    body = Table([[Paragraph('<b>Notes:</b>  ' + body_text, notes_s)]],
                 colWidths=[W-inch])
    body.setStyle(TableStyle([
        ('BOX',         (0,0),(-1,-1), 0.5, TBLBORD),
        ('BACKGROUND',  (0,0),(-1,-1), WHITE),
        ('TOPPADDING',  (0,0),(-1,-1), 8),
        ('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('LEFTPADDING', (0,0),(-1,-1), 10),
        ('RIGHTPADDING',(0,0),(-1,-1), 10),
    ]))
    return [body]

def bid_table(items, st):
    cw = W - inch
    ch_l = ParagraphStyle('chl', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE)
    ch_r = ParagraphStyle('chr', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_RIGHT)

    ban_l = ParagraphStyle('banl', fontName='Helvetica-Bold', fontSize=10, textColor=WHITE, alignment=TA_CENTER)
    rows = [
        [Paragraph('Bid Items', ban_l), '', '', '', ''],
        [Paragraph('Item &amp; Design', ch_l), Paragraph('Qty',ch_r),
         Paragraph('Unit',ch_r), Paragraph('Price',ch_r), Paragraph('Subtotal',ch_r)],
    ]
    for item in items:
        name  = item.get('name','')
        desc  = item.get('description','')
        qty   = item.get('qty','')
        unit  = item.get('unit','SY')
        price = item.get('price',0)
        sub   = item.get('subtotal',0)
        if isinstance(qty,(int,float)):
            qty_s = f'{int(qty):,}' if qty==int(qty) else f'{qty:,.1f}'
        else:
            qty_s = str(qty).strip().split()[0] if str(qty).strip() else ''
        rows.append([
            Paragraph(f'<b>{name}</b><br/><font size="8" color="#777777">{desc}</font>', st['item_name']),
            Paragraph(qty_s, st['cell']),
            Paragraph(unit,  st['cell']),
            Paragraph(f'${price:,.2f}', st['cell']),
            Paragraph(f'${sub:,.2f}',   st['cell_b']),
        ])

    # Row heights ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ banner auto-sizes (matches Project Notes header), col header fixed
    col_hdr_h = 0.28 * inch
    row_heights = [None, col_hdr_h] + [None] * (len(rows) - 2)
    t = Table(rows, colWidths=[cw*0.50, cw*0.10, cw*0.10, cw*0.15, cw*0.15],
              rowHeights=row_heights)
    ts = [
        ('SPAN',(0,0),(-1,0)), ('BACKGROUND',(0,0),(-1,0),RED), ('ALIGN',(0,0),(-1,0),'CENTER'),
        ('TOPPADDING',(0,0),(-1,0),6), ('BOTTOMPADDING',(0,0),(-1,0),6),
        ('BACKGROUND',(0,1),(-1,1),colors.HexColor('#4A4A4A')),
        ('TOPPADDING',(0,1),(-1,1),7), ('BOTTOMPADDING',(0,1),(-1,1),7),
        ('LEFTPADDING',(0,1),(0,1),8), ('RIGHTPADDING',(-1,1),(-1,1),8),
        ('TOPPADDING',(0,2),(-1,-1),4), ('BOTTOMPADDING',(0,2),(-1,-1),4),
        ('LEFTPADDING',(0,2),(0,-1),8), ('RIGHTPADDING',(-1,2),(-1,-1),8),
        ('LINEBELOW',(0,2),(-1,-1),0.3,TBLBORD),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('ALIGN',(1,0),(-1,-1),'RIGHT'),
        ('BOX',(0,0),(-1,-1),0.5,TBLBORD),
    ]
    for i in range(2, len(rows)):
        if i % 2 == 0:
            ts.append(('BACKGROUND',(0,i),(-1,i),ROWALT))
    t.setStyle(TableStyle(ts))
    return t

def total_line(total):
    """CO-style contract total ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ bold label + amount on gray background
    with a thick red underline, matching the Change Order PDF styling."""
    cw  = W - inch
    lbl = ParagraphStyle('tl', fontName='Helvetica-Bold', fontSize=13,
                          textColor=BLACK, leading=13, spaceAfter=0, spaceBefore=0)
    val = ParagraphStyle('tv', fontName='Helvetica-Bold', fontSize=13,
                          textColor=BLACK, leading=13, spaceAfter=0, spaceBefore=0,
                          alignment=TA_RIGHT)
    t = Table([[Paragraph('CONTRACT TOTAL', lbl),
                Paragraph(f'${total:,.2f}', val)]],
              colWidths=[cw * 0.60, cw * 0.40])
    t.setStyle(TableStyle([
        ('ALIGN',         (1,0),(1,-1),  'RIGHT'),
        ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
        ('BACKGROUND',    (0,0),(-1,-1), LGRAY),
        ('LINEABOVE',     (0,0),(-1,0),  1,   TBLBORD),
        ('LINEBELOW',     (0,-1),(-1,-1),2,   RED),
        ('TOPPADDING',    (0,0),(-1,-1), 10),
        ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ('LEFTPADDING',   (0,0),(0,-1),  10),
        ('RIGHTPADDING',  (-1,0),(-1,-1),10),
    ]))
    return t

class SitePlanPage(Flowable):
    def wrap(self, aw, ah):
        self._aw, self._ah = aw, ah
        return aw, ah
    def draw(self):
        c = self.canv
        c.setStrokeColor(MGRAY)
        c.setLineWidth(1)
        c.setDash(6,4)
        c.rect(0, 0, self._aw, self._ah, stroke=1, fill=0)
        c.setDash()
        cx, cy = self._aw/2, self._ah/2
        c.setFont('Helvetica-Bold', 14)
        c.setFillColor(MGRAY)
        c.drawCentredString(cx, cy + 0.2*inch, 'Site Plan / Drawing')
        c.setFont('Helvetica', 10)
        c.drawCentredString(cx, cy - 0.1*inch, 'Replace this page with site plan image')
        c.drawCentredString(cx, cy - 0.32*inch, 'or attach separately before sending to client')

def red_hdr(text, st, cw):
    t = Table([[Paragraph(text, st['appr_hdr'])]], colWidths=[cw])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),RED),
        ('TOPPADDING',(0,0),(-1,-1),7), ('BOTTOMPADDING',(0,0),(-1,-1),7),
        ('LEFTPADDING',(0,0),(-1,-1),8),
    ]))
    return t

def approval_page(data, st):
    elems = []
    cw = W - inch
    total = data.get('total', 0)

    # ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Section header ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
    elems.append(red_hdr('Client Approval & Authorization', st, cw))
    elems.append(Spacer(1, 0.14*inch))

    # ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Project summary box ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
    lbl_s = ParagraphStyle('psl', fontName='Helvetica-Bold', fontSize=8,
                            textColor=DGRAY, leading=11)
    val_s = ParagraphStyle('psv', fontName='Helvetica',      fontSize=9,
                            textColor=BLACK, leading=12)
    proj   = data.get('project_name', '')
    client = data.get('client_name',  '')
    addr   = ', '.join(filter(None,[data.get('address',''), data.get('city_state','')]))
    date   = data.get('date', '')

    sum_rows = [
        [Paragraph('PROJECT',  lbl_s), Paragraph(proj,   val_s),
         Paragraph('CLIENT',   lbl_s), Paragraph(client, val_s)],
        [Paragraph('ADDRESS',  lbl_s), Paragraph(addr,   val_s),
         Paragraph('DATE',     lbl_s), Paragraph(date,   val_s)],
    ]
    sum_t = Table(sum_rows,
                  colWidths=[cw*0.12, cw*0.38, cw*0.12, cw*0.38])
    sum_t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), LGRAY),
        ('BOX',          (0,0),(-1,-1), 0.5, TBLBORD),
        ('LINEBELOW',    (0,0),(-1,0),  0.3, TBLBORD),
        ('LINEBEFORE',   (2,0),(2,-1),  0.3, TBLBORD),
        ('TOPPADDING',   (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('LEFTPADDING',  (0,0),(-1,-1), 8),
        ('RIGHTPADDING', (-1,0),(-1,-1),8),
        ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
    ]))
    elems.append(sum_t)
    elems.append(Spacer(1, 0.14*inch))

    # ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Approved contract value (print-friendly ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ matches contract total style) ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
    amt_lbl = ParagraphStyle('al2', fontName='Helvetica-Bold', fontSize=13,
                              textColor=BLACK, leading=13, spaceAfter=0, spaceBefore=0)
    amt_val = ParagraphStyle('av2', fontName='Helvetica-Bold', fontSize=13,
                              textColor=BLACK, leading=13, spaceAfter=0, spaceBefore=0,
                              alignment=TA_RIGHT)
    amt_t = Table([[Paragraph('APPROVED CONTRACT VALUE', amt_lbl),
                    Paragraph(f'${total:,.2f}', amt_val)]],
                  colWidths=[cw*0.60, cw*0.40])
    amt_t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), LGRAY),
        ('LINEABOVE',    (0,0),(-1,0),  1,   TBLBORD),
        ('LINEBELOW',    (0,0),(-1,-1), 2,   RED),
        ('TOPPADDING',   (0,0),(-1,-1), 10),
        ('BOTTOMPADDING',(0,0),(-1,-1), 10),
        ('LEFTPADDING',  (0,0),(-1,-1), 10),
        ('RIGHTPADDING', (-1,0),(-1,-1),10),
        ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
        ('ALIGN',        (1,0),(1,-1),  'RIGHT'),
    ]))
    elems.append(amt_t)
    elems.append(Spacer(1, 0.18*inch))

    # ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Authorization language ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
    auth_st = ParagraphStyle('auth', fontName='Helvetica-Oblique', fontSize=8,
                              textColor=DGRAY, leading=13, alignment=TA_CENTER)
    elems.append(Paragraph(
        'By signing below, Client authorizes HD Hauling &amp; Grading to proceed with the work '
        'described in this Proposal &amp; Contract and agrees to be bound by all terms and '
        'conditions set forth herein.',
        auth_st))
    elems.append(Spacer(1, 0.18*inch))

    # ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Bilateral signature block ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ CO style ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
    body_st   = ParagraphStyle('sb',  fontName='Helvetica',      fontSize=9,
                                textColor=BLACK, leading=14)
    body_b_st = ParagraphStyle('sbb', fontName='Helvetica-Bold', fontSize=9,
                                textColor=BLACK, leading=14)

    sig_data = [
        [Paragraph('<b>HD Hauling &amp; Grading</b>', body_b_st),
         Paragraph('<b>Client / Authorized Representative</b>', body_b_st)],
        [Paragraph('Authorized Signature: ___________________________', body_st),
         Paragraph('Authorized Signature: ___________________________', body_st)],
        [Paragraph('Printed Name: _________________________________', body_st),
         Paragraph('Printed Name: _________________________________', body_st)],
        [Paragraph('Title: _________________________________________', body_st),
         Paragraph('Title: _________________________________________', body_st)],
        [Paragraph('Date: __________________________________________', body_st),
         Paragraph('Date: __________________________________________', body_st)],
    ]
    sig_tbl = Table(sig_data, colWidths=[cw/2, cw/2])
    sig_tbl.setStyle(TableStyle([
        ('VALIGN',        (0,0),(-1,-1), 'TOP'),
        ('TOPPADDING',    (0,0),(-1,-1), 7),
        ('BOTTOMPADDING', (0,0),(-1,-1), 7),
        ('LEFTPADDING',   (0,0),(-1,-1), 4),
        ('RIGHTPADDING',  (-1,0),(-1,-1),4),
        ('LINEABOVE',     (0,0),(-1,0),  1,   TBLBORD),
        ('LINEBELOW',     (0,-1),(-1,-1),1,   TBLBORD),
    ]))
    elems.append(sig_tbl)
    elems.append(Spacer(1, 0.22*inch))

    # ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Paving Overage Unit Prices ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Option C (bid-table style) ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
    unit_items = data.get('unit_prices', [])
    if unit_items:
        ch_l = ParagraphStyle('ucl', fontName='Helvetica-Bold', fontSize=8,
                               textColor=WHITE)
        ch_r = ParagraphStyle('ucr', fontName='Helvetica-Bold', fontSize=8,
                               textColor=WHITE, alignment=TA_RIGHT)
        up_rows = [
            # Red banner
            [Paragraph('Additional Unit Prices', ParagraphStyle(
                'ub', fontName='Helvetica-Bold', fontSize=10,
                textColor=WHITE, alignment=TA_CENTER)), ''],
            # Black column header
            [Paragraph('Description', ch_l), Paragraph('Unit Rate', ch_r)],
        ]
        for item in unit_items:
            up_rows.append([
                Paragraph(item['name'], ParagraphStyle(
                    'un', fontName='Helvetica', fontSize=9, textColor=BLACK)),
                Paragraph(f'${item["rate"]:,.2f}', ParagraphStyle(
                    'uv', fontName='Helvetica-Bold', fontSize=9,
                    textColor=BLACK, alignment=TA_RIGHT)),
            ])

        up_t = Table(up_rows,
                     colWidths=[cw*0.78, cw*0.22],
                     rowHeights=[None, 0.28*inch] + [None]*(len(up_rows)-2))
        up_ts = [
            # Red banner
            ('SPAN',         (0,0),(-1,0)),
            ('BACKGROUND',   (0,0),(-1,0),  RED),
            ('ALIGN',        (0,0),(-1,0),  'CENTER'),
            ('TOPPADDING',   (0,0),(-1,0),  6),
            ('BOTTOMPADDING',(0,0),(-1,0),  6),
            # Black column header
            ('BACKGROUND',   (0,1),(-1,1),  colors.HexColor('#4A4A4A')),
            ('TOPPADDING',   (0,1),(-1,1),  7),
            ('BOTTOMPADDING',(0,1),(-1,1),  7),
            # Data rows
            ('TOPPADDING',   (0,2),(-1,-1), 6),
            ('BOTTOMPADDING',(0,2),(-1,-1), 6),
            ('LINEBELOW',    (0,2),(-1,-2), 0.3, TBLBORD),
            ('LINEBELOW',    (0,-1),(-1,-1),1.5, RED),
            # Global
            ('LEFTPADDING',  (0,0),(-1,-1), 8),
            ('RIGHTPADDING', (-1,0),(-1,-1),8),
            ('ALIGN',        (1,0),(1,-1),  'RIGHT'),
            ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
            ('BOX',          (0,0),(-1,-1), 0.5, TBLBORD),
        ]
        for i in range(2, len(up_rows)):
            if i % 2 == 0:
                up_ts.append(('BACKGROUND', (0,i),(-1,i), ROWALT))
        up_t.setStyle(TableStyle(up_ts))
        elems.append(up_t)

    return elems

def tc_block(title, body_items, st, cw):
    """Returns a KeepTogether block for one T&C section."""
    hdr = Table([[Paragraph(title, st['tc_section'])]], colWidths=[cw])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), colors.HexColor('#F6F6F6')),
        ('LINEBEFORE',   (0,0),(0,-1),  4, RED),
        ('LINEBELOW',    (0,0),(-1,-1), 0.5, TBLBORD),
        ('TOPPADDING',   (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('LEFTPADDING',  (0,0),(-1,-1), 10),
    ]))
    items = [hdr, Spacer(1, 0.04*inch)]
    for item in body_items:
        if item.startswith('ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢'):
            items.append(Paragraph(item, st['tc_bullet']))
        else:
            items.append(Paragraph(item, st['tc_body']))
    items.append(Spacer(1, 0.06*inch))
    return KeepTogether(items)

def tc_pages(st):
    cw = W - inch
    elems = []

    elems.append(Paragraph('Terms & Conditions',
        ParagraphStyle('tch', fontName='Helvetica-Bold', fontSize=14,
                       alignment=TA_CENTER, spaceAfter=6)))
    elems.append(HRFlowable(width='100%', thickness=1, color=RED, spaceAfter=10))

    sections = [
        ('1. Contract Formation & Binding Agreement', [
            'This Proposal & Contract becomes legally binding upon execution by both the Customer/Purchaser and HD Hauling & Grading. Any conditions not expressly set forth herein shall not be recognized unless documented in writing and signed by authorized representatives of both parties. Verbal agreements, purchase orders, or prior understandings do not modify or supersede this contract unless incorporated by written amendment.',
        ]),
        ('2. Proposal Validity', [
            'Pricing in this proposal is valid for thirty (30) calendar days from the date of issuance. HD Hauling & Grading reserves the right to withdraw or modify this proposal if not executed within that period, including adjustments for material price changes.',
        ]),
        ('3. Scope of Work', [
            'HD Hauling & Grading\'s scope is limited to the paving, concrete, striping, and signage work explicitly described in the Bid Items section of this document. No additional work, modifications, or extensions of scope are included unless captured in a written, signed Change Order prior to commencement of that work.',
        ]),
        ('4. Change Orders', [
            'Any modification to the approved scope of work ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ including additions, deletions, substitutions, or design changes ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ requires a written Change Order executed by both parties before work begins. HD Hauling & Grading shall not be obligated to perform out-of-scope work without an approved Change Order and is not liable for delays caused by scope changes requested after contract execution.',
        ]),
        ('5. Site Access & Staging', [
            'The Customer shall provide HD Hauling & Grading with unobstructed vehicular access to the project site, a designated staging area for equipment and materials, and a safe haul route for loaded delivery trucks for the duration of work.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Delays, re-mobilizations, or standby time caused by restricted access, site conflicts with other trades, or unavailability of the work area will be billed at the applicable unit rates in the Paving Overage Unit Prices.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Customer is responsible for ensuring underground utilities are located and marked prior to the start of work. HD Hauling & Grading is not liable for damage to unmarked utilities.',
        ]),
        ('6. Subgrade Acceptance & Pavement Performance', [
            'HD Hauling & Grading is not responsible for pavement failure, cracking, settlement, or premature deterioration resulting from inadequate subgrade preparation, insufficient base compaction, poor drainage, or unsuitable sub-base materials outside HD Hauling & Grading\'s scope of work.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Prior to paving, the Customer or their designated representative is responsible for ensuring the subgrade and base course have been properly graded, compacted to NCDOT specifications, proof-rolled where required, and inspected. Commencement of paving constitutes Customer\'s acceptance of subgrade conditions.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Proof rolling, moisture content testing, and base course density testing are the responsibility of the Customer unless explicitly included in the scope of work.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ If HD Hauling & Grading identifies conditions that may affect pavement performance, written notification will be provided. Customer\'s direction to proceed releases HD Hauling & Grading from performance liability related to those conditions.',
        ]),
        ('7. Materials & NCDOT Specifications', [
            'All asphalt materials furnished by HD Hauling & Grading shall conform to the applicable NCDOT Standard Specifications for Roads and Structures, current edition, unless otherwise specified in writing. Mix type, aggregate gradation, and binder content shall be per the mix design designated in the Bid Items.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Material substitutions required due to plant availability or supply chain disruptions will be communicated promptly. Functionally equivalent materials will be substituted at no additional cost.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ HD Hauling & Grading does not guarantee long-term availability of specific mix designs or material sources.',
        ]),
        ('8. Weather & Temperature Conditions ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Asphalt', [
            'Asphalt paving will not be performed under the following conditions: ambient or surface temperatures below 40ÃÂÃÂÃÂÃÂ°F and falling; during rain, sleet, or snow; when the base course contains standing water or frost; or when forecast conditions within four (4) hours are anticipated to compromise compaction or curing.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Schedule adjustments caused by weather are not grounds for price renegotiation, penalties, or liquidated damages against HD Hauling & Grading.',
        ]),
        ('9. Concrete Work Conditions', [
            'All concrete work shall be performed in accordance with applicable ACI standards and NCDOT specifications. Concrete will not be placed when ambient temperatures are below 40ÃÂÃÂÃÂÃÂ°F without approved cold-weather protection measures, or when temperatures exceed 90ÃÂÃÂÃÂÃÂ°F without appropriate hot-weather precautions.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Form layout, grade stakes, and joint locations must be approved by the Customer or their representative prior to placement. Once concrete is placed, corrections to layout or elevation are billable as additional work.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Cure time and form removal timing will be determined by HD Hauling & Grading based on ambient conditions and mix design requirements. Customer requests to accelerate form removal or trafficking of concrete prior to adequate cure are at Customer\'s sole risk.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ HD Hauling & Grading is not responsible for surface defects, cracking, or scaling resulting from: improper curing practices by others, premature trafficking, freeze-thaw cycles, de-icing chemical application, or subgrade settlement outside HD Hauling & Grading\'s scope.',
        ]),
        ('10. Compaction & Quality', [
            'Asphalt pavement compaction shall meet NCDOT density requirements for the specified mix type. If compaction testing is required, the Customer is responsible for providing an independent testing agency.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ HD Hauling & Grading is not liable for compaction failures resulting from: mix temperature loss during transport caused by factors outside its control, Customer-caused delays between delivery and laydown, or subgrade instability.',
        ]),
        ('11. Warranty', [
            'HD Hauling & Grading warrants all materials and workmanship for one (1) year from the date of substantial completion. This warranty covers defects in materials and workmanship performed directly by HD Hauling & Grading.',
            'This warranty expressly excludes:',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Damage from petroleum products, chemical spills, or de-icing agents',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Pavement failure from subgrade conditions not prepared by HD Hauling & Grading',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Damage from vehicle loads exceeding pavement design capacity',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Deterioration adjacent to a repaired area on maintenance projects',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Pavement markings or signage not installed by HD Hauling & Grading',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Normal wear, surface oxidation, and expected pavement aging',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Damage from third parties, acts of God, or events beyond HD Hauling & Grading\'s control',
            'For maintenance and repair projects, the warranty applies only to the specific area(s) of new work.',
        ]),
        ('12. Traffic Control & Permits', [
            'If included in the Bid Items, HD Hauling & Grading will provide traffic control in general conformance with the MUTCD for the duration of active paving operations.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ The Customer is responsible for all permits, right-of-way authorizations, and NCDOT lane closure approvals prior to the scheduled start of work.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ ADA compliance determinations for pavement markings, curb ramps, and accessible routes are the responsibility of the Owner and Engineer of Record.',
        ]),
        ('13. Pavement Markings & Signage', [
            'Pavement markings will be installed per the approved plan or layout provided by the Customer. HD Hauling & Grading is not responsible for incorrect layouts resulting from inaccurate field dimensions or conflicting plans.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Thermoplastic markings require a minimum asphalt cure period before application.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Signage installation will follow locations and specifications provided. Sign content, ADA designation, and regulatory compliance are the Customer\'s responsibility.',
        ]),
        ('14. Limitation of Liability', [
            'HD Hauling & Grading\'s total liability under this contract, regardless of cause, shall not exceed the total contract value. In no event shall HD Hauling & Grading be liable for consequential, incidental, indirect, or punitive damages, including but not limited to loss of use, lost revenue, business interruption, or third-party claims arising from delays or defects.',
        ]),
        ('15. Payment Terms', [
            'All invoices are due Net 30 (thirty calendar days from the invoice date). Invoices will be submitted upon completion of each defined phase of work or on a monthly basis, whichever occurs first.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Balances not received within thirty (30) days accrue interest at 1.5% per month (18% annually).',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ Final payment is due within thirty (30) calendar days of the final completion invoice. Where applicable and agreed in writing, retention may be withheld per the terms of the prime contract, but shall be released no later than thirty (30) days after final completion and acceptance of HD Hauling & Grading\'s scope of work.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ The individual executing this contract on behalf of the Customer/Purchaser provides a personal guarantee for full payment of all principal and accrued interest.',
        ]),
        ('16. Lien Rights', [
            'HD Hauling & Grading expressly reserves its right to file a Claim of Lien pursuant to N.C.G.S. Chapter 44A in the event of non-payment. Nothing herein constitutes a waiver of lien rights. In the event legal action is required, the Customer shall be responsible for all reasonable attorney\'s fees and collection costs per N.C.G.S. ÃÂÃÂÃÂÃÂ§ 44A-35.',
        ]),
        ('17. Material Pricing & Availability', [
            'Due to volatility in liquid asphalt, aggregate, and fuel markets, material costs may be adjusted to reflect prevailing market rates if costs increase more than ten percent (10%) from the proposal date. Written notice will be provided prior to any adjustment.',
            'ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¢ HD Hauling & Grading is not liable for delays caused by plant shutdowns, material shortages, or supplier issues.',
        ]),
        ('18. Force Majeure', [
            'HD Hauling & Grading shall not be liable for delays or failure to perform caused by circumstances beyond its reasonable control, including acts of God, severe weather, labor disputes, government actions, supply chain disruptions, fuel shortages, or public health emergencies. The schedule will be extended by a reasonable period and pricing may be subject to renegotiation.',
        ]),
        ('19. Entire Agreement', [
            'This Proposal & Contract is the entire agreement between the parties with respect to the work described herein. It supersedes all prior proposals, representations, and understandings. No terms printed on the Customer\'s purchase orders shall apply unless explicitly incorporated by written amendment signed by both parties.',
        ]),
        ('20. Dispute Resolution', [
            'The parties agree to attempt to resolve any dispute arising under this Proposal & Contract through good-faith negotiation prior to initiating formal proceedings. If a dispute cannot be resolved through negotiation within thirty (30) days of written notice, either party may pursue resolution through binding arbitration administered under the rules of the American Arbitration Association, or by filing a claim in a court of competent jurisdiction in the State of North Carolina.',
            '\u2022 This Proposal & Contract shall be governed by and construed in accordance with the laws of the State of North Carolina, without regard to its conflict of law provisions.',
            '\u2022 The prevailing party in any arbitration or litigation arising from this Proposal & Contract shall be entitled to recover reasonable attorney\u2019s fees and costs from the non-prevailing party.',
        ]),
    ]

    for title, body in sections:
        elems.append(tc_block(title, body, st, cw))

    return elems

def build(data, out_path):
    st = S()
    proj_title = data.get('project_name', 'HD Hauling & Grading Proposal')
    doc = SimpleDocTemplate(out_path, pagesize=letter,
                             leftMargin=LM, rightMargin=RM,
                             topMargin=TM, bottomMargin=BM,
                             title=proj_title,
                             author='HD Hauling & Grading',
                             subject='Proposal & Contract')
    story = []

    story.append(CoverPage(data))
    story.append(PageBreak())

    story.append(info_block(data, st))
    story.append(Spacer(1, 0.12*inch))
    story += notes_block(data.get('notes',''), st)
    story.append(Spacer(1, 0.12*inch))
    story.append(bid_table(data.get('line_items',[]), st))
    story.append(Spacer(1, 0.1*inch))
    story.append(total_line(data.get('total',0)))
    story.append(PageBreak())

    if data.get('site_plan_image'):
        story.append(SitePlanPage())
        story.append(PageBreak())

    story += tc_pages(st)
    story.append(PageBreak())

    story += approval_page(data, st)

    doc.build(story, canvasmaker=canvas_maker(data.get('date','')))
    print(f'OK: {out_path}')

if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    out  = sys.argv[2] if len(sys.argv) > 2 else '/mnt/user-data/outputs/HD_Proposal.pdf'
    build(data, out)
