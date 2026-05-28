"""
src/balancing.py — aFRR + mFRR reserve-modellering (trin 8.2/8.3a + session 12 trin B).

Scope:
  * Op-regulering via el-forbrugende enheder (VP, elkedel).
    Ned-regulering er marginal (~4 DKK/MW/h på DK1) og udeladt.
    Elproducerende (gasmotor) håndteres i fremtidig udvidelse.
  * To markeder parallelt: aFRR (automatic frequency restoration reserve)
    og mFRR (manual frequency restoration reserve). Hver bud-variabel er
    separat; fælles fysisk footroom-constraint binder summen.
  * Kvalifikation styres per enhed og marked via YAML-flags
    (ancillary.afrr_qualified, ancillary.mfrr_qualified).
  * Max-bud per enhed og marked via YAML
    (ancillary.afrr_max_bid_mw, ancillary.mfrr_max_bid_mw). Beskytter mod
    urealistisk pris-taker-adfærd når enhedens kapacitet er stor ift. marked.

Modelmatematik per enhed i (elforbrugende) og time t:

  r_afrr[i,t]                    >= 0
  r_mfrr[i,t]                    >= 0
  r_afrr[i,t]                    <= afrr_max_bid[i]        [aFRR-loft, hvis sat]
  r_mfrr[i,t]                    <= mfrr_max_bid[i]        [mFRR-loft, hvis sat]
  r_afrr[i,t] + r_mfrr[i,t]      <= p_el_max[i]            [fælles fysisk
                                                            bunden af variabel
                                                            upper-bounds]
  heat_prod[i,t] - COP(t) · (r_afrr[i,t] + r_mfrr[i,t]) >= 0
                                                           [fælles footroom]

Forventet varmereduktion (trækkes fra produktionssiden i varmebalancen i
model.py):

  heat_reduction[t] = Σ_i  COP(t) · (α_afrr(t)·r_afrr[i,t]
                                      + α_mfrr(t)·r_mfrr[i,t])

hvor α(t) ∈ [0,1] er markedets historiske aktiveringsfraktion per time.

Objektiv (minimer omkostning → FRATRÆK indtægt for hver markedsdel):

  obj -= Σ_t  π_cap_afrr(t) · r_afrr[i,t]                  [kap-indtægt aFRR]
  obj -= Σ_t  α_afrr(t) · (π_act_afrr(t) + spot(t) + tarif + afgift)
             · r_afrr[i,t]                                  [akt-indtægt aFRR]
  obj -= Σ_t  π_cap_mfrr(t) · r_mfrr[i,t]                  [kap-indtægt mFRR]
  obj -= Σ_t  α_mfrr(t) · (π_act_mfrr(t) + spot(t) + tarif + afgift)
             · r_mfrr[i,t]                                  [akt-indtægt mFRR]

Parentesen med (π_act + spot + tarif + afgift) fanger at når VP/elkedel
aktiveres *ned*, spares forbrugssiden (spot + tarif + elafgift) ovenpå
aktiveringsprisen. Det fulde forbrug regnes i heat_prod·mc-termen, så
aktiveringsindtægten skal indeholde disse besparelser for at få
nettoregnskabet rigtigt.

Tegnkonvention: r_afrr, r_mfrr måles i elektriske MW. For en VP der forbruger
5 MW el kan den byde op til 5 MW op-regulering ("kan stoppe med at forbruge
op til 5 MW hvis kaldt"). Konvertering til varmeside via COP.

Return-dict fra add_balancing_reserves:

  r_afrr_vars, r_mfrr_vars       — per-enhed bud-variable (dim=time)
  capacity_revenue_expr          — SUM over begge markeder [DKK, sum]
  activation_revenue_expr        — SUM over begge markeder [DKK, sum]
  heat_reduction_expr            — SUM over begge markeder, dim=time [MW varme]
  eligible_units_afrr            — liste af enheder med aFRR-bud
  eligible_units_mfrr            — liste af enheder med mFRR-bud
  r_up_el_vars                   — alias for r_afrr_vars (bagudkompatibilitet)
  eligible_units                 — alias for eligible_units_afrr (bagudkompat.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import xarray as xr
import linopy as lp

from .config import CaseConfig, Unit


# ---------------------------------------------------------------------------
# Markedsspecifikation — én per reserveprodukt (aFRR, mFRR)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _MarketSpec:
    """
    Statisk markedsbeskrivelse. Pakker det minimale der adskiller aFRR og mFRR:
      - var_prefix:    linopy-variabelnavn (fx "r_afrr" → r_afrr_<unit>)
      - cap_price_key: data_var med kapacitetspris [DKK/MW/h]
      - act_price_key: data_var med aktiveringspris [DKK/MWh]
      - alpha_key:     data_var med aktiveringsfraktion [0,1]
      - qualified_attr: attributnavn på Ancillary (fx "afrr_qualified")
      - max_bid_attr:  attributnavn på Ancillary (fx "afrr_max_bid_mw")
      - label:         visningsnavn (fx "aFRR") til logbeskeder
    """
    var_prefix: str
    cap_price_key: str
    act_price_key: str
    alpha_key: str
    qualified_attr: str
    max_bid_attr: str
    label: str


_AFRR = _MarketSpec(
    var_prefix="r_afrr",
    cap_price_key="afrr_cap_up_dkk",
    act_price_key="afrr_act_up_dkk",
    alpha_key="afrr_activation_fraction_up",
    qualified_attr="afrr_qualified",
    max_bid_attr="afrr_max_bid_mw",
    label="aFRR",
)

_MFRR = _MarketSpec(
    var_prefix="r_mfrr",
    cap_price_key="mfrr_cap_up_dkk",
    act_price_key="mfrr_act_up_dkk",
    alpha_key="mfrr_activation_fraction_up",
    qualified_attr="mfrr_qualified",
    max_bid_attr="mfrr_max_bid_mw",
    label="mFRR",
)

MARKETS: tuple[_MarketSpec, ...] = (_AFRR, _MFRR)


# ---------------------------------------------------------------------------
# Hjælpefunktioner
# ---------------------------------------------------------------------------

def _eligible_units_for_market(cfg: CaseConfig, market: _MarketSpec) -> list[Unit]:
    """Filtrér til enheder kvalificerede til dette marked, enabled, elforbrugende."""
    eligible = []
    for unit in cfg.units.values():
        if not unit.enabled:
            continue
        if not getattr(unit.ancillary, market.qualified_attr):
            continue
        if unit.fuel != "electricity":
            # Scope: kun el-forbrugende. Gasmotorer (alpha>0) i senere udvidelse.
            continue
        eligible.append(unit)
    return eligible


def _get_cop_series(unit: Unit, data: xr.Dataset) -> xr.DataArray:
    """Hent COP(t) som xr.DataArray.

    Bruger unit.cop_curve hvis sat (VP), ellers konstant -1/alpha (elkedler).
    Returnerer altid en DataArray med dim 'time' for konsistent broadcasting.
    """
    if unit.cop_curve is not None and "t_ambient" in data.data_vars:
        return unit.cop_curve.evaluate(data["t_ambient"])

    # Fallback: konstant COP fra alpha.
    const_cop = 1.0 / abs(unit.alpha) if unit.alpha != 0 else 1.0
    return xr.DataArray(
        [const_cop] * len(data.time),
        coords={"time": data.time.values},
        dims=["time"],
    )


def _market_data_available(data: xr.Dataset, market: _MarketSpec) -> bool:
    """True hvis kapacitetspris-data_var er tilstede for dette marked."""
    return market.cap_price_key in data.data_vars


def _get_or_zero(data: xr.Dataset, key: str, like: xr.DataArray) -> xr.DataArray:
    """Returnér data[key] hvis til stede, ellers en nul-DataArray med samme dim."""
    if key in data.data_vars:
        return data[key]
    return xr.zeros_like(like)


# ---------------------------------------------------------------------------
# Byg reserver for ét marked
# ---------------------------------------------------------------------------

def _add_market_reserves(
    m: lp.Model,
    market: _MarketSpec,
    eligible: list[Unit],
    data: xr.Dataset,
    el_cost_per_mwh: xr.DataArray,
    apply_max_bid: bool = True,
) -> dict:
    """Byg reserve-variable og -udtryk for ét marked (aFRR eller mFRR).

    Footroom-constraint bygges IKKE her (fælles for alle markeder i caller).

    apply_max_bid: når False springes per-enheds-max-bud-constraints over.
        Bruges når et fælles reserve-loft (cfg.shared_reserve_cap_mw) er aktivt
        og erstatter de separate per-enhed/per-gruppe lofter. Den fysiske
        upper-bound (p_el_max) på variablen bevares uanset.

    Returnerer dict med:
      var_by_unit          {unit_name: lp.Variable}
      capacity_revenue     lp-udtryk (skalar sum)
      activation_revenue   lp-udtryk (skalar sum)
      heat_reduction       lp-udtryk med dim (time,)  eller None hvis tom
      eligible_names       liste af unit-navne
    """
    time_coord = data.time.values

    price_cap = data[market.cap_price_key]       # DKK/MW/h
    alpha = _get_or_zero(data, market.alpha_key, price_cap)       # [0,1]
    price_act = _get_or_zero(data, market.act_price_key, price_cap)  # DKK/MWh

    # Diagnostik — pr. marked
    alpha_mean = float(alpha.mean()) if hasattr(alpha, "mean") else 0.0
    cap_mean = float(price_cap.mean())
    act_mean = float(price_act.mean())
    print(
        f"  {market.label}-data: α gns={alpha_mean:.3f}, "
        f"kap-pris gns={cap_mean:.1f} DKK/MW/h, "
        f"akt-pris gns={act_mean:.1f} DKK/MWh"
    )

    var_by_unit: dict[str, lp.Variable] = {}
    heat_reduction_terms = []
    capacity_revenue_terms = []
    activation_revenue_terms = []

    for unit in eligible:
        cop = _get_cop_series(unit, data)
        p_el_max = float(unit.p_max_heat / cop.min().item())

        var_name = f"{market.var_prefix}_{unit.name}"
        r = m.add_variables(
            lower=0.0,
            upper=p_el_max,
            coords=[("time", time_coord)],
            name=var_name,
        )
        var_by_unit[unit.name] = r

        # Max-bud per enhed og marked (trin A for aFRR, trin B for mFRR).
        # Navngiven constraint for diagnostik; solveren bruger den strammere
        # binding (p_el_max som upper-bound vs max_bid som constraint).
        # Springes over når et fælles reserve-loft erstatter per-enheds-lofterne.
        max_bid = getattr(unit.ancillary, market.max_bid_attr)
        if apply_max_bid and max_bid is not None:
            max_bid = float(max_bid)
            if max_bid > p_el_max:
                print(
                    f"  {market.label}: {unit.name} max_bid={max_bid:.1f} MW "
                    f"> p_el_max={p_el_max:.2f} — fysisk kapacitet binder først"
                )
            else:
                print(
                    f"  {market.label}: {unit.name} max-bud = {max_bid:.1f} MW "
                    f"(fysisk p_el_max = {p_el_max:.2f} MW)"
                )
            m.add_constraints(
                r <= max_bid,
                name=f"{market.var_prefix}_max_bid_{unit.name}",
            )

        # Kapacitetsindtægt [DKK]
        capacity_revenue_terms.append((price_cap * r).sum())

        # Forventet varmereduktion per enhed [MW varme, dim=time]
        #   α · COP · r  = forventet aktiveret el-MW × COP = tabt varme i MW
        heat_reduction_terms.append(alpha * cop * r)

        # Aktiveringsindtægt [DKK]
        # Pr. MWh forventet el-reduktion:
        #   + π_act  (aktiveringspris)
        #   + spot + tarif + elafgift (sparet forbrugsomkostning)
        # gange forventet aktiveret el-volumen α(t) · r[t] · 1h
        activation_revenue_terms.append(
            (alpha * (price_act + el_cost_per_mwh) * r).sum()
        )

    capacity_revenue = sum(capacity_revenue_terms) if capacity_revenue_terms else 0
    activation_revenue = sum(activation_revenue_terms) if activation_revenue_terms else 0

    if heat_reduction_terms:
        heat_reduction = heat_reduction_terms[0]
        for term in heat_reduction_terms[1:]:
            heat_reduction = heat_reduction + term
    else:
        heat_reduction = None

    return {
        "var_by_unit": var_by_unit,
        "capacity_revenue": capacity_revenue,
        "activation_revenue": activation_revenue,
        "heat_reduction": heat_reduction,
        "eligible_names": [u.name for u in eligible],
    }


# ---------------------------------------------------------------------------
# Fælles footroom-constraint (summerer aFRR + mFRR bud per enhed)
# ---------------------------------------------------------------------------

def _add_footroom_constraints(
    m: lp.Model,
    cfg: CaseConfig,
    data: xr.Dataset,
    heat_prod,
    afrr_vars: dict,
    mfrr_vars: dict,
) -> None:
    """Footroom: produktion skal dække fuldaktivering af ALLE markedsdeles bud.

    For hver enhed i der byder i mindst ét marked:
      heat_prod[i,t] >= COP[t] · (r_afrr[i,t] + r_mfrr[i,t])

    Enheder der kun byder i ét marked får den anden term udeladt (ikke sat
    til 0, bare ikke summeret med).
    """
    all_unit_names = sorted(set(afrr_vars.keys()) | set(mfrr_vars.keys()))
    if not all_unit_names:
        return

    for unit_name in all_unit_names:
        unit = cfg.units[unit_name]
        cop = _get_cop_series(unit, data)
        p_heat_u = heat_prod.sel(unit=unit_name)

        reserve_sum = None
        for vars_dict in (afrr_vars, mfrr_vars):
            r = vars_dict.get(unit_name)
            if r is None:
                continue
            reserve_sum = r if reserve_sum is None else (reserve_sum + r)

        if reserve_sum is None:
            continue

        m.add_constraints(
            p_heat_u - cop * reserve_sum >= 0,
            name=f"r_up_footroom_{unit_name}",
        )


# ---------------------------------------------------------------------------
# Gruppe-max-bud-constraints (operatør-prækvalificeret samlet kapacitet)
# ---------------------------------------------------------------------------

def _add_group_constraints(
    m: lp.Model,
    cfg: CaseConfig,
    market: _MarketSpec,
    var_by_unit: dict[str, lp.Variable],
) -> None:
    """Tilføj gruppe-max-bud-constraints for dette marked.

    For hver AncillaryGroup med max-bud sat for dette marked:
        Σ_{i ∈ group ∩ eligible} r_<market>[i,t] ≤ max-bud    ∀t

    Enheder i gruppen der ikke er kvalificerede/enabled/elforbrugende
    (dvs. ikke har variable i var_by_unit) ignoreres stiltiende. Hvis
    ingen gruppe-enheder har variable, springes gruppen over.

    Gruppe-constraint tilføjes UDOVER eventuelle per-enhed-max-bud;
    solveren bruger den strammere binding.
    """
    for group in cfg.ancillary_groups.values():
        max_bid = getattr(group, market.max_bid_attr)
        if max_bid is None:
            continue

        group_vars = [var_by_unit[u] for u in group.units if u in var_by_unit]
        active_in_market = [u for u in group.units if u in var_by_unit]
        if not group_vars:
            print(
                f"  {market.label}: gruppe '{group.name}' har ingen aktive "
                f"enheder i dette marked — springes over"
            )
            continue

        print(
            f"  {market.label}: gruppe '{group.name}' max-bud = {max_bid:.1f} MW "
            f"for {active_in_market}"
        )
        group_sum = group_vars[0]
        for v in group_vars[1:]:
            group_sum = group_sum + v

        m.add_constraints(
            group_sum <= float(max_bid),
            name=f"{market.var_prefix}_group_{group.name}",
        )


# ---------------------------------------------------------------------------
# Fælles reserve-loft — ét loft over begge markeder og alle bydende enheder
# ---------------------------------------------------------------------------

def _add_shared_cap_constraint(
    m: lp.Model,
    cap_mw: float,
    afrr_vars: dict,
    mfrr_vars: dict,
) -> None:
    """Ét fælles reserve-loft på summen af ALLE bud, per time:

        Σ_i (r_afrr[i,t] + r_mfrr[i,t]) ≤ cap_mw    ∀t

    Repræsenterer en samlet prækvalificeret reservekapacitet (Billund: 14 MW
    frit fordelt mellem aFRR og mFRR — session 19 §4.2). Erstatter de separate
    per-enhed (Ancillary.*_max_bid_mw) og per-gruppe (AncillaryGroup) lofter,
    som caller derfor springer over når dette loft er aktivt.

    VIGTIGT: dette er ÉT loft på den samlede sum — ikke cap_mw på hvert marked.
    Modellen kan altså frit fordele de 14 MW mellem aFRR og mFRR, men summen
    over begge markeder og alle enheder må ikke overstige cap_mw i nogen time.

    Footroom-bindingen (produktion ≥ COP · samlet bud per enhed) tilføjes
    separat i _add_footroom_constraints og bevares uændret.
    """
    all_vars = list(afrr_vars.values()) + list(mfrr_vars.values())
    if not all_vars:
        return

    total = all_vars[0]
    for v in all_vars[1:]:
        total = total + v

    m.add_constraints(total <= float(cap_mw), name="shared_reserve_cap")

    n_afrr = len(afrr_vars)
    n_mfrr = len(mfrr_vars)
    print(
        f"  Fælles reserve-loft: Σ(aFRR+mFRR) ≤ {cap_mw:.1f} MW per time "
        f"({n_afrr} aFRR-bud + {n_mfrr} mFRR-bud, frit fordelt). "
        f"Per-enheds/-gruppe-lofter er sprunget over."
    )


# ---------------------------------------------------------------------------
# Hovedfunktion — tilføjer reserver til modellen
# ---------------------------------------------------------------------------

def add_balancing_reserves(
    m: lp.Model,
    cfg: CaseConfig,
    data: xr.Dataset,
    heat_prod,
) -> Optional[dict]:
    """Tilføj aFRR + mFRR up-reserver til modellen.

    Args:
        m: linopy-modellen under opbygning
        cfg: CaseConfig
        data: xr.Dataset med balance-priser.
          - Uden afrr_cap_up_dkk OG mfrr_cap_up_dkk → returnér None
          - Med kun et af markederne → byg kun det marked
        heat_prod: multi-dim linopy-variabel (unit, time)

    Returns:
        dict med opsummerede udtryk (se modulets docstring) eller None hvis
        ingen markedsdata og ingen enheder kvalificerede.
    """
    afrr_available = _market_data_available(data, _AFRR)
    mfrr_available = _market_data_available(data, _MFRR)

    if not afrr_available and not mfrr_available:
        possibly_eligible = set()
        for m_spec in MARKETS:
            for u in _eligible_units_for_market(cfg, m_spec):
                possibly_eligible.add(u.name)
        if possibly_eligible:
            unit_list = ", ".join(sorted(possibly_eligible))
            print(
                f"  Balancing: kvalificerede enheder {{{unit_list}}} men "
                "ingen balancing-data i kørsel — spring over. "
                "Kør med --with-balancing for at aktivere."
            )
        return None

    # Forbrugsside-omkostning der spares ved op-regulering (aktivering NED af
    # el-forbrug) — fælles for aFRR og mFRR.
    el_cost_per_mwh = (
        data["spot_price"]
        + cfg.electricity.tariff_consumption_flat
        + cfg.electricity.electricity_tax
    )

    per_market_results: dict[str, Optional[dict]] = {}
    any_eligible = False

    # Fælles reserve-loft (Billunds prækvalificering). Når sat erstatter det
    # de separate per-enhed/per-gruppe lofter: per-enheds-max-bud springes over
    # i _add_market_reserves, og gruppe-constraints springes over her i caller.
    shared_cap = getattr(cfg, "shared_reserve_cap_mw", None)
    apply_max_bid = shared_cap is None

    for market, available in ((_AFRR, afrr_available), (_MFRR, mfrr_available)):
        if not available:
            per_market_results[market.label] = None
            continue
        eligible = _eligible_units_for_market(cfg, market)
        if not eligible:
            per_market_results[market.label] = None
            continue

        any_eligible = True
        print(
            f"  {market.label} aktivt: {len(eligible)} enheder "
            f"({', '.join(u.name for u in eligible)})"
        )
        per_market_results[market.label] = _add_market_reserves(
            m, market, eligible, data, el_cost_per_mwh,
            apply_max_bid=apply_max_bid,
        )
        # Gruppe-constraints per marked (kun når INTET fælles loft er sat —
        # det fælles loft erstatter gruppe-lofterne).
        if shared_cap is None:
            _add_group_constraints(
                m, cfg, market, per_market_results[market.label]["var_by_unit"],
            )

    if not any_eligible:
        return None

    afrr_res = per_market_results.get("aFRR")
    mfrr_res = per_market_results.get("mFRR")

    afrr_vars = afrr_res["var_by_unit"] if afrr_res else {}
    mfrr_vars = mfrr_res["var_by_unit"] if mfrr_res else {}

    # Fælles footroom — bindes på sum af alle bud per enhed
    _add_footroom_constraints(m, cfg, data, heat_prod, afrr_vars, mfrr_vars)

    # Fælles reserve-loft på summen over begge markeder (hvis sat) — tilføjes
    # EFTER footroom, så begge bindinger gælder samtidigt.
    if shared_cap is not None:
        _add_shared_cap_constraint(m, shared_cap, afrr_vars, mfrr_vars)

    # Totale udtryk (summer over aktive markeder)
    total_capacity = 0
    total_activation = 0
    for res in per_market_results.values():
        if res is None:
            continue
        total_capacity = total_capacity + res["capacity_revenue"]
        total_activation = total_activation + res["activation_revenue"]

    # heat_reduction_expr — summer over markeder (og over enheder, sket inde i _add_market_reserves)
    reductions = [res["heat_reduction"] for res in per_market_results.values()
                  if res is not None and res["heat_reduction"] is not None]
    if reductions:
        heat_reduction_expr = reductions[0]
        for r in reductions[1:]:
            heat_reduction_expr = heat_reduction_expr + r
    else:
        heat_reduction_expr = None

    return {
        "r_afrr_vars": afrr_vars,
        "r_mfrr_vars": mfrr_vars,
        "capacity_revenue_expr": total_capacity,
        "activation_revenue_expr": total_activation,
        "heat_reduction_expr": heat_reduction_expr,
        "eligible_units_afrr": afrr_res["eligible_names"] if afrr_res else [],
        "eligible_units_mfrr": mfrr_res["eligible_names"] if mfrr_res else [],
        # Bagudkompatibilitet (læses ikke af model.py, men af gamle scripts):
        "r_up_el_vars": afrr_vars,
        "eligible_units": afrr_res["eligible_names"] if afrr_res else [],
    }


# ---------------------------------------------------------------------------
# Post-solve helpers — kaldes fra reporting.py når relevant
# ---------------------------------------------------------------------------

def _summarize_one_market(
    result: xr.Dataset,
    data: xr.Dataset,
    market: _MarketSpec,
) -> dict[str, dict]:
    """Udtræk reserve-statistik for ét marked (aFRR eller mFRR).

    Tom dict hvis ingen variable i resultet.
    """
    prefix = f"{market.var_prefix}_"
    r_vars = [v for v in result.data_vars if str(v).startswith(prefix)]
    if not r_vars:
        return {}

    price_cap = data.get(market.cap_price_key)
    price_act = data.get(market.act_price_key)
    alpha = data.get(market.alpha_key)
    spot = data.get("spot_price")

    out = {}
    for var_name in r_vars:
        unit_name = str(var_name).replace(prefix, "")
        r_series = result[var_name]
        entry = {
            "mean_bid_mw": float(r_series.mean()),
            "max_bid_mw": float(r_series.max()),
            "mwh_bid_year": float(r_series.sum()),  # MW · timer
            "hours_bidding": int((r_series > 0.01).sum()),
        }
        if price_cap is not None:
            entry["capacity_revenue_dkk"] = float((r_series * price_cap).sum())
        if alpha is not None and price_act is not None and spot is not None:
            activated_mwh = float((alpha * r_series).sum())
            entry["expected_activated_mwh"] = activated_mwh
            entry["activation_price_revenue_dkk"] = float(
                (alpha * price_act * r_series).sum()
            )
        out[unit_name] = entry
    return out


def summarize_reserves(result: xr.Dataset, data: xr.Dataset) -> Optional[dict]:
    """Udtræk reserveværdier efter solve — dual-produkt version.

    Returnerer:
        {"aFRR": {unit_name: {...}}, "mFRR": {unit_name: {...}}}
    eller None hvis ingen reservevariable findes.
    """
    out = {}
    for market in MARKETS:
        market_out = _summarize_one_market(result, data, market)
        if market_out:
            out[market.label] = market_out
    return out if out else None


def print_reserve_summary(summary: dict):
    """Print tabel med kapacitets- og aktiveringsindtægt per marked og enhed."""
    if not summary:
        print("(ingen reserver i modellen)")
        return

    grand_total_cap = 0.0
    grand_total_act = 0.0

    for market_label, market_summary in summary.items():
        if not market_summary:
            continue
        print(f"\n=== {market_label.upper()} UP RESERVE-SAMMENDRAG ===")
        total_cap = 0.0
        total_act = 0.0
        for unit_name, stats in market_summary.items():
            print(
                f"  {unit_name}: "
                f"gns bid = {stats['mean_bid_mw']:.2f} MW, "
                f"max = {stats['max_bid_mw']:.2f} MW, "
                f"timer m. bid = {stats['hours_bidding']}, "
                f"MW-h år = {stats['mwh_bid_year']:.0f}"
            )
            if "capacity_revenue_dkk" in stats:
                rev = stats["capacity_revenue_dkk"]
                total_cap += rev
                print(f"    kapacitetsindtægt: {rev/1e6:.3f} mio DKK/år")
            if "expected_activated_mwh" in stats:
                mwh = stats["expected_activated_mwh"]
                rev = stats["activation_price_revenue_dkk"]
                total_act += rev
                print(
                    f"    forv. aktiveret el: {mwh:,.0f} MWh/år, "
                    f"aktiveringsprisindtægt: {rev/1e6:.3f} mio DKK/år"
                )
        if total_cap > 0 or total_act > 0:
            print(f"  {market_label} TOTAL kapacitet:      {total_cap/1e6:.3f} mio DKK/år")
            if total_act > 0:
                print(f"  {market_label} TOTAL aktiveringspris: {total_act/1e6:.3f} mio DKK/år")
        grand_total_cap += total_cap
        grand_total_act += total_act

    if len(summary) > 1:
        print()
        print(f"  SAMLET kapacitet (aFRR + mFRR):      {grand_total_cap/1e6:.3f} mio DKK/år")
        print(f"  SAMLET aktiveringspris (aFRR + mFRR): {grand_total_act/1e6:.3f} mio DKK/år")
        print(
            f"  (OBS: sparede forbrugsomkostninger ved aktivering "
            f"modregnes indirekte via heat_prod·mc-termen — ikke vist her)"
        )
