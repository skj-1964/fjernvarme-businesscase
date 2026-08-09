# F1 Gate 0.5 — Måling af opløsning, akse og eksponerede kørsler

**Status:** Read-only måling. Ingen kode ændret, intet netværk, `run_case.main()` ikke kaldt.
**Formål:** Levere de tre målinger som dæknings-vagten i `_read_dataset`
(`data_loader_github.py:168`) mangler, før den kan designes: faktisk opløsning pr. datasæt,
den bindende aksedefinition, og hvilke eksisterende kørsler der er eksponeret.
**Forudsætning:** Gate 0, se [notat_f1_gate0_daekningsvagt.md](notat_f1_gate0_daekningsvagt.md).
**Modelrepo ved måling:** HEAD `3ea0399`.
**Dato for aflæsning:** 2026-08-07

Kaldt kode: `load_case`, `make_time_index`, `_apply_time_override`. Intet andet.
Alle tidskolonner fundet ved navneopslag, aldrig ved position.

---

## Præmis-korrektioner (læs først)

Tre af opgavens præmisser holder ikke ved måling:

1. **Klonen er ikke ældre — den er nyere end modelrepoet.** `data/df-data` står på
   `6c95bde23ecaaf5d2feabbd74ec4345778e775a1`, **2026-08-07 12:03:17 +0200**, besked
   *"Ret tidsmaerkningen i dmi/\*.csv — hour_utc bar lokal tid"*. Modelrepoets HEAD
   `3ea0399` er fra 11:55:48 samme dag. Klonen er shallow (`--depth 1`), branch `main`.
2. **A3's tal 2026-06-27 21:45 gælder ikke alle filer.** Nyeste tidsstempel i klonen er
   **2026-06-28 21:00** i `dmi/{fyn,karup,vestkyst}_2026.csv`. 21:45-tallet er korrekt for
   spot- og balancedatasættene.
3. **Antallet af 2022-filer er 10, ikke 8** (7 spot inkl. SYSTEM + 3 dmi). Alle har præcis
   1 række — bekræftet som forventet artefakt, se A0.

A2's grænser holder derimod under den halvåbne læsning. Detaljer i A2.

---

# MÅLT

## DEL A — OPLØSNING OG DÆKNING PR. FIL

68 CSV'er, alle mapper, alle områder, alle år. Tidskolonne fundet ved navneopslag i
rækkefølgen `hour_utc`, `TimeUTC`, `time_utc`, `timestamp`, `time`. Ingen fil manglede
tidskolonne; ingen fil havde uparsbare tidsstempler (NaT = 0 overalt).

### Tidskolonne pr. datasæt (målt, ikke antaget)

| mappe | tidskolonne fundet | øvrige tidsfelter i filen |
|---|---|---|
| `spot/` | `hour_utc` | `hour_dk` |
| `dmi/` | `hour_utc` | `unixtime`, `hour_dk` |
| `afrr/` | `TimeUTC` | `TimeDK` |
| `mfrr_cap/` | `TimeUTC` | `TimeDK` |
| `mfrr_act/` | `TimeUTC` | `TimeDK` |
| `imbalance/` | `TimeUTC` | `TimeDK` |

`spot/DK1_*.csv` og `spot/DK2_*.csv` har `id` som første kolonne; `DE/NO2/SE3/SE4/SYSTEM`
har ikke. Bekræftet — og uden betydning her, da alt er læst ved navn.

### A0. 2022-filerne — forventet artefakt, bekræftet

Alle 10 `*_2022.csv` har **præcis 1 række** med tidsstempel **2022-12-31 23:00:00**:
`dmi/{fyn,karup,vestkyst}_2022.csv`, `spot/{DE,DK1,DK2,NO2,SE3,SE4,SYSTEM}_2022.csv`.
Det er UTC-årsnavngivningen der slår igennem (2023-01-01 00:00 dansk tid = 2022-12-31
23:00 UTC). **Ingen afvigelse — ikke et fund.**

### A-tabel — alle 68 filer

Deltas i sekunder. `huller` = intervaller hvor differensen > modal_delta.
`dub` = antal ikke-unikke tidsstempler.

