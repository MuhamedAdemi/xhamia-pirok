"""
Fshin të gjitha të dhënat e testimit — shtëpitë, pagesat, harxhimet, SMS-të, llogaritë e portalit:

    python manage.py fillo_nga_zero --po

Ruhen stafi (përdoruesit, fjalëkalimet), kategoritë dhe konfigurimi. Para fshirjes ruhet një backup.
"""
from django.core.management.base import BaseCommand, CommandError

from xhamia.backup import fillo_nga_zero, numrat_per_fshirje


class Command(BaseCommand):
    help = 'Fshin të gjitha shtëpitë dhe pagesat (ruan stafin dhe konfigurimin), me backup para fshirjes.'

    def add_arguments(self, parser):
        parser.add_argument('--po', action='store_true', help='Konfirmim: po, fshiji.')

    def handle(self, *args, po, **opts):
        for k, v in numrat_per_fshirje().items():
            self.stdout.write(f'  {k}: {v}')
        if not po:
            raise CommandError('Asgjë nuk u fshi. Për ta konfirmuar, përsëriteni me --po')
        rruga = fillo_nga_zero()
        self.stdout.write(f'Backup para fshirjes: {rruga}')
        for k, v in numrat_per_fshirje().items():
            self.stdout.write(f'  {k}: {v}')
        self.stdout.write(self.style.SUCCESS('U fshi gjithçka. Tani importoni Excel-in te Shtëpitë → Importo.'))
