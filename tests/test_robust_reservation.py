"""Robust reservation (balancing.robust_reservation), 14/10-2026.

Fundet: uden tank om sommeren reserverede modellen elkedlen i timer med lav
varmelast og regnede med, at den FORVENTEDE aktivering fjernede varmen. Blev
reservationen afregnet på det realiserede (settle: realized), og udeblev
aktiveringen, var der ingen afsætning for varmen, og modellen var uløselig.

Med robust_reservation skal driften også holde uden aktivering, som værkerne
planlægger i dag. Testene kører et kort sommervindue uden tank.
"""
import subprocess
import sys

import pytest
import yaml

from src.config import load_case

CASE = "cases/billund_sporA_rullende_bud.yaml"
FAELLES = [
    sys.executable, "run_case.py", CASE, "--data-source", "github",
    "--heat-csv", "data/billund_abvaerk_hourly_splejset_jun2026.csv",
    "--with-balancing", "--disable", "tank_eksisterende",
    "--set", "balancing.activation.foresight=trailing30",
    "--set", "balancing.activation.settle=realized",
    "--start", "2025-07-01", "--end", "2025-07-03",
]


def _koer(robust: bool):
    return subprocess.run(
        FAELLES + ["--set", f"balancing.robust_reservation={str(robust).lower()}"],
        capture_output=True, text=True, timeout=600)


def test_uden_robust_kan_reservationen_ikke_holdes():
    # Dokumenterer fejlen, der førte til robust_reservation — og at testen
    # nedenfor faktisk kan skelne de to tilfælde.
    r = _koer(robust=False)
    assert r.returncode != 0
    assert "kan ikke løses" in r.stdout + r.stderr


def test_med_robust_kan_reservationen_holdes():
    r = _koer(robust=True)
    ud = r.stdout + r.stderr
    assert r.returncode == 0, ud[-2000:]
    assert "Robust reservation" in ud
    assert "Trin 1-objektiv" in ud and "\nObjektiv:" in ud


def test_robust_er_slaaet_fra_som_standard(tmp_path):
    d = yaml.safe_load(open("cases/andeby.yaml", encoding="utf-8"))
    d["balancing"].pop("robust_reservation", None)
    sti = tmp_path / "uden_noegle.yaml"
    sti.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    assert load_case(str(sti)).robust_reservation is False


def test_ukendt_noegle_i_balancing_afvises(tmp_path):
    # En stavefejl i robust_reservation må ikke tavst slå den fra.
    d = yaml.safe_load(open("cases/andeby.yaml", encoding="utf-8"))
    d["balancing"]["robust_reservaton"] = True
    sti = tmp_path / "stavefejl.yaml"
    sti.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="ukendte noegler i balancing"):
        load_case(str(sti))
