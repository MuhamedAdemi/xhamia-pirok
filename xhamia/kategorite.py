"""
Kategoritë e antarësisë (1 = më e larta … 4 = më e ulëta) sipas shumës që paguan një shtëpi për një vit.

Rregulli: shtëpia hyn në kategorinë më të lartë, kufirin e së cilës e arrin shuma e vitit, p.sh.
120 € / 7000 den → 1, 100 € / 6000 den → 2, 80 € / 5000 den → 3, ndryshe → 4 (edhe 79 € ose 4999 den).
Kufijtë i vendos admini te faqja Kategoritë (shuma vjetore në € dhe në den).

Kur një vit paguhet me dy monedha (p.sh. 50 € + 1.233 den), pjesët maten secila me kufirin e vet:
50/70 + 1233/4000 ≥ 1 → arrin kategorinë 4. Kështu nuk humbet asgjë nga kursi i këmbimit.

Kategoria e shtëpisë ndryshon vetvetiu me çdo pagesë të re që mbulon vitin e saj më të fundit të paguar.
"""
from dataclasses import dataclass
from decimal import Decimal

from .models import Kategoria, KonfigurimiSistemit, PagesaAntaresia

# Kur në aplikacion nuk ka ende kategori me shumë (p.sh. baza e re), përdoren kufijtë e fletores.
KUFIJTE_PARACAKTUAR = [(Decimal('120'), Decimal('7000')), (Decimal('100'), Decimal('6000')),
                       (Decimal('80'), Decimal('5000')), (Decimal('70'), Decimal('4000'))]


@dataclass
class Kufiri:
    nr: int
    eur: Decimal
    mkd: Decimal
    kategoria: Kategoria | None = None

    @property
    def etiketa(self):
        return f'{self.nr} · {self.kategoria.emri}' if self.kategoria else str(self.nr)


def kufijte(kursi_eur=None):
    """Kategoritë me pagesë, nga më e larta te më e ulëta, me numrin 1, 2, 3…"""
    kursi_eur = kursi_eur or KonfigurimiSistemit.merr().kursi_eur
    kategorite = Kategoria.objects.filter(shuma_vjetore__gt=0, është_aktiv=True).order_by('-shuma_vjetore')
    if kategorite:
        return [Kufiri(nr, k.shuma_vjetore, k.shuma_vjetore_mkd or (k.shuma_vjetore * kursi_eur), k)
                for nr, k in enumerate(kategorite, 1)]
    return [Kufiri(nr, eur, mkd) for nr, (eur, mkd) in enumerate(KUFIJTE_PARACAKTUAR, 1)]


def numrat_e_kategorive():
    """{kategoria_id: '1'…'4' ose 'G'} — si shkruhen kategoritë shkurt te listat."""
    numrat = {k.kategoria.id: str(k.nr) for k in kufijte() if k.kategoria}
    numrat.update({pk: 'G' for pk in Kategoria.objects.filter(shuma_vjetore=0).values_list('id', flat=True)})
    return numrat


def _ne_eur_dhe_den(shumat, konfigurimi):
    """{monedha: shuma} → (€, den): euro dhe denarët mbeten siç janë, frangat/dollarët kthehen në €."""
    eur = mkd = Decimal('0')
    for monedha, shuma in shumat.items():
        if not shuma:
            continue
        if monedha == 'MKD':
            mkd += shuma
        elif monedha == 'EUR':
            eur += shuma
        else:
            eur += shuma * konfigurimi.kursi(monedha) / konfigurimi.kursi_eur
    return eur, mkd


def kufiri_i_shumes(shumat, lista=None, konfigurimi=None):
    """Kategoria (Kufiri) për shumën e një viti {monedha: shuma}; None kur nuk u pagua asgjë."""
    konfigurimi = konfigurimi or KonfigurimiSistemit.merr()
    lista = lista if lista is not None else kufijte(konfigurimi.kursi_eur)
    eur, mkd = _ne_eur_dhe_den(shumat, konfigurimi)
    if not lista or (eur <= 0 and mkd <= 0):
        return None
    for k in lista:
        if eur / k.eur + mkd / k.mkd >= 1:
            return k
    return lista[-1]


