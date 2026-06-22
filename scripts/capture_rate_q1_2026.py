"""
scripts/capture_rate_q1_2026.py — capture-rate: model (perfekt foresight) mod
Billunds realiserede afregning (facit), Q1 2026, Forbrugssiden, retning Op.

Loader den gemte dispatch (.nc) + reloader data (av_payment / clear_fraction /
kapacitetspris pr. marked) UDEN at gen-solve. Aggregerer pr. måned og marked og
sammenligner mod noter/billund_balance_facit_Q1_2026_tidy.csv.

capture-rate = realiseret aktiveringsindtægt / modelleret (perfekt foresight),
pr. marked og samlet — den empiriske haircut.

Kør:
    .venv/bin/python scripts/capture_rate_q1_2026.py <dispatch.nc>
"""
from __future__ import annotations

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

CASE = "cases/billund_backtest_jan_apr_2026.yaml"
FACIT = "noter/billund_balance_facit_Q1_2026_tidy.csv"
START, END = "2026-01-01", "2026-04-30"


def load_facit() -> pd.DataFrame:
    f = pd.read_csv(FACIT, dtype={"maaned": str})
    f = f[(f.side == "FORB") & (f.retning == "Op")].copy()
    # akt = EAM (aktivering); kap+kap_ekstra = CM (reservation)
    akt = (f[f.produkt == "akt"]
           .groupby(["maaned", "marked"])[["dkk", "mwh"]].sum()
           .rename(columns={"dkk": "fac_akt_dkk", "mwh": "fac_akt_mwh"}))
    kap = (f[f.produkt.isin(["kap", "kap_ekstra"])]
           .groupby(["maaned", "marked"])[["dkk", "mwh"]].sum()
           .rename(columns={"dkk": "fac_kap_dkk", "mwh": "fac_kap_mwh"}))
    return akt.join(kap, how="outer").reset_index()


def main():
    nc = sys.argv[1] if len(sys.argv) > 1 else None
    if nc is None:
        cands = sorted(Path("output/backtest_q1_cap14").glob("*_dispatch.nc"))
        nc = str(cands[-1]) if cands else None
    if not nc or not Path(nc).exists():
        raise SystemExit(f"Dispatch .nc ikke fundet: {nc}")
    print(f"Loader dispatch: {nc}")
    result = xr.open_dataset(nc)

    cfg = load_case(CASE)
    cfg.time.start = f"{START}T00:00:00Z"
    cfg.time.end = f"{END}T23:00:00Z"
    heat_load = load_heat_load_params(CASE)
    print("Reloader data (uden solve)...")
    data = load_external_data_github(cfg, heat_load=heat_load, with_balancing=True)
    # Modellen kan ende på et andet sidste tidsstempel end data (--end uden
    # klokkeslæt → midnat); align data til dispatch-aksen.
    data = data.reindex(time=result.time.values)

    time = pd.DatetimeIndex(result.time.values)
    hours_per_month = pd.Series(1, index=time).groupby(time.to_period("M")).size()

    rows = []
    cf_rows = []
    for mk in MARKETS:
        price_cap = data[mk.cap_price_key]
        av = data[mk.act_value_key]            # brutto DKK/MW/h
        pay = data[mk.act_payment_key]         # netto DKK/MW/h
        clear = data[mk.clear_fraction_key]    # [0,1]

        # model reserveret MW pr. time = Σ over enheder
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
            "clear_when_bid": np.where(r_total.values > 0.01, clear.values, np.nan),
        })
        g = per.groupby("maaned")
        agg = g.agg(
            mod_r_mw_snit=("r_mw", "mean"),
            mod_cap_dkk=("cap_dkk", "sum"),
            mod_gross_dkk=("gross_dkk", "sum"),
            mod_net_dkk=("net_dkk", "sum"),
            mod_clear_mean=("clear", "mean"),
            mod_clear_when_bid=("clear_when_bid", "mean"),
        ).reset_index()
        agg["marked"] = mk.label
        rows.append(agg)

    model = pd.concat(rows, ignore_index=True)
    facit = load_facit()
    # facit marked-navne matcher mk.label (aFRR/mFRR)
    m = model.merge(facit, on=["maaned", "marked"], how="left")

    # capture-rate (realiseret / modelleret netto)
    m["capture_net_pct"] = m["fac_akt_dkk"] / m["mod_net_dkk"] * 100
    m["capture_gross_pct"] = m["fac_akt_dkk"] / m["mod_gross_dkk"] * 100

    print("\n" + "=" * 90)
    print("CAPTURE-RATE — aktivering (EAM): realiseret facit vs modelleret (perfekt foresight)")
    print("=" * 90)
    cols = ["maaned", "marked", "mod_net_dkk", "mod_gross_dkk", "fac_akt_dkk",
            "capture_net_pct"]
    pd.set_option("display.width", 200)
    print(m[cols].to_string(index=False, float_format=lambda x: f"{x:,.0f}"))

    print("\nReservation (kapacitet) — modelleret MW-snit vs facit MW-snit, + kap-DKK:")
    m["fac_kap_mw_snit"] = m.apply(
        lambda r: r["fac_kap_mwh"] / hours_per_month.get(
            pd.Period(r["maaned"].replace(".", "-"), "M"), np.nan), axis=1)
    print(m[["maaned", "marked", "mod_r_mw_snit", "fac_kap_mw_snit",
             "mod_cap_dkk", "fac_kap_dkk"]].to_string(
        index=False, float_format=lambda x: f"{x:,.2f}"))

    print("\nAktiveringsfrekvens — modellens clear_fraction (alle timer / betinget af bud) "
          "vs facit:")
    print(m[["maaned", "marked", "mod_clear_mean", "mod_clear_when_bid"]].to_string(
        index=False, float_format=lambda x: f"{x:.3f}"))

    # Samlet pr. marked + total
    print("\n" + "=" * 90)
    print("SAMLET jan–apr pr. marked + total")
    print("=" * 90)
    summ = m.groupby("marked").agg(
        mod_net_dkk=("mod_net_dkk", "sum"),
        mod_gross_dkk=("mod_gross_dkk", "sum"),
        mod_cap_dkk=("mod_cap_dkk", "sum"),
        fac_akt_dkk=("fac_akt_dkk", "sum"),
        fac_kap_dkk=("fac_kap_dkk", "sum"),
    ).reset_index()
    summ["capture_net_pct"] = summ["fac_akt_dkk"] / summ["mod_net_dkk"] * 100
    tot = summ.drop(columns="marked").sum()
    tot["marked"] = "TOTAL"
    tot["capture_net_pct"] = tot["fac_akt_dkk"] / tot["mod_net_dkk"] * 100
    summ = pd.concat([summ, pd.DataFrame([tot])], ignore_index=True)
    print(summ.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))

    # facit reservation total + model
    print("\nReservation total (kap-DKK) + balance-headline:")
    print(f"  Model netto balance (kap+netto akt), jan-apr: "
          f"{(summ.loc[summ.marked=='TOTAL','mod_cap_dkk'].iloc[0] + summ.loc[summ.marked=='TOTAL','mod_net_dkk'].iloc[0])/1e6:.2f} mio DKK")
    fac_total = facit[["fac_akt_dkk", "fac_kap_dkk"]].sum().sum()
    print(f"  Facit realiseret balance (FORB Op, akt+kap), jan-apr: "
          f"{fac_total/1e6:.3f} mio DKK")

    out = Path("output/backtest_q1_cap14/capture_rate_detail.csv")
    m.to_csv(out, index=False)
    print(f"\nGemt: {out}")


if __name__ == "__main__":
    main()
