"""
Shtëpitë e dyfishta: gjetja dhe fshirja përfundimtare.

Kur fshihet një duplikat, asgjë nuk humbet: pagesat (antarësi, varreza, fond), SMS-të dhe kontaktet
që mungojnë kalohen te shtëpia që mbetet. Para fshirjes ruhet një backup në server.
Numri i shtëpisë së fshirë mbetet i lirë dhe e merr shtëpia e radhës që regjistrohet.
"""
from collections import defaultdict

from django.db import transaction

from .kerkimi import normalizo
from .models import MesazhSMS, PagesaAntaresia, PagesaFondi, PagesaVarrezave, Shtepia


def _celesi(sh, me_prind=True):
    pjeset = [sh.emri_kryefamiljarit, sh.emri_prindit if me_prind else '', sh.mbiemri_kryefamiljarit]
    return tuple(normalizo(p).strip() for p in pjeset)


def gjej_duplikatet():
    """Kthen (të_njëjta, të_ngjashme): grupe shtëpish me emër+prind+mbiemër të njëjtë, dhe grupe me
    emër+mbiemër të njëjtë ku të paktën njërës i mungon emri i prindit."""
    shtepite = list(Shtepia.objects.filter(është_aktiv=True).order_by('nr_shtepise'))
    plote, pa_prind = defaultdict(list), defaultdict(list)
    for sh in shtepite:
        plote[_celesi(sh)].append(sh)
        pa_prind[_celesi(sh, me_prind=False)].append(sh)
    te_njejta = [g for g in plote.values() if len(g) > 1]
    ne_te_njejta = {sh.pk for g in te_njejta for sh in g}
    te_ngjashme = [
        g for g in pa_prind.values()
        if len(g) > 1 and any(not sh.emri_prindit for sh in g) and not all(sh.pk in ne_te_njejta for sh in g)
    ]
    return te_njejta, te_ngjashme


def cfare_ka(sh):
    return {
        'Pagesa antarësie': PagesaAntaresia.objects.filter(shtepia=sh).count(),
        'Pagesa varrezash': PagesaVarrezave.objects.filter(shtepia=sh).count(),
        'Pagesa fondi': PagesaFondi.objects.filter(shtepia=sh).count(),
        'SMS': MesazhSMS.objects.filter(shtepia=sh).count(),
        'Llogari portali': 1 if hasattr(sh, 'llogaria') else 0,
    }


def fshi_duplikatin(duplikati, mbetet=None):
    """Fshin përfundimisht `duplikati`; nëse jepet `mbetet`, gjithçka e tij kalohet atje."""
    from django.contrib.auth.models import User
    from .backup import dosja_backup, krijo_zip

    ka = cfare_ka(duplikati)
    ka_pagesa = any(ka[k] for k in ('Pagesa antarësie', 'Pagesa varrezash', 'Pagesa fondi'))
    if ka_pagesa and mbetet is None:
        raise ValueError('Kjo shtëpi ka pagesa — zgjidhni shtëpinë ku do të kalohen.')
    if mbetet is not None and mbetet.pk == duplikati.pk:
        raise ValueError('Zgjidhni një shtëpi tjetër.')

    emri, te_dhenat = krijo_zip()
    (dosja_backup() / f'para-fshirjes-se-shtepise-{duplikati.nr_shtepise}_{emri}').write_bytes(te_dhenat)

    with transaction.atomic():
        if mbetet is not None:
            for model in (PagesaAntaresia, PagesaVarrezave, PagesaFondi, MesazhSMS):
                model.objects.filter(shtepia=duplikati).update(shtepia=mbetet)
            ndryshime = []
            for fusha in ('emri_prindit', 'nr_telefoni_kryesor', 'nr_telefoni_sporadik', 'email',
                          'kontakt_sporadik_emri', 'kontakt_sporadik_email', 'kontakt_sporadik_telefoni'):
                if not getattr(mbetet, fusha) and getattr(duplikati, fusha):
                    setattr(mbetet, fusha, getattr(duplikati, fusha))
                    ndryshime.append(fusha)
            if duplikati.shenime:
                mbetet.shenime = '\n'.join(filter(None, [mbetet.shenime,
                                                         f'(nga shtëpia e fshirë #{duplikati.nr_shtepise}) {duplikati.shenime}']))
                ndryshime.append('shenime')
            if ndryshime:
                mbetet.save(update_fields=ndryshime)
        llogaria = getattr(duplikati, 'llogaria', None)
        if llogaria is not None:
            User.objects.filter(pk=llogaria.user_id).delete()
        duplikati.delete()
