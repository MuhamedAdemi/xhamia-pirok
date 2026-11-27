"""
Analizat e dashboardit të Antarësisë (si Power BI): kurba mujore, sezonaliteti i pagesave, mbulimi vit për vit,
monedhat, kategoritë, borxhi dhe për cilat vite paguajnë njerëzit.

Gjithçka llogaritet me pak kërkesa në bazë (një për pagesat, një për shtëpitë) dhe pastaj në Python, që faqja të
jetë e shpejtë edhe në PythonAnywhere falas.

Rregulli i historisë: kush ka "paguar deri" vitin X (fletore / import) i ka të paguara të gjitha vitet nga fillimi
i antarësisë deri te X; një pagesë mbulon vitet viti..viti_deri.
"""
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from django.utils import timezone

from .gjendja import gjendja_e_shtepive, kategorite_gratis
from .models import KonfigurimiSistemit, PagesaAntaresia, Shtepia

MUAJT = ['Jan', 'Shk', 'Mar', 'Pri', 'Maj', 'Qer', 'Kor', 'Gus', 'Sht', 'Tet', 'Nën', 'Dhj']
MUAJT_PLOTE = ['Janar', 'Shkurt', 'Mars', 'Prill', 'Maj', 'Qershor', 'Korrik', 'Gusht', 'Shtator', 'Tetor',
               'Nëntor', 'Dhjetor']
VITI_PARE = 2015


def _monedha_e_pageses(p):
    if p.monedha_2 and p.shuma_monedhe_2:
        return 'EUR + den' if {p.monedha, p.monedha_2} == {'EUR', 'MKD'} else f'{p.monedha} + {p.monedha_2}'
    return {'MKD': 'Denarë', 'EUR': 'Euro', 'CHF': 'Franga', 'USD': 'Dollarë'}.get(p.monedha, p.monedha)


def _ndarja_ne_eur(p, konfigurimi):
    """{viti_i_mbuluar: €} — shuma e pagesës në € e ndarë sipas viteve (sipas ndarjes së shkruar, ose njëlloj)."""
    vitet = p.shumat_e_viteve()
    peshat = {v: sum((Decimal(s) * konfigurimi.kursi(m) for m, s in shumat.items() if s), Decimal('0'))
              for v, shumat in vitet.items()}
    gjithsej = sum(peshat.values())
    eur = p.shuma_paguar or Decimal('0')
    if not gjithsej:
        return {v: eur / len(vitet) for v in vitet} if vitet else {}
    return {v: eur * pesha / gjithsej for v, pesha in peshat.items()}


def _ndryshimi(tani, para):
    """Ndryshimi në % kundrejt vitit të kaluar (None kur viti i kaluar është 0)."""
    if not para:
        return None
    return round(float((tani - para) / para * 100), 1)


