"""
Backup i të gjitha të dhënave.

Një backup është një ZIP me dy skedarë:
  - xhamia_YYYY-MM-DD_HHMM.json  — gjithçka (shtëpitë, pagesat, stafi, konfigurimi…), për rikthim të plotë
                                     me `python manage.py rikthe_backup <zip>`
  - xhamia_YYYY-MM-DD_HHMM.xlsx  — e lexueshme nga njeriu; fleta "Shtëpitë" ka të njëjtin format si
                                     skedari i importit, pra mund të importohet sërish nga aplikacioni.
"""
import io
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core import management
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .gjendja import gjendja_e_shtepive, vitet_tekst
from .models import Harxhimi, PagesaAntaresia, PagesaFondi, PagesaVarrezave, Shtepia

# Kolonat e fletës "Shtëpitë" — të njëjtat për importin dhe për backup-in.
KOLONAT_SHTEPITE = [
    'Nr.', 'Emri', 'Emri i Prindit', 'Mbiemri', 'Telefoni',
    'Paguar deri viti', 'Borxh nga viti', 'Vite pa paguar', 'Vitet pa paguar',
    'Borxhi minimal (€)', 'Burimi', 'Shënim',
]
GJERESITE = {'Nr.': 7, 'Emri': 16, 'Emri i Prindit': 16, 'Mbiemri': 16, 'Telefoni': 16,
             'Paguar deri viti': 10, 'Borxh nga viti': 10, 'Vite pa paguar': 9, 'Vitet pa paguar': 18,
             'Borxhi minimal (€)': 12, 'Burimi': 22, 'Shënim': 50}

_KOKA = dict(font=Font(bold=True, color='FFFFFF'), fill=PatternFill('solid', fgColor='2D5A1B'))
_NGJYRA_BORXHI = PatternFill('solid', fgColor='FCE4D6')
_NGJYRA_SHENIMI = PatternFill('solid', fgColor='FFF2CC')


def _fleta(wb, titulli, koka, gjeresite=None, e_para=False):
    ws = wb.active if e_para else wb.create_sheet()
    ws.title = titulli
    ws.append(koka)
    for c in ws[1]:
        c.font, c.fill = _KOKA['font'], _KOKA['fill']
    ws.freeze_panes = 'A2'
    for i, k in enumerate(koka, 1):
        ws.column_dimensions[get_column_letter(i)].width = (gjeresite or {}).get(k, 14)
    return ws


def shkruaj_shtepite(ws, rreshtat):
    """rreshtat: lista dict-esh me çelësat e KOLONAT_SHTEPITE."""
    for r in rreshtat:
        ws.append([r.get(k, '') for k in KOLONAT_SHTEPITE])
        if r.get('Shënim'):
            for c in ws[ws.max_row]:
                c.fill = _NGJYRA_SHENIMI
        elif r.get('Vite pa paguar'):
            ws.cell(ws.max_row, KOLONAT_SHTEPITE.index('Vite pa paguar') + 1).fill = _NGJYRA_BORXHI
    ws.auto_filter.ref = ws.dimensions


def rreshtat_e_shtepive():
    shtepite = list(Shtepia.objects.order_by('nr_shtepise'))
    gj = gjendja_e_shtepive(shtepite)
    rreshtat = []
    for sh in shtepite:
        g = gj[sh.id]
        rreshtat.append({
            'Nr.': sh.nr_shtepise, 'Emri': sh.emri_kryefamiljarit, 'Emri i Prindit': sh.emri_prindit,
            'Mbiemri': sh.mbiemri_kryefamiljarit, 'Telefoni': sh.nr_telefoni_kryesor,
            'Paguar deri viti': g['paguar_deri'], 'Borxh nga viti': g['borxh_nga'],
            'Vite pa paguar': len(g['papaguara']), 'Vitet pa paguar': vitet_tekst(g['papaguara']),
            'Borxhi minimal (€)': float(g['borxhi']),
            'Burimi': 'Aktive' if sh.është_aktiv else 'Joaktive', 'Shënim': sh.shenime,
        })
    return rreshtat


