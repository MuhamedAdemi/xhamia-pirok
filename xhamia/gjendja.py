"""
Gjendja e antarësisë për shumë shtëpi njëherësh: cilat vite janë të papaguara, deri kur ka paguar
dhe sa është borxhi minimal (sipas tarifës: p.sh. 50 € për vitet e kaluara, 70 € për vitin aktual).
"""
from decimal import Decimal

from django.utils import timezone

from .models import KonfigurimiSistemit, PagesaAntaresia


def gjendja_e_shtepive(shtepite):
    """Kthen {shtepia_id: {'papaguara': [...], 'borxhi': Decimal, 'paguar_deri': int|None, 'borxh_nga': int|None}}."""
    viti_aktual = timezone.now().year
    tarifa = KonfigurimiSistemit.merr().tarifa_antaresise
    mbuluara = {}
    for sh_id, nga, deri in PagesaAntaresia.objects.values_list('shtepia_id', 'viti', 'viti_deri'):
        mbuluara.setdefault(sh_id, set()).update(range(nga, (deri or nga) + 1))

    rezultati = {}
    for sh in shtepite:
        paguara = set(mbuluara.get(sh.id, set()))
        if sh.paguar_deri_viti:
            paguara.update(range(min(sh.viti_fillimit_antaresise, sh.paguar_deri_viti), sh.paguar_deri_viti + 1))
        papaguara = [v for v in range(sh.viti_fillimit_antaresise, viti_aktual + 1) if v not in paguara]
        borxh_nga = papaguara[0] if papaguara else None
        if borxh_nga:
            paguar_deri = borxh_nga - 1 if (borxh_nga - 1) in paguara else None
        else:
            paguar_deri = max(paguara) if paguara else None
        rezultati[sh.id] = {
            'papaguara': papaguara,
            'borxhi': sum((tarifa(v) for v in papaguara), Decimal('0')),
            'paguar_deri': paguar_deri,
            'borxh_nga': borxh_nga,
        }
    return rezultati


def vitet_tekst(vitet):
    """[2016, 2017, ..., 2026] → '2016–2026'; vite me ndërprerje → '2019, 2021–2026'."""
    grupet = []
    for v in vitet:
        if grupet and v == grupet[-1][1] + 1:
            grupet[-1][1] = v
        else:
            grupet.append([v, v])
    return ', '.join(str(a) if a == b else f'{a}–{b}' for a, b in grupet)
