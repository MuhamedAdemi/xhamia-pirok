from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings

from . import llogarite


def subjekti_fatures(emri, pagese, lloji):
    """P.sh. "Muhamed Mesud Ademi — Bl 1100 Nr 046386 — Antarësia 2024–2026 — Xhamia Pirok"
    (që në Gmail të gjendet lehtë sipas emrit, bllokut ose numrit)."""
    pjeset = [emri]
    if pagese.blloku:
        pjeset.append(f'Bl {pagese.blloku} Nr {pagese.nr_fatures}')
    else:
        pjeset.append(f'Nr {pagese.nr_fatures}')
    pjeset += [lloji, 'Xhamia Pirok']
    return ' — '.join(p for p in pjeset if p)


def _perdoruesi(request):
    user = getattr(request, 'user', None)
    return user if user is not None and user.is_authenticated else None


def emailat_e_stafit():
    """Kush njoftohet për çdo pagesë: VETËM emailat zyrtarë (xhamia, kryetari i këshillit, imami) —
    asnjë email personal i stafit."""
    return list(dict.fromkeys(e.strip().lower() for e in settings.EMAILET_ZYRTARE if e))


def _dergo(subjekti, template, pagese, email_i_paguesit, request, shtepi=None, stafit=False):
    """stafit=True: njoftimi automatik te stafi sapo regjistrohet pagesa (arkiv dhe monitorim i qarkullimit).
    stafit=False: butoni "Dërgo email" — vetëm te paguesi. Kthen listën e marrësve."""
    marrësit = emailat_e_stafit() if stafit else [e for e in [email_i_paguesit] if e]
    if not marrësit:
        return []
    msg = EmailMessage(
        subject=subjekti,
        body=render_to_string(template, {
            'pagese': pagese,
            'portali': llogarite.info(shtepi, _perdoruesi(request)) if shtepi else None,
        }, request=request),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=marrësit,
    )
    msg.content_subtype = 'html'
    msg.send()
    return marrësit


def njofto_stafin(pagese, request):
    """Email-i automatik te stafi për një pagesë të sapo regjistruar. Nuk e ndal kurrë regjistrimin:
    kthen None kur shkoi, ose tekstin e gabimit."""
    from .models import PagesaAntaresia, PagesaFondi
    dergo = (dërgo_email_antaresia if isinstance(pagese, PagesaAntaresia)
             else dërgo_email_fondi if isinstance(pagese, PagesaFondi) else dërgo_email_varrezat)
    try:
        dergo(pagese, request, stafit=True)
    except Exception as e:   # p.sh. Gmail pa lidhje — pagesa mbetet e regjistruar
        return str(e)[:200]
    return None


def dërgo_email_antaresia(pagese, request, stafit=False):
    lloji = f'Antarësia {pagese.vitet_tekst}'
    return _dergo(subjekti_fatures(pagese.shtepia.emri_i_plote, pagese, lloji),
                  'email/fatura_antaresia.html', pagese, pagese.shtepia.email, request, pagese.shtepia, stafit)


def dërgo_email_fondi(pagese, request, stafit=False):
    emri = pagese.shtepia.emri_i_plote if pagese.shtepia else f'{pagese.emri_donatorit} {pagese.mbiemri_donatorit}'
    lloji = f'Aktivitet: {pagese.arsyeja}' if pagese.eshte_aktivitet and pagese.arsyeja else (
        'Aktivitet' if pagese.eshte_aktivitet else 'Fondi')
    return _dergo(subjekti_fatures(emri, pagese, lloji), 'email/fatura_fondi.html', pagese,
                  pagese.email_donatorit, request, pagese.shtepia, stafit)


def dërgo_email_varrezat(pagese, request, stafit=False):
    lloji = f'Varrezat {pagese.vitet_tekst}'
    return _dergo(subjekti_fatures(pagese.shtepia.emri_i_plote, pagese, lloji),
                  'email/fatura_varrezat.html', pagese, pagese.shtepia.email, request, pagese.shtepia, stafit)
