"""Tidsvarierende forbrugstarif — punkt (d).

`electricity.tariff_consumption_flat` er ét tal. Netselskabernes forbrugstarif
er tre bånd over døgnet, forskellige sommer og vinter, og forskellige på
hverdage og weekender. Dette modul opløser en båndprofil fra casefilen til én
timeserie på modellens tidsakse.

Profilen defineres i YAML og ikke i datalaget med vilje: en driftsleder kan slå
sine egne bånd op på netselskabets prisblad, men kan ikke lægge en tidsserie i
et fælles datarepo.

To ting, der er nemme at få galt i halsen:

**Elafgiften tælles ikke med her.** Modellen lægger `electricity.electricity_tax`
til separat i både `src/model.py` og `src/balancing.py`. Står `elafgift_net`
også i profilen, ville den indgå to gange. Posten skal derfor stå eksplicit i
YAML'en som dokumentation, men den valideres mod `electricity_tax` og udelades
af den opløste serie. En lavlasttime på A-høj bliver 122,4 fra dette modul og
126,4 når modellen har lagt afgiften til.

**Opslaget sker på lokal tid.** Modellens tidsakse er UTC. Time, ugedag og måned
slås op på Europa/København. Gør man det ikke, forskydes båndene en time om
sommeren, og grænsetimerne 06 og 21 lander i det forkerte bånd — en fejl der
ser rigtig ud i outputtet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import xarray as xr

_TZ = "Europe/Copenhagen"
_DAYTYPES = ("weekday", "weekend")


# ---------------------------------------------------------------------------
# Helligdage
# ---------------------------------------------------------------------------

def _easter_sunday(year: int) -> date:
    """Anonym gregoriansk algoritme."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def danish_holidays(year: int) -> set[date]:
    """Danske helligdage i tarifmæssig forstand.

    Store bededag er afskaffet fra 2024 og er ikke med.

    1. maj, grundlovsdag, juleaftensdag og nytårsaftensdag er IKKE med. De er
    fridage på mange overenskomster, men om netselskabet regner dem som
    weekend i tarifskemaet er ikke verificeret mod afregningsdata. Afviger et
    netselskab, tilføjes de via `extra_holidays` i casefilen. Vinduet
    marts–juni 2026 indeholder grundlovsdag og kan afgøre spørgsmålet, når
    tarif-facit sammenlignes time for time.
    """
    e = _easter_sunday(year)
    return {
        date(year, 1, 1),               # nytårsdag
        e - timedelta(days=3),          # skærtorsdag
        e - timedelta(days=2),          # langfredag
        e,                              # påskedag
        e + timedelta(days=1),          # 2. påskedag
        e + timedelta(days=39),         # Kristi himmelfartsdag
        e + timedelta(days=49),         # pinsedag
        e + timedelta(days=50),         # 2. pinsedag
        date(year, 12, 25),             # juledag
        date(year, 12, 26),             # 2. juledag
    }


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

@dataclass
class TariffSeason:
    name: str
    months: list[int]
    weekday: dict          # {"00-06": "lav", ...}
    weekend: dict


@dataclass
class ConsumptionTariff:
    """Båndprofil for forbrugstariffen. Se spec_tidsvarierende_tarif.md."""
    unit: str
    bands: dict                                   # navn → DKK/MWh
    seasons: list[TariffSeason]
    fixed_components: dict = field(default_factory=dict)
    extra_holidays: list[str] = field(default_factory=list)
    source: Optional[str] = None

    # -- validering ---------------------------------------------------------

    def __post_init__(self) -> None:
        if self.unit != "kr_per_mwh":
            raise ValueError(
                f"electricity.tariff_consumption.unit skal være 'kr_per_mwh', "
                f"fik {self.unit!r}"
            )
        self._check_months()
        for season in self.seasons:
            for daytype in _DAYTYPES:
                self._check_hours(season, daytype)

    def _check_months(self) -> None:
        seen: dict[int, str] = {}
        for season in self.seasons:
            for m in season.months:
                if m in seen:
                    raise ValueError(
                        f"tariff_consumption: måned {m} står i både "
                        f"{seen[m]!r} og {season.name!r}"
                    )
                seen[m] = season.name
        mangler = sorted(set(range(1, 13)) - set(seen))
        if mangler:
            raise ValueError(
                f"tariff_consumption: månederne {mangler} er ikke dækket af "
                f"nogen sæson. Alle 12 måneder skal stå præcis én gang."
            )

    def _check_hours(self, season: TariffSeason, daytype: str) -> None:
        skema = getattr(season, daytype)
        daekning: dict[int, str] = {}
        for span, band in skema.items():
            if band not in self.bands:
                raise ValueError(
                    f"tariff_consumption: sæson {season.name!r}, {daytype}, "
                    f"interval {span!r} refererer båndet {band!r}, som ikke er "
                    f"defineret under 'bands' ({sorted(self.bands)})"
                )
            for h in _parse_span(span, season.name, daytype):
                if h in daekning:
                    raise ValueError(
                        f"tariff_consumption: sæson {season.name!r}, {daytype}, "
                        f"time {h:02d} er dækket af både {daekning[h]!r} og {span!r}"
                    )
                daekning[h] = span
        mangler = sorted(set(range(24)) - set(daekning))
        if mangler:
            raise ValueError(
                f"tariff_consumption: sæson {season.name!r}, {daytype} — "
                f"timerne {mangler} er ikke dækket. Intervaller er halvåbne, "
                f"så '06-21' dækker time 6 til og med 20."
            )

    # -- opslag -------------------------------------------------------------

    def fixed_sum(self, electricity_tax: float) -> float:
        """Sum af de tidsuafhængige poster, UDEN elafgiften.

        `elafgift_net` valideres mod modellens egen `electricity_tax` og
        udelades derefter, så afgiften kun tælles én gang.
        """
        total = 0.0
        for navn, vaerdi in self.fixed_components.items():
            if navn == "elafgift_net":
                if abs(float(vaerdi) - float(electricity_tax)) > 1e-9:
                    raise ValueError(
                        f"tariff_consumption.fixed_components.elafgift_net = "
                        f"{vaerdi} afviger fra electricity.electricity_tax = "
                        f"{electricity_tax}. De skal være samme tal — posten står "
                        f"i profilen som dokumentation og lægges til af modellen, "
                        f"ikke af tariffen."
                    )
                continue
            total += float(vaerdi)
        return total

    def season_for_month(self, month: int) -> TariffSeason:
        for season in self.seasons:
            if month in season.months:
                return season
        raise KeyError(month)          # kan ikke ske efter _check_months

    def holiday_dates(self, years) -> set[date]:
        dates: set[date] = set()
        for y in years:
            dates |= danish_holidays(int(y))
        for s in self.extra_holidays:
            dates.add(pd.Timestamp(s).date())
        return dates


