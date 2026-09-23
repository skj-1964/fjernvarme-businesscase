# F1 Gate 2 — Vagten implementeret

**Status:** `assert_coverage` + `CoverageError` implementeret i `src/data_loader.py`
og kaldt fra `_read_dataset`. Alle 14 tests grønne. Fire kørsler afvist af vagten.
**Forudsætninger:** [Gate 0](notat_f1_gate0_daekningsvagt.md), [Gate 0.5](notat_f1_gate05_oploesning_akse.md), [Gate 1](notat_f1_gate1_test.md).
**Modelrepo før ændring:** HEAD `3ea0399`. **df-data-klon:** `6c95bde` (2026-08-07).
**Dato:** 2026-08-07

**Hovedfund:** Gate 2's præmis om at tre cases har "fuld dækning" er faktuelt
forkert. Ingen af dem har det. Se §5.

---

# 1. TRIN 1 — HULLET I GATE 1 ER LUKKET

Gate 1's A, B og D beviste at `assert_coverage` manglede. De beviste ikke at
loaderen opførte sig forkert — ingen af dem kaldte `_read_dataset`.
`tests/test_coverage_guard_e2e.py` lukker det.

Nøglen er `_coverage_error()`: så længe `CoverageError` ikke fandtes,
returnerede den en lokal sentinel-klasse som intet kan rejse. Dermed fejlede
`pytest.raises` på loaderens **adfærd** og ikke på et manglende navn.

## Ordret fejlmåde på HEAD, før implementering

```
________________ test_A2_read_dataset_rejects_partial_coverage _________________
>       with pytest.raises(_coverage_error()):
E       Failed: DID NOT RAISE _VagtenFindesIkkeEndnu
tests/test_coverage_guard_e2e.py:56: Failed

________________ test_B2_read_dataset_rejects_missing_year_file ________________
>       with pytest.raises(_coverage_error()):
E       Failed: DID NOT RAISE _VagtenFindesIkkeEndnu
tests/test_coverage_guard_e2e.py:94: Failed
----------------------------- Captured stdout call -----------------------------
    (imbalance/DK1: spring over DK1_2024.csv — ikke til stede i repo)

========================= 2 failed, 2 passed in 0.44s ==========================
```

`DID NOT RAISE` — præcis den krævede fejlmåde. Stop-betingelsen er ikke udløst.

B2's opsamlede stdout viser desuden print'et fra linje 148-153 isoleret: det
var alt hvad brugeren fik at vide om at et helt år manglede.

En fjerde test, `test_A2_documents_what_head_returns_instead`, verificerede at
HEAD returnerede 2186 ikke-tomme rækker startende 2024-10-01 22:00. Den
springes nu over med `pytest.skip("vagten findes nu")`, så den ikke bliver
dødvægt.

---

# 2. DIFF-OVERSIGT

```
 src/data_loader.py        | 130 ++++++++++++++++++++++++++++++++++++++++++++++
 src/data_loader_github.py |  57 +++++++++++++++++++-
 2 files changed, 186 insertions(+), 1 deletion(-)
```

Linjenumre verificeret ved HEAD `3ea0399` før ændring: `_read_dataset`s
`return` lå på **168** som ventet, print'et på **148-153**,
`FileNotFoundError` på **143**. Ingen drift denne gang.

| fil | placering | indhold |
|---|---|---|
| `src/data_loader.py` | efter `make_time_index`, ny sektion `+65..+194` | `class CoverageError(ValueError)`, `_BUCKET_FREQ = {"1h": "h"}`, `def assert_coverage(...)` |
| `src/data_loader_github.py` | `+49` | `assert_coverage` tilføjet til import-blokken fra `.data_loader` |
| `src/data_loader_github.py` | `+62..+84` | `_MIN_OBS_PER_HOUR`-tabel med målt begrundelse pr. datasæt |
| `src/data_loader_github.py` | `168 → +192..+206` | `return`-linjen delt: `out = df.loc[mask]...`, `assert_coverage(ts.loc[mask], ...)`, `return out` |
| `src/data_loader_github.py` | `+480..+496` | Resolution-vagt i `load_external_data_github` (Trin 4) |

