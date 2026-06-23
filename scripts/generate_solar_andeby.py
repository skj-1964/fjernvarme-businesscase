"""
Generér en syntetisk solvarme-produktionsprofil for Andeby Varmeværk (trin 1).

Skriver data/synthetic_solar_andeby.csv med kolonnerne:
    time        UTC-tidsstempel, timeopløst (ISO 8601 med Z)
    power_mw    leverbar solvarmeeffekt i MW

Fysisk plausibel struktur (jf. rapport_andeby_metode §6), men IKKE måledata —
profilen erstattes senere med DMI-solstråling/måledata:

  * Daglængde varierer med årstid på 56° N (≈7 t ved vintersolhverv,
    ≈17 t ved sommersolhverv) via solens deklination.
  * Døgnvariation: sinusbue mellem solopgang og solnedgang, 0 om natten.
  * Sæson-intensitet: cosinus med peak ved sommersolhverv, ≈20 % ved
    vintersolhverv.
  * Stokastisk skydække-støj per time (mere variabel om sommeren).
  * Hele profilen skaleres til årssum = 12 GWh (≈12 % af Andebys ~100 GWh).
    Den realistiske peak (≈8 MW) ligger langt under nameplate (22 MW), fordi
    skydække/effektivitet/indfaldsvinkel reducerer den leverbare effekt.

Brug:
    python scripts/generate_solar_andeby.py            # 2025
    python scripts/generate_solar_andeby.py --year 2026
    python scripts/generate_solar_andeby.py --out data/synthetic_solar_andeby.csv
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

# Andeby er fiktivt; placeres klimatisk på dansk breddegrad.
LATITUDE_DEG = 56.0
ANNUAL_SUM_GWH = 12.0           # mål for årsproduktion (≈12 % af ~100 GWh)
SUMMER_SOLSTICE_DOY = 172       # ca. 21. juni
WINTER_FRACTION = 0.20          # sæson-intensitet ved vintersolhverv (af peak)
SEED = 1964                     # fast seed → CSV'en er reproducerbar


def _declination_deg(doy: np.ndarray) -> np.ndarray:
    """Solens deklination [grader] som funktion af dag-på-året (Cooper)."""
    return 23.45 * np.sin(np.deg2rad(360.0 / 365.0 * (doy - 81)))


def _day_length_hours(doy: np.ndarray) -> np.ndarray:
    """Daglængde [timer] på LATITUDE_DEG ud fra deklinationen."""
    lat = math.radians(LATITUDE_DEG)
    decl = np.deg2rad(_declination_deg(doy))
    # cos(omega_0) = -tan(lat)*tan(decl); clip mod numerisk over/underløb
    cos_omega = np.clip(-np.tan(lat) * np.tan(decl), -1.0, 1.0)
    omega0 = np.arccos(cos_omega)          # halv-dags-vinkel [rad]
    return 24.0 / math.pi * omega0


def _seasonal_intensity(doy: np.ndarray) -> np.ndarray:
    """Sæson-skala ∈ [WINTER_FRACTION, 1]: peak ved sommersolhverv."""
    theta = 2.0 * math.pi * (doy - SUMMER_SOLSTICE_DOY) / 365.0
    return WINTER_FRACTION + (1.0 - WINTER_FRACTION) * (1.0 + np.cos(theta)) / 2.0


def generate(year: int) -> pd.DataFrame:
    idx = pd.date_range(
        start=f"{year}-01-01 00:00",
        end=f"{year}-12-31 23:00",
        freq="h",
        tz="UTC",
    )
    doy = idx.dayofyear.to_numpy().astype(float)
    hour = idx.hour.to_numpy().astype(float)

    day_len = _day_length_hours(doy)
    seasonal = _seasonal_intensity(doy)

    # Døgnvariation: sinusbue fra solopgang til solnedgang (solar noon ≈ 12).
    sunrise = 12.0 - day_len / 2.0
    sunset = 12.0 + day_len / 2.0
    daytime = (hour >= sunrise) & (hour <= sunset)
    # Beskyt mod division ved nul daglængde (polar-grænse, ikke relevant på 56°N)
    safe_len = np.where(day_len > 0, day_len, 1.0)
    diurnal = np.where(
        daytime,
        np.sin(np.pi * np.clip((hour - sunrise) / safe_len, 0.0, 1.0)),
        0.0,
    )

    # Skydække-støj: multiplikativ dæmpning, mere variabel om sommeren.
    rng = np.random.default_rng(SEED)
    sigma = 0.15 + 0.20 * seasonal            # større spredning når solen står højt
    cloud = np.clip(1.0 - np.abs(rng.normal(0.0, sigma)), 0.05, 1.0)

    raw = seasonal * diurnal * cloud
    raw = np.where(raw < 0, 0.0, raw)

    # Skalér til årssum = ANNUAL_SUM_GWH (timeopløst → MWh = MW · 1 t).
    total_raw_mwh = raw.sum()
    scale = (ANNUAL_SUM_GWH * 1000.0) / total_raw_mwh
    power_mw = raw * scale

    return pd.DataFrame({"time": idx, "power_mw": power_mw})


def main() -> None:
    p = argparse.ArgumentParser(description="Generér syntetisk solvarme-profil for Andeby")
    p.add_argument("--year", type=int, default=2025,
                   help="Kalenderår der genereres timestamps for (default: 2025)")
    p.add_argument("--out", type=Path, default=Path("data/synthetic_solar_andeby.csv"),
                   help="Output-CSV (default: data/synthetic_solar_andeby.csv)")
    args = p.parse_args()

    df = generate(args.year)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # ISO 8601 med 'Z' så data_loader._attach_unit_profiles parser som UTC.
    out = df.copy()
    out["time"] = out["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out.to_csv(args.out, index=False, float_format="%.6f")

    total_gwh = df["power_mw"].sum() / 1000.0
    peak_mw = df["power_mw"].max()
    n_daylight = int((df["power_mw"] > 0).sum())
    print(f"Skrev {len(df)} rækker → {args.out}")
    print(f"  År:        {args.year}")
    print(f"  Årssum:    {total_gwh:.2f} GWh")
    print(f"  Peak:      {peak_mw:.2f} MW")
    print(f"  Dagstimer: {n_daylight} ({100*n_daylight/len(df):.0f} % af året)")
    print(f"  Gns (hele året): {df['power_mw'].mean():.3f} MW")


if __name__ == "__main__":
    main()
