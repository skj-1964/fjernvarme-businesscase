"""
LP/MILP-model for fjernvarme dispatch (trin 1 + trin 3).

Vektoriseret formulering i Linopy:
  - Varmebalance for hver time
  - Varmelagerdynamik med shift(time=1)
  - Målfunktion: brændsel + el (forbrug/produktion) + tariffer/afgifter + variabel O&M
  - Unit commitment for enheder med uc_enabled=True (trin 3)

Trin 1 = LP, ingen start/stop eller min-last håndhævet som binær variabel.
Trin 3 = MILP, aktiveret per-enhed via Unit.uc_enabled. Enheder uden flaget
beholder deres LP-behandling; modellen bliver automatisk MILP når mindst
én enhed har uc_enabled = True.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import xarray as xr
import linopy as lp

from .config import CaseConfig, Unit, Storage
from .unit_commitment import add_unit_commitment
from .balancing import add_balancing_reserves

# ------------------------------------------------------------------------------
# Marginalomkostning per enhed — effektiv DKK/MWh_varme tidsserie
# ------------------------------------------------------------------------------

def compute_marginal_cost(
    unit: Unit,
    cfg: CaseConfig,
    data: xr.Dataset,
) -> xr.DataArray:
    """
    Marginal omkostning per MWh varmeproduktion.

    For brændselsenheder (halm, flis, gas):
        mc = fuel_price / eta + CO2_cost + var_om − alpha × (spot − tariff_prod)

    For elforbrugende enheder (VP, elkedel):
        mc = neg_alpha_t × (spot + tariff_cons + elafgift) + var_om
        hvor neg_alpha_t = 1/COP.
        Hvis unit.cop_curve er sat: COP er tidsvarierende funktion af t_ambient.
        Ellers: COP = -1/unit.alpha (konstant).

    For overskudsvarme:
        mc = fuel_price (prissat som "brændsel") + var_om

    Returnerer xarray DataArray med koord 'time'.

    NOTE: signatur ændret fra (unit, cfg, spot) → (unit, cfg, data) for at give
    adgang til t_ambient ved COP(T)-beregning. Data skal indeholde 'spot_price'
    og (når cop_curve bruges) 't_ambient'.
    """
    spot = data["spot_price"]
    om = unit.var_om

    if unit.fuel == "electricity":
        # Rent elforbrugende enhed (VP, elkedel)
        if unit.cop_curve is not None:
            # Tidsvarierende COP → tidsvarierende neg_alpha
            if "t_ambient" not in data.data_vars:
                raise ValueError(
                    f"{unit.name}: cop_curve sat, men 't_ambient' mangler i data. "
                    f"Brug load_external_data() eller generate_dummy_data()."
                )
            cop_t = unit.cop_curve.evaluate(data["t_ambient"])
            neg_alpha = 1.0 / cop_t                    # [time], positiv
        else:
            # Konstant alpha — fallback-regime (bruges af elkedler og ældre cases)
            neg_alpha = -unit.alpha                    # skalar, positiv for el-forbruger

        el_cost_per_mwh_heat = neg_alpha * (
            spot + cfg.electricity.tariff_consumption_flat + cfg.electricity.electricity_tax
        )
        return el_cost_per_mwh_heat + om

    elif unit.fuel == "waste_heat":
        # Fast aftalt pris per MWh varme leveret
        return xr.full_like(spot, cfg.prices.fuel_price(unit.fuel) + om)

    else:
        # Brændselsenhed (halm, naturgas)
        fuel_price = cfg.prices.fuel_price(unit.fuel)
        fuel_cost = fuel_price / unit.eta_fuel_to_heat

        # CO2-tillæg (kun naturgas har co2_emissions > 0)
        co2_cost = (
            unit.co2_emissions_per_mwh_fuel
            * cfg.prices.co2_eua
            / unit.eta_fuel_to_heat
        )

        # El-indtægt for CHP (alpha > 0)
        if unit.alpha > 0:
            el_revenue_per_mwh_heat = unit.alpha * (
                spot - cfg.electricity.tariff_production_flat
            )
            return xr.full_like(spot, fuel_cost + co2_cost + om) - el_revenue_per_mwh_heat
        else:
            return xr.full_like(spot, fuel_cost + co2_cost + om)


# ------------------------------------------------------------------------------
# Modelbygning
# ------------------------------------------------------------------------------

def build_model(cfg: CaseConfig, data: xr.Dataset) -> lp.Model:
    """
    Byg LP-model (evt. MILP) med alle enheder og lagre fra konfigurationen.

    Bindinger:
      [1] Varmebalance:  Σ produktion + Σ afladning = efterspørgsel + Σ ladning
      [2] Lagerdynamik:  e_t = (1−δ) e_{t−1} + charge_t − discharge_t
      [3] Cyklusbinding: e_slut = e_start
      [4] Unit commitment (hvis nogen enhed har uc_enabled=True)

    Variable:
      heat_prod[unit, time]          ∈ [0, p_max_heat]
      storage_energy[storage, time]  ∈ [0, e_max]
      charge, discharge              ∈ [0, p_max_ch/dis]
      commit, startup, shutdown      ∈ {0,1}   (kun for UC-enheder)

    Sideeffekt: sætter m._has_uc (bool) så solve.py kan vælge MILP-solver-options.
    """
    m = lp.Model()
    time_coord = data.time.values                   # numpy datetime64 — fælles alignment

    # Filtrér: disabled enheder og lagre udelades helt fra modellen
    unit_names = [u for u, unit in cfg.units.items() if unit.enabled]
    storage_names = [s for s, stor in cfg.storage.items() if stor.enabled]

    disabled_units = [u for u in cfg.units if not cfg.units[u].enabled]
    disabled_storages = [s for s in cfg.storage if not cfg.storage[s].enabled]
    if disabled_units:
        print(f"  Deaktiverede enheder: {', '.join(disabled_units)}")
    if disabled_storages:
        print(f"  Deaktiverede lagre: {', '.join(disabled_storages)}")

    if not unit_names:
        raise ValueError("Ingen aktive produktionsenheder — modellen er tom.")

    # --------------------------------------------------------------------------
    # Variable: produktion
    # --------------------------------------------------------------------------
    p_max = xr.DataArray(
        [cfg.units[u].p_max_heat for u in unit_names],
        coords={"unit": unit_names}, dims="unit",
    )
    heat_prod = m.add_variables(
        lower=0.0,
        upper=p_max,                        # broadcastes over time
        coords=[("unit", unit_names), ("time", time_coord)],
        name="heat_prod",
    )

    # --------------------------------------------------------------------------
    # Variable: lager (kun hvis der er aktive lagre)
    # --------------------------------------------------------------------------
    has_storage = len(storage_names) > 0
    if has_storage:
        e_max = xr.DataArray(
            [cfg.storage[s].e_max_mwh for s in storage_names],
            coords={"storage": storage_names}, dims="storage",
        )
        p_ch_max = xr.DataArray(
            [cfg.storage[s].p_max_charge_mw for s in storage_names],
            coords={"storage": storage_names}, dims="storage",
        )
        p_dis_max = xr.DataArray(
            [cfg.storage[s].p_max_discharge_mw for s in storage_names],
            coords={"storage": storage_names}, dims="storage",
        )
        storage_energy = m.add_variables(
            lower=0.0, upper=e_max,
            coords=[("storage", storage_names), ("time", time_coord)],
            name="storage_energy",
        )
        charge = m.add_variables(
            lower=0.0, upper=p_ch_max,
            coords=[("storage", storage_names), ("time", time_coord)],
            name="charge",
        )
        discharge = m.add_variables(
            lower=0.0, upper=p_dis_max,
            coords=[("storage", storage_names), ("time", time_coord)],
            name="discharge",
        )

    # --------------------------------------------------------------------------
    # NB: Varmebalance ([1]) bygges EFTER UC og balancing — den skal kunne
    # inkludere heat_reduction_expr fra balancing-modulet hvis aktiveret.
    # Se nederst i funktionen.
    # --------------------------------------------------------------------------

    # --------------------------------------------------------------------------
    # [2] Lagerdynamik — vektoriseret med shift(time=1)
    # --------------------------------------------------------------------------
    if has_storage:
        delta = xr.DataArray(
            [cfg.storage[s].self_discharge_per_hour for s in storage_names],
            coords={"storage": storage_names}, dims="storage",
        )

        e_prev = storage_energy.shift(time=1)
        dyn = storage_energy - (1 - delta) * e_prev - charge + discharge
        m.add_constraints(
            dyn.sel(time=time_coord[1:]) == 0,
            name="storage_dynamics",
        )

        # Startbetingelse: e[t=0] = e_initial
        e_init = xr.DataArray(
            [cfg.storage[s].e_initial_mwh for s in storage_names],
            coords={"storage": storage_names}, dims="storage",
        )
        m.add_constraints(
            storage_energy.sel(time=time_coord[0]) == e_init,
            name="storage_initial",
        )

        # --------------------------------------------------------------------------
        # [3] Cyklusbinding: e[t=-1] = e_initial (kun aktive, cyklus-aktiverede lagre)
        # --------------------------------------------------------------------------
        for s_name in storage_names:
            s = cfg.storage[s_name]
            if s.cycle_binding:
                m.add_constraints(
                    storage_energy.sel(storage=s_name, time=time_coord[-1]) == s.e_initial_mwh,
                    name=f"storage_cycle_{s_name}",
                )

    # --------------------------------------------------------------------------
    # [4] Unit commitment (trin 3) — aktiveres for enheder med uc_enabled=True.
    # Returnerer None hvis ingen UC-enheder findes, i så fald forbliver modellen
    # ren LP.
    #
    # MILP-detektion i solve.py sker via constraint-navne (søger efter
    # "uc_state_transition" i m.constraints) — ikke via instans-attribut,
    # fordi linopy.Model bruger __slots__ og ikke tillader ekstra attributter.
    # --------------------------------------------------------------------------
    uc = add_unit_commitment(m, cfg, data, heat_prod)

    # --------------------------------------------------------------------------
    # [5] Balancemarkeder (trin 8.2/8.3a) — aFRR up-reserver for prækvalificerede
    # enheder. Returnerer None hvis balancing-data mangler (kør med
    # --with-balancing). Tilføjer footroom-constraints og returnerer:
    #   - kapacitets- og aktiveringsindtægt (til objektiv, FRATRÆKKES)
    #   - heat_reduction_expr (forventet varmereduktion pga. aktivering,
    #     inkluderes i varmebalancen nedenfor)
    # --------------------------------------------------------------------------
    bal = add_balancing_reserves(m, cfg, data, heat_prod)

    # --------------------------------------------------------------------------
    # [1] Varmebalance per time — bygges NU hvor bal og uc er kendte.
    # Alle linopy-udtryk samles på venstresiden; xarray-data på højresiden.
    #
    # Hvis balancing er aktivt, trækker vi den forventede varmereduktion
    # (α·COP·r_up_el, summeret over enheder) fra produktionssiden — det er
    # den varme vi *ikke* leverer pga. forventet aktivering af op-reserven.
    # --------------------------------------------------------------------------
    prod_side = heat_prod.sum("unit")
    if bal is not None:
        prod_side = prod_side - bal["heat_reduction_expr"]
    if has_storage:
        m.add_constraints(
            prod_side + discharge.sum("storage") - charge.sum("storage")
            == data["heat_demand"],
            name="heat_balance",
        )
    else:
        m.add_constraints(
            prod_side == data["heat_demand"],
            name="heat_balance",
        )

    # --------------------------------------------------------------------------
    # Målfunktion: total driftsomkostning (+ UC-omkostninger, − balancing-indtægt)
    # --------------------------------------------------------------------------
    mc_per_unit = xr.concat(
        [compute_marginal_cost(cfg.units[u], cfg, data).expand_dims(unit=[u]) for u in unit_names],
        dim="unit",
    )
    # Omkostning = sum over (unit, time) af mc[u,t] * heat_prod[u,t]
    # Linopy variable skal være på venstresiden af multiplikation
    obj = (heat_prod * mc_per_unit).sum()

    if uc is not None and uc["startup_cost_expr"] is not None:
        obj = obj + uc["startup_cost_expr"]
    if bal is not None:
        # Fratrækker kapacitets- OG aktiveringsindtægt fra omkostningen.
        # Aktiveringsindtægten inkluderer både aFRR-aktiveringspris OG sparede
        # forbrugsomkostninger (spot+tarif+afgift) — se balancing.py-docstring.
        # heat_prod·mc regner fuldt elforbrug; den del der spares ved aktivering
        # modregnes via activation_revenue_expr så nettoregnskabet bliver rigtigt.
        obj = obj - bal["capacity_revenue_expr"] - bal["activation_revenue_expr"]

    m.add_objective(obj)

    return m
