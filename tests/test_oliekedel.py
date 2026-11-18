"""Oliekedel som ny enhedstype (ønske november 2026).

Før kendte modellen kun naturgas som fossilt brændsel. En oliekedel kunne ikke
skrives i værksarket, og en case med `fuel: fuel_oil` stoppede med
`KeyError: Ukendt brændsel`. Nu:
  * prices.fuel_oil er en brændselspris på linje med naturgas
  * typen oil_boiler i værksarket giver fuel_oil og 0,266 t CO2 pr. MWh olie
  * mangler oliepris eller CO2-pris med en oliekedel i arket, stopper
    konverteringen med en besked på dansk
  * oliekedlen lastfordeles efter sin marginalomkostning som enhver kedel:
    billig olie bruges fuldt ud, olie til en realistisk pris står stille, så
    længe gaskedlen har ledig kapacitet (testen er set kunne blive rød begge veje)
"""
from __future__ import annotations

import copy
import subprocess
import sys

import pytest
import xarray as xr
import yaml

from src.config import Prices, load_case
from src.model import compute_marginal_cost
from tests.test_cop_tabel import _byg_og_fyld, _konverter


# --------------------------------------------------------------- værksarket
def _oliekedel(wb, pris=1050.0, etiket="fyringsolie"):
    """En oliekedel i første tomme række i Anlaeg og en oliepris på Priser."""
    ws = wb["Anlaeg"]
    for kol, v in zip("ABCDEFGHIJKLM",
                      ["oliekedel", "oil_boiler", 8.0, 0.0, 0.92, None, None,
                       20.0, 300, 1, 1, "nej", None]):
        ws[f"{kol}12"] = v
    p = wb["Priser"]
    assert p["A10"].value == "fyringsolie"       # skabelonens række
    p["A10"], p["B10"] = etiket, pris


def test_oliekedel_i_arket_giver_fuel_oil_og_co2(tmp_path):
    r, case = _konverter(tmp_path, _byg_og_fyld(tmp_path, _oliekedel))
    assert r.returncode == 0, r.stdout + r.stderr
    raa = yaml.safe_load(case.read_text(encoding="utf-8"))
    u = raa["units"]["oliekedel"]
    assert u["fuel"] == "fuel_oil"
    assert u["co2_emissions_per_mwh_fuel"] == pytest.approx(0.266)
    assert raa["prices"]["fuel_oil"]["value"] == pytest.approx(1050)
    cfg = load_case(str(case))
    assert cfg.prices.fuel_price("fuel_oil") == pytest.approx(1050)


def test_gasolie_som_etiket_er_ogsaa_olie(tmp_path):
    r, case = _konverter(tmp_path, _byg_og_fyld(
        tmp_path, lambda wb: _oliekedel(wb, etiket="gasolie")))
    assert r.returncode == 0, r.stdout + r.stderr
    assert load_case(str(case)).prices.fuel_price("fuel_oil") == pytest.approx(1050)


def test_oliekedel_uden_oliepris_stopper_med_besked(tmp_path):
    r, case = _konverter(tmp_path, _byg_og_fyld(
        tmp_path, lambda wb: _oliekedel(wb, pris=None)))
    assert r.returncode != 0 and case is None
    ud = r.stdout + r.stderr
    assert "oliekedel" in ud and "fyringsolie" in ud
    assert "Traceback" not in r.stderr


def test_oliekedel_uden_co2_pris_stopper(tmp_path):
    def uden_co2(wb):
        _oliekedel(wb)
        wb["Priser"]["B11"] = None
        for r in (8, 9):                 # gaskedel og gasmotor ud, så kun olien kræver CO2
            for c in "ABCDEFGHIJKLM":
                wb["Anlaeg"][f"{c}{r}"] = None
    r, case = _konverter(tmp_path, _byg_og_fyld(tmp_path, uden_co2))
    assert r.returncode != 0 and case is None
    assert "olie" in r.stdout + r.stderr and "CO2" in r.stdout + r.stderr


def test_skabelonen_uden_oliekedel_er_uaendret(tmp_path):
    """Den tomme oliepris i skabelonen må ikke give en pris i casen."""
    r, case = _konverter(tmp_path, _byg_og_fyld(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "fuel_oil" not in yaml.safe_load(case.read_text(encoding="utf-8"))["prices"]


# --------------------------------------------------------------- modellen
def test_oliepris_mangler_giver_klar_fejl():
    with pytest.raises(ValueError, match="fyringsolie"):
        Prices(co2_eua=0.0).fuel_price("fuel_oil")


def _andeby_med_olie(tmp_path, oliepris):
    c = yaml.safe_load(open("cases/andeby.yaml", encoding="utf-8"))
    u = copy.deepcopy(c["units"]["gaskedel_agg"])
    u.update(type="oil_boiler", fuel="fuel_oil", p_max_heat=10.0,
             eta_fuel_to_heat=0.92, var_om=20.0, co2_emissions_per_mwh_fuel=0.266)
    c["units"]["oliekedel"] = u
    c["prices"]["fuel_oil"] = {"value": oliepris, "unit": "DKK/MWh_fuel"}
    sti = tmp_path / "andeby_olie.yaml"
    sti.write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    return sti


def test_marginalomkostning_for_olie(tmp_path):
    cfg = load_case(str(_andeby_med_olie(tmp_path, 1050.0)))
    u = cfg.units["oliekedel"]
    spot = xr.DataArray([500.0, 900.0], dims="time")
    mc = compute_marginal_cost(u, cfg, xr.Dataset({"spot_price": spot}))
    forventet = (1050.0 + 0.266 * cfg.prices.co2_eua) / 0.92 + 20.0
    assert float(mc[0]) == pytest.approx(forventet)
    assert float(mc[1]) == pytest.approx(forventet)     # uafhængig af spot


@pytest.mark.parametrize("oliepris, i_brug", [(1.0, True), (1050.0, False)])
def test_oliekedlen_lastfordeles_efter_pris(tmp_path, oliepris, i_brug):
    case = _andeby_med_olie(tmp_path, oliepris)
    r = subprocess.run(
        [sys.executable, "run_case.py", str(case), "--data-source", "github",
         "--start", "2026-01-05", "--end", "2026-01-06", "--out-dir", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    ds = xr.open_dataset(next(tmp_path.glob("*_dispatch.nc")))
    olie = float(ds["heat_prod"].sel(unit="oliekedel").sum())
    if i_brug:
        assert olie == pytest.approx(10.0 * 48, rel=1e-3)   # fuld last hele perioden
    else:
        assert olie == pytest.approx(0.0, abs=1e-3)
