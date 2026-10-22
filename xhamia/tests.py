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


@override_settings(SMS_GATEWAY_USER='u', SMS_GATEWAY_PASSWORD='p')
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
        self.assertEqual(r.context['borxhlinjte'][0]['borxhi'], Decimal('180'))
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


class KonfigurimiSistemitTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x')
        ProfilStafi.objects.create(user=self.admin, rol='ADMIN')
        self.client.force_login(self.admin)

    def test_ruaj_dhe_mbaj_fjalekalimin(self):
        url = reverse('konfigurimi_sistemit')
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {'veprimi': 'ruaj', 'sms_username': 'ABC', 'sms_password': 'sekret',
                               'sms_sim_numri': '1', 'gmail_app_password': 'abcd efgh ijkl mnop'})
        self.assertEqual(KonfigurimiSistemit.merr().sms_sim_numri, 1)
        k = KonfigurimiSistemit.merr()
        self.assertEqual((k.sms_username, k.sms_password, k.gmail_app_password),
                         ('ABC', 'sekret', 'abcdefghijklmnop'))
        # Fjalëkalimet bosh = mbeten të vjetrat
        self.client.post(url, {'veprimi': 'ruaj', 'sms_username': 'ABC2', 'sms_password': '', 'gmail_app_password': ''})
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
