"""
Rapportering: KPI-tabel, timebaseret CSV, sæson-oversigt og dispatch-plots.

Holdes bevidst simpel i trin 1 — udvides i trin 2-3 (marginalomkostninger
per enhed, produktionspris i DKK/MWh, investeringsvariabel).

Trin 3-udvidelse: UC-variable (commit/startup/shutdown) inkluderes i hourly
CSV hvis til stede, og kpi_summary printer UC-metrics per enhed.
"""
from __future__ import annotations
import pandas as pd
import xarray as xr
from pathlib import Path

from .unit_commitment import summarize_uc_dispatch, print_uc_summary


# ---------------------------------------------------------------------------
#  Intern hjælper: tank-værdi per time
# ---------------------------------------------------------------------------
def _tank_value_hourly(result: xr.Dataset, dt: float) -> xr.DataArray | None:
    """
    Beregn tankens bidrag til årsøkonomien per time.

    Værdi_t = −storage_net_t × shadow_price_heat_t × dt    [DKK]

    Fortegn: positiv når tanken aflader (storage_net < 0) i dyre timer,
    eller oplader (storage_net > 0) i billige timer. Negativ når den
    gør det modsatte (sker ikke ved optimum udover marginalt via
    self-discharge).

    Returnerer DataArray[storage, time] i DKK, eller None hvis duals
    eller storage_net ikke findes i result.
    """
    if ("shadow_price_heat" not in result.data_vars
            or "storage_net" not in result.data_vars):
        return None

    sp = result["shadow_price_heat"]        # DKK/MWh, [time]
    net = result["storage_net"]              # MW,      [storage, time]
    return (-net * sp * dt)                  # DKK,     [storage, time]


