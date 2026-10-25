"""
Dërgimi i SMS-ve përmes aplikacionit "SMS Gateway for Android" (https://sms-gate.app).

SMS-i dërgohet nga SIM-i i telefonit Android ku është instaluar aplikacioni,
pra marrësi e sheh numrin real të xhamisë si dërgues. Serveri ynë i dërgon
kërkesë api.sms-gate.app (i lejuar edhe në PythonAnywhere falas), dhe ai ia
kalon telefonit përmes internetit.
"""
import re

import requests
from django.conf import settings

from .models import KonfigurimiSistemit, MesazhSMS

TIMEOUT = 15

# Një SMS konfirmimi pa përgjigje nga telefoni brenda kaq sekondash anulohet dhe skadon te gateway-i,
# që telefoni të mos e dërgojë më vonë (p.sh. kur i kthehet interneti) — dhe lejohet SMS i ri.
AFATI_PERGJIGJES = 120
# Kujtesat masive presin më gjatë në radhë (telefoni i dërgon njëra pas tjetrës).
AFATI_KUJTESAVE = 3600

# Shkronjat jashtë alfabetit GSM e kthejnë SMS-in në Unicode (70 karaktere në
# vend të 160), që e dyfishon numrin e SMS-ve. Prandaj i zëvendësojmë.
_ZEVENDESIMET = str.maketrans({
    'ë': 'e', 'Ë': 'E', 'ç': 'c', 'Ç': 'C',
    '—': '-', '–': '-', '’': "'", '‘': "'", '“': '"', '”': '"',
})


def pastro_tekstin(teksti):
    return teksti.translate(_ZEVENDESIMET).strip()


def normalizo_numrin(nr):
    """Kthen numrin në formatin ndërkombëtar (+389...), ose None nëse s'është i vlefshëm."""
    if not nr:
        return None
    nr = re.sub(r'[\s\-/().]', '', nr)
    if nr.startswith('00'):
        nr = '+' + nr[2:]
    elif nr.startswith('389'):
        nr = '+' + nr
    elif nr.startswith('0'):
        nr = '+389' + nr[1:]
    elif not nr.startswith('+') and len(nr) == 8 and nr.startswith('7'):
        nr = '+389' + nr
    if not re.fullmatch(r'\+\d{8,15}', nr):
        return None
    return nr


def _auth():
    """Kredencialet nga faqja "SMS & Email"; nëse s'janë vendosur atje, nga settings."""
    k = KonfigurimiSistemit.merr()
    if k.sms_username and k.sms_password:
        return (k.sms_username.strip(), k.sms_password.strip())
    return (settings.SMS_GATEWAY_USER, settings.SMS_GATEWAY_PASSWORD)


def _trupi(teksti, numri, ttl=None, prioriteti=0):
    trupi = {'textMessage': {'text': teksti}, 'phoneNumbers': [numri], 'priority': prioriteti}
    if ttl:
        trupi['ttl'] = ttl
    sim = KonfigurimiSistemit.merr().sms_sim_numri
    if sim:
        trupi['simNumber'] = sim
    return trupi


def eshte_konfiguruar():
    return all(_auth())


def dergo_sms(nr_telefoni, teksti, lloji, dërguar_nga, shtepia=None, ttl=None, prioriteti=0):
    """Dërgon një SMS dhe e ruan në regjistër. Kthen objektin MesazhSMS.
    `ttl` (sekonda): nëse telefoni nuk e merr brenda këtij afati, SMS-i skadon dhe nuk dërgohet më."""
    teksti = pastro_tekstin(teksti)
    numri = normalizo_numrin(nr_telefoni)
    mesazh = MesazhSMS(
        nr_telefoni=numri or (nr_telefoni or ''),
        teksti=teksti,
        lloji=lloji,
        shtepia=shtepia,
        dërguar_nga=dërguar_nga,
    )

    if not numri:
        mesazh.statusi = 'DESHTOI'
        mesazh.gabimi = 'Numri i telefonit nuk është i vlefshëm.'
    elif not eshte_konfiguruar():
        mesazh.statusi = 'DESHTOI'
        mesazh.gabimi = 'SMS Gateway nuk është konfiguruar — plotësoni faqen "SMS & Email".'
    else:
        try:
            r = requests.post(
                settings.SMS_GATEWAY_URL,
                json=_trupi(teksti, numri, ttl, prioriteti),
                auth=_auth(),
                timeout=TIMEOUT,
            )
            if r.status_code == 401:
                raise requests.RequestException(
                    'Username ose Password i gabuar — kontrolloni faqen "SMS & Email".'
                )
            r.raise_for_status()
            të_dhënat = r.json()
            mesazh.id_gateway = të_dhënat.get('id', '')
            mesazh.statusi = _statusi_nga_gateway(të_dhënat.get('state'))
        except requests.RequestException as e:
            mesazh.statusi = 'DESHTOI'
            mesazh.gabimi = str(e)[:500]
        except ValueError:
            mesazh.statusi = 'NE_PRITJE'

    mesazh.save()
    return mesazh


