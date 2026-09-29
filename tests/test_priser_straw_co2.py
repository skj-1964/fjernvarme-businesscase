"""Give Fjernvarme (29/9 2026): et ark uden halmpris og med CO2 = 0 blev konverteret
uden fejl, men run_case stoppede med `KeyError: 'straw'`.

Konverteringen skrev kun de priser, der stod i arket, og lasteren krævede både
`straw` og `co2_eua`. Nu:
  * halmpris er valgfri; bruger en enhed halm uden pris, siger fuel_price det klart
  * CO2 blank med gasenhed i arket stopper konverteringen (blank er ikke 0)
  * CO2 blank uden gasenhed skrives som 0, så casen kan indlæses
"""
from __future__ import annotations

import pytest
import yaml

from src.config import load_case
from tests.test_cop_tabel import _byg_og_fyld, _konverter


def _flis_og_co2_nul(wb):
    wb["Priser"]["B7"] = None            # ingen halm
    wb["Priser"]["B10"] = 0              # gaspris inkl. CO2-afgift


def test_ark_uden_halm_kan_koeres_af_load_case(tmp_path):
    r, case = _konverter(tmp_path, _byg_og_fyld(tmp_path, _flis_og_co2_nul))
    assert r.returncode == 0, r.stdout + r.stderr
    cfg = load_case(str(case))
    assert cfg.prices.fuel_price("flis") == pytest.approx(232)
    assert cfg.prices.co2_eua == 0


def test_halm_uden_pris_giver_klar_fejl_ikke_stille_nul(tmp_path):
    r, case = _konverter(tmp_path, _byg_og_fyld(tmp_path, _flis_og_co2_nul))
    cfg = load_case(str(case))
    with pytest.raises(ValueError, match="halm"):
        cfg.prices.fuel_price("straw")


def test_co2_blank_med_gasenhed_stopper(tmp_path):
    def blank(wb):
        _flis_og_co2_nul(wb)
        wb["Priser"]["B10"] = None
    r, case = _konverter(tmp_path, _byg_og_fyld(tmp_path, blank))
    assert r.returncode != 0
    assert case is None
    assert "CO2" in r.stdout + r.stderr and "0" in r.stdout + r.stderr
    assert "Traceback" not in r.stderr


def test_co2_blank_uden_gasenhed_skrives_som_nul(tmp_path):
    def uden_gas(wb):
        _flis_og_co2_nul(wb)
        wb["Priser"]["B10"] = None
        for r in (8, 9):                 # gaskedel og gasmotor
            for c in "ABCDEFGHIJKLM":
                wb["Anlaeg"][f"{c}{r}"] = None
        wb["Priser"]["B6"] = None
    r, case = _konverter(tmp_path, _byg_og_fyld(tmp_path, uden_gas))
    assert r.returncode == 0, r.stdout + r.stderr
    assert yaml.safe_load(case.read_text())["prices"]["co2_eua"]["value"] == 0
    load_case(str(case))