| sti | tidskol. | rows | first | last | deltas | modal | skift | huller | dub |
|---|---|---|---|---|---|---|---|---|---|
| `afrr/DK1_2024.csv` | TimeUTC | 2186 | 2024-10-01 22:00:00 | 2024-12-31 23:00:00 | 3600s: 2185 | 3600 | — | ingen | 0 |
| `afrr/DK1_2025.csv` | TimeUTC | 8760 | 2025-01-01 00:00:00 | 2025-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `afrr/DK1_2026.csv` | TimeUTC | 4270 | 2026-01-01 00:00:00 | 2026-06-27 21:00:00 | 3600s: 4269 | 3600 | — | ingen | 0 |
| `dmi/fyn_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `dmi/fyn_2023.csv` | hour_utc | 8759 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8757, 7200s: 1 | 3600 | — | [2023-10-28 23:00, 2023-10-29 01:00, 1] | 0 |
| `dmi/fyn_2024.csv` | hour_utc | 8783 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8781, 7200s: 1 | 3600 | — | [2024-10-26 23:00, 2024-10-27 01:00, 1] | 0 |
| `dmi/fyn_2025.csv` | hour_utc | 8759 | 2025-01-01 00:00:00 | 2025-12-31 23:00:00 | 3600s: 8757, 7200s: 1 | 3600 | — | [2025-10-25 23:00, 2025-10-26 01:00, 1] | 0 |
| `dmi/fyn_2026.csv` | hour_utc | 4263 | **2026-01-01 02:00:00** | 2026-06-28 21:00:00 | 3600s: 4261, 108000s: 1 | 3600 | — | **[2026-02-28 10:00, 2026-03-01 16:00, 29]** | 0 |
| `dmi/karup_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `dmi/karup_2023.csv` | hour_utc | 8759 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8757, 7200s: 1 | 3600 | — | [2023-10-28 23:00, 2023-10-29 01:00, 1] | 0 |
| `dmi/karup_2024.csv` | hour_utc | 8783 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8781, 7200s: 1 | 3600 | — | [2024-10-26 23:00, 2024-10-27 01:00, 1] | 0 |
| `dmi/karup_2025.csv` | hour_utc | 8759 | 2025-01-01 00:00:00 | 2025-12-31 23:00:00 | 3600s: 8757, 7200s: 1 | 3600 | — | [2025-10-25 23:00, 2025-10-26 01:00, 1] | 0 |
| `dmi/karup_2026.csv` | hour_utc | 4294 | 2026-01-01 00:00:00 | 2026-06-28 21:00:00 | 3600s: 4293 | 3600 | — | **ingen** | 0 |
| `dmi/vestkyst_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `dmi/vestkyst_2023.csv` | hour_utc | 8759 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8757, 7200s: 1 | 3600 | — | [2023-10-28 23:00, 2023-10-29 01:00, 1] | 0 |
| `dmi/vestkyst_2024.csv` | hour_utc | 8783 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8781, 7200s: 1 | 3600 | — | [2024-10-26 23:00, 2024-10-27 01:00, 1] | 0 |
| `dmi/vestkyst_2025.csv` | hour_utc | 8759 | 2025-01-01 00:00:00 | 2025-12-31 23:00:00 | 3600s: 8757, 7200s: 1 | 3600 | — | [2025-10-25 23:00, 2025-10-26 01:00, 1] | 0 |
| `dmi/vestkyst_2026.csv` | hour_utc | 4262 | **2026-01-01 02:00:00** | 2026-06-28 21:00:00 | 3600s: 4260, 111600s: 1 | 3600 | — | **[2026-02-28 10:00, 2026-03-01 17:00, 30]** | 0 |
| `imbalance/DK1_2025.csv` | TimeUTC | 29040 | **2025-03-04 12:00:00** | 2025-12-31 23:45:00 | 900s: 29039 | 900 | — | ingen | 0 |
| `imbalance/DK1_2026.csv` | TimeUTC | 17080 | 2026-01-01 00:00:00 | 2026-06-27 21:45:00 | 900s: 17079 | 900 | — | ingen | 0 |
| `imbalance/DK2_2025.csv` | TimeUTC | 29040 | **2025-03-04 12:00:00** | 2025-12-31 23:45:00 | 900s: 29039 | 900 | — | ingen | 0 |
| `imbalance/DK2_2026.csv` | TimeUTC | 17080 | 2026-01-01 00:00:00 | 2026-06-27 21:45:00 | 900s: 17079 | 900 | — | ingen | 0 |
| `mfrr_act/DK1_2025.csv` | TimeUTC | 29092 | **2025-03-03 23:00:00** | 2025-12-31 23:45:00 | 900s: 29091 | 900 | — | ingen | 0 |
| `mfrr_act/DK1_2026.csv` | TimeUTC | 17080 | 2026-01-01 00:00:00 | 2026-06-27 21:45:00 | 900s: 17079 | 900 | — | ingen | 0 |
| `mfrr_act/DK2_2025.csv` | TimeUTC | 29092 | **2025-03-03 23:00:00** | 2025-12-31 23:45:00 | 900s: 29091 | 900 | — | ingen | 0 |
| `mfrr_act/DK2_2026.csv` | TimeUTC | 17080 | 2026-01-01 00:00:00 | 2026-06-27 21:45:00 | 900s: 17079 | 900 | — | ingen | 0 |
| `mfrr_cap/DK1_2023.csv` | TimeUTC | 4634 | **2023-06-20 22:00:00** | 2023-12-31 23:00:00 | 3600s: 4632, 90000s: 1 | 3600 | — | **[2023-06-22 21:00, 2023-06-23 22:00, 24]** | 0 |
| `mfrr_cap/DK1_2024.csv` | TimeUTC | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `mfrr_cap/DK1_2025.csv` | TimeUTC | 8760 | 2025-01-01 00:00:00 | 2025-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `mfrr_cap/DK1_2026.csv` | TimeUTC | 4270 | 2026-01-01 00:00:00 | 2026-06-27 21:00:00 | 3600s: 4269 | 3600 | — | ingen | 0 |
| `mfrr_cap/DK2_2023.csv` | TimeUTC | 4634 | **2023-06-20 22:00:00** | 2023-12-31 23:00:00 | 3600s: 4632, 90000s: 1 | 3600 | — | **[2023-06-22 21:00, 2023-06-23 22:00, 24]** | 0 |
| `mfrr_cap/DK2_2024.csv` | TimeUTC | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `mfrr_cap/DK2_2025.csv` | TimeUTC | 8760 | 2025-01-01 00:00:00 | 2025-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `mfrr_cap/DK2_2026.csv` | TimeUTC | 4270 | 2026-01-01 00:00:00 | 2026-06-27 21:00:00 | 3600s: 4269 | 3600 | — | ingen | 0 |
| `spot/DE_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `spot/DE_2023.csv` | hour_utc | 8760 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `spot/DE_2024.csv` | hour_utc | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `spot/DE_2025.csv` | hour_utc | 6550 | 2025-01-01 00:00:00 | **2025-09-30 21:00:00** | 3600s: 6549 | 3600 | — | ingen | 0 |
| `spot/DE_2026.csv` | hour_utc | 8448 | **2026-03-31 22:00:00** | 2026-06-27 21:45:00 | 900s: 8447 | 900 | — | ingen | 0 |
| `spot/DK1_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `spot/DK1_2023.csv` | hour_utc | 8760 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `spot/DK1_2024.csv` | hour_utc | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `spot/DK1_2025.csv` | hour_utc | 15390 | 2025-01-01 00:00:00 | 2025-12-31 23:45:00 | **900s: 8839, 3600s: 6550** | 900 | **1h→15min ved 2025-09-30 22:00 → 22:15** | se note ¹ | 0 |
| `spot/DK1_2026.csv` | hour_utc | 17080 | 2026-01-01 00:00:00 | 2026-06-27 21:45:00 | 900s: 17079 | 900 | — | ingen | 0 |
| `spot/DK2_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `spot/DK2_2023.csv` | hour_utc | 8760 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `spot/DK2_2024.csv` | hour_utc | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `spot/DK2_2025.csv` | hour_utc | 15390 | 2025-01-01 00:00:00 | 2025-12-31 23:45:00 | **900s: 8839, 3600s: 6550** | 900 | **1h→15min ved 2025-09-30 22:00 → 22:15** | se note ¹ | 0 |
| `spot/DK2_2026.csv` | hour_utc | 17080 | 2026-01-01 00:00:00 | 2026-06-27 21:45:00 | 900s: 17079 | 900 | — | ingen | 0 |
| `spot/NO2_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `spot/NO2_2023.csv` | hour_utc | 8760 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `spot/NO2_2024.csv` | hour_utc | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `spot/NO2_2025.csv` | hour_utc | 6550 | 2025-01-01 00:00:00 | **2025-09-30 21:00:00** | 3600s: 6549 | 3600 | — | ingen | 0 |
| `spot/NO2_2026.csv` | hour_utc | 8448 | **2026-03-31 22:00:00** | 2026-06-27 21:45:00 | 900s: 8447 | 900 | — | ingen | 0 |
| `spot/SE3_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `spot/SE3_2023.csv` | hour_utc | 8760 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `spot/SE3_2024.csv` | hour_utc | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `spot/SE3_2025.csv` | hour_utc | 6550 | 2025-01-01 00:00:00 | **2025-09-30 21:00:00** | 3600s: 6549 | 3600 | — | ingen | 0 |
| `spot/SE3_2026.csv` | hour_utc | 8448 | **2026-03-31 22:00:00** | 2026-06-27 21:45:00 | 900s: 8447 | 900 | — | ingen | 0 |
| `spot/SE4_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `spot/SE4_2023.csv` | hour_utc | 8760 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `spot/SE4_2024.csv` | hour_utc | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `spot/SE4_2025.csv` | hour_utc | 6550 | 2025-01-01 00:00:00 | **2025-09-30 21:00:00** | 3600s: 6549 | 3600 | — | ingen | 0 |
| `spot/SE4_2026.csv` | hour_utc | 8448 | **2026-03-31 22:00:00** | 2026-06-27 21:45:00 | 900s: 8447 | 900 | — | ingen | 0 |
| `spot/SYSTEM_2022.csv` | hour_utc | 1 | 2022-12-31 23:00:00 | 2022-12-31 23:00:00 | — | — | — | ingen | 0 |
| `spot/SYSTEM_2023.csv` | hour_utc | 8760 | 2023-01-01 00:00:00 | 2023-12-31 23:00:00 | 3600s: 8759 | 3600 | — | ingen | 0 |
| `spot/SYSTEM_2024.csv` | hour_utc | 8784 | 2024-01-01 00:00:00 | 2024-12-31 23:00:00 | 3600s: 8783 | 3600 | — | ingen | 0 |
| `spot/SYSTEM_2025.csv` | hour_utc | 887 | 2025-01-01 00:00:00 | **2025-02-06 22:00:00** | 3600s: 886 | 3600 | — | ingen | 0 |

**¹ Note om DK1/DK2_2025's "huller":** rå-algoritmen (delta > modal) rapporterer 6550
"huller" for disse to filer, fordi modal-delta bliver 900 s mens hele første del er
1-timers. Det er **ikke** huller — det er opløsningsskiftet. Målt præcist: den 1-timers del
løber ubrudt `2025-01-01 00:00 .. 2025-09-30 22:00` (6550 skridt à 3600 s), og fra
`2025-09-30 22:00 → 22:15` er alle 8839 skridt à 900 s. **Der er nul 3600 s-skridt efter
overgangen** — skiftet er rent, ikke en blanding. Ingen af de to filer har ægte huller.

**Ingen fil i klonen har dubletter.** `duplicated`-oprensningen i loaderen (linje
207/233/259/285/302/362/374) rammer intet på det nuværende datasæt.

### A1. Er opløsningen konstant pr. datasæt+område?

| datasæt | område | konstant? | målt |
|---|---|---|---|
| `afrr` | DK1 | **Ja** | 3600 s, 2024-10-01 22:00 → 2026-06-27 21:00 |
| `mfrr_cap` | DK1, DK2 | **Ja** | 3600 s, 2023-06-20 22:00 → 2026-06-27 21:00 |
| `mfrr_act` | DK1, DK2 | **Ja** | 900 s, 2025-03-03 23:00 → 2026-06-27 21:45 |
| `imbalance` | DK1, DK2 | **Ja** | 900 s, 2025-03-04 12:00 → 2026-06-27 21:45 |
| `dmi` | fyn, karup, vestkyst | **Ja** | 3600 s hele perioden |
| `spot` | **DK1, DK2** | **NEJ** | 3600 s t.o.m. **2025-09-30 22:00**, derefter 900 s. Ét skift, retning grov→fin. |
| `spot` | **DE, NO2, SE3, SE4** | **NEJ** | 3600 s t.o.m. 2025-09-30 21:00 — derefter **ingen data** til 2026-03-31 22:00, hvorefter 900 s. Ét skift, grov→fin, adskilt af hullet. |
| `spot` | SYSTEM | Ja (så langt den går) | 3600 s, ophører 2025-02-06 22:00. Ingen 2026-fil. |

Docstringens påstande (`data_loader_github.py:25-30`) er hermed verificeret på ét punkt og
korrigeret på et andet. `afrr`/`mfrr_cap` = 1h ✓. `mfrr_act`/`imbalance` = 15-min ✓.
DK1-spot skifter 1h→15-min — men skæringen er **2025-09-30 22:00 UTC**, ikke "~2025-10-01".
Én time før midnat UTC, svarende til 2025-10-01 00:00 dansk sommertid.

**Konklusion for vagten:** fem af seks datasæt kan tage én konstant `expected_freq`.
**Kun `spot` kan ikke** — og det gælder alle syv områder.

### A2. Hullet i spot DE/NO2/SE3/SE4 — BEKRÆFTET

Målt for alle fire områder, **identiske grænser**:

| | målt |
|---|---|
| sidste tilstedeværende tidsstempel før hullet | **2025-09-30 21:00:00** (alle fire) |
| første manglende tidsstempel | **2025-09-30 22:00:00** |
| sidste manglende tidsstempel | **2026-03-31 21:00:00** |
| første tilstedeværende efter hullet | **2026-03-31 22:00:00** (alle fire) |
| hullets længde | 4368 timer ≈ 182 døgn |
| opløsning før / efter | 3600 s / 900 s |

Den oprindeligt angivne grænse `2025-09-30 22:00 → 2026-03-31 22:00` er **korrekt** læst som
det halvåbne interval [første manglende, første tilstedeværende igen). Hullet findes i alle
fire områder med samme grænser. **DK1/DK2 har ikke hullet** — de fortsætter ubrudt i 15-min.

**Sidegevinst:** `spot/SYSTEM` har et endnu større hul — ophører 2025-02-06 22:00 og har
ingen 2026-fil overhovedet. SYSTEM bruges ikke af modellen
(`cfg.electricity.spot_area = "DK1"` i alle cases), men vagten vil ramme det hvis nogen
skifter zone.

### A3. Nyeste tidsstempel + klonens tilstand

| | |
|---|---|
| klon-HEAD | `6c95bde23ecaaf5d2feabbd74ec4345778e775a1` |
| klon-dato | 2026-08-07 12:03:17 +0200 |
| klon-besked | `Ret tidsmaerkningen i dmi/*.csv — hour_utc bar lokal tid` |
| shallow | ja (`--depth 1`), branch `main` |
| **nyeste tidsstempel i klonen** | **2026-06-28 21:00:00** — `dmi/{fyn,karup,vestkyst}_2026.csv` |
| nyeste i spot/balance (15-min) | 2026-06-27 21:45:00 — `spot/{DK1,DK2,DE,NO2,SE3,SE4}_2026`, `imbalance/*_2026`, `mfrr_act/*_2026` |
| nyeste i timesopløste balance | 2026-06-27 21:00:00 — `afrr/DK1_2026`, `mfrr_cap/*_2026` |

Klonen er **ikke** ældre end forarbejdet. Gate 0's 21:45-tal er korrekt for spot/balance,
men DMI går et døgn længere.

### A-fund der ikke var spurgt om

1. **Alle DMI-årsfiler mangler præcis én time ved oktober-DST.** 2023: 8759 rækker (skal
   være 8760), 2024: 8783 (skal være 8784), 2025: 8759. Hullet ligger hver gang på den
   sidste søndag i oktober: `2023-10-28 23:00 → 2023-10-29 01:00`,
   `2024-10-26 23:00 → 2024-10-27 01:00`, `2025-10-25 23:00 → 2025-10-26 01:00`. Alle tre
   områder, alle tre år. Det er signaturen på den lokal→UTC-konvertering som klonens
   HEAD-commit netop retter — timen der bliver dubleret ved DST-tilbagestilling er faldet
   ud i stedet.
2. **`dmi/fyn_2026` og `dmi/vestkyst_2026` starter 02:00, ikke 00:00** — to timer mangler
   ved årsskiftet. `dmi/karup_2026` starter korrekt 00:00 og har intet hul overhovedet.
3. **`dmi/fyn_2026` har et 29-timers hul** `2026-02-28 10:00 → 2026-03-01 16:00`;
   `vestkyst_2026` har et 30-timers hul samme sted. `karup_2026` har det ikke.
   Dette hul ligger midt i fem af de syv eksisterende kørsler — se C3.
4. **`mfrr_cap/DK1_2023` og `DK2_2023` har et 24-timers hul**
   `2023-06-22 21:00 → 2023-06-23 22:00`.

---

## DEL B — AKSESEMANTIK

### B1. cases/*.yaml

| fil | cfg.time.start | cfg.time.end | res | idx.min() | idx.max() | len(idx) |
|---|---|---|---|---|---|---|
| `andeby.yaml` | 2025-01-01 00:00:00+00:00 | 2025-12-31 23:00:00+00:00 | 1h | 2025-01-01 00:00 | 2025-12-31 23:00 | 8760 |
| `billund_2025.yaml` | 2025-01-01 00:00:00+00:00 | 2025-12-31 23:00:00+00:00 | 1h | 2025-01-01 00:00 | 2025-12-31 23:00 | 8760 |
| `billund_backtest_jan_apr_2026.yaml` | 2026-01-01 00:00:00+00:00 | 2026-04-30 23:00:00+00:00 | 1h | 2026-01-01 00:00 | 2026-04-30 23:00 | 2880 |
| `billund_baseline.yaml` | 2024-01-01 00:00:00+00:00 | 2024-12-31 23:00:00+00:00 | 1h | 2024-01-01 00:00 | 2024-12-31 23:00 | 8784 |
| `billund_energypro_backtest_H2_2025.yaml` | 2025-07-01 00:00:00+00:00 | 2025-12-31 23:00:00+00:00 | 1h | 2025-07-01 00:00 | 2025-12-31 23:00 | 4416 |
| `billund_energypro_backtest_H2_2025_fase2.yaml` | 2025-07-01 00:00:00+00:00 | 2025-12-31 23:00:00+00:00 | 1h | 2025-07-01 00:00 | 2025-12-31 23:00 | 4416 |
| `billund_sporB_H2_2025.yaml` | 2025-07-01 00:00:00+00:00 | 2025-12-31 23:00:00+00:00 | 1h | 2025-07-01 00:00 | 2025-12-31 23:00 | 4416 |
| `billund_sporB_q1_2026.yaml` | 2026-01-01 00:00:00+00:00 | 2026-04-30 23:00:00+00:00 | 1h | 2026-01-01 00:00 | 2026-04-30 23:00 | 2880 |

De øvrige seks `cases/heat_load_params_v*.yaml` har ingen `time:`-blok — det er rene
parameterfiler til `--heat-params`, ikke cases.

**Nøgleobservation:** YAML-felterne er **tz-aware datetimes med eksplicit klokkeslæt**
(`2025-12-31 23:00:00+00:00`), ikke bare datoer. Alle otte cases giver derfor en akse der
dækker perioden fuldt ud. `billund_baseline` giver 8784 = fuldt skudår 2024.

### B2. CLI-overrides

| res | override | cfg.time.start | cfg.time.end | idx.min() | idx.max() | len(idx) | fuldt år | mangler |
|---|---|---|---|---|---|---|---|---|
| 1h | `--year 2025` | `2025-01-01` | `2025-12-31` | 2025-01-01 00:00 | **2025-12-31 00:00** | **8737** | 8760 | **23** |
| 1h | `--year 2026` | `2026-01-01` | `2026-12-31` | 2026-01-01 00:00 | **2026-12-31 00:00** | **8737** | 8760 | **23** |
| 1h | `--start 2025-01-01 --end 2025-12-31` | `2025-01-01` | `2025-12-31` | 2025-01-01 00:00 | **2025-12-31 00:00** | **8737** | 8760 | **23** |
| 15min | `--year 2025` | `2025-01-01` | `2025-12-31` | 2025-01-01 00:00 | **2025-12-31 00:00** | **34945** | 35040 | **95** |
| 15min | `--year 2026` | `2026-01-01` | `2026-12-31` | 2026-01-01 00:00 | **2026-12-31 00:00** | **34945** | 35040 | **95** |
| 15min | `--start 2025-01-01 --end 2025-12-31` | `2025-01-01` | `2025-12-31` | 2025-01-01 00:00 | **2025-12-31 00:00** | **34945** | 35040 | **95** |

`--year` og `--start/--end` giver **identisk** resultat — `_apply_time_override` sætter i
begge tilfælde bare strenge uden klokkeslæt.

### B3. Gate 0's 23-timers påstand — BEKRÆFTET, men scoped

| resolution | akse slutter | manglende skridt vs. kalenderår |
|---|---|---|
| `1h` | 2025-12-31 **00:00** | **23 timer** (8737 vs. 8760) |
| `15min` | 2025-12-31 **00:00** | **95 kvarter** = 23,75 timer (34945 vs. 35040) |

Bekræftet for begge opløsninger. **Men afgrænsningen er vigtig:** fejlen opstår **kun** via
CLI-override. Alle otte case-YAML'er skriver `23:00` eksplicit i `time.end` og rammer den
ikke. Gate 0's USIKKERT §4 er hermed afklaret: det er en CLI-defekt, ikke en generel
aksedefekt. Ingen af de syv eksisterende kørsler i `out/` er ramt — alle har
`periode.slut` fra YAML.

### B4. Den dobbelte end-regel — målt

For `cases/billund_sporB_q1_2026.yaml` (`idx = [2026-01-01 00:00 .. 2026-04-30 23:00]`,
`spot_area = DK1`):

| sti | argumenter til `_read_dataset` | `start_ts` | `end_ts` |
|---|---|---|---|
| **spot** (linje 445–446 → 184) | `('2026-01-01', '2026-04-30')` | `2026-01-01 00:00:00` | **`2026-04-30 23:59:59`** |
| **dmi** (linje 445–446 → 219) | `('2026-01-01', '2026-04-30')` | `2026-01-01 00:00:00` | **`2026-04-30 23:59:59`** |
| **afrr** (linje 489–490 → 277) | `('2026-01-01T00:00', '2026-04-30T23:00')` | `2026-01-01 00:00:00` | **`2026-04-30 23:00:00`** |
| **imbalance** (→ 294) | `('2026-01-01T00:00', '2026-04-30T23:00')` | `2026-01-01 00:00:00` | **`2026-04-30 23:00:00`** |
| **mfrr_cap** (→ 357) | `('2026-01-01T00:00', '2026-04-30T23:00')` | `2026-01-01 00:00:00` | **`2026-04-30 23:00:00`** |
| **mfrr_act** (→ 369) | `('2026-01-01T00:00', '2026-04-30T23:00')` | `2026-01-01 00:00:00` | **`2026-04-30 23:00:00`** |

Forskel på `end_ts`: **59 minutter 59 sekunder**. Samme mønster målt for
`billund_sporB_H2_2025` og `billund_2025`.

> Bemærk: `start_ts`/`end_ts` er beregnet ved at replikere reglen fra
> `data_loader_github.py:161-164` lokalt. `_read_dataset` er ikke kaldt.

**Den konkrete konsekvens — målt, ikke udledt.** For de tre 15-min-datasæt betyder
59:59-forskellen at de sidste tre kvarter af kørslen aldrig læses:

| datasæt | med spot/dmi-reglen | med balance-reglen | tabt |
|---|---|---|---|
| `imbalance/DK1` 2026-01-01..2026-04-30 | 11 520 rækker | **11 517** | 3 |
| `mfrr_act/DK1` 2026-01-01..2026-04-30 | 11 520 | **11 517** | 3 |
| `imbalance/DK1` 2025-07-01..2025-12-31 | 17 664 | **17 661** | 3 |
| `imbalance/DK1` 2026-03-01..2026-04-30 | 5 856 | **5 853** | 3 |

De tabte tidsstempler er `2026-04-30 23:15`, `23:30`, `23:45`. Da
`fetch_balance_prices_github:318` derefter kører `resample("1h").mean()`, bliver
**kørslens sidste time beregnet som gennemsnittet af 1 kvarter i stedet for 4**.
`spot/DK1` rammes ikke — den læses med 23:59:59-reglen og får alle 11 520 rækker.

Det er en levende defekt i alle syv kørsler i `out/`. Effekten er lille (1 time ud af
2880), men den er systematisk og bør fjernes af samme greb der indfører vagten.

---

## DEL C — EKSPONEREDE KØRSLER

### C1. `src/manifest.py` — hvad registreres

`write_manifest` (linje 150–246) skriver `schema_version 1.0` med fem blokke:

| blok | felter |
|---|---|
| `meta` | `case_name`, `titel`, `beskrivelse`, `gruppe`, `rolle_i_gruppe` |
| **`koersel`** | `datakilde`, `periode{start, slut, oploesning}`, `med_balancering`, `enheder_til`, `enheder_fra`, `overrides`, `foresight_haircut_pct` |
| `sporbarhed` | `model_commit`, `koert_tidspunkt`, `solve_status`, `model_type` |
| `noegletal` | `objektiv_dkk`, `varmeefterspoergsel_mwh`, `samlet_produktion_mwh`, `nettab_mwh`, `nettab_pct`, `balanceindtaegt_dkk{i_alt,afrr,mfrr,brutto}`, `tank_arbitrage_dkk`, `co2_ton` |
| `enheder`, `filer` | pr-enhed KPI'er; filnavne |

**Registreres:**

- periode — ja, men **kun som `YYYY-MM-DD`**. `_date10` (linje 47–52) trunkerer, så
  `2026-04-30 23:00:00+00:00` bliver `"2026-04-30"`. Klokkeslættet — netop det der
  adskiller B4's to regler — går tabt.
- `datakilde` — ja (`github`/`external`/`dummy`, linje 39–44).
- `med_balancering` — ja, men **udledt af resultatet**, ikke af `args`: linje 171–174
  scanner `result.data_vars` for `r_afrr_`/`r_mfrr_`/`r_up_el_`. Registrerer altså om
  balancering *virkede*, ikke om den var *bedt om*.
- `oploesning` — ja, `cfg.time.resolution`.

**Registreres IKKE:**

- Hvilke filer der blev indlæst. Intet felt overhovedet.
- Dækning, huller eller manglende årsfiler.
- `dmi_area` og `price_zone` (CLI-argumenter der bestemmer *hvilke* filer der læses).
- **df-data-repoets commit-SHA.** `model_commit` (linje 28–36) kører
  `git rev-parse --short HEAD` i modelrepoet — datarepoets tilstand er usporet.
- `df_data_url` / `cache_dir` / `force_refresh`.

### C2. Kørsler i `out/`

Syv kørsler, alle `datakilde=github`, alle `med_balancering=True`, alle `res=1h`,
alle `solve_status=optimal`.

| mappe | kørt (UTC) | model_commit | periode (manifest) | balanceindtægt i_alt DKK |
|---|---|---|---|---|
| `backtest_vp_onset` | 2026-06-24 09:14:23 | `18b8ebe` | 2026-01-01 .. 2026-04-30 | 18 127 769 |
| `backtest_no_onset` | 2026-06-24 09:20:05 | `18b8ebe` | 2026-01-01 .. 2026-04-30 | 18 625 957 |
| `diag_plantwide_onset` | 2026-06-24 10:01:20 | `18b8ebe` | 2026-01-01 .. 2026-04-30 | 9 541 816 |
| `sporB_plain` | 2026-06-24 10:02:18 | `18b8ebe` | 2026-01-01 .. 2026-04-30 | 3 117 465 |
| `sporB_vp_onset` | 2026-06-24 10:02:34 | `18b8ebe` | 2026-01-01 .. 2026-04-30 | 3 117 465 |
| `sporB_H2_2025` | 2026-06-24 11:15:08 | `aa1f0b8` | 2025-07-01 .. 2025-12-31 | 16 403 820 |
| `sporB_oos_marapr` | 2026-06-24 11:17:24 | `aa1f0b8` | 2026-03-01 .. 2026-04-30 | 2 347 251 |

Alle syv kørte 2026-06-24 — altså mod en df-data-klon som den var for seks uger siden.
Klonen er siden opdateret til `6c95bde` (2026-08-07), inkl. DMI-tidsstempelrettelsen.
**Ingen af manifesterne kan fortælle hvilken dataversion de brugte.**

### C3. Krydsreference mod Del A

Målt for hvert kørselsvindue mod den nuværende klon, DK1 + `dmi/fyn` (`--dmi-area` default
er `"fyn"`, `run_case.py:107`), med de to end-regler fra B4:

| kørselsvindue | datasæt | dækning | manglende interval |
|---|---|---|---|
| **2026-01-01..2026-04-30** (4 kørsler) | `spot/DK1` | 2880/2880 | — |
| | `afrr/DK1` | 2880/2880 | — |
| | `mfrr_cap/DK1` | 2880/2880 | — |
| | `imbalance/DK1` | 2880/2880 timer, men **11 517/11 520 kvarter** | `2026-04-30 23:15, 23:30, 23:45` |
| | `mfrr_act/DK1` | 2880/2880 timer, **11 517/11 520 kvarter** | `2026-04-30 23:15, 23:30, 23:45` |
| | **`dmi/fyn`** | **2849/2880** | **`2026-01-01 00:00 .. 01:00` (2 t)** og **`2026-02-28 11:00 .. 2026-03-01 15:00` (29 t)** |
| **2026-03-01..2026-04-30** (`sporB_oos_marapr`) | `spot`, `afrr`, `mfrr_cap` | 1464/1464 | — |
| | `imbalance`, `mfrr_act` | 1464/1464 t, **5 853/5 856 kvarter** | `2026-04-30 23:15, 23:30, 23:45` |
| | **`dmi/fyn`** | **1448/1464** | **`2026-03-01 00:00 .. 15:00` (16 t)** |
| **2025-07-01..2025-12-31** (`sporB_H2_2025`) | `spot`, `afrr`, `mfrr_cap` | 4416/4416 | — |
| | `imbalance`, `mfrr_act` | 4416/4416 t, **17 661/17 664 kvarter** | `2025-12-31 23:15, 23:30, 23:45` |
| | **`dmi/fyn`** | **4415/4416** | **`2025-10-26 00:00` (1 t — DST)** |

**Balancedatasættene har fuld timedækning i alle syv kørsler.** Det er den gode nyhed:
ingen af de eksisterende balancetal er ramt af den store nul-fyldning Gate 0 beskrev.

**Temperaturen er ramt i alle syv.** De manglende timer blev udfyldt af
`data_loader_github.py:459-462` (`interpolate(method="time").ffill().bfill()`) uden en lyd.
For de fem 2026-kørsler er 31 timer syntetiske — heraf 29 sammenhængende hen over
28. februar/1. marts.

**Hvor meget det betyder, afhænger af casen.** Målt i `cfg.units`:

| case | enhed med `cop_curve` |
|---|---|
| `billund_sporB_q1_2026.yaml` | **`vp_luft_vand` — JA** |
| `billund_sporB_H2_2025.yaml` | ingen |

`model.py:72` beregner `cop_t = unit.cop_curve.evaluate(data["t_ambient"])`, og
`balancing.py:171-172` bruger samme kurve til reservekapaciteten. For de fem 2026-kørsler
går de 31 interpolerede temperaturtimer derfor **direkte ind i varmepumpens COP og dermed i
den aFRR/mFRR-kapacitet der kalibreres**. Alle fem kørsler bruger `--heat-csv`, så
varmesyntesen er suspenderet — men COP-vejen er ikke.

For `sporB_H2_2025` er der ingen `cop_curve`-enhed, så den ene DST-time påvirker kun
`t_out_c`-kolonnen i rapporteringen (`reporting.py:245`).

### C4. Kan manifestet afgøre C3? — NEJ

**Klart nej.** For at besvare C3 måtte målingen gå uden om manifestet og hente:

| nødvendig oplysning | hvor den blev fundet | i manifestet? |
|---|---|---|
| præcist tidsvindue inkl. klokkeslæt | `cases/*.yaml` via `load_case` | nej — `_date10` trunkerer |
| hvilket DMI-område | `run_case.py:107` default | **nej** |
| hvilken priszone | `cfg.electricity.spot_area` | **nej** |
| hvilke årsfiler der blev læst | udledt af `_years_in_range`-logikken | **nej** |
| om filerne dækkede vinduet | egen måling af klonen | **nej** |
| hvilken df-data-version | umuligt — klonen er ændret siden | **nej** |

Sidste række er den alvorlige. Kørslerne er fra 2026-06-24; klonen står på en commit fra
2026-08-07 hvis besked er *"Ret tidsmaerkningen i dmi/\*.csv — hour_utc bar lokal tid"*.
**Det er ikke muligt at afgøre, om de syv kørsler brugte de rettede eller de forkerte
DMI-tidsstempler.** C3 ovenfor er målt mod den nuværende klon og gælder strengt taget kun
for en *gentagelse* af kørslerne i dag.

**Krav til vagten, afledt heraf:** når `write_manifest` udvides, skal `koersel` have et
`datadaekning`-felt med mindst `df_data_commit`, og pr. datasæt
`{navn, filer_laest, first, last, manglende_skridt}`. Uden `df_data_commit` er ethvert
dækningsudsagn i manifestet uverificerbart bagudrettet.

---

# USIKKERT

1. **Om de syv `out/`-kørsler brugte de nuværende eller de tidligere DMI-tidsstempler.**
   Kan ikke afgøres: manifestet registrerer ikke df-data-commit, og klonen er shallow
   (`--depth 1`), så historikken før `6c95bde` findes ikke lokalt. Ville kræve
   `git fetch --unshallow` — udelukket af gatens netværksforbud. Alternativ uden netværk:
   sammenligne `t_out_c`-kolonnen i de gemte `*_hourly.csv` mod den nuværende
   `dmi/fyn_2026.csv`. Ikke gjort.

2. **Om `dmi/*_2026.csv`'s 29/30-timers hul er et datakilde-udfald eller et artefakt af
   tidsstempelrettelsen.** `karup_2026` har hverken hullet eller den forskudte start, mens
   `fyn` og `vestkyst` har begge dele — det peger på stationsspecifikt udfald snarere end
   konverteringsfejl, men kan ikke afgøres uden DMI's rådata.

3. **Om `dmi`-filernes manglende DST-time er rettet eller består efter `6c95bde`.**
   Målingen ovenfor er *efter* commit'en og viser at hullet stadig er der (8759 rækker i
   2025). Om commit'en var ment at rette netop det, kan ikke afgøres fra beskeden alene;
   ville kræve at læse diffen.

4. **Om `resample("1h").mean()` på en time med kun 1 af 4 kvarter giver en systematisk bias
   i én retning.** Målt at det sker (B4); ikke målt hvor stor fejlen er i DKK. Kræver en
   kørsel.

5. **Om `spot/SYSTEM`-truncering og `mfrr_cap/*_2023`-hullet nogensinde rammer en reel
   kørsel.** Ingen nuværende case bruger SYSTEM-zonen eller 2023. Vagten vil fange dem, men
   de er i dag hypotetiske.

---

# 1. KONSEKVENS FOR `expected_freq`

**Én konstant frekvens er ikke nok — men den tidsafhængige variant er heller ikke den
rigtige løsning.**

Målt: fem af seks datasæt (`afrr`, `mfrr_cap`, `mfrr_act`, `imbalance`, `dmi`) har konstant
opløsning over hele deres levetid. Kun `spot` skifter, og det gør det i alle syv områder,
med ét rent skift 3600→900 s (DK1/DK2 ved 2025-09-30 22:00; DE/NO2/SE3/SE4 hen over hullet).

En `expected_freq`-parameter med breakpoints ville virke, men den ville låse vagten fast på
en kildeegenskab der ændrer sig igen næste gang markedet skifter opløsning — og den ville
ikke fange B4-defekten.

**Anbefalet signatur — mål dækning i tidsspande, ikke i skridt:**

```
assert_coverage(
    ts,                    # faktiske tidsstempler, sorteret
    start_ts, end_ts,      # ønsket interval
    *,
    label,                 # "spot/DK1", "imbalance/DK1" — til fejlbeskeden
    bucket="1h",           # granularitet dækningen måles i
    min_per_bucket=1,      # hvor mange observationer hver bucket skal have
) -> None                  # raise ved manglende dækning
```

Kaldes fra `_read_dataset` (linje 168) med:

| datasæt | `bucket` | `min_per_bucket` | begrundelse |
|---|---|---|---|
| `spot` | `"1h"` | `1` | Håndterer 1h→15-min-skiftet gratis: 15-min-data dækker trivielt hver time. Ingen breakpoints nødvendige. |
| `dmi` | `"1h"` | `1` | Konstant 1h. |
| `afrr`, `mfrr_cap` | `"1h"` | `1` | Konstant 1h. |
| `imbalance`, `mfrr_act` | `"1h"` | **`4`** | Fanger B4: en time med 1 af 4 kvarter fejler, fordi `resample("1h").mean()` nedstrøms ellers gennemsnitter over et ufuldstændigt grundlag. |

`min_per_bucket=4` er det eneste sted en kildeegenskab skrives ind, og den er stabil så
længe ISP-perioden er 15 min. Skifter markedet igen, fejler vagten højlydt — hvilket er den
ønskede adfærd, ikke en fejl i designet.

**Buckets frem for skridt gør vagten robust over for præcis den ene ting der faktisk
varierer i dataene.**

# 2. KONSEKVENS FOR AKSEN

Der findes **tre** periodedefinitioner, og de er ikke ens:

| # | definition | målt værdi (case `billund_sporB_q1_2026`) |
|---|---|---|
| 1 | `cfg.time.start/end` | `2026-01-01 00:00+00:00` .. `2026-04-30 23:00+00:00` (tz-aware fra YAML) — **eller** bare datostrenge efter CLI-override, hvilket koster 23 timer (B3) |
| 2 | `idx = make_time_index(cfg)` | `2026-01-01 00:00` .. `2026-04-30 23:00`, n=2880, tz-naiv |
| 3 | `_read_dataset`s `start_ts/end_ts` | **to varianter**: `..23:59:59` for spot/dmi, `..23:00:00` for de fire balancedatasæt |

**Den bindende definition for modellen er #2, `idx`.** Den er `ds.time`-koordinatet
(`data_loader_github.py:476`), den er `target_index` (linje 506), og det er den akse
`build_model` og objektivet opererer på. #1 er dens input; #3 er en afledt reformatering
der findes i to inkonsistente udgaver.

**Anbefaling:** vagten skal måle mod `idx`, og for at kunne det skal `_read_dataset` modtage
`idx` — eller `(idx.min(), idx.max(), idx.freq)` — i stedet for de to omformaterede
datostrenge. Det giver tre ting på én gang:

- Vagten måler mod netop den akse der bliver fyldt på linje 405 og 460–463.
- Den dobbelte end-regel forsvinder, fordi `_read_dataset:161-168` ikke længere skal gætte
  hvad `end` betød. Dermed er B4-defekten lukket som sideeffekt.
- CLI-defekten i B3 bliver synlig i stedet for tavs: en `--year 2025`-kørsel vil have en
  akse der ærligt slutter 2025-12-31 00:00, og vagten vil bekræfte dækning af netop dét —
  hvorefter afvigelsen fra kalenderåret kan rettes separat i `_apply_time_override`, som er
  hvor den hører hjemme.

Rettelsen af B3 hører **ikke** i vagten. Vagten skal måle mod den akse modellen faktisk
bruger, ikke mod den akse brugeren måske mente.

# 3. HVAD GATE 1's TEST KAN BRUGE

Konkrete perioder og datasæt fra Del A. Alle findes i den lokale klon; ingen kræver netværk.
Datoerne er målte, ikke udledte.

### A. Garanteret manglende dækning — filen findes, men dækker kun en del

**Primær test — `afrr/DK1`, periode 2024-01-01 .. 2024-12-31 (1h, 8784 timer):**
`afrr/DK1_2024.csv` findes og har 2186 rækker, men dækker kun
`2024-10-01 22:00 .. 2024-12-31 23:00`. **6598 af 8784 modeltimer mangler.** `df.empty` er
falsk; `if not frames` udløses ikke; ingen fil mangler, så `missing`-printet er tomt.
Kørslen er i dag helt tavs. Det er den reneste enkeltfil-test der findes — vagten skal
fejle, dagens kode gør ikke.

**Sekundær test — flerårsspændet der udløser `missing`-printet:** `imbalance/DK1`, periode
2024-01-01 .. 2025-12-31. `DK1_2024.csv` findes ikke, `DK1_2025.csv` gør.
`_read_dataset:150` printer *"spring over DK1_2024.csv"*, returnerer 2025-data, `df.empty`
er falsk. Hele 2024 (8784 timer) bliver nul-fyldt på linje 402/405. Dette er nøjagtigt det
scenarie Gate 0 beskrev, og det er reproducerbart offline.

**Kontrol — den sti der allerede fejler korrekt:** `imbalance/DK1`, periode
2024-01-01 .. 2024-12-31. Ingen 2024-fil overhovedet → `FileNotFoundError` på linje 143.
Brug den som negativ kontrol, så testen skelner "eksisterende vagt virker" fra "ny vagt
virker".

### B. Garanteret hul inden for dækningen — begge endepunkter til stede

| datasæt | testperiode | hul (målt) | timer |
|---|---|---|---|
| **`dmi/fyn`** | 2026-02-01 .. 2026-03-31 | `2026-02-28 11:00 .. 2026-03-01 15:00` | **29** |
| `dmi/vestkyst` | 2026-02-01 .. 2026-03-31 | `2026-02-28 11:00 .. 2026-03-01 16:00` | 30 |
| `dmi/fyn` | 2026-01-01 .. 2026-01-31 | `2026-01-01 00:00 .. 01:00` (forskudt start) | 2 |
| **`dmi/fyn`** | 2025-10-01 .. 2025-10-31 | `2025-10-26 00:00` (DST-tilbagestilling) | **1** |
| `mfrr_cap/DK1` | 2023-06-21 .. 2023-06-30 | `2023-06-22 22:00 .. 2023-06-23 21:00` | 24 |
| `spot/DE` | 2025-09-01 .. 2026-04-30 | `2025-09-30 22:00 .. 2026-03-31 21:00` | 4368 |

Brug **1-times DST-hullet** som den skarpeste test: det er den mindste mulige mangel og
afgør om vagtens tolerance er sat rigtigt. Brug **29-timers-hullet i `dmi/fyn`** som den
realistiske, fordi det er det der faktisk ramte fem produktionskørsler.

### C. Garanteret fuld dækning — vagten må ikke fejle

| datasæt | periode | rækker | huller | dubletter |
|---|---|---|---|---|
| **`afrr/DK1`** | 2025-01-01 00:00 .. 2025-12-31 23:00 | 8760 | 0 | 0 |
| **`mfrr_cap/DK1`** | 2025-01-01 00:00 .. 2025-12-31 23:00 | 8760 | 0 | 0 |
| `mfrr_cap/DK2` | 2025-01-01 00:00 .. 2025-12-31 23:00 | 8760 | 0 | 0 |
| `mfrr_cap/DK1` | 2024-01-01 00:00 .. 2024-12-31 23:00 | 8784 (skudår) | 0 | 0 |
| **`dmi/karup`** | 2026-01-01 00:00 .. 2026-06-28 21:00 | 4294 | **0** | 0 |
| `spot/DK1` | 2026-01-01 00:00 .. 2026-06-27 21:45 | 17 080 (15-min) | 0 | 0 |
| `spot/DK1` | 2023-01-01 00:00 .. 2023-12-31 23:00 | 8760 (1h) | 0 | 0 |
| `imbalance/DK1` | 2026-01-01 00:00 .. 2026-06-27 21:45 | 17 080 | 0 | 0 |

`dmi/karup_2026` er særligt værdifuld: det er det eneste DMI-område uden hverken hul eller
forskudt start, så den isolerer "vagten er ikke overfølsom" fra "DMI er generelt hullet".

### D. Test af opløsningsskiftet

`spot/DK1`, periode **2025-09-25 .. 2025-10-05**. Spænder skæringen
`2025-09-30 22:00 → 22:15` og indeholder både 3600 s- og 900 s-skridt i samme frame. Med
`bucket="1h", min_per_bucket=1` skal vagten passere. Den er den direkte regressionstest på
at anbefalingen i afsnit 1 holder.

### E. Test af B4-defekten

`imbalance/DK1`, `start="2026-01-01T00:00"`, `end="2026-04-30T23:00"`. Med
`min_per_bucket=4` skal vagten fejle på præcis én bucket — `2026-04-30 23:00` — fordi kun
`23:00` er til stede og `23:15`/`23:30`/`23:45` er skåret væk. Med den anbefalede aksefiks
(send `idx` i stedet for datostrenge) skal samme test passere. Det er regressionstesten der
beviser at den dobbelte end-regel er væk.
