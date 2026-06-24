"""
scripts/capture_rate.py — capture-rate (generaliseret): model (perfekt foresight)
mod realiseret afregning (facit), vilkårligt vindue/facit. FORB Op.

Generalisering af scripts/capture_rate_q1_2026.py (som var hardkodet til Q1 2026).
Loader gemt dispatch (.nc) + reloader data (av_payment / clear_fraction / kap-pris
pr. marked) UDEN gen-solve. Aggregerer pr. måned og marked mod facit-CSV.

Kør:
    .venv/bin/python scripts/capture_rate.py <dispatch.nc> \
        --case cases/billund_sporB_H2_2025.yaml \
        --facit noter/billund_balance_facit_H2_2025_tidy.csv \
        --start 2025-07-01 --end 2025-12-31

--window kan begrænse facit-sammenligningen til et delvindue (fx out-of-sample
mar–apr): --window 2026.03,2026.04
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_case
from src.data_loader import load_heat_load_params
from src.data_loader_github import load_external_data_github
from src.balancing import MARKETS


def load_facit(path: str) -> pd.DataFrame:
    f = pd.read_csv(path, dtype={"maaned": str})
    f = f[(f.side == "FORB") & (f.retning == "Op")].copy()
    akt = (f[f.produkt == "akt"]
           .groupby(["maaned", "marked"])[["dkk", "mwh"]].sum()
           .rename(columns={"dkk": "fac_akt_dkk", "mwh": "fac_akt_mwh"}))
    kap = (f[f.produkt.isin(["kap", "kap_ekstra"])]
           .groupby(["maaned", "marked"])[["dkk", "mwh"]].sum()
           .rename(columns={"dkk": "fac_kap_dkk", "mwh": "fac_kap_mwh"}))
    return akt.join(kap, how="outer").reset_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dispatch", help="Sti til dispatch .nc")
    ap.add_argument("--case", required=True)
    ap.add_argument("--facit", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--window", default=None,
                    help="kommasepareret liste af måneder (fx 2026.03,2026.04) — "
                         "begræns sammenligning til dette delvindue")
    args = ap.parse_args()

    nc = args.dispatch
    if not Path(nc).exists():
        raise SystemExit(f"Dispatch .nc ikke fundet: {nc}")
    print(f"Loader dispatch: {nc}  (case: {args.case})")
    result = xr.open_dataset(nc)

    cfg = load_case(args.case)
    cfg.time.start = f"{args.start}T00:00:00Z"
    cfg.time.end = f"{args.end}T23:00:00Z"
    heat_load = load_heat_load_params(args.case)
    print("Reloader data (uden solve)...")
    data = load_external_data_github(cfg, heat_load=heat_load, with_balancing=True)
    data = data.reindex(time=result.time.values)

    time = pd.DatetimeIndex(result.time.values)
    hours_per_month = pd.Series(1, index=time).groupby(time.to_period("M")).size()

    rows = []
    for mk in MARKETS:
        if mk.cap_price_key not in data.data_vars:
            continue
        price_cap = data[mk.cap_price_key]
        av = data[mk.act_value_key]
        pay = data[mk.act_payment_key]
        clear = data[mk.clear_fraction_key]

        r_total = None
        prefix = f"{mk.var_prefix}_"
        for v in result.data_vars:
            if str(v).startswith(prefix):
                r_total = result[v] if r_total is None else (r_total + result[v])
        if r_total is None:
            continue

        per = pd.DataFrame({
            "maaned": time.to_period("M").astype(str).str.replace("-", ".", regex=False),
            "r_mw": r_total.values,
            "cap_dkk": (price_cap * r_total).values,
            "gross_dkk": (av * r_total).values,
            "net_dkk": (pay * r_total).values,
            "clear": clear.values,
        })
        agg = per.groupby("maaned").agg(
            mod_r_mw_snit=("r_mw", "mean"),
            mod_cap_dkk=("cap_dkk", "sum"),
            mod_gross_dkk=("gross_dkk", "sum"),
            mod_net_dkk=("net_dkk", "sum"),
            mod_clear_mean=("clear", "mean"),
        ).reset_index()
        agg["marked"] = mk.label
        rows.append(agg)

    model = pd.concat(rows, ignore_index=True)
    facit = load_facit(args.facit)
    m = model.merge(facit, on=["maaned", "marked"], how="left")

    if args.window:
        keep = [w.strip() for w in args.window.split(",")]
        m = m[m.maaned.isin(keep)].copy()
        print(f"\n[delvindue: {keep}]")

    m["capture_net_pct"] = m["fac_akt_dkk"] / m["mod_net_dkk"] * 100

    pd.set_option("display.width", 200)
    print("\n" + "=" * 92)
    print("CAPTURE-RATE — aktivering (EAM): facit vs model (perfekt foresight)")
    print("=" * 92)
    print(m[["maaned", "marked", "mod_net_dkk", "mod_gross_dkk", "fac_akt_dkk",
             "capture_net_pct"]].to_string(index=False, float_format=lambda x: f"{x:,.0f}"))

    print("\nReservation (kapacitet) — model MW-snit vs facit MW-snit + kap-DKK:")
    m["fac_kap_mw_snit"] = m.apply(
        lambda r: r["fac_kap_mwh"] / hours_per_month.get(
            pd.Period(r["maaned"].replace(".", "-"), "M"), np.nan), axis=1)
    print(m[["maaned", "marked", "mod_r_mw_snit", "fac_kap_mw_snit",
             "mod_cap_dkk", "fac_kap_dkk"]].to_string(
        index=False, float_format=lambda x: f"{x:,.2f}"))

    print("\n" + "=" * 92)
    print("SAMLET (vindue) pr. marked + total")
    print("=" * 92)
    summ = m.groupby("marked").agg(
        mod_net_dkk=("mod_net_dkk", "sum"),
        mod_gross_dkk=("mod_gross_dkk", "sum"),
        mod_cap_dkk=("mod_cap_dkk", "sum"),
        fac_akt_dkk=("fac_akt_dkk", "sum"),
        fac_kap_dkk=("fac_kap_dkk", "sum"),
    ).reset_index()
    tot = summ.drop(columns="marked").sum()
    tot["marked"] = "TOTAL"
    summ = pd.concat([summ, pd.DataFrame([tot])], ignore_index=True)
    summ["akt_capture_pct"] = summ["fac_akt_dkk"] / summ["mod_net_dkk"] * 100
    summ["mod_balance"] = summ["mod_cap_dkk"] + summ["mod_net_dkk"]
    summ["fac_balance"] = summ["fac_kap_dkk"] + summ["fac_akt_dkk"]
    summ["bal_mod/fac_pct"] = summ["mod_balance"] / summ["fac_balance"] * 100
    print(summ.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))

    out = Path(nc).parent / "capture_rate_detail.csv"
    m.to_csv(out, index=False)
    print(f"\nGemt: {out}")


if __name__ == "__main__":
    main()
