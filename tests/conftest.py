"""Fælles fixtures for dæknings-testene.

Testene måler mod den lokale df-data-klon (data/df-data). De henter intet
over netværket og kalder aldrig run_case.main() eller en solver.

Alle tidskolonner slås op ved NAVN, aldrig ved position: balancefilerne
bruger `TimeUTC`, spot/dmi bruger `hour_utc` (målt i Gate 0.5).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DF_DATA_DIR = REPO_ROOT / "data" / "df-data"


@pytest.fixture(scope="session", autouse=True)
def _require_df_data():
    """Skip alt i denne mappe hvis klonen ikke er til stede.

    Autouse + session-scope, så en manglende klon giver én klar besked i
    stedet for at hver test fejler med FileNotFoundError nede i pandas.
    """
    if not (DF_DATA_DIR / ".git").exists():
        pytest.skip(
            f"df-data-klonen mangler: {DF_DATA_DIR}. "
            "Testene måler på den lokale klon og henter intet over netværket. "
            "Kør en github-kørsel én gang, eller: git clone --depth 1 "
            f"https://github.com/skj-1964/df-data.git {DF_DATA_DIR}"
        )


@pytest.fixture(scope="session")
def df_data(_require_df_data) -> Path:
    """Sti til df-data-klonens rod."""
    return DF_DATA_DIR


@pytest.fixture(scope="session")
def df_data_head(_require_df_data) -> str:
    """Klonens HEAD-SHA (kort) + dato, fx '6c95bde 2026-08-07'.

    En fejlende dækningstest skal kunne sige HVILKEN dataversion den målte
    mod: datarepoet opdateres uafhængigt af modelrepoet, og manifestet
    registrerer det ikke (målt i Gate 0.5 §C4). Brug den i assert-beskeder.
    """
    try:
        return subprocess.check_output(
            ["git", "-C", str(DF_DATA_DIR), "log", "-1",
             "--format=%h %ad", "--date=short"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:                       # pragma: no cover — kun diagnostik
        return "ukendt"
