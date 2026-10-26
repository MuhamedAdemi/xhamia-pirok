from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import sms
from .models import Kategoria, KonfigurimiSistemit, MesazhSMS, PagesaAntaresia, ProfilStafi, Shtepia


class NormalizoNumrinTest(TestCase):
    def test_formatet(self):
        self.assertEqual(sms.normalizo_numrin('070 123 456'), '+38970123456')
        self.assertEqual(sms.normalizo_numrin('+389 70/123-456'), '+38970123456')
        self.assertEqual(sms.normalizo_numrin('0038970123456'), '+38970123456')
        self.assertEqual(sms.normalizo_numrin('38970123456'), '+38970123456')
        self.assertEqual(sms.normalizo_numrin('70123456'), '+38970123456')
        self.assertEqual(sms.normalizo_numrin('+49 151 23456789'), '+4915123456789')

    def test_te_pavlefshme(self):
        self.assertIsNone(sms.normalizo_numrin(''))
        self.assertIsNone(sms.normalizo_numrin(None))
        self.assertIsNone(sms.normalizo_numrin('abc'))
        self.assertIsNone(sms.normalizo_numrin('123'))

    def test_pastro_tekstin(self):
        self.assertEqual(sms.pastro_tekstin('Shpërbleftë — çdo'), 'Shperblefte - cdo')


def _pergjigje(json_data):
    r = mock.Mock()
    r.json.return_value = json_data
    r.raise_for_status.return_value = None
    return r


