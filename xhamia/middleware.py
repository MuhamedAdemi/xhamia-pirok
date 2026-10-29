"""
Llogaritë e shtëpive (p.sh. "sh0254") shohin VETËM portalin e shtëpisë së vet.

Kontrolli bëhet këtu, për çdo kërkesë, e jo te secila faqe: kështu asnjë faqe e stafit (as ato që shtohen
më vonë) nuk hapet për familjet, pavarësisht si hyjnë — sesion i ruajtur, lidhje e kopjuar, butoni "prapa".
"""
from django.shortcuts import redirect

# Faturat lejohen, por pamja kontrollon që fatura t'i përkasë shtëpisë së përdoruesit.
FAQET_E_PORTALIT = {
    'portali_shtepi', 'ndrysho_fjalekalim_shtepi', 'logout',
    'fatura_antaresia_pdf', 'fatura_varrezat_pdf', 'fatura_fondi_pdf',
}


def eshte_llogari_shtepie(user):
    return user.is_authenticated and hasattr(user, 'profili_shtepi')


class PortaliShtepiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not eshte_llogari_shtepie(request.user):
            return None
        match = request.resolver_match
        if match and match.view_name in FAQET_E_PORTALIT:
            return None
        return redirect('portali_shtepi')
