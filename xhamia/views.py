from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.template.loader import render_to_string
from django.urls import reverse
from io import BytesIO
from xhtml2pdf import pisa
from openpyxl import Workbook
import json
import random
import string
from decimal import Decimal

from .models import (
    ProfilStafi, ProfilShtepi, Kategoria, Shtepia, PagesaAntaresia, PagesaFondi, Harxhimi,
    PagesaVarrezave, KonfigurimiVarrezave, MesazhSMS, KonfigurimiSistemit, gjenero_nr_shtepi,
)
from .forms import (
    LoginForm, StafForm, KategoriaForm, ShtepiaForm,
    PagesaAntaresiaForm, PagesaFondiForm, HarxhimiForm,
    PagesaVarrezaveForm, KonfigurimiVarrezaveForm, KonfigurimiSistemitForm,
    sugjero_faturen,
)
from .utils import dërgo_email_antaresia, dërgo_email_fondi, dërgo_email_varrezat
from . import sms
from .importi_pdf import importo
from . import raporti


def _gjenero_kod():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=9))


def _fshirje_3hap(request, çelësi, fshi_fn, redirect_sukses, info, mesazh_sukses='Të dhënat u fshinë me sukses.'):
    s_kod  = f'fshirje_{çelësi}_kod'
    s_ver  = f'fshirje_{çelësi}_ver'
    s_hapi = f'fshirje_{çelësi}_hapi'
    gabim_kodi = None

    if request.method == 'POST':
        veprimi = request.POST.get('veprimi')
        if veprimi == 'hapi1':
            request.session[s_kod]  = _gjenero_kod()
            request.session[s_hapi] = 2
            return redirect(request.path)
        elif veprimi == 'hapi2':
            kod_sakt  = request.session.get(s_kod, '')
            kod_hyres = request.POST.get('kodi', '').strip().upper()
            if kod_hyres == kod_sakt:
                request.session[s_ver]  = True
                request.session[s_hapi] = 3
                return redirect(request.path)
            gabim_kodi = 'Kodi i shënuar është i gabuar. Provoni përsëri.'
        elif veprimi == 'hapi3':
            if request.session.get(s_ver):
                for k in (s_kod, s_ver, s_hapi):
                    request.session.pop(k, None)
                fshi_fn()
                messages.success(request, mesazh_sukses)
                return redirect(redirect_sukses)

    hapi = int(request.session.get(s_hapi, 1))
    kod  = request.session.get(s_kod)
    return render(request, 'fshirje/konfirmo.html', {
        'hapi': hapi, 'kodi': kod, 'info': info,
        'gabim_kodi': gabim_kodi, 'step_list': [1, 2, 3],
    })


def është_admin(user):
    try:
        return user.profili.rol == 'ADMIN'
    except Exception:
        return False


def mund_regjistrojë(user):
    try:
        p = user.profili
        return p.rol == 'ADMIN' or p.mund_regjistrojë_pagesa
    except Exception:
        return False


def _ids_qe_mbulojne(model, viti):
    """ID-të e shtëpive që kanë një pagesë që e mbulon vitin (një faturë mund të mbulojë shumë vite)."""
    return set(model.objects.filter(viti__lte=viti, viti_deri__gte=viti).values_list('shtepia_id', flat=True))


def _tabela_vjetore(pagesat, viti_fillimit, paguar_deri, shuma_vjetore):
    """Gjendja vit për vit e një shtëpie (antarësi ose varreza).

    Një vit është i paguar nëse e mbulon një pagesë ose është ≤ paguar_deri (historik).
    Borxhi llogaritet vetëm për vitet deri te ky vit, me shumën vjetore (nëse dihet).
    Kthen (tabela, borxhi_total, vitet_papaguara)."""
    viti_aktual = timezone.now().year
    pagesat = list(pagesat.values('viti', 'viti_deri', 'shuma_paguar'))
    for pg in pagesat:
        pg['viti_deri'] = pg['viti_deri'] or pg['viti']
    viti_nga = min([viti_fillimit] + [pg['viti'] for pg in pagesat])
    viti_deri = max([viti_aktual] + [pg['viti_deri'] for pg in pagesat])
    shuma_vjetore = shuma_vjetore or Decimal('0')

    tabela, borxhi_total, papaguara = {}, Decimal('0'), []
    for v in range(viti_nga, viti_deri + 1):
        mbulojne = [pg for pg in pagesat if pg['viti'] <= v <= pg['viti_deri']]
        if paguar_deri and v <= paguar_deri:
            tabela[v] = {'shuma_paguar': shuma_vjetore, 'ka_paguar': True, 'borxhi': Decimal('0'), 'historike': True}
        elif mbulojne:
            shuma = sum(pg['shuma_paguar'] / (pg['viti_deri'] - pg['viti'] + 1) for pg in mbulojne)
            tabela[v] = {'shuma_paguar': shuma.quantize(Decimal('0.01')), 'ka_paguar': True,
                         'borxhi': Decimal('0'), 'historike': False}
        elif viti_fillimit <= v <= viti_aktual:
            tabela[v] = {'shuma_paguar': Decimal('0'), 'ka_paguar': False, 'borxhi': shuma_vjetore, 'historike': False}
            borxhi_total += shuma_vjetore
            papaguara.append(v)
    return tabela, borxhi_total, papaguara


def _shtepite_paguara_ids(viti):
    """ID-të e shtëpive që e kanë paguar antarësinë e vitit — pagesa reale + shënimi historik (paguar_deri_viti)."""
    actual = _ids_qe_mbulojne(PagesaAntaresia, viti)
    historike = set(Shtepia.objects.filter(
        paguar_deri_viti__gte=viti, është_aktiv=True
    ).values_list('id', flat=True))
    return actual | historike


def _shtepite_paguara_varrezat_ids(viti):
    """ID-të e shtëpive që e kanë paguar varrezat e vitit — pagesa reale + shënimi historik."""
    actual = _ids_qe_mbulojne(PagesaVarrezave, viti)
    historike = set(Shtepia.objects.filter(
        varrezat_paguar_deri_viti__gte=viti, është_aktiv=True
    ).values_list('id', flat=True))
    return actual | historike


def _pergjigje_excel(emri_skedarit, koka, rreshtat):
    wb = Workbook()
    ws = wb.active
    ws.append(koka)
    for r in rreshtat:
        ws.append(r)
    buffer = BytesIO()
    wb.save(buffer)
    resp = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = f'attachment; filename="{emri_skedarit}"'
    return resp


