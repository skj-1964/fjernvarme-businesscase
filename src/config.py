"""
Konfiguration indlæsning.

Læser case YAML → dataclasses. Validering af parametre, udregning af
afledte størrelser (fx tankenergiindhold fra volumen+ΔT).

Al domænespecifik terminologi defineret her. Modellen (model.py)
skal IKKE lave validering — kun bygge LP-udtryk.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from src.tariff import ConsumptionTariff, parse_consumption_tariff
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal
import numpy as np
import yaml

# Vandets varmekapacitet — brugt til tankenergiindhold
RHO_WATER = 1000.0          # kg/m³
CP_WATER = 4.186            # kJ/(kg·K)
SEC_PER_HOUR = 3600.0


# ------------------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------------------

@dataclass
class Ancillary:
    afrr_qualified: bool = False
    mfrr_qualified: bool = False
    fcr_qualified: bool = False
    # Max-bud per enhed [MW elektrisk] — beskytter mod pris-taker-antagelse
    # når enhedens kapacitet er stor ift. markedet. None = ingen grænse,
    # dvs. bud-volumen begrænses kun af fysisk kapacitet (p_el_max) og
    # eventuelle gruppe-constraints (se AncillaryGroup nedenfor).
    # Se STATUS_session11 §3-4: Billunds 30 MW elkedel = ~30% af aFRR-markedet,
    # defensibelt bud er ~5 MW (~5% af marked) på aFRR. mFRR-markedet er ~6×
    # større, så mfrr_max_bid kan sættes højere uden at bryde pris-taker-
    # antagelsen.
    afrr_max_bid_mw: Optional[float] = None
    mfrr_max_bid_mw: Optional[float] = None
    # Onset/idriftsættelse på balancemarkedet. ISO-dato (fx "2026-03-01").
    # Når sat gates reservationen (r_afrr + r_mfrr for enheden) til 0 i alle
    # intervaller FØR denne dato; fra og med datoen er upper-bound = p_el_max
    # som normalt. Enhedens varmedispatch er urørt — kun budafgivelsen gates.
    # Modellerer at en enhed først prækvalificeres/idriftsættes på balance på
    # et bestemt tidspunkt (et anlægsfaktum, ikke en prisrespons). None = altid
    # tilgængelig (uændret adfærd).
    available_from: Optional[str] = None
    # Budvindue (punkt g): måneder og lokale timer hvor enheden overhovedet
    # afgiver bud i kapacitetsmarkedet. Udeladt nøgle = ingen begrænsning.
    # Modellerer en driftsbeslutning, ikke en prisrespons: Billund byder ikke
    # elkedlen i CM om sommeren, fordi tankene ikke kan optage den produktion
    # et vundet bud tvinger frem. Rammer kun budafgivelsen — varmedispatch er
    # urørt, og enheden må stadig køre i spot.
    #   bid_window: {months: [10,11,12,1,2,3], hours_local: [6,7,...,21]}
    bid_window: Optional[dict] = None


@dataclass
class AncillaryGroup:
    """Gruppe af enheder der deler én samlet max-bud-grænse per marked.

    Anvendes når operatøren prækvalificerer en samlet kapacitet for en
    gruppe af enheder (fx flere elkedler), ikke per enhed. Gruppe-
    constraint tilføjes UDOVER eventuelle per-enhed-grænser, så begge
    håndhæves og den strammere binder.

    Billund 24-apr-2026: elkedlerne (elkedel_ny + elkedel_gl) melder 6 MW
    samlet på både aFRR og mFRR — en klassisk gruppe-grænse.

    Fortolkning af "per marked":
        afrr_max_bid_mw: Σ_{i ∈ group} r_afrr[i,t] ≤ værdi  ∀t
        mfrr_max_bid_mw: Σ_{i ∈ group} r_mfrr[i,t] ≤ værdi  ∀t
    aFRR og mFRR er uafhængige — samme enheder kan byde samtidigt i begge
    markeder op til hver markedsgrænse. Fælles footroom-constraint sikrer
    fysisk leverbarhed ved samtidig aktivering.
    """
    name: str
    units: list[str]
    afrr_max_bid_mw: Optional[float] = None
    mfrr_max_bid_mw: Optional[float] = None


@dataclass
class BidStrategy:
    """Værkets budstrategi på aktiveringsmarkedet (jf. interview Billund).

    Buddet sættes relativt til spot. Opregulering: spot + up_markup_dkk_mwh.
    av(t) (kovarians-korrekt aktiveringsværdi) beregnes i datalaget ved dette
    bud. up_markup_max_dkk_mwh er øvre båndgrænse (tank-styret positionering,
    Tier 2) — bruges ikke i Tier-1-beregningen, kun dokumentation.

    down_markdown_dkk_mwh: bud ned = spot − denne. None = ingen ned-bud
    (modellen er up-only som i dag indtil ned valideres mod facit).
    """
    up_markup_dkk_mwh: float
    up_markup_max_dkk_mwh: Optional[float] = None
    down_markdown_dkk_mwh: Optional[float] = None
    down_markdown_max_dkk_mwh: Optional[float] = None


@dataclass
class AncillaryCaps:
    """Generiske reservelofter (erstatter shared_reserve_cap_mw).

    per_unit_mw: maks samlet bud (aFRR+mFRR) per enhed [MW el]. Håndhæves ALTID.
        Billund: {vp_luft_vand: 5.52} (prækvalificeret eloptag).
    per_unit_market_mw: maks bud per enhed PER MARKED [MW el]:

        r_afrr[i,t] ≤ per_unit_market_mw[i]["afrr"]   ∀t
        r_mfrr[i,t] ≤ per_unit_market_mw[i]["mfrr"]   ∀t

        Modellerer at værket selv fordeler sin prækvalificerede kapacitet
        mellem markederne med faste bud-volumener. Billund (John 26/8 2026):
        VP bydes med 2 MW eloptag i aFRR-CM og 3 MW i mFRR-CM, inden for de
        5,52 MW prækvalificeret i alt. Bemærk at summen af de to markedslofter
        kan være mindre end per_unit_mw — begge håndhæves, og den strammere
        binder. Kun markeder, der nævnes, begrænses; udeladt marked = fri.
    total_mw:    maks summen af ALLE bud på tværs af markeder og enheder per time.
        Billund: 33 (begge elkedler) / 17,52 (5,52 VP + 12 elkedel_gl, elkedel_ny
        endnu ikke godkendt). Sættes konsistent med hvilke kedler casen har enabled.
    """
    per_unit_mw: dict = field(default_factory=dict)
    per_unit_market_mw: dict = field(default_factory=dict)
    total_mw: Optional[float] = None

    def __post_init__(self) -> None:
        valid = {"afrr", "mfrr"}
        for unit_name, per_market in (self.per_unit_market_mw or {}).items():
            if not isinstance(per_market, dict):
                raise ValueError(
                    f"ancillary_caps.per_unit_market_mw.{unit_name} skal være et "
                    f"map med nøglerne 'afrr' og/eller 'mfrr', fik {per_market!r}"
                )
            unknown = set(per_market) - valid
            if unknown:
                raise ValueError(
                    f"ancillary_caps.per_unit_market_mw.{unit_name}: ukendt marked "
                    f"{sorted(unknown)}. Gyldige nøgler: {sorted(valid)}"
                )


@dataclass
class ReservationGateMarket:
    """Gate-parametre for ét marked (aFRR eller mFRR).

    cm_threshold_dkk_mw_h: tærskel τ_m på day-ahead kapacitetsprisen (CM).
        Gaten er åben i intervaller hvor CM_m(t) ≥ τ_m.
    block_mw: blok-niveau B_m [MW el] der reserveres når gaten er åben.
    """
    cm_threshold_dkk_mw_h: Optional[float] = None
    # Punkt (c): tærsklen regnet af brændselsstakken i stedet for kalibreret.
    #   τ(t) = spot(t) + tarif(t) + COP(t)·var_om − COP(t)·alternativ(t)
    # Sæt {reference_unit: <navn>, floor_dkk_mw_h: 50}. Er den sat, ignoreres
    # cm_threshold_dkk_mw_h. Se src/balancing.py:_opportunity_threshold.
    opportunity_cost: Optional[dict] = None
    block_mw: float = 0.0

    def __post_init__(self) -> None:
        if self.cm_threshold_dkk_mw_h is None and self.opportunity_cost is None:
            raise ValueError(
                "reservation_gate: sæt enten cm_threshold_dkk_mw_h (kalibreret "
                "tærskel) eller opportunity_cost (beregnet tærskel af "
                "brændselsstakken)"
            )


@dataclass
class ReservationGate:
    """CM-pris-gate på reservationen (Spor B = deskriptiv, Spor A = normativ).

    Empirisk fund (jf. notat_sporB_design): Billunds reservation er en gate på
    markedets day-ahead kapacitetspris (CM). For hvert marked m og interval t:

        gate_m(t) = 1  hvis  CM_m(t) ≥ τ_m   ellers 0

    mode styrer hvordan gaten kobles til reservationsvariablen:

      'driven' (Spor B, deskriptiv): reservationen DRIVES af gaten —
          Σ_i r_m[i,t] == gate_m(t) · B_m
        Blokken reserveres hver gang CM ≥ τ (capped af footroom via de
        eksisterende footroom-constraints). Eksogent drevet, så en
        perfekt-foresight-MILP IKKE kan cherry-picke kun aktiverings-
        hale-timerne inden i de gate-åbne intervaller.

      'bound' (Spor A, normativ — bygget, men ikke kørt nu): gaten er en
          øvre grænse — Σ_i r_m[i,t] ≤ gate_m(t) · B_m
        MILP'en optimerer frit inden for gate-vinduet (med forventet CM-pris
        og τ = opportunity cost).

    Tærsklerne er afledte parametre (Q1-2026-snit), ikke rådata.
    """
    enabled: bool = False
    mode: str = "driven"                          # 'driven' (Spor B) | 'bound' (Spor A)
    afrr: Optional[ReservationGateMarket] = None
    mfrr: Optional[ReservationGateMarket] = None

    def __post_init__(self):
        if self.mode not in ("driven", "bound"):
            raise ValueError(
                f"reservation_gate.mode skal være 'driven' eller 'bound', "
                f"fik {self.mode!r}"
            )

    def market_cfg(self, gate_key: str) -> Optional[ReservationGateMarket]:
        """Returnér markedets gate-config ('afrr' | 'mfrr') eller None."""
        return getattr(self, gate_key, None)


@dataclass
class COPCurve:
    """
    COP(T_ambient) for varmepumper — lineær approksimation (trin 2).

        COP = clip(a + b·T_ambient,  cop_min, cop_max)

    a, b:       lineære koefficienter (a = COP ved T=0°C; b = d(COP)/dT)
    cop_min:    nedre fysisk grænse (defrost-regime, typisk 1.6-2.0)
    cop_max:    øvre fysisk grænse (typisk 3.8-4.2 for luft/vand)
    type:       kun 'linear' understøttet i trin 2.
                Forberedt til 'table' (tabel-interpolation) i trin 3.
    """
    type: str = "linear"
    a: float = 2.2
    b: float = 0.08
    cop_min: float = 1.8
    cop_max: float = 4.0

    def __post_init__(self):
        if self.type != "linear":
            raise NotImplementedError(
                f"COPCurve.type={self.type!r} ikke understøttet. "
                f"Brug 'linear' (tabel kommer i trin 3)."
            )
        if self.cop_min <= 0 or self.cop_max <= self.cop_min:
            raise ValueError(
                f"Ugyldige COP-grænser: cop_min={self.cop_min}, cop_max={self.cop_max}"
            )

    def evaluate(self, t_ambient):
        """
        Returnér COP for én temperatur eller en tidsserie.

        Input: skalar, np.ndarray, pd.Series eller xr.DataArray (°C).
        Output: samme type, med samme koord/indeks som input.
        """
        cop = self.a + self.b * t_ambient
        # np.clip bevarer xarray/pandas-strukturen når input er DataArray/Series
        return np.clip(cop, self.cop_min, self.cop_max)


@dataclass
class Unit:
    name: str
    type: str                                     # heat_pump, electric_boiler, biomass_boiler, ...
    p_max_heat: float                             # MW varme
    p_min_heat: float                             # MW varme (bruges som min-last når uc_enabled)
    alpha: float                                  # el-til-varme ratio (fallback når cop_curve ikke sat)
    fuel: str                                     # nøgle i prices eller "electricity"/"waste_heat"
    eta_fuel_to_heat: Optional[float] = None      # kun for brændselsenheder
    var_om: float = 0.0                           # DKK/MWh_varme
    start_cost: float = 0.0                       # DKK per start (trin 3)
    min_uptime: int = 1                           # timer (1 = ingen effektiv binding)
    min_downtime: int = 1                         # timer (1 = ingen effektiv binding)
    co2_emissions_per_mwh_fuel: float = 0.0       # t CO2 / MWh brændsel
    ancillary: Ancillary = field(default_factory=Ancillary)
    cop_curve: Optional[COPCurve] = None          # valgfri — overruler alpha for VP
    # Tidsvarierende kapacitetsloft via CSV (MW pr. time). Når sat, bygges
    # produktionsloftet som min(profil(t), p_max_heat) i model.py — bruges til
    # vejr-drevne enheder som solvarme. None = skalart p_max_heat-loft (uændret).
    production_profile_path: Optional[str] = None
    commissioned: Optional[int] = None
    notes: str = ""
    enabled: bool = True                          # false → enheden udelades helt fra modellen
    # --- Unit commitment (trin 3) ---
    # Når uc_enabled=True, bruges p_min_heat som min-last, min_uptime og
    # min_downtime som tidsbindinger, og start_cost som straf per start.
    # Gør det eksplicit: YAML-felter der allerede findes bliver IKKE aktive
    # medmindre denne flag sættes.
    uc_enabled: bool = False
    initial_status: int = 1                       # u_0 ∈ {0,1} — enhedens starttilstand

    def __post_init__(self):
        if self.p_min_heat > self.p_max_heat:
            raise ValueError(f"{self.name}: p_min > p_max")
        if self.fuel not in ("electricity", "solar") and self.eta_fuel_to_heat is None:
            raise ValueError(f"{self.name}: brændselsenhed mangler eta_fuel_to_heat")
        # cop_curve giver kun mening for elforbrugende VP'er
        if self.cop_curve is not None:
            if self.type != "heat_pump":
                raise ValueError(
                    f"{self.name}: cop_curve kun gyldig for type='heat_pump', "
                    f"ikke {self.type!r}"
                )
            if self.fuel != "electricity":
                raise ValueError(
                    f"{self.name}: cop_curve kræver fuel='electricity'"
                )
        # UC-validering
        if self.uc_enabled:
            if self.initial_status not in (0, 1):
                raise ValueError(
                    f"{self.name}: initial_status skal være 0 eller 1, "
                    f"fik {self.initial_status}"
                )
            if self.min_uptime < 1 or self.min_downtime < 1:
                raise ValueError(
                    f"{self.name}: min_uptime/min_downtime skal være ≥ 1"
                )

    @property
    def has_uc(self) -> bool:
        """True hvis enheden skal have MILP unit commitment behandling."""
        return self.uc_enabled


@dataclass
class Storage:
    name: str
    volume_m3: float
    delta_t_k: float
    e_initial_mwh: float
    p_max_charge_mw: float
    p_max_discharge_mw: float
    self_discharge_per_hour: float
    cycle_binding: bool = True
    e_max_mwh: Optional[float] = None             # beregnes hvis None
    notes: str = ""
    enabled: bool = True                          # false → lageret udelades helt fra modellen

    def __post_init__(self):
        if self.e_max_mwh is None:
            # E [MWh] = V [m³] × rho [kg/m³] × c_p [kJ/kg/K] × ΔT [K] / 3600
            self.e_max_mwh = (
                self.volume_m3 * RHO_WATER * CP_WATER * self.delta_t_k / SEC_PER_HOUR / 1000.0
            )
        if self.e_initial_mwh < 0:
            raise ValueError(
                f"{self.name}: e_initial_mwh={self.e_initial_mwh} må ikke være negativt"
            )
        if self.e_initial_mwh > self.e_max_mwh:
            # Auto-clamp: opstår typisk når volume_m3 overrides (fx via --set)
            # uden at e_initial_mwh justeres samtidig. Nulstiller til halvfuld,
            # som matcher default-intentionen i YAML ("Start halvfuld").
            # Cyclus-binding sikrer at tank ender på samme niveau som den starter,
            # så valget af start-niveau er kun en af flere valide cycler.
            new_val = self.e_max_mwh / 2.0
            print(
                f"  Storage '{self.name}': e_initial_mwh={self.e_initial_mwh} "
                f"> e_max_mwh={self.e_max_mwh:.1f} (typisk efter volume_m3-"
                f"override). Nulstiller til halvfuld ({new_val:.1f} MWh). "
                f"For eksplicit kontrol: tilføj "
                f"--set storage.{self.name}.e_initial_mwh=<værdi>."
            )
            self.e_initial_mwh = new_val


@dataclass
class Prices:
    natural_gas: float
    straw: float
    waste_heat: float
    co2_eua: float                                # DKK per MWh_gas (omregnet fra EUA)
    flis: float = 0.0                             # DKK/MWh_brændsel (flis/træflis)

    def fuel_price(self, fuel: str) -> float:
        """Returnér råvare-brændselspris i DKK/MWh_brændsel."""
        mapping = {
            "natural_gas": self.natural_gas,
            "straw": self.straw,
            "waste_heat": self.waste_heat,
            "flis": self.flis,
            "solar": 0.0,            # gratis input — marginalomkostning kortsluttes i model.py
        }
        if fuel not in mapping:
            raise KeyError(f"Ukendt brændsel: {fuel}")
        return mapping[fuel]


@dataclass
class Electricity:
    spot_area: str
    tariff_consumption_flat: float
    tariff_production_flat: float
    electricity_tax: float
    # Tidsvarierende båndprofil (punkt d). None = brug den flade værdi.
    # Er begge sat, vinder profilen — se src/tariff.py.
    tariff_consumption: Optional["ConsumptionTariff"] = None


@dataclass
class TimeHorizon:
    start: datetime
    end: datetime
    resolution: str                               # "1h" el. "15min"


# DMI-stationer der findes i df-data. Udvid listen, hvis df-data faar flere.
# Formaalet er at fange tastefejl ved config-indlaesning frem for nede i
# loaderen, hvor fejlen bliver "fil ikke fundet".
KENDTE_DMI_OMRAADER = ("fyn", "vestkyst", "karup")

# Priszoner i df-data.
KENDTE_PRISZONER = ("DK1", "DK2")


@dataclass
class DataOptions:
    """Hvilke eksterne serier casen skal hente.

    Begge felter er PAAKRAEVEDE og har med vilje ingen default. De laa
    tidligere som CLI-defaults (`--dmi-area fyn`, `--price-zone DK1`), og en
    default, man ikke kan se i casen, er en fejlkilde: den 9. september 2026
    blev Andeby lagt om til et rullende aar, hvor fyn og vestkyst mangler
    28. februar 2026. Casen fejlede paa coverage, med mindre man huskede et
    flag, der ikke stod nogen steder i casen. Flytter man blot defaulten til
    YAML, er faelden den samme -- den er bare rykket et lag ind.

    Et vaerk skal derfor erklaere sit klimaomraade og sin priszone i sin egen
    fil. CLI-flagene findes stadig og vinder, naar de gives eksplicit.
    """
    dmi_area: str
    price_zone: str
    dmi_temp_shortname: str = "temp_mean_past1h"
    eur_dkk: float = 7.45

    def __post_init__(self) -> None:
        if self.dmi_area not in KENDTE_DMI_OMRAADER:
            raise ValueError(
                f"data.dmi_area: '{self.dmi_area}' er ikke en kendt DMI-station. "
                f"Kendte: {', '.join(KENDTE_DMI_OMRAADER)}. "
                f"Er stationen ny i df-data, skal den tilfoejes i "
                f"config.KENDTE_DMI_OMRAADER."
            )
        if self.price_zone not in KENDTE_PRISZONER:
            raise ValueError(
                f"data.price_zone: '{self.price_zone}' er ikke en kendt priszone. "
                f"Kendte: {', '.join(KENDTE_PRISZONER)}."
            )
        if self.eur_dkk <= 0:
            raise ValueError(
                f"data.eur_dkk skal vaere > 0, fik {self.eur_dkk}")


@dataclass
class Solver:
    """Solvertolerance. Adskiller ABSOLUT og DIFFERENTIEL brug.

    Standardvaerdierne (0,5 % / 5.000 DKK) er valgt til en absolut
    businesscase, hvor tolerancen er lille mod usikkerheden i
    [BEKRAEFT]-antagelserne. De er FOR LOESE til scenariedifferenser:
    paa et objektiv omkring 5 mio er 0,5 % ca. 26.000 DKK, mens de
    marginale trin i et tanksweep er 2.000-14.000 DKK. Differensen
    drukner altsaa i solverens egen tolerance, og fortegnet kan vende.

    Til sweeps og enhver anden differenslaesning: saet mip_rel_gap til
    0.0002 eller lavere, eller brug --mip-gap paa kommandolinjen.
    """
    mip_rel_gap: float = 0.005
    mip_abs_gap: float = 5000.0
    time_limit: float = 600.0
    presolve: str = "on"
    parallel: str = "on"

    def __post_init__(self) -> None:
        if not (0.0 <= self.mip_rel_gap < 1.0):
            raise ValueError(
                f"solver.mip_rel_gap skal ligge i [0, 1), fik {self.mip_rel_gap}"
            )
        if self.mip_abs_gap < 0.0:
            raise ValueError(
                f"solver.mip_abs_gap skal vaere >= 0, fik {self.mip_abs_gap}"
            )
        if self.time_limit <= 0.0:
            raise ValueError(
                f"solver.time_limit skal vaere > 0, fik {self.time_limit}"
            )

    def as_options(self) -> dict:
        return {
            "mip_rel_gap": self.mip_rel_gap,
            "mip_abs_gap": self.mip_abs_gap,
            "time_limit": self.time_limit,
            "presolve": self.presolve,
            "parallel": self.parallel,
        }


@dataclass
class CaseConfig:
    meta: dict
    time: TimeHorizon
    prices: Prices
    electricity: Electricity
    units: dict[str, Unit]
    storage: dict[str, Storage]
    ancillary_groups: dict[str, AncillaryGroup] = field(default_factory=dict)
    investment_enabled: bool = False
    # Fælles reserve-loft [MW elektrisk] der gælder summen af ALLE bydende
    # enheders bud på TVÆRS af aFRR + mFRR, per time:
    #     Σ_i (r_afrr[i,t] + r_mfrr[i,t]) ≤ shared_reserve_cap_mw   ∀t
    # Repræsenterer Billunds faktiske prækvalificering (14 MW frit fordelt
    # mellem aFRR og mFRR — session 19 §4.2). Når sat, ERSTATTER den de
    # separate per-enhed (Ancillary.*_max_bid_mw) og per-gruppe
    # (AncillaryGroup) lofter; disse springes over i balancing.py.
    # None = gammel adfærd (per-enhed/per-gruppe lofter håndhæves).
    shared_reserve_cap_mw: Optional[float] = None
    # --- Ny balancering (session 22) ---
    # method: "legacy" (E[α]×E[p], gammel) | "activation_value" (E[α·p], ny,
    # kovarians-korrekt via av(t) beregnet i datalaget). Toggle mellem de to.
    balancing_method: str = "legacy"
    bid_strategy: Optional["BidStrategy"] = None
    # ancillary_caps erstatter shared_reserve_cap_mw når sat: per-enheds-loft
    # (altid håndhævet) + ét samlet loft. shared_reserve_cap_mw bevares for
    # bagudkompatibilitet med eksisterende cases.
    ancillary_caps: Optional["AncillaryCaps"] = None
    # CM-pris-gate på reservationen (Spor B/A). None/enabled=False = gammel
    # adfærd (kontinuerlig reservation op til loftet). Når enabled binder gaten
    # før det samlede loft (total_mw), så cap-niveauet bliver ~irrelevant.
    reservation_gate: Optional["ReservationGate"] = None
    # Solvertolerance. Se Solver-docstring: standarden er til ABSOLUTTE
    # koersler, ikke til scenariedifferenser.
    solver: "Solver" = field(default_factory=Solver)
    # Eksterne datakilder. Paakraevet -- se DataOptions om hvorfor der
    # ikke er nogen default.
    data: "DataOptions" = None  # type: ignore[assignment]


# ------------------------------------------------------------------------------
# Loader
# ------------------------------------------------------------------------------

def _apply_override(raw: dict, dotted_path: str, value_str: str) -> None:
    """Overskriv en leaf-værdi i raw YAML-dict via dotted path.

    Anvendes før dataclass-construction så __post_init__ ser de overriddede
    værdier (kritisk for afledte felter som Storage.e_max_mwh beregnet ud
    fra volume_m3).

    Værdien parses via yaml.safe_load så type-coercion er automatisk:
      '4000'    → int(4000)
      '4000.0'  → float(4000.0)
      'true'    → True
      'null'    → None
      '2.65'    → float(2.65)
      'hello'   → str('hello')
      '2025-10-01T00:00:00Z' → str (ISO-format)

    Begrænsninger:
      - Kun leaf-override; hele sub-dicts kan ikke erstattes
      - Stien skal eksistere i forvejen; nye nøgler tilføjes ikke
      - Lister kan ikke overrides (kompliceret path-semantik)

    Raises ValueError hvis stien ikke findes eller ikke peger på en leaf.
    """
    parts = dotted_path.split(".")
    cursor = raw

    # Naviger alle undtagen sidste segment
    for i, key in enumerate(parts[:-1]):
        if not isinstance(cursor, dict):
            path_so_far = ".".join(parts[:i])
            raise ValueError(
                f"--set {dotted_path}: '{path_so_far}' er ikke en dict "
                f"(type: {type(cursor).__name__}), kan ikke navigere videre"
            )
        if key not in cursor:
            path_so_far = ".".join(parts[:i])
            available = sorted(cursor.keys()) if isinstance(cursor, dict) else []
            raise ValueError(
                f"--set {dotted_path}: nøgle '{key}' findes ikke ved "
                f"'{path_so_far}'. Gyldige nøgler: {available}"
            )
        cursor = cursor[key]

    # Overskriv leaf
    leaf_key = parts[-1]
    if not isinstance(cursor, dict):
        raise ValueError(
            f"--set {dotted_path}: forælder '{'.'.join(parts[:-1])}' er "
            f"ikke en dict (type: {type(cursor).__name__})"
        )
    if leaf_key not in cursor:
        available = sorted(cursor.keys())
        raise ValueError(
            f"--set {dotted_path}: nøgle '{leaf_key}' findes ikke under "
            f"'{'.'.join(parts[:-1])}'. Gyldige nøgler: {available}"
        )

    old_value = cursor[leaf_key]
    if isinstance(old_value, (dict, list)):
        raise ValueError(
            f"--set {dotted_path}: peger på en {type(old_value).__name__}, "
            f"ikke en leaf-værdi. Kun skalarer (int/float/bool/str/null) "
            f"kan overrides."
        )

    try:
        new_value = yaml.safe_load(value_str)
    except yaml.YAMLError as e:
        raise ValueError(
            f"--set {dotted_path}: kunne ikke parse '{value_str}' som "
            f"YAML-værdi: {e}"
        ) from e

    cursor[leaf_key] = new_value
    print(f"  Override: {dotted_path} = {new_value!r} (var {old_value!r})")


def load_case(
    path: str | Path,
    overrides: list[str] | None = None,
) -> CaseConfig:
    """Indlæs YAML case-fil og validér.

    Args:
        path: Sti til YAML-fil.
        overrides: Valgfri liste af 'dotted.path=value'-strenge der
            overskriver specifikke YAML-værdier FØR dataclass-construction.
            Se _apply_override() for detaljer.

    Eksempler på overrides:
        'storage.tank_eksisterende.volume_m3=4000'
        'prices.co2_eua.value=800'
        'units.vp_luft_vand.ancillary.afrr_max_bid_mw=3.0'
        'ancillary_groups.elkedler.afrr_max_bid_mw=8.0'
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Overrides anvendes FØR dataclass-construction så __post_init__ ser
    # de overriddede værdier (vigtigt for Storage.e_max_mwh etc.).
    for ov in overrides or []:
        if "=" not in ov:
            raise ValueError(
                f"--set skal have format 'dotted.path=value', fik: {ov!r}"
            )
        key, _, val = ov.partition("=")
        _apply_override(raw, key.strip(), val.strip())

    # Tid
    t = raw["time"]
    time = TimeHorizon(
        start=datetime.fromisoformat(t["start"].replace("Z", "+00:00")),
        end=datetime.fromisoformat(t["end"].replace("Z", "+00:00")),
        resolution=t["resolution"],
    )

    # Priser
    p = raw["prices"]
    prices = Prices(
        natural_gas=p["natural_gas"]["value"],
        straw=p["straw"]["value"],
        waste_heat=p["waste_heat"]["value"],
        co2_eua=p["co2_eua"]["value"],
        flis=p["flis"]["value"] if "flis" in p else p["straw"]["value"],
    )

    # El
    e = raw["electricity"]
    electricity = Electricity(
        spot_area=e["spot_area"],
        tariff_consumption_flat=e["tariff_consumption_flat"],
        tariff_production_flat=e["tariff_production_flat"],
        electricity_tax=e["electricity_tax"],
        tariff_consumption=parse_consumption_tariff(e.get("tariff_consumption")),
    )

    # Enheder
    units = {}
    for name, u in raw["units"].items():
        anc = Ancillary(**u.get("ancillary", {}))
        cop_raw = u.get("cop_curve")
        cop_curve = COPCurve(**cop_raw) if cop_raw is not None else None
        u_clean = {k: v for k, v in u.items() if k not in ("ancillary", "cop_curve")}
        units[name] = Unit(name=name, ancillary=anc, cop_curve=cop_curve, **u_clean)

    # Lagre
    storages = {}
    for name, s in raw["storage"].items():
        storages[name] = Storage(name=name, **s)

    # Ancillary-grupper (session 12 — gruppe-max-bud-constraints)
    # Valideres mod enheder så typos opdages tidligt.
    groups = {}
    for gname, g in raw.get("ancillary_groups", {}).items():
        group = AncillaryGroup(name=gname, **g)
        unknown = [u for u in group.units if u not in units]
        if unknown:
            raise ValueError(
                f"ancillary_groups.{gname}: ukendte enheder {unknown}. "
                f"Gyldige enheder: {sorted(units.keys())}"
            )
        groups[gname] = group

    # Balancering (session 22): method-toggle, budstrategi, generiske lofter
    bal_raw = raw.get("balancing", {})
    balancing_method = bal_raw.get("method", "legacy")
    if balancing_method not in ("legacy", "activation_value"):
        raise ValueError(
            f"balancing.method skal være 'legacy' eller 'activation_value', "
            f"fik {balancing_method!r}"
        )
    bs_raw = bal_raw.get("bid_strategy")
    bid_strategy = BidStrategy(**bs_raw) if bs_raw else None
    if balancing_method == "activation_value" and bid_strategy is None:
        raise ValueError(
            "balancing.method='activation_value' kræver balancing.bid_strategy"
        )
    caps_raw = bal_raw.get("ancillary_caps")
    ancillary_caps = (
        AncillaryCaps(
            per_unit_mw=caps_raw.get("per_unit_mw", {}),
            per_unit_market_mw=caps_raw.get("per_unit_market_mw", {}),
            total_mw=caps_raw.get("total_mw"),
        )
        if caps_raw
        else None
    )

    # CM-pris-gate på reservationen (Spor B/A). Ren config-blok under balancing.
    gate_raw = bal_raw.get("reservation_gate")
    reservation_gate = None
    if gate_raw:
        def _market_gate(key: str) -> Optional[ReservationGateMarket]:
            mk = gate_raw.get(key)
            if not mk:
                return None
            return ReservationGateMarket(
                cm_threshold_dkk_mw_h=(
                    float(mk["cm_threshold_dkk_mw_h"])
                    if mk.get("cm_threshold_dkk_mw_h") is not None
                    else None
                ),
                opportunity_cost=mk.get("opportunity_cost"),
                block_mw=float(mk["block_mw"]),
            )
        reservation_gate = ReservationGate(
            enabled=bool(gate_raw.get("enabled", False)),
            mode=gate_raw.get("mode", "driven"),
            afrr=_market_gate("afrr"),
            mfrr=_market_gate("mfrr"),
        )

    # Eksterne datakilder (PAAKRAEVET blok)
    if "data" not in raw:
        raise ValueError(
            "casen mangler en 'data'-blok. Tilfoej fx:\n"
            "\n"
            "  data:\n"
            "    dmi_area: \"fyn\"        # fyn | vestkyst | karup\n"
            "    price_zone: \"DK1\"      # DK1 | DK2\n"
            "\n"
            "Vaerdierne laa tidligere som CLI-defaults. De skal staa i casen, "
            "saa et vaerks klimaomraade og priszone foelger med filen i stedet "
            "for at afhaenge af, om den, der koerer, huskede et flag."
        )
    data_raw = raw["data"] or {}
    ukendte_data = set(data_raw) - {
        "dmi_area", "price_zone", "dmi_temp_shortname", "eur_dkk"}
    if ukendte_data:
        raise ValueError(f"ukendte noegler i data-blokken: {sorted(ukendte_data)}")
    for paakraevet in ("dmi_area", "price_zone"):
        if paakraevet not in data_raw:
            raise ValueError(
                f"data.{paakraevet} mangler i casen og har med vilje ingen "
                f"default. Se DataOptions i src/config.py."
            )
    data_cfg = DataOptions(**data_raw)

    # Solvertolerance (valgfri blok; standard = absolut-koersel)
    solver_raw = raw.get("solver", {}) or {}
    ukendte = set(solver_raw) - {
        "mip_rel_gap", "mip_abs_gap", "time_limit", "presolve", "parallel"}
    if ukendte:
        raise ValueError(f"ukendte noegler i solver-blokken: {sorted(ukendte)}")
    solver_cfg = Solver(**solver_raw)

    return CaseConfig(
        meta=raw["meta"],
        time=time,
        prices=prices,
        electricity=electricity,
        units=units,
        storage=storages,
        ancillary_groups=groups,
        investment_enabled=raw.get("investment", {}).get("enabled", False),
        shared_reserve_cap_mw=raw.get("balancing", {}).get("shared_reserve_cap_mw"),
        balancing_method=balancing_method,
        bid_strategy=bid_strategy,
        ancillary_caps=ancillary_caps,
        reservation_gate=reservation_gate,
        solver=solver_cfg,
        data=data_cfg,
    )
