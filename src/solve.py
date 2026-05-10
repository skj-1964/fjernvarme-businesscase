"""
Solve og resultatudtræk.

Kører modellen og pakker løsningen til en pæn xarray.Dataset med
skyggepriser + dispatch. Skyggepriser på varmebalancen er guld til
diagnostik — de viser tankens værdiskabelse time-for-time, og
skyggepriser på lagerdynamikken er Bellman-værdien af lagret energi.

Understøtter både LP (trin 1) og MILP (trin 3). MILP detekteres automatisk
via m._has_uc (sat af build_model). I MILP-mode springes skyggeprisudtræk
over fordi duals ikke er veldefinerede for heltalsprogrammer.
"""
from __future__ import annotations
from typing import Iterable

import linopy as lp
import xarray as xr

from .config import CaseConfig


# ------------------------------------------------------------------------------
# Robust dual-extraction
# ------------------------------------------------------------------------------

def _get_constraint_dual(m: lp.Model, name: str) -> xr.DataArray | None:
    """
    Hent dual for en navngiven constraint. Robust ift. Linopy-versioner:
      - 0.3+ eksponerer `.dual` som attribut på hver constraint
      - Ældre versioner samler dem i `m.dual`
    Returnerer None hvis constraint ikke findes eller dual ikke kan hentes.
    """
    if name not in m.constraints:
        return None

    con = m.constraints[name]

    # Primær sti: per-constraint .dual-attribut (Linopy 0.3+)
    try:
        d = con.dual
        if d is not None and isinstance(d, xr.DataArray):
            return d
    except Exception as e:
        # Gem fejlen til den sekundære sti fejler også
        primary_err = repr(e)
    else:
        primary_err = None

    # Sekundær sti: m.dual som Dataset
    try:
        all_duals = m.dual
        if isinstance(all_duals, xr.Dataset) and name in all_duals.data_vars:
            return all_duals[name]
    except Exception as e:
        if primary_err:
            print(f"    (dual for '{name}' fejlede: primært {primary_err}, sekundært {e!r})")
        else:
            print(f"    (dual for '{name}' fejlede: {e!r})")
        return None

    if primary_err:
        print(f"    (dual for '{name}' fejlede: {primary_err})")
    return None


# ------------------------------------------------------------------------------
# Hovedfunktion
# ------------------------------------------------------------------------------

