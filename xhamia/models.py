from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ProfilStafi(models.Model):
    ROL_CHOICES = [
        ('ADMIN', 'Administrator'),
        ('STAF', 'Staf'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profili')
    nr_telefoni = models.CharField(max_length=20, blank=True)
    pozita = models.CharField(max_length=100, blank=True, verbose_name='Pozita në Xhami')
    rol = models.CharField(max_length=10, choices=ROL_CHOICES, default='STAF')
    mund_regjistrojë_pagesa = models.BooleanField(default=False, verbose_name='Mund të regjistrojë pagesa')
    merr_email_pagese = models.BooleanField(default=True, verbose_name='Merr email për çdo pagesë')
    është_aktiv = models.BooleanField(default=True)
    shtuar_nga = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stafi_shtuar'
    )
    data_shtimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Profil Stafi'
        verbose_name_plural = 'Stafi'

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} ({self.get_rol_display()})"

    @property
    def është_admin(self):
        return self.rol == 'ADMIN'


class Kategoria(models.Model):
    emri = models.CharField(max_length=100, verbose_name='Emri i Kategorisë')
    pershkrimi = models.TextField(blank=True, verbose_name='Përshkrimi')
    shuma_vjetore = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    shuma_6mujore = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    shuma_3mujore = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    shuma_mujore = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    është_aktiv = models.BooleanField(default=True)
    renditja = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Kategori'
        verbose_name_plural = 'Kategoritë'
        ordering = ['renditja', 'emri']

    def __str__(self):
        return self.emri


class Shtepia(models.Model):
    nr_shtepise = models.CharField(
        max_length=4, unique=True, verbose_name='Nr. Shtëpisë'
    )
    emri_kryefamiljarit = models.CharField(max_length=100, verbose_name='Emri')
    emri_prindit = models.CharField(max_length=100, blank=True, verbose_name='Emri i Prindit')
    mbiemri_kryefamiljarit = models.CharField(max_length=100, verbose_name='Mbiemri')
    nr_antareve_familjes = models.PositiveSmallIntegerField(default=1, verbose_name='Nr. Anëtarëve')
    kategoria = models.ForeignKey(
        Kategoria, on_delete=models.PROTECT, verbose_name='Kategoria e Pagesës'
    )
    viti_fillimit_antaresise = models.PositiveSmallIntegerField(
        default=2026, verbose_name='Antarësia Aktive nga Viti'
    )
    paguar_deri_viti = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Paguar Deri Viti (Historik)'
    )
    viti_fillimit_varrezave = models.PositiveSmallIntegerField(
        default=2026, verbose_name='Varrezat Aktive nga Viti'
    )
    varrezat_paguar_deri_viti = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Varrezat — Paguar Deri Viti (Historik)'
    )
    email = models.EmailField(blank=True, verbose_name='Email')
    nr_telefoni_kryesor = models.CharField(max_length=20, blank=True, verbose_name='Nr. Telefoni Kryesor')
    nr_telefoni_sporadik = models.CharField(max_length=20, blank=True, verbose_name='Nr. Telefoni Sporadik')
    kontakt_sporadik_emri = models.CharField(max_length=200, blank=True, verbose_name='Kontakt Sporadik (Emri)')
    kontakt_sporadik_email = models.EmailField(blank=True, verbose_name='Kontakt Sporadik (Email)')
    kontakt_sporadik_telefoni = models.CharField(max_length=20, blank=True, verbose_name='Kontakt Sporadik (Tel.)')
    shenime = models.TextField(blank=True, verbose_name='Shënime')
    është_aktiv = models.BooleanField(default=True)
    data_regjistrimit = models.DateTimeField(auto_now_add=True)
    regjistruar_nga = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='shtepite_regjistruara'
    )

    class Meta:
        verbose_name = 'Shtëpi'
        verbose_name_plural = 'Shtëpitë'
        ordering = ['nr_shtepise']

    def __str__(self):
        return f"#{self.nr_shtepise} — {self.emri_i_plote}"

    @property
    def emri_i_plote(self):
        pjeset = [self.emri_kryefamiljarit, self.emri_prindit, self.mbiemri_kryefamiljarit]
        return ' '.join(p for p in pjeset if p)


