import json
from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.contrib.auth.models import User
from .models import (
    ProfilStafi, Kategoria, Shtepia, PagesaAntaresia, PagesaFondi, Harxhimi,
    PagesaVarrezave, KonfigurimiVarrezave, KonfigurimiSistemit,
    MONEDHA_CHOICES, KURSI_PARACAKTUAR,
)


MUAJT = [
    (1, 'Janar'), (2, 'Shkurt'), (3, 'Mars'), (4, 'Prill'),
    (5, 'Maj'), (6, 'Qershor'), (7, 'Korrik'), (8, 'Gusht'),
    (9, 'Shtator'), (10, 'Tetor'), (11, 'Nëntor'), (12, 'Dhjetor'),
]


class LoginForm(forms.Form):
    username = forms.CharField(label='Emri i Përdoruesit', max_length=150)
    password = forms.CharField(label='Fjalëkalimi', widget=forms.PasswordInput)


class StafForm(forms.ModelForm):
    first_name = forms.CharField(label='Emri', max_length=100)
    last_name = forms.CharField(label='Mbiemri', max_length=100)
    email = forms.EmailField(label='Email')
    username = forms.CharField(label='Emri i Përdoruesit', max_length=150)
    password = forms.CharField(
        label='Fjalëkalimi', widget=forms.PasswordInput, required=False,
        help_text='Lëre bosh nëse nuk do ta ndryshosh.'
    )

    class Meta:
        model = ProfilStafi
        fields = ['nr_telefoni', 'pozita', 'rol', 'mund_regjistrojë_pagesa', 'merr_email_pagese']
        labels = {
            'nr_telefoni': 'Nr. Telefoni',
            'pozita': 'Pozita në Xhami',
            'rol': 'Roli',
        }


class KategoriaForm(forms.ModelForm):
    class Meta:
        model = Kategoria
        fields = ['emri', 'pershkrimi', 'shuma_vjetore', 'shuma_6mujore', 'shuma_3mujore', 'shuma_mujore', 'renditja', 'është_aktiv']
        labels = {
            'emri': 'Emri i Kategorisë',
            'pershkrimi': 'Përshkrimi',
            'shuma_vjetore': 'Shuma Vjetore (€)',
            'shuma_6mujore': 'Shuma 6-Mujore (€)',
            'shuma_3mujore': 'Shuma 3-Mujore (€)',
            'shuma_mujore': 'Shuma Mujore (€)',
            'renditja': 'Renditja',
            'është_aktiv': 'Aktive',
        }
        widgets = {
            'pershkrimi': forms.Textarea(attrs={'rows': 2}),
        }


class ShtepiaForm(forms.ModelForm):
    class Meta:
        model = Shtepia
        fields = [
            'nr_shtepise', 'emri_kryefamiljarit', 'emri_prindit', 'mbiemri_kryefamiljarit',
            'nr_antareve_familjes', 'kategoria', 'viti_fillimit_antaresise',
            'paguar_deri_viti',
            'viti_fillimit_varrezave', 'varrezat_paguar_deri_viti',
            'email', 'nr_telefoni_kryesor', 'nr_telefoni_sporadik',
            'kontakt_sporadik_emri', 'kontakt_sporadik_email', 'kontakt_sporadik_telefoni',
            'shenime', 'është_aktiv',
        ]
        labels = {
            'viti_fillimit_antaresise': 'Antarësia Aktive nga Viti',
            'paguar_deri_viti': 'Paguar Deri Viti (Historik)',
            'viti_fillimit_varrezave': 'Varrezat Aktive nga Viti',
            'varrezat_paguar_deri_viti': 'Varrezat — Paguar Deri Viti (Historik)',
        }
        widgets = {
            'shenime': forms.Textarea(attrs={'rows': 2}),
        }


