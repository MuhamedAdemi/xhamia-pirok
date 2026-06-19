from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from .models import ProfilStafi


def _marrësit_email():
    """Merr emailet e stafit që kanë aktivizuar njoftimet."""
    return list(
        ProfilStafi.objects.filter(
            merr_email_pagese=True, është_aktiv=True
        ).values_list('user__email', flat=True)
    )


def dërgo_email_antaresia(pagese, request):
    marrësit = _marrësit_email()
    if pagese.shtepia.email:
        marrësit.append(pagese.shtepia.email)
    marrësit = list(set(filter(None, marrësit)))
    if not marrësit:
        return

    html = render_to_string('email/fatura_antaresia.html', {'pagese': pagese}, request=request)
    msg = EmailMessage(
        subject=f'Fatura {pagese.nr_fatures} — Xhamia Pirok',
        body=html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=marrësit,
    )
    msg.content_subtype = 'html'
    msg.send()


def dërgo_email_fondi(pagese, request):
    marrësit = _marrësit_email()
    if pagese.email_donatorit:
        marrësit.append(pagese.email_donatorit)
    marrësit = list(set(filter(None, marrësit)))
    if not marrësit:
        return

    html = render_to_string('email/fatura_fondi.html', {'pagese': pagese}, request=request)
    msg = EmailMessage(
        subject=f'Fatura {pagese.nr_fatures} — Fondi i Xhamisë Pirok',
        body=html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=marrësit,
    )
    msg.content_subtype = 'html'
    msg.send()
