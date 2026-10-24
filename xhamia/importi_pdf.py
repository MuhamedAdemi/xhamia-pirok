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


def lexo_borxhlinjte_csv(skedari):
    """CSV me kolonat: emri;prindi;mbiemri;viti_nga[;viti_deri;...]. Kthen {celesi: viti_nga}."""
    import csv
    import io
    teksti = skedari.read()
    if isinstance(teksti, bytes):
        teksti = teksti.decode('utf-8-sig', errors='replace')
    ndares = ';' if teksti.count(';') >= teksti.count(',') else ','
    rezultati = {}
    for i, r in enumerate(csv.DictReader(io.StringIO(teksti), delimiter=ndares)):
        r = {(k or '').strip().lower(): (v or '').strip() for k, v in r.items()}
        try:
            viti_nga = int(r.get('viti_nga', ''))
        except ValueError:
            raise ValueError(f'Rreshti {i + 2} i CSV-së nuk ka "viti_nga" të vlefshëm.')
        rezultati[celesi(r.get('emri', ''), r.get('prindi', ''), r.get('mbiemri', ''))] = viti_nga
    return rezultati


def importo(skedari_shtepite, skedari_paguara, viti_paguar, perdoruesi, vetem_prove=False,
            skedari_borxhlinjte=None, perditeso_ekzistuese=True, skedari_paguara_para=None):
    """Regjistron shtëpitë nga PDF-ja e të gjitha shtëpive dhe u vendos gjendjen e pagesave:

    - te lista e të paguarave (viti V)  → e paguar deri V
    - te CSV-ja e borxhlinjve (viti_nga) → borxh që nga viti_nga
    - të tjerat, kur ka listë të paguarash → borxh vetëm për vitin V; por nëse jepet edhe lista
      e të paguarave të vitit V-1 dhe shtëpia nuk është as aty → borxh për V-1 dhe V

    Shtëpitë që ekzistojnë (emër+prind+mbiemër) nuk dyfishohen; me `perditeso_ekzistuese`
    u përditësohet gjendja. Me `vetem_prove=True` gjithçka kthehet mbrapsht — mbetet vetëm raporti."""
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
    borxhlinjte = lexo_borxhlinjte_csv(skedari_borxhlinjte) if skedari_borxhlinjte else {}
    paguara_para = None
    if skedari_paguara_para:
        paguara_para = {celesi(*pastro_rreshtin(r)[:3]) for r in lexo_rreshtat(skedari_paguara_para)}

    def gjendja(k):
        """(viti_fillimit_antaresise, paguar_deri_viti) ose None kur nuk dihet asgjë."""
        if k in paguara:
            return viti_paguar + 1, viti_paguar
        if k in borxhlinjte:
            return borxhlinjte[k], None
        if paguara:
            if paguara_para is not None and k not in paguara_para:
                return viti_paguar - 1, viti_paguar - 2
            return viti_paguar, viti_paguar - 1
        return None

    raporti = {
        'gjithsej_rreshta': len(rreshtat), 'te_reja': 0, 'ekzistuese': 0, 'perditesuara': 0,
        'shenuara_paguar': 0, 'me_borxh_te_vjeter': 0, 'borxh_vetem_vitin': 0, 'borxh_dy_vite': 0, 'pa_gjendje': 0,
        'dyfishe': [], 'shenime': [], 'paguara_pa_gjetur': [], 'borxhlinj_pa_gjetur': [],
        'konflikte': [], 'nr_nga': None, 'nr_deri': None,
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
            emri_plote = ' '.join(filter(None, (emri, prindi, mbiemri)))
            if k in pare:
                raporti['dyfishe'].append(emri_plote)
                continue
            pare.add(k)
            if shenim:
                raporti['shenime'].append({'nr': r['nr'], 'emri': emri_plote, 'shenim': shenim})
            if k in paguara and k in borxhlinjte:
                raporti['konflikte'].append(emri_plote)

            g = gjendja(k)
            if g is None:
                raporti['pa_gjendje'] += 1
            elif k in paguara:
                raporti['shenuara_paguar'] += 1
            elif k in borxhlinjte:
                raporti['me_borxh_te_vjeter'] += 1
            elif g[0] < viti_paguar:
                raporti['borxh_dy_vite'] += 1
            else:
                raporti['borxh_vetem_vitin'] += 1

            if k in ekzistuese:
                raporti['ekzistuese'] += 1
                if g and perditeso_ekzistuese:
                    raporti['perditesuara'] += Shtepia.objects.filter(pk=ekzistuese[k]).update(
                        viti_fillimit_antaresise=g[0], paguar_deri_viti=g[1],
                    )
                continue

            fillimi, paguar_deri = g or (viti_paguar, None)
            te_reja.append(Shtepia(
                nr_shtepise=f"{nr_radhes:04d}",
                emri_kryefamiljarit=emri, emri_prindit=prindi, mbiemri_kryefamiljarit=mbiemri,
                nr_telefoni_kryesor=telefoni,
                viti_fillimit_antaresise=fillimi, paguar_deri_viti=paguar_deri,
                regjistruar_nga=perdoruesi,
            ))
            nr_radhes += 1

        Shtepia.objects.bulk_create(te_reja, batch_size=200)
        raporti['te_reja'] = len(te_reja)
        if te_reja:
            raporti['nr_nga'], raporti['nr_deri'] = te_reja[0].nr_shtepise, te_reja[-1].nr_shtepise
        raporti['paguara_pa_gjetur'] = sorted(' '.join(filter(None, k)).title() for k in paguara - pare)
        raporti['borxhlinj_pa_gjetur'] = sorted(' '.join(filter(None, k)).title() for k in set(borxhlinjte) - pare)

        if vetem_prove:
            transaction.set_rollback(True)
    return raporti
