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
LOGO    = os.path.join(os.path.dirname(__file__), "hd_logo.png")
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
        'bid_title':   ParagraphStyle('bt',  fontName='Helvetica-Bold', fontSize=11,  textColor=WHITE, alignment=TA_CENTER),
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
        c.drawString(LM, fy + 0.58*inch, 'Created by:')
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
    """Three-column stacked layout. Each column has a header row then
    label-above-value pairs â no side-by-side label/value split, so
    long emails and addresses never wrap awkwardly."""

    lbl_s  = ParagraphStyle('ibl', fontName='Helvetica-Bold', fontSize=7,
                             textColor=DGRAY, leading=10, spaceBefore=4)
    val_s  = ParagraphStyle('iva', fontName='Helvetica',      fontSize=8,
                             textColor=BLACK, leading=11, spaceAfter=2)
    hdr_s  = ParagraphStyle('ihd', fontName='Helvetica-Bold', fontSize=8,
                             textColor=BLACK, alignment=TA_CENTER)

    def make_col(title, pairs):
        parts = [Paragraph(title, hdr_s)]
        for lbl, val in pairs:
            parts.append(Paragraph(lbl, lbl_s))
            parts.append(Paragraph(val or 'â', val_s))
        return parts

    from reportlab.platypus import Frame
    cw = (W - inch) / 3 - 2  # slight gap between cols

    def col_table(title, pairs):
        """Each column is its own single-cell table containing stacked paragraphs."""
        content = make_col(title, pairs)
        # Wrap in a single-cell table
        # Split into header row + content row so we can draw a rule between them
        hdr_para = content[0]   # Paragraph('Project/Sender/Client Information')
        body_content = content[1:]  # Spacer + label/value pairs

        inner = Table([
            [hdr_para],
            [body_content],
        ], colWidths=[cw - 2])
        inner.setStyle(TableStyle([
            ('LINEBELOW',    (0,0), (-1,0),  0.75, colors.HexColor('#CCCCCC')),
            ('BACKGROUND',   (0,0), (-1,0),  colors.HexColor('#F7F7F7')),
            ('TOPPADDING',   (0,0), (-1,0),  6),
            ('BOTTOMPADDING',(0,0), (-1,0),  5),
            ('LEFTPADDING',  (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING',   (0,1), (-1,1),  5),
            ('BOTTOMPADDING',(0,1), (-1,1),  6),
            ('VALIGN',       (0,0), (-1,-1), 'TOP'),
        ]))
        t = Table([[inner]], colWidths=[cw])
        t.setStyle(TableStyle([
            ('BOX',         (0,0),(-1,-1), 0.5, TBLBORD),
            ('TOPPADDING',  (0,0),(-1,-1), 0),
            ('BOTTOMPADDING',(0,0),(-1,-1),0),
            ('LEFTPADDING', (0,0),(-1,-1), 0),
            ('RIGHTPADDING',(0,0),(-1,-1), 0),
        ]))
        return t

    proj_t = col_table('Project Information', [
        ('Project Name', data.get('project_name','')),
        ('Street Address', data.get('address','')),
        ('City, State', data.get('city_state','')),
    ])
    send_t = col_table('Sender Information', [
        ('Name', data.get('sender_name','')),
        ('Email', data.get('sender_email','')),
        ('Phone', data.get('sender_phone','')),
    ])
    cli_t  = col_table('Client Information', [
        ('Name', data.get('client_name','')),
        ('Email', data.get('client_email','')),
        ('Phone', data.get('client_phone','')),
    ])

    # Lay all three side by side in a wrapper table
    gap = 4
    wrapper = Table([[proj_t, send_t, cli_t]],
                    colWidths=[cw, cw, cw],
                    hAlign='LEFT')
    wrapper.setStyle(TableStyle([
        ('LEFTPADDING',  (0,0),(-1,-1), 2),
        ('RIGHTPADDING', (0,0),(-1,-1), 2),
        ('TOPPADDING',   (0,0),(-1,-1), 0),
        ('BOTTOMPADDING',(0,0),(-1,-1), 0),
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
    ]))
    return wrapper

def notes_block(text, st):
    body_text = (text or '').strip()
    if not body_text:
        return []
    hdr = Table([[Paragraph('Project Notes', st['notes_hdr'])]], colWidths=[W-inch])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),BLACK),
        ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),8),
    ]))
    body = Table([[Paragraph(body_text, st['notes_body'])]], colWidths=[W-inch])
    body.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),0.5,TBLBORD),
        ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),8), ('RIGHTPADDING',(0,0),(-1,-1),8),
    ]))
    return [hdr, body]