@override_settings(SMS_GATEWAY_USER='u', SMS_GATEWAY_PASSWORD='p', SMS_PRIT_SEKONDA=0)
class SmsViewsTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', first_name='A', last_name='B')
        ProfilStafi.objects.create(user=self.admin, rol='ADMIN')
        self.client.force_login(self.admin)
        self.kat = Kategoria.objects.create(emri='Normale', shuma_vjetore=Decimal('60'))
        viti = timezone.now().year
        self.borxhli = Shtepia.objects.create(
            nr_shtepise='0001', emri_kryefamiljarit='Muhamed', emri_prindit='Mesud',
            mbiemri_kryefamiljarit='Ademi', kategoria=self.kat,
            viti_fillimit_antaresise=viti - 2, nr_telefoni_kryesor='070 123 456',
        )
        self.pa_numer = Shtepia.objects.create(
            nr_shtepise='0002', emri_kryefamiljarit='Ali', mbiemri_kryefamiljarit='X',
            kategoria=self.kat, viti_fillimit_antaresise=viti - 2,
        )
        self.i_rregullt = Shtepia.objects.create(
            nr_shtepise='0003', emri_kryefamiljarit='Ibrahim', mbiemri_kryefamiljarit='Y',
            kategoria=self.kat, viti_fillimit_antaresise=viti - 1, paguar_deri_viti=viti,
            nr_telefoni_kryesor='070999888',
        )

    def test_borxhlinjte_lista(self):
        r = self.client.get(reverse('borxhlinjte_sms'))
        self.assertEqual(r.status_code, 200)
        nr = [b['shtepi'].nr_shtepise for b in r.context['borxhlinjte']]
        self.assertEqual(nr, ['0001', '0002'])
        self.assertEqual(r.context['borxhlinjte'][0]['borxhi'], Decimal('170'))  # 50 + 50 + 70
        self.assertEqual(r.context['pa_numer'], 1)

    @mock.patch('xhamia.sms.requests.post')
    def test_dergo_kujtese(self, post):
        post.return_value = _pergjigje({'id': 'abc', 'state': 'Pending'})
        r = self.client.post(reverse('borxhlinjte_sms') + '?min_vite=2', {
            'teksti': 'I nderuar {emri}, vitet {vitet}, {borxhi} EUR, shtëpia {nr}',
            'shtepite': [self.borxhli.pk, self.pa_numer.pk],
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(post.call_count, 1)
        body = post.call_args.kwargs['json']
        self.assertEqual(body['phoneNumbers'], ['+38970123456'])
        self.assertIn('Muhamed Mesud Ademi', body['textMessage']['text'])
        self.assertIn('shtepia 0001', body['textMessage']['text'])
        m = MesazhSMS.objects.get()
        self.assertEqual((m.lloji, m.statusi, m.id_gateway), ('KUJTESE', 'NE_PRITJE', 'abc'))

    @mock.patch('xhamia.sms.requests.post')
    def test_konfirmim_pagese(self, post):
        post.return_value = _pergjigje({'id': 'z1', 'state': 'Pending'})
        pagese = PagesaAntaresia.objects.create(
            shtepia=self.borxhli, kategoria_pageses=self.kat, shuma_paguar=Decimal('60'),
            viti=timezone.now().year, data_pageses=date.today(), arktar=self.admin,
        )
        detaje = self.client.get(reverse('detaje_pagesa_antaresia', args=[pagese.pk]))
        self.assertContains(detaje, reverse('dergo_sms_antaresia', args=[pagese.pk]))
        r = self.client.post(reverse('dergo_sms_antaresia', args=[pagese.pk]))
        self.assertRedirects(r, reverse('detaje_pagesa_antaresia', args=[pagese.pk]))
        self.assertIn(pagese.nr_fatures, post.call_args.kwargs['json']['textMessage']['text'])
        self.assertEqual(MesazhSMS.objects.get().lloji, 'KONFIRMIM')

    @mock.patch('xhamia.sms.requests.get')
    def test_historiku_perditeso(self, get):
        MesazhSMS.objects.create(nr_telefoni='+38970123456', teksti='t', lloji='KUJTESE', id_gateway='abc')
        get.return_value = _pergjigje({'id': 'abc', 'state': 'Delivered'})
        self.client.post(reverse('historiku_sms'))
        self.assertEqual(MesazhSMS.objects.get().statusi, 'DORZUAR')
        self.assertEqual(self.client.get(reverse('historiku_sms')).status_code, 200)

    @override_settings(SMS_GATEWAY_USER='', SMS_GATEWAY_PASSWORD='')
    def test_pa_konfigurim_deshton_qarte(self):
        m = sms.dergo_sms('070123456', 'test', 'KUJTESE', self.admin)
        self.assertEqual(m.statusi, 'DESHTOI')
        self.assertIn('nuk është konfiguruar', m.gabimi)


@override_settings(SMS_PRIT_SEKONDA=0)
class KonfigurimiSistemitTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x')
        ProfilStafi.objects.create(user=self.admin, rol='ADMIN')
        self.client.force_login(self.admin)

    def test_ruaj_dhe_mbaj_fjalekalimin(self):
        url = reverse('konfigurimi_sistemit')
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {'veprimi': 'ruaj', 'sms_username': 'ABC', 'sms_password': 'sekret',
                               'sms_sim_numri': '1', 'gmail_app_password': 'abcd efgh ijkl mnop',
                               'kursi_eur': '61.5', 'kursi_chf': '66', 'kursi_usd': '57',
                               'tarifa_vitet_kaluara': '50', 'tarifa_viti_aktual': '70'})
        self.assertEqual(KonfigurimiSistemit.merr().sms_sim_numri, 1)
        k = KonfigurimiSistemit.merr()
        self.assertEqual((k.sms_username, k.sms_password, k.gmail_app_password),
                         ('ABC', 'sekret', 'abcdefghijklmnop'))
        # Fjalëkalimet bosh = mbeten të vjetrat
        self.client.post(url, {'veprimi': 'ruaj', 'sms_username': 'ABC2', 'sms_password': '', 'gmail_app_password': '',
                               'kursi_eur': '61.5', 'kursi_chf': '66', 'kursi_usd': '57',
                               'tarifa_vitet_kaluara': '50', 'tarifa_viti_aktual': '70'})
        k.refresh_from_db()
        self.assertEqual((k.sms_username, k.sms_password, k.gmail_app_password),
                         ('ABC2', 'sekret', 'abcdefghijklmnop'))

    @mock.patch('xhamia.sms.requests.post')
    def test_sms_prove_perdor_kredencialet_nga_db(self, post):
        KonfigurimiSistemit.objects.create(pk=1, sms_username='ABC', sms_password='sekret', sms_sim_numri=1)
        post.return_value = _pergjigje({'id': 'p1', 'state': 'Pending'})
        self.client.post(reverse('konfigurimi_sistemit'), {'veprimi': 'prove_sms', 'nr_prove': '070123456'})
        self.assertEqual(post.call_args.kwargs['auth'], ('ABC', 'sekret'))
        self.assertEqual(post.call_args.kwargs['json']['simNumber'], 1)

    def test_email_backend_merr_fjalekalimin_nga_db(self):
        from .email_backend import GmailBackend
        KonfigurimiSistemit.objects.create(pk=1, gmail_app_password='nga-db')
        self.assertEqual(GmailBackend().password, 'nga-db')


class PagesatShumeViteTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', first_name='A', last_name='B')
        ProfilStafi.objects.create(user=self.admin, rol='ADMIN')
        self.client.force_login(self.admin)
        self.sh = Shtepia.objects.create(
            nr_shtepise='0001', emri_kryefamiljarit='Muhamed', emri_prindit='Mesud',
            mbiemri_kryefamiljarit='Ademi', viti_fillimit_antaresise=2000,
        )

    def _paguaj(self, **te_dhenat):
        data = {
            'blloku': '1100', 'nr_fatures': '004512', 'shtepia': self.sh.pk, 'viti': 2000, 'viti_deri': '',
            'data_pageses': '2026-10-24', 'shuma_hyrese': '70', 'monedha': 'EUR', 'kursi': '61.5',
        }
        data.update(te_dhenat)
        return self.client.post(reverse('shto_pagese_antaresia'), data)

    def test_denar_konvertohet_ne_euro(self):
        self._paguaj(shuma_hyrese='4300', monedha='MKD', viti=2026)
        p = PagesaAntaresia.objects.get()
        self.assertEqual((p.monedha, p.shuma_mkd, p.shuma_paguar), ('MKD', Decimal('4300'), Decimal('69.92')))
        self.assertEqual(p.shuma_origjinale, '4.300 den')
        self.assertIsNone(p.kategoria_pageses)

    def test_euro_konvertohet_ne_denar(self):
        self._paguaj(shuma_hyrese='70', monedha='EUR', viti=2026)
        p = PagesaAntaresia.objects.get()
        self.assertEqual((p.shuma_paguar, p.shuma_mkd), (Decimal('70'), Decimal('4305')))

    def test_nje_fature_per_shume_vite_dhe_vite_te_ardhshme(self):
        r = self._paguaj(viti=2000, viti_deri=2027, shuma_hyrese='1960')
        self.assertEqual(r.status_code, 302)
        p = PagesaAntaresia.objects.get()
        self.assertEqual((p.nr_viteve, p.vitet_tekst), (28, '2000–2027'))
        detaje = self.client.get(reverse('detaje_shtepia', args=[self.sh.pk]))
        self.assertEqual(detaje.context['nr_papaguara'], 0)
        self.assertTrue(detaje.context['pagesat_per_vit'][2027]['ka_paguar'])
        self.assertEqual(detaje.context['pagesat_per_vit'][2000]['shuma_paguar'], Decimal('70.00'))
        lista = self.client.get(reverse('lista_pagesa_antaresia') + '?viti=2013')
        self.assertEqual(list(lista.context['pagesat']), [p])

    def test_vitet_e_paguara_nuk_paguhen_dy_here(self):
        self._paguaj(viti=2020, viti_deri=2022)
        r = self._paguaj(nr_fatures='004513', viti=2022, viti_deri=2024)
        self.assertEqual(r.status_code, 200)
        self.assertIn('2022', r.context['form'].errors['viti'][0])
        self.assertEqual(PagesaAntaresia.objects.count(), 1)

    def test_nr_fatures_detyrueshem_unik_dhe_sugjerohet(self):
        self._paguaj(viti=2026)
        r = self._paguaj(viti=2025)
        self.assertIn('regjistruar tashmë', r.context['form'].non_field_errors()[0])
        self.assertEqual(self._paguaj(viti=2025, blloku='1101').status_code, 302)  # tjetër bllok, i njëjti nr
        forma = self.client.get(reverse('shto_pagese_antaresia') + f'?shtepi={self.sh.pk}')
        self.assertEqual(forma.context['form'].initial['blloku'], '1101')
        self.assertEqual(forma.context['form'].initial['nr_fatures'], '004513')
        self.assertEqual(forma.context['form'].initial['viti'], 2000)

    def test_borxhi_pa_kategori_numeron_vitet(self):
        detaje = self.client.get(reverse('detaje_shtepia', args=[self.sh.pk]))
        self.assertEqual(detaje.context['nr_papaguara'], timezone.now().year - 2000 + 1)
        vite = timezone.now().year - 2000 + 1
        self.assertEqual(detaje.context['borxhi_total'], Decimal('50') * (vite - 1) + Decimal('70'))

    def test_varrezat_dhe_fondi_me_denar(self):
        r = self.client.post(reverse('shto_pagese_varrezat'), {
            'nr_fatures': '900001', 'shtepia': self.sh.pk, 'viti': 2024, 'viti_deri': 2026,
            'data_pageses': '2026-10-24', 'shuma_hyrese': '3000', 'monedha': 'MKD', 'kursi': '61.5',
        })
        self.assertEqual(r.status_code, 302)
        r = self.client.post(reverse('shto_pagese_fondi'), {
            'nr_fatures': '700001', 'lloji': 'DHURATE', 'emri_donatorit': 'A', 'mbiemri_donatorit': 'B',
            'data_pageses': '2026-10-24', 'shuma_hyrese': '50', 'monedha': 'EUR', 'kursi': '61.5',
        })
        self.assertEqual(r.status_code, 302)

    def test_faqet_hapen(self):
        self._paguaj(viti=2000, viti_deri=2026, shuma_hyrese='4300', monedha='MKD')
        p = PagesaAntaresia.objects.get()
        for url in [
            reverse('dashboard'), reverse('dashboard_varrezat'), reverse('dashboard_buxheti'),
            reverse('lista_shtepive'), reverse('detaje_shtepia', args=[self.sh.pk]),
            reverse('lista_pagesa_antaresia'), reverse('lista_pagesa_varrezave'), reverse('lista_pagesa_fondi'),
            reverse('shto_pagese_antaresia'), reverse('shto_pagese_varrezat'), reverse('shto_pagese_fondi'),
            reverse('detaje_pagesa_antaresia', args=[p.pk]), reverse('fatura_antaresia_pdf', args=[p.pk]),
            reverse('importo_shtepite'), reverse('borxhlinjte_sms'),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)


@override_settings(SMS_PRIT_SEKONDA=0)
class BllokuMonedhatRegjistriTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', first_name='A', last_name='B')
        ProfilStafi.objects.create(user=self.admin, rol='ADMIN')
        self.client.force_login(self.admin)
        self.sh = Shtepia.objects.create(
            nr_shtepise='0001', emri_kryefamiljarit='Muhamed', emri_prindit='Mesud',
            mbiemri_kryefamiljarit='Ademi', viti_fillimit_antaresise=2024,
        )

    def _paguaj(self, **te_dhenat):
        data = {
            'blloku': '1100', 'nr_fatures': '046386', 'shtepia': self.sh.pk, 'viti': 2024, 'viti_deri': 2026,
            'data_pageses': '2026-10-24', 'shuma_hyrese': '10000', 'monedha': 'MKD', 'kursi': '61.5',
        }
        data.update(te_dhenat)
        return self.client.post(reverse('shto_pagese_antaresia'), data)

    def test_fatura_me_bllok_dhe_tre_vite(self):
        self.assertEqual(self._paguaj().status_code, 302)
        p = PagesaAntaresia.objects.get()
        self.assertEqual(p.fatura_tekst, 'Bllok 1100 nr 046386')
        self.assertEqual((p.nr_viteve, p.shuma_origjinale), (3, '10.000 den'))
        self.assertIn('Bllok 1100 nr 046386', sms.teksti_antaresia(p))
        self.assertContains(self.client.get(reverse('detaje_pagesa_antaresia', args=[p.pk])), 'Bllok 1100 nr 046386')

    def test_franga_konvertohen_me_kursin_e_vet(self):
        self._paguaj(monedha='CHF', shuma_hyrese='100', kursi='66')
        p = PagesaAntaresia.objects.get()
        self.assertEqual((p.monedha, p.shuma_monedhe, p.shuma_mkd), ('CHF', Decimal('100'), Decimal('6600')))
        self.assertEqual(p.shuma_paguar, Decimal('107.32'))  # 6600 / 61.5
        self.assertEqual(p.shuma_origjinale, '100 CHF')

    def test_regjistri_me_totale_per_bllok_dhe_muaj(self):
        from . import raporti
        self._paguaj(nr_fatures='046386', data_pageses='2026-01-05', viti=2024, viti_deri=2024)
        self._paguaj(nr_fatures='046387', data_pageses='2026-01-06', viti=2025, viti_deri=2025, monedha='EUR', shuma_hyrese='70')
        self._paguaj(blloku='1262', nr_fatures='026351', data_pageses='2026-02-01', viti=2026, viti_deri=2027)
        rreshtat, gjithsej = raporti.ndertoj_regjistrin('antaresia', 2026, 'vit')
        tipet = [r['tip'] for r in rreshtat]
        self.assertEqual(tipet, ['titull', 'pagese', 'pagese', 'bllok', 'muaj', 'titull', 'pagese', 'bllok', 'muaj',
                                 'tremujor', 'gjashtemujor', 'gjithsej'])
        self.assertEqual(rreshtat[3]['totali'].shumat['MKD'], Decimal('10000'))
        self.assertEqual(rreshtat[3]['totali'].shumat['EUR'], Decimal('70'))
        self.assertEqual((gjithsej.nr, gjithsej.vite), (3, 4))
        self.assertTrue(raporti.regjistri_excel('antaresia', 2026, 'q1').startswith(b'PK'))
        r = self.client.get(reverse('regjistri') + '?lloji=antaresia&viti=2026&periudha=vit')
        self.assertContains(r, 'Bllok 1262')
        r = self.client.get(reverse('regjistri') + '?lloji=fondi&viti=2026&eksporto=excel')
        self.assertEqual(r.status_code, 200)

    def test_csv_borxhlinjte(self):
        from io import BytesIO
        from .importi_pdf import lexo_borxhlinjte_csv, celesi
        csv_ = 'emri;prindi;mbiemri;viti_nga;viti_deri\nAbduraman;Belul;Ademi;2016;2026\n'.encode('utf-8-sig')
        self.assertEqual(lexo_borxhlinjte_csv(BytesIO(csv_)), {celesi('Abduraman', 'Belul', 'Ademi'): 2016})


class ImportiExcelBackupTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', first_name='A', last_name='B')
        ProfilStafi.objects.create(user=self.admin, rol='ADMIN')
        self.client.force_login(self.admin)

    def _excel(self, rreshtat):
        from io import BytesIO
        from openpyxl import Workbook
        from .backup import KOLONAT_SHTEPITE, shkruaj_shtepite, _fleta
        wb = Workbook()
        shkruaj_shtepite(_fleta(wb, 'Shtëpitë', KOLONAT_SHTEPITE, e_para=True), rreshtat)
        b = BytesIO()
        wb.save(b)
        b.seek(0)
        b.name = 'shtepite.xlsx'
        return b

    def test_importi_gjendja_dhe_borxhi(self):
        viti = timezone.now().year
        Shtepia.objects.create(nr_shtepise='0001', emri_kryefamiljarit='Gajur', emri_prindit='Shemsedin',
                               mbiemri_kryefamiljarit='Aliu', viti_fillimit_antaresise=viti)
        excel = self._excel([
            {'Nr.': '0001', 'Emri': 'Gajur', 'Emri i Prindit': 'Shemsedin', 'Mbiemri': 'Aliu', 'Paguar deri viti': viti},
            {'Nr.': '0002', 'Emri': 'Gajur', 'Emri i Prindit': 'Shemsedin', 'Mbiemri': 'Aliu', 'Paguar deri viti': viti},
            {'Nr.': '0003', 'Emri': 'Abduraman', 'Emri i Prindit': 'Belul', 'Mbiemri': 'Ademi', 'Borxh nga viti': 2016},
            {'Nr.': '', 'Emri': 'Agim', 'Emri i Prindit': '', 'Mbiemri': 'Rakipi', 'Borxh nga viti': viti},
        ])
        r = self.client.post(reverse('importo_shtepite'), {'burimi': 'excel', 'veprimi': 'importo', 'xlsx_shtepite': excel})
        rap = r.context['raporti_excel']
        self.assertEqual((rap['te_reja'], rap['perditesuara'], rap['paguar'], rap['borxh_shume_vite'],
                          rap['borxh_vetem_aktual']), (3, 1, 2, 1, 1))
        self.assertEqual(Shtepia.objects.filter(emri_kryefamiljarit='Gajur').count(), 2)

        lista = self.client.get(reverse('lista_shtepive') + '?borxhi=2')
        borxhliu = list(lista.context['shtepite'])
        self.assertEqual([sh.mbiemri_kryefamiljarit for sh in borxhliu], ['Ademi'])
        vite = viti - 2016 + 1
        self.assertEqual(borxhliu[0].nr_papaguara, vite)
        self.assertEqual(borxhliu[0].borxhi_minimal, Decimal('50') * (vite - 1) + Decimal('70'))

        detaje = self.client.get(reverse('detaje_shtepia', args=[borxhliu[0].pk]))
        self.assertEqual(detaje.context['nr_papaguara'], vite)

    def test_importi_me_gabime_nuk_ruan(self):
        excel = self._excel([{'Emri': 'A', 'Mbiemri': 'B', 'Borxh nga viti': 'abc'}])
        r = self.client.post(reverse('importo_shtepite'), {'burimi': 'excel', 'veprimi': 'importo', 'xlsx_shtepite': excel})
        self.assertTrue(r.context['raporti_excel']['gabime'])
        self.assertFalse(Shtepia.objects.exists())

    def test_backup_dhe_rikthimi(self):
        import tempfile, zipfile
        from pathlib import Path
        from django.core import management
        sh = Shtepia.objects.create(nr_shtepise='0007', emri_kryefamiljarit='Muhamed', emri_prindit='Mesud',
                                    mbiemri_kryefamiljarit='Ademi', viti_fillimit_antaresise=2024)
        PagesaAntaresia.objects.create(blloku='1100', nr_fatures='046386', shtepia=sh, shuma_paguar=Decimal('70'),
                                       viti=2024, viti_deri=2026, data_pageses=date.today(), arktar=self.admin)
        r = self.client.get(reverse('backup') + '?shkarko=tani')
        self.assertEqual(r['Content-Type'], 'application/zip')
        with tempfile.TemporaryDirectory() as d:
            zip_rruga = Path(d) / 'b.zip'
            zip_rruga.write_bytes(r.content)
            self.assertEqual(len(zipfile.ZipFile(zip_rruga).namelist()), 3)
            PagesaAntaresia.objects.all().delete()
            Shtepia.objects.all().delete()
            with override_settings(BACKUP_DIR=d):
                management.call_command('rikthe_backup', str(zip_rruga), po=True, verbosity=0)
        p = PagesaAntaresia.objects.get()
        self.assertEqual((p.fatura_tekst, p.shtepia.emri_i_plote, p.arktar.username),
                         ('Bllok 1100 nr 046386', 'Muhamed Mesud Ademi', 'admin'))
        self.assertEqual(self.client.get(reverse('backup')).status_code, 302)  # sesioni u fshi me flush

    def test_backup_automatik_dhe_pastrimi(self):
        import tempfile
        from pathlib import Path
        from django.core import mail, management
        with tempfile.TemporaryDirectory() as d, override_settings(BACKUP_DIR=d):
            for emri in ['xhamia_2020-01-05_0300.zip', 'xhamia_2020-01-20_0300.zip', 'xhamia_2020-02-03_0300.zip']:
                (Path(d) / emri).write_bytes(b'x')
            management.call_command('backup_automatik', email=True, stdout=__import__('io').StringIO())
            mbetur = sorted(f.name for f in Path(d).glob('*.zip'))
        self.assertIn('xhamia_2020-01-05_0300.zip', mbetur)      # i pari i muajit mbahet
        self.assertNotIn('xhamia_2020-01-20_0300.zip', mbetur)   # i vjetër, jo i pari i muajit
        self.assertEqual(len(mbetur), 3)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].attachments)


