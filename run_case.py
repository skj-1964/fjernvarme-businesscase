"""
Kør en case fra kommandolinjen.

Brug:
    python run_case.py cases/billund_baseline.yaml --dummy
    python run_case.py cases/billund_baseline.yaml --external
    python run_case.py cases/billund_baseline.yaml --external --year 2023
    python run_case.py cases/billund_baseline.yaml --external \
        --start 2025-04-01 --end 2026-03-31
    python run_case.py cases/billund_baseline.yaml --external \
        --heat-params cases/heat_load_params_v2.yaml
    python run_case.py cases/billund_baseline.yaml --external \
        --set storage.tank_eksisterende.volume_m3=4000
    python run_case.py cases/billund_baseline.yaml --external \
        --set prices.co2_eua.value=800 --set prices.natural_gas.value=500

Datakilder (vælg én — default er --dummy):
    --dummy       fuldt syntetiske serier (temp, spot, last)
    --external    rigtig DMI-temp + Energinet-spot + syntetisk varmelast
                  (dual-slope v2 fra cfg.heat_load_params)
    --data-path   sti til Billunds rigtige målerdata (ikke aktiveret endnu)

Periode (vælg max én variant — alle overrider cfg.time):
    --year YYYY                     hele kalenderåret
    --start YYYY-MM-DD              startdato (kræver --end)
    --end YYYY-MM-DD                slutdato (kræver --start)

Enhedsoverrides:
    --enable / --disable NAVN    — kan gentages

Heat-load parametre (kun relevante med --external):
    --heat-params PATH   — valgfri YAML-fil der overrider case-filens
                          heat_load_params-sektion. Brug fx en alternativ
                          kalibrering fra scripts/calibrate_heat_load.py.

Generisk YAML-override (kan gentages):
    --set dotted.path=value   — overskriver vilkårlig leaf-værdi i YAML'en
                                FØR dataclass-construction. Værdien parses
                                som YAML (automatisk type-coercion).
                                Eksempler:
                                  --set storage.tank_eksisterende.volume_m3=4000
                                  --set units.vp_luft_vand.ancillary.afrr_max_bid_mw=3.0
                                  --set ancillary_groups.elkedler.afrr_max_bid_mw=8.0

Output:
    Alle filer får præfiks der afspejler kørslen, fx:
        billund_baseline__ext__2024__off-tank_eksisterende_dispatch.png
        billund_baseline__ext__2025-04-01_2026-03-31__bal_hourly.csv
        billund_baseline__ext__2024__set-volume_m3-4000_dispatch.png
    Format: {case_name}__{data}__{periode}[__bal][__{overrides}]
    Perioden er enten året (hvis hele kalenderåret) eller start_end.
    Overrides er alfabetisk sorterede; samme scenarie giver altid samme
    filnavn uanset CLI-rækkefølge.
"""
from __future__ import annotations
import argparse
from pathlib import Path

import pandas as pd

from src.config import load_case
from src.data_loader import (
    generate_dummy_data,
    load_external_data,
    load_heat_load_params,
    HeatLoadParams,
)
from src.data_loader_github import (
    DEFAULT_DF_DATA_URL,
    DEFAULT_DF_DATA_CACHE,
    load_external_data_github,
)
from src.model import build_model
from src.solve import solve_and_extract
from src.reporting import (
    kpi_summary,
    dispatch_plot,
    write_hourly_csv,
    seasonal_summary,
)