`run_case.py`, `model.py`, `balancing.py`, `reporting.py` er urørte.
Print'et på 148-153 er bevaret uændret — det siger hvilken **fil** der
manglede, hvilket vagten ikke siger.

## Designvalg

**`min_per_bucket`-tabellen ligger hos kalderen**, ikke i `assert_coverage`.
Tabellen er en påstand om kildens native opløsning, og påstanden hører hos den
der ved hvilket datasæt der læses:

```python
_MIN_OBS_PER_HOUR = {
    "spot": 1, "dmi": 1, "afrr": 1, "mfrr_cap": 1,
    "imbalance": 4, "mfrr_act": 4,
}
```

`spot` får 1 selvom den skifter 3600 s → 900 s ved 2025-09-30 22:00: med
timesbuckets dækker 15-min-data trivielt hver time, så skiftet kræver ingen
breakpoints. Det er hele pointen i bucket-designet, og test F beviser det.

**Vagten kaldes på det maskerede `ts`** (`ts.loc[mask]`), ikke på den rå frame
— det er den mængde der faktisk går videre til reindeksering og nul-fyldning
på linje 402/405 og 460-463.

**Fejlbeskeden følger `apply_heat_csv_override:791-800`** og indeholder alle
fem krævede elementer: label, ønsket interval, målt first/last, antal
utilstrækkelige buckets, og første/sidste tre manglende buckets ved navn.
Tom `ts` har sin egen gren med en meningsfuld besked frem for `IndexError`.

---

# 3. PYTEST — ORDRET

```
$ .venv/bin/pytest tests/ -v -p no:cacheprovider -rxX
tests/test_coverage_guard.py::test_A_partial_coverage_in_existing_file PASSED [  7%]
tests/test_coverage_guard.py::test_B_missing_year_file_in_multi_year_span PASSED [ 14%]
tests/test_coverage_guard.py::test_C_existing_guard_still_raises_when_no_file_at_all PASSED [ 21%]
tests/test_coverage_guard.py::test_D_gap_inside_covered_range PASSED     [ 28%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[afrr_DK1_2025] PASSED [ 35%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[mfrr_cap_DK1_2024_skudaar] PASSED [ 42%]
tests/test_coverage_guard.py::test_E_full_coverage_does_not_raise[spot_DK1_2023_1h] PASSED [ 50%]
tests/test_coverage_guard.py::test_F_resolution_change_is_not_a_gap PASSED [ 57%]
tests/test_coverage_guard.py::test_G_balance_end_rule_truncates_last_hour XFAIL [ 64%]
tests/test_coverage_guard.py::test_H_15min_bucket_is_explicitly_unsupported PASSED [ 71%]
tests/test_coverage_guard_e2e.py::test_A2_read_dataset_rejects_partial_coverage PASSED [ 78%]
tests/test_coverage_guard_e2e.py::test_A2_documents_what_head_returns_instead SKIPPED [ 85%]
tests/test_coverage_guard_e2e.py::test_B2_read_dataset_rejects_missing_year_file PASSED [ 92%]
tests/test_coverage_guard_e2e.py::test_E2_read_dataset_accepts_full_coverage PASSED [100%]
=================== 12 passed, 1 skipped, 1 xfailed in 0.79s ===================
```

Udfaldet matcher forventningen præcis: A, B, D, H, A2, B2 består nu;
C, E×3, F, E2 består fortsat; G er stadig `XFAIL`. Ingen afvigelser.

**G er stadig xfail, og det er korrekt.** Den kræver at balance-stiens
end-regel forsvinder, altså at `_read_dataset` modtager `idx` i stedet for
datostrenge. Det er eksplicit Gate 3's arbejde, og Gate 2 måtte ikke røre
`load_external_data_github`s kaldesteder. Vagten fejrer korrekt på den ene
underfyldte bucket — verificeret direkte:

```
CoverageError: imbalance/DK1: dækning mangler for den ønskede periode.
  Ønsket:  2026-01-01 00:00:00 → 2026-04-30 23:00:00 (2880 buckets à 1h, min 4 obs/bucket)
  Målt:    11517 observationer, 2026-01-01 00:00:00 → 2026-04-30 23:00:00
  Mangler: 1/2880 buckets med under 4 observationer (100.0% dækning)
  Første:  2026-04-30 23:00
  Sidste:  2026-04-30 23:00
```