def solve_and_extract(m: lp.Model, cfg: CaseConfig, solver: str = "highs") -> xr.Dataset:
    """
    Løs modellen og returnér en Dataset med:
      - heat_prod[unit, time]
      - storage_energy[storage, time]
      - charge[storage, time], discharge[storage, time]
      - storage_net[storage, time]       (charge − discharge, netto ladeeffekt)
      - commit[unit_uc, time]            (kun MILP — 0/1 status)
      - startup[unit_uc, time]           (kun MILP — 0/1 startpuls)
      - shutdown[unit_uc, time]          (kun MILP — 0/1 stoppuls)
      - shadow_price_heat[time]          (kun LP — marginalpris for varme)
      - shadow_price_storage[storage, time]
                                         (kun LP — Bellman-værdi af MWh lagret
                                          energi, dual på storage_dynamics)
      - objective_value                  (attribut)
      - status                           (attribut)
      - is_milp                          (attribut — 0/1)
    """
    # --------------------------------------------------------------------------
    # MILP-detektion og solver-options
    # --------------------------------------------------------------------------
    # Detektér via constraint-navn frem for instans-attribut:
    # linopy.Model bruger __slots__ og tillader ikke ekstra attributter.
    # add_unit_commitment() tilføjer altid "uc_state_transition" når mindst én
    # UC-enhed er aktiv, så tilstedeværelsen af den constraint er en pålidelig
    # MILP-indikator.
    is_milp = "uc_state_transition" in m.constraints

    # Linopy's solve(**solver_options) forventer individuelle kwargs, ikke en
    # dict. Hver kwarg videresendes til solverens setOptionValue(key, value).
    #
    # NB om mip_rel_gap: 0.001 (0.1%) er for aggressivt for denne problemklasse.
    # MIP-tail kan hænge længe i de sidste procenter. 0.005 (0.5%) er industri-
    # standard for business-case-formål — på 25 mio DKK giver det ±125 kDKK
    # præcision, hvilket er langt mindre end usikkerheden fra [TBC]-antagelserne.
    solver_options: dict = {}
    if is_milp and solver == "highs":
        solver_options = {
            "mip_rel_gap": 0.005,      # 0.5% optimality gap
            "mip_abs_gap": 5000.0,     # 5.000 DKK absolut gap
            "time_limit": 600.0,       # 10 min cap
            "presolve": "on",
            "parallel": "on",
        }
        opts_str = ", ".join(f"{k}={v}" for k, v in solver_options.items())
        print(f"  MILP-mode: solver={solver}, options: {opts_str}")

    status = m.solve(solver_name=solver, **solver_options)
    sol = m.solution

    extracted: list[str] = []

    # --------------------------------------------------------------------------
    # Primalvariable
    # --------------------------------------------------------------------------
    ds = xr.Dataset({"heat_prod": sol["heat_prod"]})
    extracted.append("heat_prod")

    has_storage = "storage_energy" in sol.data_vars
    for var in ("storage_energy", "charge", "discharge"):
        if var in sol.data_vars:
            ds[var] = sol[var]
            extracted.append(var)

    # Netto-ladeeffekt (positiv = oplader, negativ = aflader)
    if "charge" in ds and "discharge" in ds:
        ds["storage_net"] = ds["charge"] - ds["discharge"]
        extracted.append("storage_net")

    # UC-variable (kun i MILP-mode)
    for var in ("commit", "startup", "shutdown"):
        if var in sol.data_vars:
            ds[var] = sol[var]
            extracted.append(var)

    # Balancing-variable (trin 8.2/8.3a + session 12 trin B) — én
    # r_afrr_<unit> og/eller r_mfrr_<unit> per prækvalificeret enhed per
    # marked. Navnene er dynamiske, så vi scanner solution for prefixer. Dims
    # er (time,) per variabel.
    for var_name in sol.data_vars:
        name_str = str(var_name)
        if (
            name_str.startswith("r_afrr_")
            or name_str.startswith("r_mfrr_")
            # Legacy prefix fra før session 12 trin B (stadig understøttet
            # for bagudkompatibilitet med gamle .nc-artefakter):
            or name_str.startswith("r_up_el_")
        ):
            ds[name_str] = sol[var_name]
            extracted.append(name_str)

    # --------------------------------------------------------------------------
    # Duals / skyggepriser — kun veldefinerede for LP
    # --------------------------------------------------------------------------
    if is_milp:
        print("  MILP-mode: skyggepriser springes over (ikke veldefinerede for MILP).")
    else:
        dual_heat = _get_constraint_dual(m, "heat_balance")
        if dual_heat is not None:
            # Normalisér fortegn: vi vil have "værdi af en ekstra MWh varme".
            # Med binding heat_prod + discharge − charge == demand og minimering
            # giver Linopy dual med positivt fortegn = omkostning ved ekstra
            # efterspørgsel. Det ér marginalprisen — ingen fortegnsflip.
            ds["shadow_price_heat"] = dual_heat
            extracted.append("shadow_price_heat")
        else:
            print("  ADVARSEL: skyggepris for heat_balance kunne ikke udtrækkes.")

        if has_storage:
            dual_storage = _get_constraint_dual(m, "storage_dynamics")
            if dual_storage is not None:
                ds["shadow_price_storage"] = dual_storage
                extracted.append("shadow_price_storage")

    # --------------------------------------------------------------------------
    # Attributter
    # --------------------------------------------------------------------------
    ds.attrs["objective_value"] = float(m.objective.value)
    ds.attrs["status"] = str(status)
    ds.attrs["case_name"] = cfg.meta.get("case_name", "unnamed")
    ds.attrs["solver"] = solver
    ds.attrs["is_milp"] = int(is_milp)    # NetCDF tillader ikke bool-attr i alle engines

    print(f"  Udtrukket fra løsning: {', '.join(extracted)}")
    if "shadow_price_heat" in ds:
        sp = ds["shadow_price_heat"]
        print(
            f"  Skyggepris varme — min/gns/max: "
            f"{float(sp.min()):.1f} / {float(sp.mean()):.1f} / {float(sp.max()):.1f} DKK/MWh"
        )

    return ds
