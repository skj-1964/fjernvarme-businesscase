"""HiGHS' aggregator-presolve gav en forkert MILP-løsning (15/10-2026).

Med robust reservation og uden tank returnerede HiGHS (1.14 og 1.15) med
presolve-reglen 'aggregator' en løsning, der var 12 % for dyr, rapporteret som
optimal. Med presolve slået helt fra, eller kun aggregator (bit 12, 4096), er
optimum 1.647.142 kr. (1.311.520 før rettelserne 19/10-2026: lagerbalancen i første
time og aktiveringsværdien uden spotpris). solve.py slår derfor aggregator fra, når modellen har
planen uden aktivering, medmindre casen selv sætter solver.presolve_rule_off.

Testen kører vinduet, hvor fejlen blev fundet. Den er set fejle med
presolve_rule_off = 0 (gav 1.465.539 før og 1.801.161 efter rettelserne 19/10).
"""
import re
import subprocess
import sys

import pytest

from src.config import Solver

KMD = [
    sys.executable, "run_case.py", "cases/billund_idag.yaml", "--data-source", "github",
    "--heat-csv", "data/billund_abvaerk_hourly_splejset_jun2026.csv",
    "--with-balancing", "--disable", "tank_eksisterende",
    "--set", "grid.max_consumption_mw=1000",
    "--start", "2026-01-05", "--end", "2026-01-16", "--mip-gap", "0",
]
RIGTIGT = 1_647_142


def test_standard_er_automatisk():
    assert Solver().presolve_rule_off is None
    assert "presolve_rule_off" not in Solver().as_options()
    assert Solver(presolve_rule_off=0).as_options()["presolve_rule_off"] == 0


def test_negativ_bitmaske_afvises():
    with pytest.raises(ValueError, match=">= 0"):
        Solver(presolve_rule_off=-1)


@pytest.mark.usefixtures("df_data")
def test_robust_uden_tank_finder_det_rigtige_optimum():
    r = subprocess.run(KMD, capture_output=True, text=True, timeout=600)
    ud = r.stdout + r.stderr
    assert r.returncode == 0, ud[-2000:]
    obj = float(re.search(r"^Objektiv:\s+([\d,]+)", ud, re.M).group(1).replace(",", ""))
    # mip_abs_gap er 1.000 kr. i casen
    assert "presolve_rule_off=4096" in ud
    assert abs(obj - RIGTIGT) <= 1_000, obj
