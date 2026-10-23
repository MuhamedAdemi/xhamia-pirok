"""
Leximi i listave PDF të eksportuara nga "Masjid Manager" (Nr. | Emri | Prindi | Mbiemri | Telefon).

Në këto PDF çdo qelizë e tabelës del si fragment teksti më vete, me radhë: numri i rreshtit
(i pozicionuar majtas), pastaj Emri, Prindi, Mbiemri dhe — nëse ka — Telefoni. Prandaj
rreshtat ndërtohen nga fragmentet, jo duke ndarë tekstin me hapësira, sepse disa emra kanë
hapësira brenda (p.sh. "Haqim (Haxhi Profi)", "Gjyshi Dehar").
"""
import re

from pypdf import PdfReader


def _fragmentet(skedari):
    fragmentet = []
    for faqja in PdfReader(skedari).pages:
        faqja.extract_text(
            visitor_text=lambda t, cm, tm, fd, fs: fragmentet.append((tm[4], t.strip()))
            if t and t.strip() else None
        )
    return fragmentet


def lexo_rreshtat(skedari):
    """Kthen listën e rreshtave {'nr', 'emri', 'prindi', 'mbiemri', 'telefon'} sipas radhës në PDF."""
    rreshtat = []
    qelizat = None
    for x, teksti in _fragmentet(skedari):
        if x > 5 and re.fullmatch(r'\d+', teksti):
            qelizat = [teksti]
            rreshtat.append(qelizat)
        elif qelizat is not None and x == 0:
            if teksti == 'Masjid Manager':   # fundi i faqes
                qelizat = None
            else:
                qelizat.append(teksti)

    rezultati = []
    for q in rreshtat:
        if len(q) < 2 or q[1] == 'Emri':     # titujt e tabelës
            continue
        telefoni = ''
        if len(q) > 2 and re.fullmatch(r'\+?[\d ]{6,}', q[-1]):
            telefoni = q.pop()
        q += [''] * (4 - len(q))
        rezultati.append({
            'nr': q[0], 'emri': q[1], 'prindi': q[2], 'mbiemri': q[3], 'telefon': telefoni,
        })
    return rezultati


def pastro_rreshtin(r):
    """Rregullon të dhënat e çrregullta të eksportit. Kthen (emri, prindi, mbiemri, telefon, shënim)."""
    emri = ' '.join(r['emri'].split())
    prindi = ' '.join(r['prindi'].split())
    mbiemri = ' '.join(r['mbiemri'].split())
    telefoni = re.sub(r'\s', '', r['telefon'])
    shenim = ''

    if prindi in ('-', '—'):
        prindi = ''
    if mbiemri.lower() == 'empty':
        # Në eksport mbiemri ka rënë te kolona "Prindi"
        mbiemri, prindi = prindi, ''
        shenim = 'Mungonte mbiemri — u mor nga kolona "Prindi"'
    elif not mbiemri:
        shenim = 'Pa mbiemër'
    elif not re.fullmatch(r"[A-Za-zËëÇç'. \-]+", mbiemri) or not re.fullmatch(r"[A-Za-zËëÇç'. \-]*", prindi):
        shenim = 'Emër/mbiemër me shenja të çuditshme — kontrollojeni'

    return emri, prindi, mbiemri, telefoni, shenim


def celesi(emri, prindi, mbiemri):
    return (emri.strip().lower(), prindi.strip().lower(), mbiemri.strip().lower())


def importo(skedari_shtepite, skedari_paguara, viti_paguar, perdoruesi, vetem_prove=False):
    """Regjistron shtëpitë nga PDF-ja e të gjitha shtëpive dhe shënon si të paguara deri `viti_paguar`
    ato që gjenden te PDF-ja e të paguarave. Shtëpitë që ekzistojnë (emër+prind+mbiemër) nuk dyfishohen.
    Me `vetem_prove=True` gjithçka kthehet mbrapsht — vetëm raporti mbetet."""
    from django.db import transaction
    from .models import Shtepia

    rreshtat = lexo_rreshtat(skedari_shtepite)
    if not rreshtat:
        raise ValueError('Në PDF-në e shtëpive nuk u gjet asnjë rresht. A është eksporti "Gjithe qytetaret"?')
    paguara = set()
    if skedari_paguara:
        rreshtat_paguara = lexo_rreshtat(skedari_paguara)
        if not rreshtat_paguara:
            raise ValueError('Në PDF-në e të paguarave nuk u gjet asnjë rresht.')
        paguara = {celesi(*pastro_rreshtin(r)[:3]) for r in rreshtat_paguara}

    raporti = {
        'gjithsej_rreshta': len(rreshtat), 'te_reja': 0, 'ekzistuese': 0, 'shenuara_paguar': 0,
        'pa_paguar': 0, 'dyfishe': [], 'shenime': [], 'paguara_pa_gjetur': [],
        'nr_nga': None, 'nr_deri': None,
    }
    ekzistuese = {
        celesi(e, p, m): pk for pk, e, p, m in
        Shtepia.objects.values_list('pk', 'emri_kryefamiljarit', 'emri_prindit', 'mbiemri_kryefamiljarit')
    }
    numrat = [int(n) for n in Shtepia.objects.values_list('nr_shtepise', flat=True) if n and n.isdigit()]
    nr_radhes = max(numrat, default=0) + 1

    te_reja, pare = [], set()
    with transaction.atomic():
        for r in rreshtat:
            emri, prindi, mbiemri, telefoni, shenim = pastro_rreshtin(r)
            k = celesi(emri, prindi, mbiemri)
            if k in pare:
                raporti['dyfishe'].append(' '.join(filter(None, (emri, prindi, mbiemri))))
                continue
            pare.add(k)
            if shenim:
                raporti['shenime'].append({'nr': r['nr'], 'emri': ' '.join(filter(None, (emri, prindi, mbiemri))), 'shenim': shenim})
            ka_paguar = k in paguara

            if k in ekzistuese:
                raporti['ekzistuese'] += 1
                if ka_paguar:
                    sh = Shtepia.objects.get(pk=ekzistuese[k])
                    if not sh.paguar_deri_viti or sh.paguar_deri_viti < viti_paguar:
                        sh.paguar_deri_viti = viti_paguar
                        sh.save(update_fields=['paguar_deri_viti'])
                    raporti['shenuara_paguar'] += 1
                continue

            te_reja.append(Shtepia(
                nr_shtepise=f"{nr_radhes:04d}",
                emri_kryefamiljarit=emri, emri_prindit=prindi, mbiemri_kryefamiljarit=mbiemri,
                nr_telefoni_kryesor=telefoni,
                viti_fillimit_antaresise=viti_paguar + 1 if ka_paguar else viti_paguar,
                paguar_deri_viti=viti_paguar if ka_paguar else None,
                regjistruar_nga=perdoruesi,
            ))
            nr_radhes += 1
            raporti['shenuara_paguar' if ka_paguar else 'pa_paguar'] += 1

        Shtepia.objects.bulk_create(te_reja, batch_size=200)
        raporti['te_reja'] = len(te_reja)
        if te_reja:
            raporti['nr_nga'], raporti['nr_deri'] = te_reja[0].nr_shtepise, te_reja[-1].nr_shtepise
        raporti['paguara_pa_gjetur'] = sorted(' '.join(filter(None, k)).title() for k in paguara - pare)

        if vetem_prove:
            transaction.set_rollback(True)
    return raporti