def _parse_span(span: str, season: str, daytype: str) -> range:
    try:
        start_s, end_s = span.split("-")
        start, end = int(start_s), int(end_s)
    except ValueError:
        raise ValueError(
            f"tariff_consumption: sæson {season!r}, {daytype} — intervallet "
            f"{span!r} kan ikke læses. Formatet er 'HH-HH', fx '06-21'."
        ) from None
    if not (0 <= start < end <= 24):
        raise ValueError(
            f"tariff_consumption: sæson {season!r}, {daytype} — intervallet "
            f"{span!r} er ugyldigt. Timer skal ligge i 0–24 og start < slut."
        )
    return range(start, end)


def parse_consumption_tariff(raw: Optional[dict]) -> Optional[ConsumptionTariff]:
    if not raw:
        return None
    seasons = []
    for navn, s in (raw.get("net_tariff", {}).get("seasons", {})).items():
        seasons.append(
            TariffSeason(
                name=navn,
                months=list(s["months"]),
                weekday=dict(s["weekday"]),
                weekend=dict(s["weekend"]),
            )
        )
    if not seasons:
        raise ValueError(
            "tariff_consumption: net_tariff.seasons mangler eller er tom"
        )
    return ConsumptionTariff(
        unit=raw.get("unit", ""),
        bands=dict(raw.get("net_tariff", {}).get("bands", {})),
        seasons=seasons,
        fixed_components=dict(raw.get("fixed_components", {})),
        extra_holidays=list(raw.get("extra_holidays", [])),
        source=raw.get("source"),
    )


# ---------------------------------------------------------------------------
# Opløsning til timeserie
# ---------------------------------------------------------------------------

_CACHE_KEY = "tariff_consumption_dkk_mwh"


def resolve_consumption_tariff(cfg, data: xr.Dataset) -> xr.DataArray:
    """Forbrugstariffen på modellens tidsakse, UDEN elafgift.

    Uden profil i casen returneres `tariff_consumption_flat` som konstant, så
    eksisterende cases er upåvirkede. Er begge sat, vinder profilen, og der
    logges en advarsel med begge værdier.

    Resultatet caches på `data`, så begge forbrugere — dispatch-omkostningen og
    budprisen — deler samme serie. Ellers får vi to sandheder om samme tal.
    """
    if _CACHE_KEY in data.data_vars:
        return data[_CACHE_KEY]

    flat = float(cfg.electricity.tariff_consumption_flat)
    profil = getattr(cfg.electricity, "tariff_consumption", None)

    if profil is None:
        serie = xr.full_like(data["spot_price"], flat)
        data[_CACHE_KEY] = serie
        return serie

    idx = pd.DatetimeIndex(data["time"].values)
    lokal = idx.tz_localize("UTC").tz_convert(_TZ)

    fixed = profil.fixed_sum(cfg.electricity.electricity_tax)
    helligdage = profil.holiday_dates(sorted(set(lokal.year)))

    vaerdier = np.empty(len(lokal), dtype=float)
    for i, ts in enumerate(lokal):
        season = profil.season_for_month(ts.month)
        er_fri = ts.weekday() >= 5 or ts.date() in helligdage
        skema = season.weekend if er_fri else season.weekday
        band = None
        for span, navn in skema.items():
            lo, hi = span.split("-")
            if int(lo) <= ts.hour < int(hi):
                band = navn
                break
        vaerdier[i] = fixed + float(profil.bands[band])

    serie = xr.DataArray(vaerdier, coords={"time": data["time"]}, dims=["time"])
    data[_CACHE_KEY] = serie

    simpelt = float(serie.mean())
    print(
        f"  Forbrugstarif: profil aktiv ({profil.source or 'uden kilde'}). "
        f"Simpelt timegennemsnit {simpelt:.1f} DKK/MWh eksklusive elafgift "
        f"({cfg.electricity.electricity_tax:.1f}); flad værdi i casen er {flat:.1f}. "
        f"Faste poster {fixed:.1f}."
    )
    if abs(simpelt - flat) > 1e-9:
        print(
            f"  ADVARSEL: både tariff_consumption og tariff_consumption_flat er "
            f"sat. Profilen vinder. Flad {flat:.1f} er ikke i brug."
        )
    return serie
