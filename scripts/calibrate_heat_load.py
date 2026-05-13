"""
scripts/calibrate_heat_load.py
───────────────────────────────
Genfit `HeatLoadParams` (v2/v3 dual-slope-struktur) ved OLS mod målt
varmeproduktion ab værk og en valgt DMI-vejrstation. Skriver en YAML-fil
i samme format som `cases/heat_load_params_*.yaml` så resultatet kan
bruges direkte med `run_case.py --heat-params <fil>`.

Model:
    y(t) = gaf_slope · max(0, t_ref - t_ema(t)) · weekend_factor(t)
         + baseline[hour_of_day(t)]
         + nettab_slope · max(0, t_net - t_out(t))

Parametre estimeret:
  Fri    : gaf_slope, t_ref, nettab_slope, t_net, baseline_profile_mw[0..23]
  Fastsat: thermal_inertia_hours, weekly_dip  (CLI-flag)

Fitting:
  Ydre grid-search over (t_ref, t_net); indre lukket-form OLS for
  slopes + baseline. Valgfri fin-søgning omkring optimum (default: til).

Eksempler:
    # Standard refit mod fyn-temperatur, TI=48h (anbefalet default fra session 18)
    python scripts/calibrate_heat_load.py \\
        --dmi-area fyn \\
        --thermal-inertia 48 \\
        --output cases/heat_load_params_v3_fyn_ti48.yaml

    # Refit mod karup for EnergyPRO-harmonisering
    python scripts/calibrate_heat_load.py \\
        --dmi-area karup \\
        --thermal-inertia 48 \\
        --output cases/heat_load_params_v3_karup_ti48.yaml \\
        --label heat_load_params_v3_karup_ti48

    # Grid-search også over thermal_inertia for at finde optimum
    python scripts/calibrate_heat_load.py \\
        --dmi-area karup \\
        --thermal-inertia-grid 24,36,48,72,96 \\
        --output cases/heat_load_params_v4_karup_optimal.yaml

    # Anden måling (fx en ny SRO-eksport)
    python scripts/calibrate_heat_load.py \\
        --measured data/billund_abvaerk_2026.csv \\
        --measured-col heat_mw_total \\
        --dmi-area fyn \\
        --output cases/heat_load_params_v3_fyn_2026.yaml
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yaml

# Tillader at scriptet køres fra repo-root: `python scripts/calibrate_heat_load.py`
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_case
from src.data_loader import HeatLoadParams, synthesize_heat_load


# ─── Hjælpefunktioner ───────────────────────────────────────────────────────

def load_measured(path: Path, col: str) -> pd.Series:
    """Indlæs målt varmebehov-tidsserie. Auto-detect tidskolonne."""
    df = pd.read_csv(path)
    time_candidates = ["timestamp", "time", "datetime", "hour_utc", "hour_dk"]
    tcol = next((c for c in time_candidates if c in df.columns), None)
    if tcol is None:
        raise ValueError(f"Kunne ikke finde tidskolonne i {path}. "
                         f"Prøvede: {time_candidates}")
    if col not in df.columns:
        raise ValueError(f"Kolonnen '{col}' findes ikke i {path}. "
                         f"Tilgængelige: {list(df.columns)}")
    df[tcol] = pd.to_datetime(df[tcol])
    if df[tcol].dt.tz is not None:
        df[tcol] = df[tcol].dt.tz_convert("UTC").dt.tz_localize(None)
    return df.set_index(tcol)[col].sort_index()


def load_temperature(case_path: Path, dmi_area: str, start: str, end: str,
                     data_source: str, cache_dir: str) -> pd.Series:
    """Hent t_ambient fra valgt vejrstation via data_loader (api eller github)."""
    cfg = load_case(case_path)
    cfg.time.start = start
    cfg.time.end = end
    hl_dummy = HeatLoadParams.from_yaml_dict({
        "gaf_mw_per_k": 1.0, "t_ref": 15.0,
        "thermal_inertia_hours": 24, "weekly_dip": 0.02,
        "baseline_profile_mw": [6.0] * 24,
    })
    if data_source == "github":
        from src.data_loader_github import load_external_data_github
        ds = load_external_data_github(cfg, heat_load=hl_dummy,
                                        dmi_area=dmi_area, cache_dir=cache_dir)
    else:
        from src.data_loader import load_external_data
        ds = load_external_data(cfg, heat_load=hl_dummy, dmi_area=dmi_area)
    return pd.Series(ds["t_ambient"].values,
                     index=pd.to_datetime(ds["time"].values),
                     name=f"t_{dmi_area}")


# ─── Kerne-fit ──────────────────────────────────────────────────────────────

def fit_at(y: pd.Series, t: pd.Series, thermal_inertia: int, weekly_dip: float,
           t_ref: float, t_net: float):
    """Lukket-form OLS for slopes + 24-element baseline givet (t_ref, t_net)."""
    t_ema = t.ewm(span=thermal_inertia, adjust=False).mean()
    wf = np.where(y.index.dayofweek >= 5, 1.0 - weekly_dip, 1.0)
    H = np.zeros((len(y), 24))
    H[np.arange(len(y)), y.index.hour] = 1.0
    X = np.column_stack([
        np.maximum(0.0, t_ref - t_ema.values) * wf,
        np.maximum(0.0, t_net - t.values),
        H,
    ])
    beta, *_ = np.linalg.lstsq(X, y.values, rcond=None)
    resid = y.values - X @ beta
    ss_tot = np.sum((y.values - y.values.mean()) ** 2)
    r2 = 1.0 - np.sum(resid ** 2) / ss_tot
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    return beta, r2, rmse


def grid_search(y: pd.Series, t: pd.Series, thermal_inertia: int,
                weekly_dip: float, t_ref_range: tuple, t_net_range: tuple,
                step: float = 0.5, fine: bool = True, verbose: bool = True):
    """Ydre grid-search over (t_ref, t_net). Returnerer bedste fit."""
    t_ref_min, t_ref_max = t_ref_range
    t_net_min, t_net_max = t_net_range

    if verbose:
        print(f"  Grid-search: t_ref ∈ [{t_ref_min}, {t_ref_max}], "
              f"t_net ∈ [{t_net_min}, {t_net_max}], step={step}")

    best = (-np.inf, None, None, None, None)  # (r2, t_ref, t_net, rmse, beta)
    for t_ref in np.arange(t_ref_min, t_ref_max + 1e-9, step):
        for t_net in np.arange(t_net_min, min(t_net_max, t_ref - 0.01) + 1e-9, step):
            beta, r2, rmse = fit_at(y, t, thermal_inertia, weekly_dip,
                                     float(t_ref), float(t_net))
            if r2 > best[0]:
                best = (r2, float(t_ref), float(t_net), rmse, beta)

    if fine:
        r2_c, tr_c, tn_c, _, _ = best
        for t_ref in np.arange(tr_c - step + 0.05, tr_c + step, 0.05):
            for t_net in np.arange(tn_c - step + 0.05, tn_c + step, 0.05):
                if t_net >= t_ref:
                    continue
                beta, r2, rmse = fit_at(y, t, thermal_inertia, weekly_dip,
                                         float(t_ref), float(t_net))
                if r2 > best[0]:
                    best = (r2, round(float(t_ref), 2),
                            round(float(t_net), 2), rmse, beta)

    return best  # (r2, t_ref, t_net, rmse, beta)


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--case", default=str(REPO_ROOT / "cases/billund_baseline.yaml"),
                   help="Case-YAML der angiver tidszone og lokation (default: billund_baseline.yaml)")
    p.add_argument("--measured", default=str(REPO_ROOT / "data/billund_abvaerk_hourly.csv"),
                   help="CSV med målt varmebehov [MW] (default: data/billund_abvaerk_hourly.csv)")
    p.add_argument("--measured-col", default="heat_mw_abvaerk",
                   help="Kolonnenavn for målt varmebehov (default: heat_mw_abvaerk)")
    p.add_argument("--dmi-area", default="fyn",
                   help="DMI-vejrstation (default: fyn). Brug 'karup' for ægte Karup-data efter session 18-fix.")
    p.add_argument("--data-source", choices=["api", "github"], default="github",
                   help="Vejrdata-kilde (default: github via df-data)")
    p.add_argument("--cache-dir", default="data/df-data",
                   help="Lokal df-data cache når --data-source=github")
    p.add_argument("--thermal-inertia", type=int, default=48,
                   help="Termisk inerti i timer (EMA span). Session 18 fandt 48h optimalt. Default: 48")
    p.add_argument("--thermal-inertia-grid", default=None,
                   help="Komma-separeret liste fx '24,36,48,72'. Overskriver --thermal-inertia "
                        "og vælger den TI der maksimerer R².")
    p.add_argument("--weekly-dip", type=float, default=0.02,
                   help="GAF-reduktion i weekender (default: 0.02 = 2%%)")
    p.add_argument("--t-ref-range", default="12.0,18.0",
                   help="Min,max for t_ref grid (default: 12.0,18.0)")
    p.add_argument("--t-net-range", default="7.0,16.0",
                   help="Min,max for t_net grid (default: 7.0,16.0)")
    p.add_argument("--grid-step", type=float, default=0.5,
                   help="Trinstørrelse for ydre grid (default: 0.5 °C)")
    p.add_argument("--no-fine", action="store_true",
                   help="Spring fin-søgning over (hurtigere, mindre præcis)")
    p.add_argument("--start", default=None,
                   help="Periode-start YYYY-MM-DD (default: auto fra målt-CSV)")
    p.add_argument("--end", default=None,
                   help="Periode-slut YYYY-MM-DD (default: auto fra målt-CSV)")
    p.add_argument("--output", "-o", required=True,
                   help="Sti til output-YAML (fx cases/heat_load_params_v3_fyn_ti48.yaml)")
    p.add_argument("--label", default=None,
                   help="YAML top-level key (default: udledes fra output-filnavn)")
    p.add_argument("--note", default=None,
                   help="Fritekst til _source-feltet i output-yaml")
    args = p.parse_args()

    case_path = Path(args.case).resolve()
    meas_path = Path(args.measured).resolve()
    out_path = Path(args.output).resolve()

    # ── 1. Indlæs målt data ────────────────────────────────────────────────
    print(f"Læser målt varmebehov fra {meas_path}")
    y_full = load_measured(meas_path, args.measured_col)
    print(f"  Periode: {y_full.index.min()} → {y_full.index.max()}")
    print(f"  Total rækker: {len(y_full)}  NaN: {y_full.isna().sum()}")

    # Periode-auto eller manuel
    start = args.start or y_full.index.min().strftime("%Y-%m-%d")
    end = args.end or (y_full.index.max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # ── 2. Hent temperatur ─────────────────────────────────────────────────
    print(f"\nHenter temperatur fra dmi_area={args.dmi_area} ({args.data_source})")
    t_full = load_temperature(case_path, args.dmi_area, start, end,
                               args.data_source, args.cache_dir)
    print(f"  T_gns={t_full.mean():.2f}°C  min={t_full.min():.2f}  max={t_full.max():.2f}")

    # ── 3. Align ──────────────────────────────────────────────────────────
    common = y_full.index.intersection(t_full.index)
    y = y_full.loc[common].dropna()
    t = t_full.loc[y.index]
    print(f"\nFælles timer efter NaN-drop: {len(y)} "
          f"({y.index.min()} → {y.index.max()})")

    # ── 4. Vælg thermal_inertia ───────────────────────────────────────────
    t_ref_range = tuple(float(x) for x in args.t_ref_range.split(","))
    t_net_range = tuple(float(x) for x in args.t_net_range.split(","))

    if args.thermal_inertia_grid:
        ti_candidates = [int(x) for x in args.thermal_inertia_grid.split(",")]
        print(f"\nTI grid-search: {ti_candidates}")
        ti_results = []
        for ti in ti_candidates:
            r2, tr, tn, rmse, beta = grid_search(
                y, t, ti, args.weekly_dip, t_ref_range, t_net_range,
                args.grid_step, fine=not args.no_fine, verbose=False)
            ti_results.append((ti, r2, tr, tn, rmse, beta))
            print(f"  TI={ti}h:  R²={r2:.4f}  RMSE={rmse:.3f}  "
                  f"t_ref={tr:.2f}  t_net={tn:.2f}")
        # Vælg bedste
        best_ti = max(ti_results, key=lambda x: x[1])
        thermal_inertia, r2, t_ref, t_net, rmse, beta = best_ti
        print(f"\nValgt: TI={thermal_inertia}h (R²={r2:.4f})")
    else:
        thermal_inertia = args.thermal_inertia
        print(f"\nKalibrerer med thermal_inertia={thermal_inertia}h "
              f"(brug --thermal-inertia-grid for at søge)")
        r2, t_ref, t_net, rmse, beta = grid_search(
            y, t, thermal_inertia, args.weekly_dip, t_ref_range, t_net_range,
            args.grid_step, fine=not args.no_fine)

    gaf_slope = float(beta[0])
    nettab_slope = float(beta[1])
    baseline = beta[2:]

    # ── 5. Verifikation via synthesize_heat_load ──────────────────────────
    params_obj = HeatLoadParams(
        gaf_mw_per_k=gaf_slope,
        t_ref=t_ref,
        thermal_inertia_hours=thermal_inertia,
        nettab_slope_mw_per_k=nettab_slope,
        t_net=t_net,
        baseline_profile_mw=baseline,
        weekly_dip=args.weekly_dip,
    )
    synth = synthesize_heat_load(t, params_obj)
    y_synth = synth["total"]
    resid = y.values - y_synth.values
    rmse_verify = float(np.sqrt(np.mean(resid ** 2)))
    bias_pct = (y_synth.sum() - y.sum()) / y.sum() * 100

    print(f"\n=== Endelig fit ===")
    print(f"  gaf_mw_per_k          = {gaf_slope:.4f}")
    print(f"  t_ref                 = {t_ref:.2f}")
    print(f"  thermal_inertia_hours = {thermal_inertia}")
    print(f"  nettab_slope_mw_per_k = {nettab_slope:.4f}")
    print(f"  t_net                 = {t_net:.2f}")
    print(f"  weekly_dip            = {args.weekly_dip}")
    print(f"  R²                    = {r2:.4f}")
    print(f"  RMSE                  = {rmse:.3f} MW  (verifikation: {rmse_verify:.3f})")
    print(f"  Energibalance-bias    = {bias_pct:+.2f}% (mål: ≈0%)")

    # ── 6. Skriv YAML ──────────────────────────────────────────────────────
    label = args.label or out_path.stem  # default fra filnavn
    note = args.note or (
        f"OLS mod {meas_path.name} ({y.index.min().date()} → "
        f"{y.index.max().date()}) med {args.dmi_area}-temperatur"
    )

    payload = {label: {
        "gaf_mw_per_k": round(gaf_slope, 4),
        "t_ref": round(t_ref, 2),
        "thermal_inertia_hours": thermal_inertia,
        "nettab_slope_mw_per_k": round(nettab_slope, 4),
        "t_net": round(t_net, 2),
        "baseline_profile_mw": [round(float(b), 3) for b in baseline],
        "weekly_dip": args.weekly_dip,
        "_source": note,
        "_dmi_area": args.dmi_area,
        "_calibrated": datetime.now().strftime("%Y-%m-%d"),
        "_fit_r2": round(r2, 4),
        "_fit_rmse": round(rmse, 3),
        "_n_observations": int(len(y)),
    }}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        yaml.dump(payload, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)
    print(f"\nSkrevet: {out_path}")
    print(f"\nKlar til brug: python run_case.py <case> --heat-params {out_path}")


if __name__ == "__main__":
    main()