# ---------------------------------------------------------------------------
#  KPI — årsnøgletal per enhed
# ---------------------------------------------------------------------------
def kpi_summary(result: xr.Dataset, data: xr.Dataset, cfg) -> pd.DataFrame:
    """
    KPI'er per enhed:
      - Årlig produktion [MWh]
      - Kapacitetsfaktor [%]
      - Andel af samlet varmeproduktion [%]
      - Driftstimer (>0 produktion)
    Plus samlede:
      - Total varmeproduktion [MWh]
      - Varmeefterspørgsel [MWh]
      - Nettab (hvis dekomponeret) [MWh og %]
      - Objektiv værdi [DKK/år]
      - Tank arbitrage-værdi per lager [DKK/år] — hvis duals er udtrukket (LP)
      - Unit commitment metrics per UC-enhed — hvis MILP
    """
    hp = result["heat_prod"]                    # [unit, time], MW
    dt_delta = pd.to_timedelta(data.time.diff("time").mean().values)
    dt = dt_delta.total_seconds() / 3600.0
    production_mwh = hp.sum("time") * dt         # [unit]
    total_production = float(production_mwh.sum())
    demand_mwh = float((data["heat_demand"] * dt).sum())

    rows = []
    for unit in hp.unit.values:
        cap = cfg.units[str(unit)].p_max_heat
        hours = len(hp.time)
        prod = float(production_mwh.sel(unit=unit))
        capf = prod / (cap * hours * dt) * 100 if cap > 0 else 0
        operating_h = int(((hp.sel(unit=unit) > 1e-6)).sum())
        rows.append({
            "unit": str(unit),
            "p_max_mw": cap,
            "production_mwh": round(prod, 1),
            "share_pct": round(prod / total_production * 100, 1) if total_production > 0 else 0,
            "capacity_factor_pct": round(capf, 1),
            "operating_hours": operating_h,
        })

    df = pd.DataFrame(rows).sort_values("production_mwh", ascending=False)

    # Balance-tjek
    # Forskel = demand - produktion. Kan komme fra to kilder:
    #   1. Self-discharge af tank (rigtig "lagertab")
    #   2. Forventet varmereduktion pga. aFRR- og/eller mFRR-aktivering
    # Vi dekomponerer så rapporten ikke er misvisende.
    diff = demand_mwh - total_production

    # Beregn forventet heat_reduction hvis balancing er aktivt — summer over
    # begge markeder (aFRR + mFRR) hvis de er til stede.
    heat_reduction_mwh = 0.0
    for prefix, alpha_key in (
        ("r_afrr_", "afrr_activation_fraction_up"),
        ("r_mfrr_", "mfrr_activation_fraction_up"),
        # Legacy-præfiks fra før session 12 trin B — sikrer at gamle .nc
        # artefakter stadig kan rapporteres korrekt
        ("r_up_el_", "afrr_activation_fraction_up"),
    ):
        if alpha_key not in data.data_vars:
            continue
        alpha_values = data[alpha_key].values
        r_vars = [str(v) for v in result.data_vars if str(v).startswith(prefix)]
        for var_name in r_vars:
            unit_name = var_name.replace(prefix, "")
            if unit_name not in cfg.units:
                continue
            unit = cfg.units[unit_name]
            r_values = result[var_name].values
            if unit.cop_curve is not None and "t_ambient" in data.data_vars:
                cop_values = unit.cop_curve.evaluate(data["t_ambient"]).values
            elif unit.alpha != 0:
                cop_values = 1.0 / abs(unit.alpha)
            else:
                cop_values = 1.0
            heat_reduction_mwh += float((alpha_values * cop_values * r_values * dt).sum())

    print(f"\n--- Samlet ---")
    print(f"Varmeefterspørgsel:   {demand_mwh:>12,.0f} MWh")
    print(f"Samlet produktion:    {total_production:>12,.0f} MWh")
    print(f"Differens:            {diff:>12,.0f} MWh")

    if "heat_nettab" in data.data_vars:
        nettab_mwh = float((data["heat_nettab"] * dt).sum())
        nettab_pct = nettab_mwh / demand_mwh * 100 if demand_mwh > 0 else 0
        print(f"  heraf nettab:       {nettab_mwh:>12,.0f} MWh  ({nettab_pct:.1f}% af varmebehov)")

    if heat_reduction_mwh > 0:
        print(
            f"  forv. heat-reduktion: {heat_reduction_mwh:>10,.0f} MWh  "
            f"(fra reserve-aktivering)"
        )
        # Resten af differencen efter heat_reduction er enten self-discharge
        # eller cycle-binding-effekter — afhænger af om lager er aktivt.
        tank_effects = diff + heat_reduction_mwh  # diff er negativ når prod > demand
        if abs(tank_effects) > 1.0:
            if "storage_energy" in result.data_vars:
                print(f"  netto lagertab:     {tank_effects:>12,.0f} MWh  (self-discharge + cycle)")
            else:
                print(f"  residual:           {tank_effects:>12,.0f} MWh  (numerisk, ingen lager)")

    print(f"Objektiv:             {result.attrs['objective_value']:>12,.0f} DKK")
    print(f"Status:               {result.attrs['status']}")
    if result.attrs.get("is_milp", 0):
        print(f"Model-type:           MILP (unit commitment aktivt)")

    # Tank arbitrage-værdi per lager (kræver duals → kun LP)
    value_hourly = _tank_value_hourly(result, dt)
    if value_hourly is not None:
        print(f"\n--- Tank arbitrage-værdi (dual-baseret) ---")
        total_all = 0.0
        for s in value_hourly.storage.values:
            v = float(value_hourly.sel(storage=s).sum())
            total_all += v
            print(f"  {str(s):22s} {v:>12,.0f} DKK/år")
        if len(value_hourly.storage.values) > 1:
            print(f"  {'I alt':22s} {total_all:>12,.0f} DKK/år")
        print(f"  (sammenlign med objektiv-differens baseline vs --disable)")

    # Unit commitment metrics (kun MILP)
    if "commit" in result.data_vars:
        uc_entries = [
            (name, u) for name, u in cfg.units.items()
            if u.enabled and u.has_uc
        ]
        if uc_entries:
            uc_summary = summarize_uc_dispatch(result, uc_entries)
            print_uc_summary(uc_summary)

    # Balancing-reserve summary (trin 8.2/8.3a + session 12 trin B)
    has_balancing = any(
        str(v).startswith(("r_afrr_", "r_mfrr_", "r_up_el_"))
        for v in result.data_vars
    )
    if has_balancing:
        from .balancing import summarize_reserves, print_reserve_summary
        bal_summary = summarize_reserves(result, data)
        if bal_summary is not None:
            print_reserve_summary(bal_summary)

    return df