def _parse_args():
    p = argparse.ArgumentParser(description="Kør fjernvarme business case")
    p.add_argument("case", type=str, help="Sti til case YAML")

    # Datakilde — mutuelt eksklusive
    src = p.add_mutually_exclusive_group()
    src.add_argument("--dummy", action="store_true",
                     help="Fuldt syntetiske data (default)")
    src.add_argument("--external", action="store_true",
                     help="Rigtig DMI-temp + Energinet-spot + syntetisk last")
    src.add_argument("--data-path", type=str, default=None,
                     help="Sti til Billund-målerdata (ikke aktiveret endnu)")

    # External data options
    p.add_argument("--dmi-area", default="fyn",
                   help="DMI area-kode (default: fyn — Billund har ikke egen; fyn er klimatisk tæt)")
    p.add_argument("--dmi-temp-shortname", default="temp_mean_past1h",
                   help="DMI observationsvariabel for temperatur")
    p.add_argument("--price-zone", default="DK1",
                   help="Energinet priszone (default: DK1)")
    p.add_argument("--eur-dkk", type=float, default=7.45,
                   help="EUR→DKK kurs for spot-konvertering")
    p.add_argument("--cache-dir", default="data/raw",
                   help="Mappe til cachede API-svar (Parquet)")
    p.add_argument("--force-refresh", action="store_true",
                   help="Ignorér cache og hent fra API påny")

    # Datakilde for --external — vælg API (Energinet/DMI direkte) eller
    # GitHub-cache (df-data repo). Default er API for bagudkompatibilitet.
    # --data-source github impliserer --external.
    p.add_argument("--data-source", choices=["api", "github"], default="api",
                   help="Hvor henter --external data fra? 'api' = Energinet/DMI "
                        "direkte (default). 'github' = df-data-repo (sandkasse-"
                        "venligt; kræver github.com adgang). 'github' impliserer "
                        "--external.")
    p.add_argument("--df-data-url", default=DEFAULT_DF_DATA_URL,
                   help=f"Git-URL til df-data-repo (default: {DEFAULT_DF_DATA_URL})")
    p.add_argument("--df-data-cache", default=DEFAULT_DF_DATA_CACHE,
                   help=f"Lokal sti til df-data-klon (default: {DEFAULT_DF_DATA_CACHE})")

    # Årstal / periode — overrider cfg.time.start/end
    # --year og (--start + --end) er mutuelt eksklusive. Argparse's
    # mutually_exclusive_group understøtter ikke "enten A eller (B AND C)"
    # pænt, så vi validerer kombinationen manuelt i main().
    p.add_argument("--year", type=int, default=None,
                   help="Årstal der regnes på (overrider cfg.time.start/end). "
                        "Sætter perioden til {YEAR}-01-01..{YEAR}-12-31.")
    p.add_argument("--start", type=str, default=None,
                   help="Startdato YYYY-MM-DD (overrider cfg.time.start). "
                        "Skal bruges sammen med --end. Kan ikke kombineres "
                        "med --year.")
    p.add_argument("--end", type=str, default=None,
                   help="Slutdato YYYY-MM-DD (overrider cfg.time.end). "
                        "Skal bruges sammen med --start.")

    # Heat-load parametre (kun --external)
    # v2: dual-slope syntese kalibreres via scripts/calibrate_heat_load.py.
    # Parametrene ligger i case YAML under heat_load_params, men kan overrides
    # med --heat-params for at prøve alternative kalibreringer.
    p.add_argument("--heat-params", type=Path, default=None,
                   help="Sti til alternativ heat_load_params YAML (override "
                        "case-filens heat_load_params-sektion)")

    # Solver og output
    p.add_argument("--solver", type=str, default="highs")
    p.add_argument("--days", type=int, default=7,
                   help="Antal dage til dispatch-plot")
    p.add_argument("--out-dir", type=str, default="output")

    # Enable/disable enheder og lagre
    p.add_argument("--enable", action="append", default=[],
                   help="Override: aktivér enhed eller lager (kan gentages)")
    p.add_argument("--disable", action="append", default=[],
                   help="Override: deaktivér enhed eller lager (kan gentages)")
    # Balancemarked (trin 8.2)
    p.add_argument("--with-balancing", action="store_true",
                   help="Hent aFRR-priser fra EDS og aktivér reservemodel. "
                        "Kræver at cfg.time dækker et post-PICASSO regime "
                        "(fra ca. april 2025 og frem).")

    # Generisk YAML-override — kan gentages, anvendes på raw dict FØR
    # dataclass-construction så __post_init__ (fx Storage.e_max_mwh-
    # beregning) ser de overriddede værdier.
    p.add_argument(
        "--set", dest="set_overrides", action="append", default=[],
        metavar="PATH=VALUE",
        help=(
            "Override en YAML-parameter. Format: 'dotted.path=value'. Kan "
            "gentages for flere overrides. Værdien parses som YAML "
            "(int/float/bool/null/str coerces automatisk). Eksempler: "
            "--set storage.tank_eksisterende.volume_m3=4000  "
            "--set prices.co2_eua.value=800  "
            "--set units.vp_luft_vand.ancillary.afrr_max_bid_mw=3.0  "
            "--set ancillary_groups.elkedler.afrr_max_bid_mw=8.0"
        ),
    )

    return p.parse_args()