def kufiri_i_pageses(pagese, viti=None, lista=None, konfigurimi=None):
    """Kategoria e pagesës për një vit (parazgjedhur: viti i fundit që mbulon)."""
    shumat = pagese.shumat_e_viteve()
    return kufiri_i_shumes(shumat.get(viti or pagese.viti_deri or pagese.viti, {}), lista, konfigurimi)


def kategorite_e_pagesave():
    """{shtepia_id: {viti: 1..4}} — kategoria e pagesës së regjistruar për çdo vit (për fletoren)."""
    konfigurimi = KonfigurimiSistemit.merr()
    lista = kufijte(konfigurimi.kursi_eur)
    rezultati = {}
    for p in PagesaAntaresia.objects.all():
        for viti, shumat in p.shumat_e_viteve().items():
            k = kufiri_i_shumes(shumat, lista, konfigurimi)
            if k:
                vitet = rezultati.setdefault(p.shtepia_id, {})
                vitet[viti] = min(k.nr, vitet.get(viti, k.nr))
    return rezultati


def _viti_i_fundit_i_paguar(shtepia, perjashto=None):
    pagesat = shtepia.pagesat.all()
    if perjashto is not None:
        pagesat = pagesat.exclude(pk=perjashto.pk)
    vitet = [deri or nga for nga, deri in pagesat.values_list('viti', 'viti_deri')]
    return max(vitet + [shtepia.paguar_deri_viti or 0], default=0)


def caktoje_nga_pagesa(pagese):
    """Pas regjistrimit të një pagese antarësie: i jep pagesës kategorinë e saj dhe, nëse pagesa mbulon
    vitin më të fundit të paguar të shtëpisë, ia ndryshon kategorinë edhe shtëpisë.
    Pagesat e borxheve të vjetra (p.sh. 50 € për 2019) nuk e ulin kategorinë e shtëpisë."""
    k = kufiri_i_pageses(pagese)
    if not k or not k.kategoria:
        return None
    if pagese.kategoria_pageses_id != k.kategoria.id:
        pagese.kategoria_pageses = k.kategoria
        pagese.save(update_fields=['kategoria_pageses'])
    shtepia = pagese.shtepia
    if (pagese.viti_deri or pagese.viti) >= _viti_i_fundit_i_paguar(shtepia, perjashto=pagese) \
            and shtepia.kategoria_id != k.kategoria.id:
        shtepia.kategoria = k.kategoria
        shtepia.save(update_fields=['kategoria'])
    return k


def vendos_per_te_gjitha(ruaj=True):
    """Vendos kategorinë e çdo shtëpie që ka pagesë në aplikacion për vitin e saj më të fundit të paguar.
    Shtëpitë që dihet vetëm se kanë paguar (historik, pa shumë) mbeten siç janë, për t'i plotësuar me dorë.
    Kthen [(shtepia, kategoria_e_vjeter, kufiri_i_ri)] për ato që ndryshojnë."""
    konfigurimi = KonfigurimiSistemit.merr()
    lista = kufijte(konfigurimi.kursi_eur)
    if not any(k.kategoria for k in lista):
        return []
    te_fundit = {}
    for p in PagesaAntaresia.objects.select_related('shtepia', 'shtepia__kategoria').order_by('pk'):
        deri = p.viti_deri or p.viti
        if p.shtepia_id not in te_fundit or deri >= (te_fundit[p.shtepia_id].viti_deri or te_fundit[p.shtepia_id].viti):
            te_fundit[p.shtepia_id] = p
    ndryshimet = []
    for p in te_fundit.values():
        sh = p.shtepia
        if (p.viti_deri or p.viti) < (sh.paguar_deri_viti or 0):
            continue   # viti i fundit i paguar dihet vetëm nga historiku — pa shumë
        k = kufiri_i_pageses(p, lista=lista, konfigurimi=konfigurimi)
        if k and sh.kategoria_id != k.kategoria.id:
            ndryshimet.append((sh, sh.kategoria, k))
            if ruaj:
                sh.kategoria = k.kategoria
                sh.save(update_fields=['kategoria'])
        if ruaj and k and p.kategoria_pageses_id != k.kategoria.id:
            p.kategoria_pageses = k.kategoria
            p.save(update_fields=['kategoria_pageses'])
    return ndryshimet
