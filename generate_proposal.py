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
        'tc_section':  ParagraphStyle('ts',  fontName='Helvetica-Bold', fontSize=10,  textColor=colors.HexColor('#CC0000')),
        'tc_body':     ParagraphStyle('tb',  fontName='Helvetica',      fontSize=8,   textColor=DGRAY, leading=14, spaceBefore=1, spaceAfter=5),
        'tc_bullet':   ParagraphStyle('tbul',fontName='Helvetica',      fontSize=8,   textColor=DGRAY, leading=14, leftIndent=16, bulletIndent=2, spaceBefore=1, spaceAfter=4),
    }

class HDCanvas(pdfcanvas.Canvas):
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
        right_y = H - 0.70*inch
        if self._doc_number:
            self.setFont('Helvetica-Bold', 9)
            self.setFillColor(RED)
            self.drawRightString(W - RM, right_y, self._doc_number)
            right_y -= 0.14*inch
            self.setFont('Helvetica', 9)
            self.setFillColor(DGRAY)
        self.drawRightString(W - RM, right_y, self._date)
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


def canvas_maker(date_str, doc_number=''):
    class _C(HDCanvas):
        def __init__(self, *a, **kw):
            kw['date_str'] = date_str
            kw['doc_number'] = doc_number
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
        mid = aw / 2

        # Use cropped logo (hd_logo.png has 44% right-side white padding, shifts center)
        _cover_logo = os.path.join(_DIR, 'hd_logo_cropped.png')
        if not os.path.exists(_cover_logo):
            _cover_logo = LOGO
        if os.path.exists(_cover_logo):
            from reportlab.lib.utils import ImageReader
            _ir = ImageReader(_cover_logo)
            _iw, _ih = _ir.getSize()
            max_w = 4.0 * inch
            max_h = 2.0 * inch
            scale = min(max_w / _iw, max_h / _ih)
            lw = _iw * scale
            lh = _ih * scale
            c.drawImage(_cover_logo, mid - lw/2, ah * 0.50, width=lw, height=lh,
                        mask='auto')

        c.setFont('Helvetica-Bold', 26)
        c.setFillColor(BLACK)
        c.drawCentredString(mid, ah * 0.454, d.get('project_name', 'Proposal'))

        c.setStrokeColor(MGRAY)
        c.setLineWidth(0.75)
        c.line(mid - 2.6*inch, ah * 0.437, mid + 2.6*inch, ah * 0.437)

        # Subtitle with more spacing below divider
        c.setFont('Helvetica', 18)
        c.setFillColor(DGRAY)
        c.drawCentredString(mid, ah * 0.400, 'Proposal & Contract')

        doc_num = d.get('document_number', '')
        if doc_num:
            c.setFont('Helvetica-Bold', 12)
            c.setFillColor(RED)
            c.drawCentredString(mid, ah * 0.370, doc_num)

        date_str = d.get('date', '')
        if date_str:
            c.setFont('Helvetica', 13)
            c.setFillColor(colors.HexColor('#999999'))
            c.drawCentredString(mid, ah * (0.342 if doc_num else 0.370), date_str)

        fy = 0.55 * inch
        lx = aw * 0.18
        rx = aw * 0.62
        line_h = 0.17 * inch  # line spacing

        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(BLACK)
        c.drawString(lx, fy + 0.75*inch, 'Prepared by:')
        y = fy + 0.53*inch
        c.setFont('Helvetica', 10)
        c.setFillColor(DGRAY)
        c.drawString(lx, y, d.get('sender_name', '')); y -= line_h
        c.setFont('Helvetica', 9)
        if d.get('company'):
            c.drawString(lx, y, d.get('company', 'HD Hauling & Grading'))

        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(BLACK)
        c.drawString(rx, fy + 0.75*inch, 'Prepared for:')
        y = fy + 0.53*inch
        c.setFont('Helvetica', 10)
        c.setFillColor(DGRAY)
        c.drawString(rx, y, d.get('client_name', '')); y -= line_h
        c.setFont('Helvetica', 9)
        if d.get('client_company'):
            c.drawString(rx, y, d['client_company'])