class FilloNgaZeroTest(TestCase):
    def test_fshin_te_dhenat_por_ruan_stafin_dhe_konfigurimin(self):
        import tempfile
        from pathlib import Path
        from .models import ProfilShtepi
        admin = User.objects.create_user('admin', password='x')
        ProfilStafi.objects.create(user=admin, rol='ADMIN')
        self.client.force_login(admin)
        KonfigurimiSistemit.objects.create(pk=1, sms_username='DC75HC', sms_password='p')
        sh = Shtepia.objects.create(nr_shtepise='0001', emri_kryefamiljarit='Test', mbiemri_kryefamiljarit='T',
                                    viti_fillimit_antaresise=2026)
        PagesaAntaresia.objects.create(blloku='1', nr_fatures='1', shtepia=sh, shuma_paguar=Decimal('70'),
                                       viti=2026, data_pageses=date.today(), arktar=admin)
        u_shtepi = User.objects.create_user('sh0001', password='x')
        ProfilShtepi.objects.create(user=u_shtepi, shtepia=sh)

        url = reverse('fillo_nga_zero')
        with tempfile.TemporaryDirectory() as d, override_settings(BACKUP_DIR=d):
            self.assertContains(self.client.get(url), 'Shtëpi: 1')
            self.client.post(url, {'veprimi': 'hapi1'})
            kodi = self.client.session['fshirje_fillo_nga_zero_kod']
            self.client.post(url, {'veprimi': 'hapi2', 'kodi': kodi})
            r = self.client.post(url, {'veprimi': 'hapi3'})
            self.assertRedirects(r, reverse('importo_shtepite'))
            self.assertEqual(len(list(Path(d).glob('para-fshirjes_*.zip'))), 1)

        self.assertFalse(Shtepia.objects.exists())
        self.assertFalse(PagesaAntaresia.objects.exists())
        self.assertFalse(User.objects.filter(username='sh0001').exists())
        self.assertTrue(User.objects.filter(username='admin').exists())
        self.assertEqual(KonfigurimiSistemit.merr().sms_username, 'DC75HC')


