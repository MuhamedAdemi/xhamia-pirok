"""
Vendos kategorinë e shtëpive që kanë pagesë në aplikacion, sipas shumës së vitit të tyre më të fundit të paguar:

    python manage.py vendos_kategorite --provo   # vetëm tregon çka do të ndryshojë
    python manage.py vendos_kategorite           # i ruan ndryshimet

Shtëpitë që dihet vetëm se kanë paguar (historik pa shumë) nuk preken — ato plotësohen me dorë te Antarësia.
Pas kësaj, kategoria ndryshon vetvetiu me çdo pagesë të re.
"""
from django.core.management.base import BaseCommand

from xhamia.kategorite import vendos_per_te_gjitha


class Command(BaseCommand):
    help = 'Vendos kategoritë e shtëpive sipas pagesave të regjistruara në aplikacion.'

    def add_arguments(self, parser):
        parser.add_argument('--provo', action='store_true', help='Vetëm trego, mos ruaj asgjë.')

    def handle(self, *args, provo, **opts):
        ndryshimet = vendos_per_te_gjitha(ruaj=not provo)
        for sh, e_vjetra, k in ndryshimet:
            self.stdout.write(f'#{sh.nr_shtepise} {sh.emri_i_plote}: {e_vjetra or "pa kategori"} → {k.etiketa}')
        fjala = 'do të ndryshojnë' if provo else 'u ndryshuan'
        self.stdout.write(self.style.SUCCESS(f'{len(ndryshimet)} shtëpi {fjala}.'))
