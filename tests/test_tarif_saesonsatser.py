"""Sæsonsatser i konverteringen: ét sæt tidsperioder, to sæt satser.

Arket spørger om vinter- og sommersats for hvert tarifbånd. Indtil
september 2026 gemte konverteringen kun én sats pr. båndnavn og brugte
vintertallet hele året — så et netselskab med lavere sommersatser fik en
for høj sommerelpris på varmepumpe og elkedel, uden at noget så forkert ud.

Testene konverterer et udfyldt ark og slår satsen op time for time gennem
modellens eget tarifmodul, så både konvertering og opslag er dækket.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import yaml

from src.config import load_case
from src.tariff import resolve_consumption_tariff
from tests.test_cop_tabel import _byg_og_fyld, _konverter

# UTC-tidspunkter; tarifopslaget sker i dansk tid.
TIMER = {
    "vinter_hverdag_10": "2026-01-14 09:00",   # spidslast
    "vinter_hverdag_03": "2026-01-14 02:00",   # lavlast
    "vinter_hverdag_22": "2026-01-14 21:00",   # højlast
    "sommer_hverdag_10": "2026-07-15 08:00",   # højlast (sommer)
    "sommer_hverdag_03": "2026-07-15 01:00",   # lavlast (sommer)
    "sommer_loerdag_12": "2026-07-18 10:00",   # lavlast hele weekenden
}


def _satser(case) -> dict[str, float]:
    cfg = load_case(str(case))
    idx = pd.DatetimeIndex(pd.to_datetime(list(TIMER.values())))
    ds = xr.Dataset({"spot_price": ("time", np.zeros(len(idx)))},
                    coords={"time": idx})
    v = resolve_consumption_tariff(cfg, ds).values
    return dict(zip(TIMER, v))


def _konverter_med(tmp_path, satser: dict[str, float | None]):
    def rediger(wb):
        for celle, v in satser.items():
            wb["Priser"][celle] = v
    r, case = _konverter(tmp_path, _byg_og_fyld(tmp_path, rediger))
    assert r.returncode == 0, r.stderr
    return r, case


def test_sommersatser_bruges(tmp_path):
    # vinter: lav 7,4  høj 14,8  spids 29,5  |  sommer: lav 5,0  høj 8,0
    r, case = _konverter_med(tmp_path, {"C22": 5.0, "C23": 8.0})
    s = _satser(case)
    fast = s["vinter_hverdag_03"] - 7.4          # Energinet + D&V + elafgift
    assert s["vinter_hverdag_10"] - fast == pytest.approx(29.5)
    assert s["vinter_hverdag_22"] - fast == pytest.approx(14.8)
    assert s["sommer_hverdag_10"] - fast == pytest.approx(8.0)
    assert s["sommer_hverdag_03"] - fast == pytest.approx(5.0)
    assert s["sommer_loerdag_12"] - fast == pytest.approx(5.0)
    assert "egne sommersatser" in r.stdout


def test_ens_satser_giver_ingen_ekstra_baand(tmp_path):
    """Skabelonens eksempel (N1) har ens satser: casefilen skal se ud som før."""
    _, case = _konverter_med(tmp_path, {})
    baand = yaml.safe_load(case.read_text())["electricity"]["tariff_consumption"][
        "net_tariff"]["bands"]
    assert set(baand) == {"lav", "hoej", "spids"}


def test_kun_sommersats_gaelder_hele_aaret(tmp_path):
    r, case = _konverter_med(tmp_path, {"B23": None, "C23": 12.0})
    s = _satser(case)
    fast = s["vinter_hverdag_03"] - 7.4
    assert s["vinter_hverdag_22"] - fast == pytest.approx(12.0)
    assert s["sommer_hverdag_10"] - fast == pytest.approx(12.0)
    assert "kun sommersats" in r.stdout


def test_sommerspidslast_bruges_ikke_og_siges(tmp_path):
    r, case = _konverter_med(tmp_path, {"C24": 20.0})
    s = _satser(case)
    fast = s["vinter_hverdag_03"] - 7.4
    assert s["sommer_hverdag_10"] - fast == pytest.approx(14.8)
    assert "Sommersatsen bruges ikke" in r.stdout