@override_settings(SMS_GATEWAY_USER='u', SMS_GATEWAY_PASSWORD='p', SMS_PRIT_SEKONDA=0)
class SmsNjeNeKoheTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        admin = User.objects.create_user('admin', password='x')
        ProfilStafi.objects.create(user=admin, rol='ADMIN')
        self.client.force_login(admin)
        self.sh = Shtepia.objects.create(nr_shtepise='0001', emri_kryefamiljarit='A', mbiemri_kryefamiljarit='B',
                                         viti_fillimit_antaresise=2026, nr_telefoni_kryesor='070123456')
        self.p1 = PagesaAntaresia.objects.create(blloku='1', nr_fatures='1', shtepia=self.sh, shuma_paguar=Decimal('70'),
                                                 viti=2026, data_pageses=date.today(), arktar=admin)
        self.p2 = PagesaAntaresia.objects.create(blloku='1', nr_fatures='2', shtepia=self.sh, shuma_paguar=Decimal('70'),
                                                 viti=2025, data_pageses=date.today(), arktar=admin)

    @mock.patch('xhamia.sms.requests.delete')
    @mock.patch('xhamia.sms.requests.get')
    @mock.patch('xhamia.sms.requests.post')
    def test_sms_i_ri_pret_pergjigjen_e_te_mëparshmit(self, post, get, delete):
        post.return_value = _pergjigje({'id': 'a', 'state': 'Pending'})
        get.return_value = _pergjigje({'id': 'a', 'state': 'Pending'})
        self.client.post(reverse('dergo_sms_antaresia', args=[self.p1.pk]))
        body = post.call_args.kwargs['json']
        self.assertEqual((body['ttl'], body['priority']), (120, 100))

        # 30 klikime te një pagesë tjetër, ndërsa i pari pret ende → asnjë SMS i ri
        for _ in range(30):
            r = self.client.post(reverse('dergo_sms_antaresia', args=[self.p2.pk]), follow=True)
        self.assertEqual(post.call_count, 1)
        self.assertContains(r, 'ende pret përgjigje')

        # Pas 2 minutash pa përgjigje: i pari anulohet dhe lejohet SMS i ri
        MesazhSMS.objects.update(data_dergimit=timezone.now() - timezone.timedelta(minutes=3))
        self.client.post(reverse('dergo_sms_antaresia', args=[self.p2.pk]))
        self.assertEqual(delete.call_count, 1)
        self.assertEqual(post.call_count, 2)
        i_pari = MesazhSMS.objects.order_by('data_dergimit').first()
        self.assertEqual(i_pari.statusi, 'DESHTOI')
        self.assertIn('Anuluar', i_pari.gabimi)

    @mock.patch('xhamia.sms.requests.get')
    @mock.patch('xhamia.sms.requests.post')
    def test_ridergimi_kerkon_konfirmim(self, post, get):
        post.return_value = _pergjigje({'id': 'a', 'state': 'Sent'})
        url = reverse('dergo_sms_antaresia', args=[self.p1.pk])
        r = self.client.post(url, follow=True)
        self.assertContains(r, 'SMS-i u dërgua')
        r = self.client.post(url)
        self.assertTemplateUsed(r, 'sms/konfirmo_ridergim.html')
        self.assertEqual(post.call_count, 1)
        self.client.post(url, {'ridergo': 'po'})
        self.assertEqual(post.call_count, 2)

    @mock.patch('xhamia.sms.time', create=True)
    @mock.patch('xhamia.sms.requests.get')
    @mock.patch('xhamia.sms.requests.post')
    def test_pret_pergjigjen_e_telefonit(self, post, get, _):
        from . import sms as sms_modul
        post.return_value = _pergjigje({'id': 'a', 'state': 'Pending'})
        get.return_value = _pergjigje({'id': 'a', 'state': 'Sent'})
        m = sms_modul.dergo_sms('070123456', 't', 'KONFIRMIM', None, ttl=120)
        with mock.patch('time.sleep'):
            sms_modul.prit_pergjigjen(m, sekonda=10)
        self.assertEqual(m.statusi, 'DERGUAR')


class FondiShtepiaKerkimiMonedhatTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x')
        ProfilStafi.objects.create(user=self.admin, rol='ADMIN')
        self.client.force_login(self.admin)
        self.sh = Shtepia.objects.create(
            nr_shtepise='0589', emri_kryefamiljarit='Jusuf', emri_prindit='Nuri', mbiemri_kryefamiljarit='Jashari',
            viti_fillimit_antaresise=2026, nr_telefoni_kryesor='070111222',
            kontakt_sporadik_emri='Florijan Jashari', kontakt_sporadik_telefoni='070333444',
        )
        Shtepia.objects.create(nr_shtepise='0001', emri_kryefamiljarit='Agim', emri_prindit='Bexhet',
                               mbiemri_kryefamiljarit='Asipi', viti_fillimit_antaresise=2026)

    def test_kerkimi_gjen_me_pjese_emri_prindi_dhe_kontakt_sporadik(self):
        for q in ['nuri', 'jusu', 'flor', 'JASH flor', '0589', '333444', 'jashari nuri']:
            r = self.client.get(reverse('lista_shtepive') + f'?kerkimi={q}&statusi=te_gjitha')
            self.assertEqual([sh.nr_shtepise for sh in r.context['shtepite']], ['0589'], q)
        r = self.client.get(reverse('lista_shtepive') + '?kerkimi=xyz&statusi=te_gjitha')
        self.assertEqual(list(r.context['shtepite']), [])

    def test_pagesa_e_fondit_lidhet_me_shtepine(self):
        forma = self.client.get(reverse('shto_pagese_fondi') + f'?shtepi={self.sh.pk}')
        self.assertEqual(forma.context['form'].initial['nr_telefoni'], '070111222')
        self.assertContains(forma, 'data-sp-emri="Florijan Jashari"')
        self.assertContains(forma, '#0589 — Jusuf Nuri Jashari · Florijan Jashari')
        r = self.client.post(reverse('shto_pagese_fondi'), {
            'blloku': '1100', 'nr_fatures': '000001', 'shtepia': self.sh.pk, 'lloji': 'DHURATE',
            'emri_donatorit': 'Florijan', 'mbiemri_donatorit': 'Jashari', 'nr_telefoni': '070333444',
            'data_pageses': '2026-10-26', 'arsyeja': 'Rryma', 'shuma_hyrese': '100', 'monedha': 'EUR', 'kursi': '61.5',
        })
        self.assertEqual(r.status_code, 302)
        detaje = self.client.get(reverse('detaje_shtepia', args=[self.sh.pk]))
        self.assertContains(detaje, 'Florijan Jashari')
        self.assertContains(detaje, 'Rryma')
        fondi = self.client.get(reverse('lista_pagesa_fondi') + '?viti=2026&kerkimi=nuri')
        self.assertEqual(len(fondi.context['pagesat']), 1)

    def test_totalet_sipas_monedhes(self):
        from .models import PagesaFondi, formato_shumen, totalet_sipas_monedhes
        for nr, (shuma, monedha) in enumerate([('1380', 'EUR'), ('75000', 'MKD'), ('200', 'CHF')], 1):
            self.client.post(reverse('shto_pagese_fondi'), {
                'blloku': '1', 'nr_fatures': str(nr), 'lloji': 'DHURATE', 'emri_donatorit': 'A',
                'mbiemri_donatorit': 'B', 'data_pageses': f'{timezone.now().year}-01-0{nr}',
                'shuma_hyrese': shuma, 'monedha': monedha, 'kursi': '',
            })
        tot = totalet_sipas_monedhes(PagesaFondi.objects.all())
        self.assertEqual((tot['EUR'], tot['MKD'], tot['CHF'], tot['USD']),
                         (Decimal('1380'), Decimal('75000'), Decimal('200'), Decimal('0')))
        r = self.client.get(reverse('dashboard_fondi'))
        self.assertContains(r, '75.000 den · 1.380 € · 200 CHF')
        self.assertEqual(formato_shumen(Decimal('69.92'), 'EUR'), '69,92 €')
