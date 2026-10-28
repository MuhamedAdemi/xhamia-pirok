from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

from django.utils import timezone

MONEDHA_CHOICES = [
    ('MKD', 'Denar (MKD)'), ('EUR', 'Euro (€)'), ('CHF', 'Franga (CHF)'), ('USD', 'Dollar ($)'),
]
SIMBOLET = {'MKD': 'den', 'EUR': '€', 'CHF': 'CHF', 'USD': '$'}
KURSI_PARACAKTUAR = Decimal('61.5')
KURSET_PARACAKTUARA = {'EUR': Decimal('61.5'), 'CHF': Decimal('66'), 'USD': Decimal('57')}


MONEDHAT_RENDI = ['MKD', 'EUR', 'CHF', 'USD']


def formato_shumen(vlera, monedha):
    """75000 → '75.000 den'; 1380 → '1.380 €'; 69.92 → '69,92 €' (pa ,00 kur është e plotë)."""
    if vlera is None:
        return ''
    vlera = Decimal(vlera)
    decimale = 0 if monedha == 'MKD' or vlera == vlera.to_integral() else 2
    teksti = f"{vlera:,.{decimale}f}".replace(',', ' ').replace('.', ',').replace(' ', '.')
    return f"{teksti} {SIMBOLET.get(monedha, monedha)}"


def totalet_sipas_monedhes(pagesat):
    """Shuma e pagesave (queryset) sipas monedhës në të cilën janë marrë: {'MKD': .., 'EUR': .., ...}."""
    fusha_eur = pagesat.model.FUSHA_EUR
    totali = {m: Decimal('0') for m in MONEDHAT_RENDI}
    for monedha, shuma, mkd, eur in pagesat.values_list('monedha', 'shuma_monedhe', 'shuma_mkd', fusha_eur):
        if shuma is None:
            shuma = mkd if monedha == 'MKD' else eur
        totali[monedha] = totali.get(monedha, Decimal('0')) + (shuma or 0)
    return totali


class MonedhaMixin:
    """Shuma ruhet në monedhën e pagesës (`shuma_monedhe`), si dhe gjithmonë në € (FUSHA_EUR)
    dhe në MKD — për totalet. `monedha` tregon në çka u pagua."""
    FUSHA_EUR = 'shuma_paguar'

    @property
    def shuma_eur(self):
        return getattr(self, self.FUSHA_EUR)

    @property
    def shuma_ne_monedhe(self):
        """Shuma në monedhën e pagesës (edhe për pagesat e vjetra pa `shuma_monedhe`)."""
        if self.shuma_monedhe is not None:
            return self.shuma_monedhe
        return self.shuma_mkd if self.monedha == 'MKD' else self.shuma_eur

    @property
    def shuma_origjinale(self):
        return formato_shumen(self.shuma_ne_monedhe, self.monedha)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse(self.URL_DETAJE, args=[self.pk])

    @property
    def fatura_tekst(self):
        """Si shkruhet në bllokun e BFI-së: "Bllok 1100 nr 046386"."""
        if self.blloku:
            return f"Bllok {self.blloku} nr {self.nr_fatures}"
        return self.nr_fatures


class VitetMixin:
    """Pagesë që mbulon një ose më shumë vite: nga `viti` deri `viti_deri` (përfshirë)."""

    def save(self, *args, **kwargs):
        if not self.viti_deri or self.viti_deri < self.viti:
            self.viti_deri = self.viti
        super().save(*args, **kwargs)

    @property
    def nr_viteve(self):
        return (self.viti_deri or self.viti) - self.viti + 1

    @property
    def vitet_tekst(self):
        if self.viti_deri and self.viti_deri != self.viti:
            return f"{self.viti}–{self.viti_deri}"
        return str(self.viti)


