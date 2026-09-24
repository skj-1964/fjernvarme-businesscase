"""
Kolonne-mapping v1 (df-data-klonen) → v2 (api.sysapp.dk). F6 Gate 1 + 1b + 1c + 1d.

ENESTE SANDHEDSKILDE for mappingen. Gate 2 og Gate 3 skal importere herfra
og må ikke gentage navne lokalt.

Modulet indeholder KUN data. Ingen funktion her transformerer, henter eller
omdøber noget — det er Gate 2's arbejde. `DERIVED` beskriver en beregning som
et udtryk i tekst; den udføres ikke her.

--------------------------------------------------------------------------
HVORFOR MAPPINGEN ER SKREVET I HÅNDEN
--------------------------------------------------------------------------
Akronym-konverteringen er ikke mekanisk. En naiv PascalCase→snake_case giver
`a_frr_up_mw`, `m_frrsa_up_req_mw`, `totalm_frr_up_mw` — ingen af dem findes.
API'et bruger `afrr_up_mw`, `mfrr_sa_up_req_mw`, `total_mfrr_up_mw`. Gate 0
målte at automatisk konvertering ramte 8/18 og 3/19 kolonner. Derfor står hver
række eksplicit nedenfor.

--------------------------------------------------------------------------
V2_COLUMNS ER SANDHEDEN
--------------------------------------------------------------------------
`v2_columns` er den ORDNEDE, autoritative output-header pr. datasæt.
`v1_to_v2.values()` er det IKKE: den mangler `ADDED` (kolonner kun API'et har)
og `DERIVED` (kolonner der genereres). Skal Gate 2 vide hvordan en v2-fil ser
ud, læses `v2_columns` — ikke en mappings værdimængde.

--------------------------------------------------------------------------
TO RETNINGER IND TIL v2
--------------------------------------------------------------------------
Begge kilder skal kunne nå samme v2-skema:

    v1_to_v2    klonens CSV-filer  → v2
    api_to_v2   nye API-hentninger → v2

For syv af otte datasæt er `api_to_v2` ren identitet — API'et ER v2-navngivningen.
Kun `spot_entsoe` afviger, se A3-noten der.

--------------------------------------------------------------------------
DE FEM SPANDE
--------------------------------------------------------------------------
v1_to_v2     v1-navn → v2-navn. Identitets-par står med, ellers går regnskabet
             ikke op for `spot_dk` og `dmi_obs`, hvor klonen allerede er på
             snake_case.
api_to_v2    API-navn → v2-navn.
DROPPED      v1-navne der udgår, med begrundelse.
API_DROPPED  API-navne der udgår, med begrundelse.
ADDED        v2-navne der kun kan komme fra API'et (ikke fra klonen).
V1_ONLY      v2-navne der kun kan komme fra KLONEN (ikke fra API'et).
             ADDED's spejlbillede. Tilføjet i Gate 1c, da `spot_price_dkk`
             blev bragt med over: EDS leverer den, api_entsoe_prices.php
             gør ikke.
DERIVED      v2-navne der GENERERES, ikke overtages fra nogen af kilderne.
KEY          de v2-kolonner der tilsammen gør en række entydig.

`API_DROPPED` er ikke en dublet af `DROPPED`. Opgavens oprindelige tre spande
kunne ikke rumme `created_at`, `updated_at`, `time_dk`/`hour_dk` og `id`:
API'et LEVERER dem, og beslutningen er at droppe dem. Lagt i `ADDED` ville
Gate 2 læse dem som "tilføj disse".

Regnskabet der skal gå op for hvert datasæt (verificeret i
tests/test_schema_v2_mapping.py):

    v1-kolonner  == v1_to_v2.keys()  ⊎ DROPPED
    API-kolonner == api_to_v2.keys() ⊎ API_DROPPED
    v2_columns   == v1_to_v2.values() ⊎ ADDED ⊎ DERIVED

⊎ er disjunkt union: hver kolonne præcis ét sted, ingen udenfor.

Og spejlingen af den tredje, set fra API-vejen:

    v2_columns   == api_to_v2.values() ⊎ V1_ONLY ⊎ DERIVED

De to sidste er ikke den samme ligning. Er begge spande tomme, når begge
kilder hele v2-skemaet. Er de ikke, kan den ene kilde ikke producere en
komplet række — og det skal stå skrevet, ikke opdages i Gate 3.

--------------------------------------------------------------------------
MÅLEGRUNDLAG
--------------------------------------------------------------------------
Alle headere nedenfor er hentet i F6 Gate 1 (2026-08-08), ikke afskrevet fra
DATADISTRIBUTION_IMPLEMENTERING_V1.md §11.1. Referencedag for API-kaldene:
2026-03-15, `format=csv`. Klon-headere aflæst i df-data @ 6c95bde.

Tre ting §11.1 og Gate 0's referat ikke har med, og som er målt her:

  1. Klonens `spot/` har TRE forskellige headere, ikke én. Gate 1b målte hvor
     de kommer fra — se noten på `SPOT_DK`. `DE_2026.csv` har EUR FØR DKK;
     `DE_2025.csv` har DKK FØR EUR. Navnene er ærlige, kun rækkefølgen er
     byttet, fordi kilden selv skiftede. Læs derfor ALTID efter navn.
  2. `resolution_minutes` leveres KUN af api_entsoe_prices.php. Ingen af de
     fire balance-datasæt, hverken api_energinet_prices.php eller
     api_dmi_obs_ny.php har den. Den må ikke syntetiseres hvor den mangler.
  3. Klonens `spot_price_dkk` er IKKE beregnet af nogen i vores pipeline. Den
     er EDS' egen kolonne, målt identisk celle for celle (Gate 1b, DEL B).
     Der findes ingen valutakurs at rekonstruere — der er aldrig blevet
     omregnet.

--------------------------------------------------------------------------
ENDPOINT-KONTRAKTEN ER EN TABEL, IKKE EN REGEL (Gate 1d)
--------------------------------------------------------------------------
`ENDPOINT_CONTRACTS` beskriver hvert endpoint for sig. Der findes INGEN
fælles regel om tidszone, om hvad en bar dato betyder, eller om hvad der sker
med en ukendt parameter. To endpoints på samme vært gør modsatte ting:

    api_eds_balance.php        filtrerer på UTC,  afviser ukendt param (400)
    api_energinet_prices.php   filtrerer på DK,   ignorerer ukendt param tavst

`zone=DK1` på api_energinet_prices.php er præcis den fælde: parameteren
findes ikke (den hedder `area`), den ignoreres uden fejl, og svaret er begge
prisområder i stedet for ét. Det ligner et gyldigt svar.

UDLED ALDRIG ét endpoints opførsel af et andets. Slå op i tabellen.

--------------------------------------------------------------------------
ENHEDER STÅR I KONTRAKTEN, IKKE I NAVNET (Gate 1d)
--------------------------------------------------------------------------
`DatasetSchema.units` giver enheden for hver v2-kolonne. En enhed sættes KUN
når én af to ting gælder:

    a) endpointets eget OpenAPI-rækkeskema dokumenterer den, eller
    b) Gate 1d har målt den direkte.

Ellers står der `None`, og kolonnen er uafklaret. Enheden udledes ALDRIG af
kolonnenavnet: `afrr_up_mw` er `None`, ikke "MW", fordi ingen kilde siger det.
`price_eur_mwh` fra entsoe-endpointet er `None` af samme grund — navnet er
ikke en måling. Det er også svaret på hvorfor `spot_price_eur` beholder sit
navn selv om MWh ikke står i det: enheden hører her.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# --------------------------------------------------------------------------
# Fælles begrundelser — samme kolonne, samme grund, på tværs af datasæt.
# --------------------------------------------------------------------------

_WHY_LOCAL_TIME = (
    "Lokal tid er ikke entydig hen over efterårets DST-tilbagestilling. "
    "API'et advarer selv mod at bruge den som nøgle "
    "(meta.time_dk_note). Al tidslogik kører på UTC-aksen."
)
_WHY_AUDIT_STAMP = (
    "Kildesystemets hentetidsstempel, ikke måledata. Ændrer sig ved "
    "enhver revision og ville gøre ellers identiske rækker uens."
)
# Enheds-konstanter for de kolonner der ikke bærer en fysisk størrelse.
# De er ikke None: None betyder UAFKLARET, og disse to er afklarede.
_U_TS_UTC = "UTC-tidsstempel"
_U_ENUM = "tekst-enum"

_WHY_ENTSOE_REJECTED = (
    "api_entsoe_prices.php er forkastet som migrationsvej (Gate 1e). Ikke "
    "denne kolonnes skyld — hele vejen udgår, fordi endpointets tidsakse er "
    "dansk lokaltid i en kolonne dets meta kalder utc."
)

_WHY_DB_ID = (
    "Databaseintern nøgle uden betydning uden for kildedatabasen. Gate 0 "
    "målte at den afviger mellem API og klon selv hvor alle måleværdier er "
    "identiske."
)


@dataclass(frozen=True)
class Derived:
    """En v2-kolonne der genereres. Udtrykket er TEKST, ikke kode."""

    source: Tuple[str, ...]   # v2-kolonner udtrykket læser
    expression: str           # hvordan, i tekst
    reason: str


@dataclass(frozen=True)
class EndpointContract:
    """
    Hvordan ÉT endpoint opfører sig. Målt i F6 Gate 1d, ikke afskrevet.

    Hvert felt har en post i `status`: "målt" eller "uafklaret". Er et felt
    uafklaret, står værdien som None, og Gate 2 skal måle den — ikke låne
    naboens. `status` er obligatorisk for alle felterne i `CONTRACT_FIELDS`.
    """

    endpoint: str
    filter_timezone: Optional[str]        # "dk" | "utc"
    end_boundary: Optional[str]           # "eksklusiv" | "inklusiv-hele-døgnet"
    bare_date_semantics: Optional[str]
    unknown_param: Optional[str]          # "400" | "ignoreres tavst"
    limit_default: Optional[int]
    limit_max: Optional[int]
    limit_over_max: Optional[str]
    delivers_resolution: Optional[bool]
    status: Dict[str, str]
    area_param: Optional[str] = None
    area_values: Tuple[str, ...] = ()
    notes: str = ""


# Felterne `status` skal dække. De seks fra opgavens liste plus limit-parret,
# der ikke kan beskrives af ét tal alene.
CONTRACT_FIELDS = (
    "filter_timezone",
    "end_boundary",
    "bare_date_semantics",
    "unknown_param",
    "limit_max",
    "delivers_resolution",
)


@dataclass(frozen=True)
class DatasetSchema:
    """Ren datacontainer. Ingen adfærd."""

    name: str
    clone_path: str          # hvor v1 ligger i df-data-klonen
    endpoint: Optional[str]  # None = intet migrationsmål findes
    endpoint_params: Dict[str, str]
    # Klonens faktiske headere, ORDRET. Flere elementer = flere skemavarianter
    # i klonen; de skal alle kunne læses.
    v1_columns: Tuple[Tuple[str, ...], ...]
    api_columns: Tuple[str, ...]   # ORDRET som API'et leverer dem
    v2_columns: Tuple[str, ...]    # ORDRET. Den autoritative output-header.
    v1_to_v2: Dict[str, str]
    api_to_v2: Dict[str, str]
    dropped: Dict[str, str]
    api_dropped: Dict[str, str]
    added: Dict[str, str]
    key: Tuple[str, ...]
    derived: Dict[str, Derived] = field(default_factory=dict)
    v1_only: Dict[str, str] = field(default_factory=dict)
    # v2-navn → enhed, eller None hvis hverken målt eller dokumenteret.
    # Skal dække PRÆCIS v2_columns. Se modulets enhedsafsnit.
    units: Dict[str, Optional[str]] = field(default_factory=dict)
    # Kan datasættet overhovedet migreres? False kræver en begrundelse i
    # `not_migratable`, og omvendt. Se MIGRATIONSSPÆRRER.
    migratable: bool = True
    not_migratable: str = ""
    # Målt api_to_v2 der er FORKASTET som migrationsvej. Står her og ikke i
    # `api_to_v2`, fordi den sidste skal være tom når vejen er ubrugelig:
    # en ubrugelig mapping må ikke ligge og se brugbar ud. Målingen bevares,
    # beslutningen er en anden.
    api_to_v2_rejected: Dict[str, str] = field(default_factory=dict)
    api_path_rejected: str = ""
    notes: str = ""


# ==========================================================================
# 1. imbalance_price  —  klon: imbalance/  —  v1 18, API 20, v2 17
# ==========================================================================

_IMBALANCE_V1_TO_V2 = {
    "TimeUTC":                  "time_utc",
    "PriceArea":                "price_area",
    "SatisfiedDemand":          "satisfied_demand",
    "ImbalancePriceEUR":        "imbalance_price_eur",
    "ImbalancePriceDKK":        "imbalance_price_dkk",
    "SpotPriceEUR":             "spot_price_eur",
    "DominatingDirection":      "dominating_direction",
    # aFRR → afrr, ikke a_frr.
    "aFRRUpMW":                 "afrr_up_mw",
    "aFRRVWAUpEUR":             "afrr_vwa_up_eur",
    "aFRRVWAUpDKK":             "afrr_vwa_up_dkk",
    "aFRRDownMW":               "afrr_down_mw",
    "aFRRVWADownEUR":           "afrr_vwa_down_eur",
    "aFRRVWADownDKK":           "afrr_vwa_down_dkk",
    # mFRR → mfrr, ikke m_frr.
    "mFRRMarginalPriceUpEUR":   "mfrr_marginal_price_up_eur",
    "mFRRMarginalPriceUpDKK":   "mfrr_marginal_price_up_dkk",
    "mFRRMarginalPriceDownEUR": "mfrr_marginal_price_down_eur",
    "mFRRMarginalPriceDownDKK": "mfrr_marginal_price_down_dkk",
}

IMBALANCE_PRICE = DatasetSchema(
    name="imbalance_price",
    clone_path="imbalance/{area}_{year}.csv",
    endpoint="/api_eds_balance.php",
    endpoint_params={"dataset": "imbalance_price"},
    v1_columns=((
        "TimeUTC", "TimeDK", "PriceArea", "SatisfiedDemand",
        "ImbalancePriceEUR", "ImbalancePriceDKK", "SpotPriceEUR",
        "DominatingDirection", "aFRRUpMW", "aFRRVWAUpEUR", "aFRRVWAUpDKK",
        "aFRRDownMW", "aFRRVWADownEUR", "aFRRVWADownDKK",
        "mFRRMarginalPriceUpEUR", "mFRRMarginalPriceUpDKK",
        "mFRRMarginalPriceDownEUR", "mFRRMarginalPriceDownDKK",
    ),),
    api_columns=(
        "time_utc", "time_dk", "price_area", "satisfied_demand",
        "imbalance_price_eur", "imbalance_price_dkk", "spot_price_eur",
        "dominating_direction", "afrr_up_mw", "afrr_vwa_up_eur",
        "afrr_vwa_up_dkk", "afrr_down_mw", "afrr_vwa_down_eur",
        "afrr_vwa_down_dkk", "mfrr_marginal_price_up_eur",
        "mfrr_marginal_price_up_dkk", "mfrr_marginal_price_down_eur",
        "mfrr_marginal_price_down_dkk", "created_at", "updated_at",
    ),
    v2_columns=(
        "time_utc", "price_area", "satisfied_demand",
        "imbalance_price_eur", "imbalance_price_dkk", "spot_price_eur",
        "dominating_direction", "afrr_up_mw", "afrr_vwa_up_eur",
        "afrr_vwa_up_dkk", "afrr_down_mw", "afrr_vwa_down_eur",
        "afrr_vwa_down_dkk", "mfrr_marginal_price_up_eur",
        "mfrr_marginal_price_up_dkk", "mfrr_marginal_price_down_eur",
        "mfrr_marginal_price_down_dkk",
    ),
    v1_to_v2=_IMBALANCE_V1_TO_V2,
    api_to_v2={c: c for c in _IMBALANCE_V1_TO_V2.values()},   # identitet
    dropped={"TimeDK": _WHY_LOCAL_TIME},
    api_dropped={
        "time_dk":    _WHY_LOCAL_TIME,
        "created_at": _WHY_AUDIT_STAMP,
        "updated_at": _WHY_AUDIT_STAMP,
    },
    added={},
    key=("time_utc", "price_area"),
    units={
        # Målt: meta.timezone == "utc", meta.range_utc, og time_dk = +1/+2.
        "time_utc":                     _U_TS_UTC,
        "price_area":                   _U_ENUM,   # spec: enum ["DK1","DK2"]
        "satisfied_demand":             None,
        "imbalance_price_eur":          "EUR/MWh",  # spec
        "imbalance_price_dkk":          "DKK/MWh",  # spec
        "spot_price_eur":               "EUR/MWh",  # spec
        # spec: "Observerede værdier: -1, 0, 1 samt NULL."
        "dominating_direction":         "enum (-1, 0, 1, NULL)",
        "afrr_up_mw":                   None,
        "afrr_vwa_up_eur":              "EUR/MWh",  # spec
        "afrr_vwa_up_dkk":              None,
        "afrr_down_mw":                 None,
        "afrr_vwa_down_eur":            None,
        "afrr_vwa_down_dkk":            None,
        "mfrr_marginal_price_up_eur":   None,
        "mfrr_marginal_price_up_dkk":   None,
        "mfrr_marginal_price_down_eur": None,
        "mfrr_marginal_price_down_dkk": None,
    },
    notes=(
        "15-minutters opløsning. Ingen resolution_minutes i svaret — den må "
        "ikke syntetiseres. Klonen har 0 dubletter på (TimeUTC, PriceArea) "
        "over 92 240 rækker (2025-03-04 .. 2026-06-27)."
    ),
)


# ==========================================================================
# 2. mfrr_activation  —  klon: mfrr_act/  —  v1 19, API 21, v2 18
# ==========================================================================

_MFRR_ACT_V1_TO_V2 = {
    "TimeUTC":            "time_utc",
    "PriceArea":          "price_area",
    # SA = scheduled activation, DA = direct activation. Akronymet bevares
    # som ét led: mFRRSAUp… → mfrr_sa_up_…, ikke m_frrsa_up_…
    "mFRRSAUpReqMW":      "mfrr_sa_up_req_mw",
    "mFRRSAUpEUR":        "mfrr_sa_up_eur",
    "mFRRSADownReqMW":    "mfrr_sa_down_req_mw",
    "mFRRSADownEUR":      "mfrr_sa_down_eur",
    "mFRRDAUpMW":         "mfrr_da_up_mw",
    "mFRRDAUpEUR":        "mfrr_da_up_eur",
    "mFRRDADownMW":       "mfrr_da_down_mw",
    "mFRRDADownEUR":      "mfrr_da_down_eur",
    # Total-præfikset flytter foran akronymet: TotalmFRRUpMW →
    # total_mfrr_up_mw, ikke totalm_frr_up_mw. Bekræftet i §11.1.
    "TotalmFRRUpMW":      "total_mfrr_up_mw",
    "TotalmFRRDownMW":    "total_mfrr_down_mw",
    "mFRROfferedUpMW":    "mfrr_offered_up_mw",
    "mFRROfferedDownMW":  "mfrr_offered_down_mw",
    "mFRRLocalUpMW":      "mfrr_local_up_mw",
    "mFRRLocalDownMW":    "mfrr_local_down_mw",
    "mFRRSpecialUpMW":    "mfrr_special_up_mw",
    "mFRRSpecialDownMW":  "mfrr_special_down_mw",
}

MFRR_ACTIVATION = DatasetSchema(
    name="mfrr_activation",
    clone_path="mfrr_act/{area}_{year}.csv",
    endpoint="/api_eds_balance.php",
    endpoint_params={"dataset": "mfrr_activation"},
    v1_columns=((
        "TimeUTC", "TimeDK", "PriceArea",
        "mFRRSAUpReqMW", "mFRRSAUpEUR", "mFRRSADownReqMW", "mFRRSADownEUR",
        "mFRRDAUpMW", "mFRRDAUpEUR", "mFRRDADownMW", "mFRRDADownEUR",
        "TotalmFRRUpMW", "TotalmFRRDownMW",
        "mFRROfferedUpMW", "mFRROfferedDownMW",
        "mFRRLocalUpMW", "mFRRLocalDownMW",
        "mFRRSpecialUpMW", "mFRRSpecialDownMW",
    ),),
    api_columns=(
        "time_utc", "time_dk", "price_area",
        "mfrr_sa_up_req_mw", "mfrr_sa_up_eur",
        "mfrr_sa_down_req_mw", "mfrr_sa_down_eur",
        "mfrr_da_up_mw", "mfrr_da_up_eur",
        "mfrr_da_down_mw", "mfrr_da_down_eur",
        "total_mfrr_up_mw", "total_mfrr_down_mw",
        "mfrr_offered_up_mw", "mfrr_offered_down_mw",
        "mfrr_local_up_mw", "mfrr_local_down_mw",
        "mfrr_special_up_mw", "mfrr_special_down_mw",
        "created_at", "updated_at",
    ),
    v2_columns=(
        "time_utc", "price_area",
        "mfrr_sa_up_req_mw", "mfrr_sa_up_eur",
        "mfrr_sa_down_req_mw", "mfrr_sa_down_eur",
        "mfrr_da_up_mw", "mfrr_da_up_eur",
        "mfrr_da_down_mw", "mfrr_da_down_eur",
        "total_mfrr_up_mw", "total_mfrr_down_mw",
        "mfrr_offered_up_mw", "mfrr_offered_down_mw",
        "mfrr_local_up_mw", "mfrr_local_down_mw",
        "mfrr_special_up_mw", "mfrr_special_down_mw",
    ),
    v1_to_v2=_MFRR_ACT_V1_TO_V2,
    api_to_v2={c: c for c in _MFRR_ACT_V1_TO_V2.values()},   # identitet
    dropped={"TimeDK": _WHY_LOCAL_TIME},
    api_dropped={
        "time_dk":    _WHY_LOCAL_TIME,
        "created_at": _WHY_AUDIT_STAMP,
        "updated_at": _WHY_AUDIT_STAMP,
    },
    added={},
    key=("time_utc", "price_area"),
    # EdsMfrrActivationRow dokumenterer INGEN enheder. Alle 16 måletal er
    # derfor None. At `…_mw` og `…_eur` står i navnene er ikke en måling.
    units={
        "time_utc":   _U_TS_UTC,
        "price_area": _U_ENUM,
        **{c: None for c in _MFRR_ACT_V1_TO_V2.values()
           if c not in ("time_utc", "price_area")},
    },
    notes=(
        "15-minutters opløsning, ingen resolution_minutes i svaret. Gate 0 "
        "målte at mfrr_da_* og mfrr_special_up_mw er tomme i BÅDE API og klon "
        "i det målte vindue — tomheden er sammenfaldende, ikke et datatab."
    ),
)


# ==========================================================================
# 3. mfrr_capacity  —  klon: mfrr_cap/  —  v1 11, API 14, v2 11
#    Det eneste datasæt hvor API'et har en DIMENSION klonen mangler.
# ==========================================================================

_CAPACITY_V1_TO_V2 = {
    "TimeUTC":        "time_utc",
    "PriceArea":      "price_area",
    "UpDemandMW":     "up_demand_mw",
    "UpProcuredMW":   "up_procured_mw",
    "UpPriceEUR":     "up_price_eur",
    "UpPriceDKK":     "up_price_dkk",
    "DownDemandMW":   "down_demand_mw",
    "DownProcuredMW": "down_procured_mw",
    "DownPriceEUR":   "down_price_eur",
    "DownPriceDKK":   "down_price_dkk",
}

_CAPACITY_V1_COLS = (
    "TimeUTC", "TimeDK", "PriceArea",
    "UpDemandMW", "UpProcuredMW", "UpPriceEUR", "UpPriceDKK",
    "DownDemandMW", "DownProcuredMW", "DownPriceEUR", "DownPriceDKK",
)

MFRR_CAPACITY = DatasetSchema(
    name="mfrr_capacity",
    clone_path="mfrr_cap/{area}_{year}.csv",
    endpoint="/api_eds_balance.php",
    endpoint_params={"dataset": "mfrr_capacity"},
    v1_columns=(_CAPACITY_V1_COLS,),
    api_columns=(
        "time_utc", "time_dk", "price_area", "auction",
        "up_demand_mw", "up_procured_mw", "up_price_eur", "up_price_dkk",
        "down_demand_mw", "down_procured_mw", "down_price_eur",
        "down_price_dkk", "created_at", "updated_at",
    ),
    v2_columns=(
        "time_utc", "price_area", "auction",
        "up_demand_mw", "up_procured_mw", "up_price_eur", "up_price_dkk",
        "down_demand_mw", "down_procured_mw", "down_price_eur",
        "down_price_dkk",
    ),
    v1_to_v2=_CAPACITY_V1_TO_V2,
    api_to_v2={**{c: c for c in _CAPACITY_V1_TO_V2.values()},
               "auction": "auction"},                        # identitet
    dropped={"TimeDK": _WHY_LOCAL_TIME},
    api_dropped={
        "time_dk":    _WHY_LOCAL_TIME,
        "created_at": _WHY_AUDIT_STAMP,
        "updated_at": _WHY_AUDIT_STAMP,
    },
    added={
        "auction": (
            "Udbudsrunde, enum ['main','extra']. Klonen har den ikke og kan "
            "derfor ikke skelne runderne. Gate 1 målte 'extra' = 0 rækker "
            "over hele tabellens levetid (2023-06-20 .. 2026-08-10), så "
            "kolonnen er i dag konstant 'main' — men den ER en dimension, og "
            "et fremtidigt extra-udbud ville fordoble rækker pr. tidsstempel "
            "USYNLIGT hvis den udelades. Derfor med, og derfor i KEY.\n"
            "INGEN BACKFILL. Værdien kommer fra kilden ved genhentning, "
            "eller også kommer den ikke. En v1-fil uden kolonnen forbliver "
            "v1 — den skal hverken have 'main' skrevet ind, en tom streng, "
            "eller NULL. At udfylde den ville påstå at vi havde målt hvilken "
            "udbudsrunde en historisk række tilhørte; det har vi ikke. "
            "Gate 2 må derfor ikke antage at alle rækker i et migreret "
            "datasæt har samme kolonner."
        ),
    },
    key=("time_utc", "price_area", "auction"),
    units={
        "time_utc":         _U_TS_UTC,
        "price_area":       _U_ENUM,
        "auction":          _U_ENUM,    # spec dokumenterer den som enum
        "up_demand_mw":     None,
        "up_procured_mw":   None,
        "up_price_eur":     "EUR/MW",   # spec: "Kapacitetspris op, EUR/MW"
        "up_price_dkk":     "DKK/MW",   # spec
        "down_demand_mw":   None,
        "down_procured_mw": None,
        "down_price_eur":   None,       # spec dokumenterer kun op-siden
        "down_price_dkk":   None,
    },
    notes=(
        "Timeopløsning. Fremadrettet tabel: uden enddate rækker den ~29,7 "
        "timer frem (Gate 0). Sæt ALTID eksplicit enddate. "
        "auction er i KEY selv om den er konstant i dag — nøglen skal "
        "beskytte mod den fremtid hvor den ikke er det.\n"
        "Følgen af at auction ikke backfilles: en v1-række kan ikke danne "
        "en fuld KEY. To rækker fra hver sin kilde er derfor ikke "
        "sammenlignelige på nøglen uden at nogen først beslutter hvad en "
        "manglende auction betyder. Den beslutning er ikke truffet her."
    ),
)


# ==========================================================================
# 4. afrr_capacity  —  klon: afrr/  —  v1 11, API 13, v2 10
#    Samme kolonner som mfrr_capacity, men UDEN auction.
# ==========================================================================

AFRR_CAPACITY = DatasetSchema(
    name="afrr_capacity",
    clone_path="afrr/{area}_{year}.csv",
    endpoint="/api_eds_balance.php",
    endpoint_params={"dataset": "afrr_capacity"},
    v1_columns=(_CAPACITY_V1_COLS,),
    api_columns=(
        "time_utc", "time_dk", "price_area",
        "up_demand_mw", "up_procured_mw", "up_price_eur", "up_price_dkk",
        "down_demand_mw", "down_procured_mw", "down_price_eur",
        "down_price_dkk", "created_at", "updated_at",
    ),
    v2_columns=(
        "time_utc", "price_area",
        "up_demand_mw", "up_procured_mw", "up_price_eur", "up_price_dkk",
        "down_demand_mw", "down_procured_mw", "down_price_eur",
        "down_price_dkk",
    ),
    v1_to_v2=_CAPACITY_V1_TO_V2,
    api_to_v2={c: c for c in _CAPACITY_V1_TO_V2.values()},   # identitet
    dropped={"TimeDK": _WHY_LOCAL_TIME},
    api_dropped={
        "time_dk":    _WHY_LOCAL_TIME,
        "created_at": _WHY_AUDIT_STAMP,
        "updated_at": _WHY_AUDIT_STAMP,
    },
    added={},
    key=("time_utc", "price_area"),
    units={
        "time_utc":         _U_TS_UTC,
        "price_area":       _U_ENUM,
        "up_demand_mw":     None,
        "up_procured_mw":   None,
        "up_price_eur":     "EUR/MW",   # spec
        "up_price_dkk":     "DKK/MW",   # spec
        "down_demand_mw":   None,
        "down_procured_mw": None,
        "down_price_eur":   None,
        "down_price_dkk":   None,
    },
    notes=(
        "Timeopløsning. Ingen auction-kolonne — API'et afviser parameteren "
        "med 400 på dette datasæt. KEY er derfor ét led kortere end "
        "mfrr_capacity's. Klonen har kun DK1 (ingen DK2-filer)."
    ),
)


# ==========================================================================
# 5. spot_dk  —  klon: spot/DK1_*, spot/DK2_*  —  api_energinet_prices.php
#    TO v1-varianter i klonen. Navnene er allerede snake_case: nul omdøbninger.
# ==========================================================================

_SPOT_DK_KEPT = ("hour_utc", "price_area", "spot_price_dkk", "spot_price_eur")

SPOT_DK = DatasetSchema(
    name="spot_dk",
    clone_path="spot/{DK1|DK2}_{year}.csv",
    endpoint="/api_energinet_prices.php",
    endpoint_params={},
    v1_columns=(
        # Variant A — DK1/DK2 2022 og 2024. Ingen id/created_at/updated_at.
        ("hour_utc", "hour_dk", "price_area", "spot_price_dkk",
         "spot_price_eur"),
        # Variant C — DK1/DK2 2023, 2025, 2026. Otte kolonner.
        ("id", "hour_utc", "hour_dk", "price_area", "spot_price_dkk",
         "spot_price_eur", "created_at", "updated_at"),
    ),
    api_columns=(
        "id", "hour_utc", "hour_dk", "price_area",
        "spot_price_dkk", "spot_price_eur", "created_at", "updated_at",
    ),
    v2_columns=_SPOT_DK_KEPT,
    # Rene identitets-par. Klonen er allerede på API'ets navngivning her,
    # fordi update_data.py omdøbte EDS-navnene ved hentning.
    v1_to_v2={c: c for c in _SPOT_DK_KEPT},
    api_to_v2={c: c for c in _SPOT_DK_KEPT},
    dropped={
        "hour_dk":    _WHY_LOCAL_TIME,
        "id":         _WHY_DB_ID,
        "created_at": _WHY_AUDIT_STAMP,
        "updated_at": _WHY_AUDIT_STAMP,
    },
    api_dropped={
        "hour_dk":    _WHY_LOCAL_TIME,
        "id":         _WHY_DB_ID,
        "created_at": _WHY_AUDIT_STAMP,
        "updated_at": _WHY_AUDIT_STAMP,
    },
    added={},
    key=("hour_utc", "price_area"),
    units={
        # Målt Gate 1d: hour_dk − hour_utc = +1 t i marts, +2 t i juli.
        # Kolonnen ER UTC, selv om FILTERET er dansk lokaltid.
        "hour_utc":       _U_TS_UTC,
        "price_area":     _U_ENUM,      # "Use DK1 or DK2" (målt 400-krop)
        "spot_price_dkk": "DKK/MWh",    # spec: "Spot price in DKK/MWh"
        "spot_price_eur": "EUR/MWh",    # spec: "Spot price in EUR/MWh"
    },
    notes=(
        "TRE HEADERE I spot/, OG HVOR DE KOMMER FRA (målt i Gate 1b).\n"
        "Klonens spot/-mappe er skrevet af tre forskellige kilder. Ingen af "
        "dem har beregnet noget — hver variant er kildens egen kolonneorden:\n"
        "  A  hour_utc,hour_dk,price_area,spot_price_dkk,spot_price_eur\n"
        "     ← EDS `Elspotprices`. Målt 2025-06-15/DE: kolonner "
        "     HourUTC,HourDK,PriceArea,SpotPriceDKK,SpotPriceEUR — DKK FØR "
        "     EUR, timeopløsning. 24 filer.\n"
        "  B  …,spot_price_eur,spot_price_dkk\n"
        "     ← EDS `DayAheadPrices`. Målt 2026-06-01/DE: kolonner "
        "     TimeUTC,TimeDK,PriceArea,DayAheadPriceEUR,DayAheadPriceDKK — "
        "     EUR FØR DKK, 15-min. 4 filer (DE/NO2/SE3/SE4 2026).\n"
        "  C  id,…,created_at,updated_at\n"
        "     ← api_energinet_prices.php (denne proxy). Kun DK1/DK2, fordi "
        "     endpointets enum er ['DK1','DK2']. 6 filer.\n"
        "spot/DK1_2026.csv er en BLANDING: 8 632 rækker med id (proxy, "
        "2026-01-01 .. 2026-03-31 21:45) og 8 448 uden (EDS DayAheadPrices, "
        "fra 2026-03-31 22:00). hour_dk-formatet er fingeraftrykket: "
        "ISO-'T' = EDS, mellemrum = proxy.\n"
        "Ingen resolution_minutes. Data skifter fra time- til 15-minutters "
        "opløsning inde i filerne uden at nogen kolonne siger det.\n"
        "Målt: area=DK1 RESPEKTERES af endpointet (96 rækker, kun DK1). "
        "Gate 1d målte også den anden halvdel: `zone` er IKKE en parameter "
        "her. zone=DK1 og zone=DK2 giver begge 192 rækker med BÅDE DK1 og "
        "DK2 — parameteren ignoreres tavst, og svaret ser gyldigt ud. "
        "Docstringen i src/data_loader.py:588 er dermed målt korrekt. "
        "Filtrér på `area`, aldrig på `zone`."
    ),
)


# ==========================================================================
# 6. spot_entsoe  —  klon: spot/DE_*, NO2_*, SE3_*, SE4_*
#    api_entsoe_prices.php. Det eneste datasæt hvor api_to_v2 IKKE er identitet.
# ==========================================================================

SPOT_ENTSOE = DatasetSchema(
    name="spot_entsoe",
    clone_path="spot/{DE|NO2|SE3|SE4}_{year}.csv",
    endpoint="/api_entsoe_prices.php",
    endpoint_params={},
    v1_columns=(
        # Variant A — 2022..2025, fra EDS `Elspotprices`: DKK FØR EUR.
        ("hour_utc", "hour_dk", "price_area", "spot_price_dkk",
         "spot_price_eur"),
        # Variant B — 2026, fra EDS `DayAheadPrices`: EUR FØR DKK. Samme
        # navne, byttet rækkefølge, fordi kildens JSON-nøgleorden skiftede.
        # Læses der efter position, bytter de to valutaer plads uden at
        # noget fejler. Læs efter navn.
        ("hour_utc", "hour_dk", "price_area", "spot_price_eur",
         "spot_price_dkk"),
    ),
    api_columns=("timestamp", "area", "price_eur_mwh", "resolution_minutes"),
    # resolution_minutes ER UDGÅET AF v2 (Gate 1e). Den stod i ADDED, altså
    # "kun API'et kan levere den" — og da vejen blev forkastet, blev der ikke
    # nogen kilde tilbage. En kolonne uden kilde må ikke blive stående i
    # v2_columns; så ville Gate 2 skulle finde på den. Målingen af at
    # endpointet leverede den står stadig i ENDPOINTS_WITH_RESOLUTION_MINUTES
    # og i ENDPOINT_CONTRACTS — det er en sand oplysning om et endpoint vi
    # bare ikke bruger.
    v2_columns=("hour_utc", "price_area", "spot_price_eur", "spot_price_dkk"),
    migratable=False,
    not_migratable=(
        "MÅLET DUER IKKE. api_entsoe_prices.php leverer dansk lokaltid i "
        "kolonnen `timestamp`, som dets eget meta kalder `utc`. Målt tre "
        "gange uafhængigt — se notes. Det er en anden grund end "
        "spot_system's: dér findes INGEN kilde, her findes en kilde der "
        "svarer forkert. Begge er spærret for migration, men kun den ene kan "
        "åbnes ved at rette et endpoint.\n"
        "BESLUTTET: eget API udvides til DayAheadPrices for alle seks "
        "områder. Indtil det er på plads har spot_entsoe ingen "
        "migrationsvej, og klonens filer skal bevares uændret."
    ),
    v1_to_v2={
        "hour_utc":       "hour_utc",
        "price_area":     "price_area",
        "spot_price_eur": "spot_price_eur",
        "spot_price_dkk": "spot_price_dkk",
    },
    # TOM MED VILJE. api_entsoe_prices.php er ikke migrationsvej (Gate 1e C1),
    # og en ubrugelig mapping må ikke ligge og se brugbar ud. Den MÅLTE
    # mapping er bevaret i api_to_v2_rejected nedenfor — beslutningen er en
    # anden ting end målingen, og begge skal kunne læses.
    api_to_v2={},
    api_to_v2_rejected={
        "timestamp":          "hour_utc",         # ← selve fejlen, se notes
        "area":               "price_area",
        "price_eur_mwh":      "spot_price_eur",   # C1-normalisering
        "resolution_minutes": "resolution_minutes",
    },
    api_path_rejected=(
        "api_entsoe_prices.php leverer dansk lokaltid i en kolonne dets eget "
        "meta kalder utc. Vejen er UBRUGELIG, ikke uafklaret: der er intet "
        "tilbage at måle, og en tz-konvertering ville være en beregnet "
        "kolonne. Egen API udvides i stedet til DayAheadPrices for alle seks "
        "områder."
    ),
    dropped={"hour_dk": _WHY_LOCAL_TIME},
    # Alle fire API-kolonner udgår, fordi hele vejen udgår. Det er ikke fire
    # enkeltbeslutninger — det er én.
    api_dropped={
        "timestamp":          _WHY_ENTSOE_REJECTED,
        "area":               _WHY_ENTSOE_REJECTED,
        "price_eur_mwh":      _WHY_ENTSOE_REJECTED,
        "resolution_minutes": _WHY_ENTSOE_REJECTED,
    },
    # TOM. Havde `resolution_minutes` — den udgik med vejen, se v2_columns.
    # Det var gatens eneste ADDED uden for mfrr_capacity.auction.
    added={},
    v1_only={
        "hour_utc": _WHY_ENTSOE_REJECTED,
        "price_area": _WHY_ENTSOE_REJECTED,
        "spot_price_eur": _WHY_ENTSOE_REJECTED,
        "spot_price_dkk": (
            "Klonen HAR den; api_entsoe_prices.php har den ikke. "
            "Gate 1b målte at spot_price_dkk er EDS' egen "
            "DayAheadPriceDKK/SpotPriceDKK, overtaget uændret — 88/88 celler "
            "identiske, max Δ = 0. Den er altså kildedata og bæres med, ikke "
            "et regnestykke der kunne genskabes. "
            "KONSEKVENS: api_entsoe_prices.php kan IKKE producere en komplet "
            "spot_entsoe-række. Vælges det endpoint, mangler DKK. EDS "
            "leverer begge valutaer. Det er et kildevalg, og det er ikke "
            "truffet her — se OPEN_QUESTIONS."
        ),
    },
    key=("hour_utc", "price_area"),
    units={
        # None, IKKE fordi enheden er ukendt, men fordi kolonnens BETYDNING
        # er bestridt: klonens hour_utc er UTC, mens API'ets `timestamp`
        # er målt til dansk lokaltid. Se UNRESOLVED.
        "hour_utc":           None,
        "price_area":         _U_ENUM,
        # EntsoePriceRow.price_eur_mwh har INGEN description i OpenAPI-specen.
        # Navnet er ikke en måling — derfor None. Klonens spot_price_eur er
        # heller ikke dokumenteret nogen steder.
        "spot_price_eur":     None,
        # Findes slet ikke i EntsoePriceRow; kun klonen har den.
        "spot_price_dkk":     None,
    },
    notes=(
        "⚠ TIDSAKSEN ER MÅLT FORKERT I api_to_v2 (Gate 1d). "
        "`timestamp` afbildes til `hour_utc`, men kolonnen er IKKE UTC. Målt "
        "tre gange, uafhængigt: mod api_energinet_prices.php på en vinterdag "
        "(2026-03-15) og en sommerdag (2026-07-15), og mod klonens "
        "DK1_2026.csv. Alle tre gange falder `timestamp` sammen med `hour_dk` "
        "— 96/96 rækker med maks |Δ EUR| = 0 — og IKKE med `hour_utc` "
        "(1/96 og 0/88, maks |Δ| = 41,15 hhv. 70,01). Forskydningen er +1 t i "
        "marts og +2 t i juli, altså Europe/Copenhagen, ikke fast CET. "
        "Endpointets eget meta hævder `timezone: utc`; målingen vinder.\n"
        "AFGJORT I GATE 1e: vejen forkastes. Begge udveje var beslutninger, "
        "og ingen af dem er acceptable — en tz-konvertering ville være en "
        "beregnet kolonne (forbudt siden Gate 1), og at kalde kolonnen "
        "`hour_dk` ville lægge lokaltid i v2 (som _WHY_LOCAL_TIME forbyder). "
        "Derfor migreres spot_entsoe ikke via dette endpoint overhovedet: "
        "`api_to_v2` er TOM, alle fire API-kolonner står i API_DROPPED, og "
        "den målte mapping er flyttet til `api_to_v2_rejected` så den kan "
        "læses uden at kunne bruges. Egen API udvides i stedet til "
        "DayAheadPrices for alle seks områder; til den tid er dette datasæt "
        "en ny måling værd, ikke en genbrugt.\n"
        "A3-NORMALISERING (akserne). API'et kalder tidsaksen `timestamp` og "
        "områdeaksen `area`; alle andre spot-datasæt kalder dem `hour_utc` og "
        "`price_area`. v2 bruger `hour_utc`/`price_area`, så spot/-mappen "
        "ikke rummer to navne for samme akse. Det var §2.3's fælde.\n"
        "C1-NORMALISERING (målet). API'ets `price_eur_mwh` bliver til "
        "`spot_price_eur` i v2, af nøjagtigt samme grund: samme mappe må ikke "
        "rumme to navne for samme MÅL. `spot_dk.spot_price_eur` og dette er "
        "den samme størrelse i den samme enhed, og de hedder nu det samme. "
        "Enheden går tabt i navnet — MWh står ikke længere i det — men "
        "`spot_dk` har aldrig båret den, og to navne for én størrelse er den "
        "dyrere fejl.\n"
        "IKKE OMFATTET AF NOGEN NORMALISERING — og ikke løst: "
        "område-VÆRDIERNE. Klonen bruger DE/NO2/SE3/SE4, "
        "api_entsoe_prices.php kræver DE_LU/NO_2/SE_3/SE_4 og svarer 400 på "
        "de korte. Filnavne og kolonneværdier beholder klonens koder. En "
        "værdimapping er en anden opgave end en navnemapping, og den er ikke "
        "truffet her. Gate 2 må ikke gætte den.\n"
        "MIGRATIONSSPÆRRE: NO2/SE3/SE4 giver 0 rækker fra dette endpoint på "
        "alle datoer Gate 0 prøvede. Gate 1b målte at EDS DayAheadPrices "
        "DERIMOD har alle fire områder gennem hele hullet — kildemanglen "
        "gælder entsoe-endpointet, ikke dataene. Gate 1d målte formen på det "
        "tomme svar: area=SE_3 og area=NO_2 giver HTTP 200 med en krop på 0 "
        "bytes — ingen header, ingen fejl. En CSV-læser fejler på det; en "
        "'ingen rækker'-gren gør det ikke. Behandl 0 bytes som udeblevet svar."
    ),
)


# ==========================================================================
# 7. dmi_obs  —  klon: dmi/  —  api_dmi_obs_ny.php
#    v1 11, API 11, v2 10. Det eneste datasæt med en DERIVED-kolonne.
# ==========================================================================

_DMI_KEPT = (
    "unixtime", "area",
    "temp_mean_past1h", "radia_glob_past1h", "wind_speed_past1h",
    "precip_past1h", "pressure", "humidity_past1h", "cloud_cover",
)

_DMI_COLS = (
    "unixtime", "hour_utc", "hour_dk", "area",
    "temp_mean_past1h", "radia_glob_past1h", "wind_speed_past1h",
    "precip_past1h", "pressure", "humidity_past1h", "cloud_cover",
)

_WHY_DMI_HOUR_UTC = (
    "Kildens egen hour_utc er MÅLT FORKERT i én time om året. Ved efterårets "
    "DST-tilbagestilling giver API'et to forskellige observationer samme "
    "hour_utc (Gate 0: unixtime=1761440400 kommer ud som 2025-10-26 00:00, "
    "men er 01:00). Klonen er ramt af det samme: dmi/fyn_*.csv har 23 rækker "
    "hvor der skulle være 24 på 2023-10-29, 2024-10-27 og 2025-10-26 — "
    "hentningen deduperede på hour_utc og tabte den ene. Begge kilders "
    "hour_utc droppes derfor, og v2's genereres i stedet."
)

DMI_OBS = DatasetSchema(
    name="dmi_obs",
    clone_path="dmi/{station}_{year}.csv",
    endpoint="/api_dmi_obs_ny.php",
    endpoint_params={},
    v1_columns=(_DMI_COLS,),
    api_columns=_DMI_COLS,
    v2_columns=(
        "unixtime", "hour_utc", "area",
        "temp_mean_past1h", "radia_glob_past1h", "wind_speed_past1h",
        "precip_past1h", "pressure", "humidity_past1h", "cloud_cover",
    ),
    v1_to_v2={c: c for c in _DMI_KEPT},
    api_to_v2={c: c for c in _DMI_KEPT},                     # identitet
    dropped={"hour_dk": _WHY_LOCAL_TIME, "hour_utc": _WHY_DMI_HOUR_UTC},
    api_dropped={"hour_dk": _WHY_LOCAL_TIME, "hour_utc": _WHY_DMI_HOUR_UTC},
    added={},
    derived={
        "hour_utc": Derived(
            source=("unixtime",),
            expression='pd.Timestamp(unixtime, unit="s")',
            reason=(
                "Gate 0 målte at udtrykket rammer kildens hour_utc 48/48 uden "
                "for DST og RETTER den ene time hvor kilden tager fejl "
                "(47/48 på 2025-10-25/26, hvor afvigelsen er kildens fejl). "
                "unixtime er entydig i alle målte tilfælde — 91 725 rækker, "
                "0 dubletter. Efter genereringen er hour_utc både korrekt OG "
                "entydig, hvilket ingen af de to kilders egen hour_utc er."
            ),
        ),
    },
    key=("unixtime", "area"),
    units={
        "unixtime":           "s",       # spec: "Unix timestamp (UTC seconds)"
        "hour_utc":           _U_TS_UTC,  # DERIVED af unixtime, se derived
        "area":               _U_ENUM,
        "temp_mean_past1h":   "°C",      # spec
        "radia_glob_past1h":  "W/m²",    # spec
        "wind_speed_past1h":  "m/s",     # spec
        "precip_past1h":      "mm",      # spec
        "pressure":           "hPa",     # spec
        "humidity_past1h":    "%",       # spec
        "cloud_cover":        "%",       # spec
    },
    notes=(
        "UNDTAGELSEN: unixtime BLIVER, og den er nøglen. Det er ikke en "
        "forglemmelse.\n"
        "KEY forbliver (unixtime, area) — IKKE (hour_utc, area) — selv om "
        "den genererede hour_utc er entydig. Nøglen skal pege på den kolonne "
        "der bærer entydigheden i sig selv, ikke på en afledning af den. "
        "Ændrer nogen udtrykket i DERIVED, må nøglen ikke følge med i "
        "faldet.\n"
        "Konsekvens for aflæsning af tal: at klonen har 0 dubletter på "
        "(hour_utc, area) er IKKE bevis for at hour_utc er en sikker nøgle. "
        "Det er sporet efter at rækkerne allerede er tabt."
    ),
)


# ==========================================================================
# 8. spot_system  —  klon: spot/SYSTEM_*  —  INTET ENDPOINT
# ==========================================================================

_WHY_NO_TARGET = "Intet migrationsmål — se notes."

SPOT_SYSTEM = DatasetSchema(
    name="spot_system",
    clone_path="spot/SYSTEM_{year}.csv",
    endpoint=None,
    endpoint_params={},
    v1_columns=((
        "hour_utc", "hour_dk", "price_area", "spot_price_dkk",
        "spot_price_eur",
    ),),
    api_columns=(),
    v2_columns=(),
    v1_to_v2={},
    api_to_v2={},
    dropped={
        "hour_utc":       _WHY_NO_TARGET,
        "hour_dk":        _WHY_NO_TARGET,
        "price_area":     _WHY_NO_TARGET,
        "spot_price_dkk": _WHY_NO_TARGET,
        "spot_price_eur": _WHY_NO_TARGET,
    },
    api_dropped={},
    added={},
    key=("hour_utc", "price_area"),
    units={},   # v2_columns er tom — der er intet at give en enhed
    migratable=False,
    not_migratable=(
        "INGEN KILDE. Hverken api_energinet_prices.php (enum ['DK1','DK2']) "
        "eller api_entsoe_prices.php (SYSTEM står ikke i available_areas) "
        "leverer området, og EDS `Elspotprices` dækker ikke perioden længere. "
        "Det er en anden grund end spot_entsoe's: dér findes en kilde der "
        "svarer forkert, her findes ingen kilde."
    ),
    notes=(
        "Står med i registret for at være udtømmende, ikke fordi den kan "
        "migreres. Der findes INGEN kilde blandt de navngivne endpoints: "
        "api_energinet_prices.php har enum ['DK1','DK2'], og SYSTEM står ikke "
        "i api_entsoe_prices.php's available_areas. Klonen har 18 432 rækker "
        "(2022 .. 2025-02-06) i variant A, altså fra EDS `Elspotprices` — "
        "som ikke længere leverer den periode.\n"
        "Alle fem v1-kolonner står i DROPPED fordi der ikke er noget at "
        "afbilde dem PÅ — ikke fordi de skal slettes. Filerne skal bevares "
        "uændret, eller det skal besluttes eksplicit at datasættet udgår. "
        "Gate 2 må ikke røre dem."
    ),
)


# ==========================================================================
# Registret
# ==========================================================================

SCHEMAS: Dict[str, DatasetSchema] = {
    s.name: s
    for s in (
        IMBALANCE_PRICE,
        MFRR_ACTIVATION,
        MFRR_CAPACITY,
        AFRR_CAPACITY,
        SPOT_DK,
        SPOT_ENTSOE,
        DMI_OBS,
        SPOT_SYSTEM,
    )
}

# Målekontekst for headerne ovenfor. Ændrer nogen dem, skal denne følge med.
MEASURED = {
    "gate": "F6 Gate 1 + 1b + 1c + 1d",
    "date": "2026-08-08",
    "api_reference_day": "2026-03-15",
    # Gate 1d krydstjekkede tidszonen på en sommerdag, fordi en vinterdag
    # ikke kan skelne Europe/Copenhagen fra fast CET.
    "api_summer_check_day": "2026-07-15",
    "api_format": "csv",
    "api_base": "https://api.sysapp.dk",
    "openapi_version": "1.5.2",   # https://api.sysapp.dk/openapi.json, 84 814 B
    "clone_commit": "6c95bde23ecaaf5d2feabbd74ec4345778e775a1",
}

# Endpoints der leverer resolution_minutes SOM KOLONNE. Målt, ikke antaget (A3).
# Den må ALDRIG syntetiseres for et endpoint der ikke står her.
#
# OBS: api_eds_balance.php oplyser opløsningen i `meta.resolution` ("15 min",
# "1 hour") når format=json — men IKKE som kolonne, og slet ikke i CSV. Det er
# to forskellige ting, og meta-feltet gør ikke endpointet til en leverandør af
# kolonnen.
ENDPOINTS_WITH_RESOLUTION_MINUTES = frozenset({"/api_entsoe_prices.php"})


# ==========================================================================
# Endpoint-kontrakten (F6 Gate 1d, DEL B)
#
# Målt 2026-08-08 mod referencedøgnet 2026-03-15 (vinter) og krydstjekket
# 2026-07-15 (sommer) hvor tidszonen var på spil. Hvert felt bærer sin egen
# status. Læs ALDRIG et felt fra et andet endpoint.
# ==========================================================================

_ALL_MEASURED = {f: "målt" for f in CONTRACT_FIELDS}

ENDPOINT_CONTRACTS: Dict[str, EndpointContract] = {
    "/api_eds_balance.php": EndpointContract(
        endpoint="/api_eds_balance.php",
        filter_timezone="utc",
        end_boundary="inklusiv-hele-døgnet",
        bare_date_semantics=(
            "enddate=D udvides til D+1T00:00:00 EKSKLUSIV, altså hele døgnet D. "
            "Målt: startdate=enddate=2026-03-15 → 96 rækker, time_utc "
            "00:00..23:45. meta.range_utc.to_exclusive = '2026-03-16 00:00:00' "
            "med to_exclusive_source='enddate parameter'. Et EKSPLICIT "
            "tidsstempel er derimod eksklusivt: enddate=2026-03-16T00:00:00 → "
            "96 rækker (kun d. 15), enddate=2026-03-15T12:00:00 → 48 rækker."
        ),
        unknown_param="400",
        limit_default=1000,
        limit_max=10000,
        limit_over_max=(
            "TAVS TILBAGEFALD TIL 1000. limit=10000 → 8 640 rækker (alt i "
            "vinduet), limit=10001 → 1 000 rækker, HTTP 200, status='success', "
            "og meta siger intet om det. Ingen fejl, ingen advarsel. Brug "
            "offset til at side; offset=0/1000/2000 gav sammenhængende blokke."
        ),
        delivers_resolution=False,
        status=_ALL_MEASURED,
        area_param="area",
        area_values=("DK1", "DK2"),
        notes=(
            "Afviser ukendte parametre og siger hvorfor: 'a silently ignored "
            "filter returns a plausible but wrong answer'. Tilladte: dataset, "
            "startdate, enddate, area, auction, format, fields, limit, offset. "
            "`zone` er IKKE blandt dem og giver 400 — modsat "
            "api_energinet_prices.php, hvor samme parameter ignoreres tavst.\n"
            "format=json giver et meta-objekt med resolution, range_utc, "
            "total_records, has_more og next_offset. CSV giver intet af det. "
            "Skal Gate 2 vide om der er flere rækker, skal den bruge json."
        ),
    ),
    "/api_energinet_prices.php": EndpointContract(
        endpoint="/api_energinet_prices.php",
        filter_timezone="dk",
        end_boundary="inklusiv-hele-døgnet",
        bare_date_semantics=(
            "enddate=D dækker hele det DANSKE døgn D. Målt: "
            "startdate=enddate=2026-03-15 → 192 rækker (96 kvarter × 2 "
            "områder), hour_dk 00:00..23:45, hour_utc 2026-03-14 23:00.."
            "2026-03-15 22:45. meta.timezone='dk'."
        ),
        unknown_param="ignoreres tavst",
        limit_default=1000,
        limit_max=None,
        limit_over_max=None,
        delivers_resolution=False,
        status={**_ALL_MEASURED, "limit_max": "uafklaret"},
        area_param="area",
        area_values=("DK1", "DK2"),
        notes=(
            "FARLIGST AF DE FIRE. En ukendt parameter ignoreres uden fejl: "
            "zone=DK1 og zone=DK2 giver begge 192 rækker med BÅDE områder. "
            "Filteret hedder `area`; area=DK1 giver 96 rækker med kun DK1, og "
            "et ugyldigt area giver 400 ('Use DK1 or DK2, or omit area to "
            "include both').\n"
            "Et EKSPLICIT tidsstempel som enddate afvises med 400 ('Invalid "
            "enddate format. Use YYYY-MM-DD'). Her kan man altså IKKE følge "
            "EDS-reglen om altid at sende et tidsstempel — endpointet tager "
            "kun bare datoer.\n"
            "limit_max ikke målt: limit=999999 gav 1 000 rækker som "
            "api_eds_balance.php, men grænsen er ikke bisekteret her, og et "
            "andet endpoints 10 000 må ikke lånes."
        ),
    ),
    "/api_entsoe_prices.php": EndpointContract(
        endpoint="/api_entsoe_prices.php",
        filter_timezone=None,
        end_boundary="inklusiv-hele-døgnet",
        bare_date_semantics=(
            "enddate=D dækker hele døgnet D på endpointets egen akse. Målt: "
            "startdate=enddate=2026-03-15 → 96 rækker, timestamp "
            "00:00..23:45; startdate=D, enddate=D+1 → 192 rækker."
        ),
        unknown_param="ignoreres tavst",
        limit_default=1000,
        limit_max=None,
        limit_over_max=None,
        delivers_resolution=True,
        status={
            **_ALL_MEASURED,
            # Meta HÆVDER "utc". Målingen siger dansk lokaltid. Så længe de to
            # er i modstrid, er feltet uafklaret — ikke "dk".
            "filter_timezone": "uafklaret",
            "limit_max": "uafklaret",
        },
        area_param="area",
        area_values=("DE_LU", "DK_1", "DK_2", "FR", "NO_2", "SE_3", "SE_4",
                     "NL", "BE"),
        notes=(
            "⚠ meta.timezone hævder 'utc'. MÅLT: kolonnen `timestamp` falder "
            "sammen med dansk lokaltid, ikke UTC — se SPOT_ENTSOE.notes for "
            "de tre uafhængige målinger. Fordi kilden og målingen er i "
            "modstrid, står filter_timezone som UAFKLARET, ikke som 'dk': vi "
            "har målt hvad KOLONNEN indeholder, ikke hvilken akse filteret "
            "skærer på. De to behøver ikke være ens (api_energinet_prices.php "
            "filtrerer på dk og leverer både utc og dk).\n"
            "Områdekoderne har understreg: DK_1, ikke DK1. Et kort navn giver "
            "400 med hele enum'en i kroppen, og meta.available_areas oplyser "
            "den maskinlæsbart. SE_3 og NO_2 svarer 200 med 0 bytes.\n"
            "Eneste endpoint med resolution_minutes som kolonne (målt 15 på "
            "alle prøvede dage; specen har example 60)."
        ),
    ),
    "/api_dmi_obs_ny.php": EndpointContract(
        endpoint="/api_dmi_obs_ny.php",
        filter_timezone="dk",
        end_boundary="inklusiv-hele-døgnet",
        bare_date_semantics=(
            "enddate=D dækker hele det DANSKE døgn D. Målt: "
            "startdate=enddate=2026-03-15 → 24 rækker, hour_dk 00:00..23:00, "
            "hour_utc 2026-03-14 23:00..2026-03-15 22:00. meta.timezone='dk'."
        ),
        unknown_param="ignoreres tavst",
        limit_default=1000,
        limit_max=None,
        limit_over_max=None,
        delivers_resolution=False,
        status={**_ALL_MEASURED, "limit_max": "uafklaret"},
        area_param="area",
        area_values=(),
        notes=(
            "Eksplicit tidsstempel som enddate afvises med 400, som "
            "api_energinet_prices.php. Kun bare datoer.\n"
            "area_values er TOM fordi enum'en ikke er målt: et ugyldigt area "
            "gav 200 med tom krop, ikke en 400 med en liste. Klonen har fyn, "
            "vestkyst og karup, men det er filnavne, ikke en målt enum."
        ),
    ),
    # ---- EDS. Et ANDET API, med modsat datosemantik. ----------------------
    "https://api.energidataservice.dk/dataset/DayAheadPrices": EndpointContract(
        endpoint="https://api.energidataservice.dk/dataset/DayAheadPrices",
        filter_timezone="dk",
        end_boundary="eksklusiv",
        bare_date_semantics=(
            "En bar dato betyder T00:00 DANSK TID og udvides IKKE til hele "
            "døgnet. start=end=D giver 0 rækker. Målt F6 Gate 1c. Dette er "
            "det MODSATTE af api_eds_balance.php, som deler datasætnavne med "
            "denne tabel."
        ),
        unknown_param=None,
        limit_default=None,
        limit_max=None,
        limit_over_max=None,
        delivers_resolution=False,
        status={
            "filter_timezone": "målt",
            "end_boundary": "målt",
            "bare_date_semantics": "målt",
            "unknown_param": "uafklaret",
            "limit_max": "uafklaret",
            "delivers_resolution": "målt",
        },
        notes=(
            "For ét dansk døgn: start=D&end=D+1. Send altid et eksplicit "
            "tidsstempel som end — det er eksklusivt her, og bare datoer "
            "betyder noget andet på sysapp-proxyen.\n"
            "RATE LIMIT: se UNRESOLVED. Hverken kvote eller vindue er kendt."
        ),
    ),
    "https://api.energidataservice.dk/dataset/Elspotprices": EndpointContract(
        endpoint="https://api.energidataservice.dk/dataset/Elspotprices",
        filter_timezone="dk",
        # None, IKKE "eksklusiv": kun døgnniveauet er målt, og et halvåbent
        # interval er en påstand om ALLE tidsstempler, ikke kun midnat.
        end_boundary=None,
        bare_date_semantics=(
            "Bar dato = T00:00 dansk tid, ikke udvidet; start=end=D → 0 "
            "rækker. Målt F6 Gate 1c PÅ DØGNNIVEAU. Sub-daglig eksklusivitet "
            "er IKKE målt — se UNRESOLVED. Den må ikke arve DayAheadPrices' "
            "resultat."
        ),
        unknown_param=None,
        limit_default=None,
        limit_max=None,
        limit_over_max=None,
        delivers_resolution=False,
        status={
            "filter_timezone": "målt",
            "end_boundary": "uafklaret",
            "bare_date_semantics": "målt",
            "unknown_param": "uafklaret",
            "limit_max": "uafklaret",
            "delivers_resolution": "målt",
        },
        notes=(
            "Leverer ikke DE/NO2/SE3/SE4 efter 2025-09-30 — det er hullet i "
            "klonens spot/-filer. Timeopløst, hvor DayAheadPrices er 15-min. "
            "At de to tabeller ligger på samme vært betyder ikke at de "
            "opfører sig ens; end_boundary er derfor uafklaret her selv om "
            "den er målt på nabotabellen."
        ),
    ),
}

# ==========================================================================
# Datasæt uden migrationsvej. To, af to forskellige grunde.
# ==========================================================================

MIGRATIONSSPAERRER = tuple(
    n for n, s in SCHEMAS.items() if not s.migratable
)


# ==========================================================================
# KLONEN HENTER IKKE SIG SELV. Det er en egenskab, ikke en mangel. (Gate 1e B3)
# ==========================================================================

NO_AUTO_PULL = """\
`src/data_loader_github.py:_ensure_df_data_cache` laver `git clone --depth 1`
ÉN gang og returnerer derefter mappen uden noget netværkskald. Der findes
ingen `git pull` og ingen `git fetch` nogen steder i businesscase-repoet.

