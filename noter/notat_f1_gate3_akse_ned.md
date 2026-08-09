# F1 Gate 3 — Aksen sendes ned, den dobbelte end-regel er lukket

**Status:** `_read_dataset` modtager nu modellens akse i stedet for to
omformaterede datostrenge. B4 er lukket. 16 tests grønne, ingen xfail.
Første balancekørsel gennemført med vagten aktiv.
**Forudsætninger:** [Gate 0](notat_f1_gate0_daekningsvagt.md), [Gate 0.5](notat_f1_gate05_oploesning_akse.md), [Gate 1](notat_f1_gate1_test.md), [Gate 2](notat_f1_gate2_implementering.md).
**Modelrepo:** HEAD `3ea0399` + ikke-committede ændringer fra Gate 2 og 3.
**df-data-klon:** `6c95bde` (2026-08-07).
**Dato:** 2026-08-07

---

# 1. TRIN 0 — KORTLÆGNING

Aflæst i arbejdstræet før ændring. Bemærk at HEAD stadig er `3ea0399`, men
arbejdstræet bærer Gate 2's ikke-committede ændringer — linjenumrene nedenfor
er dem der faktisk blev ændret, ikke dem i commit'en.

## Signatur før ændring

```python
def _read_dataset(
    repo_root: Path, folder: str, zone_or_area: str,
    start: str, end: str, time_col: str,
) -> pd.DataFrame:          # linje 140-147
```

## De syv kaldesteder — Gate 0's tal er drevet, men antallet holder

| Gate 0's tal | ved Gate 3 | funktion | argumenter |
|---|---|---|---|
| 184 | **222** | `fetch_spot_prices_github` | `"spot", zone, start, end, time_col="hour_utc"` |
| 219 | **257** | `fetch_dmi_obs_github` | `"dmi", area, start, end, time_col="hour_utc"` |
| 244 | **282** | `fetch_dmi_weather_github` | `"dmi", area, start, end, time_col="hour_utc"` |
| 277 | **315** | `fetch_balance_prices_github` | `"afrr", zone, start, end, time_col="TimeUTC"` |
| 294 | **332** | `fetch_balance_prices_github` | `"imbalance", zone, start, end, time_col="TimeUTC"` |
| 357 | **395** | `fetch_balance_prices_github` | `"mfrr_cap", zone, start, end, time_col="TimeUTC"` |
| 369 | **407** | `fetch_balance_prices_github` | `"mfrr_act", zone, start, end, time_col="TimeUTC"` |

Syv bekræftet. Driften (+38) skyldes Gate 2's indsættelser.

## Hvor start/end blev dannet

```python
572:    start = idx.min().strftime("%Y-%m-%d")          # spot/DMI-stien
573:    end = idx.max().strftime("%Y-%m-%d")
616:    start_iso = pd.Timestamp(cfg.time.start).strftime("%Y-%m-%dT%H:%M")   # balance
617:    end_iso = pd.Timestamp(cfg.time.end).strftime("%Y-%m-%dT%H:%M")
```

To forskellige formater af samme akse — det er hele defekten. Bemærk desuden
at balance-stien gik tilbage til `cfg.time` frem for til `idx`, altså en
tredje periodedefinition på samme kaldevej.

## End-udvidelsesreglen, ordret

```python
185:    start_ts = pd.Timestamp(start)
186:    end_ts = pd.Timestamp(end)
187:    if end_ts == end_ts.normalize() and ":" not in str(end):
188:        end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
```

`":" not in str(end)` er hængslet. `"2026-04-30"` udvides; `"2026-04-30T23:00"`
gør ikke. Deraf 59:59-forskellen.

## Kaldes `_read_dataset` fra andre moduler?

**Nej.** Grep over hele repoet uden for `.venv`: kun
`src/data_loader_github.py` og `tests/`. De fem scripts Gate 0 fandt
(`capture_rate.py`, `capture_rate_q1_2026.py`, `calibrate_gate.py`,
`diag_sweep.py`, `calibrate_heat_load.py`) kalder alle
`load_external_data_github`, aldrig `_read_dataset` direkte. Signaturændringen
rammer dem derfor ikke. Rapporteret, ikke rettet.

