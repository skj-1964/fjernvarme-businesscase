# F1b + F1c — CLI-aksen og rapportens rækkeafvigelse

**Status:** F1b rettet (CLI-aksen dækker nu hele perioden). F1c undersøgt —
afvigelsen er **tilsigtet**, men den dokumenterede begrundelse var faktuelt
forkert og er rettet. 28 tests grønne.
**Forudsætninger:** [Gate 0](notat_f1_gate0_daekningsvagt.md), [Gate 0.5](notat_f1_gate05_oploesning_akse.md), [Gate 1](notat_f1_gate1_test.md), [Gate 2](notat_f1_gate2_implementering.md), [Gate 3](notat_f1_gate3_akse_ned.md).
**Modelrepo:** HEAD `3ea0399` + ikke-committede ændringer fra Gate 2, 3 og denne.
**df-data-klon:** `6c95bde` (2026-08-07).
**Dato:** 2026-08-07

**Hovedfund:** F1c er ikke en rapportfejl. Rapporten skjuler med rette en time
som optimeringen ikke skulle have haft. Den underliggende defekt ligger i
`model.py` og er ikke lukket her. Se §1c og §6.

---

# 1. TRIN 0 — DE NI PUNKTER

## F1c

### (a) Hvor hourly.csv skrives

`src/reporting.py:289-465`, funktionen `write_hourly_csv`. Rækkerne dannes
af modelaksen direkte:

```python
317:    t = data.time.values
318:    dt_delta = pd.to_timedelta(data.time.diff("time").mean().values)
319:    dt = dt_delta.total_seconds() / 3600.0
320:    df = pd.DataFrame(index=pd.Index(t, name="timestamp"))
```

Indekset er altså `data.time` uændret — N rækker på dette tidspunkt.

### (b) Hvilken time mangler — den FØRSTE

Målt mod Gate 3's kørsel (`billund_sporB_q1_2026`, karup):

```
akse  : n=2880 [2026-01-01 00:00:00 .. 2026-04-30 23:00:00]
hourly: n=2879 [2026-01-01 01:00:00 .. 2026-04-30 23:00:00]
manglende: [Timestamp('2026-01-01 00:00:00')]
```

Den sidste time er intakt. Det er `2026-01-01 00:00` der mangler.

### (c) Årsagen — en slicing, ikke et resample

```python
459:    # Drop første time — boundary condition
460:    df = df.iloc[1:]
```

Ét enkelt `iloc[1:]`. Ingen `resample`, intet `diff`/`shift`, intet `dropna`.
Det er den eneste `iloc`/`isel`/slicing i hele `reporting.py` — verificeret
ved grep.

Droppet er **tilsigtet** og stod allerede i docstringen (linje 314-315 før
ændring):

> *"Første time droppes — den er en boundary condition (storage_energy[0] er
> start-værdi, ikke resultat af dispatch, så heat_prod[0] = 0)."*

**Men begrundelsen er målt forkert.** I samme kørsel:

| enhed | `heat_prod[0]` | `heat_prod[1]` |
|---|---|---|
| vp_luft_vand | 0,0000 | 16,0000 |
| fliskedel | **2,5000** | 6,2923 |
| halmkedel | **4,0000** | 4,0000 |
| øvrige | 0,0000 | 0,0000 |
| **sum** | **6,5000** | 26,29 |

`heat_prod[0]` er ikke 0. Den er 6,5 MW.

**Den rigtige begrundelse er lagerdynamikken.** `src/model.py:231-246`:

```python
231:        e_prev = storage_energy.shift(time=1)
232:        dyn = storage_energy - (1 - delta) * e_prev - charge + discharge
233:        m.add_constraints(
234:            dyn.sel(time=time_coord[1:]) == 0,
235:            name="storage_dynamics",
236:        )
...
243:        m.add_constraints(
244:            storage_energy.sel(time=time_coord[0]) == e_init,
245:            name="storage_initial",
246:        )
```

Energibalancen bindes kun fra `time_coord[1:]`. Ved `t=0` er
`storage_energy[0]` pinnet til `e_initial`, mens `charge[0]`/`discharge[0]`
ikke indgår i nogen balance. Lageret kan altså aflade uden at blive tømt.
Målt:

```
storage_energy[0] = 279.0   (= e_initial, uændret)
storage_net[0]    = -13.098 MW   (afladning)
storage_energy[1] = 285.614 = 279.0 + storage_net[1]
```

