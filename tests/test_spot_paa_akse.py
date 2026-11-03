"""Spot paa modellens akse: middel over tidsskridtet, ikke :00-kvarteret.

Spot skifter fra time- til kvarterspris 2025-09-30 22:00 UTC. Testene bruger
priser, hvor :00-kvarteret og middel er forskellige, saa en loader, der tager
foerste kvarter, fejler.
"""
import pandas as pd
import pytest

from src.data_loader import CoverageError, spot_paa_akse


def akse(start, slut, freq="h"):
    return pd.date_range(start, slut, freq=freq)


def test_timeakse_tager_middel_af_kvarterer():
    kv = pd.Series([100.0, 200.0, 300.0, 400.0],
                   index=akse("2026-01-01 00:00", "2026-01-01 00:45", "15min"))
    assert spot_paa_akse(kv, akse("2026-01-01 00:00", "2026-01-01 00:00")).iloc[0] == 250.0


def test_timepriser_er_uaendrede():
    t = pd.Series([10.0, 20.0, 30.0], index=akse("2025-01-01 00:00", "2025-01-01 02:00"))
    assert spot_paa_akse(t, t.index).tolist() == [10.0, 20.0, 30.0]


def test_skiftet_fra_time_til_kvarter():
    time = pd.Series([50.0], index=pd.to_datetime(["2025-09-30 21:00"]))
    kv = pd.Series([0.0, 10.0, 20.0, 30.0],
                   index=akse("2025-09-30 22:00", "2025-09-30 22:45", "15min"))
    ud = spot_paa_akse(pd.concat([time, kv]), akse("2025-09-30 21:00", "2025-09-30 22:00"))
    assert ud.tolist() == [50.0, 15.0]


def test_kvarterakse_er_uaendret():
    kv = pd.Series([0.0, 10.0, 20.0, 30.0],
                   index=akse("2026-01-01 00:00", "2026-01-01 00:45", "15min"))
    assert spot_paa_akse(kv, kv.index).tolist() == [0.0, 10.0, 20.0, 30.0]


def test_kvarterakse_fylder_timepris_frem():
    t = pd.Series([70.0], index=pd.to_datetime(["2025-01-01 00:00"]))
    ud = spot_paa_akse(t, akse("2025-01-01 00:00", "2025-01-01 00:45", "15min"))
    assert ud.tolist() == [70.0] * 4


def test_halv_time_stoppes():
    kv = pd.Series([0.0, 10.0],
                   index=akse("2026-01-01 00:00", "2026-01-01 00:15", "15min"))
    with pytest.raises(CoverageError, match="kvarterer"):
        spot_paa_akse(kv, akse("2026-01-01 00:00", "2026-01-01 00:00"))
