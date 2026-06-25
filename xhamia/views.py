from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.template.loader import render_to_string
from django.urls import reverse
from io import BytesIO
from xhtml2pdf import pisa
import json
import random
import string
from decimal import Decimal

from .models import ProfilStafi, ProfilShtepi, Kategoria, Shtepia, PagesaAntaresia, PagesaFondi
from .forms import (
    LoginForm, StafForm, KategoriaForm, ShtepiaForm,
    PagesaAntaresiaForm, PagesaFondiForm
)
from .utils import dërgo_email_antaresia, dërgo_email_fondi


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
    actual_ids = set(PagesaAntaresia.objects.filter(viti=viti_zgjedhur).values_list('shtepia_id', flat=True))
    historical_ids = set(Shtepia.objects.filter(
        paguar_deri_viti__gte=viti_zgjedhur, është_aktiv=True
    ).values_list('id', flat=True))
    paguar_ids = actual_ids | historical_ids
    kane_paguar = len(paguar_ids)
    nuk_kane_paguar = total_shtepite - kane_paguar

    total_mbledhur = PagesaAntaresia.objects.filter(viti=viti_zgjedhur).aggregate(
        s=Sum('shuma_paguar')
    )['s'] or 0

    # Pagesat sipas muajit (për grafik)
    pagesat_mujore = []
    muajt_etiketat = ['Jan', 'Shk', 'Mar', 'Pri', 'Maj', 'Qer', 'Kor', 'Gus', 'Sht', 'Tet', 'Nën', 'Dhj']
    for m in range(1, 13):
        shuma = PagesaAntaresia.objects.filter(
            viti=viti_zgjedhur, data_pageses__month=m
        ).aggregate(s=Sum('shuma_paguar'))['s'] or 0
        pagesat_mujore.append(float(shuma))

    # Sipas kategorisë
    sipas_kategorise = []
    for kat in Kategoria.objects.filter(është_aktiv=True):
        cnt = PagesaAntaresia.objects.filter(viti=viti_zgjedhur, kategoria_pageses=kat).count()
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
        shuma_v = PagesaAntaresia.objects.filter(viti=v).aggregate(s=Sum('shuma_paguar'))['s'] or 0
        act_v = set(PagesaAntaresia.objects.filter(viti=v).values_list('shtepia_id', flat=True))
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

    konteksti = {
        'viti_zgjedhur': viti_zgjedhur,
        'vitit_lista': vitit_lista,
        'total_fondi': total_fondi,
        'total_donator': total_donator,
        'pagesat_mujore_json': json.dumps(pagesat_mujore),
        'muajt_etiketat_json': json.dumps(muajt_etiketat),
        'krahasimi_viteve_json': json.dumps(krahasimi_viteve),
        'pagesat_e_fundit': pagesat_e_fundit,
        'top_donator': top_donator,
        'faqja_aktive': 'dashboard_fondi',
    }
    return render(request, 'dashboard/fondi.html', konteksti)


# ─── Shtëpitë ───────────────────────────────────────────────────────────────

@login_required
def lista_shtepive(request):
    kerkimi = request.GET.get('kerkimi', '')
    kategoria_id = request.GET.get('kategoria', '')
    statusi = request.GET.get('statusi', 'aktive')
    viti_pageses = request.GET.get('viti_pageses', '')

    shtepite = Shtepia.objects.select_related('kategoria', 'regjistruar_nga')

    if statusi == 'aktive':
        shtepite = shtepite.filter(është_aktiv=True)
    elif statusi == 'joaktive':
        shtepite = shtepite.filter(është_aktiv=False)

    if kerkimi:
        shtepite = shtepite.filter(
            Q(nr_shtepise__icontains=kerkimi) |
            Q(emri_kryefamiljarit__icontains=kerkimi) |
            Q(mbiemri_kryefamiljarit__icontains=kerkimi)
        )

    if kategoria_id:
        shtepite = shtepite.filter(kategoria_id=kategoria_id)

    if viti_pageses:
        viti_pageses = int(viti_pageses)
        pa_pagese = request.GET.get('pa_pagese', '')
        if pa_pagese:
            shtepite = shtepite.exclude(pagesat__viti=viti_pageses)
        else:
            shtepite = shtepite.filter(pagesat__viti=viti_pageses)

    konteksti = {
        'shtepite': shtepite,
        'kategoritë': Kategoria.objects.filter(është_aktiv=True),
        'kerkimi': kerkimi,
        'kategoria_id': kategoria_id,
        'statusi': statusi,
        'faqja_aktive': 'shtepite',
    }
    return render(request, 'shtepite/lista.html', konteksti)


