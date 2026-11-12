"""
Shuma me fjalë në shqip, për fletëpagesat ("со зборови"):
5960 den → "pesë mijë e nëntëqind e gjashtëdhjetë denarë"; 200 € → "dyqind euro"; 12,50 € → "dymbëdhjetë euro e 50 cent".
"""
from decimal import ROUND_HALF_UP, Decimal

NJESHET = ['', 'një', 'dy', 'tre', 'katër', 'pesë', 'gjashtë', 'shtatë', 'tetë', 'nëntë']
MBEDHJETE = ['dhjetë', 'njëmbëdhjetë', 'dymbëdhjetë', 'trembëdhjetë', 'katërmbëdhjetë', 'pesëmbëdhjetë',
             'gjashtëmbëdhjetë', 'shtatëmbëdhjetë', 'tetëmbëdhjetë', 'nëntëmbëdhjetë']
DHJETESHET = ['', '', 'njëzet', 'tridhjetë', 'dyzet', 'pesëdhjetë', 'gjashtëdhjetë', 'shtatëdhjetë',
              'tetëdhjetë', 'nëntëdhjetë']
QINDESHET = ['', 'njëqind', 'dyqind', 'treqind', 'katërqind', 'pesëqind', 'gjashtëqind', 'shtatëqind',
             'tetëqind', 'nëntëqind']
EMRAT = {'MKD': ('denar', 'denarë'), 'EUR': ('euro', 'euro'), 'CHF': ('frangë', 'franga'), 'USD': ('dollar', 'dollarë')}
CENTET = {'EUR': 'cent', 'CHF': 'centim', 'USD': 'cent', 'MKD': 'deni'}


def _deri_1000(n):
    pjeset = []
    if n >= 100:
        pjeset.append(QINDESHET[n // 100])
        n %= 100
    if 10 <= n < 20:
        pjeset.append(MBEDHJETE[n - 10])
    else:
        if n >= 20:
            pjeset.append(DHJETESHET[n // 10])
        if n % 10:
            pjeset.append(NJESHET[n % 10])
    return ' e '.join(pjeset)


def numri_me_fjale(n):
    """Numër i plotë (0 – 999.999.999) me fjalë."""
    n = int(n)
    if n == 0:
        return 'zero'
    pjeset = []
    milionet, n = divmod(n, 1_000_000)
    mijet, njeshet = divmod(n, 1000)
    if milionet:
        pjeset.append('një milion' if milionet == 1 else f'{_deri_1000(milionet)} milion')
    if mijet:
        pjeset.append(f'{_deri_1000(mijet)} mijë')
    if njeshet:
        pjeset.append(_deri_1000(njeshet))
    return ' e '.join(pjeset)


def shuma_me_fjale(vlera, monedha='MKD'):
    vlera = Decimal(vlera or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    te_plota = int(vlera)
    centet = int((vlera - te_plota) * 100)
    njejes, shumes = EMRAT.get(monedha, (monedha, monedha))
    teksti = f'{numri_me_fjale(te_plota)} {njejes if te_plota == 1 else shumes}'
    if centet:
        teksti += f' e {centet} {CENTET.get(monedha, "cent")}'
    return teksti