13,098 MWh gratis varme i time 0. Timen er ikke en fysisk
dispatch-beslutning, og droppet fra rapporten er derfor **berettiget**.

### (d) Rammer afvigelsen andet end hourly.csv? — NEJ

| output | rækker/timer |
|---|---|
| `dispatch.nc` | **2880** `[2026-01-01 00:00 .. 2026-04-30 23:00]` |
| `hourly.csv` | 2879 |
| manifestets `varmeefterspoergsel_mwh` | 67 457,4 — beregnet på **2880** |
| `objektiv_dkk`, `balanceindtaegt` | beregnet på **2880** |

Kun `hourly.csv` er afkortet. Alt andet — inklusive objektivet og alle
nøgletal — regner på hele aksen.

**Det er selve fundet.** Optimeringen udnytter t=0's gratis afladning og
tæller den med i objektivet; rapporten skjuler timen. Rapporten og
optimeringen er uenige, men rapporten er den der har ret.

### (e) Var Gate 1's −24 samme mekanisme? — NEJ, det var to

Målt på alle syv gamle kørsler:

| kørsel | n | interval |
|---|---|---|
| `backtest_no_onset` m.fl. (5 stk.) | 2856 | 2026-01-01 01:00 .. **2026-04-30 00:00** |
| `sporB_H2_2025` | 4392 | 2025-07-01 01:00 .. **2025-12-31 00:00** |
| `sporB_oos_marapr` | 1440 | 2026-03-01 01:00 .. **2026-04-30 00:00** |

Alle starter på `idx[1]` — samme `iloc[1:]`, −1. Men alle **slutter på 00:00**
i stedet for 23:00, altså −23 i den anden ende.

−24 = −1 (F1c, `iloc[1:]`) **+** −23 (F1b, CLI-aksen).

De syv gamle kørsler brugte altså `--year` eller `--start/--end`, ikke
YAML-perioden. Det er samme defekt som F1b, målt fra den anden side. De to
gates er dermed forbundet: Gate 1's uforklarede −24 er nu fuldt forklaret.

## F1b

### (f) `_apply_time_override` ordret (før ændring, linje 391-431)

```python
391: def _apply_time_override(cfg, year: int | None,
392:                          start: str | None, end: str | None) -> None:
...
413:     if year is not None:
414:         cfg.time.start = f"{year}-01-01"
415:         cfg.time.end = f"{year}-12-31"
416:         print(f"  Override: analyseperiode = {year}-01-01..{year}-12-31")
417:         return
418:
419:     if start is not None and end is not None:
420:         # Sanity: parse datoer og tjek rækkefølge
421:         start_ts = pd.Timestamp(start)
422:         end_ts = pd.Timestamp(end)
423:         if end_ts <= start_ts:
424:             raise ValueError(f"--end ({end}) skal være efter --start ({start}).")
425:         cfg.time.start = start
426:         cfg.time.end = end
427:         print(f"  Override: analyseperiode = {start}..{end}")
428:         return
```

Begge grene skriver en **bar datostreng**. `--year` konstruerer den;
`--start/--end` videresender brugerens streng råt.

### (g) Flag og formater

| flag | type | dokumenteret format | faktisk accepteret |
|---|---|---|---|
| `--year` | `int` (linje 137) | `YYYY` | kun heltal |
| `--start` | `str` (linje 140) | `YYYY-MM-DD` | **alt `pd.Timestamp` kan parse** |
| `--end` | `str` (linje 144) | `YYYY-MM-DD` | **alt `pd.Timestamp` kan parse** |

Hjælpeteksten siger `YYYY-MM-DD`, men der er ingen formatvalidering.

### (h) `--end 2025-06-15T12:00` — respekteres allerede i dag

Målt før ændring:

```
--end 2025-06-15T12:00 -> cfg.time.end='2025-06-15T12:00'  idx.max()=2025-06-15 12:00:00  n=349
```

Klokkeslættet **trunkeres ikke**. Strengen sendes uændret videre og
`pd.date_range` respekterer den. Det virkede altså allerede, og rettelsen må
ikke tage det med sig — derfor en eksplicit test.

### (i) Hvem læser `cfg.time.start/end` ud over `make_time_index`?

