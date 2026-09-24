"""Tests til balancing.activation (session 28).

Baggrund: session 27 viste, at 'clear' — hele den reserverede MW aktiveres i
hvert kvarter, hvor prisen clearer buddet — overvurderer aktiveret energi 4-5
gange, når reservationsgaten er slået fra. Blokken balancing.activation gør
aktiveret andel f(τ) konfigurerbar pr. marked. Uden blok er alt uændret, så
ankeret ikke flytter sig.

Testene er delt i tre: beregningen (ren pandas), konfigurationen (ingen data)
og loaderen (lokal df-data-klon, ingen solver).
"""
import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.activation_value import compute_activation_value
from src.config import Activation, ActivationMarket, load_case

BASE = Path("cases") / "billund_sporA.yaml"


def _serier():
    idx = pd.date_range("2026-03-02", periods=8, freq="15min", tz=None)
    spot = pd.Series(500.0, index=idx)
    # bud = 1000. To kvarterer under, seks over med stigende afstand.
    p = pd.Series([0, 900, 1000, 1250, 1500, 2000, 3000, 1100], index=idx, dtype=float)
    alpha = pd.Series([0.9, 0.9, 0.1, 0.2, 0.25, 0.5, 0.8, 0.0], index=idx)
    return p, spot, alpha


# --- Beregningen -------------------------------------------------------------

def test_clear_er_default_og_uaendret():
    """Uden model-argument er resultatet bit-identisk med model='clear'."""
    p, s, a = _serier()
    r0 = compute_activation_value(p, s, markup=500, el_cost_flat=100)
    r1 = compute_activation_value(p, s, markup=500, el_cost_flat=100,
                                  model="clear", system_share=a, k=7.0)
    pd.testing.assert_series_equal(r0.av, r1.av)
    pd.testing.assert_series_equal(r0.clear_fraction, r1.clear_fraction)
    # clear: seks af otte kvarterer clearer → 6 × 0,25 h, fordelt på to timer
    assert r0.clear_fraction.sum() == pytest.approx(6 * 0.25)


def test_system_share_skalerer_med_alpha():
    p, s, a = _serier()
    r = compute_activation_value(p, s, markup=500, el_cost_flat=0,
                                 model="system_share", system_share=a, k=1.0)
    clears = (p >= 1000).astype(float)
    forventet = 0.25 * (clears * a)
    assert r.clear_fraction.sum() == pytest.approx(forventet.sum())
    assert r.av_payment.sum() == pytest.approx((forventet * p).sum())


def test_system_share_k_loftes_ved_en():
    """k·α over 1 må ikke give mere end fuld aktivering."""
    p, s, a = _serier()
    r = compute_activation_value(p, s, markup=500, el_cost_flat=0,
                                 model="system_share", system_share=a, k=4.0)
    clears = (p >= 1000).astype(float)
    forventet = 0.25 * clears * (4.0 * a).clip(0, 1)
    assert r.clear_fraction.sum() == pytest.approx(forventet.sum())
    assert r.clear_fraction.sum() < 6 * 0.25       # ellers er testen tom


def test_system_share_kraever_serie():
    p, s, _ = _serier()
    with pytest.raises(ValueError, match="system_share"):
        compute_activation_value(p, s, markup=500, el_cost_flat=0,
                                 model="system_share")


def test_ramp():
    p, s, _ = _serier()
    r = compute_activation_value(p, s, markup=500, el_cost_flat=0,
                                 model="ramp", ramp_dkk_mwh=1000.0)
    forventet = 0.25 * ((p - 1000) / 1000).clip(0, 1)
    assert r.clear_fraction.sum() == pytest.approx(forventet.sum())
    # Lige præcis på buddet: clear giver 1, rampen giver 0
    assert forventet.iloc[2] == 0.0


def test_ukendt_model_fejler():
    p, s, _ = _serier()
    with pytest.raises(ValueError, match="ukendt"):
        compute_activation_value(p, s, markup=500, el_cost_flat=0, model="alt")


# --- Konfigurationen ---------------------------------------------------------