# ─── Auth ───────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data['username'],
            password=form.cleaned_data['password']
        )
        if user:
            try:
                if not user.profili.është_aktiv:
                    messages.error(request, 'Llogaria juaj është çaktivizuar.')
                    return render(request, 'auth/login.html', {'form': form})
            except Exception:
                pass
            login(request, user)
            if hasattr(user, 'profili_shtepi'):
                return redirect('portali_shtepi')
            return redirect('dashboard')
        messages.error(request, 'Emri i përdoruesit ose fjalëkalimi është i gabuar.')
    return render(request, 'auth/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


def redirect_dashboard(request):
    return redirect('dashboard')


# ─── Dashboard ──────────────────────────────────────────────────────────────

@login_required
def dashboard_antaresia(request):
    viti_zgjedhur = int(request.GET.get('viti', timezone.now().year))
    vitit_lista = list(range(2020, timezone.now().year + 2))

    total_shtepite = Shtepia.objects.filter(është_aktiv=True).count()

    # Shtëpitë që kanë paguar: actual records + historike (paguar_deri_viti)
    paguar_ids = _shtepite_paguara_ids(viti_zgjedhur)
    kane_paguar = len(paguar_ids)
    nuk_kane_paguar = total_shtepite - kane_paguar

    total_mbledhur = PagesaAntaresia.objects.filter(data_pageses__year=viti_zgjedhur).aggregate(
        s=Sum('shuma_paguar')
    )['s'] or 0

    total_harxhime = Harxhimi.objects.filter(
        viti=viti_zgjedhur, burimi='ANTARESIA'
    ).aggregate(s=Sum('shuma_eur'))['s'] or 0
    bilanci_antaresia = total_mbledhur - total_harxhime
    harxhimet_e_fundit = Harxhimi.objects.select_related('stafi').filter(
        viti=viti_zgjedhur, burimi='ANTARESIA'
    ).order_by('-data_pageses')[:6]

    # Pagesat sipas muajit (për grafik)
    pagesat_mujore = []
    muajt_etiketat = ['Jan', 'Shk', 'Mar', 'Pri', 'Maj', 'Qer', 'Kor', 'Gus', 'Sht', 'Tet', 'Nën', 'Dhj']
    for m in range(1, 13):
        shuma = PagesaAntaresia.objects.filter(
            data_pageses__year=viti_zgjedhur, data_pageses__month=m
        ).aggregate(s=Sum('shuma_paguar'))['s'] or 0
        pagesat_mujore.append(float(shuma))

    # Sipas kategorisë
    sipas_kategorise = []
    for kat in Kategoria.objects.filter(është_aktiv=True):
        cnt = Shtepia.objects.filter(id__in=paguar_ids, kategoria=kat).count()
        if cnt > 0:
            sipas_kategorise.append({'emri': kat.emri, 'count': cnt})

    # Pagesat e fundit
    pagesat_e_fundit = PagesaAntaresia.objects.select_related('shtepia', 'arktar').order_by('-data_regjistrimit')[:10]

    # Shtëpitë pa pagesë (as actual as historical)
    shtepite_pa_pagese = Shtepia.objects.filter(
        është_aktiv=True
    ).exclude(
        id__in=paguar_ids
    ).select_related('kategoria')[:20]

    # Të dhënat 10-vjeçare për grafiket (shtëpi që kanë paguar = actual + historike)
    viti_aktual = timezone.now().year
    data_vitet = []
    for v in range(viti_aktual - 9, viti_aktual + 1):
        shuma_v = PagesaAntaresia.objects.filter(data_pageses__year=v).aggregate(s=Sum('shuma_paguar'))['s'] or 0
        act_v = _ids_qe_mbulojne(PagesaAntaresia, v)
        hist_v = set(Shtepia.objects.filter(
            paguar_deri_viti__gte=v, viti_fillimit_antaresise__lte=v, është_aktiv=True
        ).values_list('id', flat=True))
        data_vitet.append({'viti': v, 'shuma': float(shuma_v), 'nr': len(act_v | hist_v)})

    konteksti = {
        'viti_zgjedhur': viti_zgjedhur,
        'vitit_lista': vitit_lista,
        'total_shtepite': total_shtepite,
        'kane_paguar': kane_paguar,
        'nuk_kane_paguar': nuk_kane_paguar,
        'total_mbledhur': total_mbledhur,
        'pagesat_mujore_json': json.dumps(pagesat_mujore),
        'muajt_etiketat_json': json.dumps(muajt_etiketat),
        'sipas_kategorise_json': json.dumps(sipas_kategorise),
        'pagesat_e_fundit': pagesat_e_fundit,
        'shtepite_pa_pagese': shtepite_pa_pagese,
        'data_vitet_json': json.dumps(data_vitet),
        'total_harxhime': total_harxhime,
        'bilanci_antaresia': bilanci_antaresia,
        'harxhimet_e_fundit': harxhimet_e_fundit,
        'faqja_aktive': 'dashboard',
    }
    return render(request, 'dashboard/antaresia.html', konteksti)


@login_required
def dashboard_fondi(request):
    viti_zgjedhur = int(request.GET.get('viti', timezone.now().year))
    vitit_lista = list(range(2020, timezone.now().year + 2))

    total_fondi = PagesaFondi.objects.filter(
        data_pageses__year=viti_zgjedhur
    ).aggregate(s=Sum('shuma'))['s'] or 0

    total_donator = PagesaFondi.objects.filter(
        data_pageses__year=viti_zgjedhur
    ).count()

    pagesat_mujore = []
    muajt_etiketat = ['Jan', 'Shk', 'Mar', 'Pri', 'Maj', 'Qer', 'Kor', 'Gus', 'Sht', 'Tet', 'Nën', 'Dhj']
    for m in range(1, 13):
        shuma = PagesaFondi.objects.filter(
            data_pageses__year=viti_zgjedhur, data_pageses__month=m
        ).aggregate(s=Sum('shuma'))['s'] or 0
        pagesat_mujore.append(float(shuma))

    # Krahasimi i viteve
    krahasimi_viteve = []
    for v in range(viti_zgjedhur - 2, viti_zgjedhur + 1):
        shuma = PagesaFondi.objects.filter(data_pageses__year=v).aggregate(s=Sum('shuma'))['s'] or 0
        krahasimi_viteve.append({'viti': v, 'shuma': float(shuma)})

    pagesat_e_fundit = PagesaFondi.objects.select_related('arktar').order_by('-data_pageses')[:10]

    top_donator = PagesaFondi.objects.filter(
        data_pageses__year=viti_zgjedhur
    ).values('emri_donatorit', 'mbiemri_donatorit').annotate(
        total=Sum('shuma')
    ).order_by('-total')[:5]

    total_dhurata = PagesaFondi.objects.filter(
        data_pageses__year=viti_zgjedhur, lloji='DHURATE'
    ).aggregate(s=Sum('shuma'))['s'] or 0
    total_aktivitete = PagesaFondi.objects.filter(
        data_pageses__year=viti_zgjedhur, lloji='AKTIVITET'
    ).aggregate(s=Sum('shuma'))['s'] or 0

    konteksti = {
        'viti_zgjedhur': viti_zgjedhur,
        'vitit_lista': vitit_lista,
        'total_fondi': total_fondi,
        'total_donator': total_donator,
        'total_dhurata': total_dhurata,
        'total_aktivitete': total_aktivitete,
        'pagesat_mujore_json': json.dumps(pagesat_mujore),
        'muajt_etiketat_json': json.dumps(muajt_etiketat),
        'krahasimi_viteve_json': json.dumps(krahasimi_viteve),
        'pagesat_e_fundit': pagesat_e_fundit,
        'top_donator': top_donator,
        'faqja_aktive': 'dashboard_fondi',
    }
    return render(request, 'dashboard/fondi.html', konteksti)


@login_required
def dashboard_varrezat(request):
    viti_zgjedhur = int(request.GET.get('viti', timezone.now().year))
    vitit_lista = list(range(2020, timezone.now().year + 2))

    total_shtepite = Shtepia.objects.filter(është_aktiv=True).count()

    paguar_ids = _shtepite_paguara_varrezat_ids(viti_zgjedhur)
    kane_paguar = len(paguar_ids)
    nuk_kane_paguar = total_shtepite - kane_paguar

    total_mbledhur = PagesaVarrezave.objects.filter(data_pageses__year=viti_zgjedhur).aggregate(
        s=Sum('shuma_paguar')
    )['s'] or 0

    total_harxhime = Harxhimi.objects.filter(
        viti=viti_zgjedhur, burimi='VARREZAT'
    ).aggregate(s=Sum('shuma_eur'))['s'] or 0
    bilanci = total_mbledhur - total_harxhime
    harxhimet_e_fundit = Harxhimi.objects.select_related('stafi').filter(
        viti=viti_zgjedhur, burimi='VARREZAT'
    ).order_by('-data_pageses')[:6]

    pagesat_e_fundit = PagesaVarrezave.objects.select_related('shtepia', 'arktar').order_by('-data_regjistrimit')[:10]

    shtepite_pa_pagese = Shtepia.objects.filter(
        është_aktiv=True
    ).exclude(
        id__in=paguar_ids
    ).select_related('kategoria')[:20]

    konfigurimi = KonfigurimiVarrezave.merr()

    konteksti = {
        'viti_zgjedhur': viti_zgjedhur,
        'vitit_lista': vitit_lista,
        'total_shtepite': total_shtepite,
        'kane_paguar': kane_paguar,
        'nuk_kane_paguar': nuk_kane_paguar,
        'total_mbledhur': total_mbledhur,
        'total_harxhime': total_harxhime,
        'bilanci': bilanci,
        'harxhimet_e_fundit': harxhimet_e_fundit,
        'pagesat_e_fundit': pagesat_e_fundit,
        'shtepite_pa_pagese': shtepite_pa_pagese,
        'konfigurimi': konfigurimi,
        'faqja_aktive': 'dashboard_varrezat',
    }
    return render(request, 'dashboard/varrezat.html', konteksti)


@login_required
def regjistri(request):
    """Regjistri i pagesave si fletorja: sipas radhës, me totale për bllok, muaj, 3/6 muaj dhe vit."""
    lloji = request.GET.get('lloji', 'antaresia')
    if lloji not in raporti.LLOJET:
        lloji = 'antaresia'
    periudha = request.GET.get('periudha', 'vit')
    if periudha not in dict(raporti.PERIUDHAT):
        periudha = 'vit'
    try:
        viti = int(request.GET.get('viti', timezone.now().year))
    except ValueError:
        viti = timezone.now().year

    if request.GET.get('eksporto') == 'excel':
        resp = HttpResponse(
            raporti.regjistri_excel(lloji, viti, periudha),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp['Content-Disposition'] = f'attachment; filename="regjistri_{lloji}_{viti}_{periudha}.xlsx"'
        return resp

    rreshtat, gjithsej = raporti.ndertoj_regjistrin(lloji, viti, periudha)
    return render(request, 'dashboard/regjistri.html', {
        'rreshtat': rreshtat, 'gjithsej': gjithsej,
        'lloji': lloji, 'llojet': [(k, v[0]) for k, v in raporti.LLOJET.items()],
        'periudha': periudha, 'periudhat': raporti.PERIUDHAT,
        'viti': viti, 'vitit_lista': list(range(2020, timezone.now().year + 2)),
        'me_vite': lloji != 'fondi',
        'faqja_aktive': 'regjistri',
    })


# ─── Shtëpitë ───────────────────────────────────────────────────────────────

@login_required
def lista_shtepive(request):
    kerkimi = request.GET.get('kerkimi', '')
    kategoria_id = request.GET.get('kategoria', '')
    statusi = request.GET.get('statusi', 'aktive')
    viti = request.GET.get('viti', '')
    pagesa_statusi = request.GET.get('pagesa_statusi', '')

    shtepite = Shtepia.objects.select_related('kategoria', 'regjistruar_nga')

    if statusi == 'aktive':
        shtepite = shtepite.filter(është_aktiv=True)
    elif statusi == 'joaktive':
        shtepite = shtepite.filter(është_aktiv=False)

    if kerkimi:
        shtepite = shtepite.filter(
            Q(nr_shtepise__icontains=kerkimi) |
            Q(emri_kryefamiljarit__icontains=kerkimi) |
            Q(emri_prindit__icontains=kerkimi) |
            Q(mbiemri_kryefamiljarit__icontains=kerkimi) |
            Q(nr_telefoni_kryesor__icontains=kerkimi) |
            Q(email__icontains=kerkimi)
        )

    if kategoria_id:
        shtepite = shtepite.filter(kategoria_id=kategoria_id)

    viti_status = int(viti) if viti else timezone.now().year
    paguar_ids = _shtepite_paguara_ids(viti_status)

    if pagesa_statusi == 'papaguar':
        shtepite = shtepite.exclude(id__in=paguar_ids)
    elif pagesa_statusi == 'paguar':
        shtepite = shtepite.filter(id__in=paguar_ids)

    if request.GET.get('eksporto') == 'excel':
        koka = [
            'Nr.', 'Emri', 'Emri i Prindit', 'Mbiemri', 'Anëtarë', 'Kategoria', 'Telefoni', 'Email', 'Statusi',
            f'Ka Paguar ({viti_status})',
        ]
        rreshtat = [
            [
                sh.nr_shtepise, sh.emri_kryefamiljarit, sh.emri_prindit, sh.mbiemri_kryefamiljarit,
                sh.nr_antareve_familjes, sh.kategoria.emri if sh.kategoria else '', sh.nr_telefoni_kryesor,
                sh.email, 'Aktive' if sh.është_aktiv else 'Joaktive',
                'Po' if sh.id in paguar_ids else 'Jo',
            ]
            for sh in shtepite
        ]
        return _pergjigje_excel(f'shtepite_{timezone.now().date()}.xlsx', koka, rreshtat)

    total_ne_liste = shtepite.count()
    kane_paguar_ne_liste = sum(1 for sh in shtepite if sh.id in paguar_ids)

    konteksti = {
        'shtepite': shtepite,
        'kategoritë': Kategoria.objects.filter(është_aktiv=True),
        'kerkimi': kerkimi,
        'kategoria_id': kategoria_id,
        'statusi': statusi,
        'viti': viti,
        'viti_status': viti_status,
        'paguar_ids': paguar_ids,
        'total_ne_liste': total_ne_liste,
        'kane_paguar_ne_liste': kane_paguar_ne_liste,
        'nuk_kane_paguar_ne_liste': total_ne_liste - kane_paguar_ne_liste,
        'pagesa_statusi': pagesa_statusi,
        'vitit_lista': list(range(2020, timezone.now().year + 2)),
        'faqja_aktive': 'shtepite',
    }
    return render(request, 'shtepite/lista.html', konteksti)


@login_required
def shto_shtepi(request):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje për këtë veprim.')
        return redirect('lista_shtepive')
    nr_i_ri = gjenero_nr_shtepi()
    if request.method == 'POST':
        form = ShtepiaForm(request.POST)
    else:
        form = ShtepiaForm(initial={'nr_shtepise': nr_i_ri})
    if request.method == 'POST' and form.is_valid():
        shtepi = form.save(commit=False)
        shtepi.regjistruar_nga = request.user
        shtepi.save()
        messages.success(request, f'Shtëpia #{shtepi.nr_shtepise} u regjistrua me sukses.')
        return redirect('detaje_shtepia', pk=shtepi.pk)
    return render(request, 'shtepite/forma.html', {
        'form': form, 'titulli': 'Shto Shtëpi të Re',
        'nr_i_ri': nr_i_ri, 'faqja_aktive': 'shtepite',
    })


@login_required
def importo_shtepite(request):
    """Regjistron shtëpitë nga eksporti PDF i "Masjid Manager" (lista e të gjithave + lista e të paguarave)."""
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_shtepive')

    raporti, vetem_prove = None, False
    viti_paguar = timezone.now().year
    if request.method == 'POST':
        vetem_prove = request.POST.get('veprimi') != 'importo'
        try:
            viti_paguar = int(request.POST.get('viti_paguar') or viti_paguar)
        except ValueError:
            pass
        pdf_shtepite = request.FILES.get('pdf_shtepite')
        if not pdf_shtepite:
            messages.error(request, 'Zgjidhni PDF-në me të gjitha shtëpitë.')
        else:
            try:
                raporti = importo(
                    pdf_shtepite, request.FILES.get('pdf_paguara'), viti_paguar, request.user, vetem_prove,
                    skedari_borxhlinjte=request.FILES.get('csv_borxhlinjte'),
                    perditeso_ekzistuese=bool(request.POST.get('perditeso_ekzistuese')),
                    skedari_paguara_para=request.FILES.get('pdf_paguara_para'),
                )
            except Exception as e:
                messages.error(request, f'PDF-ja nuk u lexua: {e}')
            else:
                if not vetem_prove:
                    messages.success(request, f"U regjistruan {raporti['te_reja']} shtëpi të reja "
                                              f"dhe u përditësua gjendja e {raporti['perditesuara']} ekzistuese.")

    return render(request, 'shtepite/importo.html', {
        'raporti': raporti, 'vetem_prove': vetem_prove, 'viti_paguar': viti_paguar,
        'faqja_aktive': 'shtepite',
    })


@login_required
def detaje_shtepia(request, pk):
    shtepi = get_object_or_404(Shtepia, pk=pk)
    pagesat = shtepi.pagesat.select_related('arktar').order_by('-viti', '-data_pageses')
    pagesat_varrezave = shtepi.pagesat_varrezave.select_related('arktar').order_by('-viti', '-data_pageses')

    viti_aktual = timezone.now().year
    pagesat_per_vit, borxhi_total, papaguara = _tabela_vjetore(
        shtepi.pagesat, shtepi.viti_fillimit_antaresise, shtepi.paguar_deri_viti,
        shtepi.kategoria.shuma_vjetore if shtepi.kategoria else None,
    )
    pagesat_per_vit_varrezat, borxhi_total_varrezat, papaguara_varrezat = _tabela_vjetore(
        shtepi.pagesat_varrezave, shtepi.viti_fillimit_varrezave, shtepi.varrezat_paguar_deri_viti,
        KonfigurimiVarrezave.merr().shuma_vjetore,
    )

    vitit_lista = list(range(2000, viti_aktual + 2))

    return render(request, 'shtepite/detaje.html', {
        'shtepi': shtepi,
        'pagesat': pagesat,
        'pagesat_per_vit': pagesat_per_vit,
        'borxhi_total': borxhi_total,
        'pagesat_varrezave': pagesat_varrezave,
        'pagesat_per_vit_varrezat': pagesat_per_vit_varrezat,
        'borxhi_total_varrezat': borxhi_total_varrezat,
        'nr_papaguara': len(papaguara),
        'nr_papaguara_varrezat': len(papaguara_varrezat),
        'viti_aktual': viti_aktual,
        'vitit_lista': vitit_lista,
        'faqja_aktive': 'shtepite',
    })


@login_required
def permbyll_antaresia(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_shtepive')
    shtepi = get_object_or_404(Shtepia, pk=pk)
    if request.method == 'POST':
        try:
            viti_i_ri = int(request.POST.get('viti_i_ri', timezone.now().year))
            shtepi.paguar_deri_viti = viti_i_ri
            shtepi.save()
            messages.success(request, f'Shtëpia #{shtepi.nr_shtepise}: shënuar si e paguar deri viti {viti_i_ri}.')
        except (ValueError, TypeError):
            messages.error(request, 'Viti i zgjedhur nuk është i vlefshëm.')
    return redirect('detaje_shtepia', pk=pk)


@login_required
def permbyll_varrezat(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_shtepive')
    shtepi = get_object_or_404(Shtepia, pk=pk)
    if request.method == 'POST':
        try:
            viti_i_ri = int(request.POST.get('viti_i_ri', timezone.now().year))
            shtepi.varrezat_paguar_deri_viti = viti_i_ri
            shtepi.save()
            messages.success(request, f'Shtëpia #{shtepi.nr_shtepise}: varrezat shënuar si të paguara deri viti {viti_i_ri}.')
        except (ValueError, TypeError):
            messages.error(request, 'Viti i zgjedhur nuk është i vlefshëm.')
    return redirect('detaje_shtepia', pk=pk)


@login_required
def edito_shtepi(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje për këtë veprim.')
        return redirect('lista_shtepive')
    shtepi = get_object_or_404(Shtepia, pk=pk)
    form = ShtepiaForm(request.POST or None, instance=shtepi)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Shtëpia u përditësua me sukses.')
        return redirect('detaje_shtepia', pk=shtepi.pk)
    return render(request, 'shtepite/forma.html', {
        'form': form, 'titulli': f'Edito Shtëpinë #{shtepi.nr_shtepise}',
        'shtepi': shtepi, 'faqja_aktive': 'shtepite'
    })


# ─── Pagesat Antarësia ───────────────────────────────────────────────────────

@login_required
def lista_pagesa_antaresia(request):
    viti = request.GET.get('viti', str(timezone.now().year))
    kerkimi = request.GET.get('kerkimi', '')

    pagesat = PagesaAntaresia.objects.select_related('shtepia', 'arktar')
    if viti:
        pagesat = pagesat.filter(viti__lte=viti, viti_deri__gte=viti)
    if kerkimi:
        pagesat = pagesat.filter(
            Q(nr_fatures__icontains=kerkimi) |
            Q(blloku__icontains=kerkimi) |
            Q(shtepia__emri_kryefamiljarit__icontains=kerkimi) |
            Q(shtepia__emri_prindit__icontains=kerkimi) |
            Q(shtepia__mbiemri_kryefamiljarit__icontains=kerkimi) |
            Q(shtepia__nr_shtepise__icontains=kerkimi)
        )

    if request.GET.get('eksporto') == 'excel':
        koka = ['Nr. Faturës', 'Shtëpia', 'Shuma (€)', 'Shuma (MKD)', 'Paguar në', 'Vitet', 'Data', 'Arktar']
        rreshtat = [
            [
                p.fatura_tekst, f'#{p.shtepia.nr_shtepise} {p.shtepia.emri_i_plote}',
                float(p.shuma_paguar), float(p.shuma_mkd or 0), p.monedha,
                p.vitet_tekst, p.data_pageses.strftime('%d.%m.%Y'), p.arktar.get_full_name(),
            ]
            for p in pagesat
        ]
        return _pergjigje_excel(f'pagesat_antaresia_{timezone.now().date()}.xlsx', koka, rreshtat)

    return render(request, 'pagesat/antaresia/lista.html', {
        'pagesat': pagesat, 'viti': viti, 'kerkimi': kerkimi,
        'vitit_lista': list(range(2000, timezone.now().year + 3)),
        'faqja_aktive': 'pagesat_antaresia',
    })


# Shumat e zakonshme vjetore të antarësisë, në € dhe në den (shpesh pranohet edhe vlera më e rrumbullakët)
VLERAT_SHPEJTA_ANTARESIA = [
    (70, 'EUR'), (4300, 'MKD'), (4000, 'MKD'),
    (80, 'EUR'), (5000, 'MKD'),
    (100, 'EUR'), (6000, 'MKD'),
    (120, 'EUR'), (7300, 'MKD'), (7000, 'MKD'),
]


def _initial_pagese(request, model, te_dhenat_e_shtepise=None):
    """Vlerat fillestare: nr. i radhës nga blloku dhe — kur vjen nga faqja e shtëpisë —
    vitet e papaguara (nga viti i parë i papaguar deri sot)."""
    blloku, nr = sugjero_faturen(model)
    initial = {'blloku': blloku, 'nr_fatures': nr, 'data_pageses': timezone.now().date()}
    shtepi_id = request.GET.get('shtepi')
    if shtepi_id and te_dhenat_e_shtepise:
        shtepi = Shtepia.objects.filter(pk=shtepi_id).first()
        if shtepi:
            initial['shtepia'] = shtepi
            _, _, papaguara = _tabela_vjetore(*te_dhenat_e_shtepise(shtepi), None)
            if papaguara:
                initial['viti'], initial['viti_deri'] = papaguara[0], papaguara[-1]
    return initial


@login_required
def shto_pagese_antaresia(request):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje për të regjistruar pagesa.')
        return redirect('lista_pagesa_antaresia')
    form = PagesaAntaresiaForm(request.POST or None, initial=_initial_pagese(
        request, PagesaAntaresia, lambda sh: (sh.pagesat, sh.viti_fillimit_antaresise, sh.paguar_deri_viti),
    ))
    if request.method == 'POST' and form.is_valid():
        pagese = form.apliko_shumen(form.save(commit=False))
        pagese.kategoria_pageses = pagese.shtepia.kategoria
        pagese.arktar = request.user
        pagese.save()
        messages.success(request, f'Pagesa {pagese.fatura_tekst} u regjistrua me sukses.')
        return redirect('detaje_pagesa_antaresia', pk=pagese.pk)
    return render(request, 'pagesat/antaresia/forma.html', {
        'form': form, 'titulli': 'Regjistro Pagesë Antarësia', 'faqja_aktive': 'pagesat_antaresia',
        'vlerat_shpejta': VLERAT_SHPEJTA_ANTARESIA,
    })


@login_required
def detaje_pagesa_antaresia(request, pk):
    pagese = get_object_or_404(PagesaAntaresia, pk=pk)
    return render(request, 'pagesat/antaresia/detaje.html', {
        'pagese': pagese, 'faqja_aktive': 'pagesat_antaresia'
    })


@login_required
def fatura_antaresia_pdf(request, pk):
    pagese = get_object_or_404(PagesaAntaresia, pk=pk)
    html = render_to_string('pagesat/antaresia/fatura_pdf.html', {'pagese': pagese})
    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="fatura-{pagese.nr_fatures}.pdf"'
    return response


# ─── Pagesat Fondi ───────────────────────────────────────────────────────────

@login_required
def lista_pagesa_fondi(request):
    viti = request.GET.get('viti', timezone.now().year)
    kerkimi = request.GET.get('kerkimi', '')
    lloji = request.GET.get('lloji', '')
    pagesat = PagesaFondi.objects.select_related('arktar')
    if viti:
        pagesat = pagesat.filter(data_pageses__year=viti)
    if kerkimi:
        pagesat = pagesat.filter(
            Q(nr_fatures__icontains=kerkimi) |
            Q(blloku__icontains=kerkimi) |
            Q(emri_donatorit__icontains=kerkimi) |
            Q(mbiemri_donatorit__icontains=kerkimi) |
            Q(arsyeja__icontains=kerkimi)
        )
    if lloji:
        pagesat = pagesat.filter(lloji=lloji)

    if request.GET.get('eksporto') == 'excel':
        koka = ['Nr. Faturës', 'Lloji', 'Emri', 'Mbiemri', 'Arsyeja', 'Shuma (€)', 'Data', 'Arktar']
        rreshtat = [
            [
                p.fatura_tekst, p.get_lloji_display(), p.emri_donatorit, p.mbiemri_donatorit,
                p.arsyeja, float(p.shuma), p.data_pageses.strftime('%d.%m.%Y'), p.arktar.get_full_name(),
            ]
            for p in pagesat
        ]
        return _pergjigje_excel(f'pagesat_fondi_{timezone.now().date()}.xlsx', koka, rreshtat)

    return render(request, 'pagesat/fondi/lista.html', {
        'pagesat': pagesat, 'viti': viti, 'kerkimi': kerkimi, 'lloji': lloji,
        'lloji_choices': PagesaFondi.LLOJI_CHOICES,
        'vitit_lista': list(range(2020, timezone.now().year + 2)),
        'faqja_aktive': 'pagesat_fondi',
    })


@login_required
def shto_pagese_fondi(request):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje për të regjistruar pagesa.')
        return redirect('lista_pagesa_fondi')
    form = PagesaFondiForm(request.POST or None, initial=_initial_pagese(request, PagesaFondi))
    if request.method == 'POST' and form.is_valid():
        pagese = form.apliko_shumen(form.save(commit=False))
        pagese.arktar = request.user
        pagese.save()
        messages.success(request, f'Pagesa {pagese.fatura_tekst} u regjistrua me sukses.')
        return redirect('detaje_pagesa_fondi', pk=pagese.pk)
    return render(request, 'pagesat/fondi/forma.html', {
        'form': form, 'titulli': 'Regjistro Pagesë Fondi', 'faqja_aktive': 'pagesat_fondi'
    })


@login_required
def detaje_pagesa_fondi(request, pk):
    pagese = get_object_or_404(PagesaFondi, pk=pk)
    return render(request, 'pagesat/fondi/detaje.html', {
        'pagese': pagese, 'faqja_aktive': 'pagesat_fondi'
    })


@login_required
def fatura_fondi_pdf(request, pk):
    pagese = get_object_or_404(PagesaFondi, pk=pk)
    html = render_to_string('pagesat/fondi/fatura_pdf.html', {'pagese': pagese})
    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="fatura-{pagese.nr_fatures}.pdf"'
    return response


# ─── Pagesat Varrezave ───────────────────────────────────────────────────────

@login_required
def lista_pagesa_varrezave(request):
    viti = request.GET.get('viti', str(timezone.now().year))
    kerkimi = request.GET.get('kerkimi', '')

    pagesat = PagesaVarrezave.objects.select_related('shtepia', 'arktar')
    if viti:
        pagesat = pagesat.filter(viti__lte=viti, viti_deri__gte=viti)
    if kerkimi:
        pagesat = pagesat.filter(
            Q(nr_fatures__icontains=kerkimi) |
            Q(blloku__icontains=kerkimi) |
            Q(shtepia__emri_kryefamiljarit__icontains=kerkimi) |
            Q(shtepia__emri_prindit__icontains=kerkimi) |
            Q(shtepia__mbiemri_kryefamiljarit__icontains=kerkimi) |
            Q(shtepia__nr_shtepise__icontains=kerkimi)
        )

    if request.GET.get('eksporto') == 'excel':
        koka = ['Nr. Faturës', 'Shtëpia', 'Shuma (€)', 'Shuma (MKD)', 'Paguar në', 'Vitet', 'Data', 'Arktar']
        rreshtat = [
            [
                p.fatura_tekst, f'#{p.shtepia.nr_shtepise} {p.shtepia.emri_i_plote}',
                float(p.shuma_paguar), float(p.shuma_mkd or 0), p.monedha, p.vitet_tekst,
                p.data_pageses.strftime('%d.%m.%Y'), p.arktar.get_full_name(),
            ]
            for p in pagesat
        ]
        return _pergjigje_excel(f'pagesat_varrezave_{timezone.now().date()}.xlsx', koka, rreshtat)

    return render(request, 'pagesat/varrezat/lista.html', {
        'pagesat': pagesat, 'viti': viti, 'kerkimi': kerkimi,
        'vitit_lista': list(range(2000, timezone.now().year + 3)),
        'faqja_aktive': 'pagesat_varrezat',
    })


@login_required
def shto_pagese_varrezat(request):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje për të regjistruar pagesa.')
        return redirect('lista_pagesa_varrezave')
    shuma_paracaktuar = KonfigurimiVarrezave.merr().shuma_vjetore
    initial = _initial_pagese(
        request, PagesaVarrezave,
        lambda sh: (sh.pagesat_varrezave, sh.viti_fillimit_varrezave, sh.varrezat_paguar_deri_viti),
    )
    if shuma_paracaktuar:
        initial['shuma_hyrese'] = shuma_paracaktuar
    form = PagesaVarrezaveForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        pagese = form.apliko_shumen(form.save(commit=False))
        pagese.arktar = request.user
        pagese.save()
        messages.success(request, f'Pagesa {pagese.fatura_tekst} u regjistrua me sukses.')
        return redirect('detaje_pagesa_varrezat', pk=pagese.pk)
    return render(request, 'pagesat/varrezat/forma.html', {
        'form': form, 'titulli': 'Regjistro Pagesë Varrezash',
        'shuma_paracaktuar': shuma_paracaktuar, 'faqja_aktive': 'pagesat_varrezat',
    })


@login_required
def detaje_pagesa_varrezat(request, pk):
    pagese = get_object_or_404(PagesaVarrezave, pk=pk)
    return render(request, 'pagesat/varrezat/detaje.html', {
        'pagese': pagese, 'faqja_aktive': 'pagesat_varrezat'
    })


@login_required
def fatura_varrezat_pdf(request, pk):
    pagese = get_object_or_404(PagesaVarrezave, pk=pk)
    html = render_to_string('pagesat/varrezat/fatura_pdf.html', {'pagese': pagese})
    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="fatura-{pagese.nr_fatures}.pdf"'
    return response


@login_required
def fshi_pagese_varrezat(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_varrezave')
    pagese = get_object_or_404(PagesaVarrezave, pk=pk)
    nr = pagese.fatura_tekst

    return _fshirje_3hap(
        request,
        çelësi=f'varr_{pk}',
        fshi_fn=lambda: pagese.delete(),
        redirect_sukses=reverse('lista_pagesa_varrezave'),
        info={
            'lloji':     'Pagesë Varrezash',
            'emri':      pagese.fatura_tekst,
            'detaje':    f'{pagese.shtepia} — {pagese.shuma_origjinale} ({pagese.vitet_tekst})',
            'url_anulo': reverse('detaje_pagesa_varrezat', args=[pk]),
        },
        mesazh_sukses=f'Pagesa {nr} u fshi me sukses.',
    )


@login_required
def konfigurimi_varrezave(request):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('dashboard_varrezat')
    konfigurimi = KonfigurimiVarrezave.merr()
    form = KonfigurimiVarrezaveForm(request.POST or None, instance=konfigurimi)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Konfigurimi i varrezave u përditësua me sukses.')
        return redirect('dashboard_varrezat')
    return render(request, 'varrezat/konfigurimi.html', {
        'form': form, 'konfigurimi': konfigurimi, 'faqja_aktive': 'dashboard_varrezat',
    })


# ─── Email manual dërgim ────────────────────────────────────────────────────

@login_required
def dergo_email_antaresia(request, pk):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_antaresia')
    pagese = get_object_or_404(PagesaAntaresia, pk=pk)
    if request.method == 'POST':
        if not pagese.shtepia.email:
            messages.warning(request, 'Kjo shtëpi nuk ka email të regjistruar.')
        else:
            try:
                dërgo_email_antaresia(pagese, request)
                messages.success(request, f'Emaili u dërgua me sukses te {pagese.shtepia.email}.')
            except Exception as e:
                messages.error(request, f'Emaili nuk u dërgua: {e}')
    return redirect('detaje_pagesa_antaresia', pk=pk)


@login_required
def dergo_email_fondi_view(request, pk):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_fondi')
    pagese = get_object_or_404(PagesaFondi, pk=pk)
    if request.method == 'POST':
        if not pagese.email_donatorit:
            messages.warning(request, 'Ky donacion nuk ka email të regjistruar.')
        else:
            try:
                dërgo_email_fondi(pagese, request)
                messages.success(request, f'Emaili u dërgua me sukses te {pagese.email_donatorit}.')
            except Exception as e:
                messages.error(request, f'Emaili nuk u dërgua: {e}')
    return redirect('detaje_pagesa_fondi', pk=pk)


@login_required
def dergo_email_varrezat_view(request, pk):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_varrezave')
    pagese = get_object_or_404(PagesaVarrezave, pk=pk)
    if request.method == 'POST':
        if not pagese.shtepia.email:
            messages.warning(request, 'Kjo shtëpi nuk ka email të regjistruar.')
        else:
            try:
                dërgo_email_varrezat(pagese, request)
                messages.success(request, f'Emaili u dërgua me sukses te {pagese.shtepia.email}.')
            except Exception as e:
                messages.error(request, f'Emaili nuk u dërgua: {e}')
    return redirect('detaje_pagesa_varrezat', pk=pk)


# ─── SMS ────────────────────────────────────────────────────────────────────

def _dergo_sms_pagese(request, nr_telefoni, teksti, shtepia):
    if not nr_telefoni:
        messages.warning(request, 'Nuk ka numër telefoni të regjistruar.')
        return
    mesazh = sms.dergo_sms(nr_telefoni, teksti, 'KONFIRMIM', request.user, shtepia=shtepia)
    if mesazh.statusi == 'DESHTOI':
        messages.error(request, f'SMS-i nuk u dërgua: {mesazh.gabimi}')
    else:
        messages.success(request, f'SMS-i u dërgua te {mesazh.nr_telefoni}.')


@login_required
def dergo_sms_antaresia(request, pk):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_antaresia')
    pagese = get_object_or_404(PagesaAntaresia, pk=pk)
    if request.method == 'POST':
        _dergo_sms_pagese(request, pagese.shtepia.nr_telefoni_kryesor,
                          sms.teksti_antaresia(pagese), pagese.shtepia)
    return redirect('detaje_pagesa_antaresia', pk=pk)


@login_required
def dergo_sms_fondi(request, pk):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_fondi')
    pagese = get_object_or_404(PagesaFondi, pk=pk)
    if request.method == 'POST':
        _dergo_sms_pagese(request, pagese.nr_telefoni, sms.teksti_fondi(pagese), None)
    return redirect('detaje_pagesa_fondi', pk=pk)


@login_required
def dergo_sms_varrezat(request, pk):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_varrezave')
    pagese = get_object_or_404(PagesaVarrezave, pk=pk)
    if request.method == 'POST':
        _dergo_sms_pagese(request, pagese.shtepia.nr_telefoni_kryesor,
                          sms.teksti_varrezat(pagese), pagese.shtepia)
    return redirect('detaje_pagesa_varrezat', pk=pk)


def _borxhet_antaresise(shtepite):
    """Për çdo shtëpi: vitet e papaguara të antarësisë dhe shuma e borxhit (nëse dihet kategoria).
    E njëjta logjikë si _tabela_vjetore, por me një query të vetëm për të gjitha pagesat."""
    viti_aktual = timezone.now().year
    mbuluara = {}
    for sh_id, nga, deri in PagesaAntaresia.objects.values_list('shtepia_id', 'viti', 'viti_deri'):
        mbuluara.setdefault(sh_id, set()).update(range(nga, (deri or nga) + 1))
    rezultati = []
    for sh in shtepite:
        paguara = mbuluara.get(sh.id, set())
        vitet = [
            v for v in range(sh.viti_fillimit_antaresise, viti_aktual + 1)
            if v not in paguara and not (sh.paguar_deri_viti and v <= sh.paguar_deri_viti)
        ]
        shuma_vjetore = sh.kategoria.shuma_vjetore if sh.kategoria else Decimal('0')
        rezultati.append({'shtepi': sh, 'vitet': vitet, 'borxhi': shuma_vjetore * len(vitet)})
    return rezultati


@login_required
def borxhlinjte_sms(request):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('dashboard')

    try:
        min_vite = max(1, int(request.GET.get('min_vite', 2)))
    except ValueError:
        min_vite = 2

    shtepite = Shtepia.objects.filter(është_aktiv=True).select_related('kategoria')
    borxhlinjte = [b for b in _borxhet_antaresise(shtepite) if len(b['vitet']) >= min_vite]
    for b in borxhlinjte:
        b['numri'] = sms.normalizo_numrin(b['shtepi'].nr_telefoni_kryesor)

    teksti = sms.TEKSTI_KUJTESES_PARACAKTUAR
    if request.method == 'POST':
        teksti = request.POST.get('teksti', '').strip() or sms.TEKSTI_KUJTESES_PARACAKTUAR
        zgjedhura = set(request.POST.getlist('shtepite'))
        te_derguara, deshtuara = 0, 0
        for b in borxhlinjte:
            sh = b['shtepi']
            if str(sh.pk) not in zgjedhura or not b['numri']:
                continue
            try:
                personal = teksti.format(
                    emri=sh.emri_i_plote,
                    vitet=', '.join(str(v) for v in b['vitet']),
                    borxhi=b['borxhi'],
                    nr=sh.nr_shtepise,
                )
            except (KeyError, IndexError, ValueError):
                messages.error(request, 'Teksti ka një {fushë} të panjohur. Përdorni vetëm {emri}, {vitet}, {borxhi}, {nr}.')
                break
            mesazh = sms.dergo_sms(sh.nr_telefoni_kryesor, personal, 'KUJTESE', request.user, shtepia=sh)
            if mesazh.statusi == 'DESHTOI':
                deshtuara += 1
            else:
                te_derguara += 1
        else:
            if te_derguara:
                messages.success(request, f'{te_derguara} SMS iu dërguan telefonit për dërgim.')
            if deshtuara:
                messages.error(request, f'{deshtuara} SMS dështuan — shihni Historikun e SMS-ve.')
            if not te_derguara and not deshtuara:
                messages.warning(request, 'Nuk u zgjodh asnjë shtëpi me numër të vlefshëm.')
            return redirect(f"{reverse('borxhlinjte_sms')}?min_vite={min_vite}")

    return render(request, 'sms/borxhlinjte.html', {
        'borxhlinjte': borxhlinjte,
        'min_vite': min_vite,
        'teksti': teksti,
        'pa_numer': sum(1 for b in borxhlinjte if not b['numri']),
        'gateway_gati': sms.eshte_konfiguruar(),
        'faqja_aktive': 'sms_borxhlinjte',
    })


@login_required
def historiku_sms(request):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('dashboard')

    if request.method == 'POST':
        for m in MesazhSMS.objects.filter(statusi__in=['NE_PRITJE', 'DERGUAR']).exclude(id_gateway='')[:50]:
            sms.perditeso_statusin(m)
        messages.success(request, 'Statuset u përditësuan.')
        return redirect('historiku_sms')

    mesazhet = MesazhSMS.objects.select_related('shtepia', 'dërguar_nga')[:200]
    return render(request, 'sms/historiku.html', {
        'mesazhet': mesazhet,
        'faqja_aktive': 'sms_historiku',
    })


@login_required
def konfigurimi_sistemit(request):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('dashboard')
    konfigurimi = KonfigurimiSistemit.merr()
    form = KonfigurimiSistemitForm(instance=konfigurimi)

    if request.method == 'POST':
        veprimi = request.POST.get('veprimi')
        if veprimi == 'ruaj':
            form = KonfigurimiSistemitForm(request.POST, instance=konfigurimi)
            if form.is_valid():
                form.save()
                messages.success(request, 'Konfigurimi u ruajt.')
                return redirect('konfigurimi_sistemit')
        elif veprimi == 'prove_sms':
            mesazh = sms.dergo_sms(
                request.POST.get('nr_prove', ''),
                'Xhamia Pirok: SMS prove nga sistemi. Nese e merrni kete, SMS-te punojne!',
                'KONFIRMIM', request.user,
            )
            if mesazh.statusi == 'DESHTOI':
                messages.error(request, f'SMS prova dështoi: {mesazh.gabimi}')
            else:
                messages.success(request, f'SMS prova iu dërgua telefonit. Duhet të arrijë te {mesazh.nr_telefoni} brenda pak sekondave.')
            return redirect('konfigurimi_sistemit')
        elif veprimi == 'prove_email':
            try:
                send_mail(
                    'Email provë — Xhamia Pirok',
                    'Nëse e merrni këtë email, dërgimi i faturave me email punon.',
                    settings.DEFAULT_FROM_EMAIL, [settings.EMAIL_HOST_USER],
                )
                messages.success(request, f'Email prova u dërgua te {settings.EMAIL_HOST_USER}.')
            except Exception as e:
                messages.error(request, f'Email prova dështoi: {e}')
            return redirect('konfigurimi_sistemit')

    return render(request, 'sms/konfigurimi.html', {
        'form': form,
        'sms_gati': sms.eshte_konfiguruar(),
        'gmail_gati': bool(konfigurimi.gmail_app_password or settings.EMAIL_HOST_PASSWORD),
        'email_adresa': settings.EMAIL_HOST_USER,
        'nr_im': getattr(getattr(request.user, 'profili', None), 'nr_telefoni', ''),
        'faqja_aktive': 'konfigurimi_sistemit',
    })


# ─── Harxhimet ───────────────────────────────────────────────────────────────

@login_required
def lista_harxhimeve(request):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    viti = int(request.GET.get('viti', timezone.now().year))
    lloji = request.GET.get('lloji', '')
    harxhimet = Harxhimi.objects.select_related('stafi', 'arktar').filter(viti=viti)
    if lloji:
        harxhimet = harxhimet.filter(lloji=lloji)
    total = harxhimet.aggregate(s=Sum('shuma_eur'))['s'] or 0
    return render(request, 'harxhimet/lista.html', {
        'harxhimet': harxhimet, 'viti': viti, 'lloji': lloji,
        'total': total,
        'vitit_lista': list(range(2015, timezone.now().year + 2)),
        'lloji_choices': Harxhimi.LLOJI_CHOICES,
        'faqja_aktive': 'harxhimet',
    })


@login_required
def shto_harxhim(request):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('dashboard_buxheti')
    form = HarxhimiForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        harxhim = form.save(commit=False)
        harxhim.arktar = request.user
        harxhim.save()
        messages.success(request, f'Harxhimi {harxhim.nr_fatures} u regjistrua me sukses.')
        return redirect('detaje_harxhimi', pk=harxhim.pk)
    return render(request, 'harxhimet/forma.html', {
        'form': form, 'titulli': 'Regjistro Harxhim', 'faqja_aktive': 'harxhimet',
    })


@login_required
def detaje_harxhimi(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    harxhim = get_object_or_404(Harxhimi, pk=pk)
    return render(request, 'harxhimet/detaje.html', {
        'harxhim': harxhim, 'faqja_aktive': 'harxhimet',
    })


@login_required
def fshi_harxhimin(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_harxhimeve')
    harxhim = get_object_or_404(Harxhimi, pk=pk)
    info = f'{harxhim.nr_fatures} — {harxhim.get_lloji_display()} — {harxhim.shuma_eur}€'
    return _fshirje_3hap(
        request,
        çelësi=f'hrx_{pk}',
        fshi_fn=harxhim.delete,
        redirect_sukses='lista_harxhimeve',
        info=info,
        mesazh_sukses=f'Harxhimi {harxhim.nr_fatures} u fshi me sukses.',
    )


# ─── Dashboard Buxheti ───────────────────────────────────────────────────────

@login_required
def dashboard_buxheti(request):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    viti_aktual = timezone.now().year
    viti_zgjedhur = int(request.GET.get('viti', viti_aktual))
    vitit_lista = list(range(2015, viti_aktual + 2))

    # ── Antarësia ──
    hyra_ant = PagesaAntaresia.objects.filter(
        data_pageses__year=viti_zgjedhur
    ).aggregate(s=Sum('shuma_paguar'))['s'] or Decimal('0')
    sh_ant = Harxhimi.objects.filter(
        viti=viti_zgjedhur, burimi='ANTARESIA'
    ).aggregate(s=Sum('shuma_eur'))['s'] or Decimal('0')
    balanca_ant = hyra_ant - sh_ant

    rrogat_e_fundit = Harxhimi.objects.select_related('stafi').filter(
        viti=viti_zgjedhur, burimi='ANTARESIA'
    ).order_by('-data_pageses')[:6]

    data_10_ant = []
    for v in range(viti_aktual - 9, viti_aktual + 1):
        h = float(PagesaAntaresia.objects.filter(data_pageses__year=v).aggregate(s=Sum('shuma_paguar'))['s'] or 0)
        sh = float(Harxhimi.objects.filter(viti=v, burimi='ANTARESIA').aggregate(s=Sum('shuma_eur'))['s'] or 0)
        data_10_ant.append({'viti': v, 'hyra': h, 'shpenzime': sh})

    # ── Fondi ──
    hyra_fond = PagesaFondi.objects.filter(
        data_pageses__year=viti_zgjedhur
    ).aggregate(s=Sum('shuma'))['s'] or Decimal('0')
    sh_fond = Harxhimi.objects.filter(
        viti=viti_zgjedhur, burimi='FONDI'
    ).aggregate(s=Sum('shuma_eur'))['s'] or Decimal('0')
    balanca_fond = hyra_fond - sh_fond

    shpenzimet_e_fundit = Harxhimi.objects.filter(
        viti=viti_zgjedhur, burimi='FONDI'
    ).order_by('-data_pageses')[:6]

    sipas_llojit_fond = []
    for lloji_val, emri in Harxhimi.LLOJI_CHOICES:
        if lloji_val == 'RROGE':
            continue
        shuma = Harxhimi.objects.filter(
            viti=viti_zgjedhur, lloji=lloji_val, burimi='FONDI'
        ).aggregate(s=Sum('shuma_eur'))['s'] or 0
        if shuma > 0:
            sipas_llojit_fond.append({'lloji': emri, 'shuma': float(shuma)})

    data_10_fond = []
    for v in range(viti_aktual - 9, viti_aktual + 1):
        h = float(PagesaFondi.objects.filter(data_pageses__year=v).aggregate(s=Sum('shuma'))['s'] or 0)
        sh = float(Harxhimi.objects.filter(viti=v, burimi='FONDI').aggregate(s=Sum('shuma_eur'))['s'] or 0)
        data_10_fond.append({'viti': v, 'hyra': h, 'shpenzime': sh})

    return render(request, 'dashboard/buxheti.html', {
        'viti_zgjedhur': viti_zgjedhur,
        'vitit_lista': vitit_lista,
        # Antarësia
        'hyra_ant': hyra_ant,
        'sh_ant': sh_ant,
        'balanca_ant': balanca_ant,
        'rrogat_e_fundit': rrogat_e_fundit,
        'data_10_ant_json': json.dumps(data_10_ant),
        # Fondi
        'hyra_fond': hyra_fond,
        'sh_fond': sh_fond,
        'balanca_fond': balanca_fond,
        'shpenzimet_e_fundit': shpenzimet_e_fundit,
        'sipas_llojit_fond_json': json.dumps(sipas_llojit_fond),
        'data_10_fond_json': json.dumps(data_10_fond),
        'faqja_aktive': 'buxheti',
    })


# ─── Stafi ──────────────────────────────────────────────────────────────────

@login_required
def lista_stafit(request):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    stafi = ProfilStafi.objects.select_related('user', 'shtuar_nga').order_by('user__last_name')
    return render(request, 'stafi/lista.html', {'stafi': stafi, 'faqja_aktive': 'stafi'})


@login_required
def shto_staf(request):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    form = StafForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        if User.objects.filter(username=cd['username']).exists():
            form.add_error('username', 'Ky emër përdoruesi ekziston tashmë.')
        else:
            user = User.objects.create_user(
                username=cd['username'],
                email=cd['email'],
                password=cd['password'],
                first_name=cd['first_name'],
                last_name=cd['last_name'],
            )
            profil = form.save(commit=False)
            profil.user = user
            profil.shtuar_nga = request.user
            profil.save()
            messages.success(request, f'Stafi {user.get_full_name()} u shtua me sukses.')
            return redirect('lista_stafit')
    return render(request, 'stafi/forma.html', {'form': form, 'titulli': 'Shto Staf të Ri', 'faqja_aktive': 'stafi'})


@login_required
def edito_staf(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    profil = get_object_or_404(ProfilStafi, pk=pk)
    form = StafForm(request.POST or None, instance=profil, initial={
        'first_name': profil.user.first_name,
        'last_name': profil.user.last_name,
        'email': profil.user.email,
        'username': profil.user.username,
    })
    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        profil.user.first_name = cd['first_name']
        profil.user.last_name = cd['last_name']
        profil.user.email = cd['email']
        if cd['password']:
            profil.user.set_password(cd['password'])
        profil.user.save()
        form.save()
        messages.success(request, 'Të dhënat u përditësuan.')
        return redirect('lista_stafit')
    return render(request, 'stafi/forma.html', {
        'form': form, 'titulli': f'Edito {profil.user.get_full_name()}',
        'profil': profil, 'faqja_aktive': 'stafi'
    })


@login_required
def fshi_staf(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    profil = get_object_or_404(ProfilStafi, pk=pk)
    if profil.user == request.user:
        messages.error(request, 'Nuk mund ta çaktivizoni llogarinë tuaj.')
        return redirect('lista_stafit')
    emri = profil.user.get_full_name()

    def çaktivizo():
        profil.user.is_active = False
        profil.user.save()
        profil.është_aktiv = False
        profil.save()

    return _fshirje_3hap(
        request,
        çelësi=f'staf_{pk}',
        fshi_fn=çaktivizo,
        redirect_sukses=reverse('lista_stafit'),
        info={
            'lloji':     'Staf',
            'emri':      emri,
            'detaje':    profil.pozita or f'@{profil.user.username}',
            'url_anulo': reverse('lista_stafit'),
        },
        mesazh_sukses=f'{emri} u çaktivizua me sukses.',
    )


@login_required
def fshi_shtepi(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_shtepive')
    shtepi = get_object_or_404(Shtepia, pk=pk)

    def çaktivizo():
        shtepi.është_aktiv = False
        shtepi.save()

    return _fshirje_3hap(
        request,
        çelësi=f'shtepi_{pk}',
        fshi_fn=çaktivizo,
        redirect_sukses=reverse('lista_shtepive'),
        info={
            'lloji':     'Shtëpi',
            'emri':      f'Shtëpia #{shtepi.nr_shtepise}',
            'detaje':    shtepi.emri_i_plote,
            'url_anulo': reverse('detaje_shtepia', args=[pk]),
        },
        mesazh_sukses=f'Shtëpia #{shtepi.nr_shtepise} u çaktivizua me sukses.',
    )


@login_required
def fshi_pagese_antaresia(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_antaresia')
    pagese = get_object_or_404(PagesaAntaresia, pk=pk)
    nr = pagese.fatura_tekst

    return _fshirje_3hap(
        request,
        çelësi=f'ant_{pk}',
        fshi_fn=lambda: pagese.delete(),
        redirect_sukses=reverse('lista_pagesa_antaresia'),
        info={
            'lloji':     'Pagesë Antarësia',
            'emri':      pagese.fatura_tekst,
            'detaje':    f'{pagese.shtepia} — {pagese.shuma_origjinale} ({pagese.vitet_tekst})',
            'url_anulo': reverse('detaje_pagesa_antaresia', args=[pk]),
        },
        mesazh_sukses=f'Pagesa {nr} u fshi me sukses.',
    )


@login_required
def fshi_pagese_fondi(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_pagesa_fondi')
    pagese = get_object_or_404(PagesaFondi, pk=pk)
    nr = pagese.fatura_tekst

    return _fshirje_3hap(
        request,
        çelësi=f'fond_{pk}',
        fshi_fn=lambda: pagese.delete(),
        redirect_sukses=reverse('lista_pagesa_fondi'),
        info={
            'lloji':     'Donacion Fondi',
            'emri':      pagese.fatura_tekst,
            'detaje':    f'{pagese.emri_donatorit} {pagese.mbiemri_donatorit} — {pagese.shuma_origjinale}',
            'url_anulo': reverse('detaje_pagesa_fondi', args=[pk]),
        },
        mesazh_sukses=f'Donacioni {nr} u fshi me sukses.',
    )


# ─── Kategoritë ─────────────────────────────────────────────────────────────

@login_required
def lista_kategorive(request):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    kategoritë = Kategoria.objects.all()
    return render(request, 'kategoritë/lista.html', {'kategoritë': kategoritë, 'faqja_aktive': 'kategoritë'})


@login_required
def shto_kategori(request):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    form = KategoriaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Kategoria u shtua me sukses.')
        return redirect('lista_kategorive')
    return render(request, 'kategoritë/forma.html', {'form': form, 'titulli': 'Shto Kategori', 'faqja_aktive': 'kategoritë'})


@login_required
def edito_kategori(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Aksesi i refuzuar.')
        return redirect('dashboard')
    kat = get_object_or_404(Kategoria, pk=pk)
    form = KategoriaForm(request.POST or None, instance=kat)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Kategoria u përditësua.')
        return redirect('lista_kategorive')
    return render(request, 'kategoritë/forma.html', {
        'form': form, 'titulli': f'Edito: {kat.emri}', 'faqja_aktive': 'kategoritë'
    })


# ─── Portali i Shtëpive ─────────────────────────────────────────────────────

@login_required
def portali_shtepi(request):
    try:
        profili = request.user.profili_shtepi
    except Exception:
        return redirect('dashboard')

    shtepi = profili.shtepia
    viti = int(request.GET.get('viti', timezone.now().year))
    vitit_lista = list(range(2020, timezone.now().year + 2))

    pagesat_te_gjitha = shtepi.pagesat.select_related('arktar').order_by('-viti', '-data_pageses')

    viti_aktual = timezone.now().year
    pagesat_per_vit, borxhi_total, papaguara = _tabela_vjetore(
        shtepi.pagesat, shtepi.viti_fillimit_antaresise, shtepi.paguar_deri_viti,
        shtepi.kategoria.shuma_vjetore if shtepi.kategoria else None,
    )

    total_gjithsej = pagesat_te_gjitha.aggregate(s=Sum('shuma_paguar'))['s'] or Decimal('0')
    pagesa_e_fundit = pagesat_te_gjitha.first()

    return render(request, 'portali_shtepi/dashboard.html', {
        'shtepi': shtepi,
        'viti': viti,
        'vitit_lista': vitit_lista,
        'pagesat_per_vit': pagesat_per_vit,
        'pagesat_te_gjitha': pagesat_te_gjitha,
        'borxhi_total': borxhi_total,
        'nr_papaguara': len(papaguara),
        'viti_aktual': viti_aktual,
        'total_gjithsej': total_gjithsej,
        'pagesa_e_fundit': pagesa_e_fundit,
        'portali_shtepi': True,
    })


@login_required
def ndrysho_fjalekalim_shtepi(request):
    if not hasattr(request.user, 'profili_shtepi'):
        return redirect('dashboard')

    if request.method == 'POST':
        fjalëkalim_vjetër = request.POST.get('fjalëkalim_vjetër', '')
        fjalëkalim_ri     = request.POST.get('fjalëkalim_ri', '').strip()
        konfirmimi        = request.POST.get('konfirmimi', '').strip()

        if not request.user.check_password(fjalëkalim_vjetër):
            messages.error(request, 'Fjalëkalimi aktual është i gabuar.')
        elif fjalëkalim_ri != konfirmimi:
            messages.error(request, 'Fjalëkalimet e reja nuk përputhen.')
        elif len(fjalëkalim_ri) < 6:
            messages.error(request, 'Fjalëkalimi duhet të ketë të paktën 6 karaktere.')
        else:
            request.user.set_password(fjalëkalim_ri)
            request.user.save()
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Fjalëkalimi u ndryshua me sukses.')
            return redirect('portali_shtepi')

    return render(request, 'portali_shtepi/ndrysho_fjalekalim.html', {'portali_shtepi': True})


@login_required
def shto_llogari_shtepi(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_shtepive')
    shtepi = get_object_or_404(Shtepia, pk=pk)

    if request.method == 'POST':
        if hasattr(shtepi, 'llogaria'):
            fjalëkalimi_ri = request.POST.get('fjalëkalimi_ri', '').strip()
            if len(fjalëkalimi_ri) < 6:
                messages.error(request, 'Fjalëkalimi duhet të jetë të paktën 6 karaktere.')
            else:
                shtepi.llogaria.user.set_password(fjalëkalimi_ri)
                shtepi.llogaria.user.save()
                messages.success(request, f'Fjalëkalimi për sh{shtepi.nr_shtepise} u rivendos.')
        else:
            fjalëkalimi = request.POST.get('fjalëkalimi', '').strip()
            if len(fjalëkalimi) < 6:
                messages.error(request, 'Fjalëkalimi duhet të jetë të paktën 6 karaktere.')
            else:
                username = f'sh{shtepi.nr_shtepise}'
                if User.objects.filter(username=username).exists():
                    messages.error(request, f'Username "{username}" ekziston tashmë.')
                else:
                    user = User.objects.create_user(
                        username=username,
                        password=fjalëkalimi,
                        first_name=shtepi.emri_kryefamiljarit,
                        last_name=shtepi.mbiemri_kryefamiljarit,
                        email=shtepi.email or '',
                    )
                    profil = ProfilShtepi(shtepia=shtepi, krijuar_nga=request.user)
                    profil.user = user
                    profil.save()
                    messages.success(request, f'Llogaria u krijua. Username: {username}')

    return redirect('detaje_shtepia', pk=pk)


@login_required
def fshi_llogari_shtepi(request, pk):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje.')
        return redirect('lista_shtepive')
    shtepi = get_object_or_404(Shtepia, pk=pk)
    if request.method == 'POST' and hasattr(shtepi, 'llogaria'):
        username = shtepi.llogaria.user.username
        shtepi.llogaria.user.delete()
        messages.success(request, f'Llogaria "{username}" u fshi.')
    return redirect('detaje_shtepia', pk=pk)
