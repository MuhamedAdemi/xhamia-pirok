"""
"Evidenca e Antarësisë": për çdo shkronjë të emrit — sa anëtarë, sa kanë paguar, sa s'kanë paguar
dhe sa janë të liruar (gratis), për vitet e zgjedhura. Si tabela që Këshilli e mban në Excel.
"""
from django.utils import timezone

from .fletorja import JO_ANETAR, PAGUAR, rreshtat_e_fletores

# Radha e alfabetit shqip; I/Y dhe L/LL bashkohen si në evidencën e Këshillit.
ALFABETI = ['A', 'B', 'C', 'Ç', 'D', 'DH', 'E', 'Ë', 'F', 'G', 'GJ', 'H', 'I-Y', 'J', 'K', 'L-LL', 'M', 'N',
            'NJ', 'O', 'P', 'Q', 'R', 'RR', 'S', 'SH', 'T', 'TH', 'U', 'V', 'X', 'XH', 'Z', 'ZH']
DYSHKRONJORE = ('DH', 'GJ', 'LL', 'NJ', 'RR', 'SH', 'TH', 'XH', 'ZH')


def grupi(emri):
    e = (emri or '').strip().upper()
    if not e:
        return '?'
    for d in DYSHKRONJORE:
        if e.startswith(d):
            return 'L-LL' if d == 'LL' else d
    if e[0] in 'IY':
        return 'I-Y'
    if e[0] == 'L':
        return 'L-LL'
    return e[0]


def evidenca(vitet):
    """Kthen (grupet, totali): grupet = [{'grupi', 'vitet': [{'antar', 'paguar', 'papaguar', 'gratis'}…]}]."""
    vitet = sorted(vitet)
    _, rreshtat = rreshtat_e_fletores(vitet=vitet)
    tabela = {}
    for r in rreshtat:
        g = tabela.setdefault(grupi(r['shtepia'].emri_kryefamiljarit),
                              [{'antar': 0, 'paguar': 0, 'papaguar': 0, 'gratis': 0} for _ in vitet])
        for j, s in enumerate(r['statuset']):
            if s == JO_ANETAR:
                continue
            g[j]['antar'] += 1
            if r['gratis']:
                g[j]['gratis'] += 1
            elif s == PAGUAR:
                g[j]['paguar'] += 1
            else:
                g[j]['papaguar'] += 1
    radha = {k: i for i, k in enumerate(ALFABETI)}
    grupet = [{'grupi': k, 'vitet': tabela[k]} for k in sorted(tabela, key=lambda k: (radha.get(k, 99), k))]
    totali = [{k: sum(g['vitet'][j][k] for g in grupet) for k in ('antar', 'paguar', 'papaguar', 'gratis')}
              for j in range(len(vitet))]
    return grupet, totali


def vitet_nga(params):
    """Vitet e zgjedhura (?vitet=2025&vitet=2026); parazgjedhur viti i kaluar dhe ky vit."""
    viti = timezone.localdate().year
    vitet = sorted({int(v) for v in params.getlist('vitet') if v.isdigit() and 2000 <= int(v) <= viti + 5})
    return vitet or [viti - 1, viti]


def pdf(vitet, grupet, totali, data):
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    kafe, gri = colors.HexColor('#C9BF9A'), colors.HexColor('#F2F2F2')
    koka1 = ['Nr.', ''] + sum([[str(v), '', '', ''] for v in vitet], [])
    koka2 = ['', ''] + ['Nr. Antar', 'Kanë paguar', "S'kanë paguar", 'Gratis'] * len(vitet)
    te_dhenat = [koka1, koka2]
    for i, g in enumerate(grupet, 1):
        rr = [i, g['grupi']]
        for v in g['vitet']:
            rr += [v['antar'], v['paguar'] or '-', v['papaguar'] or '-', v['gratis'] or '-']
        te_dhenat.append(rr)
    rr = ['', 'Totali']
    for v in totali:
        rr += [v['antar'], v['paguar'], v['papaguar'], v['gratis']]
    te_dhenat.append(rr)

    stili = [
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
        ('FONT', (0, 0), (-1, 1), 'Helvetica-Bold', 8),
        ('FONT', (1, 2), (1, -1), 'Helvetica-Bold', 9),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 10),
        ('BACKGROUND', (0, 1), (-1, 1), kafe),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#808080')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, 0), (0, 1)), ('SPAN', (1, 0), (1, 1)),
    ]
    for j in range(len(vitet)):
        k = 2 + 4 * j
        stili += [('SPAN', (k, 0), (k + 3, 0)),
                  ('BACKGROUND', (k, 2), (k, -1), gri),
                  ('FONT', (k, 2), (k, -1), 'Helvetica-Bold', 9),
                  ('FONT', (k + 2, 2), (k + 2, -1), 'Helvetica-Bold', 9)]
    faqja = landscape(A4) if len(vitet) > 2 else A4
    gjeresite = [1.0 * cm, 1.4 * cm] + [1.65 * cm, 1.75 * cm, 2.05 * cm, 1.35 * cm] * len(vitet)
    shkalla = min(1, (faqja[0] - 2.4 * cm) / sum(gjeresite))   # shumë vite → kolona më të ngushta
    if shkalla < 1:
        stili.append(('FONT', (0, 0), (-1, -1), 'Helvetica', 7))
    tabela = Table(te_dhenat, colWidths=[g * shkalla for g in gjeresite], repeatRows=2)
    tabela.setStyle(TableStyle(stili))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=faqja, leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.2 * cm, title='Evidenca e Antarësisë')
    titulli = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=13, alignment=TA_CENTER)
    doc.build([Paragraph(f'Evidenca e Antarësisë — Xhamia Pirok, data {data.strftime("%d/%m/%Y")}', titulli),
               Spacer(1, 10), tabela])
    return buffer.getvalue()
