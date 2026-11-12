"""
Fletëpagesa A4 "ARKA TË PAGUAJË" për një dalje (harxhim) — si blloku "Касата да исплати", por në A4,
me përshkrimin e detajuar të punës, shumën me numra dhe me fjalë, nënshkrimet dhe vendin e vulës.
Fletëpagesës i bashkëngjitet fatura fiskale ose dokumenti i ofruesit të shërbimit.
"""
from io import BytesIO

from django.utils import timezone

from .fjalet import shuma_me_fjale
from .models import formato_shumen


def fletepagesa_pdf(h):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    gri = colors.HexColor('#555555')
    titulli = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=20, alignment=TA_CENTER, leading=24)
    nen = ParagraphStyle('n', fontName='Helvetica', fontSize=9, alignment=TA_CENTER, textColor=gri)
    etiketa = ParagraphStyle('e', fontName='Helvetica', fontSize=9, textColor=gri, leading=11)
    vlera = ParagraphStyle('v', fontName='Helvetica-Bold', fontSize=11.5, leading=15)
    teksti = ParagraphStyle('p', fontName='Helvetica', fontSize=11, leading=16)
    djathtas = ParagraphStyle('d', fontName='Helvetica-Bold', fontSize=16, alignment=TA_RIGHT)

    def esc(t):
        return (t or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    shuma = h.shuma_ne_monedhe
    buxheti = dict(h.BURIMI_CHOICES).get(h.burimi, h.burimi)

    koka = Table([[Paragraph('<b>XHAMIA PIROK</b><br/><font size="9" color="#555555">f. Pirok, Tetovë</font>',
                             ParagraphStyle('x', fontName='Helvetica', fontSize=13, leading=16)),
                   Paragraph(f'Nr. {esc(h.nr_fatures)}', djathtas)]], colWidths=[11.5 * cm, 6.5 * cm])
    koka.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                              ('LINEBELOW', (0, 0), (-1, 0), 1.2, colors.black), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))

    def rresht(e, v):
        return [Paragraph(e, etiketa), Paragraph(v or '&nbsp;', vlera)]

    fushat = Table([
        rresht('Kujt i paguhet<br/>(firma / personi fizik)', esc(h.marresi)),
        rresht('Nga qyteti / fshati', esc(h.qyteti)),
        rresht('Shuma', f'{formato_shumen(shuma, h.monedha)}'
                        + (f' &nbsp;<font size="9" color="#555555">(= {formato_shumen(h.shuma_eur, "EUR")})</font>' if h.monedha != 'EUR' else '')),
        rresht('Me fjalë', esc(shuma_me_fjale(shuma, h.monedha)).capitalize()),
        rresht('Për llogari', esc(h.llogaria)),
        rresht('Për (qëllimi)', esc(h.lloji)),
        rresht('Paguhet nga buxheti', esc(buxheti)),
        rresht('Data', h.data_pageses.strftime('%d.%m.%Y')),
    ], colWidths=[4.5 * cm, 13.5 * cm])
    fushat.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LINEBELOW', (1, 0), (1, -1), 0.6, colors.HexColor('#888888')),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (1, 2), (1, 2), colors.HexColor('#F3F3F3')),
    ]))

    pershkrimi = esc(h.pershkrimi).replace('\n', '<br/>') or '&nbsp;'
    kutia = Table([[Paragraph('<b>Përshkrimi i detajuar i punës / shërbimit</b>', etiketa)],
                   [Paragraph(pershkrimi, teksti)]], colWidths=[18 * cm], rowHeights=[None, 5.0 * cm])
    kutia.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.8, colors.black), ('VALIGN', (0, 1), (0, 1), 'TOP'),
                               ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#EEEEEE')),
                               ('TOPPADDING', (0, 1), (0, 1), 8)]))

    bashk = Paragraph('<b>Bashkëngjitur:</b> &nbsp; [ &nbsp; ] Fatura fiskale &nbsp;&nbsp; [ &nbsp; ] Llogari / faturë e ofruesit të shërbimit'
                      ' &nbsp;&nbsp; [ &nbsp; ] Tjetër: ______________________', ParagraphStyle('b', fontName='Helvetica', fontSize=9.5))

    def nenshkrim(t):
        return [Paragraph(t, ParagraphStyle('s', fontName='Helvetica', fontSize=9, alignment=TA_CENTER, textColor=gri))]

    # 4 nënshkrime me hapësirë mes tyre (kolonat 1, 3, 5 janë boshllëqe), që vijat të mos bashkohen
    emrat = ['Shefi i kontabilitetit', 'Pagoi (arkëtari)', 'Mori (marrësi)', 'Kryetari i këshillit']
    rreshti_2 = []
    for i, e in enumerate(emrat):
        rreshti_2 += nenshkrim(e) + ([''] if i < 3 else [])
    nenshkrimet = Table([[''] * 7, rreshti_2], colWidths=[4.05 * cm, 0.6 * cm] * 3 + [4.05 * cm],
                        rowHeights=[1.6 * cm, None])
    nenshkrimet.setStyle(TableStyle([('LINEABOVE', (k, 1), (k, 1), 0.7, colors.black) for k in (0, 2, 4, 6)]
                                    + [('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    vula = Table([[Paragraph('V.V.<br/><font size="7">(vendi i vulës)</font>',
                             ParagraphStyle('vv', fontName='Helvetica', fontSize=10, alignment=TA_CENTER, textColor=gri))]],
                 colWidths=[2.8 * cm], rowHeights=[2.8 * cm])
    vula.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#AAAAAA')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    fundi = Table([[vula, Paragraph(
        f'Regjistruar në aplikacion nga {esc(h.arktar.get_full_name() or h.arktar.username)} '
        f'më {timezone.localtime(h.data_regjistrimit).strftime("%d.%m.%Y %H:%M")}.', ParagraphStyle('f', fontName='Helvetica', fontSize=8, textColor=gri))]],
        colWidths=[4 * cm, 14 * cm])
    fundi.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM')]))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.4 * cm,
                            bottomMargin=1.4 * cm, title=f'Fletëpagesa {h.nr_fatures}', author='Xhamia Pirok')
    doc.build([
        koka, Spacer(1, 14),
        Paragraph('ARKA TË PAGUAJË', titulli), Paragraph('Fletëpagesë — dalje nga arka', nen), Spacer(1, 8),
        fushat, Spacer(1, 10), kutia, Spacer(1, 6), bashk, Spacer(1, 6), nenshkrimet, Spacer(1, 10), fundi,
    ])
    return buffer.getvalue()