---

# 2. VALG AF SIGNATUR OG INTERVAL

## Signatur: (a) `idx: pd.DatetimeIndex`

```python
def _read_dataset(repo_root, folder, zone_or_area, idx, time_col) -> pd.DataFrame
```

Begrundelse ud fra hvad funktionen faktisk behøver:

| behov | (a) `idx` | (b) `start_ts, end_ts, freq` |
|---|---|---|
| `_years_in_range` | `idx.min().year .. idx.max().year` | ✓ |
| masken | `idx.min()`, `idx.max()`, step | ✓ |
| `assert_coverage`s bucket-navn | udledes af `idx.freq` | kræver `freq` som separat parameter |
| kan ikke fodres med en datostreng | ✓ — en `DatetimeIndex` er ikke en `str` | ✗ — `start_ts: pd.Timestamp` accepterer klaglost `pd.Timestamp("2026-04-30")` |

Det afgørende er sidste række. Kravet var at end-udvidelsen ikke må kunne
genopstå. Med (b) ville `pd.Timestamp("2026-04-30")` stadig være et lovligt
argument, og dermed ville spørgsmålet "betød det midnat eller hele døgnet?"
stadig kunne stilles. Med (a) findes spørgsmålet ikke: aksen ER svaret.

Dertil kommer at `idx` allerede er den bindende periodedefinition
(Gate 0.5 §2): den er `ds.time`, den er `target_index`, og den er hvad
objektivet regner på. At sende noget afledt ville genåbne muligheden for en
fjerde definition.

Modargumentet — at `_read_dataset` nu kender hele aksen selvom den kun bruger
min/max/step — er reelt, og det står i docstringen. Prisen er lav; gevinsten
er at der ikke længere er tre periodebegreber i samme kaldevej.

En typetjek håndhæver det:

```python
if not isinstance(idx, pd.DatetimeIndex):
    raise TypeError(...)
```

Testet af `test_G3_read_dataset_refuses_a_date_string`.

## Interval: halvåbent til højre, lukkede bucket-etiketter

```
vindue = [idx.min(), idx.max() + step)
```

`idx` fra `make_time_index` er inklusiv i begge ender, så `idx.max()` er den
sidste modeltime. Men et bucket er ikke et punkt — bucket `idx.max()` spænder
`[idx.max(), idx.max() + step)`, og alle observationer i det span hører til
den. For 15-min-kilder er det netop `23:00`, `23:15`, `23:30`, `23:45`.

Et lukket `[idx.min(), idx.max()]` ville skære `23:15`–`23:45` væk — altså
præcis B4 igen, blot indført ad en anden vej. Det halvåbne vindue er derfor
ikke en stilistisk præference, men det eneste valg der matcher en
bucket-baseret dækningsmåling.

**Masken og vagten bruger samme afgrænsning.** Der er ét sted hvor vinduet
beregnes:

```python
step = _axis_step(idx)
window_start = idx.min()
window_end = idx.max() + step        # eksklusiv

mask = (ts >= window_start) & (ts < window_end)
assert_coverage(ts.loc[mask], window_start, idx.max(), bucket=..., ...)
```

Vagten får `idx.max()` som lukket højre-etiket og bygger buckets
`[idx.min() .. idx.max()]`. Alt i `[window_start, window_end)` gulver ned i en
etiket i det interval. De to udsagn er identiske sæt, udtrykt i hver sin
enhed — ikke to forskellige afgrænsninger.

---

# 3. DIFF-OVERSIGT

```
 src/data_loader.py        | 135 +++++++++++++++++++++++++++
 src/data_loader_github.py | 228 ++++++++++++++++++++++++++++++++++------------
 2 files changed, 305 insertions(+), 58 deletions(-)
```