class ProfilShtepi(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profili_shtepi')
    shtepia = models.OneToOneField('Shtepia', on_delete=models.CASCADE, related_name='llogaria')
    krijuar_nga = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='llogarite_shtepive_krijuara'
    )
    data_krijimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Llogari Shtëpie'
        verbose_name_plural = 'Llogaritë e Shtëpive'

    def __str__(self):
        return f"sh{self.shtepia.nr_shtepise} — {self.shtepia.emri_i_plote}"


def gjenero_nr_shtepi():
    numrat = []
    for nr in Shtepia.objects.values_list('nr_shtepise', flat=True):
        try:
            numrat.append(int(nr))
        except (ValueError, TypeError):
            pass
    return f"{(max(numrat) + 1) if numrat else 1:04d}"


def gjenero_nr_fature_antaresi():
    viti = timezone.now().year
    prefix = f"XP-ANT-{viti}-"
    last = PagesaAntaresia.objects.filter(nr_fatures__startswith=prefix).order_by('nr_fatures').last()
    if last:
        nr = int(last.nr_fatures.split('-')[-1]) + 1
    else:
        nr = 1
    return f"{prefix}{nr:04d}"


def gjenero_nr_fature_fondi():
    viti = timezone.now().year
    prefix = f"XP-FOND-{viti}-"
    last = PagesaFondi.objects.filter(nr_fatures__startswith=prefix).order_by('nr_fatures').last()
    if last:
        nr = int(last.nr_fatures.split('-')[-1]) + 1
    else:
        nr = 1
    return f"{prefix}{nr:04d}"


class PagesaAntaresia(models.Model):
    PERIUDHA_CHOICES = [
        ('VJETORE', 'Vjetore'),
        ('6MUJORE', '6-Mujore'),
        ('3MUJORE', '3-Mujore'),
        ('MUJORE', 'Mujore'),
    ]

    nr_fatures = models.CharField(
        max_length=20, unique=True, default=gjenero_nr_fature_antaresi,
        verbose_name='Nr. Faturës'
    )
    shtepia = models.ForeignKey(
        Shtepia, on_delete=models.PROTECT, related_name='pagesat',
        verbose_name='Shtëpia'
    )
    kategoria_pageses = models.ForeignKey(
        Kategoria, on_delete=models.PROTECT, verbose_name='Kategoria'
    )
    shuma_paguar = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Shuma (€)')
    periudha = models.CharField(max_length=10, choices=PERIUDHA_CHOICES, default='VJETORE')
    viti = models.PositiveSmallIntegerField(verbose_name='Viti', default=timezone.now().year)
    muaji_fillimit = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Muaji Fillimit')
    muaji_mbarimit = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Muaji Mbarimit')
    data_pageses = models.DateField(verbose_name='Data e Pagesës')
    arktar = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='pagesat_antaresise',
        verbose_name='Arktar'
    )
    shenime = models.TextField(blank=True, verbose_name='Shënime')
    shuma_mkd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma (MKD)')
    kursi_denar = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name='Kursi EUR/MKD')
    data_regjistrimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagesë Antarësia'
        verbose_name_plural = 'Pagesat Antarësia'
        ordering = ['-data_pageses']

    def __str__(self):
        return f"{self.nr_fatures} — {self.shtepia} — {self.shuma_paguar}€"


class PagesaFondi(models.Model):
    LLOJI_CHOICES = [
        ('DHURATE', 'Dhuratë / Fondi i Përgjithshëm'),
        ('AKTIVITET', 'Aktivitet'),
    ]

    nr_fatures = models.CharField(
        max_length=20, unique=True, default=gjenero_nr_fature_fondi,
        verbose_name='Nr. Faturës'
    )
    lloji = models.CharField(
        max_length=15, choices=LLOJI_CHOICES, default='DHURATE',
        verbose_name='Lloji i Pagesës'
    )
    emri_donatorit = models.CharField(max_length=100, verbose_name='Emri')
    mbiemri_donatorit = models.CharField(max_length=100, verbose_name='Mbiemri')
    email_donatorit = models.EmailField(blank=True, verbose_name='Email Donatorit')
    nr_telefoni = models.CharField(max_length=20, blank=True, verbose_name='Nr. Telefoni')
    shuma = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Shuma (€)')
    data_pageses = models.DateField(verbose_name='Data e Pagesës')
    arsyeja = models.CharField(max_length=300, blank=True, verbose_name='Arsyeja / Qëllimi')
    arktar = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='pagesat_fondit',
        verbose_name='Arktar'
    )
    shenime = models.TextField(blank=True, verbose_name='Shënime')
    shuma_mkd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma (MKD)')
    kursi_denar = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name='Kursi EUR/MKD')
    data_regjistrimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagesë Fondi'
        verbose_name_plural = 'Pagesat Fondit'
        ordering = ['-data_pageses']

    def __str__(self):
        return f"{self.nr_fatures} — {self.emri_donatorit} {self.mbiemri_donatorit} — {self.shuma}€"


