"""
HD Hauling & Grading - Report PDF Generator
Generates clean, professional multi-page PDFs from structured report data.
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak, Frame, PageTemplate
)
from reportlab.pdfgen import canvas as pdfcanvas
import os, json, re
from html.parser import HTMLParser

W, H = letter
LM = RM = 0.6 * inch
TM = 0.75 * inch
BM = 0.6 * inch

RED     = colors.HexColor('#CC0000')
DRED    = colors.HexColor('#8B0000')
BLACK   = colors.HexColor('#111111')
DGRAY   = colors.HexColor('#555555')
MGRAY   = colors.HexColor('#888888')
LGRAY   = colors.HexColor('#F5F5F5')
XLGRAY  = colors.HexColor('#FAFAFA')
TBLBRD  = colors.HexColor('#DEDEDE')
GREEN   = colors.HexColor('#27500A')
ORANGE  = colors.HexColor('#B25000')
ARED    = colors.HexColor('#A32D2D')
WHITE   = colors.white

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hd_logo_cropped.png')

CW = W - LM - RM  # content width


# ── Styles ────────────────────────────────────────────────────────────────────

def get_styles():
    return {
        'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=18,
                                textColor=RED, spaceAfter=2, leading=22),
        'subtitle': ParagraphStyle('sub', fontName='Helvetica', fontSize=10,
                                   textColor=DGRAY, spaceAfter=0, leading=14),
        'section': ParagraphStyle('section', fontName='Helvetica-Bold', fontSize=12,
                                  textColor=BLACK, spaceBefore=14, spaceAfter=6, leading=15),
        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9,
                               textColor=BLACK, leading=13, spaceAfter=4),
        'small': ParagraphStyle('small', fontName='Helvetica', fontSize=8,
                                textColor=DGRAY, leading=11),
        'th': ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=7.5,
                             textColor=WHITE, leading=10),
        'th_right': ParagraphStyle('th_r', fontName='Helvetica-Bold', fontSize=7.5,
                                   textColor=WHITE, leading=10, alignment=TA_RIGHT),
        'td': ParagraphStyle('td', fontName='Helvetica', fontSize=7.5,
                             textColor=BLACK, leading=10),
        'td_bold': ParagraphStyle('td_b', fontName='Helvetica-Bold', fontSize=7.5,
                                  textColor=BLACK, leading=10),
        'td_right': ParagraphStyle('td_r', fontName='Helvetica', fontSize=7.5,
                                   textColor=BLACK, leading=10, alignment=TA_RIGHT),
        'td_right_bold': ParagraphStyle('td_rb', fontName='Helvetica-Bold', fontSize=7.5,
                                        textColor=BLACK, leading=10, alignment=TA_RIGHT),
        'stat_val': ParagraphStyle('sv', fontName='Helvetica-Bold', fontSize=20,
                                   textColor=BLACK, leading=24, alignment=TA_CENTER),
        'stat_lbl': ParagraphStyle('sl', fontName='Helvetica-Bold', fontSize=7,
                                   textColor=DGRAY, leading=10, alignment=TA_CENTER),
        'stat_sub': ParagraphStyle('ss', fontName='Helvetica', fontSize=7,
                                   textColor=MGRAY, leading=9, alignment=TA_CENTER),
        'footer': ParagraphStyle('foot', fontName='Helvetica', fontSize=7,
                                 textColor=DGRAY, alignment=TA_CENTER),
        'page_num': ParagraphStyle('pn', fontName='Helvetica', fontSize=7,
                                   textColor=MGRAY, alignment=TA_RIGHT),
    }


# ── Page header/footer ───────────────────────────────────────────────────────

class ReportTemplate:
    def __init__(self, report_name, date_range, generated_date):
        self.report_name = report_name
        self.date_range = date_range
        self.generated_date = generated_date

    def on_page(self, canvas, doc):
        canvas.saveState()
        # Top line
        canvas.setStrokeColor(RED)
        canvas.setLineWidth(2)
        canvas.line(LM, H - 0.45 * inch, W - RM, H - 0.45 * inch)
        # Footer line
        canvas.setStrokeColor(TBLBRD)
        canvas.setLineWidth(0.5)
        canvas.line(LM, BM - 0.1 * inch, W - RM, BM - 0.1 * inch)
        # Footer text
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(DGRAY)
        canvas.drawString(LM, BM - 0.28 * inch,
                         f'HD Hauling & Grading  |  {self.report_name}  |  {self.date_range}')
        canvas.drawRightString(W - RM, BM - 0.28 * inch,
                              f'Page {doc.page}  |  Generated {self.generated_date}')
        canvas.restoreState()

    def on_first_page(self, canvas, doc):
        self.on_page(canvas, doc)


# ── Helper: strip HTML tags from cell text ────────────────────────────────────

def strip_html(text):
    if not text:
        return ''
    return re.sub(r'<[^>]+>', '', str(text)).strip()


def is_right_aligned(text):
    """Check if cell content looks like a number/money value."""
    t = strip_html(text).replace(',', '').replace(' ', '')
    if t.startswith('$') or t.startswith('+$') or t.startswith('-$'):
        return True
    if t.endswith('%'):
        return True
    if t.replace('.', '').replace('-', '').replace('+', '').isdigit() and len(t) > 0:
        return True
    return False


# ── Build stat grid ──────────────────────────────────────────────────────────

def build_stat_grid(stats, styles):
    """Render a row of KPI stat boxes as a table."""
    if not stats:
        return []
    n = len(stats)
    col_w = CW / n

    cells = []
    for st in stats:
        val = strip_html(st.get('value', ''))
        lbl = strip_html(st.get('label', ''))
        sub = strip_html(st.get('sub', ''))
        val_color = st.get('color', '#111111')

        val_style = ParagraphStyle('sv_c', parent=styles['stat_val'],
                                   textColor=colors.HexColor(val_color) if val_color else BLACK)
        parts = [
            Paragraph(val.replace('&', '&amp;'), val_style),
            Paragraph(lbl.replace('&', '&amp;').upper(), styles['stat_lbl']),
        ]
        if sub:
            parts.append(Paragraph(sub.replace('&', '&amp;'), styles['stat_sub']))

        # Stack vertically in a mini-table
        inner = Table([[p] for p in parts], colWidths=[col_w - 12])
        inner.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        cells.append(inner)

    t = Table([cells], colWidths=[col_w] * n)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOX', (0, 0), (-1, -1), 0.5, TBLBRD),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, TBLBRD),
        ('BACKGROUND', (0, 0), (-1, -1), XLGRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return [t, Spacer(1, 8)]


# ── Build data table ─────────────────────────────────────────────────────────

def build_table(title, headers, rows, styles, col_widths=None):
    """Render a section title + data table."""
    elements = []
    if title:
        elements.append(Paragraph(title.replace('&', '&amp;'), styles['section']))

    if not headers and not rows:
        return elements

    n_cols = len(headers) if headers else (max(len(r) for r in rows) if rows else 0)
    if n_cols == 0:
        return elements

    # Auto column widths
    if not col_widths:
        cw_each = CW / n_cols
        col_widths = [cw_each] * n_cols

    # Detect right-aligned columns from data (first row)
    right_cols = set()
    if rows:
        for j, cell in enumerate(rows[0]):
            if is_right_aligned(strip_html(cell)):
                right_cols.add(j)

    # Header row
    table_rows = []
    if headers:
        hdr_cells = []
        for j, h in enumerate(headers):
            txt = strip_html(h).replace('&', '&amp;')
            st = styles['th_right'] if j in right_cols else styles['th']
            hdr_cells.append(Paragraph(txt, st))
        while len(hdr_cells) < n_cols:
            hdr_cells.append('')
        table_rows.append(hdr_cells)

    # Data rows
    for row in rows:
        cells = []
        for j, cell in enumerate(row):
            txt = strip_html(cell).replace('&', '&amp;')
            if j == 0:
                st = styles['td_bold']
            elif j in right_cols or is_right_aligned(strip_html(cell)):
                st = styles['td_right_bold'] if txt.startswith('$') else styles['td_right']
            else:
                st = styles['td']
            cells.append(Paragraph(txt, st))
        while len(cells) < n_cols:
            cells.append('')
        table_rows.append(cells)

    if not table_rows:
        return elements

    t = Table(table_rows, colWidths=col_widths, repeatRows=1 if headers else 0)
    style_cmds = [
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, TBLBRD),
    ]

    # Header styling
    if headers:
        style_cmds.extend([
            ('BACKGROUND', (0, 0), (-1, 0), RED),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, DRED),
            ('TOPPADDING', (0, 0), (-1, 0), 6),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ])
        # Alternating row colors for data rows
        for r_idx in range(1, len(table_rows)):
            if r_idx % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, r_idx), (-1, r_idx), LGRAY))

    t.setStyle(TableStyle(style_cmds))
    elements.append(KeepTogether([t]))
    elements.append(Spacer(1, 6))
    return elements


# ── Build horizontal bar chart ───────────────────────────────────────────────

def build_bar_chart(title, items, styles):
    """Render a simple horizontal bar chart as a table."""
    if not items:
        return []
    elements = []
    if title:
        elements.append(Paragraph(title.replace('&', '&amp;'), styles['section']))

    max_val = max(it.get('value', 0) for it in items) or 1
    rows = []
    for it in items:
        lbl = strip_html(it.get('label', ''))
        val = it.get('value', 0)
        display = it.get('display', str(val))
        pct = max(3, val / max_val * 100)
        # Label cell
        lbl_p = Paragraph(lbl.replace('&', '&amp;'),
                         ParagraphStyle('bl', fontName='Helvetica-Bold', fontSize=8,
                                       textColor=BLACK, alignment=TA_RIGHT, leading=11))
        # Bar cell - use a mini table for the bar
        bar_inner = Table(
            [['']],
            colWidths=[CW * 0.55 * pct / 100],
            rowHeights=[14]
        )
        bar_inner.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), RED),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        # Value cell
        val_p = Paragraph(strip_html(display).replace('&', '&amp;'),
                         ParagraphStyle('bv', fontName='Helvetica-Bold', fontSize=8,
                                       textColor=BLACK, leading=11))
        rows.append([lbl_p, bar_inner, val_p])

    t = Table(rows, colWidths=[CW * 0.2, CW * 0.6, CW * 0.2])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 8))
    return elements


# ── Main build ───────────────────────────────────────────────────────────────

def build(data, out_path):
    report_name = data.get('report_name', 'Report')
    date_range = data.get('date_range', '')
    generated_date = data.get('generated_date', '')
    sections = data.get('sections', [])
    html = data.get('html', '')

    styles = get_styles()
    tmpl = ReportTemplate(report_name, date_range, generated_date)

    doc = SimpleDocTemplate(out_path, pagesize=letter,
                            title=f'HD Report - {report_name}',
                            author='HD Hauling & Grading',
                            leftMargin=LM, rightMargin=RM,
                            topMargin=TM, bottomMargin=BM)

    elements = []

    # ── Page 1 Header ────────────────────────────────────────────────────────
    # Logo + title
    header_parts = []
    if os.path.exists(LOGO_PATH):
        from reportlab.platypus import Image
        logo = Image(LOGO_PATH, width=1.4 * inch, height=0.55 * inch)
        header_parts.append([logo, ''])

    header_parts.append([
        Paragraph('HD HAULING &amp; GRADING', styles['title']),
        Paragraph(f'Generated {generated_date}',
                 ParagraphStyle('r', fontName='Helvetica', fontSize=8,
                               textColor=DGRAY, alignment=TA_RIGHT))
    ])
    header_parts.append([
        Paragraph(f'{report_name}',
                 ParagraphStyle('rn', fontName='Helvetica-Bold', fontSize=12,
                               textColor=BLACK, leading=16)),
        Paragraph(f'{date_range}',
                 ParagraphStyle('dr', fontName='Helvetica', fontSize=9,
                               textColor=DGRAY, alignment=TA_RIGHT))
    ])

    ht = Table(header_parts, colWidths=[CW * 0.65, CW * 0.35])
    ht.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width='100%', thickness=2, color=RED, spaceAfter=10))

    # ── Render structured sections ───────────────────────────────────────────
    if sections:
        for sec in sections:
            sec_type = sec.get('type', '')

            if sec_type == 'stats':
                elements.extend(build_stat_grid(sec.get('items', []), styles))

            elif sec_type == 'table':
                elements.extend(build_table(
                    sec.get('title', ''),
                    sec.get('headers', []),
                    sec.get('rows', []),
                    styles
                ))

            elif sec_type == 'bar_chart':
                elements.extend(build_bar_chart(
                    sec.get('title', ''),
                    sec.get('items', []),
                    styles
                ))

            elif sec_type == 'heading':
                elements.append(Paragraph(
                    strip_html(sec.get('text', '')).replace('&', '&amp;'),
                    styles['section']
                ))

            elif sec_type == 'text':
                elements.append(Paragraph(
                    strip_html(sec.get('text', '')).replace('&', '&amp;'),
                    styles['body']
                ))

            elif sec_type == 'spacer':
                elements.append(Spacer(1, sec.get('height', 10)))

    else:
        # Fallback: parse HTML (legacy support)
        text_content, tables = extract_report_data(html)
        for line in text_content.split('\n'):
            line = line.strip()
            if not line or len(line) < 2:
                continue
            elements.append(Paragraph(line.replace('&', '&amp;'), styles['body']))
        for tbl_data in tables:
            if not tbl_data:
                continue
            elements.extend(build_table('', tbl_data[0] if tbl_data else [],
                                       tbl_data[1:] if len(tbl_data) > 1 else [],
                                       styles))

    # ── Build with page templates ────────────────────────────────────────────
    doc.build(elements,
              onFirstPage=tmpl.on_first_page,
              onLaterPages=tmpl.on_page)
    return out_path


# ── Legacy HTML parser (fallback) ────────────────────────────────────────────

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.tables = []
        self._in_table = False
        self._current_table = []
        self._current_row = []
        self._current_cell = ''
        self._in_th = False
        self._in_td = False

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._in_table = True
            self._current_table = []
        elif tag == 'tr':
            self._current_row = []
        elif tag == 'th':
            self._in_th = True; self._current_cell = ''
        elif tag == 'td':
            self._in_td = True; self._current_cell = ''
        elif tag == 'br' and not self._in_table:
            self.result.append('\n')

    def handle_endtag(self, tag):
        if tag == 'table':
            self._in_table = False
            if self._current_table:
                self.tables.append(self._current_table)
        elif tag == 'tr':
            if self._current_row:
                self._current_table.append(self._current_row)
        elif tag in ('th', 'td'):
            self._current_row.append(self._current_cell.strip())
            self._in_th = False; self._in_td = False
        elif tag in ('div', 'p') and not self._in_table:
            self.result.append('\n')

    def handle_data(self, data):
        if self._in_th or self._in_td:
            self._current_cell += data
        else:
            self.result.append(data)

    def get_text(self):
        return ''.join(self.result).strip()


def extract_report_data(html):
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text(), parser.tables
