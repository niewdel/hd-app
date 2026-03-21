"""
HD Hauling & Grading - Change Order PDF Generator
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
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
DRED   = colors.HexColor('#A32D2D')

def S():
    base = ParagraphStyle('b', fontName='Helvetica', fontSize=10, textColor=BLACK)
    return {
        'title':    ParagraphStyle('t',  fontName='Helvetica-Bold', fontSize=20, textColor=RED, alignment=TA_CENTER),
        'subtitle': ParagraphStyle('st', fontName='Helvetica',      fontSize=11, textColor=DGRAY, alignment=TA_CENTER),
        'hdr':      ParagraphStyle('h',  fontName='Helvetica-Bold', fontSize=10, textColor=BLACK),
        'body':     ParagraphStyle('bd', fontName='Helvetica',      fontSize=9,  textColor=DGRAY, leading=14),
        'cell':     ParagraphStyle('c',  fontName='Helvetica',      fontSize=9,  textColor=BLACK, alignment=TA_RIGHT),
        'cell_b':   ParagraphStyle('cb', fontName='Helvetica-Bold', fontSize=9,  textColor=BLACK, alignment=TA_RIGHT),
        'cell_l':   ParagraphStyle('cl', fontName='Helvetica',      fontSize=9,  textColor=BLACK, alignment=TA_LEFT),
        'section':  ParagraphStyle('sc', fontName='Helvetica-Bold', fontSize=9,  textColor=RED),
        'total':    ParagraphStyle('to', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, alignment=TA_RIGHT),
        'notice':   ParagraphStyle('no', fontName='Helvetica-Bold', fontSize=8,  textColor=DGRAY, alignment=TA_CENTER),
    }

def fi(n):
    return '{:,.2f}'.format(n)

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hd_logo.png')

def build(data, out_path):
    st = S()
    cw = W - LM - RM

    doc = SimpleDocTemplate(out_path, pagesize=letter,
        title='Change Order #' + str(data.get('co_number',1)),
        author='HD Hauling & Grading',
        leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM)

    story = []

    # -- Header ----------------------------------------------------------------
    # Logo + company info side by side
    logo_cell = ''
    if os.path.exists(LOGO_PATH):
        from reportlab.platypus import Image as RLImage
        logo_cell = RLImage(LOGO_PATH, width=1.4*inch, height=1.0*inch)
    else:
        logo_cell = Paragraph('<b>HD Hauling &amp; Grading</b>', st['hdr'])

    co_num = data.get('co_number', 1)
    hdr_right = [
        Paragraph('CHANGE ORDER', ParagraphStyle('coh', fontName='Helvetica-Bold', fontSize=22, textColor=RED, alignment=TA_RIGHT)),
        Paragraph('No. ' + str(co_num), ParagraphStyle('con', fontName='Helvetica-Bold', fontSize=16, textColor=BLACK, alignment=TA_RIGHT)),
        Paragraph(data.get('date',''), ParagraphStyle('cod', fontName='Helvetica', fontSize=10, textColor=DGRAY, alignment=TA_RIGHT)),
    ]
    hdr_tbl = Table([[logo_cell, hdr_right]], colWidths=[cw*0.4, cw*0.6])
    hdr_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN',  (1,0), (1,0),  'RIGHT'),
    ]))
    story.append(hdr_tbl)
    story.append(HRFlowable(width='100%', thickness=2, color=RED, spaceAfter=10))

    # -- Project Info ----------------------------------------------------------
    proj = data.get('project_name','')
    client = data.get('client_name','')
    orig_date = data.get('orig_contract_date','')
    orig_amt = data.get('orig_contract_amount',0)

    info_data = [
        [Paragraph('<b>Project</b>', st['hdr']), Paragraph(proj, st['body']),
         Paragraph('<b>Original Contract Date</b>', st['hdr']), Paragraph(orig_date, st['body'])],
        [Paragraph('<b>Client</b>', st['hdr']), Paragraph(client, st['body']),
         Paragraph('<b>Original Contract Amount</b>', st['hdr']), Paragraph('$'+fi(orig_amt), st['body'])],
    ]
    info_tbl = Table(info_data, colWidths=[cw*0.18, cw*0.32, cw*0.25, cw*0.25])
    info_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
        ('TOPPADDING',   (0,0),(-1,-1), 5),
        ('BOTTOMPADDING',(0,0),(-1,-1), 5),
        ('LINEBELOW',    (0,-1),(-1,-1), 0.5, TBLBRD),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.12*inch))

    # -- Description -----------------------------------------------------------
    desc = data.get('description','')
    if desc:
        desc_hdr = Table([[Paragraph('DESCRIPTION OF CHANGE', st['section'])]], colWidths=[cw])
        desc_hdr.setStyle(TableStyle([
            ('BACKGROUND',   (0,0),(-1,-1), LGRAY),
            ('LINEBEFORE',   (0,0),(0,-1),  4, RED),
            ('TOPPADDING',   (0,0),(-1,-1), 6),
            ('BOTTOMPADDING',(0,0),(-1,-1), 6),
            ('LEFTPADDING',  (0,0),(-1,-1), 10),
        ]))
        story.append(desc_hdr)
        story.append(Paragraph(desc, st['body']))
        story.append(Spacer(1, 0.12*inch))

    # -- Line Items ------------------------------------------------------------
    items = data.get('line_items', [])
    if items:
        col_w = [cw*0.09, cw*0.37, cw*0.08, cw*0.08, cw*0.14, cw*0.14, cw*0.10]
        tbl_data = [[
            Paragraph('TYPE',       ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=TA_CENTER)),
            Paragraph('DESCRIPTION',ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white)),
            Paragraph('QTY',        ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=TA_RIGHT)),
            Paragraph('UNIT',       ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=TA_CENTER)),
            Paragraph('UNIT PRICE', ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=TA_RIGHT)),
            Paragraph('SUBTOTAL',   ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=TA_RIGHT)),
            Paragraph('',           ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white)),
        ]]
        for item in items:
            t = item.get('type','add')
            type_color = GREEN if t=='add' else DRED if t=='deduct' else DGRAY
            type_label = 'ADD' if t=='add' else 'DEDUCT' if t=='deduct' else 'NO COST'
            sub = item.get('subtotal',0)
            sub_str = '--' if t=='nocost' else ('$'+fi(sub))
            price_str = '--' if t=='nocost' else ('$'+fi(item.get('price',0)))
            sign_str = '+' if t=='add' else ('-' if t=='deduct' else '')
            tbl_data.append([
                Paragraph('<b>'+type_label+'</b>', ParagraphStyle('ty', fontName='Helvetica-Bold', fontSize=8, textColor=type_color, alignment=TA_CENTER)),
                Paragraph(item.get('description',''), st['cell_l']),
                Paragraph(str(item.get('qty',1)), st['cell']),
                Paragraph(item.get('unit','LS'), ParagraphStyle('uc', fontName='Helvetica', fontSize=9, textColor=BLACK, alignment=TA_CENTER)),
                Paragraph(price_str, st['cell']),
                Paragraph(sub_str, st['cell_b']),
                Paragraph(sign_str, ParagraphStyle('sg', fontName='Helvetica-Bold', fontSize=10, textColor=type_color, alignment=TA_CENTER)),
            ])

        items_tbl = Table(tbl_data, colWidths=col_w, repeatRows=1)
        items_tbl.setStyle(TableStyle([
            ('BACKGROUND',   (0,0),(-1,0),  BLACK),
            ('BACKGROUND',   (0,1),(-1,-1), colors.white),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, LGRAY]),
            ('GRID',         (0,0),(-1,-1), 0.5, TBLBRD),
            ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING',   (0,0),(-1,-1), 5),
            ('BOTTOMPADDING',(0,0),(-1,-1), 5),
            ('LEFTPADDING',  (0,0),(-1,-1), 6),
            ('RIGHTPADDING', (0,0),(-1,-1), 6),
        ]))
        story.append(items_tbl)
        story.append(Spacer(1, 0.12*inch))

    # -- Cost Summary ----------------------------------------------------------
    add_total    = data.get('add_total', 0)
    deduct_total = data.get('deduct_total', 0)
    revised      = data.get('revised_total', orig_amt)

    sum_data = [
        [Paragraph('Original Contract Amount', st['body']),   Paragraph('$'+fi(orig_amt),    st['cell'])],
        [Paragraph('This Change Order (Add)',   ParagraphStyle('ga', fontName='Helvetica', fontSize=9, textColor=GREEN)),
         Paragraph('+$'+fi(add_total),          ParagraphStyle('gv', fontName='Helvetica', fontSize=9, textColor=GREEN, alignment=TA_RIGHT))],
        [Paragraph('This Change Order (Deduct)',ParagraphStyle('ra', fontName='Helvetica', fontSize=9, textColor=DRED)),
         Paragraph('-$'+fi(deduct_total),       ParagraphStyle('rv', fontName='Helvetica', fontSize=9, textColor=DRED, alignment=TA_RIGHT))],
        [Paragraph('<b>Revised Contract Total</b>', ParagraphStyle('rt', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK)),
         Paragraph('<b>$'+fi(revised)+'</b>',   ParagraphStyle('rv2', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, alignment=TA_RIGHT))],
    ]
    sum_tbl = Table(sum_data, colWidths=[cw*0.6, cw*0.4])
    sum_tbl.setStyle(TableStyle([
        ('ALIGN',        (1,0),(1,-1), 'RIGHT'),
        ('VALIGN',       (0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',   (0,0),(-1,-1), 4),
        ('BOTTOMPADDING',(0,0),(-1,-1), 4),
        ('LINEABOVE',    (0,-1),(-1,-1), 1, TBLBRD),
        ('LINEBELOW',    (0,-1),(-1,-1), 2, RED),
        ('BACKGROUND',   (0,-1),(-1,-1), LGRAY),
    ]))
    story.append(KeepTogether([
        Paragraph('COST SUMMARY', st['section']),
        Spacer(1, 4),
        sum_tbl,
    ]))
    story.append(Spacer(1, 0.25*inch))

    # -- Signature Block -------------------------------------------------------
    sig_notice = (
        'This Change Order is hereby incorporated into and made part of the original Agreement '
        'dated ' + orig_date + ' between HD Hauling &amp; Grading ("Contractor") and '
        + client + ' ("Customer"). All terms and conditions of the original Agreement remain '
        'in full force and effect. Work described herein shall not commence until this Change '
        'Order has been executed by both parties.'
    )
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
    sig_tbl = Table(sig_data, colWidths=[cw/2, cw/2])
    sig_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
        ('TOPPADDING',   (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('LINEABOVE',    (0,0),(-1,0),  1, TBLBRD),
        ('LINEBELOW',    (0,-1),(-1,-1),1, TBLBRD),
    ]))
    story.append(KeepTogether([
        Paragraph(sig_notice, st['notice']),
        Spacer(1, 0.15*inch),
        sig_tbl,
    ]))

    doc.build(story)


if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    out  = sys.argv[2] if len(sys.argv) > 2 else '/tmp/change_order.pdf'
    build(data, out)
    print('OK:', out)