def info_block(data, st):
    """Option C — single horizontal band, no boxes, subtle top/bottom lines,
    vertical rules separating the three columns."""

    FW = W - inch  # full usable width

    title_s  = ParagraphStyle('c_t',   fontName='Helvetica-Bold', fontSize=11,
                               textColor=BLACK, leading=14, alignment=TA_LEFT)
    addr_s   = ParagraphStyle('c_a',   fontName='Helvetica',      fontSize=8,
                               textColor=DGRAY, leading=11, alignment=TA_LEFT)
    date_s   = ParagraphStyle('c_d',   fontName='Helvetica-Bold', fontSize=8,
                               textColor=RED,   leading=11, alignment=TA_LEFT)
    sec_s    = ParagraphStyle('c_sec', fontName='Helvetica-Bold', fontSize=7,
                               textColor=RED,   leading=9,  spaceAfter=2)
    name_s   = ParagraphStyle('c_n',   fontName='Helvetica',      fontSize=9,
                               textColor=BLACK, leading=12)
    detail_s = ParagraphStyle('c_det', fontName='Helvetica',      fontSize=8,
                               textColor=DGRAY, leading=11)

    proj_cell = [
        Spacer(1, 4),
        Paragraph(data.get('project_name', ''), title_s),
        Spacer(1, 4),
        Paragraph(', '.join(filter(None, [data.get('address',''), data.get('city_state','')])), addr_s),
        Spacer(1, 4),
        Paragraph(data.get('date', ''), date_s),
        Spacer(1, 4),
    ]

    by_cell = [
        Paragraph('PREPARED BY', sec_s),
        Paragraph(data.get('sender_name',  ''), name_s),
    ]
    if data.get('company'):
        by_cell.append(Paragraph(data['company'], detail_s))
    if data.get('sender_email'):
        by_cell.append(Paragraph(data['sender_email'], detail_s))
    if data.get('sender_phone'):
        by_cell.append(Paragraph(data['sender_phone'], detail_s))

    for_parts = [
        Paragraph('PREPARED FOR', sec_s),
        Paragraph(data.get('client_name',  ''), name_s),
    ]
    if data.get('client_company'):
        for_parts.append(Paragraph(data['client_company'], detail_s))
    if data.get('client_email'):
        for_parts.append(Paragraph(data['client_email'], detail_s))
    if data.get('client_phone'):
        for_parts.append(Paragraph(data['client_phone'], detail_s))
    for_cell = for_parts

    cw_proj = FW * 0.42
    cw_by   = FW * 0.27
    cw_for  = FW * 0.31

    wrapper = Table([[proj_cell, by_cell, for_cell]],
                    colWidths=[cw_proj, cw_by, cw_for],
                    hAlign='LEFT')
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
        ('VALIGN',        (0,0),(0,-1),  'MIDDLE'),
        ('VALIGN',        (1,0),(-1,-1), 'TOP'),
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
    div_st = ParagraphStyle('div', fontName='Helvetica-Bold', fontSize=8.5,
                            textColor=colors.HexColor('#333333'))

    ban_l = ParagraphStyle('banl', fontName='Helvetica-Bold', fontSize=11, textColor=WHITE, alignment=TA_CENTER)
    rows = [
        [Paragraph('BID ITEMS', ban_l), '', '', '', ''],
        [Paragraph('ITEM &amp; DESCRIPTION', ch_l), Paragraph('QTY',ch_r),
         Paragraph('UNIT',ch_r), Paragraph('PRICE',ch_r), Paragraph('SUBTOTAL',ch_r)],
    ]
    div_rows = set()  # track which rows are division headers

    # Group items by division, preserving order of first appearance
    current_div = None
    for item in items:
        div = item.get('division', '')
        if div and div != current_div:
            current_div = div
            div_rows.add(len(rows))
            rows.append([
                Paragraph(f'<b>{div.upper()}</b>', div_st), '', '', '', ''
            ])
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

    # Row heights — banner auto-sizes (matches Project Notes header), col header fixed
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
        ('TOPPADDING',(0,2),(-1,-1),6), ('BOTTOMPADDING',(0,2),(-1,-1),6),
        ('LEFTPADDING',(0,2),(0,-1),10), ('RIGHTPADDING',(-1,2),(-1,-1),10),
        ('LINEBELOW',(0,2),(-1,-1),0.3,TBLBORD),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('ALIGN',(1,0),(-1,-1),'RIGHT'),
        ('BOX',(0,0),(-1,-1),0.5,TBLBORD),
    ]
    # Division header rows: span all columns, light background, top border
    for r in div_rows:
        ts.append(('SPAN', (0,r), (-1,r)))
        ts.append(('BACKGROUND', (0,r), (-1,r), colors.HexColor('#E8E8E8')))
        ts.append(('TOPPADDING', (0,r), (-1,r), 5))
        ts.append(('BOTTOMPADDING', (0,r), (-1,r), 4))
        ts.append(('LINEABOVE', (0,r), (-1,r), 0.5, MGRAY))
    # Alternating row colors (skip division headers)
    alt = False
    for i in range(2, len(rows)):
        if i in div_rows:
            alt = False
            continue
        if alt:
            ts.append(('BACKGROUND',(0,i),(-1,i),ROWALT))
        alt = not alt
    t.setStyle(TableStyle(ts))
    return t