def excel_i_plote():
    wb = Workbook()
    shkruaj_shtepite(_fleta(wb, 'Shtëpitë', KOLONAT_SHTEPITE, GJERESITE, e_para=True), rreshtat_e_shtepive())

    ws = _fleta(wb, 'Pagesat Antarësia', ['Blloku', 'Nr. Faturës', 'Data', 'Nr. Shtëpisë', 'Kryefamiljari',
                                           'Nga Viti', 'Deri Viti', 'Paguar në', 'Shuma', 'Shuma (den)',
                                           'Shuma (€)', 'Arkëtari', 'Shënime'])
    for p in PagesaAntaresia.objects.select_related('shtepia', 'arktar').order_by('data_pageses', 'pk'):
        ws.append([p.blloku, p.nr_fatures, p.data_pageses, p.shtepia.nr_shtepise, p.shtepia.emri_i_plote,
                   p.viti, p.viti_deri, p.monedha, float(p.shuma_ne_monedhe or 0), float(p.shuma_mkd or 0),
                   float(p.shuma_paguar), p.arktar.get_full_name(), p.shenime])

    ws = _fleta(wb, 'Pagesat Varrezave', ['Blloku', 'Nr. Faturës', 'Data', 'Nr. Shtëpisë', 'Kryefamiljari',
                                           'Nga Viti', 'Deri Viti', 'Paguar në', 'Shuma', 'Shuma (den)',
                                           'Shuma (€)', 'Arkëtari', 'Shënime'])
    for p in PagesaVarrezave.objects.select_related('shtepia', 'arktar').order_by('data_pageses', 'pk'):
        ws.append([p.blloku, p.nr_fatures, p.data_pageses, p.shtepia.nr_shtepise, p.shtepia.emri_i_plote,
                   p.viti, p.viti_deri, p.monedha, float(p.shuma_ne_monedhe or 0), float(p.shuma_mkd or 0),
                   float(p.shuma_paguar), p.arktar.get_full_name(), p.shenime])

    ws = _fleta(wb, 'Pagesat Fondi', ['Blloku', 'Nr. Faturës', 'Data', 'Nr. Shtëpisë', 'Lloji', 'Emri', 'Mbiemri',
                                       'Telefoni', 'Arsyeja', 'Paguar në', 'Shuma', 'Shuma (den)', 'Shuma (€)', 'Arkëtari'])
    for p in PagesaFondi.objects.select_related('arktar', 'shtepia').order_by('data_pageses', 'pk'):
        ws.append([p.blloku, p.nr_fatures, p.data_pageses, p.shtepia.nr_shtepise if p.shtepia else '',
                   p.get_lloji_display(), p.emri_donatorit,
                   p.mbiemri_donatorit, p.nr_telefoni, p.arsyeja, p.monedha, float(p.shuma_ne_monedhe or 0),
                   float(p.shuma_mkd or 0), float(p.shuma), p.arktar.get_full_name()])

    ws = _fleta(wb, 'Harxhimet', ['Blloku', 'Nr. Faturës', 'Data', 'Lloji', 'Buxheti', 'Përshkrimi', 'Shuma (€)',
                                   'Shuma (den)', 'Regjistruar nga'])
    for h in Harxhimi.objects.select_related('arktar').order_by('data_pageses', 'pk'):
        ws.append([h.blloku, h.nr_fatures, h.data_pageses, h.get_lloji_display(), h.get_burimi_display(), h.pershkrimi,
                   float(h.shuma_eur), float(h.shuma_mkd or 0), h.arktar.get_full_name()])

    for ws in wb.worksheets[1:]:
        for rr in ws.iter_rows(min_row=2, min_col=3, max_col=3):
            for c in rr:
                c.number_format = 'DD.MM.YYYY'

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def json_i_plote():
    """Të gjitha të dhënat (përfshirë llogaritë e stafit) në formatin që e lexon `loaddata`."""
    out = io.StringIO()
    management.call_command(
        'dumpdata', 'xhamia', 'auth.user', 'auth.group',
        natural_foreign=True, indent=1, stdout=out,
    )
    return out.getvalue().encode('utf-8')


