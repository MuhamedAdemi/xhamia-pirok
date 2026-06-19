"""
Script për krijimin e llogarisë admin dhe kategorive fillestare.
Ekzekuto: python setup_admin.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from xhamia.models import ProfilStafi, Kategoria

print("=== Setup Xhamia Pirok ===\n")

# Krijo admin
emri = input("Emri yt: ").strip()
mbiemri = input("Mbiemri yt: ").strip()
username = input("Username (p.sh. admin): ").strip()
email_input = input("Email yt: ").strip()
password = input("Fjalëkalimi: ").strip()
telefoni = input("Nr. Telefoni (opsional): ").strip()

if User.objects.filter(username=username).exists():
    print(f"\n⚠️  Useri '{username}' ekziston tashmë.")
    user = User.objects.get(username=username)
else:
    user = User.objects.create_user(
        username=username,
        email=email_input,
        password=password,
        first_name=emri,
        last_name=mbiemri,
        is_staff=True,
        is_superuser=True,
    )
    print(f"\n✅ Useri '{username}' u krijua.")

if not hasattr(user, 'profili'):
    ProfilStafi.objects.create(
        user=user,
        nr_telefoni=telefoni,
        pozita='Arketar',
        rol='ADMIN',
        mund_regjistrojë_pagesa=True,
        merr_email_pagese=True,
        është_aktiv=True,
    )
    print("✅ Profili admin u krijua.")
else:
    print("⚠️  Profili ekziston tashmë.")

# Krijo kategoritë fillestare
if Kategoria.objects.count() == 0:
    Kategoria.objects.create(
        emri='E Liruar',
        pershkrimi='Familjet e varfra — të liruara nga pagesa',
        shuma_vjetore=0,
        renditja=1,
    )
    Kategoria.objects.create(
        emri='Normale',
        pershkrimi='Kategoria standarde për shumicën e familjeve',
        shuma_vjetore=70,
        shuma_6mujore=36,
        shuma_3mujore=19,
        shuma_mujore=7,
        renditja=2,
    )
    Kategoria.objects.create(
        emri='E Pasur',
        pershkrimi='Kategoria premium — kontribut i shtuar',
        shuma_vjetore=120,
        shuma_6mujore=65,
        shuma_3mujore=35,
        shuma_mujore=12,
        renditja=3,
    )
    print("✅ Kategoritë fillestare u krijuan (E Liruar, Normale, E Pasur).")
else:
    print("⚠️  Kategoritë ekzistojnë tashmë.")

print("\n🎉 Setup përfundoi! Hyr në: http://127.0.0.1:8000/login/")
print(f"   Username: {username}")
print(f"   Fjalëkalimi: {password}\n")
