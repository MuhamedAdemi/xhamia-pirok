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


def _dergo(subjekti, template, pagese, email_i_paguesit, request, shtepi=None):
    """Fatura shkon gjithmonë te emailat zyrtarë (arkëtari, këshilli, imami) — si arkiv dhe për monitorim —
    dhe te paguesi kur ka email. Kthen listën e marrësve."""
    marrësit = list(dict.fromkeys(filter(None, list(settings.EMAILET_ZYRTARE) + [email_i_paguesit])))
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


def dërgo_email_antaresia(pagese, request):
    lloji = f'Antarësia {pagese.vitet_tekst}'
    return _dergo(subjekti_fatures(pagese.shtepia.emri_i_plote, pagese, lloji),
                  'email/fatura_antaresia.html', pagese, pagese.shtepia.email, request, pagese.shtepia)


def dërgo_email_fondi(pagese, request):
    emri = pagese.shtepia.emri_i_plote if pagese.shtepia else f'{pagese.emri_donatorit} {pagese.mbiemri_donatorit}'
    lloji = f'Aktivitet: {pagese.arsyeja}' if pagese.eshte_aktivitet and pagese.arsyeja else (
        'Aktivitet' if pagese.eshte_aktivitet else 'Fondi')
    return _dergo(subjekti_fatures(emri, pagese, lloji), 'email/fatura_fondi.html', pagese,
                  pagese.email_donatorit, request, pagese.shtepia)


def dërgo_email_varrezat(pagese, request):
    lloji = f'Varrezat {pagese.vitet_tekst}'
    return _dergo(subjekti_fatures(pagese.shtepia.emri_i_plote, pagese, lloji),
                  'email/fatura_varrezat.html', pagese, pagese.shtepia.email, request, pagese.shtepia)
