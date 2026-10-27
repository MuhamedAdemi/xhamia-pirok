"""
Tregon llogaritë e stafit (pa fjalëkalime) — për të kontrolluar pse dikush nuk mund të hyjë:

    python manage.py llogarite_stafit

Për t'ia vendosur dikujt fjalëkalim të ri:   python manage.py changepassword <përdoruesi>
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Lista e llogarive të stafit: përdoruesi, roli, aktiv, a ka fjalëkalim.'

    def handle(self, *args, **opts):
        users = User.objects.filter(profili_shtepi__isnull=True).select_related('profili').order_by('username')
        self.stdout.write(f"{'Përdoruesi':<16} {'Emri':<26} {'Roli':<12} {'Aktiv':<6} Fjalëkalim")
        for u in users:
            profil = getattr(u, 'profili', None)
            roli = profil.rol if profil else ('SUPERUSER' if u.is_superuser else '— pa profil')
            aktiv = 'po' if u.is_active and (profil is None or profil.është_aktiv) else 'JO'
            fjalekalim = 'po' if u.has_usable_password() and u.password else 'JO'
            self.stdout.write(f'{u.username:<16} {u.get_full_name()[:25]:<26} {roli:<12} {aktiv:<6} {fjalekalim}')
