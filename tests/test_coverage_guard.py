"""F1 — test af dæknings-vagten `assert_coverage`.

Vagten skal sidde i `src/data_loader.py` og kaldes fra
`src/data_loader_github.py:_read_dataset`. Signaturen er fastlagt i Gate 0.5:

    assert_coverage(ts, start_ts, end_ts, *, label,
                    bucket="1h", min_per_bucket=1) -> None

Den skal rejse en exception når tidsstemplerne `ts` ikke dækker hver bucket i
[start_ts, end_ts] med mindst `min_per_bucket` observationer.

DESIGN
------
Vagten findes ikke endnu. Testene der måler den fejler derfor med en eksplicit
besked fra `_guard()` i stedet for en ImportError der ville rive hele modulet
ned — de tests der skal BESTÅ på HEAD (C, E, F) må ikke rammes af at vagten
mangler.

Alle perioder og rækketal nedenfor er MÅLT i Gate 0.5 mod df-data-klonen; de
er ikke udledt. Se noter/notat_f1_gate05_oploesning_akse.md. Hver test
asserterer sine egne forudsætninger først, så en ændring i datarepoet giver
"forudsætning brudt" og ikke "vagten virker ikke".

Alle tests kører med resolution 1h.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

# Vagten har endnu ingen fastlagt exception-type (åbent punkt, se rapportens
# USIKKERT). Vi accepterer bredt nu og strammer denne ene linje i Gate 2.
COVERAGE_ERROR: type[BaseException] = Exception


# ---------------------------------------------------------------------------
# Hjælpere
# ---------------------------------------------------------------------------

def _guard():
    """Hent `assert_coverage`. Fejler eksplicit så længe vagten ikke findes.

    Bruges af de tests der måler at vagten FEJLER på manglende dækning
    (A, B, D, G, H). De skal være røde på HEAD.
    """
    fn = _guard_optional()
    if fn is None:
        pytest.fail(
            "src.data_loader.assert_coverage findes ikke. "
            "Vagten er ikke implementeret endnu (Gate 2) — testen måler "
            "netop dét og skal fejle her på HEAD."
        )
    return fn


def _guard_optional():
    """Hent `assert_coverage` hvis den findes, ellers None.

    Bruges af falsk-positiv-testene (E, F). De måler at vagten IKKE fejrer
    på fuldt dækkede vinduer — og før vagten findes kan der pr. definition
    ikke være en falsk positiv. På HEAD måler de derfor kun deres
    dataforudsætninger; efter Gate 2 måler de vagten. De skal være grønne
    hele vejen, ellers kan de ikke skelne "vagten er for stram" fra
    "vagten mangler".
    """
    from src import data_loader

    return getattr(data_loader, "assert_coverage", None)


def _timestamps(
    df_data: Path,
    folder: str,
    area: str,
    years: list[int],
    time_col: str,
    *,
    area_col: str | None = None,
) -> pd.Series:
    """Læs og konkatenér årsfiler præcis som `_read_dataset` gør.

    Årsfiler der ikke findes springes over — det er dagens adfærd
    (data_loader_github.py:137-139) og er selve hullet vagten skal lukke.
    Tidskolonnen slås op ved navn. `area_col` filtrerer på område når
    filen kan indeholde flere (spot).
    """
    frames = []
    for year in years:
        path = df_data / folder / f"{area}_{year}.csv"
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        return pd.Series(dtype="datetime64[ns]")

    df = pd.concat(frames, ignore_index=True)
    assert time_col in df.columns, (
        f"{folder}/{area}: forventet tidskolonne {time_col!r}, "
        f"fik {list(df.columns)}"
    )
    if area_col is not None:
        assert area_col in df.columns, f"{folder}/{area}: mangler {area_col!r}"
        df = df[df[area_col] == area]
    return pd.to_datetime(df[time_col]).sort_values().reset_index(drop=True)


def _window(ts: pd.Series, start: str, end: str) -> pd.Series:
    """Afgræns til [start, end] — svarer til data_loader_github.py:167."""
    return ts[(ts >= pd.Timestamp(start)) & (ts <= pd.Timestamp(end))].reset_index(drop=True)


def _hours(start: str, end: str) -> pd.DatetimeIndex:
    """Modellens akse: timesopløst, begge endepunkter inklusive."""
    return pd.date_range(start, end, freq="h")


def _missing_hours(ts: pd.Series, start: str, end: str) -> list[pd.Timestamp]:
    covered = set(ts.dt.floor("h"))
    return [t for t in _hours(start, end) if t not in covered]


# ---------------------------------------------------------------------------
# A. PRIMÆR — delvis dækning i en fil der findes
# ---------------------------------------------------------------------------

def test_A_partial_coverage_in_existing_file(df_data, df_data_head):
    """afrr/DK1 2024: filen findes, men dækker kun okt-dec.

    2186 rækker fra 2024-10-01 22:00. 6598 af 8784 modeltimer mangler.
    Dagens kode er helt tavs: `df.empty` er falsk, `missing` er tom, og
    `if not frames` udløses ikke. Vagten skal fejle.
    """
    start, end = "2024-01-01 00:00", "2024-12-31 23:00"
    ts = _window(_timestamps(df_data, "afrr", "DK1", [2024], "TimeUTC"), start, end)

    # Forudsætninger målt i Gate 0.5 — brydes de, er datarepoet ændret.
    assert len(ts) == 2186, f"df-data {df_data_head}: forventede 2186 rækker, fik {len(ts)}"
    assert ts.min() == pd.Timestamp("2024-10-01 22:00")
    assert ts.max() == pd.Timestamp("2024-12-31 23:00")
    assert len(_missing_hours(ts, start, end)) == 6598

    with pytest.raises(COVERAGE_ERROR):
        _guard()(ts, pd.Timestamp(start), pd.Timestamp(end),
                 label="afrr/DK1", bucket="1h", min_per_bucket=1)


# ---------------------------------------------------------------------------
# B. SEKUNDÆR — manglende årsfil i et flerårsspænd
# ---------------------------------------------------------------------------

def test_B_missing_year_file_in_multi_year_span(df_data, df_data_head):
    """imbalance/DK1 2024-2025: 2024-filen findes ikke, 2025 gør.

    `_read_dataset` printer "spring over DK1_2024.csv" (linje 150) og
    returnerer 2025-data. `df.empty` er falsk, så hele 2024 nul-fyldes
    tavst på linje 402/405. Vagten skal fejle.
    """
    start, end = "2024-01-01 00:00", "2025-12-31 23:00"
    assert not (df_data / "imbalance" / "DK1_2024.csv").exists(), \
        f"df-data {df_data_head}: DK1_2024.csv er kommet til — testen måler ikke længere hullet"
    assert (df_data / "imbalance" / "DK1_2025.csv").exists()

    ts = _window(_timestamps(df_data, "imbalance", "DK1", [2024, 2025], "TimeUTC"), start, end)

    assert len(ts) == 29037, f"df-data {df_data_head}: forventede 29037 rækker, fik {len(ts)}"
    assert ts.min() == pd.Timestamp("2025-03-04 12:00")
    # Hele 2024 (8784 t) + 2025 frem til datastart (1500 t).
    assert len(_missing_hours(ts, start, end)) == 10284

    with pytest.raises(COVERAGE_ERROR):
        _guard()(ts, pd.Timestamp(start), pd.Timestamp(end),
                 label="imbalance/DK1", bucket="1h", min_per_bucket=1)


# ---------------------------------------------------------------------------
# C. NEGATIV KONTROL — den eksisterende vagt skal blive ved med at virke
# ---------------------------------------------------------------------------

def test_C_existing_guard_still_raises_when_no_file_at_all(df_data, df_data_head):
    """imbalance/DK1 2024 alene: ingen fil overhovedet.

    Skal give FileNotFoundError fra data_loader_github.py:143. Denne test
    skal BESTÅ på HEAD og blive ved med at bestå efter Gate 2 — den skelner
    "gammel vagt virker" fra "ny vagt virker".
    """
    from src.data_loader_github import _read_dataset

    assert not (df_data / "imbalance" / "DK1_2024.csv").exists(), \
        f"df-data {df_data_head}: DK1_2024.csv er kommet til"

    with pytest.raises(FileNotFoundError):
        _read_dataset(df_data, "imbalance", "DK1",
                      pd.date_range("2024-01-01 00:00", "2024-12-31 23:00", freq="h"),
                      time_col="TimeUTC")


# ---------------------------------------------------------------------------
# D. HUL INDEN FOR DÆKNING — begge endepunkter til stede
# ---------------------------------------------------------------------------

def test_D_gap_inside_covered_range(df_data, df_data_head):
    """mfrr_cap/DK1 2023-06-21..30: 24-timers hul midt i vinduet.

    Både første og sidste modeltime er dækket, så ingen længde- eller
    endepunktstjek fanger det. Valgt frem for DMI's DST-hul, fordi
    dmi/*.csv er under aktiv korrektion i datarepoet.
    """
    start, end = "2023-06-21 00:00", "2023-06-30 23:00"
    ts = _window(_timestamps(df_data, "mfrr_cap", "DK1", [2023], "TimeUTC"), start, end)

    assert len(ts) == 216, f"df-data {df_data_head}: forventede 216 rækker, fik {len(ts)}"
    assert ts.min() == pd.Timestamp(start), "første modeltime skal være dækket"
    assert ts.max() == pd.Timestamp(end), "sidste modeltime skal være dækket"

    missing = _missing_hours(ts, start, end)
    assert len(missing) == 24
    assert missing[0] == pd.Timestamp("2023-06-22 22:00")
    assert missing[-1] == pd.Timestamp("2023-06-23 21:00")

    with pytest.raises(COVERAGE_ERROR):
        _guard()(ts, pd.Timestamp(start), pd.Timestamp(end),
                 label="mfrr_cap/DK1", bucket="1h", min_per_bucket=1)


# ---------------------------------------------------------------------------
# E. FULD DÆKNING — falsk-positiv-testen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "folder,area,years,time_col,area_col,start,end,n_rows",
    [
        ("afrr",     "DK1", [2025], "TimeUTC",  None,          "2025-01-01 00:00", "2025-12-31 23:00", 8760),
        ("mfrr_cap", "DK1", [2024], "TimeUTC",  None,          "2024-01-01 00:00", "2024-12-31 23:00", 8784),
        ("spot",     "DK1", [2023], "hour_utc", "price_area",  "2023-01-01 00:00", "2023-12-31 23:00", 8760),
    ],
    ids=["afrr_DK1_2025", "mfrr_cap_DK1_2024_skudaar", "spot_DK1_2023_1h"],
)
def test_E_full_coverage_does_not_raise(
    df_data, df_data_head, folder, area, years, time_col, area_col, start, end, n_rows
):
    """Tre vinduer med 0 huller og 0 dubletter. Vagten må IKKE fejle."""
    ts = _window(
        _timestamps(df_data, folder, area, years, time_col, area_col=area_col),
        start, end,
    )

    assert len(ts) == n_rows, f"df-data {df_data_head}: forventede {n_rows} rækker, fik {len(ts)}"
    assert not ts.duplicated().any()
    assert _missing_hours(ts, start, end) == []

    guard = _guard_optional()
    if guard is None:
        return  # HEAD: ingen vagt ⇒ ingen falsk positiv mulig. Se _guard_optional.
    # Ingen `pytest.raises` — kaldet skal returnere uden at rejse.
    guard(ts, pd.Timestamp(start), pd.Timestamp(end),
          label=f"{folder}/{area}", bucket="1h", min_per_bucket=1)


# ---------------------------------------------------------------------------
# F. OPLØSNINGSSKIFTET — regressionstest på bucket-designet
# ---------------------------------------------------------------------------

def test_F_resolution_change_is_not_a_gap(df_data, df_data_head):
    """spot/DK1 hen over 1h→15min-skiftet 2025-09-30 22:00 → 22:15.

    Frames indeholder både 3600s- og 900s-skridt uden ægte huller. Netop
    dette tilfælde er grunden til at vagten måler i buckets frem for i
    skridt: med bucket="1h", min_per_bucket=1 dækker 15-min-data trivielt
    hver time, og skiftet kræver ingen breakpoints. Vagten skal PASSERE.
    """
    start, end = "2025-09-25 00:00", "2025-10-05 23:00"
    ts = _window(
        _timestamps(df_data, "spot", "DK1", [2025], "hour_utc", area_col="price_area"),
        start, end,
    )

    assert len(ts) == 627, f"df-data {df_data_head}: forventede 627 rækker, fik {len(ts)}"
    deltas = ts.diff().dropna().value_counts()
    assert deltas.get(pd.Timedelta(seconds=3600)) == 142, "1-times-delen mangler"
    assert deltas.get(pd.Timedelta(seconds=900)) == 484, "15-min-delen mangler"
    assert _missing_hours(ts, start, end) == [], "vinduet må ikke have ægte huller"

    guard = _guard_optional()
    if guard is None:
        return  # HEAD: ingen vagt ⇒ ingen falsk positiv mulig. Se _guard_optional.
    guard(ts, pd.Timestamp(start), pd.Timestamp(end),
          label="spot/DK1", bucket="1h", min_per_bucket=1)


# ---------------------------------------------------------------------------
# G. B4 — den dobbelte end-regel
# ---------------------------------------------------------------------------

def test_G_balance_end_rule_is_gone(df_data, df_data_head):
    """imbalance/DK1 over 2026-01-01 .. 2026-04-30 med min_per_bucket=4.

    Var xfail indtil Gate 3. Den gamle balance-sti sendte
    'YYYY-MM-DDTHH:MM' til `_read_dataset`, hvor kolon'et forhindrede
    end-udvidelsen i at slå til, så 23:15/23:30/23:45 blev skåret væk og
    sidste time resamplet fra 1 af 4 kvarter (11 517 af 11 520).

    Med aksen sendt ned i stedet for datostrenge er vinduet
    [idx.min(), idx.max() + step) — halvåbent til højre — og sidste bucket
    får alle fire kvarter. Vagten må ikke fyre.
    """
    axis = _hours("2026-01-01 00:00", "2026-04-30 23:00")
    step = pd.Timedelta("1h")
    ts_all = _timestamps(df_data, "imbalance", "DK1", [2026], "TimeUTC")
    ts = ts_all[(ts_all >= axis.min()) & (ts_all < axis.max() + step)].reset_index(drop=True)

    assert len(ts) == 11520, \
        f"df-data {df_data_head}: forventede 11520 kvarter (var 11517 før Gate 3), fik {len(ts)}"
    per_hour = ts.dt.floor("h").value_counts()
    assert per_hour.min() == 4, "ingen bucket må være underfyldt"
    assert per_hour[pd.Timestamp("2026-04-30 23:00")] == 4, \
        "sidste time skal have alle fire kvarter"

    _guard()(ts, axis.min(), axis.max(),
             label="imbalance/DK1", bucket="1h", min_per_bucket=4)


def test_G2_both_paths_cover_the_same_window(df_data, df_data_head):
    """Regressionstest: spot og imbalance afgrænses ens over samme akse.

    På den gamle kode adskilte de to stier sig med præcis 59:59 — spot fik
    "%Y-%m-%d" og dermed en end-udvidelse til 23:59:59, mens balance fik
    "T%H:%M" og ingen udvidelse. Begge læses nu med samme regel.
    """
    from src.data_loader_github import _read_dataset

    axis = _hours("2026-01-01 00:00", "2026-04-30 23:00")

    spot = _read_dataset(df_data, "spot", "DK1", axis, time_col="hour_utc")
    imb = _read_dataset(df_data, "imbalance", "DK1", axis, time_col="TimeUTC")

    spot_ts = pd.to_datetime(spot["hour_utc"])
    imb_ts = pd.to_datetime(imb["TimeUTC"])

    assert spot_ts.min() == imb_ts.min() == axis.min()
    assert spot_ts.max() == imb_ts.max() == pd.Timestamp("2026-04-30 23:45"), \
        "begge stier skal nå det sidste kvarter i sidste bucket"
    # Begge er 15-min i 2026 og dækker samme akse ⇒ samme rækketal.
    assert len(spot) == len(imb) == 11520, \
        f"df-data {df_data_head}: spot={len(spot)}, imbalance={len(imb)}"


def test_G3_read_dataset_refuses_a_date_string(df_data):
    """Signaturen må ikke kunne fodres med en datostreng.

    Det er selve mekanismen der lukker end-gætteriet: kan funktionen ikke
    modtage en streng, kan reglen "bar dato ⇒ udvid til 23:59:59" ikke
    genopstå et andet sted.
    """
    from src.data_loader_github import _read_dataset

    with pytest.raises(TypeError):
        _read_dataset(df_data, "afrr", "DK1", "2025-01-01", time_col="TimeUTC")


def test_G4_unknown_dataset_raises_instead_of_defaulting(df_data):
    """Et ukendt foldernavn skal rejse, ikke falde tilbage til min_per_bucket=1.

    En dækningsantagelse er en påstand om kildens native opløsning. F7
    lægger nye datasæt ind (ngas, magasin, grid2, crossborder); et
    15-min-datasæt målt med min_per_bucket=1 ville blive godkendt for
    slapt uden en lyd.
    """
    from src.data_loader_github import _read_dataset

    axis = _hours("2025-01-01 00:00", "2025-01-31 23:00")
    with pytest.raises(KeyError, match="dækningsantagelse"):
        _read_dataset(df_data, "ngas", "DK1", axis, time_col="TimeUTC")


# ---------------------------------------------------------------------------
# H. 15-MINUTTERS-GRÆNSEN
# ---------------------------------------------------------------------------

def test_H_15min_bucket_is_explicitly_unsupported(df_data):
    """bucket="15min" skal afvises med NotImplementedError.

    Begrundelse (Gate 0.5 §A1): før 2025-09-30 22:00 er spot ægte timesdata,
    så en 15-minutters model SKAL opsample — det er en erklæret opsampling,
    ikke manglende dækning. Efter skiftet er det omvendt. Én min_per_bucket
    kan ikke dække begge, og grænsen skal være synlig frem for gættet.
    """
    start, end = "2025-01-01 00:00", "2025-01-31 23:00"
    ts = _window(
        _timestamps(df_data, "spot", "DK1", [2025], "hour_utc", area_col="price_area"),
        start, end,
    )
    assert len(ts) > 0

    with pytest.raises(NotImplementedError):
        _guard()(ts, pd.Timestamp(start), pd.Timestamp(end),
                 label="spot/DK1", bucket="15min", min_per_bucket=1)