def total_line(total):
    """Contract total row — both cells use same fontSize/leading so VALIGN MIDDLE
    positions them identically."""
    cw  = W - inch
    # Use the same font size for both cells — label slightly smaller via bold weight
    lbl = ParagraphStyle('tl', fontName='Helvetica-Bold', fontSize=12,
                          textColor=BLACK, leading=12, spaceAfter=0, spaceBefore=0)
    val = ParagraphStyle('tv', fontName='Helvetica-Bold', fontSize=12,
                          textColor=BLACK, leading=12, spaceAfter=0, spaceBefore=0,
                          alignment=TA_RIGHT)
    t = Table([[Paragraph('CONTRACT TOTAL', lbl),
                Paragraph(f'${total:,.2f}', val)]],
              colWidths=[cw * 0.60, cw * 0.40],
              rowHeights=[0.48 * inch])
    t.setStyle(TableStyle([
        ('ALIGN',         (1,0),(1,-1),  'RIGHT'),
        ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
        ('BACKGROUND',    (0,0),(-1,-1), LGRAY),
        ('LINEABOVE',     (0,0),(-1,0),  1,   TBLBORD),
        ('LINEBELOW',     (0,-1),(-1,-1),2,   RED),
        ('TOPPADDING',    (0,0),(-1,-1), 0),
        ('BOTTOMPADDING', (0,0),(-1,-1), 0),
        ('LEFTPADDING',   (0,0),(-1,-1), 10),
        ('RIGHTPADDING',  (0,0),(-1,-1), 10),
    ]))
    return t