# ---------------------------------------------------------------------------
#  Sæson-oversigt — månedsopdelt dispatch, kontekst og tank-værdi
# ---------------------------------------------------------------------------
def seasonal_summary(result: xr.Dataset, data: xr.Dataset, cfg,
                     out_path: Path | None = None) -> pd.DataFrame:
    """
    Månedsopdelt oversigt over dispatch, driftskontekst og tank-værdi.

    Kolonner (i rækkefølge):
      - Produktion per aktiv enhed [GWh]    — sorteret efter årssum
      - heat_load_gwh                       — samlet varmebehov
      - {s}_value_kdkk per aktivt lager     — tankens arbitrage-værdi
                                              (kun hvis shadow_price_heat
                                              er udtrukket)
      - spot_mean_dkk_mwh                   — månedlig gns. spot
      - shadow_mean_dkk_mwh                 — månedlig gns. skyggepris
                                              (kun hvis tilgængelig)
      - t_out_c                             — månedlig gns. udetemp

    Rækker: måned 1-12 + 'År'-total.
    Energier og værdier summeres; priser og temperatur midles.

    Bemærk om månedlig tank-værdi:
    Tanken er cyklisk bundet på årsbasis men ikke på månedsbasis. Derfor
    kan en enkelt måneds tank-værdi være præget af at tanken starter
    måneden fuld og slutter tom (eller omvendt). Års-totalen er
    robust; månedsopdelingen er indikativ for *hvornår* arbitragen
    skabes.
    """
    hp = result["heat_prod"]                   # [unit, time], MW
    dt_delta = pd.to_timedelta(data.time.diff("time").mean().values)
    dt = dt_delta.total_seconds() / 3600.0

    idx = pd.to_datetime(data.time.values)
    df = pd.DataFrame(index=idx)

    # Enheder sorteret efter årssum (størst først)
    total_prod = hp.sum("time")
    units_sorted = sorted(
        hp.unit.values,
        key=lambda u: float(total_prod.sel(unit=u)),
        reverse=True,
    )
    for u in units_sorted:
        df[f"{u}_gwh"] = hp.sel(unit=u).values * dt / 1000

    df["heat_load_gwh"] = data["heat_demand"].values * dt / 1000

    # Tank-værdi per lager [kDKK per time → summer senere til måned]
    value_hourly = _tank_value_hourly(result, dt)
    if value_hourly is not None:
        for s in value_hourly.storage.values:
            df[f"{s}_value_kdkk"] = value_hourly.sel(storage=s).values / 1000.0

    df["spot_mean_dkk_mwh"] = data["spot_price"].values
    if "shadow_price_heat" in result.data_vars:
        df["shadow_mean_dkk_mwh"] = result["shadow_price_heat"].values
    if "t_ambient" in data.data_vars:
        df["t_out_c"] = data["t_ambient"].values

    # Aggregér per måned
    df["month"] = df.index.month
    sum_cols = [c for c in df.columns
                if c.endswith("_gwh") or c.endswith("_kdkk")]
    mean_cols = [c for c in df.columns
                 if c in ("spot_mean_dkk_mwh", "shadow_mean_dkk_mwh", "t_out_c")]

    monthly = df.groupby("month")[sum_cols].sum().join(
        df.groupby("month")[mean_cols].mean()
    )

    # Årstotal: sum på energier/værdier, middel på intensive størrelser
    total_row = pd.DataFrame(
        {**{c: [df[c].sum()] for c in sum_cols},
         **{c: [df[c].mean()] for c in mean_cols}},
        index=["År"],
    )
    monthly = pd.concat([monthly, total_row])

    # Formatering
    gwh_cols = [c for c in monthly.columns if c.endswith("_gwh")]
    kdkk_cols = [c for c in monthly.columns if c.endswith("_kdkk")]
    monthly[gwh_cols] = monthly[gwh_cols].round(2)
    if kdkk_cols:
        monthly[kdkk_cols] = monthly[kdkk_cols].round(0).astype(int)
    for c in ("spot_mean_dkk_mwh", "shadow_mean_dkk_mwh"):
        if c in monthly.columns:
            monthly[c] = monthly[c].round(0).astype(int)
    if "t_out_c" in monthly.columns:
        monthly["t_out_c"] = monthly["t_out_c"].round(1)

    if out_path is not None:
        monthly.to_csv(out_path)
        print(f"CSV gemt:  {out_path}")

    return monthly