| sted | brug |
|---|---|
| `src/data_loader.py:62` | `make_time_index` — `pd.date_range(start, end, freq)` |
| `src/data_loader.py:1078-1079` | **`--external`-vejen** formaterer stadig `strftime("%Y-%m-%dT%H:%M")` til `fetch_balance_prices` |
| `src/manifest.py:191-192` | `_date10()` — trunkerer til `YYYY-MM-DD` |
| `run_case.py:254-255` | `_build_output_stem` — `pd.Timestamp(cfg.time.start/end)` |
| `scripts/capture_rate.py:67-68` | sætter `f"{args.start}T00:00:00Z"` / `f"{args.end}T23:00:00Z"` |
| `scripts/capture_rate_q1_2026.py:74-75` | samme mønster |
| `scripts/calibrate_gate.py:68-69` | samme mønster |
| `scripts/calibrate_heat_load.py:90-91` | sætter råt uden klokkeslæt |

**De tre capture-/gate-scripts gjorde allerede det rigtige** — de skriver
`T23:00:00Z` eksplicit. Det er præcis mønsteret F1b indfører i CLI'en.

### Rækkefølge: kender overriden opløsningen?

**Ja.** `run_case.py:505` kalder `load_case`, `run_case.py:517` kalder
`_apply_time_override`. Verificeret:

```
cfg.time type: TimeHorizon | resolution kendt ved override: '1h'
```

`cfg.time.resolution` er sat af `load_case` (config.py:501) før overriden
kaldes. Ingen omorganisering nødvendig.

---

# 2. DIFF-OVERSIGT

```
 run_case.py               |  81 +++++++++++++---
 src/data_loader.py        | 135 +++++++++++++++++++++++++++
 src/data_loader_github.py | 228 ++++++++++++++++++++++++++++++++++------------
 src/reporting.py          |  30 +++++-
 4 files changed, 398 insertions(+), 76 deletions(-)
```

(`data_loader*.py` er kumulativt fra Gate 2+3 — urørt i denne gate.)

## `run_case.py` — F1b

| ændring | indhold |
|---|---|
| **ny** `_RESOLUTION_STEP` | `{"1h": 1h, "15min": 15min}` — samme nøgler som `make_time_index` |
| **ny** `_resolution_step(cfg)` | Læser `cfg.time.resolution`; rejser `ValueError` på ukendt værdi frem for at gætte |
| **ny** `_end_of_day(day, step)` | `day + 1 døgn − step` → 23:00 ved 1h, 23:45 ved 15min |
| `_apply_time_override` | Sætter nu `cfg.time.start/end` til **fulde ISO-timestamps**. `--year` → hele kalenderåret. `--start/--end` → bar dato i `end` udvides til dagens sidste skridt; eksplicit klokkeslæt respekteres. Print viser nu opløsningen. |

## `src/reporting.py` — F1c

| ændring | indhold |
|---|---|
| `write_hourly_csv` docstring | Rækkekontrakten (N−1) gjort eksplicit; den forkerte begrundelse (`heat_prod[0] = 0`) erstattet af den målte (ubunden lagerbalance ved t=0, `model.py:234`), med tal; advarsel om at objektivet regner på alle N timer |
| linje 459-462 | Kommentaren ved `iloc[1:]` peger nu på lagerbalancen, ikke produktionen |

**Ingen adfærdsændring i `reporting.py`.** Kun docstring og kommentar.

## Om bar dato vs. eksplicit klokkeslæt

`_apply_time_override` indfører en fortolkningsregel: `":" not in end` ⇒ bar
dato ⇒ udvid til dagens sidste skridt. Det ligner den regel Gate 3 slettede
fra `_read_dataset`, og forskellen er værd at holde fast i:

| | slettet regel (`_read_dataset`) | ny regel (`_apply_time_override`) |
|---|---|---|
| hvad blev fortolket | en allerede afledt værdi | brugerens rå input |
| fandtes en bedre kilde | **ja** — aksen | **nej** — der er intet mere autoritativt end det brugeren skrev |
| hvor mange gange | to, på to kaldeveje, **inkonsistent** | én, på CLI-grænsen |
| hvad løber nedstrøms | to forskellige strenge | ét fuldt timestamp |

Gætteriet er ikke genindført; det er flyttet til det eneste sted hvor
tvetydigheden faktisk opstår, og løst én gang.

---

# 3. PYTEST — ORDRET

