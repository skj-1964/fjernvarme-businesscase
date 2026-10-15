"""Nettilslutning: grid.max_consumption_mw (15/10-2026).

Billund er prækvalificeret på VP + to elkedler (47,52 MW), men nettilslutningen
tillader højst 33 MW el i alt. Loftet er Σ heat_prod/COP over el-forbrugende
enheder pr. time. Testvinduet 9.–11. maj 2026 har lave elpriser, så modellen
uden loft bruger op til ca. 48 MW el — testen af loftet kan altså fejle.
"""
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import yaml

from src.config import load_case

CASE = "cases/billund_idag.yaml"
FAELLES = [
    sys.executable, "run_case.py", CASE, "--data-source", "github",
    "--heat-csv", "data/billund_abvaerk_hourly_splejset_jun2026.csv",
    "--start", "2026-05-09", "--end", "2026-05-11",
]


def _koer(tmp_path: Path, loft: float, *ekstra):
    r = subprocess.run(FAELLES + ["--set", f"grid.max_consumption_mw={loft}",
                                  "--out-dir", str(tmp_path), *ekstra],
                       capture_output=True, text=True, timeout=600)
    ud = r.stdout + r.stderr
    assert r.returncode == 0, ud[-2000:]
    obj = float(re.search(r"^Objektiv:\s+([\d,]+)", ud, re.M).group(1).replace(",", ""))
    hourly = sorted(tmp_path.glob("*_hourly.csv"))
    assert len(hourly) == 1
    d = pd.read_csv(hourly[0])
    cfg = load_case(CASE)
    cop = np.asarray(cfg.units["vp_luft_vand"].cop_curve.evaluate(
        xr.DataArray(d["t_out_c"].values)))
    el = d["p_elkedel_gl_mw"] + d["p_elkedel_ny_mw"] + d["p_vp_luft_vand_mw"] / cop
    return obj, float(el.max()), ud


@pytest.mark.usefixtures("df_data")
def test_uden_loft_bruger_vinduet_over_33_mw(tmp_path):
    # Dokumenterer, at testvinduet binder: uden loft > 33 MW.
    _, el_max, _ = _koer(tmp_path, 1000.0)
    assert el_max > 40.0


@pytest.mark.usefixtures("df_data")
def test_loftet_holder_og_koster(tmp_path):
    obj_fri, _, _ = _koer(tmp_path / "fri", 1000.0)
    obj, el_max, ud = _koer(tmp_path / "loft", 33.0)
    assert "Nettilslutning: samlet eloptag ≤ 33 MW" in ud
    assert el_max <= 33.0 + 0.01  # timefilen er afrundet
    assert obj > obj_fri


@pytest.mark.usefixtures("df_data")
def test_loftet_holder_med_balancering(tmp_path):
    _, el_max, ud = _koer(tmp_path, 33.0, "--with-balancing")
    assert "Robust reservation" in ud
    assert el_max <= 33.0 + 0.01  # timefilen er afrundet


def _skriv(tmp_path, grid):
    d = yaml.safe_load(open("cases/andeby.yaml", encoding="utf-8"))
    if grid is None:
        d.pop("grid", None)
    else:
        d["grid"] = grid
    sti = tmp_path / "case.yaml"
    sti.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return str(sti)


def test_uden_grid_blok_er_der_intet_loft(tmp_path):
    assert load_case(_skriv(tmp_path, None)).grid_max_consumption_mw is None


def test_grid_blok_laeses(tmp_path):
    assert load_case(_skriv(tmp_path, {"max_consumption_mw": 33})).grid_max_consumption_mw == 33.0


def test_ukendt_noegle_i_grid_afvises(tmp_path):
    with pytest.raises(ValueError, match="ukendte noegler i grid"):
        load_case(_skriv(tmp_path, {"max_consumption": 33}))


def test_loft_skal_vaere_positivt(tmp_path):
    with pytest.raises(ValueError, match="> 0"):
        load_case(_skriv(tmp_path, {"max_consumption_mw": 0}))