# ---------------------------------------------------------------------------
#  Timebaseret CSV
# ---------------------------------------------------------------------------
def write_hourly_csv(result: xr.Dataset, data: xr.Dataset, cfg,
                     out_path: Path) -> Path:
    """
    Skriv timebaseret CSV med alle input- og output-serier.

    Kolonner (i fast rækkefølge):
      1. Index: timestamp (UTC, ISO8601)
      2. Input-last: heat_load_mw, [heat_gaf_mw, heat_guf_mw, heat_nettab_mw,
                                    heat_nettab_pct]
      3. Marked/duals/vejr: spot_price_dkk_mwh,
                            [shadow_price_heat_dkk_mwh],
                            [t_out_c],
                            [afrr_cap_up_dkk_mw_h,
                             afrr_act_up_dkk_mwh,
                             afrr_activation_fraction_up]
      4. Produktion: p_{unit}_mw for hver aktiv enhed (alfabetisk)
      5. UC-variable: {unit}_commit_01, {unit}_startup_01, {unit}_shutdown_01
                      (kun hvis MILP — en kolonne per UC-enhed)
      6. aFRR-bud (kun hvis --with-balancing):
         r_up_el_{unit}_mw, _activated_mwh, _heat_reduction_mw,
         _cap_revenue_dkk, _act_revenue_dkk
      7. Lager (per aktivt lager):
         {s}_level_mwh, {s}_level_pct, {s}_charge_mw, {s}_discharge_mw,
         {s}_net_mw, [{s}_shadow_dkk_mwh], [{s}_value_dkk]

    Første time droppes — den er en boundary condition (storage_energy[0]
    er start-værdi, ikke resultat af dispatch, så heat_prod[0] = 0).
    """
    t = data.time.values
    dt_delta = pd.to_timedelta(data.time.diff("time").mean().values)
    dt = dt_delta.total_seconds() / 3600.0
    df = pd.DataFrame(index=pd.Index(t, name="timestamp"))

    # --- Input: varmelast og dekomponering ----------------------------------
    df["heat_load_mw"] = data["heat_demand"].values
    if "heat_gaf" in data.data_vars:
        df["heat_gaf_mw"] = data["heat_gaf"].values
    if "heat_guf" in data.data_vars:
        df["heat_guf_mw"] = data["heat_guf"].values
    if "heat_nettab" in data.data_vars:
        df["heat_nettab_mw"] = data["heat_nettab"].values
        load = df["heat_load_mw"].replace(0, pd.NA)
        df["heat_nettab_pct"] = (df["heat_nettab_mw"] / load * 100).round(2)

    # --- Marked, duals og vejr ---------------------------------------------
    df["spot_price_dkk_mwh"] = data["spot_price"].values
    if "shadow_price_heat" in result.data_vars:
        df["shadow_price_heat_dkk_mwh"] = result["shadow_price_heat"].values
    if "t_ambient" in data.data_vars:
        df["t_out_c"] = data["t_ambient"].values

    # aFRR-markedsdata (hvis --with-balancing er kørt)
    if "afrr_cap_up_dkk" in data.data_vars:
        df["afrr_cap_up_dkk_mw_h"] = data["afrr_cap_up_dkk"].values
    if "afrr_act_up_dkk" in data.data_vars:
        df["afrr_act_up_dkk_mwh"] = data["afrr_act_up_dkk"].values
    if "afrr_activation_fraction_up" in data.data_vars:
        df["afrr_activation_fraction_up"] = data["afrr_activation_fraction_up"].values

    # mFRR-markedsdata (session 12 trin B)
    if "mfrr_cap_up_dkk" in data.data_vars:
        df["mfrr_cap_up_dkk_mw_h"] = data["mfrr_cap_up_dkk"].values
    if "mfrr_act_up_dkk" in data.data_vars:
        df["mfrr_act_up_dkk_mwh"] = data["mfrr_act_up_dkk"].values
    if "mfrr_activation_fraction_up" in data.data_vars:
        df["mfrr_activation_fraction_up"] = data["mfrr_activation_fraction_up"].values

    # --- Produktion per enhed (alfabetisk) ----------------------------------
    hp = result["heat_prod"]
    for unit in sorted(hp.unit.values, key=str):
        df[f"p_{unit}_mw"] = hp.sel(unit=unit).values

    # --- UC-variable (kun MILP) --------------------------------------------
    # Kolonner navngives med suffiks _01 for at markere binær
    if "commit" in result.data_vars:
        for unit in sorted(result["commit"].unit_uc.values, key=str):
            df[f"{unit}_commit_01"] = result["commit"].sel(unit_uc=unit).values.astype(int)
            df[f"{unit}_startup_01"] = result["startup"].sel(unit_uc=unit).values.astype(int)
            df[f"{unit}_shutdown_01"] = result["shutdown"].sel(unit_uc=unit).values.astype(int)

    # --- Reserve-bud per enhed og marked (trin 8.2/8.3a + session 12 trin B) -
    # For hver enhed med r_<market>_<unit> i result skrives 5 kolonner:
    #   <var>_mw                — reserveret kapacitet [MW el]
    #   <var>_activated_mwh     — forv. aktiveret volumen [MWh el]
    #   <var>_heat_reduction_mw — forv. tabt varme [MW]
    #   <var>_cap_revenue_dkk   — kapacitetsindtægt [DKK]
    #   <var>_act_revenue_dkk   — aktiveringsprisindtægt [DKK]
    #                             (KUN prisen; sparede forbrugsomkostninger er
    #                             modregnet via heat_prod·mc-termen i obj)
    # Legacy r_up_el_-præfiks (før session 12) håndteres som en aFRR-alias.

    _MARKET_DATA = [
        ("r_afrr_",  "afrr_cap_up_dkk",  "afrr_act_up_dkk",  "afrr_activation_fraction_up"),
        ("r_mfrr_",  "mfrr_cap_up_dkk",  "mfrr_act_up_dkk",  "mfrr_activation_fraction_up"),
        ("r_up_el_", "afrr_cap_up_dkk",  "afrr_act_up_dkk",  "afrr_activation_fraction_up"),
    ]

    for prefix, cap_key, act_key, alpha_key in _MARKET_DATA:
        r_up_vars = sorted(
            [str(v) for v in result.data_vars if str(v).startswith(prefix)]
        )
        if not r_up_vars:
            continue

        alpha = data.get(alpha_key)
        price_cap = data.get(cap_key)
        price_act = data.get(act_key)

        for var_name in r_up_vars:
            unit_name = var_name.replace(prefix, "")
            if unit_name not in cfg.units:
                continue
            r_values = result[var_name].values
            df[f"{var_name}_mw"] = r_values

            # Beregn COP(t) til heat_reduction — følger balancing._get_cop_series
            unit = cfg.units[unit_name]
            if unit.cop_curve is not None and "t_ambient" in data.data_vars:
                cop_values = unit.cop_curve.evaluate(data["t_ambient"]).values
            elif unit.alpha != 0:
                cop_values = 1.0 / abs(unit.alpha)  # skalar broadcast
            else:
                cop_values = 1.0

            if alpha is not None:
                alpha_values = alpha.values
                df[f"{var_name}_activated_mwh"] = alpha_values * r_values * dt
                df[f"{var_name}_heat_reduction_mw"] = alpha_values * cop_values * r_values
            if price_cap is not None:
                df[f"{var_name}_cap_revenue_dkk"] = price_cap.values * r_values * dt
            if alpha is not None and price_act is not None:
                df[f"{var_name}_act_revenue_dkk"] = (
                    alpha.values * price_act.values * r_values * dt
                )

    # --- Lager --------------------------------------------------------------
    # BUGFIX: variablerne hedder 'charge'/'discharge' i solve.py, ikke
    # 'storage_charge'/'storage_discharge'. Tidligere blev disse kolonner
    # aldrig skrevet (.get returnerede None).
    if "storage_energy" in result.data_vars:
        se = result["storage_energy"]
        ch = result.get("charge")
        dis = result.get("discharge")
        sp_stor = result.get("shadow_price_storage")
        value_hourly = _tank_value_hourly(result, dt)

        for s in sorted(se.storage.values, key=str):
            e_max = cfg.storage[str(s)].e_max_mwh
            level = se.sel(storage=s).values
            df[f"{s}_level_mwh"] = level
            df[f"{s}_level_pct"] = (level / e_max * 100).round(2) if e_max > 0 else 0
            if ch is not None:
                df[f"{s}_charge_mw"] = ch.sel(storage=s).values
            if dis is not None:
                df[f"{s}_discharge_mw"] = dis.sel(storage=s).values
            if ch is not None and dis is not None:
                df[f"{s}_net_mw"] = (ch.sel(storage=s).values
                                     - dis.sel(storage=s).values)
            if sp_stor is not None:
                df[f"{s}_shadow_dkk_mwh"] = sp_stor.sel(storage=s).values
            if value_hourly is not None:
                df[f"{s}_value_dkk"] = value_hourly.sel(storage=s).values.round(1)

    # Rund MW-kolonner til 3 decimaler, DKK/MWh-kolonner til 1
    mw_cols = [c for c in df.columns if c.endswith("_mw")]
    df[mw_cols] = df[mw_cols].round(3)
    dkk_mwh_cols = [c for c in df.columns if c.endswith("_dkk_mwh")]
    df[dkk_mwh_cols] = df[dkk_mwh_cols].round(1)

    # Drop første time — boundary condition
    df = df.iloc[1:]

    df.to_csv(out_path, date_format="%Y-%m-%dT%H:%M:%S")
    print(f"CSV gemt:  {out_path}  ({len(df):,} rækker × {len(df.columns)} kolonner)")
    return out_path