def perditeso_statusin(mesazh):
    """Pyet gateway-n për statusin aktual të një SMS-je të dërguar."""
    if not mesazh.id_gateway or not eshte_konfiguruar():
        return mesazh
    try:
        r = requests.get(
            f"{settings.SMS_GATEWAY_URL}/{mesazh.id_gateway}",
            auth=_auth(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        të_dhënat = r.json()
    except (requests.RequestException, ValueError):
        return mesazh

    mesazh.statusi = _statusi_nga_gateway(të_dhënat.get('state'))
    if mesazh.statusi == 'DESHTOI':
        arsyet = [m.get('error') for m in të_dhënat.get('recipients', []) if m.get('error')]
        mesazh.gabimi = (', '.join(arsyet) or të_dhënat.get('reason') or 'Dështoi në telefon.')[:500]
    mesazh.save(update_fields=['statusi', 'gabimi'])
    return mesazh


def anulo(mesazh, arsyeja):
    """Anulon te gateway-i një SMS që ende nuk është dërguar dhe e shënon si të dështuar."""
    if mesazh.id_gateway and eshte_konfiguruar():
        try:
            requests.delete(f"{settings.SMS_GATEWAY_URL}/{mesazh.id_gateway}", auth=_auth(), timeout=TIMEOUT)
        except requests.RequestException:
            pass    # edhe pa anulim, afati (ttl) e skadon vetë te gateway-i
    mesazh.statusi, mesazh.gabimi = 'DESHTOI', arsyeja[:500]
    mesazh.save(update_fields=['statusi', 'gabimi'])
    return mesazh


def sms_ne_pritje():
    """SMS-të e konfirmimit që ende presin përgjigje nga telefoni. Ato që e kanë kaluar afatin anulohen.
    Kthen listën e atyre që janë ende brenda afatit (pra: duhet pritur)."""
    from datetime import timedelta
    from django.utils import timezone
    tani = timezone.now()
    ne_pritje = []
    for m in MesazhSMS.objects.filter(
        lloji='KONFIRMIM', statusi='NE_PRITJE', data_dergimit__gte=tani - timedelta(days=1),
    ):
        perditeso_statusin(m)
        if m.statusi != 'NE_PRITJE':
            continue
        if (tani - m.data_dergimit).total_seconds() > AFATI_PERGJIGJES:
            anulo(m, f'Anuluar: telefoni nuk u përgjigj brenda {AFATI_PERGJIGJES // 60} minutave '
                     '(pa internet ose i fikur). Mund të dërgohet sërish.')
        else:
            ne_pritje.append(m)
    return ne_pritje


def prit_pergjigjen(mesazh, sekonda=None):
    """Pret disa sekonda që telefoni ta dërgojë SMS-in; kthen mesazhin me statusin e fundit."""
    import time
    sekonda = getattr(settings, 'SMS_PRIT_SEKONDA', 10) if sekonda is None else sekonda
    while sekonda > 0 and mesazh.statusi == 'NE_PRITJE' and mesazh.id_gateway:
        time.sleep(2)
        sekonda -= 2
        perditeso_statusin(mesazh)
    return mesazh


def _statusi_nga_gateway(state):
    return {
        'Sent': 'DERGUAR',
        'Delivered': 'DORZUAR',
        'Failed': 'DESHTOI',
        'Cancelled': 'DESHTOI',
    }.get(state, 'NE_PRITJE')


# ─── Tekstet e SMS-ve ────────────────────────────────────────────────────────

def _shuma(pagese):
    return pagese.shuma_origjinale.replace('€', 'EUR')


def _vitet(pagese):
    return f"vitet {pagese.vitet_tekst}" if pagese.nr_viteve > 1 else f"vitin {pagese.viti}"


def teksti_antaresia(pagese):
    return (
        f"Xhamia Pirok: U pranua pagesa juaj prej {_shuma(pagese)} "
        f"per antaresine per {_vitet(pagese)}. Fatura: {pagese.fatura_tekst}. "
        f"Allahu ju shperbleft!"
    )


def teksti_varrezat(pagese):
    return (
        f"Xhamia Pirok: U pranua pagesa juaj prej {_shuma(pagese)} "
        f"per mirembajtjen e varrezave per {_vitet(pagese)}. Fatura: {pagese.fatura_tekst}. "
        f"Allahu ju shperbleft!"
    )


def teksti_fondi(pagese):
    if pagese.lloji == 'AKTIVITET':
        per = f"per aktivitetin {pagese.arsyeja}" if pagese.arsyeja else "per aktivitetin"
        return (
            f"Xhamia Pirok: U pranua pagesa juaj prej {_shuma(pagese)} {per}. "
            f"Fatura: {pagese.fatura_tekst}. Allahu ju shperbleft!"
        )
    return (
        f"Xhamia Pirok: U pranua donacioni juaj prej {_shuma(pagese)} per xhamine. "
        f"Fatura: {pagese.fatura_tekst}. Allahu ju shperbleft!"
    )


TEKSTI_KUJTESES_PARACAKTUAR = (
    "Xhamia Pirok: I nderuar {emri}, sipas evidences sone keni antaresi te papaguar "
    "per vitet {vitet} (gjithsej {borxhi} EUR). Ju lutemi kontaktoni xhamine. Faleminderit!"
)
