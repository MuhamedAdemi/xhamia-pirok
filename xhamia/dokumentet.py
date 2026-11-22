"""
Faturat e skanuara të daljeve (harxhimeve): ruhen si skedarë në server (MEDIA_ROOT/faturat/<viti>/), jo në bazë.

Hapësira në PythonAnywhere (llogari falas) është e kufizuar (~512 MB gjithsej, bashkë me kodin), prandaj:
  - PDF deri në 3 MB; fotot (JPG/PNG) ngjeshen vetë në ~200–300 KB;
  - faqja Backup tregon sa zënë faturat, jep ZIP-in e një viti për arkiv dhe i heq ato nga serveri
    (harxhimi mbetet, hiqet vetëm skedari).
"""
import io
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

MADHESIA_MAKS = 3 * 1024 * 1024
HAPESIRA_PYTHONANYWHERE = 512 * 1024 * 1024
LLOJET = {'application/pdf': '.pdf', 'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}


def prano(skedari):
    """Kontrollon dhe përgatit skedarin e ngarkuar: PDF siç është (≤ 3 MB), fotot të ngjeshura në JPG."""
    lloji = (getattr(skedari, 'content_type', '') or '').lower()
    emri = Path(skedari.name or 'fatura').stem[:60] or 'fatura'
    if lloji not in LLOJET:
        prapashtesa = Path(skedari.name or '').suffix.lower()
        lloji = {v: k for k, v in LLOJET.items()}.get('.jpg' if prapashtesa == '.jpeg' else prapashtesa, '')
    if lloji == 'application/pdf':
        if skedari.size > MADHESIA_MAKS:
            raise ValidationError('PDF-ja është më e madhe se 3 MB — skanojeni me rezolucion më të ulët (150–200 dpi) ose bardh e zi.')
        te_dhenat = skedari.read()
        if not te_dhenat.startswith(b'%PDF'):
            raise ValidationError('Skedari nuk është PDF i rregullt.')
        return ContentFile(te_dhenat, name=f'{emri}.pdf')
    if lloji.startswith('image/'):
        from PIL import Image, ImageOps
        try:
            foto = ImageOps.exif_transpose(Image.open(skedari))
        except Exception:
            raise ValidationError('Fotoja nuk u lexua — provoni JPG ose PNG.')
        foto = foto.convert('RGB')
        foto.thumbnail((1800, 1800))   # mjafton për lexim dhe printim të faturës
        buffer = io.BytesIO()
        foto.save(buffer, 'JPEG', quality=72, optimize=True)
        return ContentFile(buffer.getvalue(), name=f'{emri}.jpg')
    raise ValidationError('Lejohen vetëm PDF, JPG ose PNG.')


def statistika():
    """{'gjithsej': bytes, 'nr': n, 'vitet': [(viti, nr, bytes)], 'perqindja': % e 512 MB}."""
    from .models import Harxhimi
    vitet = {}
    for viti, emri in Harxhimi.objects.exclude(dokumenti='').values_list('viti', 'dokumenti'):
        rruga = Path(settings.MEDIA_ROOT) / emri
        madhesia = rruga.stat().st_size if rruga.exists() else 0
        nr, bajtet = vitet.get(viti, (0, 0))
        vitet[viti] = (nr + 1, bajtet + madhesia)
    gjithsej = sum(b for _, b in vitet.values())
    return {
        'gjithsej': gjithsej, 'nr': sum(n for n, _ in vitet.values()),
        'vitet': [(v, n, b) for v, (n, b) in sorted(vitet.items(), reverse=True)],
        'perqindja': round(100 * gjithsej / HAPESIRA_PYTHONANYWHERE, 1),
    }


def zip_i_vitit(viti):
    """ZIP me faturat e skanuara të një viti, me emra të lexueshëm: "43-26_EVN Maqedoni_Rrymë.pdf"."""
    from .models import Harxhimi
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as z:   # PDF/JPG janë tashmë të ngjeshura
        for h in Harxhimi.objects.filter(viti=viti).exclude(dokumenti='').order_by('data_pageses', 'pk'):
            rruga = Path(settings.MEDIA_ROOT) / h.dokumenti.name
            if rruga.exists():
                emri = f'{h.nr_fatures}_{h.marresi or h.lloji}'.replace('/', '-')
                emri = ''.join(c for c in emri if c not in '\\:*?"<>|')[:80]
                z.write(rruga, f'faturat_{viti}/{emri}{rruga.suffix}')
    return buffer.getvalue()


def hiq_te_vitit(viti):
    """Heq nga serveri skedarët e faturave të një viti (pasi janë shkarkuar). Kthen sa u hoqën."""
    from .models import Harxhimi
    n = 0
    for h in Harxhimi.objects.filter(viti=viti).exclude(dokumenti=''):
        h.dokumenti.delete(save=False)
        h.dokumenti = ''
        h.save(update_fields=['dokumenti'])
        n += 1
    return n
