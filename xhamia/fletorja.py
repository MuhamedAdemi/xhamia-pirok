"""
"Fletorja e antarësisë": lista e kryefamiljarëve me gjendjen Paguar/Borxh për çdo vit
(Borxh të vjetra | viti i kaluar … 4 vite përpara | Shënime).

- `rreshtat_e_fletores()` e ndërton fletoren nga të dhënat e aplikacionit (për shkarkim PDF/Excel).
- `lexo_fletoren()` + `krahaso()` lexojnë një fletore PDF dhe gjejnë ku aplikacioni ndryshon prej saj;
  `apliko()` i ruan korrigjimet e zgjedhura.
"""
import re
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from .gjendja import gjendja_e_shtepive, kategorite_gratis, vitet_tekst
from .models import PagesaAntaresia, Shtepia

PAGUAR, BORXH = 'Paguar', 'Borxh'
JO_ANETAR = '-'   # vit para fillimit të antarësisë (që leximi i PDF-së të mos i ngatërrojë vitet)


def vitet_e_fletores(viti_aktual=None):
    viti_aktual = viti_aktual or timezone.now().year
    return list(range(viti_aktual - 1, viti_aktual + 5))


def _vitet_e_mbuluara():
    """{shtepia_id: set(vitet)} — vitet që mbulohen nga pagesat e regjistruara në aplikacion."""
    mbuluara = defaultdict(set)
    for sh_id, nga, deri in PagesaAntaresia.objects.values_list('shtepia_id', 'viti', 'viti_deri'):
        mbuluara[sh_id].update(range(nga, (deri or nga) + 1))
    return mbuluara


def _kategoria_e_shumes(shuma, monedha):
    """Kategoria sipas shumës vjetore: 1 = 120 € / 7000–7300 den e më shumë, 2 = 100 € / 6000 den,
    3 = 80 € / 5000 den, 4 = 70 € / 4000–4300 den (e më pak)."""
    kufijte = (6500, 5500, 4650) if monedha == 'MKD' else (110, 90, 75)
    for nr, kufiri in enumerate(kufijte, 1):
        if shuma >= kufiri:
            return nr
    return 4


def kategorite_e_pagesave():
    """{shtepia_id: {viti: 1..4}} — kategoria e pagesës së regjistruar për çdo vit (shuma ndahet në vitet që mbulon)."""
    rezultati = defaultdict(dict)
    for p in PagesaAntaresia.objects.only('shtepia_id', 'viti', 'viti_deri', 'monedha', 'shuma_monedhe', 'shuma_paguar'):
        vitet = range(p.viti, (p.viti_deri or p.viti) + 1)
        if p.monedha == 'MKD' and p.shuma_monedhe:
            kat = _kategoria_e_shumes(p.shuma_monedhe / len(vitet), 'MKD')
        else:
            kat = _kategoria_e_shumes((p.shuma_paguar or 0) / len(vitet), 'EUR')
        for v in vitet:
            rezultati[p.shtepia_id][v] = min(kat, rezultati[p.shtepia_id].get(v, 4))
    return rezultati


def _eshte_paguar(sh, viti, mbuluara):
    return viti in mbuluara.get(sh.id, ()) or bool(sh.paguar_deri_viti and viti <= sh.paguar_deri_viti)


def rreshtat_e_fletores(shtepite=None, filtri='', vitet=None):
    """Rreshtat e fletores, me radhë alfabetike si fletorja në letër.
    filtri: '' (të gjitha), 'borxh' (kanë borxh), 'paguar' (pa borxh)."""
    viti_aktual = timezone.now().year
    vitet = vitet or vitet_e_fletores(viti_aktual)
    if shtepite is None:
        shtepite = Shtepia.objects.filter(është_aktiv=True).select_related('kategoria')
    shtepite = sorted(shtepite, key=lambda s: (s.emri_i_plote.lower(), s.nr_shtepise))
    gjendja = gjendja_e_shtepive(shtepite)
    mbuluara = _vitet_e_mbuluara()
    gratis = kategorite_gratis()

    rreshtat = []
    for sh in shtepite:
        g = gjendja[sh.id]
        if filtri == 'borxh' and not g['papaguara'] or filtri == 'paguar' and g['papaguara']:
            continue
        statuset = []
        for v in vitet:
            if v in g['papaguara']:
                statuset.append(BORXH)
            elif _eshte_paguar(sh, v, mbuluara):
                statuset.append(PAGUAR)
            elif v < sh.viti_fillimit_antaresise:
                statuset.append(JO_ANETAR)
            else:
                statuset.append('')
        parapaguar = viti_aktual
        while _eshte_paguar(sh, parapaguar + 1, mbuluara):
            parapaguar += 1
        te_vjetra = [v for v in g['papaguara'] if v < vitet[0]]
        rreshtat.append({
            'shtepia': sh,
            'gratis': sh.kategoria_id in gratis,
            'nr_viteve_te_vjetra': len(te_vjetra),
            'kategoria': sh.kategoria.emri if sh.kategoria else '',
            'borxh_te_vjetra': vitet_tekst(te_vjetra),
            'statuset': statuset,
            'shenime': f'Parapaguar deri më {parapaguar}' if parapaguar > viti_aktual and not g['papaguara'] else '',
            'borxhi': g['borxhi'],
        })
    for i, r in enumerate(rreshtat, 1):
        r['nr'] = i
    return vitet, rreshtat


