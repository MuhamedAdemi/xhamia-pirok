"""
"Puna e përditshme" — faqet e thjeshta si te Masjid Manager, me të cilin stafi është mësuar:
Antarësia (lista e shtëpive me ⊕ për pagesë të shpejtë), Pagesat hyrëse, Pagesat dalëse, Llojet e pagesave.
"""
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    PagesaAntaresiaForm, PagesaFondiForm, PagesaVarrezaveForm, llojet_hyrese_te_fondit, sugjero_faturen,
)
from .models import (
    Harxhimi, KonfigurimiSistemit, KonfigurimiVarrezave, LlojiPageses, PagesaAntaresia, PagesaFondi,
    PagesaVarrezave, Shtepia, formato_shumen,
)
from .views import (
    _shtepite_paguara_ids, _tabela_vjetore, mund_regjistrojë, mund_shikoje, është_admin,
)

ANTARESIA, VARREZAT = 'ANTARESIA', 'VARREZAT'


def _viti(teksti, parazgjedhur):
    try:
        return int(teksti)
    except (TypeError, ValueError):
        return parazgjedhur


def _data(teksti, parazgjedhur):
    try:
        return date.fromisoformat(teksti)
    except (TypeError, ValueError):
        return parazgjedhur


def _totali(pagesat):
    """'770.322 den (12.525,56 €)' — çdo pagesë e kthyer në den dhe €, si te Masjid Manager."""
    kursi = KonfigurimiSistemit.merr().kursi_eur
    mkd = eur = Decimal('0')
    for p in pagesat:
        eur += p.shuma_eur or 0
        mkd += p.shuma_mkd if p.shuma_mkd is not None else (p.shuma_eur or 0) * (p.kursi_denar or kursi)
    return f"{formato_shumen(mkd, 'MKD')} ({formato_shumen(eur.quantize(Decimal('0.01')), 'EUR')})"


# ─── Antarësia ───────────────────────────────────────────────────────────────

@login_required
def puna_antaresia(request):
    sot = timezone.now()
    viti = _viti(request.GET.get('viti'), sot.year)
    aktive = request.GET.get('aktive', '1') != '0'
    shtepite = list(Shtepia.objects.filter(është_aktiv=aktive).order_by('nr_shtepise'))
    paguar = _shtepite_paguara_ids(viti)
    for sh in shtepite:
        sh.ka_paguar = sh.id in paguar
    return render(request, 'puna/antaresia.html', {
        'shtepite': shtepite, 'viti': viti, 'aktive': aktive, 'kerkimi': request.GET.get('q', ''),
        'vitet': list(range(sot.year + 1, 2009, -1)),
        'totali': _totali(PagesaAntaresia.objects.filter(data_pageses__year=viti)),
        'llojet_hyrese': llojet_hyrese_te_fondit(),
        'mund_regjistroje': mund_regjistrojë(request.user), 'eshte_admin': është_admin(request.user),
        'faqja_aktive': 'puna_antaresia',
    })


def _fillestare(shtepi, per):
    """Vlerat e sugjeruara për dritaren e pagesës: fatura e radhës, vitet e papaguara, shuma, paguesi."""
    sot = timezone.now()
    if per in (ANTARESIA, VARREZAT):
        if per == ANTARESIA:
            model, tarifa = PagesaAntaresia, KonfigurimiSistemit.merr().tarifa_antaresise
            te_dhenat = (shtepi.pagesat, shtepi.viti_fillimit_antaresise, shtepi.paguar_deri_viti)
        else:
            model, tarifa = PagesaVarrezave, KonfigurimiVarrezave.merr().shuma_vjetore
            te_dhenat = (shtepi.pagesat_varrezave, shtepi.viti_fillimit_varrezave, shtepi.varrezat_paguar_deri_viti)
        _, borxhi, papaguara = _tabela_vjetore(*te_dhenat, tarifa)
        viti, viti_deri = (papaguara[0], papaguara[-1]) if papaguara else (sot.year + 1, sot.year + 1)
        info = (f"Pa paguar: {', '.join(map(str, papaguara))} — {formato_shumen(borxhi, 'EUR')}"
                if papaguara else f'Çdo vit deri në {sot.year} është i paguar.')
    else:
        model, viti, viti_deri, borxhi, info = PagesaFondi, None, None, None, ''
    blloku, nr = sugjero_faturen(model)
    return {
        'blloku': blloku, 'nr_fatures': nr, 'viti': viti, 'viti_deri': viti_deri,
        'data_pageses': sot.date().isoformat(), 'info': info,
        'shuma_sugjeruar': str(borxhi) if borxhi else '',
        'emri_donatorit': shtepi.emri_kryefamiljarit, 'mbiemri_donatorit': shtepi.mbiemri_kryefamiljarit,
    }