def bid_table(items, st):
    cw = W - inch
    ch_l = ParagraphStyle('chl', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE)
    ch_r = ParagraphStyle('chr', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE, alignment=TA_RIGHT)

    rows = [
        [Paragraph('Bid Items', st['bid_title']), '', '', '', ''],
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
        qty_s = f'{int(qty):,}' if isinstance(qty,(int,float)) and qty==int(qty) else str(qty)
        rows.append([
            Paragraph(f'<b>{name}</b><br/><font size="8" color="#777777">{desc}</font>', st['item_name']),
            Paragraph(qty_s, st['cell']),
            Paragraph(unit,  st['cell']),
            Paragraph(f'${price:,.2f}', st['cell']),
            Paragraph(f'${sub:,.2f}',   st['cell_b']),
        ])

    # Build explicit row heights: both header rows forced short
    banner_h  = 0.26 * inch   # red Bid Items banner
    col_hdr_h = 0.20 * inch   # col-label row
    row_heights = [banner_h, col_hdr_h] + [None] * (len(rows) - 2)
    t = Table(rows, colWidths=[cw*0.50, cw*0.10, cw*0.10, cw*0.15, cw*0.15],
              rowHeights=row_heights)
    ts = [
        ('SPAN',(0,0),(-1,0)), ('BACKGROUND',(0,0),(-1,0),RED), ('ALIGN',(0,0),(-1,0),'CENTER'),
        ('TOPPADDING',(0,0),(-1,0),3), ('BOTTOMPADDING',(0,0),(-1,0),3),
        ('BACKGROUND',(0,1),(-1,1),COLHDR),
        ('TOPPADDING',(0,1),(-1,1),2), ('BOTTOMPADDING',(0,1),(-1,1),2),
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
    """Clean right-aligned total â label in regular weight, amount in bold black.
    No box, no background. Just a subtle top rule and generous spacing so it
    reads as a natural footer to the table above it."""
    cw  = W - inch
    lbl = ParagraphStyle('tl', fontName='Helvetica',      fontSize=10,
                          textColor=DGRAY, alignment=TA_RIGHT)
    val = ParagraphStyle('tv', fontName='Helvetica-Bold', fontSize=13,
                          textColor=BLACK, alignment=TA_RIGHT)
    t = Table([[Paragraph('TOTAL BID PRICE:', lbl),
                Paragraph(f'${total:,.2f}', val)]],
              colWidths=[cw * 0.68, cw * 0.32])
    t.setStyle(TableStyle([
        ('LINEABOVE',     (0,0),(-1,0),  0.5, TBLBORD),
        ('TOPPADDING',    (0,0),(-1,-1), 10),
        ('BOTTOMPADDING', (0,0),(-1,-1), 6),
        ('LEFTPADDING',   (0,0),(-1,-1), 0),
        ('RIGHTPADDING',  (-1,0),(-1,-1),0),
        ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
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
    elems.append(red_hdr('Client Approval', st, cw))
    total = data.get('total',0)
    val_lbl = ParagraphStyle('vl', fontName='Helvetica-Bold', fontSize=9, textColor=DGRAY)
    val_amt = ParagraphStyle('va', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, alignment=TA_RIGHT)
    sig_rows = [
        # Approved value: label left, amount right, same row
        [Paragraph('<b>Approved Value:</b>', st['appr_lbl']),
         Paragraph(f'${total:,.2f}', val_amt)],
        [Paragraph('<b>Full Name:</b>',   st['appr_lbl']), ''],
        [Paragraph('<b>Date Signed:</b>', st['appr_lbl']), ''],
        [Paragraph('<b>Signature:</b>',   st['appr_lbl']), ''],
    ]
    sig_t = Table(sig_rows, colWidths=[cw*0.40, cw*0.60])
    sig_t.setStyle(TableStyle([
        ('BOX',           (0,0),(-1,-1), 0.5, TBLBORD),
        ('LINEBELOW',     (0,0),(-1,-2), 0.3, TBLBORD),
        ('TOPPADDING',    (0,0),(-1,-1), 8),
        ('BOTTOMPADDING', (0,0),(-1,-2), 8),
        ('BOTTOMPADDING', (0,-1),(-1,-1), 36),
        ('LEFTPADDING',   (0,0),(-1,-1), 8),
        ('RIGHTPADDING',  (-1,0),(-1,-1), 8),
        ('ALIGN',         (1,0),(1,0),   'RIGHT'),
        ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
        ('SPAN',          (0,-1),(-1,-1)),
        ('BACKGROUND',    (0,0),(-1,0),  colors.HexColor('#FAFAFA')),
    ]))
    elems.append(sig_t)
    elems.append(Spacer(1, 0.18*inch))

    unit_items = data.get('unit_prices',[])
    if unit_items:
        elems.append(red_hdr('Paving Overage Unit Prices', st, cw))
        up_rows = []
        for item in unit_items:
            up_rows.append([
                Paragraph(item['name'], st['appr_val']),
                Paragraph(f'${item["rate"]:,.2f}', st['cell']),
            ])
        up_t = Table(up_rows, colWidths=[cw*0.78, cw*0.22])
        up_ts = [
            ('BOX',(0,0),(-1,-1),0.5,TBLBORD),
            ('LINEBELOW',(0,0),(-1,-2),0.3,TBLBORD),
            ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('LEFTPADDING',(0,0),(-1,-1),8), ('RIGHTPADDING',(-1,0),(-1,-1),8),
            ('ALIGN',(1,0),(1,-1),'RIGHT'), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ]
        for i in range(len(up_rows)):
            if i % 2 == 0:
                up_ts.append(('BACKGROUND',(0,i),(-1,i),LGRAY))
        up_t.setStyle(TableStyle(up_ts))
        elems.append(up_t)
    return elems

def tc_block(title, body_items, st, cw):
    hdr = Table([[Paragraph(title, st['tc_section'])]], colWidths=[cw])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), colors.HexColor('#F6F6F6')),
        ('LINEBEFORE',   (0,0),(0,-1),  4, RED),
        ('LINEBELOW',    (0,0),(-1,-1), 0.5, TBLBRD),
        ('TOPPADDING',   (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('LEFTPADDING',  (0,0),(-1,-1), 10),
    ]))
    items = [hdr, Spacer(1, 0.04*inch)]
    for item in body_items:
        if item.startswith('\u2022'):
            items.append(Paragraph(item, st['tc_bullet']))
        else:
            items.append(Paragraph(item, st['tc_body']))
    items.append(Spacer(1, 0.06*inch))
    return KeepTogether(items)


def tc_pages(st):
    cw = W - inch
    elems = []
    elems.append(Paragraph('Terms &amp; Conditions',
        ParagraphStyle('tch', fontName='Helvetica-Bold', fontSize=14,
                       alignment=TA_CENTER, spaceAfter=6)))
    elems.append(HRFlowable(width='100%', thickness=1, color=BLACK, spaceAfter=10))

    sections = [
        ('1. Contract Formation &amp; Binding Agreement', [
            'This Proposal and Contract becomes legally binding upon execution by both the Customer/Purchaser and HD Hauling &amp; Grading. Any conditions not expressly set forth herein shall not be recognized unless documented in writing and signed by authorized representatives of both parties. Verbal agreements, purchase orders, or prior understandings do not modify or supersede this contract unless incorporated by written amendment.',
        ]),
        ('2. Proposal Validity', [
            'Pricing in this proposal is valid for thirty (30) calendar days from the date of issuance. HD Hauling &amp; Grading reserves the right to withdraw or modify this proposal if not executed within that period, including adjustments for material price changes. If work has not commenced within sixty (60) days of contract execution, HD Hauling &amp; Grading reserves the right to reprice the contract to reflect current material and labor costs.',
        ]),
        ('3. Scope of Work', [
            "HD Hauling &amp; Grading's scope is limited to the paving, concrete, striping, and signage work explicitly described in the Bid Items section of this document. No additional work, modifications, or extensions of scope are included unless captured in a written, signed Change Order prior to commencement of that work.",
        ]),
        ('4. Changed Conditions', [
            'If HD Hauling &amp; Grading encounters subsurface or concealed conditions that differ materially from those indicated in the contract documents -- including but not limited to rock, unsuitable soils, organic material, underground obstructions, undocumented utilities, or excessive groundwater -- HD Hauling &amp; Grading shall promptly notify the Customer in writing.',
            '\u2022 All work related to changed conditions shall be subject to a written Change Order executed before additional work proceeds.',
            "\u2022 HD Hauling &amp; Grading is not liable for schedule delays or cost overruns resulting from changed conditions not visible during a standard site walkthrough.",
            "\u2022 If utilities are not located and marked prior to start of work by NC 811, the Customer assumes full responsibility for any damage to underground infrastructure.",
        ]),
        ('5. Change Orders', [
            'Any modification to the approved scope of work requires a written Change Order executed by both parties before work begins. HD Hauling &amp; Grading shall not be obligated to perform out-of-scope work without an approved Change Order.',
            '\u2022 Unit prices for overage work are listed in the Paving Overage Unit Prices section and shall apply to all approved change order work of similar type.',
        ]),
        ('6. Site Access &amp; Staging', [
            'The Customer shall provide HD Hauling &amp; Grading with unobstructed vehicular access to the project site, a designated staging area for equipment and materials, and a safe haul route for loaded delivery trucks for the duration of work.',
            '\u2022 Delays, re-mobilizations, or standby time caused by restricted access or site conflicts will be billed at applicable unit rates.',
            "\u2022 Customer is responsible for ensuring underground utilities are marked by NC 811 prior to start. HD Hauling &amp; Grading is not liable for damage to unmarked or inaccurately marked utilities.",
        ]),
        ("7. Subgrade Acceptance &amp; Pavement Performance", [
            "HD Hauling &amp; Grading is not responsible for pavement failure, cracking, or settlement resulting from inadequate subgrade preparation, poor drainage, or unsuitable sub-base materials outside HD Hauling &amp; Grading's scope of work.",
            "\u2022 Commencement of paving constitutes Customer's acceptance of subgrade conditions. Customer is responsible for ensuring subgrade has been properly graded, compacted to NCDOT specifications, and proof-rolled prior to paving.",
            "\u2022 If HD Hauling &amp; Grading identifies conditions that may affect pavement performance, written notification will be provided. Customer's direction to proceed releases HD Hauling &amp; Grading from performance liability related to those conditions.",
        ]),
        ("8. Materials &amp; NCDOT Specifications", [
            "All asphalt materials shall conform to the applicable NCDOT Standard Specifications for Roads and Structures, current edition, unless otherwise specified in writing.",
            "\u2022 Material substitutions required due to plant availability or supply chain disruptions will be communicated promptly. Functionally equivalent materials will be substituted at no additional cost.",
        ]),
        ("9. Weather &amp; Temperature Conditions", [
            "Asphalt paving will be performed in accordance with NCDOT temperature and weather placement requirements for the specified mix type. Work will not proceed during rain, sleet, or snow; or when the base course contains standing water or frost.",
            "\u2022 Schedule adjustments caused by weather are not grounds for price renegotiation, penalties, or liquidated damages against HD Hauling &amp; Grading.",
            "\u2022 Concrete placement shall comply with ACI 305R (hot weather) and ACI 306R (cold weather) requirements as applicable.",
        ]),
        ("10. Compaction &amp; Quality", [
            "Asphalt pavement compaction shall meet NCDOT density requirements for the specified mix type. If compaction testing is required by the Owner or Engineer of Record, the Customer is responsible for providing an independent testing agency at Customer's expense.",
        ]),
        ("11. Warranty", [
            "HD Hauling &amp; Grading warrants all materials and workmanship against defects for one (1) year from the date of substantial completion. This warranty is limited to defects in materials and workmanship directly performed by HD Hauling &amp; Grading under this contract.",
            "This warranty expressly excludes:",
            "\u2022 Damage from petroleum products, chemical spills, or de-icing agents",
            "\u2022 Pavement failure attributable to subgrade or base conditions not prepared by HD Hauling &amp; Grading",
            "\u2022 Damage from vehicle loads exceeding the pavement design capacity",
            "\u2022 Reflective cracking from existing pavement on mill-and-pave or overlay projects",
            "\u2022 Normal surface oxidation, weathering, raveling, and expected pavement aging",
            "\u2022 Damage from third parties, acts of God, flooding, or events beyond HD Hauling &amp; Grading's control",
            "Warranty claims must be submitted in writing within the warranty period. HD Hauling &amp; Grading's sole obligation is repair or replacement of the defective work at HD Hauling &amp; Grading's discretion.",
        ]),
        ("12. Traffic Control &amp; Permits", [
            "If included in the Bid Items, HD Hauling &amp; Grading will provide traffic control in general conformance with the MUTCD for the duration of active paving operations only.",
            "\u2022 The Customer is responsible for all permits, right-of-way authorizations, NCDOT encroachment agreements, and lane closure approvals prior to the scheduled start of work.",
        ]),
        ("13. Limitation of Liability", [
            "HD Hauling &amp; Grading's total liability under this contract shall not exceed the total contract price paid. In no event shall HD Hauling &amp; Grading be liable for consequential, incidental, indirect, special, or punitive damages, including loss of use, lost revenue, business interruption, or third-party claims.",
        ]),
        ("14. Payment Terms", [
            "Payment is due Net 30 -- all invoices are due and payable within thirty (30) calendar days of the invoice date. Invoices will be issued upon substantial completion of the work or upon completion of each defined phase, whichever occurs first.",
            "\u2022 Any balance not received within thirty (30) days of the invoice date shall accrue interest at the rate of 1.5% per month (18% per annum) on the outstanding balance, calculated from the invoice date until paid in full.",
            "\u2022 HD Hauling &amp; Grading reserves the right to suspend work if any invoice remains outstanding beyond thirty (30) days. Schedule delays resulting from payment-related work suspensions are the Customer's responsibility.",
            "\u2022 The individual executing this contract provides a personal guarantee for full payment of all principal, accrued interest, attorneys' fees, and collection costs.",
            "\u2022 Disputed invoice amounts must be submitted in writing within ten (10) days of the invoice date. Undisputed portions remain due per these terms.",
        ]),
        ("15. Lien Rights &amp; Collections", [
            "NOTICE: HD Hauling &amp; Grading is a licensed contractor in the State of North Carolina. HD Hauling &amp; Grading expressly reserves its right to file a Claim of Lien against the property and a Bond Claim against any applicable payment bond pursuant to N.C.G.S. Chapter 44A in the event of non-payment.",
            "\u2022 Nothing in this contract constitutes a waiver of lien rights.",
            "\u2022 In the event legal action is required to collect payment, the Customer shall be responsible for all reasonable attorneys' fees, court costs, and collection expenses per N.C.G.S. SS 44A-35.",
        ]),
        ("16. Material Pricing &amp; Availability", [
            "Due to volatility in liquid asphalt index (LAI) pricing and aggregate costs, material costs may be adjusted if costs increase more than ten percent (10%) from the proposal date to the date of material purchase. Written notice will be provided prior to any adjustment.",
        ]),
        ("17. Force Majeure", [
            "HD Hauling &amp; Grading shall not be liable for delays caused by acts of God, severe weather, labor disputes, government actions, supply chain disruptions, fuel shortages, or other circumstances beyond its reasonable control. The project schedule shall be extended accordingly.",
        ]),
        ("18. Dispute Resolution", [
            "This contract shall be governed by the laws of the State of North Carolina. The parties agree to attempt good-faith negotiation before pursuing formal legal action. Venue for any legal proceedings shall be in the county where the project is located.",
        ]),
        ("19. Entire Agreement", [
            "This Proposal and Contract constitutes the entire agreement between the parties and supersedes all prior proposals, representations, and understandings. No terms printed on Customer's purchase orders shall apply unless explicitly incorporated by written amendment signed by both parties.",
        ]),
    ]

    for title, body in sections:
        elems.append(tc_block(title, body, st, cw))

    # Execution signature block
    elems.append(Spacer(1, 0.3*inch))
    sig_data = [
        [Paragraph('<b>HD Hauling &amp; Grading</b>', st['body']),
         Paragraph('<b>Customer / Purchaser</b>', st['body'])],
        [Paragraph('Authorized Signature: ___________________________', st['body']),
         Paragraph('Authorized Signature: ___________________________', st['body'])],
        [Paragraph('Printed Name: _________________________________', st['body']),
         Paragraph('Printed Name: _________________________________', st['body'])],
        [Paragraph('Title: _________________________________________', st['body']),
         Paragraph('Title: _________________________________________', st['body'])],
        [Paragraph('Date: __________________________________________', st['body']),
         Paragraph('Date: __________________________________________', st['body'])],
    ]
    sig_tbl = Table(sig_data, colWidths=[(W-inch)/2, (W-inch)/2])
    sig_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
        ('TOPPADDING',   (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('LINEABOVE',    (0,0),(-1,0),  1, TBLBRD),
        ('LINEBELOW',    (0,-1),(-1,-1),1, TBLBRD),
    ]))
    elems.append(KeepTogether([
        Paragraph('CONTRACT EXECUTION', ParagraphStyle('cex', fontName='Helvetica-Bold',
            fontSize=10, alignment=TA_CENTER, spaceBefore=10, spaceAfter=8)),
        sig_tbl
    ]))
    return elems


def build(data, out_path):
    st = S()
    doc = SimpleDocTemplate(out_path, pagesize=letter,
                             title=data.get('project_name','Proposal'),
                             author='HD Hauling & Grading',
                             creator='HD Hauling & Grading',
                             subject=data.get('project_name','Proposal'),
                             leftMargin=0.5*inch, rightMargin=0.5*inch,
                             topMargin=0.6*inch, bottomMargin=0.6*inch)
    story = []
    story += cover_page(data, st)
    story.append(PageBreak())
    story += bid_items_page(data, st)
    story += site_plan_page(data, st)
    story += approval_page(data, st)
    story.append(PageBreak())
    story += tc_pages(st)
    doc.build(story)