# ─── Leximi i fletores PDF ─────────────────────────────────────────────────────

def normalizo_emrin(emri):
    """'Asllan Izairi empty' / 'Abdilaqim - Iljazi' / 'G�zim' → krahasim pa ndryshime të vogla."""
    s = emri.lower().replace('ë', 'e').replace('ç', 'c').replace('�', 'e')
    s = re.sub(r'\bempty\b', ' ', s)
    s = re.sub(r'(?<!\w)-(?!\w)', ' ', s)
    return ' '.join(s.split())


def lexo_fletoren(skedari):
    """Lexon fletoren PDF. Çdo qelizë del si rresht teksti më vete: Nr, Kryefamiljari, pastaj
    Paguar/Borxh për çdo vit me radhë (nga viti i parë i kokës) dhe ndoshta 'Parapaguar deri më …'.
    Kthen (viti_i_pare, [{'nr', 'emri', 'statuset': {viti: 'Paguar'|'Borxh'}}])."""
    from pypdf import PdfReader

    fjalet = []
    for faqja in PdfReader(skedari).pages:
        fjalet += [t.strip() for t in (faqja.extract_text() or '').splitlines() if t.strip()]

    viti_i_pare = None
    rreshtat, r = [], None
    for i, t in enumerate(fjalet):
        pas = fjalet[i + 1] if i + 1 < len(fjalet) else ''
        if viti_i_pare is None and re.fullmatch(r'20\d\d', t):
            viti_i_pare = int(t)          # koka: "… (2024, 2023...) 2025 2026 …"
        elif re.fullmatch(r'\d{1,5}', t) and pas and pas not in (PAGUAR, BORXH) and not re.fullmatch(r'\d+', pas):
            r = {'nr': int(t), 'emri': None, 'lista': []}
            rreshtat.append(r)
        elif r is not None and r['emri'] is None:
            r['emri'] = ' '.join(t.split())
        elif r is not None and t in (PAGUAR, BORXH):
            r['lista'].append(t)
        elif r is not None and t in (JO_ANETAR, '—', '�'):
            r['lista'].append(None)

    viti_i_pare = viti_i_pare or timezone.now().year - 1
    rezultati = []
    for r in rreshtat:
        statuset = {viti_i_pare + j: s for j, s in enumerate(r['lista']) if s}
        if r['emri'] and statuset:        # rreshtat pa asnjë status janë kokat e faqeve
            rezultati.append({'nr': r['nr'], 'emri': r['emri'], 'statuset': statuset})
    return viti_i_pare, rezultati


def _synimi(statuset):
    """Nga statuset e fletores → (viti i parë me borxh ose None, viti i fundit i paguar me radhë)."""
    vitet = sorted(statuset)
    borxh = [v for v in vitet if statuset[v] == BORXH]
    if borxh:
        return borxh[0], borxh[0] - 1
    return None, vitet[-1]


def _emra_te_ngjashem(emri, shtepite, sa=4):
    """Shtëpitë me emër të ngjashëm: i njëjti emër dhe mbiemër i ngjashëm (prindi mund të mungojë,
    të jetë i shkurtuar si "Xh" ose i ndryshuar), ose emri i plotë shumë i ngjashëm."""
    from difflib import SequenceMatcher

    fjalet = normalizo_emrin(emri).split()
    if not fjalet:
        return []
    pikët = []
    for sh in shtepite:
        e, pr, mb = (normalizo_emrin(x) for x in (sh.emri_kryefamiljarit, sh.emri_prindit, sh.mbiemri_kryefamiljarit))
        i_plote = SequenceMatcher(None, ' '.join(fjalet), normalizo_emrin(sh.emri_i_plote)).ratio()
        mbiemri = SequenceMatcher(None, fjalet[-1], mb).ratio() if mb else 0
        if e == fjalet[0] and mbiemri >= 0.8:
            prindi = fjalet[1] if len(fjalet) > 2 else ''
            perputhet_prindi = not prindi or not pr or pr.startswith(prindi) or prindi.startswith(pr)
            pikët.append((2 + mbiemri + (1 if perputhet_prindi else 0), sh))
        elif i_plote >= 0.85:
            pikët.append((i_plote, sh))
    pikët.sort(key=lambda x: -x[0])
    return [sh for _, sh in pikët[:sa]]


