"""
Dokumentet Word (.docx) për printim në A4: fletorja e antarësisë dhe letrat "Informim" (2 në një faqe).
"""
from io import BytesIO

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .fletorja import BORXH, JO_ANETAR, PAGUAR, kategorite_e_pagesave

BLU = RGBColor(0x1F, 0x4E, 0x79)
GRI = RGBColor(0x8E, 0x8E, 0x93)


def _dokumenti(landscape=False, margjina=1.2):
    doc = Document()
    stili = doc.styles['Normal']
    stili.font.name = 'Arial'
    stili.font.size = Pt(9)
    stili.paragraph_format.space_after = Pt(0)
    stili.paragraph_format.space_before = Pt(0)
    seksioni = doc.sections[0]
    seksioni.page_width, seksioni.page_height = Cm(21), Cm(29.7)
    if landscape:
        seksioni.orientation = WD_ORIENT.LANDSCAPE
        seksioni.page_width, seksioni.page_height = Cm(29.7), Cm(21)
    for ana in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'):
        setattr(seksioni, ana, Cm(margjina))
    return doc


def _ruaj(doc):
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _hije(qeliza, ngjyra):
    tcPr = qeliza._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), ngjyra)
    tcPr.append(shd)


def _perserit_koken(rreshti):
    trPr = rreshti._tr.get_or_add_trPr()
    el = OxmlElement('w:tblHeader')
    el.set(qn('w:val'), 'true')
    trPr.append(el)


def _mos_ndaj(rreshti):
    trPr = rreshti._tr.get_or_add_trPr()
    trPr.append(OxmlElement('w:cantSplit'))


def _shkruaj(qeliza, teksti, madhesia=9, bold=False, ngjyra=None, qender=False):
    p = qeliza.paragraphs[0]
    if qender:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(str(teksti))
    run.font.size = Pt(madhesia)
    run.bold = bold
    if ngjyra:
        run.font.color.rgb = ngjyra
    return run


# ─── Fletorja ──────────────────────────────────────────────────────────────────

def vlera_e_vitit(r, j, viti, kategorite):
    """Çka shkruhet në qelizën e vitit: kategoria 1–4 kur ka pagesë të regjistruar, ✓ kur dihet vetëm se
    ka paguar, bosh kur ka borxh, – kur nuk ishte anëtar, G kur është i liruar."""
    if r['gratis']:
        return 'G'
    s = r['statuset'][j]
    if s == PAGUAR:
        return str(kategorite.get(r['shtepia'].id, {}).get(viti, '✓'))
    if s == JO_ANETAR:
        return '–'
    return ''


def fletorja_word(vitet, rreshtat, data, filtri=''):
    kategorite = kategorite_e_pagesave()
    landscape = len(vitet) > 4
    doc = _dokumenti(landscape)
    gjeresia_faqes = 27.3 if landscape else 18.6

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('LISTA E ANËTARËVE DHE EVIDENCA E PAGESAVE')
    run.bold, run.font.size, run.font.color.rgb = True, Pt(13), BLU
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pershkrimi = {'borxh': ' me borxh', 'paguar': ' pa borxh'}.get(filtri, '')
    run = p.add_run(f'Gjendja më {data.strftime("%d.%m.%Y")} · {len(rreshtat)} kryefamiljarë{pershkrimi}   ·   '
                    f'1–4 = kategoria e pagesës · ✓ = paguar · bosh = pa paguar · – = s\'ishte anëtar · G = i liruar')
    run.font.size, run.font.color.rgb = Pt(7.5), GRI
    p.paragraph_format.space_after = Pt(6)

    koka = ['Nr.', 'Emri', 'Emri i prindit', 'Mbiemri', 'Kat.', 'Borxh'] + [str(v) for v in vitet]
    fikse = [0.9, 3.1, 2.6, 3.3, 1.0, 1.2]
    viti_gj = max(1.0, (gjeresia_faqes - sum(fikse)) / len(vitet))
    gjeresite = [Cm(g) for g in fikse + [viti_gj] * len(vitet)]

    tabela = doc.add_table(rows=1, cols=len(koka))
    tabela.style = 'Table Grid'
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabela.autofit = False
    for i, (q, t) in enumerate(zip(tabela.rows[0].cells, koka)):
        q.width = gjeresite[i]
        _shkruaj(q, t, 8.5, bold=True, ngjyra=RGBColor(0xFF, 0xFF, 0xFF), qender=True)
        _hije(q, '1F4E79')
    _perserit_koken(tabela.rows[0])

    for r in rreshtat:
        sh = r['shtepia']
        vlerat = [r['nr'], sh.emri_kryefamiljarit, sh.emri_prindit, sh.mbiemri_kryefamiljarit,
                  'G' if r['gratis'] else '', r['nr_viteve_te_vjetra'] or '']
        vlerat += [vlera_e_vitit(r, j, v, kategorite) for j, v in enumerate(vitet)]
        rreshti = tabela.add_row()
        _mos_ndaj(rreshti)
        for i, (q, v) in enumerate(zip(rreshti.cells, vlerat)):
            q.width = gjeresite[i]
            if i == 5 and v:
                _shkruaj(q, v, 9, bold=True, ngjyra=RGBColor(0xCC, 0x00, 0x00), qender=True)
            elif i >= 6 and v == '✓':
                _shkruaj(q, v, 7, ngjyra=GRI, qender=True)
            elif i >= 6:
                _shkruaj(q, v, 9, bold=True, qender=True)
            else:
                _shkruaj(q, v, 9, qender=i in (0, 4))
    return _ruaj(doc)


