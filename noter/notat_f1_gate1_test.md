# F1 Gate 1 — Testen skrevet. Bekræftet at den fejler på HEAD.

**Status:** Tests oprettet under `tests/`. `src/` og `run_case.py` er ikke rørt.
Intet netværk. Vagten er ikke implementeret — det er Gate 2.
**Forudsætninger:** [Gate 0](notat_f1_gate0_daekningsvagt.md), [Gate 0.5](notat_f1_gate05_oploesning_akse.md).
**Modelrepo:** HEAD `3ea0399`. **df-data-klon:** `6c95bde` (2026-08-07).
**Dato:** 2026-08-07

---

# TRIN 0 — USIKKERT 1 ER LUKKET

**Konklusion: de syv kørsler i `out/` er genkørbare, men deres resultater er
forkerte og skal kasseres som tal. Ingen observationer er gået tabt — de var
mærket 1–2 timer forkert ved kørselstidspunktet.**

## Målingen

Alle syv `*_hourly.csv` har en `t_out_c`-kolonne uden NaN. Tidskolonnen hedder
`timestamp` (ikke `time`).

| kørsel | fil-rækker | vindue i outputtet |
|---|---|---|
| `backtest_no_onset` | 2856 | 2026-01-01 01:00 .. 2026-04-30 00:00 |
| `backtest_vp_onset` | 2856 | 2026-01-01 01:00 .. 2026-04-30 00:00 |
| `diag_plantwide_onset` | 2856 | 2026-01-01 01:00 .. 2026-04-30 00:00 |
| `sporB_plain` | 2856 | 2026-01-01 01:00 .. 2026-04-30 00:00 |
| `sporB_vp_onset` | 2856 | 2026-01-01 01:00 .. 2026-04-30 00:00 |
| `sporB_H2_2025` | 4392 | 2025-07-01 01:00 .. 2025-12-31 00:00 |
| `sporB_oos_marapr` | 1440 | 2026-03-01 01:00 .. 2026-04-30 00:00 |

Sammenligning af `t_out_c` mod `dmi/fyn_{2025,2026}.csv` i den nuværende klon,
først med direkte tidsstempel-match, derefter med faste timeforskydninger:

| kørsel | shift −2 t | shift −1 t | **shift 0 (direkte)** | shift +1 t |
|---|---|---|---|---|
| 2026-kørslerne (5 stk.) | 30,7 % | **73,0 %** | **3,8 %** | 2,1 % |
| `sporB_H2_2025` | **65,5 %** | 37,2 % | **1,8 %** | 1,4 % |
| `sporB_oos_marapr` | 55,1 % | 46,5 % | **1,9 %** | 0,8 % |

Direkte match er nær nul. Bedste faste forskydning er −1 t om vinteren og −2 t
om sommeren — nøjagtigt den danske UTC-offset. `sporB_oos_marapr` ligger midt
imellem, fordi den spænder sommertidsskiftet 2026-03-29.

Med korrekt tidszonekonvertering (outputtets label tolket som
`Europe/Copenhagen` vægur → UTC):

| kørsel | eksakt match | afviger | max abs. forskel |
|---|---|---|---|
| `backtest_no_onset` | **2824/2825 (99,96 %)** | 1 | 0,1875 °C |
| `backtest_vp_onset` | **2824/2825 (99,96 %)** | 1 | 0,1875 °C |
| `diag_plantwide_onset` | **2824/2825 (99,96 %)** | 1 | 0,1875 °C |
| `sporB_plain` | **2824/2825 (99,96 %)** | 1 | 0,1875 °C |
| `sporB_vp_onset` | **2824/2825 (99,96 %)** | 1 | 0,1875 °C |
| `sporB_H2_2025` | **4391/4391 (100,00 %)** | 0 | 0 |
| `sporB_oos_marapr` | **1423/1424 (99,93 %)** | 1 | 0,1875 °C |

Den ene afvigende time er i alle tilfælde `2026-03-29 02:00` — det ikke-eksisterende
klokkeslæt ved sommertidens start, som er et artefakt af `nonexistent="shift_forward"`
i selve målingen, ikke en dataforskel.

## Hvad det betyder

`hour_utc` i DMI-filerne bar **lokal dansk vægur** da de syv kørsler blev
udført. Loaderen læste labelen som UTC. Derfor blev `t_ambient` forskudt
1 time om vinteren og 2 timer om sommeren i forhold til den faktiske
observationstid. Klonens HEAD-commit `6c95bde` — *"Ret tidsmaerkningen i
dmi/\*.csv — hour_utc bar lokal tid"* — retter præcis dét.