class ProfilStafi(models.Model):
    ROL_CHOICES = [
        ('ADMIN', 'Administrator'),
        ('STAF', 'Staf'),
        ('MONITORUES', 'Monitorues'),
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

    @property
    def mund_shikoje(self):
        """Admini dhe monitoruesit (p.sh. imami, kryetari i këshillit) shohin gjithçka; vetëm admini ndryshon."""
        return self.rol in ('ADMIN', 'MONITORUES')

    @property
    def vetem_shikim(self):
        return self.rol == 'MONITORUES'

    @property
    def mund_regjistroje(self):
        return self.rol == 'ADMIN' or (self.rol == 'STAF' and self.mund_regjistrojë_pagesa)


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
        Kategoria, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Kategoria (opsionale)'
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
    fjalekalimi_fillestar = models.BooleanField(
        default=False, help_text='Po — familja ende përdor fjalëkalimin fillestar/të përkohshëm.',
    )
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
    """Numri më i vogël i lirë — kur fshihet një shtëpi (p.sh. duplikat), numri i saj i jepet shtëpisë së re."""
    zene = set()
    for nr in Shtepia.objects.values_list('nr_shtepise', flat=True):
        try:
            zene.add(int(nr))
        except (ValueError, TypeError):
            pass
    nr = 1
    while nr in zene:
        nr += 1
    return f"{nr:04d}"


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


class PagesaAntaresia(VitetMixin, MonedhaMixin, models.Model):
    URL_DETAJE = 'detaje_pagesa_antaresia'

    PERIUDHA_CHOICES = [
        ('VJETORE', 'Vjetore'),
        ('6MUJORE', '6-Mujore'),
        ('3MUJORE', '3-Mujore'),
        ('MUJORE', 'Mujore'),
    ]

    blloku = models.CharField(max_length=10, blank=True, verbose_name='Blloku')
    nr_fatures = models.CharField(max_length=30, verbose_name='Nr. i Faturës')
    shtepia = models.ForeignKey(
        Shtepia, on_delete=models.PROTECT, related_name='pagesat',
        verbose_name='Shtëpia'
    )
    kategoria_pageses = models.ForeignKey(
        Kategoria, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Kategoria'
    )
    shuma_paguar = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Shuma (€)')
    periudha = models.CharField(max_length=10, choices=PERIUDHA_CHOICES, default='VJETORE')
    viti = models.PositiveSmallIntegerField(verbose_name='Nga Viti', default=timezone.now().year)
    viti_deri = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Deri Viti')
    muaji_fillimit = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Muaji Fillimit')
    muaji_mbarimit = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Muaji Mbarimit')
    data_pageses = models.DateField(verbose_name='Data e Pagesës')
    arktar = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='pagesat_antaresise',
        verbose_name='Arktar'
    )
    paguesi = models.CharField(
        max_length=150, blank=True, verbose_name='Paguar nga',
        help_text='Personi që pagoi, nëse nuk është kryefamiljari (p.sh. djali).',
    )
    shenime = models.TextField(blank=True, verbose_name='Shënime')
    shuma_mkd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma (MKD)')
    kursi_denar = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name='Kursi EUR/MKD')
    monedha = models.CharField(max_length=3, choices=MONEDHA_CHOICES, default='EUR', verbose_name='Paguar në')
    shuma_monedhe = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma në monedhën e pagesës'
    )
    data_regjistrimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagesë Antarësia'
        constraints = [
            models.UniqueConstraint(
                fields=['blloku', 'nr_fatures'], name='%(class)s_fatura_unike',
                violation_error_message='Kjo faturë (blloku + numri) është regjistruar tashmë.',
            ),
        ]
        verbose_name_plural = 'Pagesat Antarësia'
        ordering = ['-data_pageses']

    def __str__(self):
        return f"{self.fatura_tekst} — {self.shtepia} — {self.shuma_origjinale}"


class PagesaFondi(MonedhaMixin, models.Model):
    FUSHA_EUR = 'shuma'
    URL_DETAJE = 'detaje_pagesa_fondi'

    LLOJI_CHOICES = [
        ('DHURATE', 'Dhuratë / Fondi i Përgjithshëm'),
        ('AKTIVITET', 'Aktivitet'),
    ]

    blloku = models.CharField(max_length=10, blank=True, verbose_name='Blloku')
    nr_fatures = models.CharField(max_length=30, verbose_name='Nr. i Faturës')
    lloji = models.CharField(
        max_length=15, choices=LLOJI_CHOICES, default='DHURATE',
        verbose_name='Lloji i Pagesës'
    )
    shtepia = models.ForeignKey(
        'Shtepia', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pagesat_fondit', verbose_name='Shtëpia',
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
    monedha = models.CharField(max_length=3, choices=MONEDHA_CHOICES, default='EUR', verbose_name='Paguar në')
    shuma_monedhe = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma në monedhën e pagesës'
    )
    data_regjistrimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagesë Fondi'
        constraints = [
            models.UniqueConstraint(
                fields=['blloku', 'nr_fatures'], name='%(class)s_fatura_unike',
                violation_error_message='Kjo faturë (blloku + numri) është regjistruar tashmë.',
            ),
        ]
        verbose_name_plural = 'Pagesat Fondit'
        ordering = ['-data_pageses']

    def __str__(self):
        return f"{self.fatura_tekst} — {self.emri_donatorit} {self.mbiemri_donatorit} — {self.shuma_origjinale}"


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


