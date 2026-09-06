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

import numpy as np
import pandas as pd
import xarray as xr

from src.tariff import resolve_consumption_tariff
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
    # Nye serier til activation_value-metoden (forudberegnet i datalaget):
    #   av_key:          DKK pr. reserveret MW pr. time (BRUTTO indtægt;
    #                    p_act + spot + el_cost_flat — bruges i objektivet)
    #   act_payment_key: DKK pr. reserveret MW pr. time (NETTO aktiverings-
    #                    betaling; kun p_act). Diagnostik/rapportering.
    #   clear_key:       andel af timen hvor buddet clearer [0,1] (varmeside-α)
    act_value_key: str = ""
    act_payment_key: str = ""
    clear_fraction_key: str = ""
    # Nøgle til reservation_gate-config pr. marked ('afrr' | 'mfrr').
    gate_key: str = ""


_AFRR = _MarketSpec(
    var_prefix="r_afrr",
    cap_price_key="afrr_cap_up_dkk",
    act_price_key="afrr_act_up_dkk",
    alpha_key="afrr_activation_fraction_up",
    qualified_attr="afrr_qualified",
    max_bid_attr="afrr_max_bid_mw",
    label="aFRR",
    act_value_key="afrr_activation_value_up",
    act_payment_key="afrr_activation_payment_up",
    clear_fraction_key="afrr_clear_fraction_up",
    gate_key="afrr",
)

