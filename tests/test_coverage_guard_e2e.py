"""F1 — end-to-end-test af dæknings-vagten gennem `_read_dataset`.

Forskellen på denne fil og `test_coverage_guard.py`:

  test_coverage_guard.py  kalder `assert_coverage` direkte og beviser at
                          vagten mangler.
  denne fil               kalder den faktiske `_read_dataset` og beviser at
                          LOADEREN i dag opfører sig forkert — den returnerer
                          tavst en delvist dækket frame.

Fejlmåden er derfor en anden og med vilje: A2/B2 skal fejle med
"DID NOT RAISE", ikke med "navnet findes ikke". Se `_coverage_error()`.

Perioder og rækketal er MÅLT i Gate 0.5 mod df-data-klonen.
Se noter/notat_f1_gate05_oploesning_akse.md.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.data_loader_github import _read_dataset


def _axis(start: str, end: str, freq: str = "h") -> pd.DatetimeIndex:
    """Modelakse som `make_time_index` ville bygge den: inklusiv i begge ender."""
    return pd.date_range(start, end, freq=freq)


def _coverage_error() -> type[BaseException]:
    """Hent `CoverageError`, eller en sentinel der aldrig kan rejses.

    Sentinel'en er pointen: så længe vagten ikke findes, fejler
    `pytest.raises(...)` med "DID NOT RAISE" — altså på loaderens faktiske
    adfærd, ikke på et manglende navn. Det er forskellen på at måle koden og
    at måle sig selv.
    """
    from src import data_loader

    exc = getattr(data_loader, "CoverageError", None)
    if exc is not None:
        return exc

    class _VagtenFindesIkkeEndnu(Exception):
        """Kan ikke rejses af noget. Tvinger pytest.raises til DID NOT RAISE."""

    return _VagtenFindesIkkeEndnu


# ---------------------------------------------------------------------------
# A2 — delvis dækning i en fil der findes, gennem _read_dataset
# ---------------------------------------------------------------------------

def test_A2_read_dataset_rejects_partial_coverage(df_data, df_data_head):
    """afrr/DK1 2024: filen findes, dækker kun okt-dec.

    Dagens `_read_dataset` returnerer 2186 rækker uden en lyd — `df.empty`
    er falsk, `missing` er tom, `if not frames` udløses ikke. 6598 af 8784
    modeltimer mangler og bliver nul-fyldt nedstrøms på linje 402/405.
    """
    with pytest.raises(_coverage_error()):
        _read_dataset(df_data, "afrr", "DK1",
                      _axis("2024-01-01 00:00", "2024-12-31 23:00"),
                      time_col="TimeUTC")


def test_A2_documents_what_head_returns_instead(df_data, df_data_head):
    """Dokumenterer HVAD dagens kode returnerer i stedet for at fejle.

    Denne test består både før og efter Gate 2 er irrelevant — den kører kun
    når vagten IKKE findes, og springes over bagefter. Den er beviset for at
    A2's "DID NOT RAISE" skyldes en delvist dækket frame og ikke en tom.
    """
    from src import data_loader

    if getattr(data_loader, "CoverageError", None) is not None:
        pytest.skip("vagten findes nu — dagens tavse adfærd er væk (Gate 2)")

    df = _read_dataset(df_data, "afrr", "DK1",
                       _axis("2024-01-01 00:00", "2024-12-31 23:00"),
                       time_col="TimeUTC")
    assert not df.empty, "frame er ikke tom — derfor fanger df.empty-vagten den ikke"
    assert len(df) == 2186, f"df-data {df_data_head}: forventede 2186, fik {len(df)}"
    ts = pd.to_datetime(df["TimeUTC"])
    assert ts.min() == pd.Timestamp("2024-10-01 22:00")


# ---------------------------------------------------------------------------
# B2 — manglende årsfil i et flerårsspænd, gennem _read_dataset
# ---------------------------------------------------------------------------

def test_B2_read_dataset_rejects_missing_year_file(df_data, df_data_head):
    """imbalance/DK1 2024-2025: 2024-filen findes ikke.

    Dagens kode printer "spring over DK1_2024.csv" (linje 148-153) og
    returnerer 2025-data. 10 284 modeltimer mangler.
    """
    assert not (df_data / "imbalance" / "DK1_2024.csv").exists(), \
        f"df-data {df_data_head}: DK1_2024.csv er kommet til — testen måler ikke længere hullet"

    with pytest.raises(_coverage_error()):
        _read_dataset(df_data, "imbalance", "DK1",
                      _axis("2024-01-01 00:00", "2025-12-31 23:00"),
                      time_col="TimeUTC")


# ---------------------------------------------------------------------------
# E2 — fuld dækning gennem _read_dataset. Skal bestå på HEAD og blive ved.
# ---------------------------------------------------------------------------

def test_E2_read_dataset_accepts_full_coverage(df_data, df_data_head):
    """afrr/DK1 2025: 8760 rækker, 0 huller. Loaderen skal returnere normalt."""
    df = _read_dataset(df_data, "afrr", "DK1",
                       _axis("2025-01-01 00:00", "2025-12-31 23:00"),
                       time_col="TimeUTC")

    assert len(df) == 8760, f"df-data {df_data_head}: forventede 8760, fik {len(df)}"
    ts = pd.to_datetime(df["TimeUTC"])
    assert ts.min() == pd.Timestamp("2025-01-01 00:00")
    assert ts.max() == pd.Timestamp("2025-12-31 23:00")
    assert not ts.duplicated().any()