# ─── Letrat "Informim" ──────────────────────────────────────────────────────────

def _paragraf(qeliza, i_pari=False, para=4, pas=4, rreshtimi=None):
    p = qeliza.paragraphs[0] if i_pari else qeliza.add_paragraph()
    p.paragraph_format.space_before = Pt(para)
    p.paragraph_format.space_after = Pt(pas)
    if rreshtimi is not None:
        p.alignment = rreshtimi
    return p


def _run(p, teksti, madhesia=11, bold=False, italic=False, nenvize=False, fonti=None):
    run = p.add_run(teksti)
    run.font.size = Pt(madhesia)
    run.bold, run.italic, run.underline = bold, italic, nenvize
    if fonti:
        run.font.name = fonti
    return run


def _letra(qeliza, l, o, gjeresia):
    p = _paragraf(qeliza, i_pari=True, para=2, pas=0, rreshtimi=WD_ALIGN_PARAGRAPH.RIGHT)
    _run(p, 'KËSHILLI I XHAMISË\nPIROK', 10, bold=True, fonti='Times New Roman')
    p = _paragraf(qeliza, para=0, pas=10, rreshtimi=WD_ALIGN_PARAGRAPH.CENTER)
    _run(p, 'Informim', 14, bold=True)

    p = _paragraf(qeliza, pas=8)
    _run(p, 'Deri te z. ', italic=True)
    _run(p, l['emri_plote'], 12, bold=True, nenvize=True)
    _run(p, '  anëtar i xhamisë Pirok.', italic=True)

    p = _paragraf(qeliza, pas=8)
    _run(p, 'Nëpërmjet kësaj thirrjeje ju informojmë se e keni të papaguar anëtarësinë e xhamisë edhe atë për vitet:',
         italic=True)
    p = _paragraf(qeliza, pas=8)
    _run(p, l['periudha'], 11, bold=True, italic=True, nenvize=True)
    if o['me_shume']:
        _run(p, f"   (shuma minimale: {l['borxhi']:.0f} €)", 10, italic=True)

    p = _paragraf(qeliza, pas=8, rreshtimi=WD_ALIGN_PARAGRAPH.JUSTIFY)
    _run(p, o['paragrafi'], italic=True)
    p = _paragraf(qeliza, pas=10, rreshtimi=WD_ALIGN_PARAGRAPH.CENTER)
    _run(p, 'Vesselamu alejkum...', italic=True)

    p = _paragraf(qeliza, pas=10)
    p.paragraph_format.tab_stops.add_tab_stop(gjeresia - Cm(0.5), WD_TAB_ALIGNMENT.RIGHT)
    _run(p, f"  {o['vendi']}\t", italic=True)
    _run(p, 'Këshilli i xhamisë Pirok', italic=True)
    p.add_run().add_break()
    _run(p, f"  {o['data']}", italic=True)

    p = _paragraf(qeliza, pas=2, rreshtimi=WD_ALIGN_PARAGRAPH.JUSTIFY)
    _run(p, 'Vërejtje: ', 8, bold=True, italic=True, fonti='Times New Roman')
    _run(p, o['verejtja'], 8, bold=True, italic=True, fonti='Times New Roman')
    if o['afati']:
        p = _paragraf(qeliza, para=0, pas=0)
        _run(p, f"Afati i pagesës deri më {o['afati']}.", 8, bold=True, nenvize=True, fonti='Times New Roman')
    p = _paragraf(qeliza, para=2, pas=0, rreshtimi=WD_ALIGN_PARAGRAPH.RIGHT)
    _run(p, f"Shtëpia nr. {l['shtepi'].nr_shtepise}", 7).font.color.rgb = GRI


def letrat_word(letrat, o):
    """Dy letra në një faqe A4, secila në kornizën e vet (vija mes tyre shërben për prerje)."""
    doc = _dokumenti(margjina=1.0)
    gjeresia = Cm(19)
    for i in range(0, len(letrat), 2):
        cifti = letrat[i:i + 2]
        if i:
            p = doc.add_paragraph()
            p.paragraph_format.page_break_before = True
            _run(p, '', 1)
        tabela = doc.add_table(rows=len(cifti), cols=1)
        tabela.style = 'Table Grid'
        tabela.autofit = False
        for rreshti, l in zip(tabela.rows, cifti):
            rreshti.height = Cm(13.6)
            rreshti.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            _mos_ndaj(rreshti)
            q = rreshti.cells[0]
            q.width = gjeresia
            _letra(q, l, o, gjeresia - Cm(0.4))
    # paragrafi i fundit i dokumentit sa më i vogël, që të mos krijojë faqe bosh
    p = doc.add_paragraph()
    _run(p, '', 1)
    p.paragraph_format.line_spacing = Pt(1)
    return _ruaj(doc)
