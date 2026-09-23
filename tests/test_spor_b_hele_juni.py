"""Spor B: vindue, varmelast og juni-loft skal hænge sammen (session 29).

Session 28 kørte til 23/6, men sammenlignede med facit og et juni-loft for
hele måneden. Det gav 110 % i stedet for 117 %, uden at noget fejlede.
Disse tests binder de tre ting sammen, så det ikke kan ske tavst igen.
"""
from pathlib import Path

import pandas as pd
import pytest

from src.config import load_case

SPOR_B = Path("cases") / "billund_sporB.yaml"
MAALT = Path("data") / "billund_abvaerk_hourly.csv"
SPLEJSET = Path("data") / "billund_abvaerk_hourly_splejset_jun2026.csv"

# Billunds reserverede MWh, forbrug op, fra månedsafregningen juni 2026
# (kvarterdata, hele måneden). Loftet i casen er MWh / timer i vinduet.
FACIT_MWH_JUNI = {"afrr": 57.52, "mfrr": 40.52}


def _vindue():
    cfg = load_case(str(SPOR_B))
    start = pd.Timestamp(cfg.time.start).tz_localize(None)
    slut = pd.Timestamp(cfg.time.end).tz_localize(None)
    return cfg, pd.date_range(start, slut, freq="h")


@pytest.fixture(scope="module")
def splejset():
    return pd.read_csv(SPLEJSET, parse_dates=["timestamp"])


def test_splejset_daekker_hele_vinduet(splejset):
    """Ingen time i Spor B-vinduet må mangle — ellers interpolerer loaderen."""
    _, tider = _vindue()
    mangler = tider.difference(pd.DatetimeIndex(splejset.timestamp))
    assert len(mangler) == 0, f"{len(mangler)} timer mangler, første {mangler[:3]}"


def test_maalt_del_er_uaendret(splejset):
    """Den målte del skal være identisk med den rene målte fil."""
    maalt = pd.read_csv(MAALT, parse_dates=["timestamp"])
    del_ = splejset[splejset.kilde == "maalt"].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        del_[["timestamp", "heat_mw_abvaerk"]], maalt, check_dtype=False)


def test_syntese_kun_efter_sidste_maaling(splejset):
    assert set(splejset.kilde) == {"maalt", "dmi_syntese"}
    sidste_maalt = splejset.loc[splejset.kilde == "maalt", "timestamp"].max()
    foerste_syn = splejset.loc[splejset.kilde == "dmi_syntese", "timestamp"].min()
    assert foerste_syn == sidste_maalt + pd.Timedelta(hours=1)
    assert splejset.timestamp.is_monotonic_increasing
    assert not splejset.timestamp.duplicated().any()


def test_maalt_fil_daekker_ikke_vinduet():
    """Den rene fil skal fortsat få kørslen til at stoppe (> 5 % mangler)."""
    _, tider = _vindue()
    maalt = pd.read_csv(MAALT, parse_dates=["timestamp"])
    andel = len(tider.difference(pd.DatetimeIndex(maalt.timestamp))) / len(tider)
    assert andel > 0.05


@pytest.mark.parametrize("marked", ["afrr", "mfrr"])
def test_juni_loft_svarer_til_vinduets_timer(marked):
    """loft × timer i juni i vinduet = Billunds juni-MWh (±0,05 MWh)."""
    cfg, tider = _vindue()
    timer_juni = int((tider.strftime("%Y-%m") == "2026-06").sum())
    # Facit er hele juni, så vinduet skal også være det (fejlen i session 28).
    assert timer_juni == 30 * 24, f"vinduet dækker {timer_juni} timer af juni"
    loft = getattr(cfg.availability, marked).mw_by_month["2026-06"]
    assert loft * timer_juni == pytest.approx(FACIT_MWH_JUNI[marked], abs=0.05)
