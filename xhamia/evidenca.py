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


def kategorite_sipas_grupit():
    """Kategoria e sotme e shtëpive aktive për çdo shkronjë: (kolonat, {grupi: [numrat]}, totali).
    Kolonat: 1, 2, 3, 4 (sipas shumës), G (gratis), Pa (pa kategori)."""
    from .kategorite import kufijte, numrat_e_kategorive
    from .models import Shtepia
    numrat = numrat_e_kategorive()
    kolonat = [str(k.nr) for k in kufijte() if k.kategoria] + ['G', 'Pa']
    indeksi = {k: i for i, k in enumerate(kolonat)}
    tabela = {}
    for emri, kategoria_id in Shtepia.objects.filter(është_aktiv=True).values_list('emri_kryefamiljarit', 'kategoria_id'):
        rreshti = tabela.setdefault(grupi(emri), [0] * len(kolonat))
        rreshti[indeksi.get(numrat.get(kategoria_id), indeksi['Pa'])] += 1
    totali = [sum(r[i] for r in tabela.values()) for i in range(len(kolonat))]
    return kolonat, tabela, totali


def vitet_nga(params):
    """Vitet e zgjedhura (?vitet=2025&vitet=2026); parazgjedhur viti i kaluar dhe ky vit."""
    viti = timezone.localdate().year
    vitet = sorted({int(v) for v in params.getlist('vitet') if v.isdigit() and 2000 <= int(v) <= viti + 5})
    return vitet or [viti - 1, viti]


def pdf(vitet, grupet, totali, data, kategorite=None):
    """kategorite = (kolonat, {grupi: [numrat]}, totali) nga kategorite_sipas_grupit(), ose None."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    kafe, gri = colors.HexColor('#C9BF9A'), colors.HexColor('#F2F2F2')
    kolonat, sipas_grupit, totali_kat = kategorite or ([], {}, [])
    koka1 = ['Nr.', ''] + sum([[str(v), '', '', ''] for v in vitet], [])
    koka2 = ['', ''] + ['Nr. Antar', 'Kanë paguar', "S'kanë paguar", 'Gratis'] * len(vitet)
    if kolonat:
        koka1 += ['Kategoritë (sot)'] + [''] * (len(kolonat) - 1)
        koka2 += [k if k in ('G', 'Pa') else f'Kat. {k}' for k in kolonat]
    te_dhenat = [koka1, koka2]
    for i, g in enumerate(grupet, 1):
        rr = [i, g['grupi']]
        for v in g['vitet']:
            rr += [v['antar'], v['paguar'] or '-', v['papaguar'] or '-', v['gratis'] or '-']
        rr += [n or '-' for n in sipas_grupit.get(g['grupi'], [0] * len(kolonat))]
        te_dhenat.append(rr)
    rr = ['', 'Totali']
    for v in totali:
        rr += [v['antar'], v['paguar'], v['papaguar'], v['gratis']]
    rr += totali_kat
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
    if kolonat:
        k = 2 + 4 * len(vitet)
        stili += [('SPAN', (k, 0), (-1, 0)), ('BACKGROUND', (k, 0), (-1, 1), colors.HexColor('#DCE6FA'))]
    gjeresite = [1.0 * cm, 1.4 * cm] + [1.65 * cm, 1.75 * cm, 2.05 * cm, 1.35 * cm] * len(vitet) \
        + [1.25 * cm] * len(kolonat)
    faqja = landscape(A4) if sum(gjeresite) > A4[0] - 2.4 * cm else A4
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
