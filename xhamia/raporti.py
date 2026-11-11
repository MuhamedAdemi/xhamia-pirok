"""
Regjistri i pagesave "si fletorja": pagesat sipas radhës, me nëntotal sa herë ndryshon blloku
i faturave, total për çdo muaj dhe tremujor, gjithsej 3 / 6 / 9 muajt e parë dhe për gjithë vitin,
si dhe statistika e vitit muaj për muaj.
E njëjta strukturë shfaqet në faqe dhe shkarkohet si Excel.
"""
import calendar
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import PagesaAntaresia, PagesaFondi, PagesaVarrezave

MUAJT = ['Janar', 'Shkurt', 'Mars', 'Prill', 'Maj', 'Qershor', 'Korrik', 'Gusht',
         'Shtator', 'Tetor', 'Nëntor', 'Dhjetor']
MONEDHAT = ['MKD', 'EUR', 'CHF', 'USD']

LLOJET = {
    'antaresia': ('Antarësia', PagesaAntaresia),
    'fondi': ('Fondi', PagesaFondi),
    'varrezat': ('Varrezat', PagesaVarrezave),
}

PERIUDHAT = (
    [('vit', 'Gjithë viti (12 muaj)'), ('n9', '9 muajt e parë (Jan–Sht)'), ('h1', '6 muajt e parë (Jan–Qer)'),
     ('h2', 'Gjashtëmujori II (Kor–Dhj)')]
    + [(f'q{i}', f'Tremujori {r}') for i, r in zip(range(1, 5), ['I — 3 muajt e parë (Jan–Mar)', 'II (Pri–Qer)', 'III (Kor–Sht)', 'IV (Tet–Dhj)'])]
    + [(f'm{i}', MUAJT[i - 1]) for i in range(1, 13)]
)


def muajt_e_periudhes(periudha):
    if periudha == 'n9':
        return 1, 9
    if periudha.startswith('h'):
        nga = 1 if periudha == 'h1' else 7
        return nga, nga + 5
    if periudha.startswith('q'):
        nga = (int(periudha[1]) - 1) * 3 + 1
        return nga, nga + 2
    if periudha.startswith('m'):
        m = int(periudha[1:])
        return m, m
    return 1, 12


class Totali:
    def __init__(self):
        self.shumat = {m: Decimal('0') for m in MONEDHAT}
        self.eur = Decimal('0')
        self.nr = 0
        self.vite = 0

    def shto(self, p):
        for monedha, shuma in p.shumat_sipas_monedhes().items():
            self.shumat[monedha] += shuma
        self.eur += p.shuma_eur or 0
        self.nr += 1
        self.vite += getattr(p, 'nr_viteve', 1)

    def bashko(self, tjetri):
        for m in MONEDHAT:
            self.shumat[m] += tjetri.shumat[m]
        self.eur += tjetri.eur
        self.nr += tjetri.nr
        self.vite += tjetri.vite

    def kopje(self):
        t = Totali()
        t.bashko(self)
        return t


def _emrat(lloji, p):
    if lloji == 'fondi':
        return p.emri_donatorit, '', p.mbiemri_donatorit
    sh = p.shtepia
    return sh.emri_kryefamiljarit, sh.emri_prindit, sh.mbiemri_kryefamiljarit