_MFRR = _MarketSpec(
    var_prefix="r_mfrr",
    cap_price_key="mfrr_cap_up_dkk",
    act_price_key="mfrr_act_up_dkk",
    alpha_key="mfrr_activation_fraction_up",
    qualified_attr="mfrr_qualified",
    max_bid_attr="mfrr_max_bid_mw",
    label="mFRR",
    act_value_key="mfrr_activation_value_up",
    act_payment_key="mfrr_activation_payment_up",
    clear_fraction_key="mfrr_clear_fraction_up",
    gate_key="mfrr",
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
    method: str = "legacy",
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

    # Activation_value-serier (forudberegnet i datalaget, kun brugt når
    # method == 'activation_value'). Nul-fallback hvis ikke til stede.
    av = _get_or_zero(data, market.act_value_key, price_cap)              # DKK/MW/h
    clear_frac = _get_or_zero(data, market.clear_fraction_key, price_cap)  # [0,1]

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

        # Onset-gate: før available_from må enheden ikke byde reserver.
        # Bygger en eksogen per-tids øvre grænse (0 før onset, p_el_max fra og
        # med onset) og binder reserve-variablen til den. Rammer KUN buddet —
        # varmedispatch er urørt. Enhedens varmedispatch er urørt; gaten
        # forhindrer kun reservationen i intervaller før idriftsættelsen.
        onset = getattr(unit.ancillary, "available_from", None)
        if onset is not None:
            onset_ts = np.datetime64(str(onset))
            available = time_coord >= onset_ts          # bool, dim time
            gate = xr.DataArray(
                np.where(available, p_el_max, 0.0),
                coords={"time": time_coord},
                dims=["time"],
            )
            m.add_constraints(
                r <= gate,
                name=f"{market.var_prefix}_onset_gate_{unit.name}",
            )
            n_open = int(available.sum())
            n_total = len(time_coord)
            print(
                f"  {market.label}: {unit.name} onset-gate available_from="
                f"{onset} → byder kun {n_open}/{n_total} intervaller "
                f"({n_open/n_total*100:.1f}%), 0 før onset"
            )

        # Budvindue (punkt g): uden for vinduet afgives intet bud.
        vindue = _bid_window_mask(unit, time_coord)
        if vindue is not None:
            m.add_constraints(
                r <= xr.where(vindue, p_el_max, 0.0),
                name=f"{market.var_prefix}_bid_window_{unit.name}",
            )
            n_aabne = int(vindue.sum())
            print(
                f"  {market.label}: {unit.name} budvindue → byder i "
                f"{n_aabne}/{len(time_coord)} intervaller "
                f"({n_aabne/len(time_coord)*100:.1f}%)"
            )

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

        # Forventet varmereduktion + aktiveringsindtægt — metodeafhængigt.
        if method == "activation_value":
            # Ny (kovarians-korrekt): av[t] er DKK pr. reserveret MW pr. time,
            # forudberegnet fra sub-time-priser. clear_frac[t] er andelen af
            # timen buddet clearer → varmeside-α.
            heat_reduction_terms.append(clear_frac * cop * r)
            activation_revenue_terms.append((av * r).sum())
        else:
            # Gammel (E[α]×E[p]): time-midlet α × time-midlet pris.
            #   varmereduktion = α · COP · r
            #   indtægt = α · (π_act + spot + tarif + afgift) · r
            heat_reduction_terms.append(alpha * cop * r)
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


def _bid_window_mask(unit, time_coord) -> Optional[xr.DataArray]:
    """Boolsk maske: må enheden afgive bud i dette interval?

    Punkt (g). Vinduet er en driftsbeslutning, ikke en prisrespons. Billund
    byder ikke elkedlen i kapacitetsmarkedet om sommeren, fordi tankene ikke
    kan optage den produktion, et vundet bud tvinger frem, og byder om sommeren
    kun varmepumpen og kun i dagtimerne.

    Måned og time slås op på LOKAL tid. Modellens akse er UTC, og en
    UTC-baseret nøgle ville forskyde vinduet en time om sommeren — præcis den
    årstid, reglen handler om.

    None = ingen begrænsning (uændret adfærd for alle eksisterende cases).
    """
    window = getattr(unit.ancillary, "bid_window", None)
    if not window:
        return None
    vaerdier = getattr(time_coord, "values", time_coord)
    lokal = pd.DatetimeIndex(vaerdier).tz_localize("UTC").tz_convert(
        "Europe/Copenhagen"
    )
    tilladt = np.ones(len(lokal), dtype=bool)
    months = window.get("months")
    if months is not None:
        tilladt &= np.isin(lokal.month, list(months))
    hours = window.get("hours_local")
    if hours is not None:
        tilladt &= np.isin(lokal.hour, list(hours))
    return xr.DataArray(tilladt, coords={"time": vaerdier}, dims=["time"])

def _add_per_unit_caps(
    m: lp.Model,
    caps,  # AncillaryCaps
    afrr_vars: dict,
    mfrr_vars: dict,
) -> None:
    """Per-enheds-lofter på reservationen, per time.

    To uafhængige former, der begge håndhæves når de er sat:

        (1) samlet:      r_afrr[i,t] + r_mfrr[i,t] ≤ per_unit_mw[i]        ∀t
        (2) per marked:  r_afrr[i,t] ≤ per_unit_market_mw[i]["afrr"]       ∀t
                         r_mfrr[i,t] ≤ per_unit_market_mw[i]["mfrr"]       ∀t

    (1) er prækvalificeringen: hvor meget eloptag enheden må binde i alt.
    (2) er værkets egen fordeling mellem markederne. Billund (John 26/8 2026):
    VP prækvalificeret til 5,52 MW, men bydes med 2 MW i aFRR og 3 MW i mFRR.
    Den strammere binder; de er ikke ment som alternativer til hinanden.

    Håndhæves ALTID når sat — uafhængigt af det samlede loft (total_mw).
    """
    for unit_name, cap_mw in (caps.per_unit_mw or {}).items():
        terms = [d[unit_name] for d in (afrr_vars, mfrr_vars) if unit_name in d]
        if not terms:
            continue
        s = terms[0]
        for term in terms[1:]:
            s = s + term
        m.add_constraints(s <= float(cap_mw), name=f"per_unit_cap_{unit_name}")
        print(
            f"  Per-enheds-loft: {unit_name} (aFRR+mFRR) ≤ {float(cap_mw):.1f} MW/time"
        )

    vars_by_market = {"afrr": afrr_vars, "mfrr": mfrr_vars}
    label_by_market = {"afrr": "aFRR", "mfrr": "mFRR"}
    for unit_name, per_market in (getattr(caps, "per_unit_market_mw", None) or {}).items():
        for market_key, cap_mw in per_market.items():
            if cap_mw is None:
                continue
            market_vars = vars_by_market[market_key]
            if unit_name not in market_vars:
                # Enheden er ikke kvalificeret til dette marked i denne case.
                # Ikke en fejl — loftet er blot uden virkning.
                continue
            m.add_constraints(
                market_vars[unit_name] <= float(cap_mw),
                name=f"per_unit_market_cap_{unit_name}_{market_key}",
            )
            print(
                f"  Per-markeds-loft: {unit_name} {label_by_market[market_key]} "
                f"≤ {float(cap_mw):.1f} MW/time"
            )


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
# CM-pris-gate på reservationen (Spor B = driven, Spor A = bound)
# ---------------------------------------------------------------------------


def _available_bid_capacity(cfg, market, eligible, data, caps) -> xr.DataArray:
    """Hvor meget kan der overhovedet bydes i dette marked, interval for interval?

    Summen over de kvalificerede enheder af hver enheds bindende budloft,
    nulstillet uden for enhedens budvindue (punkt g).

    Serien bruges til at loft-begrænse gatens blokserie. Uden den ville
    `driven`-gatens lighedstegn kræve en reservation, der er fysisk umulig, så
    snart et budvindue lukker en enhed ude — og modellen ville være infeasible
    frem for at vise det, reglen faktisk gør: at der bydes mindre.
    """
    time_coord = data["time"]
    total = None
    lukket = None
    for unit in eligible:
        cop = _get_cop_series(unit, data)
        lofter = [float(unit.p_max_heat / cop.min().item())]
        if caps is not None:
            pu = (caps.per_unit_mw or {}).get(unit.name)
            if pu is not None:
                lofter.append(float(pu))
            pm = (getattr(caps, "per_unit_market_mw", None) or {}).get(unit.name, {})
            if pm.get(market.gate_key) is not None:
                lofter.append(float(pm[market.gate_key]))
        else:
            mb = getattr(unit.ancillary, market.max_bid_attr, None)
            if mb is not None:
                lofter.append(float(mb))
        cap = min(lofter)
        vindue = _bid_window_mask(unit, time_coord)
        serie = (
            xr.full_like(data["spot_price"], cap)
            if vindue is None
            else xr.where(vindue, cap, 0.0)
        )
        total = serie if total is None else total + serie
        if vindue is not None:
            luk = ~vindue
            lukket = luk if lukket is None else (lukket | luk)
    if total is None:
        total = xr.full_like(data["spot_price"], 0.0)
    if lukket is None:
        lukket = xr.zeros_like(data["spot_price"], dtype=bool)
    return total, lukket



def _alternative_heat_cost(cfg, data: xr.Dataset) -> xr.DataArray:
    """Marginalomkostningen for det billigste ikke-elektriske alternativ.

    Enhederne sorteres efter marginalomkostning, og kapaciteten lægges sammen,
    indtil varmelasten er dækket. Den enhed, der lukker hullet, er på
    marginalen. Rent eksogent: både varmelast og brændselspriser er data.

    Det er en forenkling — den ser bort fra lager, min-driftstid og
    biomassens faktiske rådighed. Men den fanger dét, sagen handler om: at
    alternativet om vinteren kan være gaskedlen og ikke halmen, og at
    budprisen derfor burde være spot − 1.800 og ikke spot − 600.
    """
    from src.model import compute_marginal_cost as marginal_cost   # undgår cirkelimport

    kandidater = []
    for navn, unit in cfg.units.items():
        if not unit.enabled or unit.fuel in ("electricity", "solar"):
            continue
        mc = marginal_cost(unit, cfg, data)
        kandidater.append((float(mc.mean()), float(unit.p_max_heat), mc))
    if not kandidater:
        raise ValueError(
            "opportunity_cost: casen har ingen ikke-elektriske enheder at "
            "regne alternativomkostningen mod"
        )
    kandidater.sort(key=lambda k: k[0])

    last = data["heat_load"] if "heat_load" in data.data_vars else None
    if last is None:
        last = xr.full_like(data["spot_price"], 0.0)

    kumuleret = 0.0
    resultat = None
    for _, kapacitet, mc in kandidater:
        naaet = last > kumuleret
        resultat = mc if resultat is None else xr.where(naaet, mc, resultat)
        kumuleret += kapacitet
    return resultat


def _opportunity_threshold(cfg, mkt_cfg, data: xr.Dataset, market) -> xr.DataArray:
    """Punkt (c): τ(t) regnet af brændselsstakken i stedet for kalibreret.

        τ(t) = spot(t) + tarif(t) + COP(t)·var_om − COP(t)·alternativ(t)

    Det er alternativomkostningen ved at binde 1 MW eloptag i én time: hvad
    elvarmen koster, minus hvad den varme ellers ville have kostet. Er
    kapacitetsprisen større, betaler det sig at byde.

    Johns regel — spotprognosen minus 600 kr., gulv 50 — falder ud af det
    samme regnestykke ved COP omkring 3 og biomasse som alternativ. Forskellen
    er, at τ her følger med, når gaskedlen kommer på marginalen.
    """
    ref_navn = mkt_cfg.opportunity_cost.get("reference_unit")
    if ref_navn not in cfg.units:
        raise ValueError(
            f"opportunity_cost.reference_unit={ref_navn!r} findes ikke i casen"
        )
    unit = cfg.units[ref_navn]
    cop = _get_cop_series(unit, data)
    tarif = resolve_consumption_tariff(cfg, data)
    alt = _alternative_heat_cost(cfg, data)

    tau = (
        data["spot_price"] + tarif + cfg.electricity.electricity_tax
        + cop * unit.var_om
        - cop * alt
    )
    gulv = float(mkt_cfg.opportunity_cost.get("floor_dkk_mw_h", 0.0))
    tau = xr.where(tau < gulv, gulv, tau)
    print(
        f"  {market.label}: beregnet tærskel (punkt c) — τ gns "
        f"{float(tau.mean()):.0f}, median {float(tau.median()):.0f}, "
        f"spænd {float(tau.min()):.0f}–{float(tau.max()):.0f} DKK/MW/h "
        f"(gulv {gulv:.0f}, alternativ gns {float(alt.mean()):.0f} DKK/MWh)"
    )
    return tau

def _add_reservation_gate(
    m: lp.Model,
    cfg,
    gate,  # ReservationGate
    market: _MarketSpec,
    var_by_unit: dict[str, lp.Variable],
    data: xr.Dataset,
    available_cap: Optional[xr.DataArray] = None,
    window_closed: Optional[xr.DataArray] = None,
) -> None:
    """Knyt reservationen til markedets day-ahead CM-pris via en gate.

    For hvert interval t er gaten åben når CM_m(t) ≥ τ_m. Blokken B_m
    reserveres (samlet over markedets enheder) som en EKSOGEN serie:

        block_series(t) = B_m   hvis  CM_m(t) ≥ τ_m   ellers 0

    mode == 'driven' (Spor B):  Σ_i r_m[i,t] == block_series(t)
        Reservationen drives af gaten — blokken reserveres hver gang gaten
        er åben, capped af footroom via de eksisterende footroom-constraints.
        Equality (ikke ≤) fjerner MILP'ens frihed til at cherry-picke kun
        aktiverings-hale-timerne inden i de gate-åbne intervaller; eksogent
        drevet reservation er hele pointen i det deskriptive spor.

    mode == 'bound' (Spor A):   Σ_i r_m[i,t] ≤ block_series(t)
        Gaten er en øvre grænse; MILP'en optimerer frit i gate-vinduet.

    CM-prisen (cap_price_key) er allerede indlæst og timeopløst — samme
    tidsakse som reservationsvariablen. Ingen nye binære variable: gaten er
    en data-afhængig parameter, så block_series er forberegnet og eksogen.
    """
    mkt_cfg = gate.market_cfg(market.gate_key)
    if mkt_cfg is None:
        return
    if not var_by_unit:
        return
    if market.cap_price_key not in data.data_vars:
        return

    price_cap = data[market.cap_price_key]              # DKK/MW/h, dim time
    if getattr(mkt_cfg, "opportunity_cost", None):
        threshold = _opportunity_threshold(cfg, mkt_cfg, data, market)
    else:
        threshold = float(mkt_cfg.cm_threshold_dkk_mw_h)
    gate_open = price_cap >= threshold                  # bool DataArray, dim time

    block = float(mkt_cfg.block_mw)
    block_series = xr.where(gate_open, block, 0.0)      # eksogen MW-serie

    # Blokken kan ikke overstige det, der faktisk kan bydes. Uden dette loft
    # bliver `driven`-gatens lighedstegn infeasible, så snart et budvindue
    # (punkt g) eller et per-markeds-loft lukker kapacitet ude.
    if available_cap is not None:
        begraenset = xr.where(block_series > available_cap, available_cap, block_series)
        n_klippet = int((begraenset < block_series - 1e-9).sum())
        if n_klippet:
            tabt = float((block_series - begraenset).sum())
            print(
                f"  {market.label}: blokken er klippet af tilgængelig budkapacitet "
                f"i {n_klippet} intervaller ({tabt:.0f} MW-timer mindre reservation)"
            )
        block_series = begraenset

    # Samlet reservation over markedets enheder.
    total = None
    for r in var_by_unit.values():
        total = r if total is None else (total + r)

    if gate.mode == "driven":
        if window_closed is not None and bool(window_closed.any()):
            # Punkt (g) mod gatens lighedstegn. Hvor et budvindue lukker en
            # enhed ude, kan påstanden "der bydes altid blokken" ikke gælde —
            # den er netop dét, reglen modsiger. Lighedstegnet lempes derfor
            # til en øvre grænse i de intervaller og bevares i resten.
            #
            # Det er ikke en teknikalitet for at undgå infeasibility. Med kun
            # varmepumpen tilbage skal footroom-bindingen dækkes ved COP ≈ 3,
            # og sommerens varmelast er for lille til at bære blokken. Modellen
            # kan altså ikke både adlyde Johns sommerregel og blokken. Det er
            # regnestykket bag, at Billunds juni-reservation er 0,08 MW.
            n = int(window_closed.sum())
            print(
                f"  {market.label}: lighedstegnet lempet til ≤ i {n} intervaller, "
                f"hvor et budvindue lukker kapacitet ude"
            )
            m.add_constraints(
                total <= block_series,
                name=f"{market.var_prefix}_gate_driven_ub",
            )
            m.add_constraints(
                total >= xr.where(window_closed, 0.0, block_series),
                name=f"{market.var_prefix}_gate_driven_lb",
            )
        else:
            m.add_constraints(
                total == block_series,
                name=f"{market.var_prefix}_gate_driven",
            )
    else:  # 'bound'
        m.add_constraints(
            total <= block_series,
            name=f"{market.var_prefix}_gate_bound",
        )

    freq = float(gate_open.mean())
    cm_open = float(price_cap.where(gate_open).mean()) if freq > 0 else 0.0
    tau_vis = float(threshold.mean()) if hasattr(threshold, "mean") else threshold
    print(
        f"  {market.label}: CM-gate ({gate.mode}) τ={tau_vis:.0f} DKK/MW/h, "
        f"blok={block:.1f} MW → gate-åben {freq*100:.1f}% af intervaller "
        f"(gns CM når åben={cm_open:.0f}), MW-snit≈{freq*block:.2f} MW"
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
        + resolve_consumption_tariff(cfg, data)
        + cfg.electricity.electricity_tax
    )

    per_market_results: dict[str, Optional[dict]] = {}
    any_eligible = False

    # Fælles reserve-loft (Billunds prækvalificering). Når sat erstatter det
    # de separate per-enhed/per-gruppe lofter: per-enheds-max-bud springes over
    # i _add_market_reserves, og gruppe-constraints springes over her i caller.
    # Balancering-metode (session 22) + lofter.
    method = getattr(cfg, "balancing_method", "legacy")
    caps = getattr(cfg, "ancillary_caps", None)
    shared_cap = getattr(cfg, "shared_reserve_cap_mw", None)
    # ancillary_caps har forrang: når sat springes både per-enheds-afrr_max_bid
    # (gammel pris-taker-beskyttelse) og shared_reserve_cap over.
    use_new_caps = caps is not None
    apply_max_bid = (not use_new_caps) and (shared_cap is None)
    print(
        "  Balancering: metode = "
        + ("activation_value (kovarians-korrekt av)" if method == "activation_value"
           else "legacy (E[α]×E[p])")
    )

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
            method=method,
        )
        # Gruppe-constraints per marked (kun når INTET fælles loft / nye caps).
        if not use_new_caps and shared_cap is None:
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

    # Lofter: nye ancillary_caps har forrang; ellers gammel shared_reserve_cap.
    if use_new_caps:
        _add_per_unit_caps(m, caps, afrr_vars, mfrr_vars)
        if caps.total_mw is not None:
            _add_shared_cap_constraint(m, caps.total_mw, afrr_vars, mfrr_vars)
    elif shared_cap is not None:
        _add_shared_cap_constraint(m, shared_cap, afrr_vars, mfrr_vars)

    # CM-pris-gate på reservationen (Spor B = driven, Spor A = bound). Når
    # aktiv binder gaten typisk før det samlede loft, så cap-niveauet bliver
    # ~irrelevant — det er en bekræftelse i sig selv.
    gate = getattr(cfg, "reservation_gate", None)
    if gate is not None and gate.enabled:
        print(
            f"  Reservation-gate AKTIV (mode={gate.mode}): reservationen "
            f"styres af day-ahead CM-prisen pr. marked."
        )
        market_vars = {"aFRR": afrr_vars, "mFRR": mfrr_vars}
        for market in MARKETS:
            eligible_m = _eligible_units_for_market(cfg, market)
            avail, lukket = _available_bid_capacity(
                cfg, market, eligible_m, data, caps,
            )
            _add_reservation_gate(
                m, cfg, gate, market, market_vars[market.label], data,
                available_cap=avail, window_closed=lukket,
            )

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
    # Activation_value-metoden: av/clear ligger i data når den var aktiv.
    # Auto-detekteres her, så sammendraget matcher den metode der blev løst.
    av = data.get(market.act_value_key) if market.act_value_key else None
    av_payment = data.get(market.act_payment_key) if market.act_payment_key else None
    clear = data.get(market.clear_fraction_key) if market.clear_fraction_key else None

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
        if av is not None:
            # Ny metode (kovarians-korrekt). Tre tal pr. enhed (Diagnose 2):
            #   brutto  = Σ av·r          — matcher objektivets akt-term
            #             (= netto-betaling + forbrugsmodregning)
            #   netto   = Σ av_payment·r  — ren aktiveringsbetaling (kun p_act)
            #   modregn = Σ (av−av_payment)·r — sparet forbrug (spot+tarif+afgift)
            gross = float((av * r_series).sum())
            entry["activation_gross_dkk"] = gross
            if av_payment is not None:
                net = float((av_payment * r_series).sum())
                entry["activation_payment_dkk"] = net
                entry["consumption_offset_dkk"] = gross - net
            # Bagudkompat: behold feltet, men sæt det til NETTO (manifestets
            # balanceindtægt = kapacitet + netto-aktivering, jf. Diagnose 2).
            entry["activation_price_revenue_dkk"] = (
                entry.get("activation_payment_dkk", gross)
            )
            if clear is not None:
                entry["expected_activated_mwh"] = float((clear * r_series).sum())
        elif alpha is not None and price_act is not None and spot is not None:
            # Gammel metode (E[α]×E[p]). NB: udelader sparet forbrug (historisk
            # forenkling i sammendraget — objektivet medregner det).
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
    grand_total_net = 0.0
    grand_total_off = 0.0

    for market_label, market_summary in summary.items():
        if not market_summary:
            continue
        print(f"\n=== {market_label.upper()} UP RESERVE-SAMMENDRAG ===")
        total_cap = 0.0
        total_net = 0.0
        total_off = 0.0
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
                # Ny metode: vis netto-betaling + forbrugsmodregning (= brutto).
                if "activation_payment_dkk" in stats:
                    net = stats["activation_payment_dkk"]
                    off = stats.get("consumption_offset_dkk", 0.0)
                    total_net += net
                    total_off += off
                    print(
                        f"    forv. aktiveret el: {mwh:,.0f} MWh/år | "
                        f"netto akt-betaling: {net/1e6:.3f} + forbrugsmodregn: "
                        f"{off/1e6:.3f} = brutto {(net+off)/1e6:.3f} mio DKK/år"
                    )
                else:
                    rev = stats.get("activation_price_revenue_dkk", 0.0)
                    total_net += rev
                    print(
                        f"    forv. aktiveret el: {mwh:,.0f} MWh/år, "
                        f"aktiveringsprisindtægt: {rev/1e6:.3f} mio DKK/år"
                    )
        if total_cap > 0 or total_net > 0 or total_off > 0:
            print(f"  {market_label} TOTAL kapacitet:           {total_cap/1e6:.3f} mio DKK/år")
            print(f"  {market_label} TOTAL netto akt-betaling:  {total_net/1e6:.3f} mio DKK/år")
            print(f"  {market_label} TOTAL forbrugsmodregning:  {total_off/1e6:.3f} mio DKK/år")
            print(f"  {market_label} TOTAL brutto (akt):        {(total_net+total_off)/1e6:.3f} mio DKK/år")
            print(f"  {market_label} NETTO balanceindtægt (kap+netto): {(total_cap+total_net)/1e6:.3f} mio DKK/år")
        grand_total_cap += total_cap
        grand_total_net += total_net
        grand_total_off += total_off

    if len(summary) > 1:
        print()
        print(f"  SAMLET kapacitet (aFRR + mFRR):             {grand_total_cap/1e6:.3f} mio DKK/år")
        print(f"  SAMLET netto akt-betaling (aFRR + mFRR):    {grand_total_net/1e6:.3f} mio DKK/år")
        print(f"  SAMLET forbrugsmodregning (aFRR + mFRR):    {grand_total_off/1e6:.3f} mio DKK/år")
        print(f"  SAMLET brutto aktivering (aFRR + mFRR):     {(grand_total_net+grand_total_off)/1e6:.3f} mio DKK/år")
        print(f"  SAMLET NETTO balanceindtægt (kap+netto):    {(grand_total_cap+grand_total_net)/1e6:.3f} mio DKK/år")
        print(f"  SAMLET BRUTTO balanceindtægt (kap+brutto):  {(grand_total_cap+grand_total_net+grand_total_off)/1e6:.3f} mio DKK/år")
        print(
            f"  (Brutto akt = netto akt-betaling + forbrugsmodregning. "
            f"Objektivet bruger brutto; manifestet rapporterer netto.)"
        )
