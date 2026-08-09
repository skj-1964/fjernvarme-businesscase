"""F1b/F1c — modelaksen fra CLI, og rapportens rækkekontrakt.

F1b: `_apply_time_override` satte `cfg.time.end` til en bar datostreng, så
     `--year 2025` gav en akse der sluttede 2025-12-31 00:00 (8737 timer i
     stedet for 8760). Målt i Gate 0.5 §B2/B3.

F1c: `write_hourly_csv` dropper første time med vilje. Kontrakten pinnes her,
     så droppet ikke stilfærdigt kan blive til to eller nul.

Forventede længder er skrevet direkte, ikke genudledt.
Kræver ikke df-data — rører hverken loader eller netværk.
"""
from __future__ import annotations

import pandas as pd
import pytest

from run_case import _apply_time_override
from src.config import load_case
from src.data_loader import make_time_index

CASE = "cases/billund_2025.yaml"


def _cfg(resolution: str):
    cfg = load_case(CASE)
    cfg.time.resolution = resolution
    return cfg


# ---------------------------------------------------------------------------
# F1b — alle seks kombinationer fra Gate 0.5 §B2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "resolution,year,exp_start,exp_end,exp_len",
    [
        ("1h",    2025, "2025-01-01 00:00", "2025-12-31 23:00",  8760),
        ("15min", 2025, "2025-01-01 00:00", "2025-12-31 23:45", 35040),
        ("1h",    2026, "2026-01-01 00:00", "2026-12-31 23:00",  8760),
        ("15min", 2026, "2026-01-01 00:00", "2026-12-31 23:45", 35040),
    ],
    ids=["year2025_1h", "year2025_15min", "year2026_1h", "year2026_15min"],
)
def test_year_override_covers_whole_calendar_year(
    resolution, year, exp_start, exp_end, exp_len
):
    """--year YYYY skal give hele kalenderåret, opløsningsafhængigt.

    Før F1b: 8737 hhv. 34945 — de sidste 23 timer manglede.
    """
    cfg = _cfg(resolution)
    _apply_time_override(cfg, year, None, None)
    idx = make_time_index(cfg)

    assert idx.min() == pd.Timestamp(exp_start)
    assert idx.max() == pd.Timestamp(exp_end)
    assert len(idx) == exp_len


@pytest.mark.parametrize(
    "resolution,exp_end,exp_len",
    [
        ("1h",    "2025-12-31 23:00",  8760),
        ("15min", "2025-12-31 23:45", 35040),
    ],
    ids=["startend2025_1h", "startend2025_15min"],
)
def test_start_end_override_matches_year_override(resolution, exp_end, exp_len):
    """--start 2025-01-01 --end 2025-12-31 skal give samme som --year 2025."""
    cfg = _cfg(resolution)
    _apply_time_override(cfg, None, "2025-01-01", "2025-12-31")
    idx = make_time_index(cfg)

    assert idx.min() == pd.Timestamp("2025-01-01 00:00")
    assert idx.max() == pd.Timestamp(exp_end)
    assert len(idx) == exp_len

    # Identisk med --year-vejen.
    cfg_year = _cfg(resolution)
    _apply_time_override(cfg_year, 2025, None, None)
    assert make_time_index(cfg_year).equals(idx)


def test_explicit_time_on_end_is_respected():
    """--end 2025-06-15T12:00 må IKKE udvides til 23:00.

    Virkede også før F1b (målt i Trin 0h). Testen findes for at rettelsen
    ikke tager det med sig.
    """
    cfg = _cfg("1h")
    _apply_time_override(cfg, None, "2025-06-01", "2025-06-15T12:00")
    idx = make_time_index(cfg)

    assert idx.max() == pd.Timestamp("2025-06-15 12:00")
    assert len(idx) == 349


def test_explicit_midnight_is_respected_too():
    """--end 2025-06-15T00:00 betyder midnat, ikke hele døgnet.

    Skelnen er kolon'et i strengen. Uden den kunne brugeren ikke bede om en
    akse der slutter ved midnat.
    """
    cfg = _cfg("1h")
    _apply_time_override(cfg, None, "2025-06-01", "2025-06-15T00:00")
    assert make_time_index(cfg).max() == pd.Timestamp("2025-06-15 00:00")


def test_no_override_leaves_yaml_untouched():
    """Uden flag skal cfg.time være præcis som YAML'en satte den."""
    cfg = _cfg("1h")
    before_start, before_end = cfg.time.start, cfg.time.end
    _apply_time_override(cfg, None, None, None)

    assert (cfg.time.start, cfg.time.end) == (before_start, before_end)
    idx = make_time_index(cfg)
    assert len(idx) == 8760, "YAML-cases ramte aldrig F1b — det skal de blive ved med"


def test_resolution_is_read_from_cfg_not_assumed():
    """En ukendt opløsning skal rejse frem for at gætte en skridtlængde."""
    cfg = _cfg("1h")
    cfg.time.resolution = "30min"
    with pytest.raises(ValueError, match="resolution"):
        _apply_time_override(cfg, 2025, None, None)


def test_end_before_start_still_rejected():
    cfg = _cfg("1h")
    with pytest.raises(ValueError, match="efter"):
        _apply_time_override(cfg, None, "2025-06-15", "2025-06-01")


# ---------------------------------------------------------------------------
# F1c — rapportens rækkekontrakt
# ---------------------------------------------------------------------------

def test_hourly_csv_contract_is_n_minus_one(tmp_path):
    """hourly.csv dækker [idx[1], idx[-1]] — N−1 rækker, med vilje.

    Første time droppes fordi lagerbalancen først bindes fra t=1
    (`model.py:234`), så `charge/discharge[0]` er ubundet og timen leverer
    gratis varme. Testen pinner kontrakten: droppet må hverken blive til
    nul eller to rækker uden at nogen tager stilling.
    """
    import numpy as np
    import xarray as xr

    from src.reporting import write_hourly_csv

    idx = pd.date_range("2026-01-01 00:00", periods=48, freq="h")
    n = len(idx)
    units = ["fliskedel"]

    data = xr.Dataset(
        {
            "heat_demand": ("time", np.full(n, 10.0)),
            "spot_price": ("time", np.full(n, 500.0)),
        },
        coords={"time": idx},
    )
    result = xr.Dataset(
        {"heat_prod": (("unit", "time"), np.full((1, n), 10.0))},
        coords={"time": idx, "unit": units},
    )

    class _Unit:
        enabled = True
        production_profile_path = None

    class _Cfg:
        units = {"fliskedel": _Unit()}
        storage = {}

    out = write_hourly_csv(result, data, _Cfg(), tmp_path / "h.csv")
    df = pd.read_csv(out, parse_dates=["timestamp"])

    assert len(df) == n - 1, "kontrakten er N−1, ikke N"
    assert df["timestamp"].iloc[0] == idx[1], "første række skal være idx[1]"
    assert df["timestamp"].iloc[-1] == idx[-1], "sidste række skal være idx[-1]"
    assert idx[0] not in set(df["timestamp"]), "t=0 skal være droppet"