def ndertoj_regjistrin(lloji, viti, periudha='vit'):
    """Kthen (rreshtat, totali). Çdo rresht ka 'tip': titull | pagese | bllok | muaj | tremujor | kumulativ | gjithsej.
    Pas çdo blloku: totali i bllokut; pas çdo muaji: totali i muajit; në fund të tremujorit: totali i tremujorit dhe
    (kur periudha nis në janar) GJITHSEJ 3 / 6 / 9 muajt e parë; në fund: GJITHSEJ e periudhës (viti)."""
    _, model = LLOJET[lloji]
    m_nga, m_deri = muajt_e_periudhes(periudha)
    nga = date(viti, m_nga, 1)
    deri = date(viti, m_deri, calendar.monthrange(viti, m_deri)[1])

    pagesat = model.objects.filter(data_pageses__range=(nga, deri))
    if lloji != 'fondi':
        pagesat = pagesat.select_related('shtepia')
    pagesat = sorted(pagesat, key=lambda p: (p.data_pageses, p.blloku or '', p.nr_fatures.zfill(10), p.pk))

    rreshtat = []
    gjithsej = Totali()
    t_bllok = t_muaj = t_3m = None
    nr_muajve = m_deri - m_nga + 1

    def mbyll_bllokun(blloku):
        if t_bllok and t_bllok.nr:
            rreshtat.append({'tip': 'bllok', 'etiketa': f'Bllok {blloku}' if blloku else 'Pa bllok', 'totali': t_bllok})

    def mbyll_muajin(muaji, deri_te):
        rreshtat.append({'tip': 'muaj', 'etiketa': f'Totali — {MUAJT[muaji - 1]}', 'totali': t_muaj})
        if deri_te is not None and not _kalon_tremujorin(muaji, deri_te):
            return
        q = (muaji - 1) // 3 + 1
        if nr_muajve > 3:
            rreshtat.append({'tip': 'tremujor', 'etiketa': f'Totali — Tremujori {"I II III IV".split()[q - 1]}',
                             'totali': t_3m})
        # GJITHSEJ kumulative nga janari (jo në fund të periudhës — aty del GJITHSEJ e plotë)
        if m_nga == 1 and q < 4 and deri_te is not None:
            rreshtat.append({'tip': 'kumulativ', 'etiketa': f'GJITHSEJ — {3 * q} muajt e parë (Jan–{MUAJT[3 * q - 1][:3]})',
                             'totali': gjithsej.kopje()})

    blloku_aktual = muaji_aktual = None
    for i, p in enumerate(pagesat, 1):
        muaji = p.data_pageses.month
        if muaji != muaji_aktual:
            if muaji_aktual is not None:
                mbyll_bllokun(blloku_aktual)
                mbyll_muajin(muaji_aktual, deri_te=muaji)
                if _kalon_tremujorin(muaji_aktual, muaji):
                    t_3m = None
            t_bllok, t_muaj = Totali(), Totali()
            t_3m = t_3m or Totali()
            rreshtat.append({'tip': 'titull', 'etiketa': f'{MUAJT[muaji - 1]} {viti}'})
            muaji_aktual, blloku_aktual = muaji, p.blloku
        elif p.blloku != blloku_aktual:
            mbyll_bllokun(blloku_aktual)
            t_bllok, blloku_aktual = Totali(), p.blloku

        emri, prindi, mbiemri = _emrat(lloji, p)
        rreshtat.append({
            'tip': 'pagese', 'nr': i, 'pagese': p, 'emri': emri, 'prindi': prindi, 'mbiemri': mbiemri,
            'blloku': p.blloku, 'nr_fatures': p.nr_fatures, 'data': p.data_pageses,
            'shumat': {m: p.shumat_sipas_monedhes().get(m) for m in MONEDHAT},
            'eur': p.shuma_eur,
            'vitet': getattr(p, 'vitet_tekst', ''), 'nr_viteve': getattr(p, 'nr_viteve', ''),
            'pershkrimi': (p.arsyeja or p.get_lloji_display()) if lloji == 'fondi' else '',
        })
        for t in (t_bllok, t_muaj, t_3m, gjithsej):
            t.shto(p)

    if muaji_aktual is not None:
        mbyll_bllokun(blloku_aktual)
        mbyll_muajin(muaji_aktual, deri_te=None)

    emri_periudhes = dict(PERIUDHAT)[periudha]
    rreshtat.append({'tip': 'gjithsej', 'etiketa': f'GJITHSEJ — {emri_periudhes} {viti}', 'totali': gjithsej})
    return rreshtat, gjithsej


def _kalon_tremujorin(m1, m2):
    return (m1 - 1) // 3 != (m2 - 1) // 3


