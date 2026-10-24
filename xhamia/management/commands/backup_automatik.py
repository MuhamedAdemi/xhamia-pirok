"""
Backup ditor — për "Scheduled task" në PythonAnywhere:

    cd ~/xhamia-pirok && venv/bin/python manage.py backup_automatik --email

Ruhet në ~/xhamia-backups (30 ditët e fundit + i pari i çdo muaji përgjithmonë) dhe, me --email,
i dërgohet edhe arkivit zyrtar në Gmail — kopje jashtë serverit për raste fatkeqësie.
"""
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand

from xhamia.backup import dosja_backup, krijo_zip, pastro_backup_te_vjetra


class Command(BaseCommand):
    help = 'Krijon backup të plotë (JSON + Excel në ZIP), e ruan në server dhe opsionalisht e dërgon me email.'

    def add_arguments(self, parser):
        parser.add_argument('--email', action='store_true', help='Dërgoje backup-in edhe me email.')

    def handle(self, *args, **opts):
        emri, te_dhenat = krijo_zip()
        rruga = dosja_backup() / emri
        rruga.write_bytes(te_dhenat)
        self.stdout.write(f'Backup u ruajt: {rruga} ({len(te_dhenat) // 1024} KB)')

        fshire = pastro_backup_te_vjetra()
        if fshire:
            self.stdout.write(f'U fshinë {len(fshire)} backup të vjetra.')

        if opts['email']:
            msg = EmailMessage(
                subject=f'[Backup] Xhamia Pirok — {emri}',
                body=('Backup automatik i të gjitha të dhënave të Xhamisë Pirok.\n\n'
                      'Ruajeni këtë email. Për rikthim të plotë: python manage.py rikthe_backup <skedari.zip> --po\n'
                      'Excel-i brenda ZIP-it mund të hapet dhe të lexohet direkt.'),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.EMAIL_HOST_USER],
            )
            msg.attach(emri, te_dhenat, 'application/zip')
            msg.send()
            self.stdout.write(f'Backup u dërgua me email te {settings.EMAIL_HOST_USER}.')