@login_required
def pagese_e_shpejte(request):
    """Dritarja ⊕: GET jep vlerat e sugjeruara, POST e regjistron pagesën me të njëjtat kontrolle si format e plota."""
    if not mund_regjistrojë(request.user):
        return JsonResponse({'ok': False, 'gabimet': ['Nuk keni leje për të regjistruar pagesa.']}, status=403)
    burimi = request.POST if request.method == 'POST' else request.GET
    shtepi = get_object_or_404(Shtepia, pk=_viti(burimi.get('shtepia'), 0))
    per = burimi.get('per') or ANTARESIA
    if request.method != 'POST':
        return JsonResponse(_fillestare(shtepi, per))

    data = request.POST.copy()
    if per == ANTARESIA:
        form = PagesaAntaresiaForm(data)
    elif per == VARREZAT:
        form = PagesaVarrezaveForm(data)
    else:
        # QueryDict.update() shton vlera në vend që t'i zëvendësojë — prandaj caktohen një nga një
        for fusha, vlera in {'lloji': per, 'arsyeja': data.get('shenime', ''), 'shenime': '',
                             'nr_telefoni': shtepi.nr_telefoni_kryesor, 'email_donatorit': shtepi.email}.items():
            data[fusha] = vlera
        form = PagesaFondiForm(data)
    if not form.is_valid():
        gabimet = [f"{form.fields[f].label}: {g}" if f in form.fields and f != '__all__' else g
                   for f, lista in form.errors.items() for g in lista]
        return JsonResponse({'ok': False, 'gabimet': gabimet})
    pagese = form.apliko_shumen(form.save(commit=False))
    if per == ANTARESIA:
        pagese.kategoria_pageses = pagese.shtepia.kategoria
    pagese.arktar = request.user
    pagese.save()
    return JsonResponse({
        'ok': True, 'fatura': pagese.fatura_tekst, 'shuma': pagese.shuma_origjinale,
        'url': pagese.get_absolute_url(),
    })


# ─── Pagesat hyrëse ──────────────────────────────────────────────────────────

def _rresht(p, per, paguesi, shenim, url_fshi):
    return {'p': p, 'per': per, 'paguesi': paguesi, 'shenim': shenim, 'shtepia': getattr(p, 'shtepia', None),
            'url_fshi': url_fshi}


@login_required
def puna_hyrese(request):
    sot = timezone.now().date()
    prej = _data(request.GET.get('prej'), date(sot.year, 1, 1))
    deri = _data(request.GET.get('deri'), sot)
    per = request.GET.get('per', '')
    afati = {'data_pageses__gte': prej, 'data_pageses__lte': deri}
    pagesat, rreshtat = [], []
    if per in ('', ANTARESIA):
        for p in PagesaAntaresia.objects.filter(**afati).select_related('shtepia'):
            pagesat.append(p)
            rreshtat.append(_rresht(p, f'Antarësia {p.vitet_tekst}', p.paguesi or p.shtepia.emri_i_plote, p.shenime,
                                    reverse('fshi_pagese_antaresia', args=[p.pk])))
    if per in ('', VARREZAT):
        for p in PagesaVarrezave.objects.filter(**afati).select_related('shtepia'):
            pagesat.append(p)
            rreshtat.append(_rresht(p, f'Varrezat {p.vitet_tekst}', p.paguesi or p.shtepia.emri_i_plote, p.shenime,
                                    reverse('fshi_pagese_varrezat', args=[p.pk])))
    if per not in (ANTARESIA, VARREZAT):
        fondi = PagesaFondi.objects.filter(**afati).select_related('shtepia')
        if per:
            fondi = fondi.filter(lloji=per)
        for p in fondi:
            pagesat.append(p)
            rreshtat.append(_rresht(p, p.lloji, f'{p.emri_donatorit} {p.mbiemri_donatorit}',
                                    ' — '.join(x for x in (p.arsyeja, p.shenime) if x),
                                    reverse('fshi_pagese_fondi', args=[p.pk])))
    rreshtat.sort(key=lambda r: (r['p'].data_pageses, r['p'].data_regjistrimit), reverse=True)
    return render(request, 'puna/hyrese.html', {
        'rreshtat': rreshtat, 'totali': _totali(pagesat), 'prej': prej, 'deri': deri, 'per': per,
        'llojet': [(ANTARESIA, 'Antarësia'), (VARREZAT, 'Varrezat')] + [(e, e) for e in llojet_hyrese_te_fondit()],
        'mund_regjistroje': mund_regjistrojë(request.user), 'eshte_admin': është_admin(request.user),
        'faqja_aktive': 'puna_hyrese',
    })


