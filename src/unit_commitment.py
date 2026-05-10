"""
Unit commitment for LP → MILP udvidelse (trin 3).

Tight Rajan & Takriti (2005) formulering. Isoleret modul så model.py forbliver
overskueligt.

Per enhed aktiveres UC ved at sætte Unit.uc_enabled = True (default False).
Bindinger trækkes direkte fra Unit's eksisterende felter:
    p_min_heat      → P_min (min-last)
    min_uptime      → UT
    min_downtime    → DT
    start_cost      → c_startup
    initial_status  → u_0

Enheder med uc_enabled = False beholder deres LP-behandling uanset hvad de
har stående i min_uptime/min_downtime/start_cost (de bruges kun når flaget
er sat — undgår at gamle YAML-felter uforvarende aktiverer MILP).

Variable (kun for UC-enheder):
    u[i, t] ∈ {0,1}    commit-status
    v[i, t] ∈ {0,1}    startup
    w[i, t] ∈ {0,1}    shutdown

Constraints:
    UC-1  u[t] − u[t−1] = v[t] − w[t]                 (tilstandsovergang)
    UC-2  v[t] + w[t] ≤ 1                             (mutuel eksklusion)
    UC-3  Σ_{τ=t−UT+1..t} v[τ] ≤ u[t]                 (min-uptime, tight)
    UC-4  Σ_{τ=t−DT+1..t} w[τ] ≤ 1 − u[t]             (min-downtime, tight)
    UC-5  P_min · u[t] ≤ p[t] ≤ P_max · u[t]          (kobling til heat_prod)

Objektivtillæg:
    Σ_t c_startup · v[t]

NOTE om tight-formuleringen: vi bruger R&T 2005 "rolling sum" frem for
den naive formulering u[t] ≥ v[τ] ∀ τ ∈ [t−UT+1, t]. Den tight version
har strammere LP-relaxation → faktor 10-100 på branch-and-bound-tid.
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple

import numpy as np
import xarray as xr
import linopy as lp

from .config import CaseConfig, Unit


# ------------------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------------------

def _collect_uc_units(cfg: CaseConfig) -> List[Tuple[str, Unit]]:
    """
    Find alle aktive enheder med uc_enabled = True.

    Returnerer liste af (navn, Unit)-tuples. Navnet er dict-nøglen i cfg.units,
    hvilket matcher det navn som heat_prod-variablen bruger på 'unit'-koordinaten.
    """
    return [
        (name, unit)
        for name, unit in cfg.units.items()
        if unit.enabled and unit.has_uc
    ]


# ------------------------------------------------------------------------------
# Hovedfunktion
# ------------------------------------------------------------------------------

def add_unit_commitment(
    m: lp.Model,
    cfg: CaseConfig,
    data: xr.Dataset,
    heat_prod: lp.Variable,
) -> Optional[Dict[str, Any]]:
    """
    Tilføj UC-variable og constraints til modellen for enheder med uc_enabled=True.

    Parameters
    ----------
    m : lp.Model
        Modellen der bygges i build_model().
    cfg : CaseConfig
        Fuld konfig; vi filtrerer selv på enabled + uc_enabled.
    data : xr.Dataset
        Skal have koordinat `time`.
    heat_prod : lp.Variable
        Den allerede oprettede (unit, time)-variabel for varmeproduktion.

    Returns
    -------
    dict med nøgler:
        'u', 'v', 'w'                — binære variable
        'startup_cost_expr'          — LinearExpression til obj-tillæg (eller None)
        'uc_entries'                 — liste af (navn, Unit)-tuples med UC aktiv
    eller None hvis ingen UC-enheder findes.
    """
    uc_entries = _collect_uc_units(cfg)
    if not uc_entries:
        return None

    uc_names = [name for name, _ in uc_entries]
    time_coord = data.time.values
    t0 = time_coord[0]

    # Informativ startup-besked
    print(f"  UC aktiveret på: {', '.join(uc_names)}")
    for name, unit in uc_entries:
        print(
            f"    {name}: p_min={unit.p_min_heat} MW, "
            f"UT={unit.min_uptime}h, DT={unit.min_downtime}h, "
            f"c_start={unit.start_cost:.0f} DKK, u0={unit.initial_status}"
        )

    # ==========================================================================
    # Binære variable
    # ==========================================================================
    u = m.add_variables(
        binary=True,
        coords=[("unit_uc", uc_names), ("time", time_coord)],
        name="commit",
    )
    v = m.add_variables(
        binary=True,
        coords=[("unit_uc", uc_names), ("time", time_coord)],
        name="startup",
    )
    w = m.add_variables(
        binary=True,
        coords=[("unit_uc", uc_names), ("time", time_coord)],
        name="shutdown",
    )

    # ==========================================================================
    # UC-1: tilstandsovergang  u[t] − u[t−1] = v[t] − w[t]    for t ≥ 1
    # ==========================================================================
    u_shifted = u.shift(time=1)
    lhs = (u - u_shifted) - (v - w)
    m.add_constraints(
        lhs.sel(time=time_coord[1:]) == 0,
        name="uc_state_transition",
    )

    # ==========================================================================
    # Initialbetingelser (t = 0): fastlås u, v, w
    # ==========================================================================
    init_u = xr.DataArray(
        [unit.initial_status for _, unit in uc_entries],
        coords={"unit_uc": uc_names}, dims="unit_uc",
    )
    m.add_constraints(
        u.sel(time=t0) == init_u,
        name="uc_initial_u",
    )
    m.add_constraints(
        v.sel(time=t0) == 0,
        name="uc_initial_v",
    )
    m.add_constraints(
        w.sel(time=t0) == 0,
        name="uc_initial_w",
    )

    # ==========================================================================
    # UC-2: mutuel eksklusion  v[t] + w[t] ≤ 1
    # ==========================================================================
    # (følger teknisk af UC-1 + binary, men eksplicit constraint giver strammere
    # LP-relaxation og bedre solver-performance)
    m.add_constraints(v + w <= 1, name="uc_startup_shutdown_excl")

    # ==========================================================================
    # UC-3 og UC-4: min-up/down time via rullende sum
    # ==========================================================================
    # Vi bygger summen Σ_{k=0..N-1} x.shift(time=k) hvilket giver rolling
    # backwards sum. Constraint håndhæves kun hvor alle shifts er defineret
    # (dvs. t ≥ N−1). Per enhed fordi UT/DT kan variere.
    for name, unit in uc_entries:
        UT = unit.min_uptime
        DT = unit.min_downtime

        u_i = u.sel(unit_uc=name)
        v_i = v.sel(unit_uc=name)
        w_i = w.sel(unit_uc=name)

        # UC-3: min-uptime
        if UT > 1:
            rolling_v = sum(v_i.shift(time=k) for k in range(UT))
            valid = time_coord[UT - 1 :]
            m.add_constraints(
                rolling_v.sel(time=valid) <= u_i.sel(time=valid),
                name=f"uc_minup_{name}",
            )

        # UC-4: min-downtime
        if DT > 1:
            rolling_w = sum(w_i.shift(time=k) for k in range(DT))
            valid = time_coord[DT - 1 :]
            m.add_constraints(
                rolling_w.sel(time=valid) <= 1 - u_i.sel(time=valid),
                name=f"uc_mindown_{name}",
            )

    # ==========================================================================
    # UC-5: kobling mellem heat_prod og u  (min-load og max-load)
    # ==========================================================================
    # heat_prod har allerede upper=p_max_heat som variabel-bound. Den er redundant
    # med UC-5 for UC-enheder men gør ingen skade (solveren bruger den stærkeste).
    for name, unit in uc_entries:
        p_i = heat_prod.sel(unit=name)
        u_i = u.sel(unit_uc=name)
        pmin = unit.p_min_heat
        pmax = unit.p_max_heat

        m.add_constraints(
            p_i - pmin * u_i >= 0,
            name=f"uc_minload_{name}",
        )
        m.add_constraints(
            p_i - pmax * u_i <= 0,
            name=f"uc_maxload_{name}",
        )

    # ==========================================================================
    # Objektivtillæg: startup costs
    # ==========================================================================
    # Byg som LinearExpression. Hvis c_startup = 0 skipper vi termen helt
    # (undgår "0 * v"-udtryk som kan forvirre Linopy i nogle versioner).
    startup_terms = []
    for name, unit in uc_entries:
        if unit.start_cost != 0:
            startup_terms.append(unit.start_cost * v.sel(unit_uc=name).sum())

    startup_cost_expr = sum(startup_terms) if startup_terms else None

    return {
        "u": u,
        "v": v,
        "w": w,
        "startup_cost_expr": startup_cost_expr,
        "uc_entries": uc_entries,
    }


# ------------------------------------------------------------------------------
# Post-solve rapportering
# ------------------------------------------------------------------------------

def summarize_uc_dispatch(
    solution: xr.Dataset,
    uc_entries: List[Tuple[str, Unit]],
) -> Dict[str, Dict[str, float]]:
    """
    Beregn nøgletal per UC-enhed fra løsning.

    Parameters
    ----------
    solution : xr.Dataset
        Fra solve_and_extract(); skal indeholde 'commit', 'startup', 'shutdown'
        samt 'heat_prod'.
    uc_entries : list[tuple[str, Unit]]
        Navn + Unit-objekt per UC-enhed.

    Returns
    -------
    dict keyed by unit_name med felter:
        num_starts, num_stops, hours_on, avg_block_hours,
        startup_cost_total_dkk, capacity_factor_when_on
    """
    out: Dict[str, Dict[str, float]] = {}

    if "commit" not in solution.data_vars:
        return out

    for name, unit in uc_entries:
        u_t = solution["commit"].sel(unit_uc=name).values
        v_t = solution["startup"].sel(unit_uc=name).values
        w_t = solution["shutdown"].sel(unit_uc=name).values
        p_t = solution["heat_prod"].sel(unit=name).values

        num_starts = int(np.round(v_t.sum()))
        num_stops = int(np.round(w_t.sum()))
        hours_on = int(np.round(u_t.sum()))
        avg_block = hours_on / num_starts if num_starts > 0 else float("nan")
        startup_cost = num_starts * unit.start_cost

        # Capacity factor kun over timer hvor enheden er on
        on_mask = u_t > 0.5
        if on_mask.sum() > 0:
            cf_on = float(p_t[on_mask].mean() / unit.p_max_heat)
        else:
            cf_on = float("nan")

        out[name] = {
            "num_starts": num_starts,
            "num_stops": num_stops,
            "hours_on": hours_on,
            "avg_block_hours": avg_block,
            "startup_cost_total_dkk": startup_cost,
            "capacity_factor_when_on": cf_on,
        }

    return out


def print_uc_summary(uc_summary: Dict[str, Dict[str, float]]) -> None:
    """Print formateret UC-oversigt til stdout."""
    if not uc_summary:
        return
    print("\n--- Unit commitment (MILP) ---")
    header = (
        f"  {'enhed':18s}  {'starts':>6s} {'hours_on':>8s} "
        f"{'avg_blok':>8s} {'CF|on':>7s} {'start_kost':>11s}"
    )
    print(header)
    for name, s in uc_summary.items():
        print(
            f"  {name:18s}  "
            f"{s['num_starts']:6d} "
            f"{s['hours_on']:8d} "
            f"{s['avg_block_hours']:7.1f}h "
            f"{s['capacity_factor_when_on']:6.1%} "
            f"{s['startup_cost_total_dkk']/1000:>9.0f} kDKK"
        )
