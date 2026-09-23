"""
F6 Gate 1/1b — vagt om kolonne-mappingen v1 → v2.

Testen holder src/schema_v2.py ærlig gennem Gate 2 og Gate 3. Den gør fire ting:

1. FASTFRYSER klonens faktiske v1-headere. Ændrer df-data sig, fejler testen —
   den læser headerne fra disk og sammenligner med de indfrosne.
2. ASSERTERER de tre regnskaber: hver v1-, API- og v2-kolonne ligger i præcis
   én spand, og ingen står udenfor.
3. FANGER en kolonne der tilføjes eller fjernes uden at mappingen opdateres.
4. HÅNDHÆVER Gate 1/1b's beslutninger, så de ikke kan opløses stiltiende.

Testen rører ingen data og laver ingen netværkskald. API-headerne er indfrosne
fra gatens målinger (2026-03-15, format=csv) og kan kun genmåles ved en ny
gate — en test må ikke afhænge af at nettet er oppe.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.schema_v2 import (
    CONTRACT_FIELDS,
    DECISIONS,
    ENDPOINT_CONTRACTS,
    ENDPOINTS_WITH_RESOLUTION_MINUTES,
    MIGRATIONSSPAERRER,
    NO_AUTO_PULL,
    SCHEMAS,
    UNRESOLVED,
)

CLONE = Path(__file__).resolve().parents[1] / "data" / "df-data"

# Hvilke klonmapper/-mønstre hvert datasæt dækker. Holdt her og ikke i
# schema_v2.py, fordi det er en testdetalje: schema_v2 skal beskrive skemaet,
# ikke filsystemet.
CLONE_FILES = {
    "imbalance_price": ("imbalance", "*.csv"),
    "mfrr_activation": ("mfrr_act", "*.csv"),
    "mfrr_capacity":   ("mfrr_cap", "*.csv"),
    "afrr_capacity":   ("afrr", "*.csv"),
    "spot_dk":         ("spot", "DK[12]_*.csv"),
    "spot_entsoe":     ("spot", "[DNS][EOE]*_*.csv"),
    "dmi_obs":         ("dmi", "*.csv"),
    "spot_system":     ("spot", "SYSTEM_*.csv"),
}

ALL_NAMES = sorted(SCHEMAS)

pytestmark = pytest.mark.skipif(
    not CLONE.is_dir(),
    reason="df-data-klonen ikke til stede; mapping-vagten kræver den",
)


def _clone_files(name: str) -> list[Path]:
    sub, pattern = CLONE_FILES[name]
    files = sorted((CLONE / sub).glob(pattern))
    if name == "spot_entsoe":
        # Glob'en over må ikke fange SYSTEM_*.
        files = [f for f in files if not f.name.startswith("SYSTEM")]
    return files


def _header(path: Path) -> tuple[str, ...]:
    with path.open(newline="", encoding="utf-8") as fh:
        return tuple(next(csv.reader(fh)))


# --------------------------------------------------------------------------
# 1. Fastfrysning af klonens v1-headere
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ALL_NAMES)
def test_klon_headere_er_uaendrede(name: str) -> None:
    """Hver fil i klonen skal matche en af de indfrosne v1-varianter ORDRET.

    Rækkefølgen tælles med. spot/DE_2026.csv har EUR før DKK hvor
    spot/DE_2025.csv har DKK før EUR — samme navne, byttet plads, fordi
    kilden selv skiftede fra Elspotprices til DayAheadPrices. Fryses kun
    mængden, går den forskel upåagtet hen, og en positionsbaseret loader i
    Gate 2 bytter to valutaer uden at fejle.
    """
    schema = SCHEMAS[name]
    files = _clone_files(name)
    assert files, f"ingen klonfiler fundet for {name}"

    frozen = set(schema.v1_columns)
    for path in files:
        header = _header(path)
        assert header in frozen, (
            f"{path.relative_to(CLONE)} har en header der ikke er indfrosset "
            f"i schema_v2.{name}.v1_columns.\n"
            f"  på disk:   {header}\n"
            f"  indfrosne: {sorted(frozen)}\n"
            f"Er kolonnen tilføjet eller fjernet med vilje, så opdatér "
            f"v1_columns OG v1_to_v2/DROPPED i src/schema_v2.py."
        )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_alle_indfrosne_varianter_findes_paa_disk(name: str) -> None:
    """Ingen døde varianter.

    Uden denne kan en variant blive stående i schema_v2.py længe efter at
    filen der havde den er væk — og så beskytter fastfrysningen ikke længere
    det den påstår.
    """
    on_disk = {_header(p) for p in _clone_files(name)}
    for variant in SCHEMAS[name].v1_columns:
        assert variant in on_disk, (
            f"schema_v2.{name}.v1_columns har en variant ingen fil på disk "
            f"bruger længere: {variant}"
        )


# --------------------------------------------------------------------------
# 2. De tre regnskaber
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ALL_NAMES)
def test_ligning1_v1_er_udtoemmende(name: str) -> None:
    """v1-kolonner == v1_to_v2.keys ⊎ DROPPED, disjunkt.

    Kontrolleres mod UNIONEN af varianter, og hver enkelt variant skal være en
    delmængde. Sådan holder ligningen også for spot_dk, hvor variant A mangler
    id/created_at/updated_at.
    """
    schema = SCHEMAS[name]
    mapped, dropped = set(schema.v1_to_v2), set(schema.dropped)

    overlap = mapped & dropped
    assert not overlap, (
        f"{name}: v1-kolonner står både i v1_to_v2 og DROPPED: {sorted(overlap)}"
    )

    union = set().union(*(set(v) for v in schema.v1_columns))
    assert mapped | dropped == union, (
        f"{name}: v1-regnskabet går ikke op.\n"
        f"  i klonen, ikke gjort rede for: {sorted(union - (mapped | dropped))}\n"
        f"  i spandene, men ikke i klonen: {sorted((mapped | dropped) - union)}"
    )

    for variant in schema.v1_columns:
        assert set(variant) <= union


@pytest.mark.parametrize("name", ALL_NAMES)
def test_ligning2_api_er_udtoemmende(name: str) -> None:
    """API-kolonner == api_to_v2.keys ⊎ API_DROPPED, disjunkt.

    API_DROPPED er ikke en dublet af DROPPED. Uden den har
    created_at/updated_at/time_dk/hour_dk/id intet sted at stå: API'et
    LEVERER dem, og beslutningen er at droppe dem. Lagt i ADDED ville Gate 2
    læse dem som "tilføj disse".
    """
    schema = SCHEMAS[name]
    mapped, dropped = set(schema.api_to_v2), set(schema.api_dropped)

    overlap = mapped & dropped
    assert not overlap, (
        f"{name}: API-kolonner står både i api_to_v2 og API_DROPPED: "
        f"{sorted(overlap)}"
    )
    api = set(schema.api_columns)
    assert mapped | dropped == api, (
        f"{name}: API-regnskabet går ikke op.\n"
        f"  API leverer, ingen spand tager den: {sorted(api - (mapped | dropped))}\n"
        f"  i en spand, men API'et leverer den ikke: {sorted((mapped | dropped) - api)}"
    )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_ligning3_v2_er_udtoemmende(name: str) -> None:
    """v2_columns == v1_to_v2.values ⊎ ADDED ⊎ DERIVED, disjunkt.

    Det er denne ligning der gør v2_columns til sandheden: enhver v2-kolonne
    skal enten komme fra klonen, kun fra API'et, eller genereres — og præcis
    én af delene.
    """
    schema = SCHEMAS[name]
    from_v1 = set(schema.v1_to_v2.values())
    added = set(schema.added)
    derived = set(schema.derived)

    for a, b, label in ((from_v1, added, "v1_to_v2-mål/ADDED"),
                        (from_v1, derived, "v1_to_v2-mål/DERIVED"),
                        (added, derived, "ADDED/DERIVED")):
        assert not a & b, f"{name}: overlap mellem {label}: {sorted(a & b)}"

    v2 = set(schema.v2_columns)
    assert from_v1 | added | derived == v2, (
        f"{name}: v2-regnskabet går ikke op.\n"
        f"  i v2_columns, ingen spand producerer den: "
        f"{sorted(v2 - (from_v1 | added | derived))}\n"
        f"  produceret, men ikke i v2_columns: "
        f"{sorted((from_v1 | added | derived) - v2)}"
    )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_ligning3_spejlet_api_vejen_er_udtoemmende(name: str) -> None:
    """v2_columns == api_to_v2.values ⊎ V1_ONLY ⊎ DERIVED, disjunkt.

    Spejlingen af ligning 3, set fra API-vejen. Uden den kan de to retninger
    drive fra hinanden: v1-vejen ville skrive ét skema og API-vejen et andet,
    og først en diff langt nede i Gate 3 ville vise det.

    V1_ONLY er ADDED's spejlbillede og skal være erklæret eksplicit — en
    v2-kolonne API'et ikke kan levere er en asymmetri nogen skal have taget
    stilling til, ikke noget en loader opdager ved at fejle.
    """
    schema = SCHEMAS[name]
    produced = set(schema.api_to_v2.values())
    v1_only = set(schema.v1_only)
    derived = set(schema.derived)

    for a, b, label in ((produced, v1_only, "api_to_v2-mål/V1_ONLY"),
                        (produced, derived, "api_to_v2-mål/DERIVED"),
                        (v1_only, derived, "V1_ONLY/DERIVED")):
        assert not a & b, f"{name}: overlap mellem {label}: {sorted(a & b)}"

    v2 = set(schema.v2_columns)
    assert produced | v1_only | derived == v2, (
        f"{name}: v2-regnskabet set fra API-vejen går ikke op.\n"
        f"  API-vejen hverken leverer, genererer eller erklærer som V1_ONLY: "
        f"{sorted(v2 - (produced | v1_only | derived))}\n"
        f"  produceret/erklæret, men ikke i v2_columns: "
        f"{sorted((produced | v1_only | derived) - v2)}"
    )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_added_og_v1_only_er_aegte_asymmetrier(name: str) -> None:
    """ADDED må kun rumme det v1 mangler, V1_ONLY kun det API'et mangler.

    Ryger en kolonne i den forkerte spand, ser regnskabet stadig rigtigt ud
    mens beskrivelsen af hvad kilderne kan er blevet løgn.
    """
    schema = SCHEMAS[name]
    for col in schema.added:
        assert col not in schema.v1_to_v2.values(), (
            f"{name}: {col!r} står i ADDED, men v1-vejen leverer den"
        )
        assert col in schema.api_to_v2.values(), (
            f"{name}: {col!r} står i ADDED, men API-vejen leverer den ikke"
        )
    for col in schema.v1_only:
        assert col not in schema.api_to_v2.values(), (
            f"{name}: {col!r} står i V1_ONLY, men API-vejen leverer den"
        )
        assert col in schema.v1_to_v2.values(), (
            f"{name}: {col!r} står i V1_ONLY, men v1-vejen leverer den ikke"
        )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_ingen_dublerede_navne(name: str) -> None:
    schema = SCHEMAS[name]
    for mapping, label in ((schema.v1_to_v2, "v1_to_v2"),
                           (schema.api_to_v2, "api_to_v2")):
        targets = list(mapping.values())
        assert len(set(targets)) == len(targets), (
            f"{name}: to kilder peger på samme v2-navn i {label}"
        )
    for seq, label in ((schema.api_columns, "api_columns"),
                       (schema.v2_columns, "v2_columns")):
        assert len(set(seq)) == len(seq), f"{name}: {label} har samme navn to gange"
    for variant in schema.v1_columns:
        assert len(set(variant)) == len(variant), (
            f"{name}: v1-variant har samme navn to gange: {variant}"
        )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_hver_beslutning_har_en_begrundelse(name: str) -> None:
    schema = SCHEMAS[name]
    for bucket, label in ((schema.dropped, "DROPPED"),
                          (schema.api_dropped, "API_DROPPED"),
                          (schema.added, "ADDED")):
        for col, reason in bucket.items():
            assert reason and reason.strip(), (
                f"{name}: {label}[{col!r}] mangler begrundelse"
            )
    for col, d in schema.derived.items():
        assert d.reason.strip(), f"{name}: DERIVED[{col!r}] mangler begrundelse"
        assert d.expression.strip(), f"{name}: DERIVED[{col!r}] mangler udtryk"


# --------------------------------------------------------------------------
# 3. DERIVED
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ALL_NAMES)
def test_derived_kan_beregnes_fra_begge_kilder(name: str) -> None:
    """En DERIVED-kolonnes kilder skal kunne nås fra BÅDE v1 og API.

    Kan den kun beregnes fra den ene vej, producerer de to loadere forskellige
    skemaer — og den ene fejler først når nogen bruger kolonnen.
    """
    schema = SCHEMAS[name]
    from_v1 = set(schema.v1_to_v2.values())
    from_api = set(schema.api_to_v2.values())
    for col, d in schema.derived.items():
        assert d.source, f"{name}: DERIVED[{col!r}] har ingen kilde"
        for src in d.source:
            assert src in schema.v2_columns, (
                f"{name}: DERIVED[{col!r}] læser {src!r}, som ikke er i v2_columns"
            )
            assert src in from_v1, (
                f"{name}: DERIVED[{col!r}] læser {src!r}, som v1-vejen ikke leverer"
            )
            assert src in from_api, (
                f"{name}: DERIVED[{col!r}] læser {src!r}, som API-vejen ikke leverer"
            )


def test_dmi_hour_utc_genereres_og_begge_kilders_egen_droppes() -> None:
    """A4: kildens hour_utc er målt forkert i én time om året, i BEGGE kilder.

    Både klonens og API'ets hour_utc skal droppes, og v2's genereres fra
    unixtime. Står én af dem tilbage i en mapping, vinder den forkerte værdi.
    """
    schema = SCHEMAS["dmi_obs"]
    assert "hour_utc" in schema.dropped, "klonens hour_utc skal i DROPPED"
    assert "hour_utc" in schema.api_dropped, "API'ets hour_utc skal i API_DROPPED"
    assert "hour_utc" not in schema.v1_to_v2.values()
    assert "hour_utc" not in schema.api_to_v2.values()

    d = schema.derived["hour_utc"]
    assert d.source == ("unixtime",)
    assert "unixtime" in d.expression
    assert "hour_utc" in schema.v2_columns


def test_dmi_key_er_unixtime_ikke_den_genererede_hour_utc() -> None:
    """A4: KEY forbliver (unixtime, area).

    Nøglen skal pege på kolonnen der bærer entydigheden i sig selv, ikke på en
    afledning af den. Ændrer nogen udtrykket i DERIVED, må nøglen ikke følge
    med i faldet.
    """
    schema = SCHEMAS["dmi_obs"]
    assert schema.key == ("unixtime", "area")
    assert "unixtime" in schema.v1_to_v2
    assert "unixtime" not in schema.dropped
    assert "hour_utc" not in schema.key


def test_kun_dmi_har_derived() -> None:
    """DERIVED er en undtagelse, ikke en generel mekanisme.

    Kommer der flere, skal det være en bevidst handling — testen tvinger den
    der tilføjer én til også at røre denne linje.
    """
    with_derived = {n for n, s in SCHEMAS.items() if s.derived}
    assert with_derived == {"dmi_obs"}, (
        f"DERIVED er tilføjet til {sorted(with_derived - {'dmi_obs'})} — "
        f"bekræft at det er bevidst og opdatér denne test"
    )


# --------------------------------------------------------------------------
# 4. Nøgler og beslutninger fra Gate 1/1b
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ALL_NAMES)
def test_key_bestaar_af_v2_kolonner(name: str) -> None:
    """En nøgle må kun bruge kolonner der faktisk står i v2-headeren."""
    schema = SCHEMAS[name]
    assert schema.key, f"{name}: KEY er tom"
    if schema.endpoint is None:
        return  # spot_system har intet migrationsmål; nøglen er dokumentation
    assert set(schema.key) <= set(schema.v2_columns), (
        f"{name}: KEY bruger kolonner der ikke er i v2_columns: "
        f"{sorted(set(schema.key) - set(schema.v2_columns))}"
    )


def test_auction_er_med_og_i_noeglen() -> None:
    """B3: auction skal med på mfrr_capacity, og den skal være i KEY.

    Uden den kan et extra-udbud fordoble rækker pr. tidsstempel usynligt.
    Gate 1 målte 'extra' = 0 rækker over hele tabellens levetid, men nøglen
    skal beskytte mod den fremtid hvor det ikke gælder.
    """
    schema = SCHEMAS["mfrr_capacity"]
    assert "auction" in schema.api_columns
    assert "auction" in schema.added
    assert "auction" in schema.v2_columns
    assert "auction" in schema.key
    # v1 kan ikke levere den — derfor står den i ADDED og ikke i v1_to_v2.
    assert "auction" not in schema.v1_to_v2.values()
    # afrr_capacity har den ikke — API'et afviser parameteren der.
    assert "auction" not in SCHEMAS["afrr_capacity"].api_columns
    assert "auction" not in SCHEMAS["afrr_capacity"].key


@pytest.mark.parametrize("name", ALL_NAMES)
def test_lokal_tid_og_revisionsstempler_er_droppet(name: str) -> None:
    """B3: hour_dk/time_dk, created_at, updated_at og id udgår overalt.

    Kontrolleres på alle tre sider: hverken v1-vejen, API-vejen eller
    v2-headeren må bære dem videre.
    """
    schema = SCHEMAS[name]
    forbidden = {"time_dk", "hour_dk", "created_at", "updated_at", "id",
                 "TimeDK"}
    for produced, label in ((set(schema.v1_to_v2.values()), "v1_to_v2-mål"),
                            (set(schema.api_to_v2.values()), "api_to_v2-mål"),
                            (set(schema.v2_columns), "v2_columns")):
        survivors = produced & forbidden
        assert not survivors, (
            f"{name}: skulle være droppet, men bevares i {label}: {sorted(survivors)}"
        )
    sources = set(schema.v1_to_v2) & forbidden
    assert not sources, f"{name}: v1-kolonne skulle være droppet: {sorted(sources)}"


@pytest.mark.parametrize("name", ALL_NAMES)
def test_resolution_minutes_syntetiseres_ikke(name: str) -> None:
    """A3 (Gate 1): kun api_entsoe_prices.php leverer resolution_minutes.

    Den må ikke optræde i noget datasæt hvis endpoint ikke leverer den — en
    syntetiseret opløsningskolonne er en påstand vi ikke har målt.
    """
    schema = SCHEMAS[name]
    in_v2 = "resolution_minutes" in schema.v2_columns
    if schema.endpoint in ENDPOINTS_WITH_RESOLUTION_MINUTES:
        # Gate 1e: endpointet LEVERER den stadig — men vejen er forkastet, og
        # så er der ingen kilde tilbage. En kolonne uden kilde må ikke stå i
        # v2_columns; det er præcis den syntetisering testen findes for.
        assert not schema.migratable, (
            f"{name}: endpointet leverer resolution_minutes og vejen er ikke "
            "forkastet — så skal kolonnen med i v2_columns"
        )
        assert not in_v2, (
            f"{name}: vejen er forkastet, men resolution_minutes står stadig "
            "i v2_columns. Ingen kilde kan levere den."
        )
        assert "resolution_minutes" in schema.api_columns
    else:
        assert not in_v2, (
            f"{name}: resolution_minutes er i v2_columns, men {schema.endpoint} "
            f"leverer den ikke. Den må ikke syntetiseres."
        )
        assert "resolution_minutes" not in schema.api_columns


def test_ingen_v2_kolonne_uden_maalt_kilde() -> None:
    """Den mekaniske version af "ingen beregnede kolonner".

    Hvert v2-navn skal have én af tre målte herkomster: det MÅLTE api_columns,
    en indfrossen v1-header (via V1_ONLY), eller en DERIVED-erklæring med et
    udtryk. Kan et navn ingen af delene, er det opstået ud af ingenting.
    """
    for name, schema in SCHEMAS.items():
        if schema.endpoint is None:
            continue
        unexplained = (set(schema.v2_columns)
                       - set(schema.api_to_v2.values())
                       - set(schema.v1_only)
                       - set(schema.derived))
        assert not unexplained, (
            f"{name}: v2-navne uden målt kilde og uden DERIVED-erklæring: "
            f"{sorted(unexplained)}"
        )
        # V1_ONLY er kun en gyldig herkomst hvis klonen faktisk HAR kolonnen.
        # Ellers ville spanden være et smuthul til at opfinde navne.
        v1_union = set().union(*(set(v) for v in schema.v1_columns))
        for col, reason in schema.v1_only.items():
            src = [k for k, v in schema.v1_to_v2.items() if v == col]
            assert src and src[0] in v1_union, (
                f"{name}: {col!r} er erklæret V1_ONLY, men ingen indfrossen "
                f"v1-header indeholder kilden til den"
            )
            assert reason.strip(), f"{name}: V1_ONLY[{col!r}] mangler begrundelse"


def test_kun_spot_entsoe_har_en_ikke_triviel_api_mapping() -> None:
    """A2: for de øvrige datasæt ER API'et v2-navngivningen.

    Bliver et andet endpoint pludselig ikke-identisk, er det et skifte i
    kildens kontrakt, ikke en detalje — så skal nogen se på det.

    Gate 1e: spot_entsoe var den eneste undtagelse, og den er nu forkastet
    som vej — dens api_to_v2 er tom. Undtagelsen lever videre i
    api_to_v2_rejected, hvor den kan læses uden at kunne bruges.
    """
    non_identity = {n for n, s in SCHEMAS.items()
                    if any(k != v for k, v in s.api_to_v2.items())}
    assert non_identity == set(), (
        f"et endpoint er holdt op med at være v2-navngivningen: "
        f"{sorted(non_identity)}. Det er et skifte i kildens kontrakt."
    )
    identity_non_empty = {n for n, s in SCHEMAS.items() if s.api_to_v2}
    assert len(identity_non_empty) == 6, (
        f"forventede 6 datasæt med ren identitets-mapping, fik "
        f"{len(identity_non_empty)}: {sorted(identity_non_empty)}"
    )
    # Den forkastede mapping ER ikke-identitet, og skal blive ved med at være
    # det — ellers er det ikke længere den måling Gate 1b/1c foretog.
    rejected = SCHEMAS["spot_entsoe"].api_to_v2_rejected
    assert any(k != v for k, v in rejected.items())


def test_spot_mappen_har_eet_navn_pr_akse_og_pr_maal() -> None:
    """A3 + C1: samme mappe må ikke rumme to navne for samme akse ELLER mål.

    A3 normaliserede akserne (timestamp→hour_utc, area→price_area).
    C1 normaliserede målet (price_eur_mwh→spot_price_eur). Efter begge skal
    de to spot-datasæt være navnemæssigt uskelnelige på det de deler.
    """
    entsoe, dk = SCHEMAS["spot_entsoe"], SCHEMAS["spot_dk"]
    # Gate 1e: normaliseringerne blev MÅLT og står ved magt — de er bare
    # flyttet til den forkastede mapping sammen med resten af vejen.
    rejected = entsoe.api_to_v2_rejected
    assert rejected["timestamp"] == "hour_utc"
    assert rejected["area"] == "price_area"
    assert rejected["price_eur_mwh"] == "spot_price_eur"
    # Ingen af API'ets egne navne må slippe igennem til v2.
    for leaked in ("timestamp", "area", "price_eur_mwh"):
        assert leaked not in entsoe.v2_columns, (
            f"{leaked!r} slap igennem til spot_entsoe.v2_columns"
        )
    # Alt hvad de to datasæt deler, hedder det samme.
    shared = set(entsoe.v2_columns) & set(dk.v2_columns)
    assert shared == {"hour_utc", "price_area", "spot_price_eur",
                      "spot_price_dkk"}, sorted(shared)
    assert entsoe.key == dk.key


def test_spot_entsoe_baerer_dkk_med() -> None:
    """Gate 1c: DKK bæres med. Den er kildedata, ikke et regnestykke.

    Gate 1b målte at klonens spot_price_dkk er EDS' egen kolonne, overtaget
    uændret (88/88 celler, max Δ = 0). Den tidligere beslutning om at droppe
    den byggede på at den var beregnet af os; den præmis er afkræftet.

    Fordi api_entsoe_prices.php ikke har kolonnen, skal den stå i V1_ONLY —
    ellers påstår skemaet at begge kilder kan levere en komplet række.
    """
    schema = SCHEMAS["spot_entsoe"]
    assert "spot_price_dkk" in schema.v2_columns
    assert "spot_price_dkk" not in schema.dropped
    assert schema.v1_to_v2["spot_price_dkk"] == "spot_price_dkk"
    assert "spot_price_dkk" in schema.v1_only
    # Målingen der bærer beslutningen: endpointet har ingen DKK-kolonne.
    assert not [c for c in schema.api_columns if "dkk" in c.lower()]


def test_auction_backfilles_ikke() -> None:
    """C2: en v1-fil uden auction forbliver v1.

    Værdien kommer fra kilden ved genhentning eller ikke. Står der en
    default-værdi nogen steder, er den en påstand om hvilken udbudsrunde en
    historisk række tilhørte — og den har ingen målt hjemmel.
    """
    schema = SCHEMAS["mfrr_capacity"]
    reason = schema.added["auction"]
    assert "INGEN BACKFILL" in reason, (
        "beslutningen om ikke at backfille auction skal stå eksplicit i "
        "modulet, ikke kun i et notat"
    )
    # auction må ikke kunne komme fra v1-vejen — hverken som mål eller kilde.
    assert "auction" not in schema.v1_to_v2
    assert "auction" not in schema.v1_to_v2.values()
    assert "auction" not in schema.v1_only


# ==========================================================================
# Gate 1d — ENDPOINT-KONTRAKTEN
#
# Kontrakten er en tabel, ikke en regel. Testene her holder den ærlig:
# et felt må ikke stå som målt uden en værdi, og to endpoints må ikke
# stiltiende blive ens.
# ==========================================================================

ALL_CONTRACTS = sorted(ENDPOINT_CONTRACTS)


@pytest.mark.parametrize("key", ALL_CONTRACTS)
def test_kontraktnoegle_matcher_endpointfeltet(key: str) -> None:
    """Opslagsnøglen og objektets eget endpoint skal være samme streng."""
    assert ENDPOINT_CONTRACTS[key].endpoint == key


@pytest.mark.parametrize("key", ALL_CONTRACTS)
def test_status_daekker_praecis_kontraktfelterne(key: str) -> None:
    """Ingen felter uden status, ingen status uden felt."""
    c = ENDPOINT_CONTRACTS[key]
    assert set(c.status) == set(CONTRACT_FIELDS), (
        f"{key}: status dækker {sorted(c.status)}, "
        f"forventede {sorted(CONTRACT_FIELDS)}"
    )
    ulovlige = {v for v in c.status.values()} - {"målt", "uafklaret"}
    assert not ulovlige, f"{key}: ukendte statusværdier {ulovlige}"


@pytest.mark.parametrize("key", ALL_CONTRACTS)
def test_maalt_betyder_vaerdi_og_uafklaret_betyder_none(key: str) -> None:
    """
    Den ene invariant der gør tabellen brugbar: står der 'målt', ER der en
    værdi; står der 'uafklaret', er værdien None. Et felt kan ellers se
    besvaret ud uden at være det — og omvendt.
    """
    c = ENDPOINT_CONTRACTS[key]
    for felt in CONTRACT_FIELDS:
        vaerdi = getattr(c, felt)
        if c.status[felt] == "målt":
            assert vaerdi is not None, (
                f"{key}.{felt} er mærket 'målt', men står som None"
            )
        else:
            assert vaerdi is None, (
                f"{key}.{felt} er mærket 'uafklaret', men bærer værdien "
                f"{vaerdi!r} — så er den enten målt eller gættet"
            )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_hvert_datasaet_med_endpoint_har_en_kontrakt(name: str) -> None:
    """Gate 2 skal aldrig kalde et endpoint der ikke er beskrevet."""
    ep = SCHEMAS[name].endpoint
    if ep is None:
        return
    assert ep in ENDPOINT_CONTRACTS, f"{name}: {ep} mangler i ENDPOINT_CONTRACTS"


@pytest.mark.parametrize("key", ALL_CONTRACTS)
def test_delivers_resolution_stemmer_med_frozensettet(key: str) -> None:
    """De to kilder til samme påstand må ikke kunne komme i modstrid."""
    c = ENDPOINT_CONTRACTS[key]
    if c.status["delivers_resolution"] != "målt":
        return
    assert c.delivers_resolution == (key in ENDPOINTS_WITH_RESOLUTION_MINUTES), (
        f"{key}: delivers_resolution={c.delivers_resolution}, men "
        f"ENDPOINTS_WITH_RESOLUTION_MINUTES siger det modsatte"
    )


def test_de_to_sysapp_endpoints_er_stadig_uenige() -> None:
    """
    Den målte modsigelse skal blive stående. Harmoniserer nogen de to felter,
    forsvinder præcis den fælde kontrakten findes for: samme vært, samme
    datoformat, modsat betydning.
    """
    eb = ENDPOINT_CONTRACTS["/api_eds_balance.php"]
    ep = ENDPOINT_CONTRACTS["/api_energinet_prices.php"]
    assert eb.filter_timezone == "utc" and ep.filter_timezone == "dk", (
        "Målt: api_eds_balance.php filtrerer på UTC, api_energinet_prices.php "
        "på dansk lokaltid. Ændres det, skal målingen laves om først."
    )
    assert eb.unknown_param == "400" and ep.unknown_param == "ignoreres tavst"


def test_eds_har_modsat_datosemantik_af_proxyen() -> None:
    """
    En bar dato betyder ikke det samme på de to API'er. Det er den ene fejl
    §10.3.1 gjorde, og den må ikke krybe tilbage.
    """
    proxy = ENDPOINT_CONTRACTS["/api_eds_balance.php"]
    eds = ENDPOINT_CONTRACTS[
        "https://api.energidataservice.dk/dataset/DayAheadPrices"
    ]
    assert proxy.end_boundary == "inklusiv-hele-døgnet"
    assert eds.end_boundary == "eksklusiv"


def test_elspotprices_arver_ikke_dayaheadprices() -> None:
    """B2: den ene blev målt, den anden ikke. De må ikke smelte sammen."""
    els = ENDPOINT_CONTRACTS[
        "https://api.energidataservice.dk/dataset/Elspotprices"
    ]
    assert els.status["end_boundary"] == "uafklaret"
    assert els.end_boundary is None


def test_entsoe_tidsakse_staar_som_uafklaret() -> None:
    """
    Målingen slår endpointets eget meta. Så længe de to er i modstrid, må
    feltet ikke stå som besvaret.
    """
    c = ENDPOINT_CONTRACTS["/api_entsoe_prices.php"]
    assert c.status["filter_timezone"] == "uafklaret"
    assert c.filter_timezone is None


def test_entsoe_omraadekoder_har_understreg() -> None:
    """Målt enum. De korte koder (DK1, DE) giver 400."""
    c = ENDPOINT_CONTRACTS["/api_entsoe_prices.php"]
    assert "DK_1" in c.area_values and "DE_LU" in c.area_values
    assert "DK1" not in c.area_values and "DE" not in c.area_values


@pytest.mark.parametrize(
    "emne",
    [
        "api_entsoe_prices.php",   # den målte tidsaksefejl
        "RATE LIMIT",              # EDS' ukendte kvote
        "SKEMABLANDING",           # den tavse v1/v2-blanding
        "MANUELLE SKRIVEVEJ",      # den umigrerbare arbejdsgang
    ],
)
def test_unresolved_naevner_stadig(emne: str) -> None:
    """
    Disse fire er ikke løst. Forsvinder de fra UNRESOLVED, ser Gate 2 et
    afklaret billede der ikke findes.
    """
    assert any(emne in u for u in UNRESOLVED), (
        f"UNRESOLVED nævner ikke længere {emne!r}"
    )


# ==========================================================================
# Gate 1d — ENHEDER
# ==========================================================================

# Enhedsordforrådet. Frit tekstfelt ville drive: "EUR/MWh", "eur/mwh",
# "EUR pr. MWh" ville alle bestå, og ingen af dem kunne sammenlignes.
TILLADTE_ENHEDER = {
    "EUR/MWh", "DKK/MWh", "EUR/MW", "DKK/MW",
    "°C", "m/s", "W/m²", "mm", "hPa", "%", "s",
    "tekst-enum", "UTC-tidsstempel", "enum (-1, 0, 1, NULL)",
}

# Frosset. At sætte en enhed er en beslutning om at nogen har MÅLT eller
# LÆST den; tallet her skal ændres i samme greb, så det ikke sker i forbifarten.
# Gate 1e: 75 → 74 og 42 → 41, fordi spot_entsoe.resolution_minutes udgik
# sammen med den forkastede API-vej.
ANTAL_V2_KOLONNER = 74
ANTAL_UDEN_ENHED = 41


@pytest.mark.parametrize("name", ALL_NAMES)
def test_units_daekker_praecis_v2_columns(name: str) -> None:
    """Hverken en kolonne uden enhedspost eller en post uden kolonne."""
    d = SCHEMAS[name]
    assert set(d.units) == set(d.v2_columns), (
        f"{name}: units dækker {sorted(set(d.units) ^ set(d.v2_columns))} "
        f"forkert i forhold til v2_columns"
    )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_enheder_kommer_fra_ordforraadet(name: str) -> None:
    d = SCHEMAS[name]
    ukendte = {u for u in d.units.values() if u is not None} - TILLADTE_ENHEDER
    assert not ukendte, f"{name}: enheder uden for ordforrådet: {sorted(ukendte)}"


def test_antallet_uden_enhed_er_frosset() -> None:
    tot = sum(len(d.v2_columns) for d in SCHEMAS.values())
    uden = sum(
        1 for d in SCHEMAS.values() for c in d.v2_columns if d.units[c] is None
    )
    assert (tot, uden) == (ANTAL_V2_KOLONNER, ANTAL_UDEN_ENHED), (
        f"målt {uden}/{tot} uden enhed, indefrosset {ANTAL_UDEN_ENHED}/"
        f"{ANTAL_V2_KOLONNER}. Er en enhed kommet til, så skriv HVOR den er "
        "målt eller dokumenteret, og ret tallet."
    )


def test_enheden_udledes_ikke_af_navnet() -> None:
    """
    Prøven på reglen. Disse kolonner BÆRER enheden i navnet, men ingen kilde
    dokumenterer den — så de skal stå som None. Sætter nogen "MW" på
    afrr_up_mw uden en måling, fanges det her.
    """
    navne_der_frister = {
        "imbalance_price": ("afrr_up_mw", "afrr_down_mw",
                            "mfrr_marginal_price_up_dkk"),
        "mfrr_activation": ("total_mfrr_up_mw", "mfrr_sa_up_eur"),
        "mfrr_capacity":   ("up_demand_mw", "down_price_eur"),
        # resolution_minutes udgik af v2 i Gate 1e sammen med vejen.
        "spot_entsoe":     ("spot_price_eur",),
    }
    for name, kolonner in navne_der_frister.items():
        for c in kolonner:
            assert SCHEMAS[name].units[c] is None, (
                f"{name}.{c} har fået en enhed. Står den i OpenAPI-specen "
                "eller er den målt? Ellers er den udledt af navnet."
            )


def test_den_bestridte_kolonne_er_flagget() -> None:
    """
    spot_dk.hour_utc ER UTC (målt). spot_entsoe.hour_utc er bestridt, fordi
    API-vejen leverer dansk lokaltid. De to må ikke se ens ud.
    """
    assert SCHEMAS["spot_dk"].units["hour_utc"] == "UTC-tidsstempel"
    assert SCHEMAS["spot_entsoe"].units["hour_utc"] is None


# ==========================================================================
# Gate 1e — MIGRATIONSSPÆRRER, DEN FORKASTEDE VEJ, BESLUTNINGERNE
# ==========================================================================

@pytest.mark.parametrize("name", ALL_NAMES)
def test_migratable_og_begrundelse_foelges_ad(name: str) -> None:
    """En spærre uden begrundelse er en gåde; en begrundelse uden spærre er støj."""
    s = SCHEMAS[name]
    assert s.migratable == (not s.not_migratable), (
        f"{name}: migratable={s.migratable}, men not_migratable er "
        f"{'sat' if s.not_migratable else 'tom'}"
    )


def test_de_to_spaerrer_har_forskellig_grund() -> None:
    """
    spot_system og spot_entsoe er begge spærret, men ikke af samme grund, og
    forskellen afgør om spærren kan åbnes. Smelter de to begrundelser sammen,
    forsvinder den skelnen — og dermed hvad der skal gøres ved dem.
    """
    assert set(MIGRATIONSSPAERRER) == {"spot_entsoe", "spot_system"}
    system = SCHEMAS["spot_system"].not_migratable
    entsoe = SCHEMAS["spot_entsoe"].not_migratable
    assert "INGEN KILDE" in system
    assert "MÅLET DUER IKKE" in entsoe
    assert system != entsoe


def test_forkastet_api_vej_er_ubrugelig_ikke_uafklaret() -> None:
    """
    C2. Bruger nogen `api_to_v2` for spot_entsoe, får de INTET — ikke noget
    forkert. Det er forskellen på ubrugelig og uafklaret: en uafklaret
    mapping ligger og ser rigtig ud, indtil den bliver brugt.
    """
    s = SCHEMAS["spot_entsoe"]
    assert s.api_to_v2 == {}, (
        "spot_entsoe.api_to_v2 er ikke længere tom. Vejen er forkastet — "
        "genopliv den ikke uden at måle tidsaksen igen."
    )
    assert s.api_path_rejected, "en tom api_to_v2 uden begrundelse er en fejl"
    # Hele API-siden skal være gjort rede for som droppet, ikke glemt.
    assert set(s.api_dropped) == set(s.api_columns)


def test_ingen_v2_kolonne_kan_komme_fra_den_forkastede_vej() -> None:
    """
    Prøven på at forkastelsen er gennemført: intet v2-navn må stamme fra
    api_to_v2_rejected uden også at kunne komme fra klonen.
    """
    s = SCHEMAS["spot_entsoe"]
    fra_klonen = set(s.v1_to_v2.values())
    for v2navn in s.api_to_v2_rejected.values():
        if v2navn not in s.v2_columns:
            continue
        assert v2navn in fra_klonen, (
            f"{v2navn!r} står i v2_columns, men kan kun komme fra den "
            "forkastede API-vej"
        )


def test_resolution_minutes_udgik_med_vejen() -> None:
    """
    Den eneste kolonne der KUN kunne komme fra det forkastede endpoint. Den
    må ikke snige sig tilbage: målingen af at endpointet leverede den er
    stadig sand, men vi bruger ikke endpointet.
    """
    s = SCHEMAS["spot_entsoe"]
    assert "resolution_minutes" not in s.v2_columns
    assert "resolution_minutes" not in s.added
    assert "resolution_minutes" not in s.units
    # Målingen om endpointet står ved magt.
    assert "/api_entsoe_prices.php" in ENDPOINTS_WITH_RESOLUTION_MINUTES
    assert "resolution_minutes" in s.api_columns


def test_maalingen_bag_forkastelsen_staar_i_modulet() -> None:
    """
    C3. Tallene ER begrundelsen. Uden dem er forkastelsen en påstand, og den
    næste der ser endpointet vil prøve igen.
    """
    tekst = SCHEMAS["spot_entsoe"].notes
    for spor in ("96/96", "+1 t i marts", "+2 t i juli", "Europe/Copenhagen"):
        assert spor in tekst, f"målesporet {spor!r} er forsvundet fra notes"


@pytest.mark.parametrize("emne", ["KILDEKOLONNE PR. RÆKKE", "VERSIONSVAGT"])
def test_beslutningerne_staar_skrevet(emne: str) -> None:
    assert any(emne in d for d in DECISIONS), f"DECISIONS mangler {emne!r}"


def test_kildekolonnen_er_betinget_af_api_udvidelsen() -> None:
    """
    D1's forudsætning må ikke tabes: kolonnen kan kun bæres hvis API'et
    leverer den. Står det ikke, ser beslutningen ubetinget ud.
    """
    d = next(x for x in DECISIONS if "KILDEKOLONNE" in x)
    assert "3.4" in d and "FORUDSÆTNING" in d


def test_versionsvagten_afbryder_ved_manglende_felt() -> None:
    """D2's svære halvdel: tomt felt må ikke betyde 'antag v1'."""
    d = next(x for x in DECISIONS if "VERSIONSVAGT" in x)
    assert "--adopt-schema=v1" in d
    assert "AFBRYD" in d
    assert "LÆS FØR HENTNING" in d


def test_fravaeret_af_auto_pull_er_beskrevet_som_egenskab() -> None:
    """
    B3. Uden begrundelsen ligner det en manglende feature, og så bliver den
    "rettet" af den næste der læser koden.
    """
    for spor in ("MÅLEINSTRUMENT", "6c95bde", "force_refresh"):
        assert spor in NO_AUTO_PULL, f"NO_AUTO_PULL mangler {spor!r}"