@login_required
def shto_shtepi(request):
    if not është_admin(request.user):
        messages.error(request, 'Nuk keni leje për këtë veprim.')
        return redirect('lista_shtepive')
    form = ShtepiaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        shtepi = form.save(commit=False)
        shtepi.regjistruar_nga = request.user
        shtepi.save()
        messages.success(request, f'Shtëpia #{shtepi.nr_shtepise} u regjistrua me sukses.')
        return redirect('detaje_shtepia', pk=shtepi.pk)
    return render(request, 'shtepite/forma.html', {'form': form, 'titulli': 'Shto Shtëpi të Re', 'faqja_aktive': 'shtepite'})


@login_required
def detaje_shtepia(request, pk):
    shtepi = get_object_or_404(Shtepia, pk=pk)
    pagesat = shtepi.pagesat.select_related('arktar', 'kategoria_pageses').order_by('-viti', '-data_pageses')

    viti_aktual = timezone.now().year
    viti_fillimit = shtepi.viti_fillimit_antaresise
    paguar_deri = shtepi.paguar_deri_viti
    pagesat_per_vit = {}
    borxhi_total = Decimal('0')
    for v in range(viti_fillimit, viti_aktual + 1):
        shuma_duhet = shtepi.kategoria.shuma_vjetore
        if paguar_deri and v <= paguar_deri:
            pagesat_per_vit[v] = {
                'shuma_paguar': shuma_duhet,
                'ka_paguar': True,
                'borxhi': Decimal('0'),
                'historike': True,
            }
        else:
            shuma_paguar = shtepi.pagesat.filter(viti=v).aggregate(
                s=Sum('shuma_paguar')
            )['s'] or Decimal('0')
            ka_paguar = shuma_paguar >= shuma_duhet
            borxh_v = max(Decimal('0'), shuma_duhet - shuma_paguar)
            borxhi_total += borxh_v
            pagesat_per_vit[v] = {
                'shuma_paguar': shuma_paguar,
                'ka_paguar': ka_paguar,
                'borxhi': borxh_v,
                'historike': False,
            }

    vitit_lista = list(range(2000, viti_aktual + 2))

    return render(request, 'shtepite/detaje.html', {
        'shtepi': shtepi,
        'pagesat': pagesat,
        'pagesat_per_vit': pagesat_per_vit,
        'borxhi_total': borxhi_total,
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
    viti = request.GET.get('viti', timezone.now().year)
    kerkimi = request.GET.get('kerkimi', '')
    pagesat = PagesaAntaresia.objects.select_related('shtepia', 'arktar', 'kategoria_pageses')
    if viti:
        pagesat = pagesat.filter(viti=viti)
    if kerkimi:
        pagesat = pagesat.filter(
            Q(nr_fatures__icontains=kerkimi) |
            Q(shtepia__emri_kryefamiljarit__icontains=kerkimi) |
            Q(shtepia__mbiemri_kryefamiljarit__icontains=kerkimi) |
            Q(shtepia__nr_shtepise__icontains=kerkimi)
        )
    return render(request, 'pagesat/antaresia/lista.html', {
        'pagesat': pagesat, 'viti': viti, 'kerkimi': kerkimi,
        'vitit_lista': list(range(2020, timezone.now().year + 2)),
        'faqja_aktive': 'pagesat_antaresia',
    })


@login_required
def shto_pagese_antaresia(request):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje për të regjistruar pagesa.')
        return redirect('lista_pagesa_antaresia')
    form = PagesaAntaresiaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        pagese = form.save(commit=False)
        pagese.arktar = request.user
        pagese.save()
        try:
            dërgo_email_antaresia(pagese, request)
            messages.success(request, f'Pagesa {pagese.nr_fatures} u regjistrua dhe emaili u dërgua me sukses.')
        except Exception as e:
            messages.warning(request, f'Pagesa u regjistrua, por emaili nuk u dërgua: {e}')
        return redirect('detaje_pagesa_antaresia', pk=pagese.pk)
    return render(request, 'pagesat/antaresia/forma.html', {
        'form': form, 'titulli': 'Regjistro Pagesë Antarësia', 'faqja_aktive': 'pagesat_antaresia'
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
    pagesat = PagesaFondi.objects.select_related('arktar')
    if viti:
        pagesat = pagesat.filter(data_pageses__year=viti)
    if kerkimi:
        pagesat = pagesat.filter(
            Q(nr_fatures__icontains=kerkimi) |
            Q(emri_donatorit__icontains=kerkimi) |
            Q(mbiemri_donatorit__icontains=kerkimi)
        )
    return render(request, 'pagesat/fondi/lista.html', {
        'pagesat': pagesat, 'viti': viti, 'kerkimi': kerkimi,
        'vitit_lista': list(range(2020, timezone.now().year + 2)),
        'faqja_aktive': 'pagesat_fondi',
    })


@login_required
def shto_pagese_fondi(request):
    if not mund_regjistrojë(request.user):
        messages.error(request, 'Nuk keni leje për të regjistruar pagesa.')
        return redirect('lista_pagesa_fondi')
    form = PagesaFondiForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        pagese = form.save(commit=False)
        pagese.arktar = request.user
        pagese.save()
        try:
            dërgo_email_fondi(pagese, request)
            messages.success(request, f'Pagesa {pagese.nr_fatures} u regjistrua dhe emaili u dërgua me sukses.')
        except Exception as e:
            messages.warning(request, f'Pagesa u regjistrua, por emaili nuk u dërgua: {e}')
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
            'detaje':    f'{shtepi.emri_kryefamiljarit} {shtepi.mbiemri_kryefamiljarit} — {shtepi.kategoria.emri}',
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
    nr = pagese.nr_fatures

    return _fshirje_3hap(
        request,
        çelësi=f'ant_{pk}',
        fshi_fn=lambda: pagese.delete(),
        redirect_sukses=reverse('lista_pagesa_antaresia'),
        info={
            'lloji':     'Pagesë Antarësia',
            'emri':      pagese.nr_fatures,
            'detaje':    f'{pagese.shtepia} — {pagese.shuma_paguar}€ ({pagese.viti})',
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
    nr = pagese.nr_fatures

    return _fshirje_3hap(
        request,
        çelësi=f'fond_{pk}',
        fshi_fn=lambda: pagese.delete(),
        redirect_sukses=reverse('lista_pagesa_fondi'),
        info={
            'lloji':     'Donacion Fondi',
            'emri':      pagese.nr_fatures,
            'detaje':    f'{pagese.emri_donatorit} {pagese.mbiemri_donatorit} — {pagese.shuma}€',
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

    pagesat_te_gjitha = shtepi.pagesat.select_related('arktar', 'kategoria_pageses').order_by('-viti', '-data_pageses')

    viti_aktual = timezone.now().year
    viti_fillimit = shtepi.viti_fillimit_antaresise
    paguar_deri = shtepi.paguar_deri_viti
    pagesat_per_vit = {}
    borxhi_total = Decimal('0')
    for v in range(viti_fillimit, viti_aktual + 1):
        shuma_duhet = shtepi.kategoria.shuma_vjetore
        if paguar_deri and v <= paguar_deri:
            pagesat_per_vit[v] = {
                'shuma_paguar': shuma_duhet,
                'ka_paguar': True,
                'borxhi': Decimal('0'),
                'historike': True,
            }
        else:
            shuma_paguar = shtepi.pagesat.filter(viti=v).aggregate(
                s=Sum('shuma_paguar')
            )['s'] or Decimal('0')
            ka_paguar = shuma_paguar >= shuma_duhet
            borxh_v = max(Decimal('0'), shuma_duhet - shuma_paguar)
            borxhi_total += borxh_v
            pagesat_per_vit[v] = {
                'shuma_paguar': shuma_paguar,
                'ka_paguar': ka_paguar,
                'borxhi': borxh_v,
                'historike': False,
            }

    total_gjithsej = pagesat_te_gjitha.aggregate(s=Sum('shuma_paguar'))['s'] or Decimal('0')
    pagesa_e_fundit = pagesat_te_gjitha.first()

    return render(request, 'portali_shtepi/dashboard.html', {
        'shtepi': shtepi,
        'viti': viti,
        'vitit_lista': vitit_lista,
        'pagesat_per_vit': pagesat_per_vit,
        'pagesat_te_gjitha': pagesat_te_gjitha,
        'borxhi_total': borxhi_total,
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