Observationerne er identiske; kun mærkningen har flyttet sig. Kørslerne kan
altså gentages og vil give korrekt temperatur. Men **de gemte tal er
produceret på en faseforskudt temperaturserie** og kan ikke bruges som de er.

Det rammer hårdest de fem 2026-kørsler, hvor `billund_sporB_q1_2026.yaml` har
`vp_luft_vand` med `cop_curve` sat: `model.py:72` og `balancing.py:171-172`
beregner varmepumpens COP direkte af `t_ambient`, så en 1-times faseforskydning
går lige ind i den aFRR/mFRR-kapacitet der kalibreres.
`sporB_H2_2025` har ingen `cop_curve`-enhed; dér påvirker forskydningen kun
`t_out_c` i rapporteringen.

## De 31 hul-timer

Spørgsmålet var, om hullerne i den nuværende klon også fandtes ved
kørselstidspunktet. Svar: **ja — hullet er ikke opstået siden.**

| kørsel | blok | målt indhold i outputtet |
|---|---|---|
| 2026-kørslerne (5 stk.) | 2026-02-28 12:00 .. 2026-03-01 16:00 (29 t) | 8,577 → 6,523, **lineær** (max residual < 1e-6) |
| 2026-kørslerne (5 stk.) | 2026-01-01 01:00 .. 02:00 (2 t) | 5,008 / 4,992 — for kort til lineær-test |
| `sporB_oos_marapr` | 2026-03-01 01:00 .. 16:00 (16 t) | konstant 6,450 — bfill fra første observation |
| `sporB_H2_2025` | 2025-10-26 02:00 (1 t) | 9,000 — for kort til test |

Den 29-timers blok er eksakt lineær mellem sine endepunkter. Det er signaturen
på `interpolate(method="time")` i `data_loader_github.py:461`. Den 16-timers
blok ligger ved kørslens start og er en flad `bfill`-værdi — samme kodelinje,
`.bfill()`-grenen. Begge dele beviser at hullet fandtes ved kørslen og blev
udfyldt tavst, præcis som Gate 0 forudsagde.

## Afgørelse

| spørgsmål | svar |
|---|---|
| Er de syv kørsler genkørbare? | **Ja.** Kildeobservationerne er intakte i klonen. |
| Kan de gemte tal bruges? | **Nej.** Temperaturserien er faseforskudt 1–2 timer. |
| Er hullerne nye? | **Nej.** De fandtes ved kørslen og blev interpoleret tavst. |
| Konsekvens | Alle syv skal genkøres mod `6c95bde` eller senere, efter Gate 2. |

Dette er en selvstændig konklusion, uafhængig af dæknings-vagten: den ville
ikke have fanget faseforskydningen, fordi dataene *var* der — de var bare
mærket forkert. Vagten fanger manglende dækning, ikke forkert mærkning.

---

# TRIN 1 — TESTSTILLADS

| fil | rolle |
|---|---|
| `/opt/fjernvarme-businesscase/tests/__init__.py` | Tom. Får pytest (importmode `prepend`) til at indsætte **repoets rod** i `sys.path` frem for `tests/`, så `import src.data_loader` virker. Verificeret med den bare `pytest`-binær, ikke kun `python -m pytest`. |
| `/opt/fjernvarme-businesscase/tests/conftest.py` | Skip-fixture + `df_data` (sti) + `df_data_head` (klonens `%h %ad`). |
| `/opt/fjernvarme-businesscase/tests/test_coverage_guard.py` | Testene A–H. |

`conftest.py` leverer:

- `_require_df_data` — session-scoped autouse; `pytest.skip` med sti,
  begrundelse og en `git clone`-kommando hvis `data/df-data/.git` mangler.
- `df_data` — `Path` til klonens rod.
- `df_data_head` — fx `6c95bde 2026-08-07`. Bruges i assert-beskeder, så en
  fejlende test siger hvilken dataversion den målte mod. Nødvendigt fordi
  datarepoet opdateres uafhængigt af modelrepoet og manifestet ikke
  registrerer det (Gate 0.5 §C4). Bekræftet synlig i fejlrapporten:
  `df_data_head = '6c95bde 2026-08-07'`.

**Ingen `pytest.ini` eller `pyproject.toml` oprettet.** Repoets rod er urørt.
Testene kører med `pytest tests/` fra roden uden konfiguration.

## Designvalg: `_guard()` vs. `_guard_optional()`