def statistika_vjetore(lloji, viti):
    """Statistika e vitit: çdo muaj, çdo tremujor dhe gjithsej 3 / 6 / 9 / 12 muaj (nga janari).
    Kthen [{'etiketa', 'tip': muaj|tremujor|kumulativ|gjithsej, 'totali': Totali}]."""
    _, model = LLOJET[lloji]
    muajt = [Totali() for _ in range(12)]
    for p in model.objects.filter(data_pageses__year=viti):
        muajt[p.data_pageses.month - 1].shto(p)

    def bashko(lista):
        t = Totali()
        for x in lista:
            t.bashko(x)
        return t

    rreshtat = [{'tip': 'muaj', 'etiketa': MUAJT[i], 'totali': muajt[i]} for i in range(12)]
    rreshtat += [{'tip': 'tremujor', 'etiketa': f'Tremujori {r} ({MUAJT[3 * i][:3]}–{MUAJT[3 * i + 2][:3]})',
                  'totali': bashko(muajt[3 * i:3 * i + 3])} for i, r in enumerate('I II III IV'.split())]
    rreshtat += [{'tip': 'kumulativ', 'etiketa': f'Gjithsej {n} muajt e parë (Jan–{MUAJT[n - 1][:3]})',
                  'totali': bashko(muajt[:n])} for n in (3, 6, 9)]
    rreshtat.append({'tip': 'gjithsej', 'etiketa': f'GJITHSEJ VITI {viti}', 'totali': bashko(muajt)})
    return rreshtat


# ─── Excel ───────────────────────────────────────────────────────────────────

_HOLLE = Side(style='thin', color='999999')
_TRASHE = Side(style='medium', color='000000')
_NGJYRAT = {
    'bllok': 'EDE7DC', 'muaj': 'D9EAD3', 'tremujor': 'C9DAF8', 'kumulativ': 'B4C7E7', 'gjithsej': 'F6B26B',
    'titull': '2D5A1B',
}


def regjistri_excel(lloji, viti, periudha='vit'):
    emri_llojit, _ = LLOJET[lloji]
    rreshtat, _ = ndertoj_regjistrin(lloji, viti, periudha)
    me_vite = lloji != 'fondi'

    koka = ['Nr.', 'Emri', 'Emri i Prindit', 'Mbiemri'] if me_vite else ['Nr.', 'Emri', 'Mbiemri', 'Përshkrimi']
    koka += ['Blloku', 'Nr. Faturës', 'Data', 'Denarë', 'Euro', 'Franga', 'Dollar']
    if me_vite:
        koka += ['Vitet', 'Nr. viteve']
    koka += ['Vlera në €']
    kol_shuma = koka.index('Denarë') + 1

    wb = Workbook()
    ws = wb.active
    ws.title = f'{emri_llojit} {viti}'[:31]
    ws.append([f'Regjistri i {emri_llojit} — {dict(PERIUDHAT)[periudha]} {viti} — Xhamia Pirok'])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(koka)
    for c in ws[3]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='2D5A1B')
        c.alignment = Alignment(horizontal='center')
    ws.freeze_panes = 'A4'

    for r in rreshtat:
        if r['tip'] == 'pagese':
            vlera = [r['nr'], r['emri'], r['prindi'], r['mbiemri']] if me_vite else [r['nr'], r['emri'], r['mbiemri'], r['pershkrimi']]
            vlera += [r['blloku'], r['nr_fatures'], r['data']]
            vlera += [float(r['shumat'][m]) if r['shumat'][m] is not None else None for m in MONEDHAT]
            if me_vite:
                vlera += [r['vitet'], r['nr_viteve']]
            vlera += [float(r['eur'] or 0)]
            ws.append(vlera)
            ws.cell(ws.max_row, koka.index('Data') + 1).number_format = 'DD.MM.YYYY'
        elif r['tip'] == 'titull':
            ws.append([r['etiketa']])
            ws.cell(ws.max_row, 1).font = Font(bold=True, color='2D5A1B', size=12)
        else:
            t = r['totali']
            vlera = [None] * len(koka)
            vlera[1] = r['etiketa']
            vlera[koka.index('Data')] = f'{t.nr} pagesa'
            for j, m in enumerate(MONEDHAT):
                vlera[kol_shuma - 1 + j] = float(t.shumat[m]) or None
            if me_vite:
                vlera[koka.index('Nr. viteve')] = t.vite
            vlera[-1] = float(t.eur)
            ws.append(vlera)
            rr = ws.max_row
            for c in ws[rr]:
                c.font = Font(bold=True)
                c.fill = PatternFill('solid', fgColor=_NGJYRAT[r['tip']])
                c.border = Border(top=_HOLLE, bottom=_TRASHE if r['tip'] == 'bllok' else _HOLLE)

        for j in range(4):
            ws.cell(ws.max_row, kol_shuma + j).number_format = '#,##0' if j == 0 else '#,##0.00'
        ws.cell(ws.max_row, len(koka)).number_format = '#,##0.00'

    gjeresite = {'Nr.': 6, 'Emri': 18, 'Emri i Prindit': 16, 'Mbiemri': 18, 'Përshkrimi': 26, 'Blloku': 9,
                 'Nr. Faturës': 12, 'Data': 12, 'Denarë': 12, 'Euro': 11, 'Franga': 10, 'Dollar': 10,
                 'Vitet': 11, 'Nr. viteve': 10, 'Vlera në €': 12}
    for i, k in enumerate(koka, 1):
        ws.column_dimensions[get_column_letter(i)].width = gjeresite.get(k, 12)
    _printim_excel(ws)

    _fleta_statistika(wb, lloji, viti)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


