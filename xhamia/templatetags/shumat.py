"""Shfaqja e shumave: 1.380 € · 75.000 den · 200 CHF — pa zero të tepërta, sipas monedhës së marrë."""
from decimal import Decimal

from django import template

from xhamia.models import formato_shumen, MONEDHAT_RENDI

register = template.Library()


@register.filter
def euro(vlera):
    """Decimal → '1.380 €' ose '69,92 €'."""
    return formato_shumen(Decimal(vlera or 0), 'EUR')


@register.filter
def monedhat(totali):
    """{'MKD': 75000, 'EUR': 1380, 'CHF': 200, 'USD': 0} → '75.000 den · 1.380 € · 200 CHF'."""
    pjeset = [formato_shumen(totali[m], m) for m in MONEDHAT_RENDI if totali and totali.get(m)]
    return ' · '.join(pjeset) or '0 €'


@register.filter
def shuma(vlera, monedha='EUR'):
    """Shuma në një monedhë të caktuar; bosh kur është 0/None (për kolonat e tabelave)."""
    if not vlera:
        return ''
    return formato_shumen(Decimal(vlera), monedha)