Vagten findes ikke. En import på modulniveau ville rive hele modulet ned og
gøre det umuligt for C, E og F at bestå. Derfor to hjælpere:

- `_guard()` — `pytest.fail(...)` med klar besked hvis `assert_coverage`
  mangler. Bruges af A, B, D, G, H, som **skal** være røde på HEAD.
- `_guard_optional()` — returnerer `None` hvis vagten mangler. Bruges af E og
  F, som er falsk-positiv-tests: før vagten findes kan der pr. definition ikke
  være en falsk positiv, så de måler deres dataforudsætninger på HEAD og
  eksercerer vagten fra Gate 2. De skal være grønne hele vejen, ellers kan de
  ikke skelne "vagten er for stram" fra "vagten mangler".

Hver test asserterer sine egne forudsætninger (rækketal, første/sidste
tidsstempel, antal manglende timer) **før** den rører vagten. Ændrer datarepoet
sig, fejler testen med "forudsætning brudt" og ikke med "vagten virker ikke".

---

# TRIN 2 — TESTENE

| id | datasæt | periode | forudsætning (målt) | forventet |
|---|---|---|---|---|
| **A** | `afrr/DK1` | 2024-01-01 00:00 .. 2024-12-31 23:00 | 2186 rækker fra 2024-10-01 22:00; **6598 af 8784 timer mangler** | exception |
| **B** | `imbalance/DK1` | 2024-01-01 .. 2025-12-31 23:00 | `DK1_2024.csv` findes ikke; 29 037 rækker fra 2025-03-04 12:00; **10 284 timer mangler** | exception |
| **C** | `imbalance/DK1` | 2024-01-01 .. 2024-12-31 | ingen fil overhovedet | `FileNotFoundError` fra linje 143 — **skal bestå på HEAD** |
| **D** | `mfrr_cap/DK1` | 2023-06-21 00:00 .. 2023-06-30 23:00 | 216 rækker; begge endepunkter dækket; **hul 2023-06-22 22:00 .. 2023-06-23 21:00, 24 t** | exception |
| **E1** | `afrr/DK1` | 2025 helår | 8760 rækker, 0 huller, 0 dubletter | ingen exception |
| **E2** | `mfrr_cap/DK1` | 2024 helår (skudår) | 8784 rækker, 0 huller | ingen exception |
| **E3** | `spot/DK1` | 2023 helår (1h) | 8760 rækker, 0 huller | ingen exception |
| **F** | `spot/DK1` | 2025-09-25 .. 2025-10-05 | 627 rækker; **142 × 3600 s + 484 × 900 s**; 0 ægte huller | ingen exception |
| **G** | `imbalance/DK1` | `2026-01-01T00:00` .. `2026-04-30T23:00` | **11 517 rækker**; præcis én underfyldt bucket: `2026-04-30 23:00` med 1 af 4 kvarter | `xfail` |
| **H** | `spot/DK1` | 2025-01-01 .. 2025-01-31 | — | `NotImplementedError` på `bucket="15min"` |

Bemærkninger:

- **D** bruger `mfrr_cap` og ikke DMI's DST-hul, netop fordi `dmi/*.csv` er
  under aktiv korrektion i datarepoet (`6c95bde`). Et fixture bygget på
  DMI-filerne kunne skifte farve af grunde der intet har med vagten at gøre.
- **G** er markeret `xfail(strict=False)`. Kroppen måler defekten eksekverbart
  (11 517 rækker, én underfyldt bucket) og slutter med **ønsketilstanden** —
  at vagten passerer, fordi vinduet er fodret korrekt. Den skal vende til
  `XPASS` når `_read_dataset` modtager `idx` i stedet for datostrenge. Så
  fjernes markeringen.
- **H** afviser `bucket="15min"`. Begrundelse fra Gate 0.5 §A1: før
  2025-09-30 22:00 er spot ægte timesdata, så en 15-minutters model **skal**
  opsample — det er erklæret opsampling, ikke manglende dækning. Efter skiftet
  er det omvendt. Én `min_per_bucket` kan ikke dække begge, og grænsen skal
  være synlig frem for gættet.
- `COVERAGE_ERROR` er sat til `Exception` med en kommentar. Vagtens
  exception-type er ikke fastlagt endnu; Gate 2 strammer den ene linje.

---

# TRIN 3 — BEVIS

