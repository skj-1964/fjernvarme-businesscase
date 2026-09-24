"""Tests til balancing.availability og balancing.activation.foresight (session 28).

availability er et månedligt loft på den samlede reservation pr. marked
(hourly: hver time, energy: månedens MWh). foresight: profile lader
optimeringen se aktiveringsværdiens gennemsnit pr. måned × time på døgnet.

Begge er beskrivende kalibreringer af Billund marts–juni 2026 (Spor B).
En måned uden loft skal stoppe kørslen — et loft må ikke tavst falde bort,
når casen køres på et andet vindue.
"""
import tempfile
from pathlib import Path

import linopy as lp
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.balancing import _add_availability_caps
from src.config import Activation, Availability, AvailabilityMarket, load_case

BASE = Path("cases") / "billund_sporA.yaml"
SPOR_B = Path("cases") / "billund_sporB.yaml"


def _case_med(balancing_tillaeg: str) -> str:
    tekst = BASE.read_text().replace("balancing:\n", "balancing:\n" + balancing_tillaeg, 1)
    p = Path(tempfile.mkdtemp()) / "case.yaml"
    p.write_text(tekst)
    return str(p)


# --- Konfiguration -----------------------------------------------------------

def test_spor_a_uden_loft_og_realiseret_foresight():
    """Ankeret: Spor A må ikke have fået loft eller profil."""
    cfg = load_case(str(BASE))
    assert cfg.availability is None
    assert cfg.activation.foresight == "realized"


def test_spor_b_kalibrering_parses():
    cfg = load_case(str(SPOR_B))
    assert cfg.availability.enabled and cfg.availability.mode == "energy"
    assert set(cfg.availability.afrr.mw_by_month) == {
        "2026-03", "2026-04", "2026-05", "2026-06"}
    assert cfg.activation.foresight == "profile"
    assert cfg.activation.afrr.model == "system_share"
    assert cfg.activation.mfrr.model == "clear"
    assert not cfg.reservation_gate.enabled


@pytest.mark.parametrize("blok, fejl", [
    ("  availability:\n    enabled: true\n    mode: weekly\n", "mode"),
    ("  availability:\n    enabled: true\n    afrr: {mw_by_month: {'2026-3': 1.0}}\n",
     "ÅÅÅÅ-MM"),
    ("  availability:\n    enabled: true\n    afrr: {mw_by_month: {'2026-03': -1}}\n",
     "≥ 0"),
    ("  availability:\n    enabled: true\n    afrr: {mw: 1.0}\n", "ukendte"),
    ("  availability:\n    enabled: true\n    fcr: {mw_by_month: {}}\n", "ukendte"),
    ("  activation:\n    foresight: perfect\n", "foresight"),
])
def test_ugyldig_blok_fejler(blok, fejl):
    with pytest.raises(ValueError, match=fejl):
        load_case(_case_med(blok))


# --- Constraintet ------------------------------------------------------------

def _model():
    tid = pd.date_range("2026-03-31 20:00", periods=8, freq="h").values
    m = lp.Model()
    r1 = m.add_variables(lower=0, upper=10, coords=[("time", tid)], name="r_a1")
    r2 = m.add_variables(lower=0, upper=10, coords=[("time", tid)], name="r_a2")
    return m, tid, {"aFRR": {"u1": r1, "u2": r2}, "mFRR": {}}


def _avail(mode, maaneder):
    return Availability(enabled=True, mode=mode,
                        afrr=AvailabilityMarket(mw_by_month=maaneder))


def test_hourly_loft_pr_time():
    m, tid, mv = _model()
    _add_availability_caps(m, _avail("hourly", {"2026-03": 1.5, "2026-04": 0.5}),
                           mv, tid)
    c = m.constraints["availability_afrr"]
    rhs = np.asarray(c.rhs).ravel()
    assert len(rhs) == 8
    np.testing.assert_allclose(rhs, [1.5] * 4 + [0.5] * 4)


def test_energy_loft_pr_maaned():
    m, tid, mv = _model()
    _add_availability_caps(m, _avail("energy", {"2026-03": 1.5, "2026-04": 0.5}),
                           mv, tid)
    c = m.constraints["availability_afrr"]
    rhs = sorted(np.asarray(c.rhs).ravel().tolist())
    # to måneder × fire timer: 4·0,5 = 2 og 4·1,5 = 6
    assert rhs == pytest.approx([2.0, 6.0])


def test_manglende_maaned_fejler():
    m, tid, mv = _model()
    with pytest.raises(ValueError, match="2026-04"):
        _add_availability_caps(m, _avail("hourly", {"2026-03": 1.0}), mv, tid)


def test_marked_uden_loft_eller_variable_springes_over():
    m, tid, mv = _model()
    avail = Availability(enabled=True, mode="hourly",
                         mfrr=AvailabilityMarket(mw_by_month={"2026-03": 1.0}))
    _add_availability_caps(m, avail, mv, tid)       # mFRR har ingen variable
    assert "availability_afrr" not in m.constraints
    assert "availability_mfrr" not in m.constraints


# --- Foresight i loaderen (df-data, ingen solver) ----------------------------

def _balance(df_data, activation):
    from src.data_loader import make_time_index
    from src.data_loader_github import (
        fetch_balance_prices_github, fetch_spot_prices_github)
    cfg = load_case(str(BASE))
    cfg.time.start = "2026-03-02T00:00:00Z"
    cfg.time.end = "2026-03-15T23:00:00Z"
    idx = make_time_index(cfg)
    spot = fetch_spot_prices_github("DK1", idx, repo_root=df_data)
    return fetch_balance_prices_github(
        idx, zone="DK1", repo_root=df_data, target_index=idx,
        av_params={"spot_15min": spot, "markup_up": 500.0,
                   "el_cost_flat": 132.0, "activation": activation})


def test_profile_bevarer_sum_og_fjerner_variation(df_data):
    real = _balance(df_data, Activation())
    prof = _balance(df_data, Activation(foresight="profile"))
    for v in ("afrr_activation_value_up", "mfrr_clear_fraction_up"):
        a, b = real[v].values, prof[v].values
        assert b.sum() == pytest.approx(a.sum(), rel=1e-9)
        assert b.std() < a.std(), f"{v}: profilen udjævnede ikke"
        # samme værdi for samme time på døgnet inden for måneden
        tider = pd.DatetimeIndex(prof.time.values)
        s = pd.Series(b, index=tider)
        assert s.groupby(tider.hour).nunique().max() == 1
    # kapacitetsprisen er urørt
    np.testing.assert_array_equal(real["afrr_cap_up_dkk"].values,
                                  prof["afrr_cap_up_dkk"].values)