class KonfigurimiVarrezave(models.Model):
    """Rresht i vetëm (singleton) me shumën vjetore fikse për mirëmbajtjen e varrezave."""
    shuma_vjetore = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        verbose_name='Shuma Vjetore (€) — e njëjtë për çdo shtëpi'
    )
    pershkrimi = models.TextField(blank=True, verbose_name='Shënime / Përshkrimi i Programit')

    class Meta:
        verbose_name = 'Konfigurimi i Varrezave'
        verbose_name_plural = 'Konfigurimi i Varrezave'

    def __str__(self):
        return f"Shuma vjetore: {self.shuma_vjetore}€"

    @classmethod
    def merr(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def gjenero_nr_fature_varrezat():
    viti = timezone.now().year
    prefix = f"XP-VARR-{viti}-"
    last = PagesaVarrezave.objects.filter(nr_fatures__startswith=prefix).order_by('nr_fatures').last()
    if last:
        nr = int(last.nr_fatures.split('-')[-1]) + 1
    else:
        nr = 1
    return f"{prefix}{nr:04d}"


class PagesaVarrezave(models.Model):
    nr_fatures = models.CharField(
        max_length=20, unique=True, default=gjenero_nr_fature_varrezat,
        verbose_name='Nr. Faturës'
    )
    shtepia = models.ForeignKey(
        Shtepia, on_delete=models.PROTECT, related_name='pagesat_varrezave',
        verbose_name='Shtëpia'
    )
    shuma_paguar = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Shuma (€)')
    viti = models.PositiveSmallIntegerField(verbose_name='Viti', default=timezone.now().year)
    data_pageses = models.DateField(verbose_name='Data e Pagesës')
    arktar = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='varrezat_regjistruara',
        verbose_name='Arktar'
    )
    shenime = models.TextField(blank=True, verbose_name='Shënime')
    shuma_mkd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma (MKD)')
    kursi_denar = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name='Kursi EUR/MKD')
    data_regjistrimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagesë Varrezash'
        verbose_name_plural = 'Pagesat e Varrezave'
        ordering = ['-data_pageses']

    def __str__(self):
        return f"{self.nr_fatures} — {self.shtepia} — {self.shuma_paguar}€"


def gjenero_nr_fature_harxhim():
    viti = timezone.now().year
    prefix = f"XP-HRX-{viti}-"
    last = Harxhimi.objects.filter(nr_fatures__startswith=prefix).order_by('nr_fatures').last()
    if last:
        nr = int(last.nr_fatures.split('-')[-1]) + 1
    else:
        nr = 1
    return f"{prefix}{nr:04d}"


