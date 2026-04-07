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
TM = 1.0 * inch
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
        'tc_body':     ParagraphStyle('tb',  fontName='Helvetica',      fontSize=7.5, textColor=DGRAY, leading=11, spaceBefore=1, spaceAfter=3),
        'tc_bullet':   ParagraphStyle('tbul',fontName='Helvetica',      fontSize=7.5, textColor=DGRAY, leading=11, leftIndent=16, bulletIndent=2, spaceBefore=1, spaceAfter=2),
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
            self.drawImage(LOGO, LM, H - 0.72*inch, width=1.05*inch, height=0.44*inch,
                           preserveAspectRatio=True, mask='auto')
        self.setFont('Helvetica-Bold', 16)
        self.setFillColor(BLACK)
        self.drawRightString(W - RM, H - 0.48*inch, 'PROPOSAL & CONTRACT')
        if self._doc_number:
            self.setFont('Helvetica-Bold', 9)
            self.setFillColor(RED)
            self.drawRightString(W - RM, H - 0.65*inch, self._doc_number)
        self.setStrokeColor(BLACK)
        self.setLineWidth(0.75)
        self.line(LM, H - 0.80*inch, W - RM, H - 0.80*inch)
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
        is_lump_sum = item.get('is_lump_sum', False)
        qty_s = f'{int(qty):,}' if isinstance(qty,(int,float)) and qty==int(qty) else str(qty)
        price_s = f'${sub:,.2f}' if is_lump_sum else f'${price:,.2f}'
        rows.append([
            Paragraph(f'<b>{name}</b><br/><font size="8" color="#777777">{desc}</font>', st['item_name']),
            Paragraph(qty_s, st['cell']),
            Paragraph(unit,  st['cell']),
            Paragraph(price_s, st['cell']),
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
        c.setFillColor(BLACK)
        c.drawCentredString(self._aw/2, self._ah - 0.25*inch, 'Exhibit A — Site Plan')
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
        'By signing below, Client agrees to all terms and conditions of this Proposal &amp; Contract.',
        auth_st))
    elems.append(Spacer(1, 0.14*inch))

    # ── Bilateral signature block ─────────────────────────────────────────────
    body_st   = ParagraphStyle('sb',  fontName='Helvetica',      fontSize=9,
                                textColor=BLACK, leading=14)
    body_b_st = ParagraphStyle('sbb', fontName='Helvetica-Bold', fontSize=9,
                                textColor=BLACK, leading=14)

    _line = '_' * 30
    sig_data = [
        [Paragraph('<b>HD Hauling &amp; Grading</b>', body_b_st),
         Paragraph('<b>Client / Authorized Representative</b>', body_b_st)],
        [Paragraph('Authorized Signature: ' + _line, body_st),
         Paragraph('Authorized Signature: ' + _line, body_st)],
        [Paragraph('Printed Name: ' + _line, body_st),
         Paragraph('Printed Name: ' + _line, body_st)],
        [Paragraph('Title: ' + _line, body_st),
         Paragraph('Title: ' + _line, body_st)],
        [Paragraph('Date: ' + _line, body_st),
         Paragraph('Date: ' + _line, body_st)],
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

    return [KeepTogether(elems)]

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
    items = [hdr, Spacer(1, 0.03*inch)]
    for item in body_items:
        if item.startswith('•'):
            items.append(Paragraph('- ' + item[1:].lstrip(), st['tc_bullet']))
        else:
            items.append(Paragraph(item, st['tc_body']))
    items.append(Spacer(1, 0.03*inch))
    return KeepTogether(items)

def tc_pages(st):
    cw = W - inch
    elems = []

    elems.append(Paragraph('Terms & Conditions',
        ParagraphStyle('tch', fontName='Helvetica-Bold', fontSize=14,
                       alignment=TA_CENTER, spaceAfter=10)))

    sections = [
        ('1. Contract Formation & Binding Agreement', [
            'This Proposal & Contract becomes legally binding upon execution by both the Customer and HD Hauling & Grading. Conditions not expressly set forth herein shall not be recognized unless documented in writing and signed by both parties. Verbal agreements or purchase orders do not modify this contract.',
        ]),
        ('2. Proposal Validity', [
            'Pricing is valid for thirty (30) calendar days from issuance. HD Hauling & Grading reserves the right to withdraw or modify this proposal if not executed within that period, including adjustments for material price fluctuations.',
        ]),
        ('3. Scope of Work & Change Orders', [
            'HD Hauling & Grading\'s scope is limited to work explicitly described in the Bid Items, which may include: grading, earthwork, utility installation, erosion control, land clearing, paving, concrete, pavement markings, signage, and landscaping. No additional work is included unless captured in a written, signed Change Order.',
            '• Any modification to the approved scope\u2014including additions, deletions, or design changes\u2014requires a written Change Order executed by both parties before work begins. HD Hauling & Grading is not obligated to perform out-of-scope work without an approved Change Order.',
        ]),
        ('4. Site Access & Unforeseen Conditions', [
            'Customer shall provide unobstructed vehicular access, a staging area, and safe haul routes for the duration of work. Delays caused by restricted access or site conflicts will be billed per the Additional Unit Prices.',
            '• Customer is responsible for ensuring underground utilities are located and marked (NC811) prior to start of work. HD Hauling & Grading is not liable for damage to unmarked or abandoned utilities.',
            '• This proposal is based on conditions shown in approved drawings and geotechnical reports. Unforeseen conditions (unsuitable soils, rock, underground obstructions, contaminated materials, undocumented utilities, groundwater) will be addressed via Change Order or the Additional Unit Prices.',
            '• Customer is responsible for all environmental testing and disposal of contaminated materials unless explicitly included in scope.',
        ]),
        ('5. Grading & Earthwork', [
            'Grading and earthwork are based on plan quantities; actual field quantities may vary. Subgrade preparation, proof rolling, and compaction testing are the Customer\'s responsibility unless included in Bid Items. Commencement of subsequent work constitutes acceptance of subgrade conditions.',
            '• HD Hauling & Grading is not responsible for settlement, erosion, or drainage issues caused by conditions not identified in project documents, work by others, or acts of God. Import/export of fill beyond plan quantities will be addressed via Change Order. Finish grading tolerances are per NCDOT standards.',
        ]),
        ('6. Utility Installation', [
            'Utility work shall conform to approved drawings, NCDOT specifications, and local requirements. Scope includes pipe, structures, and fittings as shown on plans. Taps, connections to mains, and meter installation are Customer\'s responsibility unless included in scope.',
            '• Dewatering and rock excavation for utility trenches will be billed per Additional Unit Prices if not in Bid Items. HD Hauling & Grading is not responsible for damage to unmarked utilities, trench settlement from improper compaction by others, or utility service interruptions.',
        ]),
        ('7. Erosion Control & Land Clearing', [
            'Erosion control will be installed per the approved plan and NCDEQ regulations. Initial installation is included when in Bid Items; ongoing maintenance is Customer\'s responsibility after demobilization unless a maintenance agreement is included.',
            '• HD Hauling & Grading is not responsible for NOVs caused by storms exceeding design capacity, damage by other trades, or Customer\'s failure to maintain devices. Additional measures due to plan revisions or unforeseen conditions will be addressed via Change Order.',
            '• Land clearing is limited to areas shown on approved plans. Customer is responsible for tree removal permits and environmental clearances. Stump removal depth is per plan spec or 12" below finished grade.',
        ]),
        ('8. Rock Excavation & Blasting', [
            'Rock that cannot be removed by standard excavation equipment (CAT 330 or equivalent) shall be classified as rock and billed per Additional Unit Prices. If blasting is required, a licensed subcontractor will be engaged per NCOSFM/NFPA 495 regulations.',
            '• Customer is responsible for pre-blast surveys, blasting permits, and property owner notification. HD Hauling & Grading is not liable for vibration claims when blasting is within regulatory limits.',
        ]),
        ('9. Subgrade, Pavement & Concrete', [
            'HD Hauling & Grading is not responsible for pavement failure resulting from inadequate subgrade preparation, poor drainage, or unsuitable materials outside our scope. Commencement of paving constitutes Customer\'s acceptance of subgrade conditions.',
            '• Concrete work per ACI/NCDOT standards. Form layout and joint locations must be approved prior to placement. HD Hauling & Grading is not responsible for defects from improper curing by others, premature trafficking, freeze-thaw cycles, or de-icing chemicals.',
        ]),
        ('10. Materials, Weather & Compaction', [
            'All materials shall conform to NCDOT Standard Specifications or project specifications. Equivalent material substitutions due to availability will be at no additional cost. Asphalt paving will not be performed below 40\u00b0F, during precipitation, or on wet/frozen base.',
            '• Earthwork and utility operations may be suspended during rain events. Schedule adjustments caused by weather are not grounds for price renegotiation or penalties.',
            '• All compaction shall meet NCDOT density requirements. Customer provides independent testing. HD Hauling & Grading is not liable for failures from unsuitable material or moisture conditions outside specification limits.',
        ]),
        ('11. Warranty', [
            'HD Hauling & Grading warrants materials and workmanship for one (1) year from substantial completion. This warranty excludes: damage from petroleum products, chemicals, or de-icing agents; pavement failure from conditions not prepared by HD Hauling & Grading; overloaded traffic; utility trench settlement from conditions outside scope; erosion from lack of maintenance; normal wear and tear; damage from third parties or acts of God.',
            '• For maintenance/repair projects, the warranty applies only to the specific area(s) of new work performed.',
        ]),
        ('12. Traffic Control, Markings & Signage', [
            'If included in Bid Items, traffic control will conform to MUTCD standards. Customer is responsible for all permits, ROW authorizations, NCDOT encroachment agreements, and lane closure approvals. ADA compliance is the responsibility of the Owner and Engineer of Record.',
            '• Pavement markings per approved plan; thermoplastic requires minimum asphalt cure time. Signage per approved plans; sign content and regulatory compliance are Customer\'s responsibility.',
        ]),
        ('13. Limitation of Liability & Payment Terms', [
            'HD Hauling & Grading\'s total liability shall not exceed the total contract value. HD Hauling & Grading shall not be liable for consequential, incidental, indirect, or punitive damages including loss of use, lost revenue, or business interruption.',
            '• Invoices are due Net 30. Balances past 30 days accrue interest at 1.5%/month (18% annually). Final payment due within 30 days of completion invoice. Retention shall be released no later than 30 days after final completion.',
        ]),
        ('14. Lien Rights & Material Pricing', [
            'HD Hauling & Grading reserves its right to file a Claim of Lien per N.C.G.S. Chapter 44A. Customer shall be responsible for attorney\'s fees and collection costs per N.C.G.S. \u00a7\u00a044A-35.',
            '• Material costs are subject to change due to market volatility. No price adjustments without a written Change Order. If Customer denies a price adjustment Change Order, HD Hauling & Grading may suspend the affected scope. HD Hauling & Grading is not liable for delays from plant shutdowns or material shortages.',
        ]),
        ('15. Force Majeure & Entire Agreement', [
            'HD Hauling & Grading shall not be liable for delays caused by circumstances beyond reasonable control, including acts of God, severe weather, labor disputes, government actions, supply chain disruptions, or public health emergencies.',
            '• This Proposal & Contract constitutes the entire agreement and supersedes all prior proposals and understandings. No terms on Customer\'s purchase orders apply unless incorporated by written amendment.',
        ]),
        ('16. Dispute Resolution', [
            'Disputes shall first be addressed through good-faith negotiation. If unresolved within thirty (30) days, either party may pursue binding arbitration (AAA rules) or file in a court of competent jurisdiction in North Carolina. This contract is governed by North Carolina law. The prevailing party shall recover reasonable attorney\u2019s fees and costs.',
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

    # Pricing options comparison table (if multi-option proposal)
    pricing_opts = data.get('pricing_options', [])
    if pricing_opts and len(pricing_opts) > 1:
        story.append(Spacer(1, 0.25*inch))
        story.append(Paragraph('Pricing Options', ParagraphStyle('po_hdr', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, spaceAfter=4)))
        story.append(Spacer(1, 0.08*inch))
        opt_data = [['Option', 'Description', 'Total']]
        for opt in pricing_opts:
            opt_data.append([
                opt.get('name', ''),
                opt.get('description', ''),
                '${:,.2f}'.format(float(opt.get('total', 0)))
            ])
        opt_tbl = Table(opt_data, colWidths=[1.8*inch, 3.5*inch, 1.7*inch])
        opt_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLHDR),
            ('TEXTCOLOR', (0,0), (-1,0), WHITE),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 10),
            ('ALIGN', (-1,0), (-1,-1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, LGRAY]),
            ('GRID', (0,0), (-1,-1), 0.5, TBLBORD),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(opt_tbl)

    story.append(PageBreak())

    if data.get('site_plan_image') or data.get('site_plan_url'):
        story.append(SitePlanPage(data.get('site_plan_image'), data.get('site_plan_url')))
        story.append(PageBreak())

    story += tc_pages(st)
    up_block = unit_prices_block(data)
    if up_block:
        # Start unit prices on a fresh page so both table + approval fit together
        story.append(PageBreak())
        story += up_block
        story.append(Spacer(1, 0.3*inch))
    else:
        story.append(PageBreak())

    story += approval_page(data, st)

    doc.build(story, canvasmaker=canvas_maker(data.get('date',''), data.get('document_number','')))
    print(f'OK: {out_path}')

if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    out  = sys.argv[2] if len(sys.argv) > 2 else '/mnt/user-data/outputs/HD_Proposal.pdf'
    build(data, out)