KOKA_STATISTIKA = ['Periudha', 'Pagesa', 'Denarë', 'Euro', 'Franga', 'Dollar', 'Gjithsej në €']


def _rreshti_statistikes(r):
    t = r['totali']
    return [r['etiketa'], t.nr] + [float(t.shumat[m]) for m in MONEDHAT] + [float(t.eur)]


def _printim_excel(ws):
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _fleta_statistika(wb, lloji, viti):
    emri_llojit, _ = LLOJET[lloji]
    ws = wb.create_sheet('Statistika')
    ws.append([f'Statistika e {emri_llojit} — {viti} — Xhamia Pirok'])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(KOKA_STATISTIKA)
    for c in ws[3]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='2D5A1B')
        c.alignment = Alignment(horizontal='center')
    for r in statistika_vjetore(lloji, viti):
        ws.append(_rreshti_statistikes(r))
        rr = ws.max_row
        ws.cell(rr, 3).number_format = '#,##0'
        for kol in range(4, 8):
            ws.cell(rr, kol).number_format = '#,##0.00'
        if r['tip'] != 'muaj':
            for c in ws[rr]:
                c.font = Font(bold=True)
                c.fill = PatternFill('solid', fgColor=_NGJYRAT[r['tip']])
    for kol, gj in zip('ABCDEFG', (34, 9, 13, 12, 10, 10, 14)):
        ws.column_dimensions[kol].width = gj
    _printim_excel(ws)


# ─── PDF (për printim / arkiv) ────────────────────────────────────────────────

_NGJYRAT_PDF = {'bllok': '#EDE7DC', 'muaj': '#D9EAD3', 'tremujor': '#C9DAF8', 'kumulativ': '#B4C7E7',
                'gjithsej': '#F6B26B', 'titull': '#2D5A1B'}


def _shuma_pdf(v, monedha):
    from .models import formato_shumen
    return formato_shumen(v, monedha) if v else ''