Bemærk `100.0%` — afrunding af 2879/2880. Underfyldte buckets tælles korrekt
(1), men procenten runder til 100,0. Kosmetisk; noteret under USIKKERT.

---

# 4. TRIN 4 — 15-MINUTTERS-GRÆNSEN

Grænsen er håndhævet **to steder**, fordi de to steder ved forskellige ting:

| sted | håndhæver | hvorfor dér |
|---|---|---|
| `assert_coverage` | `bucket != "1h"` → `NotImplementedError` | Vagten selv ved hvilke buckets den kan måle. Dækker test H. |
| `load_external_data_github`, `+480` | `cfg.time.resolution != "1h"` → `NotImplementedError` | `_read_dataset` kender ikke `cfg` og kan ikke se modellens opløsning. Dette er det snævreste sted hvor `cfg` ER tilgængelig, uden at ændre `_read_dataset`s signatur. |

Begge beskeder forklarer hvorfor: før 2025-09-30 22:00 er spot ægte timesdata,
så en 15-minutters model **skal** opsample — erklæret opsampling, ikke
manglende dækning. Efter skiftet ville en manglende kvartersrække være et ægte
hul. Én `min_per_bucket` kan ikke dække begge.

Grænsen er dermed håndhævet uden signaturændring og uden at tvinge noget
igennem. Alle otte cases i `cases/` kører `1h`, så ingen eksisterende kørsel
rammes.

---

# 5. DE FIRE KØRSLER — OG EN FEJL I PRÆMISSEN

## Resultat

| case | forventet i opgaven | faktisk |
|---|---|---|
| `billund_sporB_H2_2025` | grøn | **CoverageError på `dmi/fyn`** |
| `billund_sporB_q1_2026` | grøn | **CoverageError på `dmi/fyn`** |
| `billund_2025` | grøn | **CoverageError på `dmi/fyn`** |
| `billund_baseline` (2024) | CoverageError på `afrr` | **CoverageError på `dmi/fyn`** |

Ingen `objektiv_dkk` eller `balanceindtaegt` kan rapporteres — ingen af de fire
kørsler nåede frem til solveren.

## Præmissen holder ikke

Opgaven kalder de tre første "de tre cases der har fuld dækning". **Det er de
ikke.** Gate 0.5 §C3 målte det allerede, og målingen står i notatet:

| kørselsvindue | `dmi/fyn` | manglende |
|---|---|---|
| 2025-07-01 .. 2025-12-31 | 4415/4416 | 1 t (DST 2025-10-26) |
| 2026-01-01 .. 2026-04-30 | 2849/2880 | 31 t |
| 2025-01-01 .. 2025-12-31 | 8759/8760 | 1 t (DST 2025-10-26) |
| 2024-01-01 .. 2024-12-31 | 8783/8784 | 1 t (DST 2024-10-27) |

Gate 0.5 §A-fund 1 målte at **alle** DMI-årsfiler mangler præcis én time ved
oktober-DST. Enhver kørsel der spænder en sidste-søndag-i-oktober rammes
derfor. `dmi` læses først i `load_external_data_github` (linje 503), så vagten
fyrer dér, længe før den når `afrr` eller balancedataene.

Det er ikke en fejl i vagten. Vagten gør præcis hvad den skal: de timer BLEV
interpoleret tavst før i dag — Gate 1 §Trin 0 beviste det ved at måle den
lineære interpolation i de gemte outputs. Præmissen om "fuld dækning" var
forkert, og gaten har afsløret det.

## Fejlbeskeden fra `billund_baseline`, ordret

```
Traceback (most recent call last):
  ...
  File "/opt/fjernvarme-businesscase/src/data_loader_github.py", line 257, in fetch_dmi_obs_github
    df = _read_dataset(repo_root, "dmi", area, start, end, time_col="hour_utc")
  File "/opt/fjernvarme-businesscase/src/data_loader_github.py", line 198, in _read_dataset
    assert_coverage(
  File "/opt/fjernvarme-businesscase/src/data_loader.py", line 179, in assert_coverage
    raise CoverageError(
src.data_loader.CoverageError: dmi/fyn: dækning mangler for den ønskede periode.
  Ønsket:  2024-01-01 00:00:00 → 2024-12-31 23:59:59 (8784 buckets à 1h, min 1 obs/bucket)
  Målt:    8783 observationer, 2024-01-01 00:00:00 → 2024-12-31 23:00:00
  Mangler: 1/8784 buckets uden observationer (100.0% dækning)
  Første:  2024-10-27 00:00
  Sidste:  2024-10-27 00:00
  Data er ikke fyldt eller korrigeret — kørslen er stoppet før nul-fyldning. Kontrollér at df-data dækker perioden, eller indskrænk cfg.time.
```

