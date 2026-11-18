"""
Njoftime / urime për gjithë xhematin: një SMS te të gjithë që kanë telefon, ose një email (me foto opsionale)
te të gjithë që kanë email. Dërgohet me valë — çdo klikim dërgon një pjesë, sepse:
  - PythonAnywhere e ndërpret kërkesën që zgjat shumë;
  - Gmail lejon ~500 marrës në ditë;
  - telefoni i xhamisë i dërgon SMS-të një nga një.
`Njoftim.derguar` mban mend kujt i ka shkuar, prandaj "Vazhdo dërgimin" nuk i dërgon askujt dy herë.
"""
from email.mime.image import MIMEImage
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from . import sms
from .models import Shtepia

VALA_SMS = 200          # numra për një klikim
SMS_NE_KERKESE = 20     # numra në një kërkesë te SMSGate
VALA_EMAIL = 100        # email-e për një klikim
EMAIL_NE_MESAZH = 50    # marrës (BCC) në një email
GMAIL_NE_DITE = 450     # kufiri i sigurt i Gmail-it falas (~500 në ditë)


def marresit(kanali):
    """[(marrësi, shtepia)] pa përsëritje — numrat e normalizuar ose email-et me shkronja të vogla."""
    pare, lista = set(), []
    shtepite = Shtepia.objects.filter(është_aktiv=True).order_by('nr_shtepise')
    for sh in shtepite.only('id', 'nr_shtepise', 'nr_telefoni_kryesor', 'email'):
        if kanali == 'SMS':
            m = sms.normalizo_numrin(sh.nr_telefoni_kryesor)
        else:
            m = (sh.email or '').strip().lower()
            try:
                validate_email(m)
            except ValidationError:
                m = None
        if m and m not in pare:
            pare.add(m)
            lista.append((m, sh))
    return lista


def te_mbetur(njoftim):
    derguar = set(njoftim.derguar)
    return [(m, sh) for m, sh in marresit(njoftim.kanali) if m not in derguar]


def _emaili(njoftim, bcc):
    paragrafet = ''.join(f'<p style="margin:0 0 12px;">{escape(p).replace(chr(10), "<br>")}</p>'
                         for p in njoftim.teksti.split('\n\n') if p.strip())
    foto = '<p style="text-align:center;"><img src="cid:foto" style="max-width:100%; border-radius:8px;"></p>' if njoftim.foto else ''
    html = f'''<div style="font-family:Arial,sans-serif; max-width:640px; margin:auto; color:#1C1C1E;">
  <div style="background:#2D5A1B; color:#fff; padding:16px 20px; border-radius:10px 10px 0 0;">
    <strong style="font-size:18px;">🕌 Xhamia Pirok</strong></div>
  <div style="border:1px solid #DDD; border-top:none; padding:20px; border-radius:0 0 10px 10px; font-size:15px; line-height:1.5;">
    <h2 style="margin:0 0 14px; font-size:19px;">{escape(njoftim.titulli)}</h2>{foto}{paragrafet}
    <p style="color:#888; font-size:12px; margin-top:20px;">Xhamia Pirok · f. Pirok, Tetovë</p></div></div>'''
    msg = EmailMultiAlternatives(subject=njoftim.titulli, body=njoftim.teksti, from_email=settings.DEFAULT_FROM_EMAIL,
                                 to=[settings.EMAIL_HOST_USER], bcc=bcc)
    msg.attach_alternative(html, 'text/html')
    if njoftim.foto:
        msg.mixed_subtype = 'related'
        img = MIMEImage(bytes(njoftim.foto), _subtype=(njoftim.foto_lloji.split('/')[-1] or 'jpeg'))
        img.add_header('Content-ID', '<foto>')
        img.add_header('Content-Disposition', 'inline', filename=njoftim.foto_emri or 'foto.jpg')
        msg.attach(img)
    return msg


def dergo_valen(njoftim, perdoruesi):
    """Dërgon valën e radhës. Kthen (të_dërguara, të_dështuara, të_mbetura)."""
    mbetur = te_mbetur(njoftim)
    if njoftim.kanali == 'SMS':
        vala = mbetur[:VALA_SMS]
        pjeset = [vala[i:i + SMS_NE_KERKESE] for i in range(0, len(vala), SMS_NE_KERKESE)]
    else:
        vala = mbetur[:VALA_EMAIL]
        pjeset = [vala[i:i + EMAIL_NE_MESAZH] for i in range(0, len(vala), EMAIL_NE_MESAZH)]
    ok = deshtuar = 0
    for pjesa in pjeset:
        if njoftim.kanali == 'SMS':
            mesazhet = sms.dergo_sms_shumeve(pjesa, njoftim.teksti, 'NJOFTIM', perdoruesi, ttl=24 * 3600)
            for m in mesazhet:
                if m.statusi == 'DESHTOI':
                    njoftim.deshtuar[m.nr_telefoni] = m.gabimi
                    deshtuar += 1
                else:
                    njoftim.derguar.append(m.nr_telefoni)
                    ok += 1
        else:
            adresat = [m for m, _ in pjesa]
            try:
                _emaili(njoftim, adresat).send()
                njoftim.derguar.extend(adresat)
                ok += len(adresat)
            except Exception as e:   # p.sh. Gmail: kufiri ditor — ndalet; vazhdohet më vonë
                for a in adresat:
                    njoftim.deshtuar[a] = str(e)[:200]
                deshtuar += len(adresat)
                break
        njoftim.save(update_fields=['derguar', 'deshtuar'])
    return ok, deshtuar, len(mbetur) - ok


def dergo_prove(njoftim, marresi, perdoruesi):
    """Provë vetëm te një numër / email (nuk shënohet si i dërguar)."""
    if njoftim.kanali == 'SMS':
        numri = sms.normalizo_numrin(marresi)
        if not numri:
            return 'Numri i provës nuk është i vlefshëm.'
        m = sms.dergo_sms_shumeve([(numri, None)], njoftim.teksti, 'NJOFTIM', perdoruesi, ttl=3600)[0]
        return m.gabimi if m.statusi == 'DESHTOI' else None
    try:
        validate_email(marresi)
        _emaili(njoftim, [marresi]).send()
    except Exception as e:
        return str(e)[:200]
    return None