def _case_med(balancing_tillaeg: str, method: str | None = None) -> str:
    tekst = BASE.read_text()
    tekst = tekst.replace("balancing:\n", "balancing:\n" + balancing_tillaeg, 1)
    if method is not None:
        tekst = re.sub(r"^  method: .*$", f"  method: {method}", tekst,
                       count=1, flags=re.M)
    p = Path(tempfile.mkdtemp()) / "case.yaml"
    p.write_text(tekst)
    return str(p)


def test_uden_blok_er_clear():
    cfg = load_case(str(BASE))
    assert cfg.activation == Activation()
    assert cfg.activation.afrr.model == "clear"
    assert cfg.activation.mfrr.model == "clear"


def test_blok_parses():
    cfg = load_case(_case_med(
        "  activation:\n"
        "    afrr: {model: system_share, k: 2.5}\n"
        "    mfrr: {model: ramp, ramp_dkk_mwh: 800}\n"))
    assert cfg.activation.afrr == ActivationMarket("system_share", 2.5, None)
    assert cfg.activation.mfrr.ramp_dkk_mwh == 800.0
    assert cfg.activation.mfrr.model == "ramp"


@pytest.mark.parametrize("blok, fejl", [
    ("  activation:\n    afrr: {model: pro_rata}\n", "model"),
    ("  activation:\n    afrr: {model: ramp}\n", "ramp_dkk_mwh"),
    ("  activation:\n    afrr: {model: system_share, k: 0}\n", "k"),
    ("  activation:\n    afrr: {model: clear, faktor: 2}\n", "ukendte"),
    ("  activation:\n    fcr: {model: clear}\n", "ukendte"),
])
def test_ugyldig_blok_fejler(blok, fejl):
    with pytest.raises(ValueError, match=fejl):
        load_case(_case_med(blok))


def test_kraever_activation_value_metoden():
    """Legacy-metoden bruger ikke av(t); en ikke-clear model ville være tavs."""
    with pytest.raises(ValueError, match="activation_value"):
        load_case(_case_med(
            "  activation:\n    afrr: {model: system_share}\n",
            method="legacy"))


# --- Loaderen (df-data, ingen solver) ----------------------------------------

def _balance(df_data, activation):
    from src.data_loader import make_time_index
    from src.data_loader_github import (
        fetch_balance_prices_github, fetch_spot_prices_github)
    cfg = load_case(str(BASE))
    cfg.time.start = "2026-03-02T00:00:00Z"
    cfg.time.end = "2026-03-08T23:00:00Z"
    idx = make_time_index(cfg)
    spot = fetch_spot_prices_github("DK1", idx, repo_root=df_data)
    return fetch_balance_prices_github(
        idx, zone="DK1", repo_root=df_data, target_index=idx,
        av_params={"spot_15min": spot, "markup_up": 500.0,
                   "el_cost_flat": 132.0, "activation": activation})


def test_loader_clear_uaendret_med_og_uden_cfg(df_data):
    """activation=None og en tom Activation() giver samme serier."""
    a = _balance(df_data, None)
    b = _balance(df_data, Activation())
    for v in ("afrr_activation_value_up", "mfrr_clear_fraction_up"):
        np.testing.assert_array_equal(a[v].values, b[v].values)


def test_loader_system_share_saenker_aktiveringen(df_data):
    """Grøn skal kunne blive rød: modellen skal nå frem til beregningen."""
    a = _balance(df_data, Activation())
    b = _balance(df_data, Activation(
        afrr=ActivationMarket("system_share", 1.0),
        mfrr=ActivationMarket("system_share", 1.0)))
    for mk in ("afrr", "mfrr"):
        ca = float(a[f"{mk}_clear_fraction_up"].sum())
        cb = float(b[f"{mk}_clear_fraction_up"].sum())
        assert ca > 0, f"{mk}: ingen clear i testugen — testen måler ingenting"
        assert cb < 0.8 * ca, f"{mk}: system_share ændrede ikke aktiveringen"
        # Kapacitetspris og α uberørt
    np.testing.assert_array_equal(a["afrr_cap_up_dkk"].values,
                                  b["afrr_cap_up_dkk"].values)
