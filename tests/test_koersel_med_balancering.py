"""Røgtest: en rigtig kørsel med --with-balancing, ende til ende.

Ingen anden test bygger balancemodellen gennem run_case. Derfor kunne en
NameError i balancing._add_market_reserves (september 2026: `cop` fjernet
fra løkken, men brugt i varmereduktionen) komme på main med 338 grønne tests
— og alle kørsler med balancering døde i første sekund.

Testen kører to døgn i marts 2026 for Billund, både med den lineære VP-kurve
og med den målte ydelsestabel, og for begge balanceringsmetoder. Den måler
ikke tal, kun at kørslen når til en optimal løsning. Ca. 5 sekunder pr. kørsel
mod den lokale df-data-klon; intet netværk.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HEAT_CSV = REPO_ROOT / "data" / "billund_abvaerk_hourly_splejset_jun2026.csv"


@pytest.mark.parametrize("case", ["billund_sporA_rullende",
                                  "billund_sporA_rullende_vptabel"])
@pytest.mark.parametrize("metode", ["activation_value", "legacy"])
def test_to_doegn_med_balancering(case, metode, tmp_path, df_data):
    r = subprocess.run(
        [sys.executable, "run_case.py", f"cases/{case}.yaml",
         "--data-source", "github", "--with-balancing",
         "--balancing-method", metode,
         "--heat-csv", str(HEAT_CSV),
         "--start", "2026-03-02", "--end", "2026-03-03",
         "--out-dir", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "('ok', 'optimal')" in r.stdout
    assert "SAMLET brutto aktivering" in r.stdout      # balancedelen blev bygget
