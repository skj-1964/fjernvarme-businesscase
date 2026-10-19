"""Spotprisen er ikke en besparelse ved opregulering (19/10-2026).

Billund bekræftede: når elkedlen eller varmepumpen stoppes ved opregulering,
betaler værket stadig den strøm, det købte dagen før, og får opreguleringsprisen.
Tarif og elafgift spares. Værdien af en aktiveret MWh er derfor
aktiveringsprisen plus tarif og afgift, ikke plus spotprisen.

Før rettelsen regnede modellen p_act + spot + tarif. Testen er set fejle på den
kode.
"""
import pandas as pd
import pytest

from src.activation_value import compute_activation_value


def test_vaerdien_pr_mwh_indeholder_ikke_spotprisen():
    idx = pd.date_range("2026-01-05", periods=4, freq="15min")
    p = pd.Series([0.0, 2500.0, 1600.0, 900.0], index=idx)   # opreguleringspris
    spot = pd.Series(800.0, index=idx)                        # købt dagen før
    r = compute_activation_value(p, spot, markup=500, el_cost_flat=150)
    # Buddet (800 + 500 = 1300) clearer i kvarter 2 og 3: 0,25 h hver.
    assert float(r.av_payment.sum()) == pytest.approx(0.25 * (2500 + 1600))
    assert float(r.av.sum()) == pytest.approx(0.25 * (2500 + 150) + 0.25 * (1600 + 150))
    # Forskellen mellem brutto og betaling er kun den sparede tarif og afgift.
    assert float((r.av - r.av_payment).sum()) == pytest.approx(0.5 * 150)


def test_spotprisen_flytter_ikke_vaerdien_naar_buddet_clearer():
    idx = pd.date_range("2026-01-05", periods=1, freq="15min")
    p = pd.Series([3000.0], index=idx)
    lav = compute_activation_value(p, pd.Series(200.0, index=idx), markup=500, el_cost_flat=150)
    hoej = compute_activation_value(p, pd.Series(900.0, index=idx), markup=500, el_cost_flat=150)
    assert float(lav.av.sum()) == pytest.approx(float(hoej.av.sum()))
