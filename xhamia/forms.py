from django import forms
from django.contrib.auth.models import User
from .models import ProfilStafi, Kategoria, Shtepia, PagesaAntaresia, PagesaFondi


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
            'nr_shtepise', 'emri_kryefamiljarit', 'mbiemri_kryefamiljarit',
            'nr_antareve_familjes', 'kategoria',
            'email', 'nr_telefoni_kryesor', 'nr_telefoni_sporadik',
            'kontakt_sporadik_emri', 'kontakt_sporadik_email', 'kontakt_sporadik_telefoni',
            'shenime', 'është_aktiv',
        ]
        widgets = {
            'shenime': forms.Textarea(attrs={'rows': 2}),
        }


class PagesaAntaresiaForm(forms.ModelForm):
    muaji_fillimit = forms.ChoiceField(
        choices=[('', '—')] + MUAJT, required=False, label='Muaji Fillimit'
    )
    muaji_mbarimit = forms.ChoiceField(
        choices=[('', '—')] + MUAJT, required=False, label='Muaji Mbarimit'
    )

    def clean_muaji_fillimit(self):
        val = self.cleaned_data.get('muaji_fillimit')
        return int(val) if val else None

    def clean_muaji_mbarimit(self):
        val = self.cleaned_data.get('muaji_mbarimit')
        return int(val) if val else None

    class Meta:
        model = PagesaAntaresia
        fields = [
            'shtepia', 'kategoria_pageses', 'shuma_paguar',
            'periudha', 'viti', 'muaji_fillimit', 'muaji_mbarimit',
            'data_pageses', 'shenime',
        ]
        widgets = {
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
            'shenime': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'shtepia': 'Shtëpia',
            'kategoria_pageses': 'Kategoria',
            'shuma_paguar': 'Shuma (€)',
            'periudha': 'Periudha e Pagesës',
            'viti': 'Viti',
            'data_pageses': 'Data e Pagesës',
            'shenime': 'Shënime',
        }


class PagesaFondiForm(forms.ModelForm):
    class Meta:
        model = PagesaFondi
        fields = [
            'emri_donatorit', 'mbiemri_donatorit',
            'email_donatorit', 'nr_telefoni',
            'shuma', 'data_pageses', 'arsyeja', 'shenime',
        ]
        widgets = {
            'data_pageses': forms.DateInput(attrs={'type': 'date'}),
            'shenime': forms.Textarea(attrs={'rows': 2}),
            'arsyeja': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'emri_donatorit': 'Emri',
            'mbiemri_donatorit': 'Mbiemri',
            'email_donatorit': 'Email',
            'nr_telefoni': 'Nr. Telefoni',
            'shuma': 'Shuma (€)',
            'data_pageses': 'Data e Pagesës',
            'arsyeja': 'Arsyeja / Qëllimi',
            'shenime': 'Shënime',
        }