class SitePlanPage(Flowable):
    """Renders the uploaded site plan image at top of page with Exhibit A heading.
    Accepts base64 data URL, remote image URL, or remote PDF URL."""
    def __init__(self, image_data=None, site_plan_url=None):
        super().__init__()
        self._image_data = image_data
        self._site_plan_url = site_plan_url
        self._tmp_path = None

    def _resolve_image(self):
        """Returns a local file path to the site plan image, or None."""
        import base64, tempfile
        # 1. Base64 data URL (from proposal builder file upload)
        if self._image_data and ',' in self._image_data:
            try:
                img_bytes = base64.b64decode(self._image_data.split(',')[1])
                ext = self._image_data.split(';')[0].split('/')[1] if ';' in self._image_data else 'png'
                if ext == 'pdf':
                    return self._pdf_to_image(img_bytes)
                with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
                    tmp.write(img_bytes)
                    return tmp.name
            except Exception:
                pass
        # 2. Remote URL (from Supabase Storage)
        if self._site_plan_url:
            try:
                import requests as _http
                r = _http.get(self._site_plan_url, timeout=15, allow_redirects=True)
                if r.status_code == 200:
                    ct = r.headers.get('content-type', '')
                    if 'pdf' in ct or self._site_plan_url.lower().endswith('.pdf'):
                        return self._pdf_to_image(r.content)
                    ext = 'png'
                    if 'jpeg' in ct or 'jpg' in ct:
                        ext = 'jpg'
                    elif 'webp' in ct:
                        ext = 'webp'
                    with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
                        tmp.write(r.content)
                        return tmp.name
            except Exception:
                pass
        return None

    def _pdf_to_image(self, pdf_bytes):
        """Convert first page of a PDF to a PNG image file. Returns file path or None."""
        import tempfile
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=200)
            if images:
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    images[0].save(tmp.name, 'PNG')
                    return tmp.name
        except ImportError:
            # pdf2image not available — try PyMuPDF as fallback
            try:
                import fitz
                doc = fitz.open(stream=pdf_bytes, filetype='pdf')
                page = doc[0]
                pix = page.get_pixmap(dpi=200)
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    pix.save(tmp.name)
                    return tmp.name
            except ImportError:
                pass
        except Exception:
            pass
        return None

    def wrap(self, aw, ah):
        self._aw, self._ah = aw, ah
        return aw, ah
    def draw(self):
        c = self.canv
        heading_h = 0.5*inch
        # Draw heading at top
        c.setFont('Helvetica-Bold', 16)
        c.setFillColor(RED)
        c.drawCentredString(self._aw/2, self._ah - 0.25*inch, 'Exhibit A — Site Plan')
        c.setStrokeColor(RED)
        c.setLineWidth(1)
        c.line(0, self._ah - heading_h, self._aw, self._ah - heading_h)
        img_top = self._ah - heading_h - 0.15*inch

        img_path = self._resolve_image()
        if img_path:
            try:
                from reportlab.lib.utils import ImageReader
                ir = ImageReader(img_path)
                iw, ih = ir.getSize()
                max_w = self._aw
                max_h = img_top
                scale = min(max_w / iw, max_h / ih)
                dw = iw * scale
                dh = ih * scale
                x = (self._aw - dw) / 2
                y = img_top - dh
                c.drawImage(img_path, x, y, width=dw, height=dh,
                            preserveAspectRatio=True, mask='auto')
                os.unlink(img_path)
                return
            except Exception:
                if img_path and os.path.exists(img_path):
                    os.unlink(img_path)

        # Fallback placeholder
        c.setStrokeColor(MGRAY)
        c.setLineWidth(1)
        c.setDash(6,4)
        ph = img_top * 0.6
        px = 0
        py = img_top - ph
        c.rect(px, py, self._aw, ph, stroke=1, fill=0)
        c.setDash()
        cx, cy = self._aw/2, py + ph/2
        c.setFont('Helvetica-Bold', 14)
        c.setFillColor(MGRAY)
        c.drawCentredString(cx, cy + 0.2*inch, 'Site Plan / Drawing')
        c.setFont('Helvetica', 10)
        c.drawCentredString(cx, cy - 0.1*inch, 'Upload a site plan image in the proposal builder')
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

    # ── Section header ────────────────────────────────────────────────────────
    elems.append(red_hdr('Client Approval & Authorization', st, cw))
    elems.append(Spacer(1, 0.14*inch))

    # ── Project summary box ───────────────────────────────────────────────────
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

    # ── Approved contract value (print-friendly — matches contract total style) ─
    amt_lbl = ParagraphStyle('al2', fontName='Helvetica-Bold', fontSize=11,
                              textColor=BLACK, leading=11, spaceAfter=0, spaceBefore=0)
    amt_val = ParagraphStyle('av2', fontName='Helvetica-Bold', fontSize=11,
                              textColor=BLACK, leading=11, spaceAfter=0, spaceBefore=0,
                              alignment=TA_RIGHT)
    amt_t = Table([[Paragraph('APPROVED CONTRACT VALUE', amt_lbl),
                    Paragraph(f'${total:,.2f}', amt_val)]],
                  colWidths=[cw*0.60, cw*0.40],
                  rowHeights=[0.44 * inch])
    amt_t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), LGRAY),
        ('LINEABOVE',    (0,0),(-1,0),  1,   TBLBORD),
        ('LINEBELOW',    (0,0),(-1,-1), 2,   RED),
        ('TOPPADDING',   (0,0),(-1,-1), 0),
        ('BOTTOMPADDING',(0,0),(-1,-1), 0),
        ('LEFTPADDING',  (0,0),(-1,-1), 10),
        ('RIGHTPADDING', (0,0),(-1,-1), 10),
        ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
        ('ALIGN',        (1,0),(1,-1),  'RIGHT'),
    ]))
    elems.append(amt_t)
    elems.append(Spacer(1, 0.18*inch))

    # ── Authorization language ────────────────────────────────────────────────
    auth_st = ParagraphStyle('auth', fontName='Helvetica-Oblique', fontSize=8,
                              textColor=DGRAY, leading=13, alignment=TA_CENTER)
    elems.append(Paragraph(
        'By signing below, Client authorizes HD Hauling &amp; Grading to proceed with the work '
        'described in this Proposal &amp; Contract and agrees to be bound by all terms and '
        'conditions set forth herein.',
        auth_st))
    elems.append(Spacer(1, 0.14*inch))

    # ── Bilateral signature block ─────────────────────────────────────────────
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

    return elems

