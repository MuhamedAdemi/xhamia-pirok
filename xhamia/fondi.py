"""
"Fletorja e Fondit" — muaj për muaj: gjendja në fillim të muajit, hyrat (donacionet e Fondit),
daljet (harxhimet me buxhet "Fondi i Xhamisë"), bilanci i muajit dhe gjendja në fund.
Për gjithë vitin: përmbledhja e 12 muajve. Faqe, PDF (për arkiv/printim) dhe Excel.
Shumat mbahen sipas monedhës (den, €, CHF, $) — si arka — dhe gjithsej në €.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from .models import Harxhimi, PagesaFondi, formato_shumen
from .raporti import MONEDHAT, MUAJT, Totali

EMRAT_E_MONEDHAVE = {'MKD': 'Denarë', 'EUR': 'Euro', 'CHF': 'Franga', 'USD': 'Dollar'}


class Gjendja:
    """Shuma sipas monedhës + gjithsej në € (mund të jetë edhe negative)."""

    def __init__(self, shumat=None, eur=Decimal('0')):
        self.shumat = {m: Decimal((shumat or {}).get(m) or 0) for m in MONEDHAT}
        self.eur = Decimal(eur or 0)

    @classmethod
    def nga(cls, hyra, dalje, fillimi=None):
        """fillimi + hyra − dalje"""
        fillimi = fillimi or cls()
        return cls({m: fillimi.shumat[m] + hyra.shumat[m] - dalje.shumat[m] for m in MONEDHAT},
                   fillimi.eur + hyra.eur - dalje.eur)


def _hyrat(**filtri):
    return PagesaFondi.objects.filter(**filtri)


def _daljet(**filtri):
    return Harxhimi.objects.filter(burimi='FONDI', **filtri)


def _totali(pagesat):
    t = Totali()
    for p in pagesat:
        t.shto(p)
    return t


def gjendja_para(data):
    """Gjendja e Fondit para një date (të gjitha hyrat − të gjitha daljet deri atëherë)."""
    return Gjendja.nga(_totali(_hyrat(data_pageses__lt=data)), _totali(_daljet(data_pageses__lt=data)))


def _rreshti(p, i, dalje=False):
    if dalje:   # si në fletore: Firma / personi fizik · për çka
        emri = p.marresi or p.lloji
        pershkrimi = ' — '.join(x for x in ((p.lloji if p.marresi else ''), p.pershkrimi) if x)
    else:
        emri = p.shtepia.emri_i_plote if p.shtepia_id else f'{p.emri_donatorit} {p.mbiemri_donatorit}'
        pershkrimi = ' — '.join(x for x in (p.lloji, p.arsyeja) if x)
    return {'nr': i, 'pagese': p, 'emri': emri, 'pershkrimi': pershkrimi, 'fatura': p.fatura_tekst,
            'data': p.data_pageses, 'shumat': p.shumat_sipas_monedhes(), 'eur': p.shuma_eur}


def muaji(viti, muaji_nr):
    """Fletorja e një muaji: {'fillimi', 'hyrat', 't_hyra', 'daljet', 't_dalje', 'bilanci', 'fundi', ...}."""
    nga = date(viti, muaji_nr, 1)
    deri = date(viti + (muaji_nr == 12), muaji_nr % 12 + 1, 1)
    radha = ('data_pageses', 'blloku', 'nr_fatures', 'pk')
    hyrat = list(_hyrat(data_pageses__gte=nga, data_pageses__lt=deri).select_related('shtepia').order_by(*radha))
    daljet = list(_daljet(data_pageses__gte=nga, data_pageses__lt=deri).order_by(*radha))
    t_hyra, t_dalje = _totali(hyrat), _totali(daljet)
    fillimi = gjendja_para(nga)
    bilanci, fundi = Gjendja.nga(t_hyra, t_dalje), Gjendja.nga(t_hyra, t_dalje, fillimi)
    return {
        'rreshtat_bilanci': [('Gjendja në fillim të muajit', fillimi), ('+ Hyrat', t_hyra), ('− Daljet', t_dalje),
                             ('= Bilanci i muajit (hyra − dalje)', bilanci), ('GJENDJA NË FUND TË MUAJIT', fundi)],
        'viti': viti, 'muaji': muaji_nr, 'emri': f'{MUAJT[muaji_nr - 1]} {viti}',
        'fillimi': fillimi,
        'hyrat': [_rreshti(p, i) for i, p in enumerate(hyrat, 1)], 't_hyra': t_hyra,
        'daljet': [_rreshti(h, i, dalje=True) for i, h in enumerate(daljet, 1)], 't_dalje': t_dalje,
        'bilanci': bilanci, 'fundi': fundi,
        'monedhat': _monedhat_ne_perdorim([t_hyra, t_dalje, fillimi]),
    }


def viti_i_plote(viti):
    """Përmbledhja e vitit: për çdo muaj hyrat, daljet, bilanci dhe gjendja në fund; plus totali i vitit."""
    hyra = [Totali() for _ in range(12)]
    dalje = [Totali() for _ in range(12)]
    for p in _hyrat(data_pageses__year=viti):
        hyra[p.data_pageses.month - 1].shto(p)
    for h in _daljet(data_pageses__year=viti):
        dalje[h.data_pageses.month - 1].shto(h)
    fillimi = gjendja_para(date(viti, 1, 1))
    gjendja, muajt = fillimi, []
    k_hyra, k_dalje = Totali(), Totali()
    for i in range(12):
        gjendja = Gjendja.nga(hyra[i], dalje[i], gjendja)
        muajt.append({'muaji': i + 1, 'emri': MUAJT[i], 'hyra': hyra[i], 'dalje': dalje[i],
                      'bilanci': Gjendja.nga(hyra[i], dalje[i]), 'fundi': gjendja})
        k_hyra.bashko(hyra[i])
        k_dalje.bashko(dalje[i])
        if i in (2, 5, 8):   # pas marsit, qershorit, shtatorit: gjithsej 3 / 6 / 9 muajt e parë
            muajt.append({'kumulativ': True, 'emri': f'Gjithsej {i + 1} muajt e parë (Jan–{MUAJT[i][:3]})',
                          'hyra': k_hyra.kopje(), 'dalje': k_dalje.kopje(),
                          'bilanci': Gjendja.nga(k_hyra, k_dalje), 'fundi': gjendja})
    t_hyra, t_dalje = Totali(), Totali()
    for i in range(12):
        t_hyra.bashko(hyra[i])
        t_dalje.bashko(dalje[i])
    return {
        'viti': viti, 'fillimi': fillimi, 'muajt': muajt, 't_hyra': t_hyra, 't_dalje': t_dalje,
        'bilanci': Gjendja.nga(t_hyra, t_dalje), 'fundi': gjendja,
        'monedhat': _monedhat_ne_perdorim([t_hyra, t_dalje, fillimi]),
    }


def _monedhat_ne_perdorim(lista):
    """Denarët dhe euro gjithmonë; frangat/dollarët vetëm kur ka lëvizje në to."""
    return [m for m in MONEDHAT if m in ('MKD', 'EUR') or any(x.shumat[m] for x in lista)]


def shuma(v, monedha):
    return formato_shumen(v, monedha) if v else '–'


# ─── Excel ───────────────────────────────────────────────────────────────────

def excel(viti, muaji_nr=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    koka_stil = (Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor='6B4423'))
    bold = Font(bold=True)

    def koka(rreshti):
        ws.append(rreshti)
        for c in ws[ws.max_row]:
            c.font, c.fill = koka_stil
            c.alignment = Alignment(horizontal='center')

    def ngjyros(ngjyra):
        for c in ws[ws.max_row]:
            c.font = bold
            c.fill = PatternFill('solid', fgColor=ngjyra)

    def numrat(shumat, eur):
        return [float(shumat[m]) for m in MONEDHAT] + [float(eur)]

    emrat = [EMRAT_E_MONEDHAVE[m] for m in MONEDHAT] + ['Gjithsej €']
    if muaji_nr:
        d = muaji(viti, muaji_nr)
        ws.title = d['emri'][:31]
        ws.append([f'Fletorja e Fondit — {d["emri"]} — Xhamia Pirok'])
        ws['A1'].font = Font(bold=True, size=14)
        ws.append([])
        ws.append(['Gjendja në fillim të muajit', '', '', ''] + numrat(d['fillimi'].shumat, d['fillimi'].eur))
        ngjyros('EDE7DC')
        ws.append([])
        ws.append(['HYRAT (donacionet e Fondit)'])
        ws.cell(ws.max_row, 1).font = Font(bold=True, color='38761D', size=12)
        koka(['Nr.', 'Paguesi', 'Lloji / arsyeja', 'Fatura', 'Data'] + emrat)
        for r in d['hyrat']:
            ws.append([r['nr'], r['emri'], r['pershkrimi'], r['fatura'], r['data']]
                      + [float(r['shumat'].get(m) or 0) or None for m in MONEDHAT] + [float(r['eur'])])
        ws.append(['', f'Totali i hyrave · {d["t_hyra"].nr}', '', '', ''] + numrat(d['t_hyra'].shumat, d['t_hyra'].eur))
        ngjyros('D9EAD3')
        ws.append([])
        ws.append(['DALJET (harxhimet nga Fondi)'])
        ws.cell(ws.max_row, 1).font = Font(bold=True, color='C00000', size=12)
        koka(['Nr.', 'Firma / personi fizik', 'Për çka', 'Nr.', 'Data'] + emrat)
        for r in d['daljet']:
            ws.append([r['nr'], r['emri'], r['pershkrimi'], r['fatura'], r['data']]
                      + [float(r['shumat'].get(m) or 0) or None for m in MONEDHAT] + [float(r['eur'])])
        ws.append(['', f'Totali i daljeve · {d["t_dalje"].nr}', '', '', ''] + numrat(d['t_dalje'].shumat, d['t_dalje'].eur))
        ngjyros('F4CCCC')
        ws.append([])
        ws.append(['Bilanci i muajit (hyra − dalje)', '', '', '', ''] + numrat(d['bilanci'].shumat, d['bilanci'].eur))
        ngjyros('C9DAF8')
        ws.append(['Gjendja në fund të muajit', '', '', '', ''] + numrat(d['fundi'].shumat, d['fundi'].eur))
        ngjyros('F6B26B')
        gjeresite = (6, 30, 30, 20, 12)
    else:
        d = viti_i_plote(viti)
        ws.title = f'Fondi {viti}'
        ws.append([f'Fletorja e Fondit — viti {viti} — Xhamia Pirok'])
        ws['A1'].font = Font(bold=True, size=14)
        ws.append([])
        koka(['Muaji'] + [f'Hyra {e}' for e in emrat] + [f'Dalje {e}' for e in emrat] + ['Bilanci €', 'Gjendja në fund €'])
        ws.append(['Gjendja në fillim të vitit'] + [''] * (2 * len(emrat) + 1) + [float(d['fillimi'].eur)])
        ngjyros('EDE7DC')
        for m in d['muajt']:
            ws.append([m['emri']] + numrat(m['hyra'].shumat, m['hyra'].eur) + numrat(m['dalje'].shumat, m['dalje'].eur)
                      + [float(m['bilanci'].eur), float(m['fundi'].eur)])
            if m.get('kumulativ'):
                ngjyros('B4C7E7')
        ws.append([f'GJITHSEJ {viti}'] + numrat(d['t_hyra'].shumat, d['t_hyra'].eur)
                  + numrat(d['t_dalje'].shumat, d['t_dalje'].eur) + [float(d['bilanci'].eur), float(d['fundi'].eur)])
        ngjyros('F6B26B')
        gjeresite = (26,)
    for rr in ws.iter_rows(min_row=3):
        for c in rr:
            if isinstance(c.value, float):
                c.number_format = '#,##0.00'
            elif hasattr(c.value, 'year'):
                c.number_format = 'DD.MM.YYYY'
    from openpyxl.utils import get_column_letter
    for i in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(i)].width = gjeresite[i - 1] if i <= len(gjeresite) else 12
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ─── PDF ─────────────────────────────────────────────────────────────────────

def pdf(viti, muaji_nr=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    kafe = colors.HexColor('#6B4423')
    titulli = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=14, alignment=TA_CENTER)
    nentitull = ParagraphStyle('n', fontName='Helvetica-Bold', fontSize=11, spaceBefore=6)

    def tabela(te_dhenat, gjeresite, shuma_nga, ngjyrat=()):
        stili = [
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 8.5),
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8.5),
            ('BACKGROUND', (0, 0), (-1, 0), kafe),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (shuma_nga, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#AAAAAA')),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]
        for i, ngjyra in ngjyrat:
            stili += [('BACKGROUND', (0, i), (-1, i), colors.HexColor(ngjyra)), ('FONT', (0, i), (-1, i), 'Helvetica-Bold', 8.5)]
        t = LongTable(te_dhenat, colWidths=[g * cm for g in gjeresite], repeatRows=1)
        t.setStyle(TableStyle(stili))
        return t

    pjeset = []
    if muaji_nr:
        d = muaji(viti, muaji_nr)
        mm = d['monedhat']
        emrat = [EMRAT_E_MONEDHAVE[m] for m in mm] + ['Gjithsej €']

        def shumat(sh, eur):
            return [shuma(sh.get(m), m) for m in mm] + [shuma(eur, 'EUR')]

        gj = [0.9, 5.2, 6.4, 3.2, 1.8] + [2.3] * len(emrat)
        pjeset += [Paragraph(f'FLETORJA E FONDIT — {d["emri"].upper()}', titulli), Spacer(1, 8)]
        for emri_seksionit, rreshtat, t, ngjyra in (('Hyrat — donacionet e Fondit', d['hyrat'], d['t_hyra'], '#D9EAD3'),
                                                   ('Daljet — harxhimet nga Fondi', d['daljet'], d['t_dalje'], '#F4CCCC')):
            te_dhenat = [['Nr.', 'Paguesi' if 'Hyrat' in emri_seksionit else 'Firma / personi fizik',
                          'Përshkrimi' if 'Hyrat' in emri_seksionit else 'Për çka', 'Nr.', 'Data'] + emrat]
            for r in rreshtat:
                te_dhenat.append([r['nr'], r['emri'][:32], r['pershkrimi'][:40], r['fatura'], r['data'].strftime('%d.%m.%y')]
                                 + shumat(r['shumat'], r['eur']))
            te_dhenat.append(['', f'Totali · {t.nr}', '', '', ''] + shumat(t.shumat, t.eur))
            pjeset += [Paragraph(emri_seksionit, nentitull), Spacer(1, 3),
                       tabela(te_dhenat, gj, 5, [(len(te_dhenat) - 1, ngjyra)]), Spacer(1, 6)]
        permbledhja = [['', 'Bilanci'] + emrat,
                       ['', 'Gjendja në fillim të muajit'] + shumat(d['fillimi'].shumat, d['fillimi'].eur),
                       ['+', 'Hyrat'] + shumat(d['t_hyra'].shumat, d['t_hyra'].eur),
                       ['−', 'Daljet'] + shumat(d['t_dalje'].shumat, d['t_dalje'].eur),
                       ['=', 'Bilanci i muajit (hyra − dalje)'] + shumat(d['bilanci'].shumat, d['bilanci'].eur),
                       ['', 'GJENDJA NË FUND TË MUAJIT'] + shumat(d['fundi'].shumat, d['fundi'].eur)]
        pjeset += [Paragraph('Bilanci', nentitull), Spacer(1, 3),
                   tabela(permbledhja, [0.7, 7.5] + [2.6] * len(emrat), 2, [(4, '#C9DAF8'), (5, '#F6B26B')])]
        faqja = landscape(A4)
    else:
        d = viti_i_plote(viti)
        koka = ['Muaji', 'Hyra den', 'Hyra €', 'Hyra gjithsej €', 'Dalje den', 'Dalje €', 'Dalje gjithsej €',
                'Bilanci €', 'Gjendja në fund €']
        te_dhenat = [koka, ['Gjendja në fillim të vitit', '', '', '', '', '', '', '', shuma(d['fillimi'].eur, 'EUR')]]
        ngjyrat_kum = []
        for m in d['muajt']:
            if m.get('kumulativ'):
                ngjyrat_kum.append((len(te_dhenat), '#B4C7E7'))
            te_dhenat.append([m['emri'], shuma(m['hyra'].shumat['MKD'], 'MKD'), shuma(m['hyra'].shumat['EUR'], 'EUR'),
                              shuma(m['hyra'].eur, 'EUR'), shuma(m['dalje'].shumat['MKD'], 'MKD'),
                              shuma(m['dalje'].shumat['EUR'], 'EUR'), shuma(m['dalje'].eur, 'EUR'),
                              shuma(m['bilanci'].eur, 'EUR'), shuma(m['fundi'].eur, 'EUR')])
        te_dhenat.append([f'GJITHSEJ {viti}', shuma(d['t_hyra'].shumat['MKD'], 'MKD'), shuma(d['t_hyra'].shumat['EUR'], 'EUR'),
                          shuma(d['t_hyra'].eur, 'EUR'), shuma(d['t_dalje'].shumat['MKD'], 'MKD'),
                          shuma(d['t_dalje'].shumat['EUR'], 'EUR'), shuma(d['t_dalje'].eur, 'EUR'),
                          shuma(d['bilanci'].eur, 'EUR'), shuma(d['fundi'].eur, 'EUR')])
        pjeset += [Paragraph(f'FLETORJA E FONDIT — VITI {viti}', titulli), Spacer(1, 10),
                   tabela(te_dhenat, [5.4] + [2.6] * 8, 1, [(1, '#EDE7DC'), (len(te_dhenat) - 1, '#F6B26B')] + ngjyrat_kum)]
        faqja = landscape(A4)

    def fundi(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#6E6E73'))
        canvas.drawRightString(doc.pagesize[0] - 1.2 * cm, 0.7 * cm, f'Xhamia Pirok — Fletorja e Fondit — faqja {doc.page}')
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=faqja, leftMargin=1.0 * cm, rightMargin=1.0 * cm,
                            topMargin=1.1 * cm, bottomMargin=1.3 * cm, title='Fletorja e Fondit')
    doc.build(pjeset, onFirstPage=fundi, onLaterPages=fundi)
    return buffer.getvalue()