(Tallene er kumulative for Gate 2 + Gate 3, da ingen af dem er committet.)

## `src/data_loader.py`

| ændring | indhold |
|---|---|
| `import math` | til nedadgående afrunding |
| `coverage_pct` | `math.floor(andel * 1000) / 10` — 8783/8784 viser nu **99.9 %**, ikke 100.0 % (Trin 3.2) |

`assert_coverage`s signatur er uændret. `CoverageError` uændret.

## `src/data_loader_github.py`

| ændring | indhold |
|---|---|
| `_years_in_range(start, end)` → `_years_in_range(idx)` | Udleder år af aksens endepunkter. Docstring forklarer hvorfor `idx.max() + step` aldrig kræver endnu et år. |
| **ny** `_axis_step(idx)` | Aksens skridtlængde fra `idx.freq`, med fallback til entydig differens. Rejser på uregelmæssig akse. |
| **ny** `_STEP_BUCKET` | `Timedelta → bucket-navn`. Ukendte skridt sendes videre som `str(step)`, så vagten kan afvise dem læsbart. |
| `_read_dataset` signatur | `start: str, end: str` → `idx: pd.DatetimeIndex` |
| `_read_dataset` krop | Typetjek; tom-akse-tjek; `KeyError` for ukendt `folder` (Trin 3.1); end-udvidelsen **slettet**; mask nu `>= window_start & < window_end`; `min_per_bucket=_MIN_OBS_PER_HOUR[folder]` uden `.get`-fallback; `bucket` fra aksens skridt |
| Resolution-vagten i `load_external_data_github` | **Fjernet** (Trin 2) — se nedenfor |
| Linje 572-573 | `strftime("%Y-%m-%d")` **slettet**; `idx` sendes direkte |
| Linje 616-617 | `strftime("%Y-%m-%dT%H:%M")` **slettet**; samme `idx` sendes |

## De syv kaldesteder — hvad der blev ændret ved hvert

| # | funktion | før | efter |
|---|---|---|---|
| 1 | `fetch_spot_prices_github` | `(repo_root, "spot", zone, start, end, time_col="hour_utc")` | `(repo_root, "spot", zone, idx, time_col="hour_utc")` |
| 2 | `fetch_dmi_obs_github` | `(..., "dmi", area, start, end, ...)` | `(..., "dmi", area, idx, ...)` |
| 3 | `fetch_dmi_weather_github` | `(..., "dmi", area, start, end, ...)` | `(..., "dmi", area, idx, ...)` |
| 4 | `fetch_balance_prices_github` (afrr) | `(..., "afrr", zone, start, end, ...)` | `(..., "afrr", zone, idx, ...)` |
| 5 | " (imbalance) | `(..., "imbalance", zone, start, end, ...)` | `(..., "imbalance", zone, idx, ...)` |
| 6 | " (mfrr_cap) | `(..., "mfrr_cap", zone, start, end, ...)` | `(..., "mfrr_cap", zone, idx, ...)` |
| 7 | " (mfrr_act) | `(..., "mfrr_act", zone, start, end, ...)` | `(..., "mfrr_act", zone, idx, ...)` |

De fire `fetch_*_github`-signaturer er ændret tilsvarende: parameterparret
`start: str, end: str` er erstattet af `idx: pd.DatetimeIndex`. Syv
fejlbeskeder der interpolerede `{start}..{end}` er rettet til
`{idx.min()}..{idx.max()}`.

## Trin 2 — 15-minutters-grænsen er flyttet og findes nu ét sted

Gate 2 havde grænsen to steder: i `assert_coverage` (`bucket != "1h"`) og i
`load_external_data_github` (`cfg.time.resolution != "1h"`). Den sidste var
et nødgreb, fordi `_read_dataset` ikke kendte opløsningen.

Med aksen nedsendt kender den den. Grænsen er derfor **fjernet fra
`load_external_data_github`** og håndhæves nu udelukkende af
`assert_coverage`, som får bucket-navnet fra aksens eget skridt:

```python
bucket=_STEP_BUCKET.get(step, str(step))
```

En 15-minutters akse giver `bucket="15min"`, som vagten afviser. Verificeret:

```
$ _read_dataset(R, "spot", "DK1", pd.date_range(..., freq="15min"), time_col="hour_utc")
NotImplementedError: assert_coverage: bucket='15min' er ikke understøttet — kun ['1h'] er. ...
```

Ét sted, ikke to. Test H består fortsat.

## Trin 3.1 — ukendt datasæt rejser

```python
if folder not in _MIN_OBS_PER_HOUR:
    raise KeyError(
        f"_read_dataset: ingen dækningsantagelse for datasættet {folder!r}. ..."
    )
```

Beskeden nævner eksplicit at F7 lægger nye datasæt ind, og at et
15-min-datasæt målt med `min_per_bucket=1` ville blive godkendt for slapt
uden en lyd. Testet af `test_G4_unknown_dataset_raises_instead_of_defaulting`
med `folder="ngas"`.

---

# 4. PYTEST — ORDRET

```
$ .venv/bin/pytest tests/ -v -p no:cacheprovider -rxX
tests/test_coverage_guard.py::test_A_partial_coverage_in_existing_file PASSED [  5%]
tests/test_coverage_guard.py::test_B_missing_year_file_in_multi_year_span PASSED [ 11%]
tests/test_coverage_guard.py::test_C_existing_guard_still_raises_when_no_file_at_all PASSED [ 17%]
tests/test_coverage_guard.py::test_D_gap_inside_covered_range PASSED     [ 23%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[afrr_DK1_2025] PASSED [ 29%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[mfrr_cap_DK1_2024_skudaar] PASSED [ 35%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[spot_DK1_2023_1h] PASSED [ 41%]
tests/test_coverage_guard.py::test_F_resolution_change_is_not_a_gap PASSED [ 47%]
tests/test_coverage_guard.py::test_G_balance_end_rule_is_gone PASSED     [ 52%]
tests/test_coverage_guard.py::test_G2_both_paths_cover_the_same_window PASSED [ 58%]
tests/test_coverage_guard.py::test_G3_read_dataset_refuses_a_date_string PASSED [ 64%]
tests/test_coverage_guard.py::test_G4_unknown_dataset_raises_instead_of_defaulting PASSED [ 70%]
tests/test_coverage_guard.py::test_H_15min_bucket_is_explicitly_unsupported PASSED [ 76%]
tests/test_coverage_guard_e2e.py::test_A2_read_dataset_rejects_partial_coverage PASSED [ 82%]
tests/test_coverage_guard_e2e.py::test_A2_documents_what_head_returns_instead SKIPPED [ 88%]
tests/test_coverage_guard_e2e.py::test_B2_read_dataset_rejects_missing_year_file PASSED [ 94%]
tests/test_coverage_guard_e2e.py::test_E2_read_dataset_accepts_full_coverage PASSED [100%]
======================== 16 passed, 1 skipped in 0.78s =========================
```

**Ingen xfail tilbage.** Ingen afvigelser fra forventningen.

Test G er omdøbt fra `test_G_balance_end_rule_truncates_last_hour` til
`test_G_balance_end_rule_is_gone` — den måler nu det modsatte og skal hedde
det. Den asserterer **11 520** kvarter (var 11 517), at ingen bucket er
underfyldt, og at `2026-04-30 23:00` har alle fire.

Tre nye tests:

- `G2` — regressionstest på den dobbelte end-regel: `spot/DK1` og
  `imbalance/DK1` læses over samme akse og skal dække samme interval. Begge
  slutter nu `2026-04-30 23:45` med 11 520 rækker. På den gamle kode adskilte
  de sig med 59:59.
- `G3` — `_read_dataset` afviser en datostreng med `TypeError`.
- `G4` — ukendt `folder` rejser `KeyError`.

`test_A2_documents_what_head_returns_instead` springes over som designet —
den dokumenterede kun HEAD's tavse adfærd og er dødvægt nu.

