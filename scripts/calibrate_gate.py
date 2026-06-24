"""
scripts/calibrate_gate.py — rekalibrér Spor B reservation_gate (driven) mod facit.

Under driven-gaten er modelleret reservation pr. time EKSOGEN:
    Σ_i r_m[t] == B_m   hvis CM_m(t) ≥ τ_m   ellers 0
(capped af footroom, som først bindes i det fulde solve). Reservations-VOLUMEN
afhænger derfor kun af CM-serien + (τ_m, B_m) — den kan kalibreres analytisk fra
day-ahead-kapacitetsprisen uden at løse MILP'en.

For hvert marked m fittes (τ_m, B_m) så modelleret MÅNEDLIG reservation
(MW-snit) matcher facit pr. måned:
    model_m(måned) = B_m · f_m(måned),  f_m = andel timer i måneden med CM_m ≥ τ_m
    facit_m(måned) = realiseret kap_MW_snit (FORB, Op)
Givet τ vælges B_m som timevægtet mindste-kvadraters-løsning; τ vælges på et grid
så månedlig RMSE minimeres. Footroom kan kun SÆNKE den realiserede reservation —
det fulde solve (run_case + capture_rate.py) afslører om/hvor den binder.

Kør:
    .venv/bin/python scripts/calibrate_gate.py \
        --case cases/billund_sporB_H2_2025.yaml \
        --facit noter/billund_balance_facit_H2_2025_tidy.csv \
        --start 2025-07-01 --end 2025-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_case
from src.data_loader import load_heat_load_params
from src.data_loader_github import load_external_data_github
from src.balancing import MARKETS


def facit_monthly_reservation(facit_path: str) -> pd.DataFrame:
    """Facit reservation (kap+kap_ekstra, FORB Op) pr. måned/marked → kap_MW_snit.

    Returnerer DataFrame indekseret (maaned, marked) med kolonner mwh, hours, mw_snit.
    """
    f = pd.read_csv(facit_path, dtype={"maaned": str})
    f = f[(f.side == "FORB") & (f.retning == "Op")
          & (f.produkt.isin(["kap", "kap_ekstra"]))].copy()
    g = f.groupby(["maaned", "marked"])["mwh"].sum().rename("mwh").reset_index()
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--facit", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--tau-max", type=float, default=2000.0,
                    help="øvre tærskel-grid (DKK/MW/h)")
    ap.add_argument("--tau-step", type=float, default=5.0)
    ap.add_argument("--b-max", type=float, default=None,
                    help="fysisk øvre blok-grænse [MW]; default = ancillary_caps.total_mw. "
                         "Forhindrer degenererede fit (lille åbnings-andel × kæmpe blok).")
    args = ap.parse_args()

    cfg = load_case(args.case)
    cfg.time.start = f"{args.start}T00:00:00Z"
    cfg.time.end = f"{args.end}T23:00:00Z"
    heat_load = load_heat_load_params(args.case)
    print(f"Loader data {args.start}..{args.end} (CM-serier, ingen solve)...")
    data = load_external_data_github(cfg, heat_load=heat_load, with_balancing=True)

    time = pd.DatetimeIndex(data.time.values)
    maaned = time.to_period("M").astype(str).str.replace("-", ".", regex=False)
    months = pd.Index(sorted(pd.unique(maaned)))
    hours_per_month = pd.Series(1, index=maaned).groupby(level=0).size().reindex(months)

    facit = facit_monthly_reservation(args.facit)

    cap = cfg.ancillary_caps.total_mw if cfg.ancillary_caps else None
    b_max = args.b_max if args.b_max is not None else (cap if cap else np.inf)
    print(f"Fysisk blok-grænse b_max = {b_max} MW (block_mw kan ikke overstige cap/footroom)")

    tau_grid = np.arange(0.0, args.tau_max + args.tau_step, args.tau_step)

    print("\n" + "=" * 92)
    print("KALIBRERING — driven CM-gate mod facit månedlig reservation (MW-snit)")
    print("=" * 92)

    results = {}
    for mk in MARKETS:
        if mk.cap_price_key not in data.data_vars:
            print(f"\n{mk.label}: ingen CM-data ({mk.cap_price_key}) — springes over")
            continue
        cm = pd.Series(data[mk.cap_price_key].values, index=maaned)

        # facit MW-snit pr. måned for dette marked
        fac = (facit[facit.marked == mk.label]
               .set_index("maaned")["mwh"].reindex(months).fillna(0.0))
        fac_mw = fac / hours_per_month                     # MW-snit pr. måned
        h = hours_per_month.values.astype(float)
        g = fac_mw.values.astype(float)                    # mål pr. måned

        best = None
        for tau in tau_grid:
            # andel timer pr. måned med CM ≥ tau
            openf = (cm >= tau).groupby(level=0).mean().reindex(months).fillna(0.0)
            f = openf.values.astype(float)
            denom = float((h * f * f).sum())
            if denom <= 1e-12:
                continue                                   # gate aldrig åben
            B = float((h * f * g).sum() / denom)           # timevægtet LS
            B = float(np.clip(B, 0.0, b_max))              # fysisk blok-grænse
            model = B * f
            rmse = float(np.sqrt((h * (model - g) ** 2).sum() / h.sum()))
            # korrelation mellem åbningsfrekvens og facit (form-match)
            if f.std() > 1e-9 and g.std() > 1e-9:
                corr = float(np.corrcoef(f, g)[0, 1])
            else:
                corr = float("nan")
            if best is None or rmse < best["rmse"]:
                best = {"tau": float(tau), "B": B, "rmse": rmse, "corr": corr,
                        "openf": openf, "model": model}

        results[mk.label] = best
        print(f"\n--- {mk.label} ---")
        print(f"  Bedste fit: τ = {best['tau']:.0f} DKK/MW/h, "
              f"B = {best['B']:.2f} MW  (månedlig RMSE = {best['rmse']:.3f} MW, "
              f"form-korr åben↔facit = {best['corr']:.2f})")
        tbl = pd.DataFrame({
            "facit_MW": g,
            "gate_åben%": best["openf"].values * 100,
            "model_MW": best["model"],
        }, index=months)
        tbl["afvig_MW"] = tbl["model_MW"] - tbl["facit_MW"]
        print(tbl.to_string(float_format=lambda x: f"{x:.2f}"))

    # Forslag til YAML
    print("\n" + "=" * 92)
    print("FORSLAG TIL reservation_gate (indsæt i casen):")
    print("=" * 92)
    for label, r in results.items():
        if r is None:
            continue
        key = label.lower()
        share = f"{r['B']/cap*100:.1f}% af cap({cap:.0f})" if cap else "n/a"
        print(f"  {key}: {{ cm_threshold_dkk_mw_h: {r['tau']:.0f}, "
              f"block_mw: {r['B']:.2f} }}   # block = {share}")

    return results


if __name__ == "__main__":
    main()