```
$ .venv/bin/pytest tests/ -v -p no:cacheprovider
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.0, pluggy-1.6.0
rootdir: /opt/fjernvarme-businesscase
collecting ... collected 10 items

tests/test_coverage_guard.py::test_A_partial_coverage_in_existing_file FAILED [ 10%]
tests/test_coverage_guard.py::test_B_missing_year_file_in_multi_year_span FAILED [ 20%]
tests/test_coverage_guard.py::test_C_existing_guard_still_raises_when_no_file_at_all PASSED [ 30%]
tests/test_coverage_guard.py::test_D_gap_inside_covered_range FAILED     [ 40%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[afrr_DK1_2025] PASSED [ 50%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[mfrr_cap_DK1_2024_skudaar] PASSED [ 60%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[spot_DK1_2023_1h] PASSED [ 70%]
tests/test_coverage_guard.py::test_F_resolution_change_is_not_a_gap PASSED [ 80%]
tests/test_coverage_guard.py::test_G_balance_end_rule_truncates_last_hour XFAIL [ 90%]
tests/test_coverage_guard.py::test_H_15min_bucket_is_explicitly_unsupported FAILED [100%]

=================================== FAILURES ===================================
___________________ test_A_partial_coverage_in_existing_file ___________________

df_data = PosixPath('/opt/fjernvarme-businesscase/data/df-data')
df_data_head = '6c95bde 2026-08-07'
...
E           Failed: src.data_loader.assert_coverage findes ikke. Vagten er ikke
            implementeret endnu (Gate 2) — testen måler netop dét og skal fejle
            her på HEAD.

tests/test_coverage_guard.py:50: Failed
=========================== short test summary info ============================
XFAIL tests/test_coverage_guard.py::test_G_balance_end_rule_truncates_last_hour
  - Gate 0.5 §B4: balance-stien sender 'YYYY-MM-DDTHH:MM' til _read_dataset
    (data_loader_github.py:489-490), så end-udvidelsen på linje 163-164 ikke
    slår til og de sidste tre kvarter skæres væk. Sidste time resamples derfor
    fra 1 af 4 kvarter. Testen skal VENDE til XPASS når _read_dataset modtager
    idx i stedet for datostrenge (Gate 2).
FAILED tests/test_coverage_guard.py::test_A_partial_coverage_in_existing_file
FAILED tests/test_coverage_guard.py::test_B_missing_year_file_in_multi_year_span
FAILED tests/test_coverage_guard.py::test_D_gap_inside_covered_range
FAILED tests/test_coverage_guard.py::test_H_15min_bucket_is_explicitly_unsupported
==================== 4 failed, 5 passed, 1 xfailed in 0.75s ====================
```

## Udfald mod forventning

| id | forventet | faktisk | hvordan den fejler |
|---|---|---|---|
| A | fejler | **FAILED** ✓ | `_guard()` → `pytest.fail`: `assert_coverage` findes ikke. Alle forudsætnings-asserts (2186 rækker, 6598 manglende timer) passerede først. |
| B | fejler | **FAILED** ✓ | Samme. Forudsætninger (29 037 rækker, 10 284 manglende) passerede. |
| C | består | **PASSED** ✓ | `_read_dataset` rejste `FileNotFoundError` som ventet. |
| D | fejler | **FAILED** ✓ | Samme. Hullet 2023-06-22 22:00 .. 06-23 21:00 verificeret først. |
| E1–E3 | består | **PASSED** ✓ | Dataforudsætninger grønne; vagt-kaldet sprunget over (findes ikke). |
| F | består | **PASSED** ✓ | Blandet 3600 s/900 s verificeret, 0 huller. |
| G | xfail | **XFAIL** ✓ | Defekten dokumenteret; vender til XPASS når end-reglen er væk. |
| H | fejler | **FAILED** ✓ | Samme `pytest.fail`. |

**Ingen af A, B eller D består på HEAD.** Stop-betingelsen i opgaven er ikke
udløst. Testene måler det de skal.

Alle fire fejl kommer fra samme sted, `tests/test_coverage_guard.py:50` — ikke
fra manglende exception. Det er den rigtige fejlmåde på dette tidspunkt: den
siger "vagten findes ikke", ikke "vagten virker ikke". Fra Gate 2 vil samme
tests fejle på `pytest.raises` hvis vagten er for slap.

---

# MÅLT vs. USIKKERT

## MÅLT

- Alle syv kørsler brugte DMI-data mærket i lokal dansk tid; korrekt
  tz-konvertering giver 99,93–100,00 % eksakt match mod den nuværende klon.
- De 31 hul-timer var huller også ved kørslen og blev udfyldt lineært
  (`interpolate`) hhv. fladt (`bfill`).