def _build_output_stem(args, cfg) -> str:
    """
    Byg filnavn-stem som afspejler kørslens parametre.

    Format: {case_name}__{data}__{year}[__{overrides}]

    Året læses fra cfg.time.start (post-override), så det altid afspejler
    den faktiske analyseperiode — uanset om året er sat via YAML eller --year.

    Overrides er alfabetisk sorterede, så samme scenarie altid giver
    samme filnavn uanset CLI-rækkefølge. Dobbelt-underscore adskiller
    'kategorier' (case/data/år/overrides), enkelt-bindestreg adskiller
    individuelle overrides.

    Eksempler:
      billund_baseline__ext__2024
      billund_baseline__ext__2024__off-tank_eksisterende
      billund_baseline__dummy__2024__off-halmkedel-on-overskudsvarme
    """
    parts = [cfg.meta["case_name"]]

    # Datakilde
    if args.external:
        parts.append("gh" if args.data_source == "github" else "ext")
    elif args.data_path is not None:
        parts.append("file")
    else:
        parts.append("dummy")

    # Periode — læses fra cfg (post-override). Hvis det er et rent kalenderår,
    # bruges kun året (bagudkompatibel med tidligere filnavne). Ellers bruges
    # start_end i ISO-format, hvilket er entydigt og sorterbart i fx:
    #   billund_baseline__ext__2025-04-01_2026-03-31__bal
    start_ts = pd.Timestamp(cfg.time.start)
    end_ts = pd.Timestamp(cfg.time.end)
    is_full_year = (
        start_ts.month == 1 and start_ts.day == 1
        and end_ts.month == 12 and end_ts.day == 31
        and start_ts.year == end_ts.year
    )
    if is_full_year:
        parts.append(str(start_ts.year))
    else:
        parts.append(f"{start_ts.strftime('%Y-%m-%d')}_{end_ts.strftime('%Y-%m-%d')}")

    # Balancing-markør
    if args.with_balancing:
        parts.append("bal")

    # Overrides — alfabetisk sorteret for determinisme
    overrides = []
    for name in sorted(args.enable):
        overrides.append(f"on-{name}")
    for name in sorted(args.disable):
        overrides.append(f"off-{name}")
    # --set-overrides: inkluder kort form af hver override i filnavnet.
    # Bruger de sidste 2 path-segmenter så generiske leaf-navne (fx 'value')
    # ikke giver filnavn-kollision mellem forskellige overrides:
    #   'prices.co2_eua.value=800' → 'set-co2_eua_value-800'
    #   'prices.natural_gas.value=500' → 'set-natural_gas_value-500'
    #   'storage.tank_eksisterende.volume_m3=4000' → 'set-tank_eksisterende_volume_m3-4000'
    # Hvis path har <2 segmenter, bruges hele stien.
    for ov in sorted(args.set_overrides):
        key, _, val = ov.partition("=")
        segments = key.split(".")
        key_short = "_".join(segments[-2:]) if len(segments) >= 2 else segments[0]
        val_safe = (
            str(val).replace(".", "_").replace("/", "-")
                    .replace(":", "-").replace(" ", "_")
        )
        overrides.append(f"set-{key_short}-{val_safe}")
    if overrides:
        parts.append("-".join(overrides))

    return "__".join(parts)