Den `afrr`-besked Trin 5.3 sigtede efter nås aldrig i en rigtig kørsel, men
verificeret ved direkte kald:

```
CoverageError: afrr/DK1: dækning mangler for den ønskede periode.
  Ønsket:  2024-01-01 00:00:00 → 2024-12-31 23:59:59 (8784 buckets à 1h, min 1 obs/bucket)
  Målt:    2186 observationer, 2024-10-01 22:00:00 → 2024-12-31 23:00:00
  Mangler: 6598/8784 buckets uden observationer (24.9% dækning)
  Første:  2024-01-01 00:00, 2024-01-01 01:00, 2024-01-01 02:00
  Sidste:  2024-10-01 19:00, 2024-10-01 20:00, 2024-10-01 21:00
  Data er ikke fyldt eller korrigeret — kørslen er stoppet før nul-fyldning. Kontrollér at df-data dækker perioden, eller indskrænk cfg.time.
```

Print + vagt i kombination, som specificeret:

```
    (imbalance/DK1: spring over DK1_2024.csv — ikke til stede i repo)
CoverageError: imbalance/DK1: dækning mangler for den ønskede periode.
  Ønsket:  2024-01-01 00:00:00 → 2025-12-31 23:59:59 (17544 buckets à 1h, min 4 obs/bucket)
  Målt:    29040 observationer, 2025-03-04 12:00:00 → 2025-12-31 23:45:00
  Mangler: 10284/17544 buckets med under 4 observationer (41.4% dækning)
  Første:  2024-01-01 00:00, 2024-01-01 01:00, 2024-01-01 02:00
  Sidste:  2025-03-04 09:00, 2025-03-04 10:00, 2025-03-04 11:00
```

Print'et siger hvilken **fil**, vagten hvilke **timer**. To forskellige udsagn,
begge nødvendige.

Tom-`ts`-grenen:

```
CoverageError: dmi/fyn: ingen brugbare tidsstempler.
  Ønsket:  2026-07-01 00:00:00 → 2026-07-31 23:59:59 (744 buckets à 1h, min 1 obs/bucket)
  Målt:    0 observationer
  Mangler: 744/744 buckets (0.0% dækning)
  Kilden leverede intet for perioden. Data er ikke fyldt eller korrigeret — kørslen er stoppet før nul-fyldning.
```

## Hvad jeg IKKE gjorde

Jeg tilføjede **ikke** en tolerance. Kravet i Trin 2 er entydigt: *"Rejs
CoverageError hvis nogen bucket har færre end min_per_bucket."* Nul tolerance
er hvad der blev specificeret, og det er hvad der er implementeret. En
tolerance ville have gjort de fire kørsler grønne, men den beslutning er
ikke min at tage stiltiende — det er præcis den slags stiltiende opblødning
gaten er sat i verden for at forhindre. Se Gate 3.

---

# 6. MÅLT vs. USIKKERT

## MÅLT

- `DID NOT RAISE`-fejlmåden for A2/B2 på HEAD før implementering.
- Linjenumre 143, 148-153 og 168 verificeret ved HEAD `3ea0399` før ændring.
- 12 passed, 1 skipped, 1 xfailed efter implementering.
- Alle fire kørsler afvist på `dmi/fyn`, med ordrette beskeder ovenfor.
- `afrr`-, `imbalance`- (begge varianter) og tom-`ts`-beskederne ved direkte
  kald af `_read_dataset`.
- `git status`: kun `src/data_loader.py` og `src/data_loader_github.py`
  ændret; `tests/` og `out/` utrackede.

## USIKKERT