class PagesaVarrezave(VitetMixin, MonedhaMixin, models.Model):
    URL_DETAJE = 'detaje_pagesa_varrezat'

    blloku = models.CharField(max_length=10, blank=True, verbose_name='Blloku')
    nr_fatures = models.CharField(max_length=30, verbose_name='Nr. i Faturës')
    shtepia = models.ForeignKey(
        Shtepia, on_delete=models.PROTECT, related_name='pagesat_varrezave',
        verbose_name='Shtëpia'
    )
    shuma_paguar = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Shuma (€)')
    viti = models.PositiveSmallIntegerField(verbose_name='Nga Viti', default=timezone.now().year)
    viti_deri = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Deri Viti')
    data_pageses = models.DateField(verbose_name='Data e Pagesës')
    arktar = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='varrezat_regjistruara',
        verbose_name='Arktar'
    )
    paguesi = models.CharField(
        max_length=150, blank=True, verbose_name='Paguar nga',
        help_text='Personi që pagoi, nëse nuk është kryefamiljari (p.sh. djali).',
    )
    shenime = models.TextField(blank=True, verbose_name='Shënime')
    shuma_mkd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma (MKD)')
    kursi_denar = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name='Kursi EUR/MKD')
    monedha = models.CharField(max_length=3, choices=MONEDHA_CHOICES, default='EUR', verbose_name='Paguar në')
    shuma_monedhe = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma në monedhën e pagesës'
    )
    data_regjistrimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagesë Varrezash'
        constraints = [
            models.UniqueConstraint(
                fields=['blloku', 'nr_fatures'], name='%(class)s_fatura_unike',
                violation_error_message='Kjo faturë (blloku + numri) është regjistruar tashmë.',
            ),
        ]
        verbose_name_plural = 'Pagesat e Varrezave'
        ordering = ['-data_pageses']

    def __str__(self):
        return f"{self.fatura_tekst} — {self.shtepia} — {self.shuma_origjinale}"


def gjenero_nr_fature_harxhim():
    viti = timezone.now().year
    prefix = f"XP-HRX-{viti}-"
    last = Harxhimi.objects.filter(nr_fatures__startswith=prefix).order_by('nr_fatures').last()
    if last:
        nr = int(last.nr_fatures.split('-')[-1]) + 1
    else:
        nr = 1
    return f"{prefix}{nr:04d}"


class Harxhimi(MonedhaMixin, models.Model):
    FUSHA_EUR = 'shuma_eur'
    URL_DETAJE = 'detaje_harxhimi'
    # Lloji shkruhet lirisht; këto janë vetëm sugjerime te forma.
    LLOJET_SUGJERIME = [
        'Mirëmbajtje', 'Rrymë elektrike', 'Ujë', 'Nxemje / Naftë', 'Internet', 'Pastrim',
        'Riparime', 'Material ndërtimi', 'Aktivitet', 'Mirëmbajtja e varrezave', 'Tjetër',
    ]
    BURIMI_CHOICES = [
        ('FONDI', 'Fondi i Xhamisë'),
        ('VARREZAT', 'Varrezat (Mirëmbajtja)'),
        ('ANTARESIA', 'Antarësia (e vjetër)'),
    ]
    MUAJT_MAP = {
        1: 'Janar', 2: 'Shkurt', 3: 'Mars', 4: 'Prill',
        5: 'Maj', 6: 'Qershor', 7: 'Korrik', 8: 'Gusht',
        9: 'Shtator', 10: 'Tetor', 11: 'Nëntor', 12: 'Dhjetor',
    }

    blloku = models.CharField(max_length=10, blank=True, verbose_name='Blloku')
    nr_fatures = models.CharField(max_length=30, verbose_name='Nr. i Faturës')
    lloji = models.CharField(max_length=100, verbose_name='Lloji')
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
    monedha = models.CharField(max_length=3, choices=MONEDHA_CHOICES, default='EUR', verbose_name='Paguar në')
    shuma_monedhe = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Shuma në monedhën e pagesës'
    )
    data_regjistrimit = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-data_pageses']
        verbose_name = 'Harxhim'
        verbose_name_plural = 'Harxhimet'
        constraints = [
            models.UniqueConstraint(
                fields=['blloku', 'nr_fatures'], name='harxhimi_fatura_unike',
                violation_error_message='Kjo faturë (blloku + numri) është regjistruar tashmë.',
            ),
        ]

    def get_lloji_display(self):
        return self.lloji

    def __str__(self):
        return f"{self.fatura_tekst} — {self.lloji} — {self.shuma_origjinale}"

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
    kursi_eur = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('61.5'), verbose_name='1 € = ? den')
    kursi_chf = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('66'), verbose_name='1 CHF = ? den')
    kursi_usd = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('57'), verbose_name='1 $ = ? den')
    tarifa_vitet_kaluara = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('50'), verbose_name='Antarësia — minimumi për çdo vit të kaluar (€)'
    )
    tarifa_viti_aktual = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('70'), verbose_name='Antarësia — minimumi për vitin aktual e më tej (€)'
    )

    class Meta:
        verbose_name = 'Konfigurimi i Sistemit'
        verbose_name_plural = 'Konfigurimi i Sistemit'

    def __str__(self):
        return 'Konfigurimi i Sistemit'

    @classmethod
    def merr(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def tarifa_antaresise(self, viti):
        """Shuma minimale e antarësisë për një vit: vitet e kaluara më lirë, viti aktual (e më tej) me tarifën e plotë."""
        return self.tarifa_viti_aktual if viti >= timezone.now().year else self.tarifa_vitet_kaluara

    def kursi(self, monedha):
        """Sa denarë vlen 1 njësi e monedhës."""
        return {'MKD': Decimal('1'), 'EUR': self.kursi_eur, 'CHF': self.kursi_chf, 'USD': self.kursi_usd}[monedha]