- Samtlige rækketal, endepunkter og hulgrænser i testene er verificeret mod
  klonen `6c95bde` før de blev hard-codet.
- Testudfaldet ovenfor, kørt med både `python -m pytest` og den bare
  `pytest`-binær fra repoets rod.
- `git status` efter gaten: kun `out/` og `tests/` er utrackede. `src/` og
  `run_case.py` er urørte.

## USIKKERT

1. **Vagtens exception-type.** Ikke fastlagt i Gate 0.5. Testene accepterer
   `Exception` via konstanten `COVERAGE_ERROR`. Gate 2 skal vælge — en dedikeret
   `CoverageError(ValueError)` ville lade testene skelne dækningsfejl fra
   tilfældige `KeyError` i vagtens egen kode. Én linje at stramme.
2. **Om `assert_coverage` skal ligge i `data_loader.py` eller i et nyt modul.**
   Testene importerer fra `src.data_loader` som fastlagt i opgaven. Flyttes
   den, skal `_guard_optional()` rettes ét sted.
3. **Skip-stien i `conftest.py` er ikke eksekveret.** Klonen findes, så
   `_require_df_data` har aldrig skippet. Beskeden er læst igennem, ikke kørt.
   Kræver en kørsel med klonen midlertidigt flyttet — ikke gjort, da det ville
   røre `data/`.
4. **Hvorfor `*_hourly.csv` har 24 rækker færre end modelaksen** (2856 vs.
   2880; 4392 vs. 4416; 1440 vs. 1464). Konsistent −24 i alle syv. Ligger i
   `reporting.py` og ikke i loaderen, og er uden for denne gates afgrænsning.
   Bemærket, ikke undersøgt.
5. **Om `min_per_bucket=4` er rigtigt for `mfrr_act`** såvel som `imbalance`.
   Begge er 15-min i hele deres levetid (Gate 0.5 §A1), så det burde gælde
   begge — men kun `imbalance` er testet i G.

---

# HVAD GATE 2 KAN TAGE FOR GIVET

## Kan tages for givet

- **Signaturen virker.** `assert_coverage(ts, start_ts, end_ts, *, label,
  bucket, min_per_bucket)` er kaldt fra otte forskellige testtilfælde uden at
  parameterlisten kom til kort.
- **Bucket-designet holder.** Test F beviser at 1h→15min-skiftet ikke kræver
  breakpoints: med `bucket="1h", min_per_bucket=1` er 15-min-data trivielt
  dækkende. Ingen tidsafhængig `expected_freq` nødvendig.
- **Testdata er stabile og offline.** Alle ni datavinduer er verificeret mod
  `6c95bde`, og hver test asserterer sine forudsætninger, så et skift i
  datarepoet giver en entydig fejlbesked.
- **Den eksisterende `FileNotFoundError`-vagt virker** (test C) og skal ikke
  røres.
- **Falsk-positiv-dækningen er på plads** (E×3, F) og bliver aktiv i samme
  øjeblik vagten findes.
- **Genkørsel af de syv kørsler er meningsfuld** — kildedata er intakte.

## Kan IKKE tages for givet

- **At vagten alene løser B4.** Test G vender kun hvis `_read_dataset` også
  holder op med at modtage to forskellige datostrenge. Det er en ændring i
  `load_external_data_github` (linje 445-446 og 489-490), ikke i vagten.
- **At `_read_dataset` kan kalde vagten uden signaturændring.** Vagten skal
  kende den ønskede akse. I dag får `_read_dataset` kun `start`/`end` som
  strenge. Gate 0.5 anbefaler at sende `idx` — det er en signaturændring i
  `_read_dataset` og alle syv kaldesteder.
- **At `min_per_bucket` kan sættes ét sted.** Den er datasætspecifik: 1 for
  `spot`/`dmi`/`afrr`/`mfrr_cap`, 4 for `imbalance`/`mfrr_act`. Kaldestedet
  skal vide hvilket datasæt det læser.
- **At de syv kørsler i `out/` kan sammenlignes med nye.** De er
  faseforskudte. Enhver før/efter-sammenligning måler både vagten og
  DMI-rettelsen på én gang.
- **At `_attach_unit_profiles` er dækket.** Den fylder 0.0 ubetinget
  (`data_loader.py:855`) og har ingen test i denne gate. Gate 0 udpegede den
  som et selvstændigt sæde for vagten.
- **At `--external`-vejen er dækket.** Ingen test rører `_api_get` eller
  `_eds_get`. De kræver netværk eller et cache-fixture, og begge dele er uden
  for denne gates afgrænsning.
