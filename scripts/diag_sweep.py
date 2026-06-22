"""
scripts/diag_sweep.py — Balance-diagnostik (Diagnose 1 + 3) for billund_2025.

KUN MÅLING/RAPPORTERING. Ingen ændring af dispatch-logik. Objektivet bruger
uændret brutto-av; her attribueres total_mw-cap'ens bidrag som en kurve.

Data (priser, av(t), clear_fraction, av_payment) er UAFHÆNGIGE af cap'en, så
de loades én gang og genbruges. Kun optimeringen genløses pr. cap.

Kør:
    .venv/bin/python scripts/diag_sweep.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_case
from src.data_loader import load_heat_load_params
from src.data_loader_github import load_external_data_github
from src.model import build_model
from src.solve import solve_and_extract
from src.reporting import kpi_summary
from src.balancing import summarize_reserves, MARKETS

CASE = "cases/billund_2025.yaml"
CAPS = [8.65, 13.0, 17.3, 25.0, 33.0]      # MW (combined aFRR+mFRR, alle enheder)
CAP_LABELS = {
    8.65: "prækval (1 pulje)",
    17.3: "prækval (begge mkd.)",
    33.0: "nuværende",
}
ELKEDLER = ["elkedel_ny", "elkedel_gl"]


def _dist(series: pd.Series, name: str) -> dict:
    s = series.astype(float)
    n = len(s)
    return {
        "navn": name,
        "middel": float(s.mean()),
        "median": float(s.median()),
        "p90": float(s.quantile(0.90)),
        "p99": float(s.quantile(0.99)),
        "max": float(s.max()),
        "andel>0": float((s > 1e-9).mean()),
        "andel>0.5": float((s > 0.5).mean()),
        "andel>0.9": float((s > 0.9).mean()),
        "n": n,
    }


def main():
    print("Loader case + data (én gang — cap-uafhængigt)...")
    cfg = load_case(CASE)
    heat_load = load_heat_load_params(CASE)
    data = load_external_data_github(
        cfg, heat_load=heat_load, with_balancing=True,
    )

    # ---------------------------------------------------------------
    # DIAGNOSE 3a — clear_fraction- og av-fordelinger (cap-uafhængige)
    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("DIAGNOSE 3 — aktiverings-realiserbarhed (prisbaseret, cap-uafhængig)")
    print("=" * 78)
    diag3_rows = []
    for mk in MARKETS:
        cf = pd.Series(data[mk.clear_fraction_key].values)
        diag3_rows.append({**_dist(cf, f"{mk.label} clear_fraction"), "enhed": "[0,1]"})
    cf_df = pd.DataFrame(diag3_rows)
    print("\nclear_fraction-fordeling (andel af timen buddet clearer):")
    print(cf_df[["navn", "middel", "median", "p90", "p99", "max",
                 "andel>0", "andel>0.5", "andel>0.9"]].to_string(
        index=False, float_format=lambda x: f"{x:.3f}"))

    av_rows = []
    for mk in MARKETS:
        av = pd.Series(data[mk.act_value_key].values)         # brutto DKK/MW/h
        pay = pd.Series(data[mk.act_payment_key].values)      # netto DKK/MW/h
        av_rows.append({**_dist(av, f"{mk.label} av (brutto)")})
        av_rows.append({**_dist(pay, f"{mk.label} av_payment (netto)")})
    av_df = pd.DataFrame(av_rows)
    print("\nav(t)-fordeling (DKK pr. reserveret MW pr. time):")
    print(av_df[["navn", "middel", "median", "p90", "p99", "max",
                 "andel>0"]].to_string(
        index=False, float_format=lambda x: f"{x:.1f}"))

    # ---------------------------------------------------------------
    # DIAGNOSE 1 — cap-sweep
    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("DIAGNOSE 1 — cap-sweep (total_mw, attribuering)")
    print("=" * 78)

    sweep_rows = []
    concentration = {}   # cap -> per-market top-1% andel af Σ av_payment·r
    for cap in CAPS:
        cfg.ancillary_caps.total_mw = float(cap)
        print(f"\n--- total_mw = {cap} MW ---")
        m = build_model(cfg, data)
        result = solve_and_extract(m, cfg, solver="highs")
        kpi = kpi_summary(result, data, cfg)
        summ = summarize_reserves(result, data)

        cap_dkk = net_dkk = off_dkk = mwh_bid = 0.0
        vp_mwh = vp_net = 0.0
        per_market_conc = {}
        for mk in MARKETS:
            msum = summ.get(mk.label, {})
            # total reserveret MW pr. time for dette marked (sum over enheder)
            r_total = None
            for unit, entry in msum.items():
                cap_dkk += entry.get("capacity_revenue_dkk", 0.0)
                net_dkk += entry.get("activation_payment_dkk", 0.0)
                off_dkk += entry.get("consumption_offset_dkk", 0.0)
                mwh_bid += entry.get("mwh_bid_year", 0.0)
                if unit == "vp_luft_vand":
                    vp_mwh += entry.get("mwh_bid_year", 0.0)
                    vp_net += (entry.get("capacity_revenue_dkk", 0.0)
                               + entry.get("activation_payment_dkk", 0.0))
                rv = result[f"{mk.var_prefix}_{unit}"]
                r_total = rv if r_total is None else (r_total + rv)
            # top-1% koncentration af Σ av_payment·r for dette marked
            if r_total is not None:
                pay = data[mk.act_payment_key]
                hourly_rev = pd.Series((pay * r_total).values).sort_values(
                    ascending=False)
                tot = hourly_rev.sum()
                k = max(1, int(round(0.01 * len(hourly_rev))))
                per_market_conc[mk.label] = (
                    float(hourly_rev.iloc[:k].sum() / tot) if tot > 0 else 0.0)
        concentration[cap] = per_market_conc

        net_bal = cap_dkk + net_dkk
        gross_bal = cap_dkk + net_dkk + off_dkk
        total_prod = float(kpi["production_mwh"].sum())
        flh = {}
        for ek in ELKEDLER:
            row = kpi[kpi["unit"] == ek]
            if len(row):
                prod = float(row["production_mwh"].iloc[0])
                pmax = float(row["p_max_mw"].iloc[0])
                flh[ek] = prod / pmax if pmax > 0 else 0.0
        sweep_rows.append({
            "cap_mw": cap,
            "label": CAP_LABELS.get(cap, ""),
            "bal_netto_mio": net_bal / 1e6,
            "bal_brutto_mio": gross_bal / 1e6,
            "kapacitet_mio": cap_dkk / 1e6,
            "akt_netto_mio": net_dkk / 1e6,
            "forbrugsmodregn_mio": off_dkk / 1e6,
            "reserve_mwh": mwh_bid,
            "vp_andel_mwh_pct": (vp_mwh / mwh_bid * 100) if mwh_bid else 0.0,
            "vp_bal_netto_mio": vp_net / 1e6,
            "prod_mwh": total_prod,
            "flh_elkedel_ny": flh.get("elkedel_ny", 0.0),
            "flh_elkedel_gl": flh.get("elkedel_gl", 0.0),
        })

    sw = pd.DataFrame(sweep_rows)
    print("\n" + "=" * 78)
    print("DIAGNOSE 1 — SAMLET TABEL")
    print("=" * 78)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    print("\nBalanceindtægt + split (mio DKK/år):")
    print(sw[["cap_mw", "label", "bal_netto_mio", "bal_brutto_mio",
              "kapacitet_mio", "akt_netto_mio", "forbrugsmodregn_mio"]].to_string(
        index=False, float_format=lambda x: f"{x:.2f}"))
    print("\nVP-andel, produktion, elkedel-fuldlasttimer:")
    print(sw[["cap_mw", "reserve_mwh", "vp_andel_mwh_pct", "vp_bal_netto_mio",
              "prod_mwh", "flh_elkedel_ny", "flh_elkedel_gl"]].to_string(
        index=False, float_format=lambda x: f"{x:,.1f}"))

    print("\nTop-1%-timers andel af Σ av_payment·r (indtægtskoncentration):")
    for cap in CAPS:
        c = concentration[cap]
        parts = ", ".join(f"{lbl}={v*100:.1f}%" for lbl, v in c.items())
        print(f"  total_mw={cap:>5}: {parts}")

    out = Path("output/diag_ref/diag1_sweep.csv")
    sw.to_csv(out, index=False)
    cf_df.to_csv("output/diag_ref/diag3_clear_fraction.csv", index=False)
    av_df.to_csv("output/diag_ref/diag3_av.csv", index=False)
    print(f"\nGemt: {out} + diag3_*.csv")


if __name__ == "__main__":
    main()