def unit_prices_block(data):
    """Renders the Additional Unit Prices table as a list of flowables."""
    unit_items = data.get('unit_prices', [])
    if not unit_items:
        return []
    cw = W - inch
    elems = []
    ch_l = ParagraphStyle('ucl', fontName='Helvetica-Bold', fontSize=8,
                           textColor=WHITE)
    ch_r = ParagraphStyle('ucr', fontName='Helvetica-Bold', fontSize=8,
                           textColor=WHITE, alignment=TA_RIGHT)
    up_rows = [
        [Paragraph('Additional Unit Prices', ParagraphStyle(
            'ub', fontName='Helvetica-Bold', fontSize=10,
            textColor=WHITE, alignment=TA_CENTER)), ''],
        [Paragraph('Description', ch_l), Paragraph('Unit Rate', ch_r)],
    ]
    for item in unit_items:
        up_rows.append([
            Paragraph(item['name'], ParagraphStyle(
                'un', fontName='Helvetica', fontSize=8, textColor=BLACK)),
            Paragraph(f'${item["rate"]:,.2f}', ParagraphStyle(
                'uv', fontName='Helvetica-Bold', fontSize=8,
                textColor=BLACK, alignment=TA_RIGHT)),
        ])

    up_t = Table(up_rows,
                 colWidths=[cw*0.78, cw*0.22],
                 rowHeights=[None, 0.24*inch] + [None]*(len(up_rows)-2))
    up_ts = [
        ('SPAN',         (0,0),(-1,0)),
        ('BACKGROUND',   (0,0),(-1,0),  RED),
        ('ALIGN',        (0,0),(-1,0),  'CENTER'),
        ('TOPPADDING',   (0,0),(-1,0),  5),
        ('BOTTOMPADDING',(0,0),(-1,0),  5),
        ('BACKGROUND',   (0,1),(-1,1),  colors.HexColor('#4A4A4A')),
        ('TOPPADDING',   (0,1),(-1,1),  5),
        ('BOTTOMPADDING',(0,1),(-1,1),  5),
        ('TOPPADDING',   (0,2),(-1,-1), 4),
        ('BOTTOMPADDING',(0,2),(-1,-1), 4),
        ('LINEBELOW',    (0,2),(-1,-2), 0.3, TBLBORD),
        ('LINEBELOW',    (0,-1),(-1,-1),1.5, RED),
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
    elems.append(Spacer(1, 0.12*inch))
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
        if item.startswith('•'):
            items.append(Paragraph('- ' + item[1:].lstrip(), st['tc_bullet']))
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
            'This Proposal & Contract becomes legally binding upon execution by both the Customer/Purchaser and HD Hauling & Grading. Any conditions not expressly set forth herein shall not be recognized unless documented in writing and signed by authorized representatives of both parties. Verbal agreements, purchase orders, or prior understandings do not modify or supersede this contract unless incorporated by a written amendment.',
        ]),
        ('2. Proposal Validity', [
            'Pricing in this proposal is valid for thirty (30) calendar days from the date of issuance. HD Hauling & Grading reserves the right to withdraw or modify this proposal if not executed within that period, including adjustments for material price fluctuations.',
        ]),
        ('3. Scope of Work', [
            'HD Hauling & Grading\'s scope is limited to the site construction work explicitly described in the Bid Items section of this document, which may include but is not limited to: grading and earthwork, utility installation (storm drain, sanitary sewer, water), erosion control and stormwater management, land clearing and tree removal, paving, asphalt, concrete, pavement markings, signage, and landscaping. No additional work, modifications, or extensions of scope are included unless captured in a written, signed Change Order prior to commencement.',
        ]),
        ('4. Change Orders', [
            'Any modification to the approved scope of work\u200a\u2014\u200aincluding additions, deletions, substitutions, or design changes\u200a\u2014\u200arequires a written Change Order executed by both parties before work begins. HD Hauling & Grading shall not be obligated to perform out-of-scope work without an approved Change Order and is not liable for delays caused by scope changes requested after execution.',
        ]),
        ('5. Site Access & Staging', [
            'The Customer shall provide HD Hauling & Grading with unobstructed vehicular access to the project site, a designated staging area for equipment and materials, and a safe haul route for loaded delivery trucks for the duration of the work.',
            '• Delays, re-mobilizations, or standby time caused by restricted access, site conflicts with other trades, or unavailability of the work area will be billed at the applicable rates in the Additional Unit Prices schedule.',
            '• Customer is responsible for ensuring underground utilities are located and marked (NC811) prior to the start of work. HD Hauling & Grading is not liable for damage to unmarked, improperly marked, or abandoned utilities.',
        ]),
        ('6. Unforeseen Site Conditions', [
            'This proposal is based on the site conditions shown on the approved construction drawings and geotechnical report (if provided). HD Hauling & Grading is not responsible for conditions that are not discoverable through reasonable observation of the site or review of available project documents.',
            '• Unforeseen conditions include but are not limited to: unsuitable soils, rock, underground obstructions, contaminated materials, undocumented utilities, perched or seasonal groundwater, springs, and any subsurface condition materially different from what is represented in the project documents.',
            '• If unforeseen conditions are encountered, HD Hauling & Grading will notify the Customer in writing. Additional work required to address such conditions will be performed under a Change Order or at the applicable Additional Unit Prices listed herein.',
            '• Customer is responsible for all environmental testing, hazardous material identification, and disposal of contaminated materials unless explicitly included in HD Hauling & Grading\'s scope of work.',
        ]),
        ('7. Grading & Earthwork', [
            'Grading, filling, and earthwork operations are based on the plan quantities and cross-sections shown in the approved construction drawings. Actual field quantities may vary from the plan quantities provided.',
            '• Subgrade preparation, proof rolling, and compaction testing are the Customer\'s responsibility unless explicitly included in the Bid Items. Commencement of subsequent work (base, paving, building pads) constitutes the Customer\'s acceptance of subgrade conditions.',
            '• HD Hauling & Grading is not responsible for settlement, erosion, slope failure, or drainage issues caused by: geotechnical conditions not identified in the project documents, work by others on or adjacent to completed grades, failure to maintain erosion control devices after demobilization, or acts of God.',
            '• Import or export of fill material beyond the quantities shown on the approved plans will be addressed via Change Order. Unsuitable material encountered during excavation will be handled per the Additional Unit Prices.',
            '• Finish grading tolerances are per NCDOT standards unless otherwise specified in the contract documents.',
        ]),
        ('8. Utility Installation (Storm Drain, Sanitary Sewer, Water)', [
            'All utility installation work shall be performed in accordance with the approved construction drawings, applicable NCDOT specifications, and local governing authority requirements. Pipe materials, bedding, and backfill shall conform to the project specifications.',
            '• HD Hauling & Grading\'s scope includes installation of pipe, structures, and fittings as shown on the approved plans. Taps, connections to existing mains, and meter installation by the utility provider are the Customer\'s responsibility unless explicitly included in the scope.',
            '• Dewatering required due to groundwater, perched water, or stormwater intrusion during excavation will be billed at the applicable Additional Unit Prices if not included in the Bid Items.',
            '• Rock excavation for utility trenches discovered during construction will be billed per the Additional Unit Prices.',
            '• HD Hauling & Grading is not responsible for: damage to unmarked or incorrectly located existing utilities, settlement of trench backfill caused by improper compaction by others or premature loading, or utility service interruptions required by the work.',
            '• All required testing (pressure, vacuum, mandrel, televising) will be coordinated by HD Hauling & Grading if included in the Bid Items. Re-testing required due to conditions outside HD Hauling & Grading\'s control will be billed as additional work.',
        ]),
        ('9. Erosion Control & Stormwater Management', [
            'Erosion and sediment control measures will be installed per the approved Erosion & Sediment Control Plan and all applicable NCDEQ and local regulations.',
            '• Initial installation of erosion control devices is included when listed in the Bid Items. Ongoing maintenance (silt fence repair, inlet protection cleaning, sediment basin dewatering) is the Customer\'s responsibility after HD Hauling & Grading\'s demobilization unless a maintenance agreement is included.',
            '• HD Hauling & Grading is not responsible for fines, penalties, or Notices of Violation (NOVs) issued by regulatory agencies for: erosion control failures caused by storm events exceeding design capacity, work by other trades that damages installed devices, or the Customer\'s failure to maintain devices after demobilization.',
            '• Additional erosion control measures required due to plan revisions, regulatory changes, or unforeseen site conditions will be addressed via Change Order.',
        ]),
        ('10. Land Clearing & Tree Removal', [
            'Land clearing, grubbing, and tree removal are limited to the areas shown on the approved clearing and grading plans. All cleared materials will be disposed of in accordance with applicable regulations.',
            '• The Customer is responsible for obtaining any required tree removal permits, environmental clearances, and wetland delineations prior to the start of clearing operations.',
            '• HD Hauling & Grading is not responsible for: damage to trees, vegetation, or improvements outside the designated clearing limits, environmental violations resulting from inaccurate or incomplete clearing plans, or disposal of hazardous materials (creosote timbers, asbestos, etc.) unless specifically addressed.',
            '• Stump removal depth is per plan specification or twelve (12) inches below finished grade, whichever is greater, unless otherwise specified in the contract documents.',
        ]),
        ('11. Rock Excavation & Blasting', [
            'If rock is encountered during excavation that cannot be removed by standard excavation equipment (defined as material that cannot be excavated with a CAT 330 or equivalent hydraulic excavator with a standard bucket), it shall be classified as rock and billed per the Additional Unit Prices.',
            '• If blasting is required, HD Hauling & Grading will engage a licensed, insured blasting subcontractor. All blasting operations will comply with NCOSFM regulations, NFPA 495, and all applicable local ordinances.',
            '• The Customer is responsible for: pre-blast survey coordination and notification to adjacent property owners, obtaining any required blasting permits, and providing access for the blasting contractor.',
            '• HD Hauling & Grading is not liable for: vibration damage claims from adjacent properties when blasting is performed within regulatory limits, project delays caused by blasting permitting requirements, or cost increases resulting from rock quantities exceeding plan estimates.',
        ]),
        ('12. Subgrade Acceptance & Pavement Performance', [
            'HD Hauling & Grading is not responsible for pavement failure, cracking, settlement, or premature deterioration resulting from inadequate subgrade preparation, insufficient base compaction, poor drainage, or unsuitable sub-base materials outside HD Hauling & Grading\'s scope.',
            '• Prior to paving, the Customer or their designated representative is responsible for ensuring the subgrade and base course have been properly graded, compacted to NCDOT specifications, proof-rolled where required, and inspected. Commencement of paving constitutes the Customer\'s acceptance of subgrade conditions.',
            '• Proof rolling, moisture content testing, and base course density testing are the responsibility of the Customer unless explicitly included in the scope.',
            '• If HD Hauling & Grading identifies conditions that may affect pavement performance, written notification will be provided. The Customer\'s direction to proceed releases HD Hauling & Grading from performance liability related to those identified conditions.',
        ]),
        ('13. Materials & Specifications', [
            'All materials furnished by HD Hauling & Grading shall conform to the applicable NCDOT Standard Specifications for Roads and Structures (current edition), or the project specifications, whichever is more stringent, unless otherwise specified.',
            '• Material substitutions required due to plant availability or supply chain disruptions will be communicated promptly. Functionally equivalent materials will be substituted at no additional cost to the Customer.',
            '• HD Hauling & Grading does not guarantee long-term availability of specific mix designs, pipe sizes, or material sources.',
        ]),
        ('14. Weather & Temperature Conditions', [
            'Asphalt paving will not be performed when ambient or surface temperatures are below 40\u00b0F and falling, during precipitation, when the base contains standing water or frost, or when forecast conditions within four (4) hours are anticipated to compromise compaction or curing.',
            '• Concrete will not be placed when ambient temperatures are below 40\u00b0F without approved cold-weather protection measures, or above 90\u00b0F without hot-weather precautions per ACI standards.',
            '• Earthwork, grading, and utility operations may be suspended during or after significant rain events when soil conditions do not permit safe or specification-compliant operations.',
            '• Schedule adjustments caused by weather are not grounds for price renegotiation, penalties, or liquidated damages.',
        ]),
        ('15. Concrete Work Conditions', [
            'All concrete work shall be performed in accordance with applicable ACI standards and NCDOT specifications for the work described.',
            '• Form layout, grade stakes, and joint locations must be approved by the Customer or their representative prior to placement. Once concrete is placed, corrections to layout or elevation are billable as additional work.',
            '• Cure time and form removal timing will be determined by HD Hauling & Grading based on ambient conditions and mix design requirements. Customer requests to accelerate form removal or trafficking of concrete prior to adequate cure are at the Customer\'s sole risk.',
            '• HD Hauling & Grading is not responsible for surface defects, cracking, or scaling resulting from: improper curing practices by others, premature trafficking, freeze-thaw cycles, de-icing chemical application, or subgrade settlement outside HD Hauling & Grading\'s scope of work.',
        ]),
        ('16. Compaction & Quality', [
            'All compaction operations (earthwork, trench backfill, base course, asphalt) shall meet NCDOT density requirements for the specified material. If compaction testing is required, the Customer is responsible for providing an independent testing agency.',
            '• HD Hauling & Grading is not liable for compaction failures resulting from: unsuitable material not identified in the geotechnical report, moisture conditions outside specification limits, subgrade instability, or Customer-caused delays.',
        ]),
        ('17. Warranty', [
            'HD Hauling & Grading warrants all materials and workmanship for one (1) year from the date of substantial completion. This warranty covers defects in materials and workmanship performed directly by HD Hauling & Grading.',
            'This warranty expressly excludes:',
            '• Damage from petroleum products, chemical spills, or de-icing agents applied to the surface',
            '• Pavement or subgrade failure from conditions not prepared by HD Hauling & Grading',
            '• Damage from vehicle loads or construction traffic exceeding the pavement design capacity',
            '• Deterioration adjacent to a repaired area on maintenance and repair projects',
            '• Settlement of utility trenches, fills, or backfill areas caused by conditions outside the scope',
            '• Erosion, slope failure, or drainage issues caused by lack of maintenance or work by others',
            '• Normal wear and tear, surface oxidation, and expected pavement aging',
            '• Damage from third parties, acts of God, or events beyond HD Hauling & Grading\'s control',
            'For maintenance and repair projects, the warranty applies only to the specific area(s) of new work performed.',
        ]),
        ('18. Traffic Control & Permits', [
            'If included in the Bid Items, HD Hauling & Grading will provide traffic control in general conformance with the MUTCD for the duration of active operations on the project.',
            '• The Customer is responsible for all permits, right-of-way authorizations, NCDOT encroachment agreements, and lane closure approvals prior to the scheduled start of work.',
            '• ADA compliance determinations for pavement markings, curb ramps, and accessible routes are the responsibility of the Owner and the Engineer of Record.',
        ]),
        ('19. Pavement Markings & Signage', [
            'Pavement markings will be installed per the approved plan or layout provided by the Customer. HD Hauling & Grading is not responsible for incorrect layouts resulting from inaccurate field dimensions or conflicting plan documents.',
            '• Thermoplastic markings require a minimum asphalt cure period before application can begin.',
            '• Signage installation will follow locations and specifications provided in the approved plans. Sign content, ADA designation, and regulatory compliance are the Customer\'s responsibility.',
        ]),
        ('20. Limitation of Liability', [
            'HD Hauling & Grading\'s total liability under this contract, regardless of cause, shall not exceed the total contract value. In no event shall HD Hauling & Grading be liable for consequential, incidental, indirect, or punitive damages, including but not limited to loss of use, lost revenue, business interruption, or third-party claims.',
        ]),
        ('21. Payment Terms', [
            'All invoices are due Net 30 (thirty calendar days from the invoice date). Invoices will be submitted upon completion of each defined phase of work or on a monthly basis, whichever occurs first.',
            '• Balances not received within thirty (30) days of the invoice date accrue interest at 1.5% per month (18% annually).',
            '• Final payment is due within thirty (30) calendar days of the final completion invoice. Where applicable and agreed in writing, retention may be withheld per the terms of the prime contract but shall be released no later than thirty (30) days after final completion and acceptance of the work.',
            '• The individual executing this contract on behalf of the Customer/Purchaser provides a personal guarantee for full payment of all outstanding principal and accrued interest.',
        ]),
        ('22. Lien Rights', [
            'HD Hauling & Grading expressly reserves its right to file a Claim of Lien pursuant to N.C.G.S. Chapter 44A in the event of non-payment. Nothing herein constitutes a waiver of lien rights. In the event legal action is required, the Customer shall be responsible for all reasonable attorney\'s fees and collection costs per N.C.G.S. \u00a7\u00a044A-35.',
        ]),
        ('23. Material Pricing & Availability', [
            'Due to volatility in liquid asphalt, aggregate, pipe, fuel, and commodity markets, material costs may be adjusted to reflect prevailing market rates if costs increase more than ten percent (10%) from the proposal date. Written notice will be provided prior to any price adjustment.',
            '• HD Hauling & Grading is not liable for delays caused by plant shutdowns, material shortages, or supplier availability issues.',
        ]),
        ('24. Force Majeure', [
            'HD Hauling & Grading shall not be liable for delays or failure to perform caused by circumstances beyond its reasonable control, including acts of God, severe weather, labor disputes, government actions, supply chain disruptions, fuel shortages, or public health emergencies. The schedule will be extended by a reasonable period and pricing may be subject to renegotiation.',
        ]),
        ('25. Entire Agreement', [
            'This Proposal & Contract constitutes the entire agreement between the parties with respect to the work described herein. It supersedes all prior proposals, representations, and understandings. No terms printed on the Customer\'s purchase orders shall apply unless explicitly incorporated by a written amendment signed by both parties.',
        ]),
        ('26. Dispute Resolution', [
            'The parties agree to attempt to resolve any dispute arising under this Proposal & Contract through good-faith negotiation prior to initiating formal proceedings. If a dispute cannot be resolved through negotiation within thirty (30) days of written notice, either party may pursue resolution through binding arbitration under the rules of the American Arbitration Association, or by filing a claim in a court of competent jurisdiction in the State of North Carolina.',
            '\u2022 This Proposal & Contract shall be governed by and construed in accordance with the laws of the State of North Carolina, without regard to conflict of law provisions.',
            '\u2022 The prevailing party in any arbitration or litigation arising from this Proposal & Contract shall be entitled to recover all reasonable attorney\u2019s fees and costs from the non-prevailing party.',
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

    if data.get('site_plan_image') or data.get('site_plan_url'):
        story.append(SitePlanPage(data.get('site_plan_image'), data.get('site_plan_url')))
        story.append(PageBreak())

    story += tc_pages(st)
    story += unit_prices_block(data)
    story.append(PageBreak())

    story += approval_page(data, st)

    doc.build(story, canvasmaker=canvas_maker(data.get('date',''), data.get('document_number','')))
    print(f'OK: {out_path}')

if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    out  = sys.argv[2] if len(sys.argv) > 2 else '/mnt/user-data/outputs/HD_Proposal.pdf'
    build(data, out)