class ShumaMonedhaMixin(forms.Form):
    """Shuma shkruhet në monedhën e pagesës (den, €, CHF, $). Ruhet ashtu siç u pagua, si dhe
    e konvertuar në den dhe € (për totalet). Kursi parazgjedhur merret nga faqja e konfigurimit."""
    FUSHA_EUR = None   # emri i fushës në model ku ruhet shuma në €

    shuma_hyrese = forms.DecimalField(
        label='Shuma', max_digits=12, decimal_places=2, min_value=Decimal('0.01'),
    )
    monedha = forms.ChoiceField(
        label='Paguar në', choices=MONEDHA_CHOICES, initial='EUR', widget=forms.RadioSelect,
    )
    kursi = forms.DecimalField(
        label='Kursi (sa denarë)', max_digits=8, decimal_places=4,
        min_value=Decimal('1'), required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.konfigurimi = KonfigurimiSistemit.merr()
        self.fields['kursi'].initial = self.konfigurimi.kursi_eur
        self.fields['monedha'].initial = 'MKD'
        self.kurset = {m: self.konfigurimi.kursi(m) for m, _ in MONEDHA_CHOICES}
        self.kurset_json = json.dumps({m: str(k) for m, k in self.kurset.items()})

    def apliko_shumen(self, pagese):
        shuma, monedha = self.cleaned_data['shuma_hyrese'], self.cleaned_data['monedha']
        kursi_eur = self.konfigurimi.kursi_eur
        # Kursi i shkruar vlen për monedhën e pagesës; te denarët ai është kursi i euros.
        kursi = self.cleaned_data.get('kursi') or self.konfigurimi.kursi(monedha if monedha != 'MKD' else 'EUR')
        if monedha in ('EUR', 'MKD'):
            kursi_eur = kursi
        mkd = shuma if monedha == 'MKD' else shuma * kursi
        eur = shuma if monedha == 'EUR' else mkd / kursi_eur

        pagese.monedha = monedha
        pagese.shuma_monedhe = shuma
        pagese.kursi_denar = kursi
        pagese.shuma_mkd = mkd.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        setattr(pagese, self.FUSHA_EUR, eur.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        return pagese


def sugjero_faturen(model):
    """Faturat e bllokut të BFI-së janë njëra pas tjetrës — sugjero bllokun e fundit dhe numrin pasues."""
    for blloku, nr in model.objects.order_by('-data_regjistrimit').values_list('blloku', 'nr_fatures')[:20]:
        if nr and nr.isdigit():
            return blloku, str(int(nr) + 1).zfill(len(nr))
    return '', ''


class VitetFormMixin(forms.Form):
    """Validon intervalin 'Nga viti — Deri viti' dhe që asnjë vit të mos jetë paguar më parë."""
    VITI_MIN, VITI_MAX = 1990, 2100
    MAX_VITE = 50

    def _vitet_e_paguara(self, shtepia, viti, viti_deri):
        raise NotImplementedError

    def clean(self):
        cd = super().clean()
        viti, viti_deri, shtepia = cd.get('viti'), cd.get('viti_deri'), cd.get('shtepia')
        if viti is None:
            return cd
        if not viti_deri:
            viti_deri = cd['viti_deri'] = viti
        if not (self.VITI_MIN <= viti <= self.VITI_MAX) or not (self.VITI_MIN <= viti_deri <= self.VITI_MAX):
            raise forms.ValidationError(f'Vitet duhet të jenë mes {self.VITI_MIN} dhe {self.VITI_MAX}.')
        if viti_deri < viti:
            self.add_error('viti_deri', '"Deri viti" nuk mund të jetë para "Nga viti".')
        elif viti_deri - viti + 1 > self.MAX_VITE:
            self.add_error('viti_deri', f'Një faturë mund të mbulojë më së shumti {self.MAX_VITE} vite.')
        elif shtepia:
            te_paguara = self._vitet_e_paguara(shtepia, viti, viti_deri)
            if te_paguara:
                self.add_error('viti', 'Këto vite janë paguar tashmë për këtë shtëpi: '
                               + ', '.join(str(v) for v in sorted(te_paguara)))
        return cd


def _vitet_e_mbuluara(pagesat, viti, viti_deri, paguar_deri):
    """Vitet në [viti, viti_deri] që janë paguar tashmë (me pagesa ose historikisht)."""
    te_paguara = {v for v in range(viti, viti_deri + 1) if paguar_deri and v <= paguar_deri}
    for nga, deri in pagesat.filter(viti__lte=viti_deri, viti_deri__gte=viti).values_list('viti', 'viti_deri'):
        te_paguara |= set(range(max(nga, viti), min(deri or nga, viti_deri) + 1))
    return te_paguara


class PagesaAntaresiaForm(ShumaMonedhaMixin, VitetFormMixin, forms.ModelForm):
    FUSHA_EUR = 'shuma_paguar'

    def _vitet_e_paguara(self, shtepia, viti, viti_deri):
        return _vitet_e_mbuluara(shtepia.pagesat, viti, viti_deri, shtepia.paguar_deri_viti)

    class Meta:
        model = PagesaAntaresia
        fields = ['blloku', 'nr_fatures', 'shtepia', 'viti', 'viti_deri', 'data_pageses', 'shenime']
        widgets = {
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
            'shenime': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'blloku': 'Blloku (4 shifra)',
            'nr_fatures': 'Nr. i Faturës (6 shifra)',
            'shtepia': 'Shtëpia',
            'viti': 'Nga Viti',
            'viti_deri': 'Deri Viti',
            'data_pageses': 'Data e Pagesës',
            'shenime': 'Shënime',
        }


class PagesaFondiForm(ShumaMonedhaMixin, forms.ModelForm):
    FUSHA_EUR = 'shuma'

    class Meta:
        model = PagesaFondi
        fields = [
            'blloku', 'nr_fatures', 'lloji', 'emri_donatorit', 'mbiemri_donatorit',
            'email_donatorit', 'nr_telefoni', 'data_pageses', 'arsyeja', 'shenime',
        ]
        widgets = {
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
            'shenime': forms.Textarea(attrs={'rows': 2}),
            'arsyeja': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'blloku': 'Blloku (4 shifra)',
            'nr_fatures': 'Nr. i Faturës (6 shifra)',
            'lloji': 'Lloji i Pagesës',
            'emri_donatorit': 'Emri',
            'mbiemri_donatorit': 'Mbiemri',
            'email_donatorit': 'Email',
            'nr_telefoni': 'Nr. Telefoni',
            'data_pageses': 'Data e Pagesës',
            'arsyeja': 'Arsyeja / Qëllimi (p.sh. emri i aktivitetit)',
            'shenime': 'Shënime',
        }


class PagesaVarrezaveForm(ShumaMonedhaMixin, VitetFormMixin, forms.ModelForm):
    FUSHA_EUR = 'shuma_paguar'

    def _vitet_e_paguara(self, shtepia, viti, viti_deri):
        return _vitet_e_mbuluara(shtepia.pagesat_varrezave, viti, viti_deri, shtepia.varrezat_paguar_deri_viti)

    class Meta:
        model = PagesaVarrezave
        fields = ['blloku', 'nr_fatures', 'shtepia', 'viti', 'viti_deri', 'data_pageses', 'shenime']
        widgets = {
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
            'shenime': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'blloku': 'Blloku (4 shifra)',
            'nr_fatures': 'Nr. i Faturës (6 shifra)',
            'shtepia': 'Shtëpia',
            'viti': 'Nga Viti',
            'viti_deri': 'Deri Viti',
            'data_pageses': 'Data e Pagesës',
            'shenime': 'Shënime',
        }


class KonfigurimiVarrezaveForm(forms.ModelForm):
    class Meta:
        model = KonfigurimiVarrezave
        fields = ['shuma_vjetore', 'pershkrimi']
        widgets = {
            'pershkrimi': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'shuma_vjetore': 'Shuma Vjetore (€) — e njëjtë për çdo shtëpi',
            'pershkrimi': 'Shënime / Përshkrimi i Programit',
        }


class HarxhimiForm(forms.ModelForm):
    muaji = forms.ChoiceField(
        choices=[('', '—')] + list(MUAJT),
        required=False, label='Muaji (vetëm për rroge)'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['stafi'].queryset = User.objects.filter(
            profili__isnull=False, profili__është_aktiv=True
        ).order_by('last_name', 'first_name')
        self.fields['stafi'].required = False
        self.fields['shuma_mkd'].required = False
        self.fields['kursi_denar'].required = False

    def clean_muaji(self):
        val = self.cleaned_data.get('muaji')
        return int(val) if val else None

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('lloji') == 'RROGE' and not cleaned.get('stafi'):
            self.add_error('stafi', 'Zgjidhni stafin për pagesën e rrogës.')
        return cleaned

    class Meta:
        model = Harxhimi
        fields = [
            'lloji', 'burimi', 'stafi', 'muaji', 'viti', 'data_pageses',
            'pershkrimi', 'shuma_eur', 'shuma_mkd', 'kursi_denar',
        ]
        widgets = {
            'pershkrimi': forms.Textarea(attrs={'rows': 3}),
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'lloji': 'Lloji i Harxhimit',
            'burimi': 'Paguhet nga Buxheti',
            'stafi': 'Stafi (vetëm për rroge)',
            'shuma_eur': 'Shuma (€)',
            'shuma_mkd': 'Shuma (MKD) — Opsionale',
            'kursi_denar': 'Kursi EUR/MKD',
        }


class KonfigurimiSistemitForm(forms.ModelForm):
    """Fushat e fjalëkalimeve lihen bosh = mbetet vlera e ruajtur."""
    sms_password = forms.CharField(
        required=False, label='Password', widget=forms.PasswordInput(render_value=False),
    )
    gmail_app_password = forms.CharField(
        required=False, label='Gmail App Password (16 shkronja)',
        widget=forms.PasswordInput(render_value=False),
    )

    class Meta:
        model = KonfigurimiSistemit
        fields = ['sms_username', 'sms_password', 'sms_sim_numri', 'gmail_app_password',
                  'kursi_eur', 'kursi_chf', 'kursi_usd']
        labels = {'sms_username': 'Username'}

    def clean_sms_password(self):
        return self.cleaned_data.get('sms_password') or self.instance.sms_password

    def clean_gmail_app_password(self):
        val = (self.cleaned_data.get('gmail_app_password') or '').replace(' ', '')
        return val or self.instance.gmail_app_password
