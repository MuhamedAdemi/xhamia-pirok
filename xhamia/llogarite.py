"""
Llogaritë e portalit të shtëpive (përdoruesi "sh0254"): krijim me fjalëkalimin fillestar 123456,
rivendosje nga arkëtari, rivendosje me SMS kur e harrojnë, dhe teksti me të dhënat e hyrjes
që i shtohet SMS-it / email-it të pagesës.
"""
import secrets

from django.conf import settings
from django.contrib.auth.models import User

from .models import ProfilShtepi

FJALEKALIMI_FILLESTAR = '123456'


def emri_perdoruesit(shtepi):
    return f'sh{shtepi.nr_shtepise}'


def adresa_e_portalit():
    return getattr(settings, 'SITE_URL', 'https://xhamiapirok.pythonanywhere.com').rstrip('/')


def siguro_llogarine(shtepi, krijuar_nga=None):
    """Kthen ProfilShtepi e shtëpisë; nëse s'ka, e krijon me fjalëkalimin fillestar."""
    profil = ProfilShtepi.objects.filter(shtepia=shtepi).select_related('user').first()
    if profil:
        return profil
    user = User.objects.filter(username=emri_perdoruesit(shtepi)).first()
    if user is None:
        user = User.objects.create_user(
            username=emri_perdoruesit(shtepi), password=FJALEKALIMI_FILLESTAR,
            first_name=shtepi.emri_kryefamiljarit, last_name=shtepi.mbiemri_kryefamiljarit,
            email=shtepi.email or '',
        )
    else:
        user.set_password(FJALEKALIMI_FILLESTAR)
        user.save(update_fields=['password'])
    return ProfilShtepi.objects.create(user=user, shtepia=shtepi, krijuar_nga=krijuar_nga,
                                       fjalekalimi_fillestar=True)


def rivendos(profil, fjalekalimi=FJALEKALIMI_FILLESTAR):
    profil.user.set_password(fjalekalimi)
    profil.user.save(update_fields=['password'])
    profil.fjalekalimi_fillestar = True
    profil.save(update_fields=['fjalekalimi_fillestar'])


def fjalekalim_i_perkohshem():
    """6 shifra të rastësishme — për rivendosjen me SMS (e di vetëm pronari i telefonit)."""
    return f'{secrets.randbelow(1_000_000):06d}'


def info(shtepi, krijuar_nga=None):
    """Të dhënat e hyrjes për t'ia treguar familjes. Fjalëkalimi tregohet vetëm sa është ende ai fillestar."""
    profil = siguro_llogarine(shtepi, krijuar_nga)
    return {
        'adresa': adresa_e_portalit(),
        'perdoruesi': profil.user.username,
        'fjalekalimi': FJALEKALIMI_FILLESTAR if profil.fjalekalimi_fillestar else None,
    }


def rreshti_sms(shtepi, krijuar_nga=None):
    i = info(shtepi, krijuar_nga)
    adresa = i['adresa'].replace('https://', '')
    teksti = f" Pagesat tuaja online: {adresa} perdoruesi {i['perdoruesi']}"
    if i['fjalekalimi']:
        teksti += f" fjalekalimi {i['fjalekalimi']} (mund ta ndryshoni)"
    return teksti + '.'
