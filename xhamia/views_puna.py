"""
"Puna e përditshme" — faqet e thjeshta si te Masjid Manager, me të cilin stafi është mësuar:
Antarësia (lista e shtëpive me ⊕ për pagesë të shpejtë), Pagesat hyrëse, Pagesat dalëse, Llojet e pagesave.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import evidenca, fletorja, word

WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

from .forms import (
    PagesaAntaresiaForm, PagesaFondiForm, PagesaVarrezaveForm, llojet_hyrese_te_fondit, sugjero_faturen,
)
from .utils import njofto_stafin
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
                if papaguara else 'Asnjë vit pa paguar.')
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
        'url': pagese.get_absolute_url(), 'gabim_emaili': njofto_stafin(pagese, request),
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


# ─── Fletorja e antarësisë ───────────────────────────────────────────────────

@login_required
def puna_fletorja(request):
    """Shkarkimi i fletores (PDF/Excel) dhe krahasimi i një fletoreje PDF me aplikacionin."""
    raporti = None
    if request.method == 'POST':
        if not është_admin(request.user):
            messages.error(request, 'Vetëm administratori mund ta korrigjojë gjendjen.')
            return redirect('puna_fletorja')
        if request.POST.get('veprimi') == 'apliko':
            n = fletorja.apliko(request.POST.getlist('ndrysho'), request.user)
            messages.success(request, f'U korrigjua gjendja e {n} shtëpive sipas fletores.')
            return redirect('puna_fletorja')
        skedari = request.FILES.get('pdf_fletorja')
        if not skedari:
            messages.error(request, 'Zgjidhni fletoren PDF.')
        else:
            try:
                viti_i_pare, rreshtat = fletorja.lexo_fletoren(skedari)
            except Exception as e:
                messages.error(request, f'PDF-ja nuk u lexua: {e}')
            else:
                if not rreshtat:
                    messages.error(request, 'Në PDF nuk u gjet asnjë rresht me Paguar/Borxh.')
                else:
                    raporti = fletorja.krahaso(rreshtat, viti_i_pare)
    viti = timezone.localdate().year
    return render(request, 'puna/fletorja.html', {
        'raporti': raporti, 'eshte_admin': është_admin(request.user),
        'vitet': fletorja.vitet_e_fletores(), 'te_gjitha_vitet': list(range(2015, viti + 6)),
        'nga': viti - 1, 'deri': viti, 'faqja_aktive': 'puna_fletorja',
    })


@login_required
def evidenca_antaresise(request):
    """Evidenca sipas shkronjave: anëtarë / kanë paguar / s'kanë paguar / gratis për vitet e zgjedhura."""
    vitet = evidenca.vitet_nga(request.GET)
    grupet, totali = evidenca.evidenca(vitet)
    if request.GET.get('shkarko') == 'pdf':
        data = timezone.localdate()
        resp = HttpResponse(evidenca.pdf(vitet, grupet, totali, data), content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="evidenca_antaresise_{data.isoformat()}.pdf"'
        return resp
    viti = timezone.localdate().year
    return render(request, 'puna/evidenca.html', {
        'vitet': vitet, 'grupet': grupet, 'totali': totali,
        'te_gjitha_vitet': list(range(2015, viti + 2)), 'faqja_aktive': 'evidenca',
    })


@login_required
def fletorja_shkarko(request, formati):
    filtri = request.GET.get('filtri', '')
    parazgjedhur = fletorja.vitet_e_fletores()
    nga = _viti(request.GET.get('nga'), parazgjedhur[0])
    deri = max(nga, min(_viti(request.GET.get('deri'), parazgjedhur[-1]), nga + 9))
    vitet, rreshtat = fletorja.rreshtat_e_fletores(filtri=filtri, vitet=list(range(nga, deri + 1)))
    data = timezone.localdate()
    emri = f'fletorja_antaresise_{data.isoformat()}'
    if formati == 'excel':
        return _fletorja_excel(emri, vitet, rreshtat, data)
    if formati == 'word':
        resp = HttpResponse(word.fletorja_word(vitet, rreshtat, data, filtri), content_type=WORD)
        resp['Content-Disposition'] = f'attachment; filename="{emri}.docx"'
        return resp
    resp = HttpResponse(fletorja.fletorja_pdf(vitet, rreshtat, data, filtri), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{emri}.pdf"'
    return resp


def _fletorja_excel(emri, vitet, rreshtat, data):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = 'Fletorja'
    ws.append([f'LISTA E ANËTARËVE DHE EVIDENCA E PAGESAVE — {data.strftime("%d.%m.%Y")}'])
    ws['A1'].font = Font(bold=True, size=14, color='1F4E79')
    koka = ['Nr.', 'Nr. Sh.', 'Kryefamiljari', 'Kategoria', f'Borxh të vjetra ({vitet[0] - 1}, {vitet[0] - 2}...)'] \
        + [str(v) for v in vitet] + ['Shënime']
    ws.append(koka)
    for c in ws[2]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='1F4E79')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ngjyrat = {fletorja.PAGUAR: Font(bold=True, color='38761D'), fletorja.BORXH: Font(color='CC5500')}
    for r in rreshtat:
        sh = r['shtepia']
        ws.append([r['nr'], sh.nr_shtepise, sh.emri_i_plote, r['kategoria'], r['borxh_te_vjetra']]
                  + r['statuset'] + [r['shenime']])
        for j, s in enumerate(r['statuset']):
            if s in ngjyrat:
                c = ws.cell(row=ws.max_row, column=6 + j)
                c.font = ngjyrat[s]
                c.alignment = Alignment(horizontal='center')
    for kol, gjeresia in zip('ABCDE', (6, 8, 34, 12, 16)):
        ws.column_dimensions[kol].width = gjeresia
    ws.column_dimensions[ws.cell(row=2, column=len(koka)).column_letter].width = 26
    ws.freeze_panes = 'C3'
    ws.print_title_rows = '2:2'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    buffer = BytesIO()
    wb.save(buffer)
    resp = HttpResponse(buffer.getvalue(),
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{emri}.xlsx"'
    return resp