```
$ .venv/bin/pytest tests/ -v -p no:cacheprovider
tests/test_coverage_guard.py::test_A_partial_coverage_in_existing_file PASSED [  3%]
tests/test_coverage_guard.py::test_B_missing_year_file_in_multi_year_span PASSED [  6%]
tests/test_coverage_guard.py::test_C_existing_guard_still_raises_when_no_file_at_all PASSED [ 10%]
tests/test_coverage_guard.py::test_D_gap_inside_covered_range PASSED     [ 13%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[afrr_DK1_2025] PASSED [ 17%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[mfrr_cap_DK1_2024_skudaar] PASSED [ 20%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[spot_DK1_2023_1h] PASSED [ 24%]
tests/test_coverage_guard.py::test_F_resolution_change_is_not_a_gap PASSED [ 27%]
tests/test_coverage_guard.py::test_G_balance_end_rule_is_gone PASSED     [ 31%]
tests/test_coverage_guard.py::test_G2_both_paths_cover_the_same_window PASSED [ 34%]
tests/test_coverage_guard.py::test_G3_read_dataset_refuses_a_date_string PASSED [ 37%]
tests/test_coverage_guard.py::test_G4_unknown_dataset_raises_instead_of_defaulting PASSED [ 41%]
tests/test_coverage_guard.py::test_H_15min_bucket_is_explicitly_unsupported PASSED [ 44%]
tests/test_coverage_guard_e2e.py::test_A2_read_dataset_rejects_partial_coverage PASSED [ 48%]
tests/test_coverage_guard_e2e.py::test_A2_documents_what_head_returns_instead SKIPPED [ 51%]
tests/test_coverage_guard_e2e.py::test_B2_read_dataset_rejects_missing_year_file PASSED [ 55%]
tests/test_coverage_guard_e2e.py::test_E2_read_dataset_accepts_full_coverage PASSED [ 58%]
tests/test_time_axis.py::test_year_override_covers_whole_calendar_year[year2025_1h] PASSED [ 62%]
tests/test_time_axis.py::test_year_override_covers_whole_calendar_year[year2025_15min] PASSED [ 65%]
tests/test_time_axis.py::test_year_override_covers_whole_calendar_year[year2026_1h] PASSED [ 68%]
tests/test_time_axis.py::test_year_override_covers_whole_calendar_year[year2026_15min] PASSED [ 72%]
tests/test_time_axis.py::test_start_end_override_matches_year_override[startend2025_1h] PASSED [ 75%]
tests/test_time_axis.py::test_start_end_override_matches_year_override[startend2025_15min] PASSED [ 79%]
tests/test_time_axis.py::test_explicit_time_on_end_is_respected PASSED   [ 82%]
tests/test_time_axis.py::test_explicit_midnight_is_respected_too PASSED  [ 86%]
tests/test_time_axis.py::test_no_override_leaves_yaml_untouched PASSED   [ 89%]
tests/test_time_axis.py::test_resolution_is_read_from_cfg_not_assumed PASSED [ 93%]
tests/test_time_axis.py::test_end_before_start_still_rejected PASSED     [ 96%]
tests/test_time_axis.py::test_hourly_csv_contract_is_n_minus_one PASSED  [100%]
======================== 28 passed, 1 skipped in 1.28s =========================
```

Ingen afvigelser. 11 nye tests i `tests/test_time_axis.py`, som hverken rører
df-data eller netværket.

## Om den test Trin 1 bad om

Trin 1 bad om en test der asserterer at `hourly.csv` har **N** rækker og at
første tidsstempel matcher `idx.min()`. Den test er **ikke** skrevet, fordi
målingen viser at N−1 er korrekt: t=0 er en ubunden lagertime. Trin 1's
alternativ — *"hvis afvigelsen viser sig at være tilsigtet, så sig det, ret
intet, og dokumentér det i docstringen"* — er den gren der er fulgt.

I stedet pinner `test_hourly_csv_contract_is_n_minus_one` den faktiske
kontrakt: N−1 rækker, første række = `idx[1]`, sidste = `idx[-1]`, og `idx[0]`
fraværende. Droppet kan dermed ikke stilfærdigt blive til nul eller to rækker.
Skal kontrakten laves om, kræver det at nogen tager stilling til
`model.py:234` først.

---

# 4. DE TRE KØRSLER

## 4.1 Gate 3's kørsel, uændret kommandolinje

```
python run_case.py cases/billund_sporB_q1_2026.yaml \
    --data-source github --with-balancing --dmi-area karup
```

| felt | Gate 3 | nu | ændring |
|---|---|---|---|
| `solve_status` | optimal | **optimal** | — |
| `objektiv_dkk` | 15 733 150 | **15 733 150** | **0** |
| `balanceindtaegt.i_alt` | 3 128 655 | **3 128 655** | 0 |
| `.afrr` | 1 636 399 | **1 636 399** | 0 |
| `.mfrr` | 1 492 256 | **1 492 256** | 0 |
| `hourly.csv` | 2 879 rækker | **2 879 rækker** | — |