# ---------------------------------------------------------------------------
#  Dispatch-plot (uændret)
# ---------------------------------------------------------------------------
def dispatch_plot(result: xr.Dataset, data: xr.Dataset, out_path: Path,
                  cfg=None, days: int = 7):
    """
    Stacked area plot af dispatch for de første 'days' dage.

    Øverste panel: produktion stakket + varmelast (sort linje) + udetemp
                   (rød linje på højre y-akse), hvis tilgængelig.
    Midt panel:    spotpris.
    Nederste panel: lagerfyldning i % (hvis lager aktivt).
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib mangler — springer plot over")
        return

    hours = days * 24
    t = result.time.values[:hours]
    hp = result["heat_prod"].sel(time=t)
    demand = data["heat_demand"].sel(time=t)
    has_temp = "t_ambient" in data.data_vars

    has_storage = "storage_energy" in result.data_vars and cfg is not None
    if has_storage:
        fig, (ax1, ax2, ax3) = plt.subplots(
            3, 1, figsize=(12, 9), sharex=True,
            gridspec_kw={"height_ratios": [3, 1, 1]},
        )
    else:
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(12, 7), sharex=True,
            gridspec_kw={"height_ratios": [3, 1]},
        )
        ax3 = None

    units_sorted = hp.sum("time").sortby(hp.sum("time"), ascending=False).unit.values
    bottom = None
    for u in units_sorted:
        y = hp.sel(unit=u).values
        ax1.fill_between(t, bottom if bottom is not None else 0,
                         (bottom if bottom is not None else 0) + y,
                         label=str(u), alpha=0.8)
        bottom = (bottom if bottom is not None else 0) + y

    ax1.plot(t, demand.values, "k-", lw=1.5, label="Varmelast")
    ax1.set_ylabel("Varme [MW]")
    ax1.set_title(f"Dispatch — første {days} dage")
    ax1.grid(alpha=0.3)

    if has_temp:
        temp = data["t_ambient"].sel(time=t).values
        ax1b = ax1.twinx()
        ax1b.plot(t, temp, color="tab:red", lw=1.2, alpha=0.85,
                  label="Udetemp", linestyle="--")
        ax1b.set_ylabel("Udetemperatur [°C]", color="tab:red")
        ax1b.tick_params(axis="y", labelcolor="tab:red")
        ax1b.axhline(0, color="tab:red", lw=0.5, alpha=0.3)

        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax1b.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, loc="upper right", ncol=2, fontsize=8)
    else:
        ax1.legend(loc="upper right", ncol=2, fontsize=8)

    ax2.plot(t, data["spot_price"].sel(time=t).values, "b-", lw=1)
    ax2.set_ylabel("Spot [DKK/MWh]")
    ax2.grid(alpha=0.3)
    ax2.axhline(0, color="k", lw=0.5, alpha=0.4)

    if ax3 is not None:
        se = result["storage_energy"].sel(time=t)
        storage_names = se.storage.values
        for s in storage_names:
            e_max = cfg.storage[str(s)].e_max_mwh
            pct = se.sel(storage=s).values / e_max * 100
            ax3.plot(t, pct, lw=1.3, label=f"{s} ({e_max:.0f} MWh)")
            ax3.fill_between(t, 0, pct, alpha=0.15)
        ax3.set_ylabel("Lager [%]")
        ax3.set_ylim(0, 105)
        ax3.grid(alpha=0.3)
        ax3.axhline(100, color="#888", lw=0.5, linestyle="--")
        if len(storage_names) > 1:
            ax3.legend(loc="upper right", fontsize=8)
        else:
            ax3.text(0.01, 0.95, str(storage_names[0]), transform=ax3.transAxes,
                     fontsize=8, color="#444", va="top")

    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot gemt: {out_path}")