class Harxhimi(models.Model):
    LLOJI_CHOICES = [
        ('RROGE', 'Rroge Stafi'),
        ('MIREMBAJTJE', 'Mirëmbajtje'),
        ('RRYME', 'Rrymë Elektrike'),
        ('UJI', 'Ujë'),
        ('NXEMJE', 'Nxemje / Naftë'),
        ('INTERNET', 'Internet'),
        ('TJETER', 'Tjetër'),
    ]
    BURIMI_CHOICES = [
        ('ANTARESIA', 'Antarësia (Rrogat)'),
        ('FONDI', 'Fondi i Xhamisë'),
        ('VARREZAT', 'Varrezat (Mirëmbajtja)'),
    ]
    MUAJT_MAP = {
        1: 'Janar', 2: 'Shkurt', 3: 'Mars', 4: 'Prill',
        5: 'Maj', 6: 'Qershor', 7: 'Korrik', 8: 'Gusht',
        9: 'Shtator', 10: 'Tetor', 11: 'Nëntor', 12: 'Dhjetor',
    }

    nr_fatures = models.CharField(
        max_length=25, unique=True, default=gjenero_nr_fature_harxhim,
        verbose_name='Nr. Dokumentit'
    )
    lloji = models.CharField(max_length=20, choices=LLOJI_CHOICES, verbose_name='Lloji')
    burimi = models.CharField(
        max_length=20, choices=BURIMI_CHOICES, default='FONDI',
        verbose_name='Buxheti'
    )
    stafi = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='rrogat_e_marra', verbose_name='Stafi (rroge)'
    )
    pershkrimi = models.TextField(blank=True, verbose_name='Përshkrimi')
    shuma_eur = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Shuma (€)')
    shuma_mkd = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Shuma (MKD)'
    )
    kursi_denar = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        verbose_name='Kursi EUR/MKD'
    )
    muaji = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Muaji')
    viti = models.PositiveSmallIntegerField(verbose_name='Viti')
    data_pageses = models.DateField(verbose_name='Data')
    arktar = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='harxhimet_regjistruara', verbose_name='Regjistruar nga'
    )
    data_regjistrimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-data_pageses']
        verbose_name = 'Harxhim'
        verbose_name_plural = 'Harxhimet'

    def __str__(self):
        return f"{self.nr_fatures} — {self.get_lloji_display()} — {self.shuma_eur}€"

    @property
    def emri_muajit(self):
        return self.MUAJT_MAP.get(self.muaji, '') if self.muaji else ''


class MesazhSMS(models.Model):
    LLOJI_CHOICES = [
        ('KONFIRMIM', 'Konfirmim Pagese'),
        ('KUJTESE', 'Kujtesë Borxhi'),
    ]
    STATUSI_CHOICES = [
        ('NE_PRITJE', 'Në pritje'),
        ('DERGUAR', 'Dërguar'),
        ('DORZUAR', 'Dorëzuar'),
        ('DESHTOI', 'Dështoi'),
    ]

    nr_telefoni = models.CharField(max_length=30, verbose_name='Nr. Telefoni')
    teksti = models.TextField(verbose_name='Teksti')
    lloji = models.CharField(max_length=15, choices=LLOJI_CHOICES, verbose_name='Lloji')
    statusi = models.CharField(max_length=15, choices=STATUSI_CHOICES, default='NE_PRITJE', verbose_name='Statusi')
    gabimi = models.CharField(max_length=500, blank=True, verbose_name='Gabimi')
    id_gateway = models.CharField(max_length=100, blank=True)
    shtepia = models.ForeignKey(
        Shtepia, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mesazhet_sms', verbose_name='Shtëpia'
    )
    dërguar_nga = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sms_te_derguara', verbose_name='Dërguar nga'
    )
    data_dergimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mesazh SMS'
        verbose_name_plural = 'Mesazhet SMS'
        ordering = ['-data_dergimit']

    def __str__(self):
        return f"{self.nr_telefoni} — {self.get_lloji_display()} — {self.get_statusi_display()}"


class KonfigurimiSistemit(models.Model):
    """Rresht i vetëm (singleton) me fjalëkalimet që admini i vendos nga aplikacioni,
    në vend që t'i shkruajë në config/local_settings.py."""
    sms_username = models.CharField(max_length=100, blank=True, verbose_name='SMS Gateway — Username')
    sms_password = models.CharField(max_length=200, blank=True, verbose_name='SMS Gateway — Password')
    sms_sim_numri = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=[(1, 'SIM 1'), (2, 'SIM 2')],
        verbose_name='Nga cili SIM dërgohen SMS-të',
    )
    gmail_app_password = models.CharField(max_length=100, blank=True, verbose_name='Gmail — App Password')

    class Meta:
        verbose_name = 'Konfigurimi i Sistemit'
        verbose_name_plural = 'Konfigurimi i Sistemit'

    def __str__(self):
        return 'Konfigurimi i Sistemit'

    @classmethod
    def merr(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
