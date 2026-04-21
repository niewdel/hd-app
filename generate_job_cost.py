"""
HD Hauling & Grading - Job Cost PDF Generator
INTERNAL CONFIDENTIAL - not a client document
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
import os, sys, json

W, H = letter
LM = RM = 0.6*inch
TM = BM = 0.65*inch

RED    = colors.HexColor('#CC0000')
BLACK  = colors.HexColor('#111111')
DGRAY  = colors.HexColor('#555555')
LGRAY  = colors.HexColor('#F5F5F5')
TBLBRD = colors.HexColor('#D0D0D0')
GREEN  = colors.HexColor('#27500A')
YELLOW = colors.HexColor('#B25000')
DRED   = colors.HexColor('#A32D2D')
ORANGE = colors.HexColor('#CC6600')

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hd_logo.png')

def fi(n):
    return '{:,.2f}'.format(n)

def margin_color(pct):
    if pct is None: return DGRAY
    if pct >= 30: return GREEN
    if pct >= 15: return YELLOW
    return DRED

def build(data, out_path):
    cw = W - LM - RM
    doc = SimpleDocTemplate(out_path, pagesize=letter,
        title='Job Cost Sheet - ' + data.get('project_name',''),
        author='HD Hauling & Grading',
        leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM)

    body  = ParagraphStyle('b',  fontName='Helvetica',      fontSize=10, textColor=BLACK)
    small = ParagraphStyle('s',  fontName='Helvetica',      fontSize=9,  textColor=DGRAY, leading=13)
    bold  = ParagraphStyle('bo', fontName='Helvetica-Bold', fontSize=10, textColor=BLACK)
    hdr   = ParagraphStyle('h',  fontName='Helvetica-Bold', fontSize=9,  textColor=colors.white)
    red   = ParagraphStyle('r',  fontName='Helvetica-Bold', fontSize=9,  textColor=RED)

    story = []

    # -- Header bar
    logo_cell = ''
    if os.path.exists(LOGO_PATH):
        from reportlab.platypus import Image as RLImage
        logo_cell = RLImage(LOGO_PATH, width=1.3*inch, height=0.93*inch)
    else:
        logo_cell = Paragraph('<b>HD Hauling &amp; Grading</b>', bold)

    title_right = [
        Paragraph('JOB COST SHEET', ParagraphStyle('jct', fontName='Helvetica-Bold', fontSize=18, textColor=BLACK, alignment=TA_RIGHT)),
        Paragraph('INTERNAL &mdash; CONFIDENTIAL', ParagraphStyle('conf', fontName='Helvetica-Bold', fontSize=9, textColor=RED, alignment=TA_RIGHT)),
        Paragraph(data.get('date',''), ParagraphStyle('dt', fontName='Helvetica', fontSize=9, textColor=DGRAY, alignment=TA_RIGHT)),
    ]
    hdr_tbl = Table([[logo_cell, title_right]], colWidths=[cw*0.35, cw*0.65])
    hdr_tbl.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(1,0),(1,0),'RIGHT')]))
    story.append(hdr_tbl)
    story.append(HRFlowable(width='100%', thickness=2, color=RED, spaceAfter=10))

    # -- Project Info
    proj = data.get('project_name','')
    client = data.get('client_name','')
    info = Table([
        [Paragraph('<b>Project</b>', bold), Paragraph(proj, body),
         Paragraph('<b>Client</b>', bold), Paragraph(client, body)],
    ], colWidths=[cw*0.15, cw*0.35, cw*0.15, cw*0.35])
    info.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),4),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('LINEBELOW',(0,-1),(-1,-1),0.5,TBLBRD),
    ]))
    story.append(info)
    story.append(Spacer(1, 0.15*inch))

    # -- Cost Breakdown Table
    mat   = float(data.get('mat_cost', 0) or 0)
    truck = float(data.get('truck_cost', 0) or 0)
    labor = float(data.get('labor_cost', 0) or 0)
    ovh_pct = float(data.get('overhead_pct', 0) or 0)
    overhead = float(data.get('overhead', 0) or 0)
    total_cost = float(data.get('total_cost', 0) or 0)
    if total_cost <= 0:
        total_cost = mat + labor + truck + overhead
    bid_price = float(data.get('bid_price', 0) or 0)
    margin_dollar = data.get('margin_dollar')
    margin_pct = data.get('margin_pct')
    if margin_dollar is not None: margin_dollar = float(margin_dollar)
    if margin_pct is not None: margin_pct = float(margin_pct)
    if margin_pct is None or not (margin_pct == margin_pct):  # NaN check
        margin_pct = 0.0

    mc = margin_color(margin_pct)

    def row(label, value, bold_row=False, color=None):
        lbl_style = ParagraphStyle('rl', fontName='Helvetica-Bold' if bold_row else 'Helvetica',
            fontSize=10 if bold_row else 9, textColor=color or (BLACK if bold_row else DGRAY))
        val_style = ParagraphStyle('rv', fontName='Helvetica-Bold' if bold_row else 'Helvetica',
            fontSize=10 if bold_row else 9, textColor=color or (BLACK if bold_row else BLACK),
            alignment=TA_RIGHT)
        return [Paragraph(label, lbl_style), Paragraph(value, val_style)]

    cost_data = [
        [Paragraph('COST CATEGORY', hdr), Paragraph('AMOUNT', ParagraphStyle('ah', fontName='Helvetica-Bold', fontSize=9, textColor=colors.white, alignment=TA_RIGHT))],
        row('Materials',   '$'+fi(mat)   if mat   > 0 else '--'),
        row('Labor',       '$'+fi(labor) if labor > 0 else '--'),
        row('Trucking',    '$'+fi(truck) if truck > 0 else '--'),
        row('Overhead (' + str(int(ovh_pct)) + '%)', '$'+fi(overhead) if overhead > 0 else '--'),
        row('Total Cost',  '$'+fi(total_cost), bold_row=True),
        row('Bid Price',   '$'+fi(bid_price),  bold_row=True),
    ]

    cost_tbl = Table(cost_data, colWidths=[cw*0.6, cw*0.4])
    cost_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,0),  BLACK),
        ('ROWBACKGROUNDS',(0,1),(-1,-3), [colors.white, LGRAY]),
        ('BACKGROUND',    (0,-2),(-1,-2), LGRAY),
        ('BACKGROUND',    (0,-1),(-1,-1), LGRAY),
        ('LINEBELOW',     (0,-3),(-1,-3), 1, TBLBRD),
        ('GRID',          (0,0),(-1,-1),  0.5, TBLBRD),
        ('VALIGN',        (0,0),(-1,-1),  'MIDDLE'),
        ('TOPPADDING',    (0,0),(-1,-1),  6),
        ('BOTTOMPADDING', (0,0),(-1,-1),  6),
        ('LEFTPADDING',   (0,0),(-1,-1),  10),
        ('RIGHTPADDING',  (0,0),(-1,-1),  10),
    ]))
    story.append(Paragraph('Cost Breakdown', ParagraphStyle('cbh', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, spaceAfter=6)))
    story.append(cost_tbl)
    story.append(Spacer(1, 0.18*inch))

    # -- True Margin Summary box
    if margin_pct is not None:
        margin_label = 'Healthy' if margin_pct >= 30 else ('Tight' if margin_pct >= 15 else 'Concerning')
        margin_data = [
            [Paragraph('TRUE MARGIN', ParagraphStyle('mh', fontName='Helvetica-Bold', fontSize=12, textColor=colors.white)),
             Paragraph('$'+fi(margin_dollar) + '  (' + '{:.1f}'.format(margin_pct) + '%)  ' + margin_label,
                ParagraphStyle('mv', fontName='Helvetica-Bold', fontSize=14, textColor=colors.white, alignment=TA_RIGHT))],
        ]
        margin_tbl = Table(margin_data, colWidths=[cw*0.35, cw*0.65])
        margin_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0),(-1,-1), mc),
            ('VALIGN',     (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0),(-1,-1), 10),
            ('BOTTOMPADDING',(0,0),(-1,-1),10),
            ('LEFTPADDING',(0,0),(-1,-1), 14),
            ('RIGHTPADDING',(0,0),(-1,-1),14),
        ]))
        story.append(margin_tbl)
        story.append(Spacer(1, 0.15*inch))

    # -- Disclaimer
    story.append(Paragraph(
        'This document is for internal job costing purposes only. Material cost reflects bid estimate; '
        'actual cost may vary. Equipment and labor costs are as entered at time of proposal. '
        'Overhead is a flat % applied to the subtotal of all cost categories.',
        ParagraphStyle('disc', fontName='Helvetica', fontSize=7, textColor=DGRAY, alignment=TA_CENTER)
    ))

    doc.build(story)

if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    out  = sys.argv[2] if len(sys.argv) > 2 else '/tmp/job_cost.pdf'
    build(data, out)
    print('OK:', out)