def antaresia(viti):
    sot = timezone.localdate()
    viti_aktual = sot.year
    konfigurimi = KonfigurimiSistemit.merr()
    pagesat = list(PagesaAntaresia.objects.only(
        'id', 'shtepia_id', 'data_pageses', 'shuma_paguar', 'monedha', 'shuma_monedhe', 'monedha_2',
        'shuma_monedhe_2', 'viti', 'viti_deri', 'vitet_shumat', 'shuma_mkd', 'kursi_denar',
    ))

    # ── Kurba mujore: viti i zgjedhur kundrejt vitit të kaluar (€ dhe numri i pagesave)
    mujore = {viti: [0.0] * 12, viti - 1: [0.0] * 12}
    numri_mujor = [0] * 12
    for p in pagesat:
        v, m = p.data_pageses.year, p.data_pageses.month - 1
        if v in mujore:
            mujore[v][m] += float(p.shuma_paguar or 0)
        if v == viti:
            numri_mujor[m] += 1
    kumulative = {v: [round(sum(s[:i + 1]), 2) for i in range(12)] for v, s in mujore.items()}

    # ── Sezonaliteti: gjithë vitet bashkë — në cilët muaj paguhet më shumë / më pak
    sezoni_eur, sezoni_nr, vitet_me_te_dhena = [0.0] * 12, [0] * 12, set()
    for p in pagesat:
        sezoni_eur[p.data_pageses.month - 1] += float(p.shuma_paguar or 0)
        sezoni_nr[p.data_pageses.month - 1] += 1
        vitet_me_te_dhena.add(p.data_pageses.year)
    i_forti = max(range(12), key=lambda i: sezoni_nr[i]) if any(sezoni_nr) else None
    i_dobeti = min(range(12), key=lambda i: sezoni_nr[i]) if any(sezoni_nr) else None

    # ── Treguesit (KPI) — për vitin aktual krahasohet me të njëjtën periudhë të vitit të kaluar
    te_vitit = [p for p in pagesat if p.data_pageses.year == viti]
    if viti == viti_aktual:
        kufiri = sot.replace(year=viti - 1) if not (sot.month == 2 and sot.day == 29) else date(viti - 1, 2, 28)
        te_kaluarit = [p for p in pagesat if p.data_pageses.year == viti - 1 and p.data_pageses <= kufiri]
        periudha = f'deri më {sot:%d.%m}'
    else:
        te_kaluarit = [p for p in pagesat if p.data_pageses.year == viti - 1]
        periudha = 'gjithë vitin'
    eur_tani = sum((p.shuma_paguar or Decimal('0') for p in te_vitit), Decimal('0'))
    eur_para = sum((p.shuma_paguar or Decimal('0') for p in te_kaluarit), Decimal('0'))

    # ── Mbulimi vit për vit: sa shtëpi e kanë paguar secilin vit (pagesa + historia)
    shtepite = list(Shtepia.objects.filter(është_aktiv=True).only(
        'id', 'kategoria_id', 'viti_fillimit_antaresise', 'paguar_deri_viti'))
    gratis = kategorite_gratis()
    mbuluara = defaultdict(set)
    for p in pagesat:
        mbuluara[p.shtepia_id].update(range(p.viti, (p.viti_deri or p.viti) + 1))
    fillimet = [sh.viti_fillimit_antaresise for sh in shtepite if sh.viti_fillimit_antaresise]
    vitet = list(range(max(VITI_PARE, min(fillimet + list(vitet_me_te_dhena) + [viti_aktual])), viti_aktual + 1))
    mbulimi = []
    for v in vitet:
        detyruar = paguar = 0
        for sh in shtepite:
            if sh.kategoria_id in gratis or (sh.viti_fillimit_antaresise or 0) > v:
                continue
            detyruar += 1
            if v in mbuluara.get(sh.id, ()) or (sh.paguar_deri_viti and sh.paguar_deri_viti >= v):
                paguar += 1
        mbulimi.append({'viti': v, 'paguar': paguar, 'papaguar': detyruar - paguar,
                        'perqindja': round(100 * paguar / detyruar, 1) if detyruar else 0})
    mbulimi_i_vitit = next((m for m in mbulimi if m['viti'] == viti), None)

    # ── Për cilat vite paguan njerëzit gjatë vitit të zgjedhur (viti aktual apo borxhe të vjetra)
    per_vitet = defaultdict(float)
    for p in te_vitit:
        for v, eur in _ndarja_ne_eur(p, konfigurimi).items():
            per_vitet[v] += float(eur)
    per_vitet = sorted(per_vitet.items())
    borxh_i_vjeter = sum(e for v, e in per_vitet if v < viti)

    # ── Monedhat e pagesave të vitit
    monedhat = Counter(_monedha_e_pageses(p) for p in te_vitit)

    # ── Kategoritë e shtëpive (tani) dhe shpërndarja e borxhit (sa vite pa paguar)
    from .kategorite import numrat_e_kategorive
    numrat = numrat_e_kategorive()
    kategorite = Counter(numrat.get(sh.kategoria_id, '—') for sh in shtepite)
    gjendja = gjendja_e_shtepive(shtepite)
    grupet = ['0', '1', '2', '3', '4', '5–9', '10+']
    borxhi = Counter()
    borxhi_total = Decimal('0')
    for sh in shtepite:
        g = gjendja[sh.id]
        n = len(g['papaguara'])
        borxhi[grupet[min(n, 5)] if n < 5 else ('5–9' if n < 10 else '10+')] += 1
        borxhi_total += g['borxhi']

    return {
        'muajt': MUAJT,
        'mujore': {'tani': [round(x, 2) for x in mujore[viti]], 'para': [round(x, 2) for x in mujore[viti - 1]],
                   'numri': numri_mujor, 'kumul_tani': kumulative[viti], 'kumul_para': kumulative[viti - 1]},
        'sezoni': {'eur': [round(x, 2) for x in sezoni_eur], 'nr': sezoni_nr,
                   'i_forti': MUAJT_PLOTE[i_forti] if i_forti is not None else '—',
                   'i_dobeti': MUAJT_PLOTE[i_dobeti] if i_dobeti is not None else '—',
                   'vitet': len(vitet_me_te_dhena)},
        'mbulimi': mbulimi,
        'per_vitet': [{'viti': v, 'eur': round(e, 2)} for v, e in per_vitet],
        'monedhat': [{'emri': k, 'nr': n} for k, n in monedhat.most_common()],
        'kategorite': [{'emri': (f'Kategoria {k}' if k.isdigit() else ('Gratis' if k == 'G' else 'Pa kategori')),
                        'nr': kategorite[k]} for k in sorted(kategorite, key=lambda k: (not k.isdigit(), k))],
        'borxhi': [{'grupi': g, 'nr': borxhi[g]} for g in grupet],
        'kpi': {
            'eur': eur_tani, 'eur_para': eur_para, 'ndryshimi': _ndryshimi(eur_tani, eur_para), 'periudha': periudha,
            'nr': len(te_vitit), 'nr_para': len(te_kaluarit), 'ndryshimi_nr': _ndryshimi(len(te_vitit), len(te_kaluarit)),
            'mesatarja': (eur_tani / len(te_vitit)) if te_vitit else Decimal('0'),
            'mbulimi': mbulimi_i_vitit,
            'borxh_i_vjeter': borxh_i_vjeter, 'borxh_i_vjeter_perqindja': round(100 * borxh_i_vjeter / float(eur_tani), 1) if eur_tani else 0,
            'borxhi_total': borxhi_total, 'pa_borxh': borxhi['0'], 'shtepite': len(shtepite),
            'gratis': sum(1 for sh in shtepite if sh.kategoria_id in gratis),
        },
    }