def _load_data(args, cfg):
    """Vælg datakilde baseret på flags."""
    if args.external:
        heat_load = load_heat_load_params(args.case, override_yaml=args.heat_params)
        if args.data_source == "github":
            print(f"Henter data fra df-data ({args.df_data_url})...")
        else:
            print(f"Henter ekstern data (DMI area={args.dmi_area}, "
                  f"spot={args.price_zone})...")
        source = args.heat_params if args.heat_params else args.case
        print(f"  Heat-load params (fra {Path(source).name}):")
        print(f"    β_gaf = {heat_load.gaf_mw_per_k:.4f} MW/K   "
              f"T_ref = {heat_load.t_ref:.1f}°C   "
              f"EMA = {heat_load.thermal_inertia_hours}h")
        if heat_load.nettab_slope_mw_per_k > 0:
            print(f"    β_net = {heat_load.nettab_slope_mw_per_k:.4f} MW/K   "
                  f"T_net = {heat_load.t_net:.1f}°C   (dual-slope v2)")
        else:
            print(f"    (single-slope fallback — nettab_slope_mw_per_k = 0)")
        print(f"    baseline_profile_mw: gns {heat_load.baseline_profile_mw.mean():.2f} "
              f"MW, min {heat_load.baseline_profile_mw.min():.2f}, "
              f"max {heat_load.baseline_profile_mw.max():.2f}")

        if args.data_source == "github":
            return load_external_data_github(
                cfg,
                heat_load=heat_load,
                dmi_area=args.dmi_area,
                dmi_temp_shortname=args.dmi_temp_shortname,
                price_zone=args.price_zone,
                eur_dkk=args.eur_dkk,
                with_balancing=args.with_balancing,
                repo_url=args.df_data_url,
                cache_dir=args.df_data_cache,
                force_refresh=args.force_refresh,
            )

        return load_external_data(
            cfg,
            heat_load=heat_load,
            dmi_area=args.dmi_area,
            dmi_temp_shortname=args.dmi_temp_shortname,
            price_zone=args.price_zone,
            eur_dkk=args.eur_dkk,
            cache_dir=args.cache_dir,
            force_refresh=args.force_refresh,
            with_balancing=args.with_balancing,
        )

    if args.data_path is not None:
        from src.data_loader import load_billund_data
        print(f"Indlæser Billund-data fra {args.data_path}...")
        return load_billund_data(cfg, args.data_path)

    print("Genererer dummy-data...")
    return generate_dummy_data(cfg)


def _apply_time_override(cfg, year: int | None,
                         start: str | None, end: str | None) -> None:
    """Override analyseperiode i cfg.time.

    Tre varianter:
      1. Ingen override           → cfg.time uændret (bruger YAML-værdier)
      2. --year YYYY              → hele kalenderåret
      3. --start X --end Y        → fra X til Y (inklusive)

    --year og --start/--end er mutuelt eksklusive; --start kræver --end.
    make_time_index og load_external_data bruger cfg.time direkte, så både
    tidsakse og API-kald følger automatisk med.
    """
    # Validér konflikter
    if year is not None and (start is not None or end is not None):
        raise ValueError(
            "--year kan ikke kombineres med --start eller --end. "
            "Brug enten --year YYYY eller (--start YYYY-MM-DD --end YYYY-MM-DD)."
        )
    if (start is None) != (end is None):
        raise ValueError("--start og --end skal bruges sammen (eller slet ikke).")

    if year is not None:
        cfg.time.start = f"{year}-01-01"
        cfg.time.end = f"{year}-12-31"
        print(f"  Override: analyseperiode = {year}-01-01..{year}-12-31")
        return

    if start is not None and end is not None:
        # Sanity: parse datoer og tjek rækkefølge
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        if end_ts <= start_ts:
            raise ValueError(f"--end ({end}) skal være efter --start ({start}).")
        cfg.time.start = start
        cfg.time.end = end
        print(f"  Override: analyseperiode = {start}..{end}")
        return

    # Ingen override — cfg.time uændret


def _apply_enable_disable(cfg, enable, disable):
    for name in enable:
        if name in cfg.units:
            cfg.units[name].enabled = True
            print(f"  Override: {name} ENABLED")
        elif name in cfg.storage:
            cfg.storage[name].enabled = True
            print(f"  Override: {name} (lager) ENABLED")
        else:
            raise KeyError(f"--enable {name}: hverken enhed eller lager")
    for name in disable:
        if name in cfg.units:
            cfg.units[name].enabled = False
            print(f"  Override: {name} DISABLED")
        elif name in cfg.storage:
            cfg.storage[name].enabled = False
            print(f"  Override: {name} (lager) DISABLED")
        else:
            raise KeyError(f"--disable {name}: hverken enhed eller lager")