**Objektivet er uændret til sidste krone.** Det er det ønskede: F1c rørte kun
docstring og kommentar, og F1b rammer ikke YAML-drevne kørsler, fordi alle
otte cases allerede skriver `23:00` eksplicit. Havde tallet flyttet sig,
havde det været et fund.

`hourly.csv` har fortsat 2 879 rækker `[2026-01-01 01:00 .. 2026-04-30 23:00]`
— nu som en dokumenteret og testet kontrakt frem for en uforklaret afvigelse.

## 4.2 `--year 2025` — aksen er nu 8760, og fejlen er DST-timen

```
  Override: analyseperiode = 2025-01-01T00:00:00..2025-12-31T23:00:00 (1h)
src.data_loader.CoverageError: dmi/fyn: dækning mangler for den ønskede periode.
  Ønsket:  2025-01-01 00:00:00 → 2025-12-31 23:00:00 (8760 buckets à 1h, min 1 obs/bucket)
  Målt:    8759 observationer, 2025-01-01 00:00:00 → 2025-12-31 23:00:00
  Mangler: 1/8760 buckets uden observationer (99.9% dækning)
  Første:  2025-10-26 00:00
  Sidste:  2025-10-26 00:00
  Data er ikke fyldt eller korrigeret — kørslen er stoppet før nul-fyldning. Kontrollér at df-data dækker perioden, eller indskrænk cfg.time.
```

**8760 buckets** — F1b er lukket (var 8737). Aksen slutter `2025-12-31 23:00`.

Den manglende bucket er **`2025-10-26 00:00`**, altså DST-tilbagestillingen —
netop den time Gate 0.5 §A-fund 1 målte mangler i alle DMI-årsfiler. Det er
F8, ikke aksen: `Målt` viser at data spænder hele `2025-01-01 00:00 →
2025-12-31 23:00`, kun med ét hul i midten.

## 4.3 `--year 2026` — vagten afviser, korrekt

```
  Override: analyseperiode = 2026-01-01T00:00:00..2026-12-31T23:00:00 (1h)
src.data_loader.CoverageError: dmi/karup: dækning mangler for den ønskede periode.
  Ønsket:  2026-01-01 00:00:00 → 2026-12-31 23:00:00 (8760 buckets à 1h, min 1 obs/bucket)
  Målt:    4294 observationer, 2026-01-01 00:00:00 → 2026-06-28 21:00:00
  Mangler: 4466/8760 buckets uden observationer (49.0% dækning)
  Første:  2026-06-28 22:00, 2026-06-28 23:00, 2026-06-29 00:00
  Sidste:  2026-12-31 21:00, 2026-12-31 22:00, 2026-12-31 23:00
  Data er ikke fyldt uden korrigeret — kørslen er stoppet før nul-fyldning.
```

**Dette ser ud som en regression og er det ikke.** Før F1b sluttede aksen
2026-12-31 00:00 og indeholdt de samme manglende måneder — vagten ville have
afvist den lige så meget. Forskellen er at aksen nu ærligt hedder 8760 timer.

df-data slutter `2026-06-28 21:00` for `dmi/karup` (målt i Gate 0.5 §A3).
Halvdelen af 2026 findes ikke endnu. Vagten siger det højt i stedet for at
nul-fylde. Det er præcis den adfærd F1 blev bygget for.

---

# 5. MÅLT vs. USIKKERT

## MÅLT

- Den manglende time i `hourly.csv` er den **første**, `2026-01-01 00:00`.
- Mekanismen er `df.iloc[1:]` på `reporting.py:459` — eneste slicing i filen.
- `heat_prod[0] = 6,5 MW`, ikke 0. Den gamle docstring var forkert.
- `storage_net[0] = −13,098` MW mens `storage_energy[0] = 279,0 = e_initial`
  uændret ⇒ 13,098 MWh gratis varme i t=0.
- `model.py:234` binder energibalancen fra `time_coord[1:]`.
- `dispatch.nc` og alle manifest-nøgletal regner på **2880** timer; kun
  `hourly.csv` er afkortet.
- Gate 1's −24 = −1 (`iloc[1:]`) + −23 (F1b). De syv gamle kørsler brugte
  CLI-override.
- `--end 2025-06-15T12:00` respekteredes allerede før rettelsen.
- `cfg.time.resolution` er kendt når `_apply_time_override` kaldes
  (`load_case` på linje 505, override på 517).