---

# 5. KØRSLEN — NY BASELINE

```
$ python run_case.py cases/billund_sporB_q1_2026.yaml \
      --data-source github --with-balancing --dmi-area karup
```

Ingen `--end` eller `--year` brugt. Aksen er casens egen:
`2026-01-01 00:00 .. 2026-04-30 23:00`, 2880 timer.

| felt | værdi |
|---|---|
| `solve_status` | **optimal** |
| `model_type` | MILP |
| `objektiv_dkk` | **15 733 150** |
| `balanceindtaegt_dkk.i_alt` (netto) | **3 128 655** |
| `balanceindtaegt_dkk.afrr` | **1 636 399** |
| `balanceindtaegt_dkk.mfrr` | **1 492 256** |
| `brutto.i_alt` | 3 539 135 |
| `brutto.afrr` | 1 909 790 |
| `brutto.mfrr` | 1 629 345 |
| varmebehov | 67 457,4 MWh |
| nettab | 23,9 % |

Produktionsfordeling: `vp_luft_vand` 26 726,6 MWh (39,2 %), `halmkedel`
19 217,2 (28,2 %), `fliskedel` 18 049,1 (26,5 %), `elkedel_gl` 4 102,1
(6,0 %), `gasmotor` 50,4 (0,1 %), `gaskedel_agg` 0.

## Dette er en NY BASELINE — ikke en sammenligning

Tallene må **ikke** holdes op mod `out/`. To uafhængige grunde:

1. **Faseforskydningen.** De syv gamle kørsler brugte DMI-filer hvor
   `hour_utc` bar lokal dansk tid (målt i Gate 1 §Trin 0, 99,93–100 % match
   efter tz-konvertering). Enhver før/efter måler både vagten og
   DMI-rettelsen på én gang.
2. **Andet vejrområde og anden varmekilde.** Denne kørsel bruger
   `--dmi-area karup`, mens `out/` brugte `fyn`. Og den kører **uden**
   `--heat-csv`, som de gamle kørsler brugte (`heatcsv` i deres stem), så
   varmesyntesen er aktiv her og suspenderet der. Tre variable er ændret
   samtidig.

Kørslen beviser at B4 er lukket og at kæden er grøn hele vejen til solveren.
Den er ikke et validt sammenligningsgrundlag for noget som helst, og
`objektiv_dkk` bør ikke citeres videre uden disse tre forbehold.

## `--dmi-area fyn` afvises stadig — korrekt, ikke en regression

```
  File "/opt/fjernvarme-businesscase/src/data_loader_github.py", line 274, in _read_dataset
    assert_coverage(
  File "/opt/fjernvarme-businesscase/src/data_loader.py", line 184, in assert_coverage
    raise CoverageError(
src.data_loader.CoverageError: dmi/fyn: dækning mangler for den ønskede periode.
  Ønsket:  2026-01-01 00:00:00 → 2026-04-30 23:00:00 (2880 buckets à 1h, min 1 obs/bucket)
  Målt:    2849 observationer, 2026-01-01 02:00:00 → 2026-04-30 23:00:00
  Mangler: 31/2880 buckets uden observationer (98.9% dækning)
  Første:  2026-01-01 00:00, 2026-01-01 01:00, 2026-02-28 11:00
  Sidste:  2026-03-01 13:00, 2026-03-01 14:00, 2026-03-01 15:00
  Data er ikke fyldt eller korrigeret — kørslen er stoppet før nul-fyldning. Kontrollér at df-data dækker perioden, eller indskrænk cfg.time.
```

De 31 timer er dem Gate 0.5 §C3 målte og Gate 1 §Trin 0 beviste blev
interpoleret tavst i de gamle kørsler. Vagten gør præcis hvad den skal.
Blokeringen ophører når F8 er løst — ikke ved at bløde vagten op.

Nedadgående afrunding verificeret på et andet tilfælde:

