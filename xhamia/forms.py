import json
from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.utils import timezone
from django.contrib.auth.models import User
from .models import (
    ProfilStafi, Kategoria, Shtepia, PagesaAntaresia, PagesaFondi, Harxhimi, LlojiPageses,
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
        fields = ['nr_telefoni', 'pozita', 'rol', 'mund_regjistrojë_pagesa']
        labels = {
            'nr_telefoni': 'Nr. Telefoni',
            'pozita': 'Pozita në Xhami',
            'rol': 'Roli',
        }


class KategoriaForm(forms.ModelForm):
    class Meta:
        model = Kategoria
        fields = ['emri', 'pershkrimi', 'shuma_vjetore', 'shuma_vjetore_mkd', 'shuma_6mujore', 'shuma_3mujore',
                  'shuma_mujore', 'renditja', 'është_aktiv']
        labels = {
            'emri': 'Emri i Kategorisë',
            'pershkrimi': 'Përshkrimi',
            'shuma_vjetore': 'Shuma Vjetore (€)',
            'shuma_vjetore_mkd': 'Shuma Vjetore (den)',
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


class ZgjedhjaShtepise(forms.Select):
    """<select> i shtëpive ku çdo opsion mban kontaktet (për t'i plotësuar vetë te forma)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opsioni = super().create_option(name, value, label, selected, index, subindex, attrs)
        sh = getattr(value, 'instance', None)
        if sh is not None:
            opsioni['attrs'].update({
                'data-emri': sh.emri_kryefamiljarit, 'data-mbiemri': sh.mbiemri_kryefamiljarit,
                'data-tel': sh.nr_telefoni_kryesor, 'data-email': sh.email,
                'data-sp-emri': sh.kontakt_sporadik_emri, 'data-sp-tel': sh.kontakt_sporadik_telefoni,
                'data-sp-email': sh.kontakt_sporadik_email,
            })
        return opsioni


class FushaShtepise(forms.ModelChoiceField):
    """Etiketa: "#0589 — Jusuf Nuri Jashari · Florijan · 070…" — që kërkimi të gjejë edhe sipas
    kontaktit sporadik dhe telefonit."""
    widget = ZgjedhjaShtepise

    def __init__(self, **kwargs):
        kwargs.setdefault('queryset', Shtepia.objects.order_by('nr_shtepise'))
        super().__init__(**kwargs)

    def label_from_instance(self, sh):
        shtese = [x for x in (sh.kontakt_sporadik_emri, sh.nr_telefoni_kryesor) if x]
        return f"#{sh.nr_shtepise} — {sh.emri_i_plote}" + (f" · {' · '.join(shtese)}" if shtese else '')


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


def _decimal(vlera):
    try:
        return Decimal(str(vlera).replace(',', '.')) if str(vlera).strip() else None
    except Exception:
        return 'gabim'


def kufijte_json():
    """Kufijtë e kategorive dhe kurset për JavaScript-in e formës (që ta tregojë kategorinë e çdo viti)."""
    from .kategorite import kufijte
    k = KonfigurimiSistemit.merr()
    return json.dumps({
        'kufijte': [{'nr': x.nr, 'emri': x.kategoria.emri if x.kategoria else '', 'eur': str(x.eur), 'mkd': str(x.mkd)}
                    for x in kufijte(k.kursi_eur)],
        'kurset': {m: str(k.kursi(m)) for m, _ in MONEDHA_CHOICES},
    })


EURO_DENAR = 'EUR_MKD'


class PagesaAntaresiaForm(ShumaMonedhaMixin, VitetFormMixin, forms.ModelForm):
    FUSHA_EUR = 'shuma_paguar'
    shtepia = FushaShtepise(label='Shtëpia')
    shuma_2 = forms.DecimalField(
        label='Denarë', max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False,
        help_text='Pjesa në denarë kur paguhet "Euro + Denar", p.sh. 150 € + 3.700 den.',
    )
    monedha_2 = forms.ChoiceField(label='Monedha e dytë', choices=MONEDHA_CHOICES, initial='MKD', required=False)
    vitet_shumat = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        k = self.konfigurimi
        self.tarifat_json = json.dumps({
            'kaluara': str(k.tarifa_vitet_kaluara), 'aktual': str(k.tarifa_viti_aktual),
            'viti': timezone.now().year, 'kursi_eur': str(k.kursi_eur),
        })
        self.kufijte_json = kufijte_json()
        # Opsioni i 5-të: pagesa me euro dhe denarë njëherësh (p.sh. 50 € + 1.300 den) — Myftinia pranon vetëm € dhe den
        self.fields['monedha'].choices = list(MONEDHA_CHOICES) + [(EURO_DENAR, 'Euro + Denar')]

    def _vitet_e_paguara(self, shtepia, viti, viti_deri):
        pagesat = shtepia.pagesat.all()
        if self.instance.pk:   # kur ndryshohet një pagesë, vitet e saj nuk llogariten si "të paguara më parë"
            pagesat = pagesat.exclude(pk=self.instance.pk)
        return _vitet_e_mbuluara(pagesat, viti, viti_deri, shtepia.paguar_deri_viti)

    @classmethod
    def per_ndryshim(cls, pagese, data=None):
        """Forma e mbushur me pagesën ekzistuese (shuma, monedhat, kursi, ndarja sipas viteve)."""
        euro_denar = pagese.monedha == 'EUR' and pagese.monedha_2 == 'MKD' and pagese.shuma_monedhe_2
        initial = {
            'shuma_hyrese': pagese.shuma_ne_monedhe, 'monedha': EURO_DENAR if euro_denar else pagese.monedha,
            'kursi': pagese.kursi_denar,
            'shuma_2': pagese.shuma_monedhe_2, 'monedha_2': pagese.monedha_2 or 'MKD',
            'vitet_shumat': json.dumps(pagese.vitet_shumat) if pagese.vitet_shumat else '',
        }
        return cls(data, instance=pagese, initial=initial)

    def clean(self):
        cd = super().clean()
        if cd.get('monedha') == EURO_DENAR:
            cd['monedha'], cd['monedha_2'] = 'EUR', 'MKD'
            if not cd.get('shuma_2'):
                self.add_error('shuma_2', 'Shkruani edhe denarët (ose zgjidhni vetëm "Euro").')
        monedha, shuma_2 = cd.get('monedha'), cd.get('shuma_2')
        if shuma_2:
            cd['monedha_2'] = cd.get('monedha_2') or 'MKD'
            if cd['monedha_2'] == monedha:
                self.add_error(None, 'Monedha e dytë duhet të jetë tjetër nga e para — për euro dhe denarë zgjidhni "Euro + Denar".')
        else:
            cd['monedha_2'] = ''
        cd['vitet_shumat'] = self._ndarja(cd)
        return cd

    def _ndarja(self, cd):
        """Ndarja sipas viteve nga JSON-i i formës: {"2024": {"EUR": "50"}, ...}. Totali i çdo monedhe
        duhet të jetë sa shuma e pagesës në atë monedhë."""
        teksti = (cd.get('vitet_shumat') or '').strip()
        viti, shuma = cd.get('viti'), cd.get('shuma_hyrese')
        if not teksti or not viti or not shuma or self.errors:
            return {}
        viti_deri = cd.get('viti_deri') or viti
        try:
            ndarja = json.loads(teksti)
            assert isinstance(ndarja, dict)
        except (ValueError, AssertionError):
            self.add_error(None, 'Shumat për çdo vit nuk u lexuan — provoni përsëri.')
            return {}
        pritet = {cd['monedha']: shuma}
        if cd.get('shuma_2'):
            pritet[cd['monedha_2']] = cd['shuma_2']
        rezultati, totalet = {}, {m: Decimal('0') for m in pritet}
        for v in range(viti, viti_deri + 1):
            vlerat = ndarja.get(str(v)) or {}
            for m, s in vlerat.items():
                if m not in pritet and _decimal(s) not in (None, 0):
                    self.add_error(None, f'Viti {v} ka shumë në {m}, por pagesa nuk ka pjesë në këtë monedhë.')
                    return {}
            rreshti = {}
            for m in pritet:
                s = _decimal(vlerat.get(m, ''))
                if s == 'gabim' or (s is not None and s < 0):
                    self.add_error(None, f'Shuma e vitit {v} nuk është numër i rregullt.')
                    return {}
                if s:
                    rreshti[m] = str(int(s)) if s == s.to_integral() else str(s)
                    totalet[m] += s
            if not rreshti:
                self.add_error(None, f'Shkruani shumën e vitit {v} (ose hiqni shenjën "Shuma ndryshon sipas viteve").')
                return {}
            rezultati[str(v)] = rreshti
        for m, total in totalet.items():
            if total != pritet[m]:
                from .models import formato_shumen
                self.add_error(None, f'Shumat e viteve japin {formato_shumen(total, m)}, por pagesa është '
                                     f'{formato_shumen(pritet[m], m)}. Ndreqni shumat që totali të përputhet.')
                return {}
        return rezultati

    def apliko_shumen(self, pagese):
        pagese = super().apliko_shumen(pagese)
        cd = self.cleaned_data
        pagese.vitet_shumat = cd.get('vitet_shumat') or {}
        shuma_2, monedha_2 = cd.get('shuma_2'), cd.get('monedha_2')
        if not shuma_2:
            pagese.monedha_2, pagese.shuma_monedhe_2 = '', None
            return pagese
        # kursi i euros: ai i shkruar te forma (kur pagesa e parë është në € ose den), ndryshe nga konfigurimi
        kursi_eur = pagese.kursi_denar if pagese.monedha in ('EUR', 'MKD') else self.konfigurimi.kursi_eur
        kursi_2 = kursi_eur if monedha_2 == 'EUR' else self.konfigurimi.kursi(monedha_2)
        mkd_2 = shuma_2 * kursi_2
        pagese.monedha_2, pagese.shuma_monedhe_2 = monedha_2, shuma_2
        pagese.shuma_mkd = (pagese.shuma_mkd + mkd_2).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        pagese.shuma_paguar = (pagese.shuma_paguar + mkd_2 / kursi_eur).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return pagese

    class Meta:
        model = PagesaAntaresia
        fields = ['blloku', 'nr_fatures', 'shtepia', 'paguesi', 'viti', 'viti_deri', 'data_pageses', 'shenime']
        widgets = {
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
            'shenime': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'blloku': 'Blloku (4 shifra)',
            'nr_fatures': 'Nr. i Faturës (6 shifra)',
            'shtepia': 'Shtëpia',
            'paguesi': 'Paguar nga (opsionale)',
            'viti': 'Nga Viti',
            'viti_deri': 'Deri Viti',
            'data_pageses': 'Data e Pagesës',
            'shenime': 'Shënime',
        }


def llojet_hyrese_te_fondit(lloji_aktual=None):
    """Llojet hyrëse nga faqja "Llojet e pagesave"; lloji i një pagese të vjetër mbetet i zgjedhshëm."""
    llojet = LlojiPageses.emrat('HYRESE') or [PagesaFondi.LLOJI_PARAZGJEDHUR]
    if lloji_aktual and lloji_aktual not in llojet:
        llojet.append(lloji_aktual)
    return llojet


class PagesaFondiForm(ShumaMonedhaMixin, forms.ModelForm):
    FUSHA_EUR = 'shuma'
    shtepia = FushaShtepise(required=False, label='Shtëpia (opsionale)', empty_label='— Pa shtëpi (donator i jashtëm) —')
    lloji = forms.ChoiceField(label='Lloji i Pagesës')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aktual = self.instance.lloji if self.instance.pk else None
        self.fields['lloji'].choices = [(e, e) for e in llojet_hyrese_te_fondit(aktual)]

    class Meta:
        model = PagesaFondi
        fields = [
            'blloku', 'nr_fatures', 'shtepia', 'lloji', 'emri_donatorit', 'mbiemri_donatorit',
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
    shtepia = FushaShtepise(label='Shtëpia')

    def _vitet_e_paguara(self, shtepia, viti, viti_deri):
        return _vitet_e_mbuluara(shtepia.pagesat_varrezave, viti, viti_deri, shtepia.varrezat_paguar_deri_viti)

    class Meta:
        model = PagesaVarrezave
        fields = ['blloku', 'nr_fatures', 'shtepia', 'paguesi', 'viti', 'viti_deri', 'data_pageses', 'shenime']
        widgets = {
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
            'shenime': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'blloku': 'Blloku (4 shifra)',
            'nr_fatures': 'Nr. i Faturës (6 shifra)',
            'shtepia': 'Shtëpia',
            'paguesi': 'Paguar nga (opsionale)',
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


class HarxhimiForm(ShumaMonedhaMixin, forms.ModelForm):
    """Harxhimet mbahen vetëm për Fondin dhe Varrezat; antarësia i dorëzohet Myftinisë."""
    FUSHA_EUR = 'shuma_eur'
    burimi = forms.ChoiceField(
        label='Paguhet nga buxheti', choices=Harxhimi.BURIMI_CHOICES[:2], initial='FONDI',
    )

    class Meta:
        model = Harxhimi
        fields = ['nr_fatures', 'marresi', 'qyteti', 'llogaria', 'lloji', 'burimi', 'data_pageses', 'pershkrimi']
        widgets = {
            'lloji': forms.TextInput(attrs={'list': 'llojet', 'autocomplete': 'off',
                                            'placeholder': 'p.sh. Rrymë elektrike, Riparim i çatisë…'}),
            'pershkrimi': forms.Textarea(attrs={'rows': 5}),
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'nr_fatures': 'Nr. i fletëpagesës (p.sh. 43/26)',
            'marresi': 'Marrësi — firma / personi fizik',
            'qyteti': 'Nga qyteti / fshati',
            'llogaria': 'Për llogari (opsionale)',
            'lloji': 'Për (lloji i harxhimit)',
            'data_pageses': 'Data',
            'pershkrimi': 'Përshkrimi i detajuar i punës / shërbimit',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['marresi'].required = True

    def clean_nr_fatures(self):
        """Blloku nuk është më në formë, prandaj kontrolli i numrit të dyfishtë bëhet këtu (ndryshe: IntegrityError)."""
        nr = (self.cleaned_data.get('nr_fatures') or '').strip()
        te_njejta = Harxhimi.objects.filter(blloku=self.instance.blloku or '', nr_fatures=nr)
        if self.instance.pk:
            te_njejta = te_njejta.exclude(pk=self.instance.pk)
        if te_njejta.exists():
            raise forms.ValidationError(f'Fletëpagesa nr {nr} është regjistruar tashmë.')
        return nr


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
                  'kursi_eur', 'kursi_chf', 'kursi_usd', 'tarifa_vitet_kaluara', 'tarifa_viti_aktual']
        labels = {
            'sms_username': 'Username',
            'kursi_eur': 'Kursi blerës: 1 € = ? den', 'kursi_chf': 'Kursi blerës: 1 CHF = ? den',
            'kursi_usd': 'Kursi blerës: 1 $ = ? den',
        }

    def clean_sms_password(self):
        return self.cleaned_data.get('sms_password') or self.instance.sms_password

    def clean_gmail_app_password(self):
        val = (self.cleaned_data.get('gmail_app_password') or '').replace(' ', '')
        return val or self.instance.gmail_app_password
