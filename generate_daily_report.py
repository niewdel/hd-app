"""
HD Hauling & Grading - Daily Job Report PDF Generator

Generates a daily summary of all scheduled work orders for a given date.
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable, Image)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

RED     = colors.HexColor('#CC0000')
BLACK   = colors.HexColor('#111111')
WHITE   = colors.HexColor('#FFFFFF')
LGRAY   = colors.HexColor('#F4F4F4')
DGRAY   = colors.HexColor('#555555')
TBLBORD = colors.HexColor('#CCCCCC')
ROWALT  = colors.HexColor('#F8F8F8')
COLHDR  = colors.HexColor('#3A3A3A')

W, H    = letter
_DIR    = os.path.dirname(os.path.abspath(__file__))
LOGO    = os.path.join(_DIR, 'hd_logo_cropped.png')
if not os.path.exists(LOGO):
    LOGO = os.path.join(_DIR, 'hd_logo.png')


def _styles():
    return {
        'title':     ParagraphStyle('t',  fontName='Helvetica-Bold', fontSize=18, textColor=RED, alignment=TA_CENTER),
        'subtitle':  ParagraphStyle('st', fontName='Helvetica',      fontSize=12, textColor=BLACK, alignment=TA_CENTER),
        'date':      ParagraphStyle('dt', fontName='Helvetica-Bold', fontSize=14, textColor=BLACK, alignment=TA_CENTER),
        'hdr_cell':  ParagraphStyle('hc', fontName='Helvetica-Bold', fontSize=9,  textColor=WHITE, alignment=TA_LEFT),
        'cell':      ParagraphStyle('cl', fontName='Helvetica',      fontSize=9,  textColor=BLACK, alignment=TA_LEFT),
        'cell_c':    ParagraphStyle('cc', fontName='Helvetica',      fontSize=9,  textColor=BLACK, alignment=TA_CENTER),
        'footer':    ParagraphStyle('ft', fontName='Helvetica-Bold', fontSize=8,  textColor=DGRAY, alignment=TA_CENTER),
        'weather':   ParagraphStyle('wt', fontName='Helvetica',      fontSize=10, textColor=DGRAY, alignment=TA_LEFT),
        'section':   ParagraphStyle('sc', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, alignment=TA_LEFT),
    }


def build(data, outpath):
    """Build the Daily Job Report PDF."""
    s = _styles()

    doc = SimpleDocTemplate(
        outpath,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )

    story = []

    # Logo
    if os.path.exists(LOGO):
        try:
            img = Image(LOGO, width=1.4 * inch, height=1.4 * inch)
            img.hAlign = 'CENTER'
            story.append(img)
            story.append(Spacer(1, 8))
        except Exception:
            pass

    # Title
    story.append(Paragraph('DAILY JOB REPORT', s['title']))
    story.append(Spacer(1, 6))

    # Date
    report_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        dt = datetime.strptime(report_date, '%Y-%m-%d')
        date_display = dt.strftime('%A, %B %d, %Y')
    except (ValueError, TypeError):
        date_display = str(report_date)
    story.append(Paragraph(date_display, s['date']))
    story.append(Spacer(1, 4))

    # Divider
    story.append(HRFlowable(width='100%', thickness=2, color=RED, spaceBefore=4, spaceAfter=12))

    # Weather summary
    weather = data.get('weather', '')
    if weather:
        story.append(Paragraph('<b>Weather:</b> ' + weather, s['weather']))
        story.append(Spacer(1, 10))

    # Work orders table
    work_orders = data.get('work_orders', [])

    story.append(Paragraph('Scheduled Work Orders', s['section']))
    story.append(Spacer(1, 8))

    if work_orders:
        # Table header
        col_widths = [2.2 * inch, 2.0 * inch, 1.2 * inch, 0.9 * inch, 1.0 * inch]
        header = [
            Paragraph('Project', s['hdr_cell']),
            Paragraph('Work Order', s['hdr_cell']),
            Paragraph('Crew', s['hdr_cell']),
            Paragraph('Status', s['hdr_cell']),
            Paragraph('Est. Tons', s['hdr_cell']),
        ]
        rows = [header]

        for wo in work_orders:
            rows.append([
                Paragraph(str(wo.get('project', '')), s['cell']),
                Paragraph(str(wo.get('name', '')), s['cell']),
                Paragraph(str(wo.get('assigned', '')), s['cell']),
                Paragraph(str(wo.get('status', '')).capitalize(), s['cell_c']),
                Paragraph(str(wo.get('tonnage', '—')), s['cell_c']),
            ])

        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl_style = TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), COLHDR),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            # Body rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
            ('TOPPADDING', (0, 1), (-1, -1), 7),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, TBLBORD),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
        # Alternate row colors
        for i in range(1, len(rows)):
            if i % 2 == 0:
                tbl_style.add('BACKGROUND', (0, i), (-1, i), ROWALT)

        tbl.setStyle(tbl_style)
        story.append(tbl)
    else:
        story.append(Paragraph('No work orders scheduled for this date.', s['cell']))

    story.append(Spacer(1, 24))

    # Summary counts
    total_count = len(work_orders)
    active_count = sum(1 for wo in work_orders if wo.get('status', '').lower() == 'active')
    pending_count = sum(1 for wo in work_orders if wo.get('status', '').lower() == 'pending')
    complete_count = sum(1 for wo in work_orders if wo.get('status', '').lower() == 'complete')
    total_tons = 0
    for wo in work_orders:
        try:
            t = wo.get('tonnage', 0)
            if isinstance(t, str):
                t = t.replace(',', '')
            total_tons += float(t) if t else 0
        except (ValueError, TypeError):
            pass

    summary_data = [
        ['Total Work Orders', str(total_count)],
        ['Active', str(active_count)],
        ['Pending', str(pending_count)],
        ['Complete', str(complete_count)],
        ['Total Estimated Tons', '{:,.0f}'.format(total_tons) if total_tons else '—'],
    ]
    summary_tbl = Table(summary_data, colWidths=[2.5 * inch, 1.5 * inch])
    summary_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), BLACK),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, TBLBORD),
        ('LINEBELOW', (0, -1), (-1, -1), 1, RED),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(summary_tbl)

    # Footer
    story.append(Spacer(1, 40))
    story.append(HRFlowable(width='100%', thickness=1, color=TBLBORD, spaceBefore=0, spaceAfter=8))
    story.append(Paragraph('INTERNAL USE ONLY — HD HAULING &amp; GRADING', s['footer']))
    story.append(Paragraph('Generated ' + datetime.now().strftime('%m/%d/%Y at %I:%M %p'), s['footer']))

    doc.build(story)