```
### dmi/fyn 2024 = 8783/8784
  Mangler: 1/8784 buckets uden observationer (99.9% dækning)
```

---

# 6. MÅLT vs. USIKKERT

## MÅLT

- Syv kaldesteder bekræftet (linjenumre drevet +38 siden Gate 0 pga. Gate 2).
- `_read_dataset` kaldes ikke fra andre moduler end
  `src/data_loader_github.py` og `tests/`.
- 16 passed, 1 skipped, 0 xfail.
- `imbalance/DK1` over q1-2026-aksen giver nu **11 520** kvarter mod 11 517 før.
- `spot` og `imbalance` slutter begge `2026-04-30 23:45` over samme akse.
- Kørslens tal, `solve_status=optimal`.
- `--dmi-area fyn` afvises fortsat med 31 manglende buckets.
- 99,9 % ved 8783/8784.
- `git status`: kun `src/data_loader.py` og `src/data_loader_github.py`
  ændret. `run_case.py`, `model.py`, `balancing.py`, `reporting.py` urørte.

## USIKKERT

1. **Tolerance-spørgsmålet fra Gate 2 er stadig uafklaret.** Denne gate
   flyttede ikke på det. `--dmi-area fyn` og alle helårskørsler over et
   oktober-DST-skift er fortsat blokeret. Det er F8.
2. **`_axis_step` bruger `idx.freq.nanos`.** Det virker for Tick-offsets
   (`h`, `15min`), som er alt `make_time_index` producerer. En akse med en
   ikke-Tick-freq (fx månedsslut) ville rejse `AttributeError` frem for en
   læsbar besked. Ikke relevant i dag; ikke testet.
3. **`hourly.csv` har 2 879 rækker mod aksens 2 880.** I Gate 1 var
   afvigelsen −24; nu −1. Ligger i `reporting.py`, som er uden for gatens
   afgrænsning. Ændringen i afvigelsens størrelse er ikke undersøgt og bør
   være det, før tallene bruges til noget.
4. **Kørslen brugte ikke `--heat-csv`.** Kommandolinjen i opgaven havde det
   ikke med. Varmesyntesen er derfor aktiv, hvilket gør tallene
   usammenlignelige med de gamle kørsler ud over faseforskydningen.
5. **`_read_dataset`s `_axis_step` kaldes før filerne læses**, så en
   uregelmæssig akse rejser før `FileNotFoundError`. Rækkefølgen af de to
   fejltyper er ikke bevidst valgt.

---

# 7. STADIG URØRT

| område | status |
|---|---|
| **F8 — tolerance/DMI-huller** | Blokerer `--dmi-area fyn` og alle kørsler over oktober-DST. Skal afgøres: generel tolerance à la `apply_heat_csv_override` (≤5 % → interpolér), pr-datasæt-tolerance (temperatur må interpoleres, markedspriser må ikke), eller ret hullerne i df-data. |
| **`--external`-vejen** | `_api_get` og `_eds_get` har ingen dækningsvagt. `fetch_balance_prices` i `data_loader.py` har stadig `merged.fillna(0.0)` og `reindex(fill_value=0.0)` uden vagt. Gate 0 udpegede dem som to selvstændige sæder. |
| **`_attach_unit_profiles`** | Fylder stadig 0.0 ubetinget. Rammer begge loadere. Gate 0's fjerde sæde. |
| **`write_manifest`** | Registrerer ikke `df_data_commit` og intet dækningsfelt. Uden `df_data_commit` er ethvert dækningsudsagn uverificerbart bagudrettet (Gate 0.5 §C4). |
| **CLI-defekten i `_apply_time_override`** | `--year 2025` giver en akse der slutter 2025-12-31 00:00 — 23 timer kortere end kalenderåret (Gate 0.5 §B3). Vagten måler nu trofast mod den forkortede akse og vil ikke opdage det. |
| **Genkørsel af `out/`** | De syv kørsler er faseforskudte og kan ikke bruges som baseline. Kan først ske efter F8. |