# ─── Pagesat dalëse ──────────────────────────────────────────────────────────

@login_required
def puna_dalese(request):
    if not mund_shikoje(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('puna_antaresia')
    sot = timezone.now().date()
    prej = _data(request.GET.get('prej'), date(sot.year, 1, 1))
    deri = _data(request.GET.get('deri'), sot)
    per = request.GET.get('per', '')
    harxhimet = Harxhimi.objects.filter(data_pageses__gte=prej, data_pageses__lte=deri).order_by(
        '-data_pageses', '-data_regjistrimit')
    if per:
        harxhimet = harxhimet.filter(lloji=per)
    harxhimet = list(harxhimet)
    llojet = LlojiPageses.emrat('DALESE')
    llojet += sorted(set(Harxhimi.objects.order_by().values_list('lloji', flat=True).distinct()) - set(llojet))
    return render(request, 'puna/dalese.html', {
        'harxhimet': harxhimet, 'totali': _totali(harxhimet), 'prej': prej, 'deri': deri, 'per': per,
        'llojet': llojet, 'eshte_admin': është_admin(request.user), 'faqja_aktive': 'puna_dalese',
    })


# ─── Llojet e pagesave ───────────────────────────────────────────────────────

@login_required
def puna_llojet(request):
    if not mund_shikoje(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('puna_antaresia')
    return render(request, 'puna/llojet.html', {
        'seksionet': [
            ('Hyrëse', 'HYRESE', LlojiPageses.objects.filter(drejtimi='HYRESE')),
            ('Dalëse', 'DALESE', LlojiPageses.objects.filter(drejtimi='DALESE')),
        ],
        'eshte_admin': është_admin(request.user), 'faqja_aktive': 'puna_llojet',
    })


@login_required
@require_POST
def ndrysho_llojin(request):
    """Shto / riemërto / fshi një lloj. Riemërtimi ndryshon edhe pagesat ekzistuese me atë lloj."""
    if not është_admin(request.user):
        messages.error(request, 'Vetëm admini mund t\'i ndryshojë llojet.')
        return redirect('puna_llojet')
    veprimi = request.POST.get('veprimi')
    emri = ' '.join(request.POST.get('emri', '').split())[:100]
    try:
        with transaction.atomic():
            if veprimi == 'shto' and emri:
                drejtimi = 'DALESE' if request.POST.get('drejtimi') == 'DALESE' else 'HYRESE'
                renditja = LlojiPageses.objects.filter(drejtimi=drejtimi).count()
                LlojiPageses.objects.create(drejtimi=drejtimi, emri=emri, renditja=renditja)
                messages.success(request, f'U shtua lloji «{emri}».')
            elif veprimi == 'riemerto' and emri:
                lloji = get_object_or_404(LlojiPageses, pk=request.POST.get('pk'))
                i_vjetri, lloji.emri = lloji.emri, emri
                lloji.save()
                model = PagesaFondi if lloji.drejtimi == 'HYRESE' else Harxhimi
                n = model.objects.filter(lloji=i_vjetri).update(lloji=emri)
                messages.success(request, f'«{i_vjetri}» u bë «{emri}»' + (f' (edhe te {n} pagesa).' if n else '.'))
            elif veprimi == 'fshi':
                lloji = get_object_or_404(LlojiPageses, pk=request.POST.get('pk'))
                lloji.delete()
                messages.success(request, f'Lloji «{lloji.emri}» u hoq nga lista. Pagesat e vjetra me këtë lloj mbeten.')
    except IntegrityError:
        messages.error(request, f'Lloji «{emri}» ekziston tashmë.')
    return redirect('puna_llojet')
