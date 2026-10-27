"""
Letrat "Informim" për anëtarët me borxh — për postë (PDF, një letër për faqe) dhe për email.
Teksti bazohet në letrën e Këshillit të Xhamisë (Janar/2026); paragrafi dhe vërejtja mund të ndryshohen.
"""
from io import BytesIO

from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from .gjendja import gjendja_e_shtepive, vitet_tekst
from .models import KonfigurimiSistemit, Shtepia

MUAJT = ['Janar', 'Shkurt', 'Mars', 'Prill', 'Maj', 'Qershor', 'Korrik', 'Gusht',
         'Shtator', 'Tetor', 'Nëntor', 'Dhjetor']

PARAGRAFI = (
    'Ju lutemi që në kohë sa më të shpejtë të paraqiteni te arkëtari i xhamisë dhe të bëni pagesën e '
    'anëtarësisë, me qëllim të zhvillimit të aktiviteteve dhe jetës fetare në xhaminë tonë dhe më gjerë.'
)
VEREJTJA = (
    'Këshilli i Xhamisë së f. Pirok mori vendim që anëtarët e xhamisë të cilët nuk e kanë kryer pagesën '
    'vjetore, nënpunësit fetarë do të detyrohen të mos i kryejnë ritualet fetare që do të kenë nevojë. '
    'Ju falënderojmë për mirëkuptimin dhe shpresojmë në bashkëpunim të mëtutjeshëm.'
)


def data_e_sotme():
    sot = timezone.localdate()
    return f'{MUAJT[sot.month - 1]}/{sot.year}'


def periudha_tekst(vitet):
    """[2014..2025] → 'Prej 2014 deri 2025 = 12 vite'; me ndërprerje → 'Për vitet 2019, 2021–2025 = 6 vite'."""
    n = len(vitet)
    fjala = 'vit' if n == 1 else 'vite'
    if n == 1:
        return f'Për vitin {vitet[0]} = 1 vit'
    if vitet == list(range(vitet[0], vitet[-1] + 1)):
        return f'Prej {vitet[0]} deri {vitet[-1]} = {n} {fjala}'
    return f'Për vitet {vitet_tekst(vitet)} = {n} {fjala}'


def letrat_per(shtepite, viti_deri, min_vite=1):
    """Lista e letrave: vetëm shtëpitë aktive me së paku `min_vite` vite të papaguara deri në `viti_deri`."""
    shtepite = list(shtepite)
    gj = gjendja_e_shtepive(shtepite)
    tarifa = KonfigurimiSistemit.merr().tarifa_antaresise
    letrat = []
    for sh in shtepite:
        vitet = [v for v in gj[sh.id]['papaguara'] if v <= viti_deri]
        if len(vitet) < max(min_vite, 1):
            continue
        letrat.append({
            'shtepi': sh,
            'emri': f'{sh.emri_kryefamiljarit} {sh.mbiemri_kryefamiljarit}'.strip(),
            'vitet': vitet,
            'periudha': periudha_tekst(vitet),
            'borxhi': sum(tarifa(v) for v in vitet),
        })
    return letrat


def opsionet_nga(params):
    """Opsionet e letrës nga GET/POST, me vlera të paracaktuara."""
    viti_aktual = timezone.localdate().year
    try:
        viti_deri = int(params.get('viti_deri') or viti_aktual)
    except ValueError:
        viti_deri = viti_aktual
    try:
        min_vite = max(1, int(params.get('min_vite') or 1))
    except ValueError:
        min_vite = 1
    return {
        'viti_deri': viti_deri,
        'min_vite': min_vite,
        'vendi': (params.get('vendi') or 'PIROK').strip(),
        'data': (params.get('data') or data_e_sotme()).strip(),
        'afati': (params.get('afati') or '').strip(),
        'paragrafi': (params.get('paragrafi') or PARAGRAFI).strip(),
        'verejtja': (params.get('verejtja') or VEREJTJA).strip(),
        'me_shume': params.get('me_shume') == '1',
    }


def pdf(letrat, opsionet):
    html = render_to_string('letrat/letra_pdf.html', {'letrat': letrat, 'o': opsionet})
    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer, encoding='utf-8')
    return buffer.getvalue()


def teksti_email(letra, o):
    rreshtat = [
        f"Deri te z. {letra['emri']}, anëtar i xhamisë Pirok.",
        '',
        'Nëpërmjet kësaj thirrjeje ju informojmë se e keni të papaguar anëtarësinë e xhamisë për vitet:',
        f"{letra['periudha']}.",
    ]
    if o['me_shume']:
        rreshtat.append(f"Shuma minimale: {letra['borxhi']:.0f} €.")
    rreshtat += ['', o['paragrafi'], '', 'Vesselamu alejkum.', '', 'Këshilli i Xhamisë Pirok',
                 f"{o['vendi']}, {o['data']}", '', f"Vërejtje: {o['verejtja']}"]
    if o['afati']:
        rreshtat.append(f"Afati i pagesës deri më {o['afati']}.")
    return '\n'.join(rreshtat)
