"""
Të dhënat për Power BI: tabela CSV që Power BI i lexon me "Get data → Web" (dhe i rifreskon me "Refresh").

Lidhjet hapen vetëm me çelësin sekret (`KonfigurimiSistemit.celesi_powerbi`), që admini e krijon / ndryshon /
mbyll te faqja "📊 Power BI". Nuk përmbajnë telefona, email-e apo adresa — vetëm sa duhet për analiza.
"""
import csv
import io

from .gjendja import gjendja_e_shtepive
from .kategorite import numrat_e_kategorive
from .models import Harxhimi, PagesaAntaresia, PagesaFondi, PagesaVarrezave, Shtepia


def _n(v):
    """Numër me pikë dhjetore (pa ndarës mijëshesh), bosh kur mungon."""
    return '' if v is None else f'{float(v):.2f}'


def _shtepite():
    shtepite = list(Shtepia.objects.select_related('kategoria').order_by('nr_shtepise'))
    gjendja = gjendja_e_shtepive(shtepite)
    numrat = numrat_e_kategorive()
    yield ['nr_shtepise', 'emri', 'prindi', 'mbiemri', 'kategoria', 'kategoria_nr', 'aktive', 'viti_fillimit',
           'paguar_deri', 'vite_borxh', 'borxhi_eur']
    for sh in shtepite:
        g = gjendja[sh.id]
        yield [sh.nr_shtepise, sh.emri_kryefamiljarit, sh.emri_prindit, sh.mbiemri_kryefamiljarit,
               sh.kategoria.emri if sh.kategoria_id else '', numrat.get(sh.kategoria_id, ''),
               'po' if sh.është_aktiv else 'jo', sh.viti_fillimit_antaresise or '', g['paguar_deri'] or '',
               len(g['papaguara']), _n(g['borxhi'])]


def _antaresia():
    yield ['pagesa_id', 'data', 'viti', 'muaji', 'blloku', 'nr_fatures', 'nr_shtepise', 'nga_viti', 'deri_viti',
           'monedha', 'shuma_monedhe', 'monedha_2', 'shuma_monedhe_2', 'shuma_den', 'shuma_eur', 'kategoria_pageses']
    for p in PagesaAntaresia.objects.select_related('shtepia', 'kategoria_pageses').order_by('data_pageses', 'pk'):
        yield [p.pk, p.data_pageses.isoformat(), p.data_pageses.year, p.data_pageses.month, p.blloku, p.nr_fatures,
               p.shtepia.nr_shtepise, p.viti, p.viti_deri or p.viti, p.monedha, _n(p.shuma_monedhe), p.monedha_2 or '',
               _n(p.shuma_monedhe_2), _n(p.shuma_mkd), _n(p.shuma_paguar),
               p.kategoria_pageses.emri if p.kategoria_pageses_id else '']


def _antaresia_vitet():
    """Një rresht për çdo vit që mbulon një pagesë, me € e atij viti — për analiza "për cilin vit u pagua"."""
    from .analiza import _ndarja_ne_eur
    from .models import KonfigurimiSistemit
    konfigurimi = KonfigurimiSistemit.merr()
    yield ['pagesa_id', 'data', 'nr_shtepise', 'viti_mbuluar', 'shuma_eur']
    for p in PagesaAntaresia.objects.select_related('shtepia').order_by('data_pageses', 'pk'):
        for viti, eur in sorted(_ndarja_ne_eur(p, konfigurimi).items()):
            yield [p.pk, p.data_pageses.isoformat(), p.shtepia.nr_shtepise, viti, _n(eur)]


def _fondi():
    yield ['pagesa_id', 'data', 'viti', 'muaji', 'blloku', 'nr_fatures', 'lloji', 'zekat', 'nr_shtepise', 'donatori',
           'monedha', 'shuma_monedhe', 'shuma_den', 'shuma_eur']
    for p in PagesaFondi.objects.select_related('shtepia').order_by('data_pageses', 'pk'):
        yield [p.pk, p.data_pageses.isoformat(), p.data_pageses.year, p.data_pageses.month, p.blloku, p.nr_fatures,
               p.lloji, 'po' if p.eshte_zekat else 'jo', p.shtepia.nr_shtepise if p.shtepia_id else '',
               f'{p.emri_donatorit} {p.mbiemri_donatorit}'.strip(), p.monedha, _n(p.shuma_monedhe), _n(p.shuma_mkd),
               _n(p.shuma)]


def _varrezat():
    yield ['pagesa_id', 'data', 'viti', 'muaji', 'blloku', 'nr_fatures', 'nr_shtepise', 'nga_viti', 'deri_viti',
           'monedha', 'shuma_monedhe', 'shuma_den', 'shuma_eur']
    for p in PagesaVarrezave.objects.select_related('shtepia').order_by('data_pageses', 'pk'):
        yield [p.pk, p.data_pageses.isoformat(), p.data_pageses.year, p.data_pageses.month, p.blloku, p.nr_fatures,
               p.shtepia.nr_shtepise, p.viti, p.viti_deri or p.viti, p.monedha, _n(p.shuma_monedhe), _n(p.shuma_mkd),
               _n(p.shuma_paguar)]


def _harxhimet():
    yield ['harxhimi_id', 'data', 'viti', 'muaji', 'nr', 'marresi', 'lloji', 'burimi', 'nga_zekati',
           'monedha', 'shuma_monedhe', 'shuma_den', 'shuma_eur']
    for h in Harxhimi.objects.order_by('data_pageses', 'pk'):
        yield [h.pk, h.data_pageses.isoformat(), h.data_pageses.year, h.data_pageses.month, h.nr_fatures, h.marresi,
               h.lloji, h.get_burimi_display(), 'po' if h.nga_zekati else 'jo', h.monedha, _n(h.shuma_monedhe),
               _n(h.shuma_mkd), _n(h.shuma_eur)]


TABELAT = {
    'shtepite': ('Shtëpitë (kategoria, paguar deri, borxhi)', _shtepite),
    'antaresia': ('Pagesat e antarësisë', _antaresia),
    'antaresia_vitet': ('Antarësia e ndarë sipas vitit që mbulon', _antaresia_vitet),
    'fondi': ('Donacionet e fondit', _fondi),
    'varrezat': ('Pagesat e varrezave', _varrezat),
    'harxhimet': ('Harxhimet (daljet)', _harxhimet),
}


def csv_i_tabeles(emri):
    """Teksti CSV (UTF-8 me BOM, që Power BI / Excel t'i lexojnë drejt ë-të dhe ç-të)."""
    buffer = io.StringIO()
    shkruesi = csv.writer(buffer)
    for rreshti in TABELAT[emri][1]():
        shkruesi.writerow(rreshti)
    return '﻿' + buffer.getvalue()