- Alle seks kombinationer fra Gate 0.5 §B2 giver nu de forventede længder.
- Objektivet uændret: 15 733 150 før og efter.
- `--year 2025` giver 8760 buckets; fejlen er DST-timen `2025-10-26 00:00`.
- `--year 2026` afvises med 4466 manglende buckets.

## USIKKERT

1. **Om t=0's gratis afladning bør lukkes i `model.py`.** Det er en reel
   defekt: optimeringen får 13,098 MWh varme uden modydelse og tæller den i
   objektivet. Størrelsen er lille (≈0,02 % af 67 457 MWh over q1-2026), men
   den er systematisk og findes i hver eneste kørsel. `model.py` er uden for
   denne gates afgrænsning. **Ikke lukket.**
2. **Om `":" not in end` er robust nok.** `--end 2025-12-31T00` (uden minutter)
   ville blive læst som bar dato og udvidet. Obskurt, men muligt. En
   strengere formatvalidering på CLI-grænsen ville lukke det.
3. **`--start` udvides ikke.** En bar startdato betyder midnat, hvilket er det
   rigtige — men asymmetrien mellem `--start` og `--end` er ikke testet for
   andet end de tilfælde ovenfor.
4. **`_build_output_stem` (run_case.py:254-255)** læser nu fulde timestamps
   frem for datostrenge. Filnavnene i §4 ser uændrede ud, men den fulde
   stem-logik er ikke gennemgået for kantetilfælde.
5. **`manifest.py:_date10` trunkerer stadig til `YYYY-MM-DD`.** Efter F1b
   findes klokkeslættet i `cfg.time`, men manifestet kaster det væk. Den
   information der netop blev gjort korrekt, registreres ikke.

---

# 6. ÉN PERIODEDEFINITION — ELLER FLERE?

**På github-vejen: én. På `--external`-vejen: stadig to.**

| lag | definition | status |
|---|---|---|
| CLI (`_apply_time_override`) | fulde ISO-timestamps, opløsningsafhængige | ✅ F1b |
| YAML (`cases/*.yaml`) | tz-aware datetimes med eksplicit klokkeslæt | ✅ var altid korrekt |
| akse (`make_time_index`) | `pd.date_range(start, end, freq)` | ✅ den bindende |
| loader github (`_read_dataset`) | modtager `idx`; vindue `[idx.min(), idx.max()+step)` | ✅ Gate 3 |
| vagt (`assert_coverage`) | buckets `[idx.min() .. idx.max()]` | ✅ Gate 2/3 |
| rapport (`write_hourly_csv`) | `[idx[1], idx[-1]]` — **bevidst N−1** | ✅ dokumenteret + testet |
| objektiv (`model.py`) | alle N timer, inkl. ubunden t=0 | ⚠️ **ikke afstemt** |
| **loader external** (`data_loader.py:1078-1079`) | `strftime("%Y-%m-%dT%H:%M")` → `fetch_balance_prices` | ❌ **den gamle defekt lever her** |
| manifest (`_date10`) | trunkeret til `YYYY-MM-DD` | ⚠️ taber klokkeslættet |

To reelle uafstemtheder tilbage:

1. **`--external`-vejen har stadig B4.** `src/data_loader.py:1078-1079`
   formaterer `cfg.time` til `"%Y-%m-%dT%H:%M"` og sender det til
   `fetch_balance_prices`, som ingen dækningsvagt har. Gate 3 lukkede kun
   github-vejen. Samme defekt, samme form, urørt.
2. **Objektivet og rapporten er uenige om t=0**, og rapporten har ret.
   Lukkes i `model.py`, ikke her.

## Stadig urørt fra tidligere gates

| område | status |
|---|---|
| **F8 — DMI-huller / tolerance** | Blokerer `--dmi-area fyn` og alle helårskørsler over oktober-DST. Uændret. |
| **`--external`-vejen** | `_api_get`, `_eds_get` uden vagt; `fetch_balance_prices` med `fillna(0.0)` og `reindex(fill_value=0.0)`; plus B4 ovenfor. |
| **`_attach_unit_profiles`** | Fylder stadig 0.0 ubetinget. Rammer begge loadere. |
| **`write_manifest`** | Intet `df_data_commit`, intet dækningsfelt, og nu også trunkeret periode. |
| **t=0's ubundne lagerbalance** | **Nyt fund i denne gate.** `model.py:234`. |
| **Genkørsel af `out/`** | De syv er både faseforskudte og aksefor kortede. Kan først ske efter F8. |