def _print_data_summary(data):
    print(f"  {len(data.time)} timesteps  "
          f"[{data.time.values[0]} → {data.time.values[-1]}]")
    print(f"  Varmelast: min={float(data.heat_demand.min()):.1f}, "
          f"gns={float(data.heat_demand.mean()):.1f}, "
          f"max={float(data.heat_demand.max()):.1f} MW  "
          f"(årssum {float(data.heat_demand.sum())/1000:.1f} GWh)")
    # Dekomponering, hvis vi kører --external
    if "heat_gaf" in data.data_vars:
        print(f"    GAF (rumvarme):      {float(data.heat_gaf.sum())/1000:5.1f} GWh "
              f"(gns {float(data.heat_gaf.mean()):.2f} MW)")
        print(f"    Baseline (guf-navn): {float(data.heat_guf.sum())/1000:5.1f} GWh "
              f"(gns {float(data.heat_guf.mean()):.2f} MW)")
        print(f"    Nettab-tillæg:       {float(data.heat_nettab.sum())/1000:5.1f} GWh "
              f"(gns {float(data.heat_nettab.mean()):.2f} MW)")
    print(f"  Spot:      min={float(data.spot_price.min()):.0f}, "
          f"gns={float(data.spot_price.mean()):.0f}, "
          f"max={float(data.spot_price.max()):.0f} DKK/MWh")
    if "t_ambient" in data.data_vars:
        print(f"  Udetemp:   min={float(data.t_ambient.min()):.1f}, "
              f"gns={float(data.t_ambient.mean()):.1f}, "
              f"max={float(data.t_ambient.max()):.1f} °C")


def main():
    args = _parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --data-source github impliserer --external (vi har ingen mening om
    # at læse df-data uden synthesize-pipelinen aktiv).
    if args.data_source == "github" and not args.external:
        args.external = True

    print(f"Indlæser case: {args.case}")
    cfg = load_case(args.case, overrides=args.set_overrides)

    _apply_time_override(cfg, args.year, args.start, args.end)
    _apply_enable_disable(cfg, args.enable, args.disable)

    active_units = [u for u, unit in cfg.units.items() if unit.enabled]
    print(f"  Aktive enheder: {len(active_units)}/{len(cfg.units)} — "
          f"{', '.join(active_units)}")
    print(f"  Lagre:   {len(cfg.storage)}")
    for s_name, s in cfg.storage.items():
        print(f"    {s_name}: {s.volume_m3} m³ → "
              f"{s.e_max_mwh:.1f} MWh termisk kapacitet")

    print()
    data = _load_data(args, cfg)
    _print_data_summary(data)

    print("\nBygger model...")
    m = build_model(cfg, data)
    print(f"  Variable:  {m.nvars:,}")
    print(f"  Bindinger: {m.ncons:,}")

    print(f"\nLøser med {args.solver}...")
    result = solve_and_extract(m, cfg, solver=args.solver)

    print("\n=== KPI'er ===")
    kpi = kpi_summary(result, data, cfg)
    print(kpi.to_string(index=False))

    # Byg filnavn-stem fra kørselsparametre
    stem = _build_output_stem(args, cfg)

    # Månedsopdelt oversigt — printes og gemmes som CSV
    print("\n=== Månedsopdelt (GWh, °C, DKK/MWh) ===")
    monthly = seasonal_summary(result, data, cfg,
                               out_dir / f"{stem}_monthly.csv")
    print(monthly.to_string())

    kpi.to_csv(out_dir / f"{stem}_kpi.csv", index=False)
    result.to_netcdf(out_dir / f"{stem}_dispatch.nc")
    write_hourly_csv(result, data, cfg, out_dir / f"{stem}_hourly.csv")
    dispatch_plot(result, data, out_dir / f"{stem}_dispatch.png",
                  cfg=cfg, days=args.days)

    print(f"\nOutput i: {out_dir.absolute()}")
    print(f"Filnavn-stem: {stem}")


if __name__ == "__main__":
    main()
