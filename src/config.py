"""
Konfiguration indlæsning.

Læser case YAML → dataclasses. Validering af parametre, udregning af
afledte størrelser (fx tankenergiindhold fra volumen+ΔT).

Al domænespecifik terminologi defineret her. Modellen (model.py)
skal IKKE lave validering — kun bygge LP-udtryk.
"""
from __future__ import annotations
from dataclasses import dataclass, field
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
        if self.fuel not in ("electricity",) and self.eta_fuel_to_heat is None:
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

    def fuel_price(self, fuel: str) -> float:
        """Returnér råvare-brændselspris i DKK/MWh_brændsel."""
        mapping = {
            "natural_gas": self.natural_gas,
            "straw": self.straw,
            "waste_heat": self.waste_heat,
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


@dataclass
class TimeHorizon:
    start: datetime
    end: datetime
    resolution: str                               # "1h" el. "15min"


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
    )

    # El
    e = raw["electricity"]
    electricity = Electricity(
        spot_area=e["spot_area"],
        tariff_consumption_flat=e["tariff_consumption_flat"],
        tariff_production_flat=e["tariff_production_flat"],
        electricity_tax=e["electricity_tax"],
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
    )