def regjistri_pdf(lloji, viti, periudha='vit'):
    """Regjistri si PDF A4 horizontale: pagesat me totalet (bllok, muaj, tremujor, 3/6/9 muaj, viti) dhe,
    për gjithë vitin, statistika muaj për muaj në fund."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    emri_llojit, _ = LLOJET[lloji]
    rreshtat, _ = ndertoj_regjistrin(lloji, viti, periudha)
    me_vite = lloji != 'fondi'
    koka = (['Nr.', 'Emri', 'Prindi', 'Mbiemri'] if me_vite else ['Nr.', 'Emri', 'Mbiemri', 'Përshkrimi']) \
        + ['Blloku', 'Nr. fat.', 'Data', 'Denarë', 'Euro', 'Franga', 'Dollar'] + (['Vitet'] if me_vite else [])
    te_dhenat, stili = [koka], []
    for r in rreshtat:
        i = len(te_dhenat)
        if r['tip'] == 'pagese':
            emrat = [r['emri'], r['prindi'], r['mbiemri']] if me_vite else [r['emri'], r['mbiemri'], r['pershkrimi'][:28]]
            te_dhenat.append([r['nr']] + emrat + [r['blloku'], r['nr_fatures'], r['data'].strftime('%d.%m.%y')]
                             + [_shuma_pdf(r['shumat'][m], m) for m in MONEDHAT] + ([r['vitet']] if me_vite else []))
        elif r['tip'] == 'titull':
            te_dhenat.append([r['etiketa']] + [''] * (len(koka) - 1))
            stili += [('SPAN', (0, i), (-1, i)), ('BACKGROUND', (0, i), (-1, i), colors.HexColor(_NGJYRAT_PDF['titull'])),
                      ('TEXTCOLOR', (0, i), (-1, i), colors.white), ('FONT', (0, i), (-1, i), 'Helvetica-Bold', 9),
                      ('ALIGN', (0, i), (-1, i), 'LEFT')]
        else:
            t = r['totali']
            te_dhenat.append(['', f"{r['etiketa']} · {t.nr} pagesa", '', '', '', '', '']
                             + [_shuma_pdf(t.shumat[m], m) for m in MONEDHAT] + ([f'{t.vite} vite'] if me_vite else []))
            stili += [('SPAN', (1, i), (6, i)), ('BACKGROUND', (0, i), (-1, i), colors.HexColor(_NGJYRAT_PDF[r['tip']])),
                      ('FONT', (0, i), (-1, i), 'Helvetica-Bold', 8)]
            if r['tip'] == 'bllok':
                stili.append(('LINEBELOW', (0, i), (-1, i), 1.2, colors.black))
    kol_shuma = 7
    gjeresite = ([1.0, 3.6, 3.0, 3.8] if me_vite else [1.0, 3.6, 3.8, 6.0]) + [1.5, 1.8, 1.7, 2.2, 2.0, 1.8, 1.8] \
        + ([1.9] if me_vite else [])
    stili = [
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 8),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2D5A1B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (kol_shuma, 0), (kol_shuma + 3, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#BBBBBB')),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ] + stili
    tabela = LongTable(te_dhenat, colWidths=[g * cm for g in gjeresite], repeatRows=1)
    tabela.setStyle(TableStyle(stili))

    titulli = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=14, alignment=TA_CENTER)
    pjeset = [Paragraph(f'Regjistri i {emri_llojit} — {dict(PERIUDHAT)[periudha]} {viti} — Xhamia Pirok', titulli),
              Spacer(1, 8), tabela]
    if periudha == 'vit':
        pjeset += [PageBreak(), Paragraph(f'Statistika e {emri_llojit} — {viti}', titulli), Spacer(1, 8),
                   _tabela_statistikes_pdf(lloji, viti)]

    def fundi(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#6E6E73'))
        canvas.drawRightString(doc.pagesize[0] - 1.2 * cm, 0.7 * cm, f'Xhamia Pirok — Regjistri i {emri_llojit} {viti} — faqja {doc.page}')
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=1.1 * cm, bottomMargin=1.3 * cm, title=f'Regjistri i {emri_llojit} {viti}')
    doc.build(pjeset, onFirstPage=fundi, onLaterPages=fundi)
    return buffer.getvalue()


def _tabela_statistikes_pdf(lloji, viti):
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Table, TableStyle

    te_dhenat = [KOKA_STATISTIKA]
    stili = [
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2D5A1B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#BBBBBB')),
    ]
    for r in statistika_vjetore(lloji, viti):
        t, i = r['totali'], len(te_dhenat)
        te_dhenat.append([r['etiketa'], t.nr or ''] + [_shuma_pdf(t.shumat[m], m) for m in MONEDHAT]
                         + [_shuma_pdf(t.eur, 'EUR')])
        if r['tip'] != 'muaj':
            stili += [('BACKGROUND', (0, i), (-1, i), colors.HexColor(_NGJYRAT_PDF[r['tip']])),
                      ('FONT', (0, i), (-1, i), 'Helvetica-Bold', 9)]
    tabela = Table(te_dhenat, colWidths=[c * cm for c in (7.5, 2, 3.2, 3, 2.6, 2.6, 3.4)], repeatRows=1)
    tabela.setStyle(TableStyle(stili))
    return tabela


# ─── Fletorja e bllokut ──────────────────────────────────────────────────────

def _numri(nr):
    try:
        return int(nr)
    except (TypeError, ValueError):
        return None


def blloqet():
    """Blloqet e përdorura (më i fundit i pari): [(blloku, nr_pagesave)]."""
    numri, i_fundit = {}, {}
    for _, model in LLOJET.values():
        for blloku, regjistruar in model.objects.exclude(blloku='').values_list('blloku', 'data_regjistrimit'):
            numri[blloku] = numri.get(blloku, 0) + 1
            i_fundit[blloku] = max(i_fundit.get(blloku, regjistruar), regjistruar)
    return [(b, numri[b]) for b in sorted(numri, key=lambda b: i_fundit[b], reverse=True)]


def fletorja_e_bllokut(blloku):
    """Të gjitha pagesat e një blloku (Antarësia, Fondi, Varrezat), sipas numrit të faturës — si fletorja në letër.
    Kthen (rreshtat, totali, numrat_qe_mungojne)."""
    rreshtat, totali = [], Totali()
    for lloji, (emri_llojit, model) in LLOJET.items():
        pagesat = model.objects.filter(blloku=blloku)
        if lloji != 'fondi':
            pagesat = pagesat.select_related('shtepia')
        for p in pagesat:
            if lloji == 'fondi':
                emri = p.shtepia.emri_i_plote if p.shtepia_id else f'{p.emri_donatorit} {p.mbiemri_donatorit}'
                vitet = p.lloji
            else:
                emri, vitet = p.shtepia.emri_i_plote, f'{emri_llojit} {p.vitet_tekst}'
            rreshtat.append({
                'pagese': p, 'emri': emri, 'nr_fatures': p.nr_fatures, 'data': p.data_pageses,
                'shumat': {m: p.shumat_sipas_monedhes().get(m) for m in MONEDHAT}, 'eur': p.shuma_eur,
                'pershkrimi': vitet, 'lloji': emri_llojit,
            })
            totali.shto(p)
    rreshtat.sort(key=lambda r: (_numri(r['nr_fatures']) is None, _numri(r['nr_fatures']) or 0, r['nr_fatures'], r['data']))
    for i, r in enumerate(rreshtat, 1):
        r['nr'] = i
    numrat = sorted({n for n in (_numri(r['nr_fatures']) for r in rreshtat) if n is not None})
    mungojne = [n for n in range(numrat[0], numrat[-1] + 1) if n not in set(numrat)] if numrat else []
    gjatesia = max((len(r['nr_fatures']) for r in rreshtat), default=6)
    return rreshtat, totali, [str(n).zfill(gjatesia) for n in mungojne]


KOKA_BLLOKU = ['Nr.', 'Emri  Prindi  Mbiemri', 'Nr. faturës', 'Data', 'Denarë', 'Euro', 'Franga', 'Dollar', 'Për (vitet)']


def blloku_excel(blloku):
    rreshtat, totali, mungojne = fletorja_e_bllokut(blloku)
    wb = Workbook()
    ws = wb.active
    ws.title = f'Blloku {blloku}'[:31]
    ws.append([f'Fletorja e bllokut {blloku} — Xhamia Pirok'])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(KOKA_BLLOKU)
    for c in ws[3]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='2D5A1B')
        c.alignment = Alignment(horizontal='center')
    for r in rreshtat:
        ws.append([r['nr'], r['emri'], r['nr_fatures'], r['data']]
                  + [float(r['shumat'][m]) if r['shumat'][m] is not None else None for m in MONEDHAT] + [r['pershkrimi']])
        ws.cell(ws.max_row, 4).number_format = 'DD.MM.YYYY'
    ws.append(['', f'TOTALI I BLLOKUT {blloku} · {totali.nr} pagesa', '', '']
              + [float(totali.shumat[m]) or None for m in MONEDHAT] + [f'= {float(totali.eur):,.2f} € gjithsej'])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True, color='C00000')
        c.fill = PatternFill('solid', fgColor='F6B26B')
    if mungojne:
        ws.append([])
        ws.append(['', 'Numrat që mungojnë (anuluar / pa regjistruar): ' + ', '.join(mungojne)])
    for rr in ws.iter_rows(min_row=4, min_col=5, max_col=8):
        for i, c in enumerate(rr):
            c.number_format = '#,##0' if i == 0 else '#,##0.00'
    for kol, gj in zip('ABCDEFGHI', (6, 34, 12, 12, 12, 11, 10, 10, 24)):
        ws.column_dimensions[kol].width = gj
    ws.freeze_panes = 'A4'
    ws.print_title_rows = '3:3'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def blloku_pdf(blloku):
    """Fletorja e bllokut për printim (A4 vertikale): pagesat sipas numrit të faturës dhe totali në fund."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    rreshtat, totali, mungojne = fletorja_e_bllokut(blloku)
    # kolonat Franga / Dollar vetëm kur ka pagesa në to
    monedhat = [m for m in MONEDHAT if m in ('MKD', 'EUR') or totali.shumat[m]]
    emrat_monedhave = {'MKD': 'Denarë', 'EUR': 'Euro', 'CHF': 'Franga', 'USD': 'Dollar'}
    koka = ['Nr.', 'Emri  Prindi  Mbiemri', 'Nr. fat.', 'Data'] + [emrat_monedhave[m] for m in monedhat] + ['Për (vitet)']
    te_dhenat = [koka]
    for r in rreshtat:
        te_dhenat.append([r['nr'], r['emri'][:34], r['nr_fatures'], r['data'].strftime('%d.%m.%y')]
                         + [_shuma_pdf(r['shumat'][m], m) for m in monedhat] + [r['pershkrimi'][:24]])
    te_dhenat.append(['', f'TOTALI · {totali.nr} pagesa', '', ''] + [_shuma_pdf(totali.shumat[m], m) for m in monedhat]
                     + [_shuma_pdf(totali.eur, 'EUR') + ' gjithsej'])
    kol_shuma = 4
    gjeresite = [1.0, 6.2, 1.8, 1.8] + [2.1] * len(monedhat) + [3.6]
    stili = [
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2D5A1B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (kol_shuma, 0), (kol_shuma + len(monedhat) - 1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#999999')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F5F7F2')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F6B26B')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 10),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#9C0006')),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    tabela = LongTable(te_dhenat, colWidths=[g * cm for g in gjeresite], repeatRows=1)
    tabela.setStyle(TableStyle(stili))

    titulli = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=15, alignment=TA_CENTER)
    nen = ParagraphStyle('n', fontName='Helvetica', fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor('#555555'))
    vargu = f'nr {rreshtat[0]["nr_fatures"]} – {rreshtat[-1]["nr_fatures"]}' if rreshtat else 'pa pagesa'
    pjeset = [Paragraph(f'BLLOKU {blloku}', titulli), Spacer(1, 3),
              Paragraph(f'Xhamia Pirok · {vargu} · {totali.nr} pagesa', nen), Spacer(1, 8), tabela]
    if mungojne:
        pjeset += [Spacer(1, 8), Paragraph('Numrat që mungojnë (anuluar / pa regjistruar): ' + ', '.join(mungojne),
                                           ParagraphStyle('m', fontName='Helvetica', fontSize=8.5))]

    def fundi(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#6E6E73'))
        canvas.drawRightString(doc.pagesize[0] - 1.2 * cm, 0.7 * cm, f'Xhamia Pirok — Blloku {blloku} — faqja {doc.page}')
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.0 * cm, rightMargin=1.0 * cm,
                            topMargin=1.1 * cm, bottomMargin=1.3 * cm, title=f'Blloku {blloku}')
    doc.build(pjeset, onFirstPage=fundi, onLaterPages=fundi)
    return buffer.getvalue()