DET ER MED VILJE, OG DET SKAL BLIVE SÅDAN.

Hvorfor det ikke er en mangel:

1. Klonen er MÅLEINSTRUMENT, ikke kun cache. Alle headere i dette modul, alle
   rækketal i tests/test_coverage_guard.py og hele fastfrysningen i
   tests/test_schema_v2_mapping.py er målt mod ÉT commit: 6c95bde. Et pull
   ville flytte grundlaget under 201 tests uden at nogen bad om det.
2. Datarepoet opdateres uafhængigt af modelrepoet, og manifestet registrerer
   ikke dataversionen (målt i Gate 0.5 §C4). En test der pludselig fejler
   ville altså ikke kunne sige om koden eller dataene ændrede sig.
3. Reproducerbarhed i miljøer uden udgående net. Det var grunden til at
   github-vejen blev bygget.

Hvad der går galt hvis nogen "retter" det:

  * `force_refresh=True` som default → `shutil.rmtree` på klonen ved hver
    kørsel. Utrackede lokale ændringer i mappen forsvinder uden varsel.
  * et `git pull` i `_ensure_df_data_cache` → dækningstestene måler mod et
    andet commit end deres indfrosne tal, og fejlbeskederne peger på koden.

Vil man have nyere data, er vejen en EKSPLICIT handling: `--df-data-cache`
til en anden sti, eller `force_refresh=True` i det enkelte kald. Ikke en
default.
"""


# ==========================================================================
# Beslutninger truffet (Gate 1e). Ikke forslag længere — men heller ikke
# bygget: alt nedenfor er Gate 2's arbejde.
# ==========================================================================

DECISIONS = (
    "PROVENIENS: KILDEKOLONNE PR. RÆKKE er valgt, med HEADER-FINGERAFTRYK "
    "som sekundær vagt. Hver v2-række bærer hvilken kildetabel den kom fra; "
    "loaderen kræver desuden at filens header matcher en indfrosset variant. "
    "De to fanger hver sin fejl og erstatter ikke hinanden: headeren fanger "
    "et skift OVER stregen, kildekolonnen et skift UNDER den — og det er den "
    "sidste vi beviseligt har haft (spot/DK1_2026.csv, to skemaer under én "
    "header). "
    "FORUDSÆTNING: kildekolonnen kan kun bæres hvis API'et leverer den. Det "
    "er krav 3.4 i API-udvidelsen. Leverer API'et den ikke, er beslutningen "
    "ikke gennemførlig, og header-fingeraftrykket står alene — det er "
    "svagere, og det skal siges højt frem for at blive opdaget. "
    "IKKE BYGGET HER. Gate 2. Historiske rækker backfilles ikke, af samme "
    "grund som `auction` ikke gør: vi har ikke målt hvor de kom fra.",

    "VERSIONSVAGT: update_data.py læser DATA_VERSION.md FØR ethvert "
    "netværkskald og afbryder ved uenighed mellem filens `schema_version` og "
    "scriptets egen SCHEMA_VERSION. Fejlbeskeden skal nævne BEGGE versioner "
    "og hvilken vej uenigheden går — 'scriptet er nyere end repoet' og "
    "'repoet er nyere end scriptet' kræver forskellig handling af mennesket. "
    "MANGLENDE ELLER TOMT FELT (som er tilstanden i dag — feltet findes "
    "slet ikke): AFBRYD, med en engangsudvej `--adopt-schema=v1`, der "
    "skriver feltet og ikke gør andet. Mennesket erklærer versionen; "
    "værktøjet gætter den ikke. At antage v1 automatisk ville være samme "
    "fejl som at backfille auction — og ville skrive 'v1' oven på "
    "DK1_2026.csv, som beviseligt ikke er rent v1. "
    "LÆS FØR HENTNING, ikke efter: afbryder vagten bagefter, er der brugt "
    "kvote hos EDS på et svar der kastes væk, og EDS' rate limit er ukendt. "
    "IKKE BYGGET HER — og kan ikke bygges herfra: update_data.py ligger i "
    "df-data.",
)


# Uafklaret og bevidst IKKE besluttet her. Gate 2 må ikke gætte disse.
OPEN_QUESTIONS = (
    "Områdekode-VÆRDIER: klonen bruger DE/NO2/SE3/SE4, "
    "api_entsoe_prices.php kræver DE_LU/NO_2/SE_3/SE_4. En værdimapping er "
    "ikke truffet. Filnavne og kolonneværdier beholder klonens koder. "
    "Gate 1d målte MÅLSIDEN udtømmende — den fulde enum står i "
    "ENDPOINT_CONTRACTS['/api_entsoe_prices.php'].area_values og oplyses "
    "maskinlæsbart i meta.available_areas — men KILDESIDEN er stadig et "
    "valg: hvad DE afbildes til, og hvad der sker med SYSTEM, er ikke "
    "besluttet.",
    "auction ved sammenligning på tværs af kilder: kolonnen backfilles ikke, "
    "så en v1-række kan ikke danne en fuld KEY. Hvad en manglende auction "
    "betyder ved join/dedup er ikke besluttet.",
    "Hvornår API-udvidelsen til DayAheadPrices er på plads, og om den "
    "leverer kildekolonnen (krav 3.4). Indtil da har spot_entsoe ingen "
    "migrationsvej — se DECISIONS og SPOT_ENTSOE.not_migratable.",
)

# Hvad der IKKE er fundet, så ingen tror det er afklaret.
UNRESOLVED = (
    "TIDSAKSEN I api_entsoe_prices.php — MÅLT, OG AFGJORT I GATE 1e. Står "
    "her fordi selve uoverensstemmelsen stadig er uforklaret: endpointet "
    "leverer dansk lokaltid i en kolonne dets meta kalder 'utc'. Gate 1d "
    "målte det tre gange, mod to andre kilder, på både en vinter- og en "
    "sommerdag — 96/96 med maks |Δ| = 0 mod hour_dk, mod 1/96 og 0/88 på "
    "UTC-aksen. Forskydningen er +1 t i marts og +2 t i juli, altså "
    "Europe/Copenhagen, ikke fast CET. "
    "FØLGEN er truffet: vejen forkastes (SPOT_ENTSOE.api_path_rejected). "
    "ÅRSAGEN er ikke fundet, og den bør meldes til den der vedligeholder "
    "endpointet — ellers rammer den nogen igen.",

    "Hvem skrev proxy-rækkerne (variant C) i spot/DK1_2026.csv og "
    "DK2_2026.csv. Gate 1d indsnævrede det: rækkerne lå allerede i df-data's "
    "ALLERFØRSTE commit (6cc7a69, 2026-05-10) — 8 632 rækker, alle med id, "
    "2026-01-01..2026-03-31 21:45. INGEN af de fem versioner af "
    "scripts/update_data.py i repoets historik kalder api_energinet_prices.php "
    "for spot; alle bruger fetch_eds (Elspotprices, senere DayAheadPrices). "
    "Proxyen bruges kun til DMI. Skriveren ligger altså FØR git — filerne blev "
    "lagt ind ved den første import. Hypotesen om 'en ældre update_data.py på "
    "workstationen' er dermed afkræftet for alt git kan vise.",

    "Elspotprices' SUB-DAGLIGE eksklusivitet. Gate 1c nåede ikke at måle den: "
    "kaldet ramte HTTP 429 efter 6 forsøg, og et 429 er en udeblevet måling, "
    "ikke et tomt svar. Døgnniveauet ER målt. Den må IKKE arve "
    "DayAheadPrices' resultat — se ENDPOINT_CONTRACTS.",

    "EDS' RATE LIMIT. Hverken kvote eller vindue er kendt. Målt er kun at "
    "8 sekunder mellem kald ikke altid er nok: Gate 1b ramte 429 to gange med "
    "4 s, Gate 1c to gange med 8 s (den ene lykkedes efter 60 s pause). "
    "Gate 2 skal have backoff FØR en genhentning, ikke opdage det midtvejs. "
    "Et 429 skal rapporteres som udeblevet, aldrig som nul rækker.",

    "DEN MANUELLE SKRIVEVEJ MOD df-data. Der findes ingen automatik. "
    "update_data.py køres i hånden, og de to seneste commits (decd48f "
    "2026-08-04, 6c95bde 2026-08-07) blev ifølge klonens reflog begået OG "
    "pushet fra denne server — samme mappe som loaderens cache, "
    "data/df-data. Kørslen logges ikke ud over DATA_VERSION.md's dato, og "
    "intet registrerer hvilken version af update_data.py der skrev hvad. "
    "Vejen kan ikke migreres herfra: update_data.py ligger i df-data, som "
    "denne gate ikke må skrive i.",

    "SKEMABLANDING ER TAVS. Kører en ÆLDRE update_data.py mod et v2-repo — "
    "eller den migrerede mod et v1-repo — appenderes den nye kørsels rækker "
    "til de eksisterende årsfiler med kildens egne kolonnenavne. Resultatet "
    "er én fil med to skemaer. Det er allerede sket én gang: "
    "spot/DK1_2026.csv bærer 8 632 proxy-rækker med id/created_at/updated_at "
    "og 8 448 EDS-rækker uden, i samme fil under samme header — id'erne "
    "blev til flydende tal (2001010.0), hvilket er pd.concat's aftryk når en "
    "kolonne mangler i den ene ramme. DATA_VERSION.md HAR IKKE et "
    "schema_version-felt i dag (målt: ingen forekomst i filen), så intet "
    "skifter når skemaet gør. Fejlen er tavs og rammer en tredjepart, der "
    "kloner repoet og læser filen som ét skema.",
)
