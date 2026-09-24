"""Vagt om den tidsvarierende forbrugstarif (punkt d) og budvinduet (punkt g).

Testene rører ingen data, kalder ingen solver og laver ingen netværkskald.
De holder fast i de fejl, der er stille — dem hvor resultatet stadig ser
plausibelt ud, men er forkert:

* elafgiften talt to gange, så en lavlasttime bliver 130,4 i stedet for 126,4
* båndopslag på UTC i stedet for lokal tid, som forskyder alt en time om
  sommeren og rammer grænsetimerne 06 og 21
* et timebånd, der mangler for én dagtype i én sæson, og bare falder igennem
* store bededag, der er afskaffet fra 2024, men stadig ligger i kalenderen
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.config import load_case
from src.tariff import (
    ConsumptionTariff,
    TariffSeason,
    danish_holidays,
    parse_consumption_tariff,
    resolve_consumption_tariff,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES = REPO_ROOT / "cases"

_SKEMA = {
    "unit": "kr_per_mwh",
    "fixed_components": {"energinet": 115.0, "dv": 0.0, "elafgift_net": 4.0},
    "net_tariff": {
        "bands": {"lav": 7.4, "hoej": 14.8, "spids": 29.5},
        "seasons": {
            "vinter": {
                "months": [10, 11, 12, 1, 2, 3],
                "weekday": {"00-06": "lav", "06-21": "spids", "21-24": "hoej"},
                "weekend": {"00-06": "lav", "06-21": "hoej", "21-24": "hoej"},
            },
            "sommer": {
                "months": [4, 5, 6, 7, 8, 9],
                "weekday": {"00-06": "lav", "06-24": "hoej"},
                "weekend": {"00-06": "lav", "06-24": "lav"},
            },
        },
    },
}


class _El:
    tariff_consumption_flat = 128.2
    electricity_tax = 4.0
    tariff_consumption = None


class _Cfg:
    def __init__(self, profil):
        self.electricity = _El()
        self.electricity.tariff_consumption = profil


def _dataset(start: str, timer: int) -> xr.Dataset:
    idx = pd.date_range(start, periods=timer, freq="h")
    return xr.Dataset(
        {"spot_price": ("time", np.zeros(timer))}, coords={"time": idx}
    )


def _serie(profil_raw, start: str, timer: int) -> pd.Series:
    cfg = _Cfg(parse_consumption_tariff(profil_raw))
    ds = _dataset(start, timer)
    s = resolve_consumption_tariff(cfg, ds).to_series()
    s.index = s.index.tz_localize("UTC").tz_convert("Europe/Copenhagen")
    return s


# --- helligdage ------------------------------------------------------------

def test_store_bededag_er_afskaffet():
    """Fjerde fredag efter påske må ikke være helligdag fra 2024."""
    from datetime import timedelta
    for aar in (2024, 2025, 2026):
        h = danish_holidays(aar)
        paaske = min(d for d in h if d.month in (3, 4) and d.weekday() == 6)
        assert paaske + timedelta(days=26) not in h


def test_paaskeberegning_2026():
    """Påskedag 2026 er 5. april. Følgedagene skal falde rigtigt."""
    h = danish_holidays(2026)
    assert date(2026, 4, 5) in h            # påskedag
    assert date(2026, 4, 3) in h            # langfredag
    assert date(2026, 5, 14) in h           # Kristi himmelfartsdag
    assert date(2026, 5, 25) in h           # 2. pinsedag


def test_grundlovsdag_er_ikke_helligdag_som_standard():
    """Ikke verificeret mod afregningsdata — skal tilføjes bevidst, ikke antages."""
    assert date(2026, 6, 5) not in danish_holidays(2026)


# --- bånd og dagtype -------------------------------------------------------

def test_dagtype_slaar_igennem_om_sommeren():
    """En tirsdag og en lørdag i juni skal give forskellig tarif kl. 10."""
    s = _serie(_SKEMA, "2026-06-01", 24 * 8)
    tirsdag = s[(s.index.date == date(2026, 6, 2)) & (s.index.hour == 10)].iloc[0]
    loerdag = s[(s.index.date == date(2026, 6, 6)) & (s.index.hour == 10)].iloc[0]
    assert tirsdag == pytest.approx(129.8)
    assert loerdag == pytest.approx(122.4)


def test_spidslast_kun_paa_vinterhverdage():
    s = _serie(_SKEMA, "2026-01-05", 24 * 7)
    mandag = s[(s.index.date == date(2026, 1, 5)) & (s.index.hour == 10)].iloc[0]
    soendag = s[(s.index.date == date(2026, 1, 11)) & (s.index.hour == 10)].iloc[0]
    assert mandag == pytest.approx(144.5)       # 115 + 29,5
    assert soendag == pytest.approx(129.8)      # 115 + 14,8


def test_intervaller_er_halvaabne():
    """'06-21' dækker time 6 til og med 20. Time 21 hører til næste bånd."""
    s = _serie(_SKEMA, "2026-01-05", 24)
    kl20 = s[s.index.hour == 20].iloc[0]
    kl21 = s[s.index.hour == 21].iloc[0]
    assert kl20 == pytest.approx(144.5)
    assert kl21 == pytest.approx(129.8)


def test_opslag_paa_lokal_tid_ikke_utc():
    """Sommertid: UTC 04:00 er lokal 06:00 og hører til dagbåndet."""
    s = _serie(_SKEMA, "2026-06-02", 24)
    kl05 = s[s.index.hour == 5].iloc[0]
    kl06 = s[s.index.hour == 6].iloc[0]
    assert kl05 == pytest.approx(122.4)
    assert kl06 == pytest.approx(129.8)


# --- elafgift --------------------------------------------------------------

def test_elafgift_tælles_ikke_med_i_serien():
    """Lavlasttime skal være 122,4 herfra. Modellen lægger de 4 til selv."""
    s = _serie(_SKEMA, "2026-06-06", 24)
    assert s.iloc[3] == pytest.approx(122.4)


def test_elafgift_uenighed_afvises():
    profil = parse_consumption_tariff(_SKEMA)
    with pytest.raises(ValueError, match="afviger fra"):
        profil.fixed_sum(electricity_tax=8.0)


# --- validering ------------------------------------------------------------

def test_manglende_timer_afvises_med_navngivet_saeson():
    skema = {
        **_SKEMA,
        "net_tariff": {
            "bands": _SKEMA["net_tariff"]["bands"],
            "seasons": {
                "vinter": {
                    "months": list(range(1, 13)),
                    "weekday": {"00-06": "lav"},          # 6–24 mangler
                    "weekend": {"00-24": "lav"},
                },
            },
        },
    }
    with pytest.raises(ValueError, match="vinter.*weekday"):
        parse_consumption_tariff(skema)


def test_maaneder_skal_daekke_hele_aaret():
    skema = {
        **_SKEMA,
        "net_tariff": {
            "bands": _SKEMA["net_tariff"]["bands"],
            "seasons": {
                "kun_vinter": {
                    "months": [1, 2],
                    "weekday": {"00-24": "lav"},
                    "weekend": {"00-24": "lav"},
                },
            },
        },
    }
    with pytest.raises(ValueError, match="ikke dækket"):
        parse_consumption_tariff(skema)


def test_ukendt_baandnavn_afvises():
    skema = {
        **_SKEMA,
        "net_tariff": {
            "bands": {"lav": 7.4},
            "seasons": {
                "hele_aaret": {
                    "months": list(range(1, 13)),
                    "weekday": {"00-24": "mellem"},
                    "weekend": {"00-24": "lav"},
                },
            },
        },
    }
    with pytest.raises(ValueError, match="ikke er defineret"):
        parse_consumption_tariff(skema)


def test_forkert_enhed_afvises():
    with pytest.raises(ValueError, match="kr_per_mwh"):
        ConsumptionTariff(
            unit="oere_per_kwh",
            bands={"lav": 1.0},
            seasons=[
                TariffSeason(
                    name="a",
                    months=list(range(1, 13)),
                    weekday={"00-24": "lav"},
                    weekend={"00-24": "lav"},
                )
            ],
        )


# --- bagudkompatibilitet og cases -----------------------------------------

def test_uden_profil_bruges_den_flade_vaerdi():
    cfg = _Cfg(None)
    serie = resolve_consumption_tariff(cfg, _dataset("2026-06-01", 24))
    assert float(serie.mean()) == pytest.approx(128.2)


def test_flad_kontrolprofil_giver_den_flade_vaerdi(tmp_path):
    """Regressionsvagten: er alle tre bånd ens, skal profilen give samme værdi
    i hver eneste time — uanset sæson, ugedag og klokkeslæt.

    Kontrollen laa tidligere i cases/billund_sporB_v3_d_tarif_flad.yaml. Den
    case blev slettet 9. september 2026 ved oprydningen til fem cases, saa
    profilen bygges nu i testen. 115,0 + 13,2 + 0,0 + 0,0 = 128,2.
    """
    import yaml

    raw = yaml.safe_load((CASES / "billund_sporB.yaml").read_text())
    raw["electricity"]["tariff_consumption"] = {
        "unit": "kr_per_mwh",
        "source": "regressionskontrol — flad 128,2",
        "fixed_components": {"energinet": 115.0, "dv": 0.0, "elafgift_net": 4.0},
        "net_tariff": {
            "bands": {"lav": 13.2, "hoej": 13.2, "spids": 13.2},
            "seasons": {
                "vinter": {
                    "months": [10, 11, 12, 1, 2, 3],
                    "weekday": {"00-06": "lav", "06-21": "spids", "21-24": "hoej"},
                    "weekend": {"00-06": "lav", "06-21": "hoej", "21-24": "hoej"},
                },
                "sommer": {
                    "months": [4, 5, 6, 7, 8, 9],
                    "weekday": {"00-06": "lav", "06-24": "hoej"},
                    "weekend": {"00-06": "lav", "06-24": "lav"},
                },
            },
        },
    }
    sti = tmp_path / "flad.yaml"
    sti.write_text(yaml.safe_dump(raw, allow_unicode=True))

    cfg = load_case(str(sti))
    serie = resolve_consumption_tariff(cfg, _dataset("2026-03-01", 24 * 40))
    assert float(serie.min()) == pytest.approx(128.2)
    assert float(serie.max()) == pytest.approx(128.2)


def test_andeby_baerer_alle_nye_felter():
    """Referencecasen skal demonstrere de features, den skal generalisere."""
    cfg = load_case(str(CASES / "andeby.yaml"))
    assert cfg.electricity.tariff_consumption is not None
    caps = cfg.ancillary_caps
    assert caps.per_unit_market_mw, "per_unit_market_mw mangler i andeby.yaml"
    assert cfg.reservation_gate is not None
    assert cfg.reservation_gate.afrr.opportunity_cost is not None
    vinduer = [
        u.name for u in cfg.units.values()
        if getattr(u.ancillary, "bid_window", None)
    ]
    assert vinduer, "ingen enhed i andeby.yaml har et bid_window"
    assert len(cfg.storage) >= 2, "andeby.yaml skal vise tanken i to lag"