def emri_backup(kur=None):
    return f"xhamia_{(kur or timezone.localtime()).strftime('%Y-%m-%d_%H%M')}"


def krijo_zip():
    """Kthen (emri_i_skedarit, bytes)."""
    emri = emri_backup()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{emri}.json', json_i_plote())
        z.writestr(f'{emri}.xlsx', excel_i_plote())
        z.writestr('LEXOMË.txt', (
            'Backup i Xhamisë Pirok\n\n'
            f'{emri}.json  -> rikthim i plotë:  python manage.py rikthe_backup {emri}.zip --po\n'
            f'{emri}.xlsx  -> për lexim; fleta "Shtëpitë" importohet nga aplikacioni (Shtëpitë -> Importo).\n'
        ))
    return f'{emri}.zip', buffer.getvalue()


# ─── Backup-et automatike në server ──────────────────────────────────────────

def dosja_backup():
    dosja = Path(getattr(settings, 'BACKUP_DIR', Path(settings.BASE_DIR).parent / 'xhamia-backups'))
    dosja.mkdir(parents=True, exist_ok=True)
    return dosja


def lista_backup():
    """Backup-et e ruajtura në server, më i riu i pari: [(Path, madhësia KB, data)]."""
    skedaret = sorted(dosja_backup().glob('*.zip'), key=lambda f: f.stat().st_mtime, reverse=True)
    return [(f, round(f.stat().st_size / 1024), datetime.fromtimestamp(f.stat().st_mtime)) for f in skedaret]


def pastro_backup_te_vjetra(ditet=30):
    """Mban: të gjitha backup-et e 30 ditëve të fundit + të parin e çdo muaji përgjithmonë."""
    skedaret = sorted(dosja_backup().glob('xhamia_*.zip'))
    muajt_e_ruajtur, fshire = set(), []
    kufiri = timezone.localtime().date().toordinal() - ditet
    for f in skedaret:
        try:
            data = datetime.strptime(f.stem[7:17], '%Y-%m-%d').date()
        except ValueError:
            continue
        muaji = (data.year, data.month)
        if muaji not in muajt_e_ruajtur:
            muajt_e_ruajtur.add(muaji)      # i pari i muajit — mbahet përgjithmonë
            continue
        if data.toordinal() < kufiri:
            f.unlink()
            fshire.append(f.name)
    return fshire


def numrat_per_fshirje():
    from .models import MesazhSMS, ProfilShtepi
    return {
        'Shtëpi': Shtepia.objects.count(),
        'Pagesa antarësie': PagesaAntaresia.objects.count(),
        'Pagesa varrezash': PagesaVarrezave.objects.count(),
        'Pagesa fondi': PagesaFondi.objects.count(),
        'Harxhime': Harxhimi.objects.count(),
        'SMS (historiku)': MesazhSMS.objects.count(),
        'Llogari shtëpish (portali)': ProfilShtepi.objects.count(),
    }


def fillo_nga_zero():
    """Fshin shtëpitë, pagesat, harxhimet, SMS-të dhe llogaritë e portalit të shtëpive.
    Ruhen: stafi (përdoruesit dhe fjalëkalimet), kategoritë, konfigurimi (SMS, email, kurset, tarifat).
    Para fshirjes ruhet një backup i plotë në server."""
    from django.contrib.auth.models import User
    from django.db import transaction
    from .models import MesazhSMS, ProfilShtepi

    emri, te_dhenat = krijo_zip()
    rruga = dosja_backup() / f'para-fshirjes_{emri}'
    rruga.write_bytes(te_dhenat)
    with transaction.atomic():
        perdoruesit_e_shtepive = list(ProfilShtepi.objects.values_list('user_id', flat=True))
        PagesaAntaresia.objects.all().delete()
        PagesaVarrezave.objects.all().delete()
        PagesaFondi.objects.all().delete()
        Harxhimi.objects.all().delete()
        MesazhSMS.objects.all().delete()
        Shtepia.objects.all().delete()          # fshin edhe ProfilShtepi (cascade)
        User.objects.filter(pk__in=perdoruesit_e_shtepive).delete()
    return rruga
