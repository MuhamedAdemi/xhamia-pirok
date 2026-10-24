"""
Regjistri i pagesave "si fletorja": pagesat sipas radhës, me nëntotal sa herë ndryshon blloku
i faturave, total për çdo muaj, tremujor, gjashtëmujor dhe për gjithë periudhën.
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
    [('vit', 'Gjithë viti'), ('h1', 'Gjashtëmujori I (Jan–Qer)'), ('h2', 'Gjashtëmujori II (Kor–Dhj)')]
    + [(f'q{i}', f'Tremujori {r}') for i, r in zip(range(1, 5), ['I (Jan–Mar)', 'II (Pri–Qer)', 'III (Kor–Sht)', 'IV (Tet–Dhj)'])]
    + [(f'm{i}', MUAJT[i - 1]) for i in range(1, 13)]
)


def muajt_e_periudhes(periudha):
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
        self.shumat[p.monedha] += p.shuma_ne_monedhe or 0
        self.eur += p.shuma_eur or 0
        self.nr += 1
        self.vite += getattr(p, 'nr_viteve', 1)


def _emrat(lloji, p):
    if lloji == 'fondi':
        return p.emri_donatorit, '', p.mbiemri_donatorit
    sh = p.shtepia
    return sh.emri_kryefamiljarit, sh.emri_prindit, sh.mbiemri_kryefamiljarit


def ndertoj_regjistrin(lloji, viti, periudha='vit'):
    """Kthen (rreshtat, totali). Çdo rresht ka 'tip': pagese | bllok | muaj | tremujor | gjashtemujor | gjithsej."""
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
    t_bllok = t_muaj = t_3m = t_6m = None
    nr_muajve = m_deri - m_nga + 1

    def mbyll_bllokun(blloku):
        if t_bllok and t_bllok.nr:
            rreshtat.append({'tip': 'bllok', 'etiketa': f'Bllok {blloku}' if blloku else 'Pa bllok', 'totali': t_bllok})

    blloku_aktual = muaji_aktual = None
    for i, p in enumerate(pagesat, 1):
        muaji = p.data_pageses.month
        if muaji != muaji_aktual:
            if muaji_aktual is not None:
                mbyll_bllokun(blloku_aktual)
                _mbyll_muajin(rreshtat, muaji_aktual, viti, t_muaj, t_3m, t_6m, nr_muajve, deri_te=muaji)
                if _kalon_tremujorin(muaji_aktual, muaji):
                    t_3m = Totali()
                if _kalon_gjashtemujorin(muaji_aktual, muaji):
                    t_6m = Totali()
            t_bllok, t_muaj = Totali(), Totali()
            t_3m, t_6m = t_3m or Totali(), t_6m or Totali()
            rreshtat.append({'tip': 'titull', 'etiketa': f'{MUAJT[muaji - 1]} {viti}'})
            muaji_aktual, blloku_aktual = muaji, p.blloku
        elif p.blloku != blloku_aktual:
            mbyll_bllokun(blloku_aktual)
            t_bllok, blloku_aktual = Totali(), p.blloku

        emri, prindi, mbiemri = _emrat(lloji, p)
        rreshtat.append({
            'tip': 'pagese', 'nr': i, 'pagese': p, 'emri': emri, 'prindi': prindi, 'mbiemri': mbiemri,
            'blloku': p.blloku, 'nr_fatures': p.nr_fatures, 'data': p.data_pageses,
            'shumat': {m: (p.shuma_ne_monedhe if p.monedha == m else None) for m in MONEDHAT},
            'eur': p.shuma_eur,
            'vitet': getattr(p, 'vitet_tekst', ''), 'nr_viteve': getattr(p, 'nr_viteve', ''),
            'pershkrimi': (p.arsyeja or p.get_lloji_display()) if lloji == 'fondi' else '',
        })
        for t in (t_bllok, t_muaj, t_3m, t_6m, gjithsej):
            t.shto(p)

    if muaji_aktual is not None:
        mbyll_bllokun(blloku_aktual)
        _mbyll_muajin(rreshtat, muaji_aktual, viti, t_muaj, t_3m, t_6m, nr_muajve, deri_te=None)

    emri_periudhes = dict(PERIUDHAT)[periudha]
    rreshtat.append({'tip': 'gjithsej', 'etiketa': f'GJITHSEJ — {emri_periudhes} {viti}', 'totali': gjithsej})
    return rreshtat, gjithsej


def _kalon_tremujorin(m1, m2):
    return (m1 - 1) // 3 != (m2 - 1) // 3


def _kalon_gjashtemujorin(m1, m2):
    return (m1 - 1) // 6 != (m2 - 1) // 6


def _mbyll_muajin(rreshtat, muaji, viti, t_muaj, t_3m, t_6m, nr_muajve, deri_te):
    rreshtat.append({'tip': 'muaj', 'etiketa': f'Totali — {MUAJT[muaji - 1]}', 'totali': t_muaj})
    fund_3m = deri_te is None or _kalon_tremujorin(muaji, deri_te)
    fund_6m = deri_te is None or _kalon_gjashtemujorin(muaji, deri_te)
    if nr_muajve > 3 and fund_3m:
        q = (muaji - 1) // 3 + 1
        rreshtat.append({'tip': 'tremujor', 'etiketa': f'Totali — Tremujori {"I II III IV".split()[q - 1]}', 'totali': t_3m})
    if nr_muajve > 6 and fund_6m:
        h = (muaji - 1) // 6 + 1
        rreshtat.append({'tip': 'gjashtemujor', 'etiketa': f'Totali — Gjashtëmujori {"I II".split()[h - 1]}', 'totali': t_6m})


# ─── Excel ───────────────────────────────────────────────────────────────────

_HOLLE = Side(style='thin', color='999999')
_TRASHE = Side(style='medium', color='000000')
_NGJYRAT = {
    'bllok': 'EDE7DC', 'muaj': 'D9EAD3', 'tremujor': 'C9DAF8', 'gjashtemujor': 'B4C7E7', 'gjithsej': 'F6B26B',
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

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
