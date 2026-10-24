"""
Rikthim i plotë nga një backup:

    python manage.py rikthe_backup xhamia_2026-10-24_0300.zip --po

KUJDES: fshin të gjitha të dhënat aktuale dhe i zëvendëson me ato të backup-it.
Para rikthimit ruhet automatikisht një backup i gjendjes aktuale (për çdo rast).
"""
import io
import tempfile
import zipfile
from pathlib import Path

from django.core import management
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from xhamia.backup import dosja_backup, krijo_zip


class Command(BaseCommand):
    help = 'Rikthen të gjitha të dhënat nga një backup (ZIP ose JSON).'

    def add_arguments(self, parser):
        parser.add_argument('skedari', help='Rruga e skedarit .zip ose .json të backup-it.')
        parser.add_argument('--po', action='store_true', help='Konfirmim: po, fshiji të dhënat aktuale.')

    def handle(self, *args, skedari, po, **opts):
        rruga = Path(skedari)
        if not rruga.exists():
            raise CommandError(f'Skedari nuk u gjet: {rruga}')
        if rruga.suffix == '.zip':
            with zipfile.ZipFile(rruga) as z:
                emrat = [n for n in z.namelist() if n.endswith('.json')]
                if not emrat:
                    raise CommandError('ZIP-i nuk ka skedar .json.')
                te_dhenat = z.read(emrat[0])
        else:
            te_dhenat = rruga.read_bytes()

        if not po:
            raise CommandError('Ky veprim FSHIN të dhënat aktuale. Përsëriteni me --po për ta konfirmuar.')

        emri, siguria = krijo_zip()
        (dosja_backup() / f'para-rikthimit_{emri}').write_bytes(siguria)
        self.stdout.write(f'Gjendja aktuale u ruajt te {dosja_backup() / ("para-rikthimit_" + emri)}')

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            tmp.write(te_dhenat)
        try:
            with transaction.atomic():
                management.call_command('flush', interactive=False, verbosity=0)
                management.call_command('loaddata', tmp.name, verbosity=1)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS('Rikthimi përfundoi.'))