def krahaso(rreshtat_fletores, viti_i_pare):
    """Krahason fletoren me aplikacionin. Kthen raportin me listat:
    'korrigjime' (aplikacioni gabon — rekomandohet ndryshimi), 'konflikte' (ndryshimi do të fshinte
    borxhe të vjetra të aplikacionit — vendos stafi), 'me_pagese' (në aplikacion ka pagesë të regjistruar
    që e kundërshton fletoren — nuk preket), 'pa_gjetur', 'te_dyfishta', 'njejte' (numri)."""
    shtepite = list(Shtepia.objects.all())
    gjendja = gjendja_e_shtepive(shtepite)
    mbuluara = _vitet_e_mbuluara()
    sipas_emrit = defaultdict(list)
    for sh in shtepite:
        sipas_emrit[normalizo_emrin(sh.emri_i_plote)].append(sh)

    grupet = defaultdict(list)
    for r in rreshtat_fletores:
        grupet[normalizo_emrin(r['emri'])].append(r)

    raporti = {'korrigjime': [], 'konflikte': [], 'me_pagese': [], 'pa_gjetur': [], 'te_dyfishta': [],
               'njejte': 0, 'gjithsej': len(rreshtat_fletores), 'viti_i_pare': viti_i_pare}
    for celesi, rr in grupet.items():
        r = rr[0]
        if any(x['statuset'] != r['statuset'] for x in rr):
            raporti['te_dyfishta'].append(r['emri'])
            continue
        lista = sipas_emrit.get(celesi)
        if not lista:
            for x in rr:
                kandidatet = []
                for sh in _emra_te_ngjashem(x['emri'], shtepite):
                    borxh_nga, paguar_deri = _synimi(x['statuset'])
                    kandidatet.append({'shtepia': sh, 'propozimi': (borxh_nga or sh.viti_fillimit_antaresise, paguar_deri)})
                raporti['pa_gjetur'].append({'emri': x['emri'], 'kandidatet': kandidatet,
                                             'fletorja': [x['statuset'][v] for v in sorted(x['statuset'])]})
            continue
        for sh in lista:
            g = gjendja[sh.id]
            aplikacioni = {v: (BORXH if v in g['papaguara'] else PAGUAR if _eshte_paguar(sh, v, mbuluara) else '')
                           for v in r['statuset']}
            if aplikacioni == r['statuset']:
                raporti['njejte'] += 1
                continue
            rreshti = {
                'shtepia': sh, 'emri_fletores': r['emri'],
                'fletorja': [r['statuset'][v] for v in sorted(r['statuset'])],
                'aplikacioni': [aplikacioni[v] for v in sorted(r['statuset'])],
                'vitet': sorted(r['statuset']),
            }
            paguar_ne_app = [v for v, s in r['statuset'].items() if s == BORXH and v in mbuluara.get(sh.id, ())]
            if paguar_ne_app:
                rreshti['arsyeja'] = f'Në aplikacion është regjistruar pagesë për {vitet_tekst(sorted(paguar_ne_app))}.'
                raporti['me_pagese'].append(rreshti)
                continue
            borxh_nga, paguar_deri = _synimi(r['statuset'])
            fillimi = borxh_nga if borxh_nga else sh.viti_fillimit_antaresise
            rreshti['propozimi'] = (fillimi, paguar_deri)
            rreshti['pas'] = (f'Borxh nga {borxh_nga}' if borxh_nga else f'Paguar deri {paguar_deri}')
            te_vjetra = [v for v in g['papaguara'] if v < viti_i_pare]
            if te_vjetra:
                rreshti['arsyeja'] = (f'Aplikacioni ka borxh të vjetër {vitet_tekst(te_vjetra)}, ndërsa fletorja '
                                      f'thotë {viti_i_pare} i paguar — me ndryshim borxhi i vjetër fshihet.')
                raporti['konflikte'].append(rreshti)
            else:
                raporti['korrigjime'].append(rreshti)
    for k in ('korrigjime', 'konflikte', 'me_pagese'):
        raporti[k].sort(key=lambda x: x['shtepia'].emri_i_plote.lower())
    return raporti