1. **Om nul tolerance er det rigtige valg.** Implementeret som specificeret,
   men konsekvensen er at ingen kørsel der spænder et oktober-DST-skift kan
   gennemføres. Den eksisterende dækningsvagt i kodebasen —
   `apply_heat_csv_override:794` — bruger 5 % tolerance og interpolerer
   under. Om `assert_coverage` skal have samme form er en designbeslutning
   der ikke er truffet. Kræver en beslutning, ikke en måling.
2. **Om DMI's DST-hul bliver rettet i df-data.** Klonens HEAD-commit
   (`6c95bde`) retter tidsmærkningen, men hullet består (målt i Gate 0.5).
   Bliver det rettet opstrøms, forsvinder tre af de fire afviste kørsler af
   sig selv. Kan ikke afgøres uden netværk.
3. **`100.0% dækning` ved 2879/2880.** Procenten runder op til 100,0 mens
   `Mangler: 1/2880` er korrekt. Kosmetisk, men kan læses som modstridende.
   En decimal mere, eller "afrundet", ville løse det.
4. **Om `_MIN_OBS_PER_HOUR` skal dække `folder`-navne der ikke er i tabellen.**
   `.get(folder, 1)` falder tilbage til 1. Det er defensivt for et ukendt
   datasæt, men et nyt 15-min-datasæt ville blive målt for slapt uden
   advarsel. Ikke afklaret om det bør være en `KeyError` i stedet.
5. **`--external`-vejen er urørt.** `_api_get` og `_eds_get` har ingen vagt.
   Uden for Gate 2's afgrænsning.
6. **`_attach_unit_profiles` er urørt.** Fylder stadig 0.0 ubetinget
   (`data_loader.py:855`, nu forskudt af indsættelsen). Gate 0 udpegede den
   som et selvstændigt sæde.

---

# 7. HVAD GATE 3 SKAL TAGE FAT I

## Blokerende — i prioriteret rækkefølge

1. **Tolerance-spørgsmålet skal afgøres først.** Vagten blokerer i dag alle
   fire testede kørsler på 1-31 manglende DMI-timer ud af 2880-8784. Tre
   mulige veje, og valget er ikke teknisk:
   - Tolerance à la `apply_heat_csv_override` (≤ X % → interpolér med print,
     over → rejs). Genbruger et mønster der allerede er accepteret i
     kodebasen.
   - Pr-datasæt-tolerance: `dmi` tåler interpolation (fysisk kontinuert
     størrelse), `afrr`/`imbalance` gør ikke (markedsdata; et hul er ikke
     nul).
   - Ingen tolerance, og fiks i stedet DMI-hullerne i df-data.

   Den anden vej er den fagligt mest korrekte og den, målingerne peger på:
   Gate 1 §Trin 0 viste at DMI-hullerne blev interpoleret lineært, hvilket er
   forsvarligt for temperatur; nul-fyldning af balancepriser er det ikke.

2. **End-reglen (B4).** Test G vender først når `_read_dataset` modtager
   `idx` i stedet for to forskellige datostrenge fra linje 445-446 og
   489-490. Det er en signaturændring i `_read_dataset` og alle syv
   kaldesteder. Uden den er balancekørsler med `min_per_bucket=4` umulige,
   fordi sidste time altid mangler tre kvarter.

3. **Genkør de syv kørsler i `out/`.** De er faseforskudte (Gate 1 §Trin 0)
   og kan ikke bruges som baseline. Kan først ske når 1 og 2 er løst.

## Kan tages for givet efter Gate 2

- `assert_coverage` virker og er dækket af 14 tests inkl. e2e gennem
  `_read_dataset`.
- Bucket-designet holder: `spot`s 1h → 15-min-skift kræver ingen
  særbehandling (test F).
- Fejlbeskeden er læsbar for en fremmed bruger og navngiver de manglende
  timer.
- Print'et om manglende filer og vagten om manglende timer sameksisterer.
- 15-minutters-grænsen er synlig to steder og rammer ingen eksisterende case.

## Ikke rørt, stadig åbent

- `--external`-vejen (`_api_get`, `_eds_get`).
- `_attach_unit_profiles`s ubetingede `fill_value=0.0`.
- `write_manifest`s manglende `df_data_commit` og dækningsfelt
  (Gate 0.5 §C4).
- CLI-defekten i `_apply_time_override` (23 timers kortere akse ved
  `--year`, Gate 0.5 §B3).