def apliko(zgjedhjet, perdoruesi):
    """zgjedhjet: lista e tekstit 'id:fillimi:paguar_deri' nga formulari. Kthen numrin e shtëpive të ndryshuara."""
    data = timezone.localdate().strftime('%d.%m.%Y')
    ndryshuara = 0
    with transaction.atomic():
        for z in zgjedhjet:
            try:
                sh_id, fillimi, paguar_deri = (int(x) for x in z.split(':'))
            except ValueError:
                continue
            sh = Shtepia.objects.select_for_update().filter(pk=sh_id).first()
            if not sh or not (2000 <= fillimi <= 2100 and 2000 <= paguar_deri <= 2100):
                continue
            shenim = (f'{data}: korrigjuar sipas fletores nga {perdoruesi.get_full_name() or perdoruesi.username} '
                      f'(ishte: nga {sh.viti_fillimit_antaresise}, paguar deri {sh.paguar_deri_viti or "—"}).')
            sh.viti_fillimit_antaresise, sh.paguar_deri_viti = fillimi, paguar_deri
            sh.shenime = f'{sh.shenime}\n{shenim}'.strip()
            sh.save(update_fields=['viti_fillimit_antaresise', 'paguar_deri_viti', 'shenime'])
            ndryshuara += 1
    return ndryshuara


# ─── PDF ───────────────────────────────────────────────────────────────────────

def fletorja_pdf(vitet, rreshtat, data, filtri=''):
    """PDF A4 horizontale si fletorja në letër. Ndërtohet me reportlab direkt (xhtml2pdf është
    shumë i ngadaltë për ~1150 rreshta)."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    blu, gjelber, portokalli = colors.HexColor('#1F4E79'), colors.HexColor('#38761D'), colors.HexColor('#CC5500')
    titulli = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=15, textColor=blu, alignment=TA_CENTER)
    nen = ParagraphStyle('n', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#6E6E73'),
                         alignment=TA_CENTER)
    koka_st = ParagraphStyle('k', fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.white,
                             alignment=TA_CENTER, leading=9)

    pershkrimi = {'borxh': ' me borxh', 'paguar': ' pa borxh'}.get(filtri, '')
    koka = ['Nr.', 'Nr. Sh.', 'Kryefamiljari', 'Kategoria',
            Paragraph(f'Borxh të vjetra<br/>({vitet[0] - 1}, {vitet[0] - 2}...)', koka_st)] \
        + [str(v) for v in vitet] + ['Shënime']
    te_dhenat = [koka] + [
        [r['nr'], r['shtepia'].nr_shtepise, r['shtepia'].emri_i_plote, r['kategoria'], r['borxh_te_vjetra']]
        + r['statuset'] + [r['shenime']]
        for r in rreshtat
    ]
    gjeresite = [1.1 * cm, 1.3 * cm, 6.6 * cm, 2.2 * cm, 2.7 * cm] + [1.45 * cm] * len(vitet) + [4.6 * cm]
    stili = [
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 8),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('BACKGROUND', (0, 0), (-1, 0), blu),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 1), (1, -1), 'CENTER'),
        ('ALIGN', (4, 1), (-2, -1), 'CENTER'),
        ('TEXTCOLOR', (4, 1), (4, -1), colors.HexColor('#CC0000')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D9DEE7')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F6F8FB')]),
        ('TOPPADDING', (0, 1), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 2.5),
    ]
    for i, r in enumerate(rreshtat, 1):
        for j, s in enumerate(r['statuset']):
            if s == PAGUAR:
                stili += [('TEXTCOLOR', (5 + j, i), (5 + j, i), gjelber),
                          ('FONT', (5 + j, i), (5 + j, i), 'Helvetica-Bold', 8)]
            elif s == BORXH:
                stili.append(('TEXTCOLOR', (5 + j, i), (5 + j, i), portokalli))
            elif s == JO_ANETAR:
                stili.append(('TEXTCOLOR', (5 + j, i), (5 + j, i), colors.HexColor('#AEAEB2')))
    tabela = LongTable(te_dhenat, colWidths=gjeresite, repeatRows=1)
    tabela.setStyle(TableStyle(stili))

    def fundi(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#6E6E73'))
        canvas.drawRightString(doc.pagesize[0] - 1.2 * cm, 0.7 * cm,
                               f'Xhamia Pirok — Fletorja e antarësisë, {data.strftime("%d.%m.%Y")} — faqja {doc.page}')
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=1.1 * cm, bottomMargin=1.3 * cm,
                            title='Fletorja e antarësisë', author='Xhamia Pirok')
    doc.build([
        Paragraph('LISTA E ANËTARËVE DHE EVIDENCA E PAGESAVE', titulli), Spacer(1, 4),
        Paragraph(f'Gjendja më {data.strftime("%d.%m.%Y")} · {len(rreshtat)} kryefamiljarë{pershkrimi}', nen),
        Spacer(1, 8), tabela,
    ], onFirstPage=fundi, onLaterPages=fundi)
    return buffer.getvalue()
