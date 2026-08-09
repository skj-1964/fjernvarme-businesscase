# F6 Gate 0 — Eget API målt mod klonen, række for række

**Status:** Read-only med netværk. 48 API-kald, alle svar i `/tmp/f6_gate0/`.
df-data-klonen urørt (`6c95bde`, tom `git status`). 28 tests grønne.
**Opslagsværk:** `noter/DATADISTRIBUTION_IMPLEMENTERING_V1.md` — brugt som
opslagsværk, ikke facit. Uenigheder er markeret eksplicit.
**Dato:** 2026-08-07

**Hovedfund:** Værdierne er identiske — 4 394 talsammenligninger, nul
afvigelser. Men §10.3's punkt 1 er målt forkert og ville have kostet et døgn
pr. kørsel, og §10.4's hypotese om DE-hullet er målt forkert på en måde der
ændrer hvad F3 skal gøre.

---

# DEL A — KOLONNE-MAPPING, MÅLT

Kald: `api_eds_balance.php?dataset=…&startdate=2026-03-15&enddate=2026-03-16&area=DK1&fields=all`
i både `format=csv` og `format=json`. Alle 200, ingen PHP-fejl i nogen krop.

| datasæt | rækker | klon-vindue |
|---|---|---|
| `imbalance_price` | 192 | 192 |
| `mfrr_activation` | 192 | 192 |
| `mfrr_capacity` | 48 | 48 |
| `afrr_capacity` | 48 | 48 |
| spot DK1 (`api_energinet_prices.php`) | 96 | 96 |

## A1/A2 — Kolonnenavne, ordret

**API `imbalance_price` (20):**
`time_utc, time_dk, price_area, satisfied_demand, imbalance_price_eur, imbalance_price_dkk, spot_price_eur, dominating_direction, afrr_up_mw, afrr_vwa_up_eur, afrr_vwa_up_dkk, afrr_down_mw, afrr_vwa_down_eur, afrr_vwa_down_dkk, mfrr_marginal_price_up_eur, mfrr_marginal_price_up_dkk, mfrr_marginal_price_down_eur, mfrr_marginal_price_down_dkk, created_at, updated_at`

**Klon `imbalance/DK1_2026.csv` (18):**
`TimeUTC, TimeDK, PriceArea, SatisfiedDemand, ImbalancePriceEUR, ImbalancePriceDKK, SpotPriceEUR, DominatingDirection, aFRRUpMW, aFRRVWAUpEUR, aFRRVWAUpDKK, aFRRDownMW, aFRRVWADownEUR, aFRRVWADownDKK, mFRRMarginalPriceUpEUR, mFRRMarginalPriceUpDKK, mFRRMarginalPriceDownEUR, mFRRMarginalPriceDownDKK`

**API `mfrr_activation` (21):**
`time_utc, time_dk, price_area, mfrr_sa_up_req_mw, mfrr_sa_up_eur, mfrr_sa_down_req_mw, mfrr_sa_down_eur, mfrr_da_up_mw, mfrr_da_up_eur, mfrr_da_down_mw, mfrr_da_down_eur, total_mfrr_up_mw, total_mfrr_down_mw, mfrr_offered_up_mw, mfrr_offered_down_mw, mfrr_local_up_mw, mfrr_local_down_mw, mfrr_special_up_mw, mfrr_special_down_mw, created_at, updated_at`

**Klon `mfrr_act/DK1_2026.csv` (19):** samme i PascalCase, uden `created_at`/`updated_at`.

**API `mfrr_capacity` (14):**
`time_utc, time_dk, price_area, **auction**, up_demand_mw, up_procured_mw, up_price_eur, up_price_dkk, down_demand_mw, down_procured_mw, down_price_eur, down_price_dkk, created_at, updated_at`

**Klon `mfrr_cap/DK1_2026.csv` (11):** som ovenfor **uden `auction`**, uden
`created_at`/`updated_at`.

**API `afrr_capacity` (13):** som `mfrr_capacity` men **uden `auction`**.
**Klon `afrr/DK1_2026.csv` (11):** samme minus `created_at`/`updated_at`.

**Spot:** API og klon har **identiske kolonner i identisk rækkefølge**:
`id, hour_utc, hour_dk, price_area, spot_price_dkk, spot_price_eur, created_at, updated_at`.

## A3 — §11.1's mapping, række for række

| §11.1 påstand | udfald |
|---|---|
| `TimeUTC` → `time_utc` | **bekræftet** |
| `UpPriceDKK` / `DownPriceDKK` → `up_price_dkk` / `down_price_dkk` | **bekræftet** |
| `UpProcuredMW` / `DownProcuredMW` → `up_procured_mw` / `down_procured_mw` | **bekræftet** |
| `aFRRVWAUpDKK` / `aFRRVWADownDKK` → `afrr_vwa_up_dkk` / `afrr_vwa_down_dkk` | **bekræftet** |
| `mFRRMarginalPriceUpDKK` / `…DownDKK` → `mfrr_marginal_price_up_dkk` / `…_down_dkk` | **bekræftet** |
| `ImbalancePriceDKK` → `imbalance_price_dkk` | **bekræftet** |
| `TotalmFRRUpMW` → `total_mfrr_up_mw` | **bekræftet** |

**Alle syv rækker holder.** Ingen korrektioner.

### Men tabellen er ufuldstændig — 4 mangler

§11.1 dækker 7 af de i alt **59** kolonner der skal mappes. Tre kategorier er
slet ikke nævnt:

1. **`auction` på `mfrr_capacity`.** API'et leverer en kolonne klonen ikke har.
   I det målte vindue er der kun værdien `main`, men spec'en har enum
   `['main','extra']`. Udelades den ved migration, kan et fremtidigt
   `extra`-udbud **fordoble rækkeantallet pr. tidsstempel** uden at det ses.
   Dette er den vigtigste udeladelse i §11.1.
2. **`created_at` / `updated_at`** på alle fire balancedatasæt. §11.3 siger de
   skal udgå — konsistent, men mappingen nævner dem ikke.
3. **Akronym-reglen er ikke mekanisk.** En naiv PascalCase→snake-konvertering
   giver `a_frr_up_mw`, `m_frrsa_up_req_mw`, `totalm_frr_up_mw` — ingen af dem
   findes. API'et bruger `afrr_up_mw`, `mfrr_sa_up_req_mw`, `total_mfrr_up_mw`.
   **Mappingen skal skrives eksplicit ud; den kan ikke genereres.** Målt ved
   at prøve: 8/18 og 3/19 kolonner ramte med automatisk konvertering.

> **Uenighed med §11.1's linjenumre.** Tabellen henviser til loader-linjer
> 279, 296, 356, 368 osv. Gate 3 målte at de er drevet til 315, 332, 395, 407.
> Målingen vinder.

## A4 — VÆRDISAMMENLIGNING (gatens vigtigste måling)

Join på tidsstempel, hver talkolonne sammenlignet række for række.

| datasæt | fælles rækker | matchende værdier | **afvigende** | max abs. Δ |
|---|---|---|---|---|
| `imbalance_price` | 192 | **2 880** | **0** | 0 |
| `mfrr_activation` | 192 | **1 514** | **0** | 0 |
| `mfrr_capacity` (auction=main) | 48 | **384** | **0** | 0 |
| `afrr_capacity` | 48 | **384** | **0** | 0 |
| spot DK1 | 96 | **192** | **0** | 0 |
| **i alt** | | **5 354** | **0** | **0** |

Desuden: `time_dk` identisk med `TimeDK` i begge 15-min-datasæt; `price_area`
identisk med `PriceArea`.

I `mfrr_activation` er 6 kolonner helt tomme i både API og klon i vinduet
(`mfrr_da_*`, `mfrr_special_up_mw`), og flere delvist. **Tomheden er
sammenfaldende** — hvor klonen er tom, er API'et også tom. Ingen kolonne har
data det ene sted og ikke det andet.

**Konklusion: eget API leverer nøjagtigt samme datasæt som EDS gør i dag.**
Ikke et lignende datasæt — det samme, celle for celle.

Én undtagelse uden betydning: spot-kolonnen `id` afviger mellem API og klon.
Det er en databaseintern nøgle som §11.3 alligevel dropper.

## A5 — Datatyper

**Bekræftet: DECIMAL serialiseres som JSON-strenge.**

```
imbalance_price (JSON):
  satisfied_demand      str  = '0.0'
  imbalance_price_eur   str  = '140.58'
  dominating_direction  int  = 0
mfrr_capacity (JSON):
  up_demand_mw          int  = 454
  up_price_dkk          str  = '177.997332'
```

INT-kolonner kommer som tal, DECIMAL som strenge. Samme i spot
(`spot_price_dkk` = `'1050.50'`, `id` = int).

§10.3's anbefaling om `format=csv` er **bekræftet som nødvendig**, ikke blot
foretrukken: i CSV er alt tekst og parses ensartet af `pd.read_csv`, mens
JSON-svaret giver en blandet typebillede der kræver eksplicit coercion.

---

# DEL B — DE FEM KONTRAKTFORSKELLE

## B1 — Halvåbent interval: **§10.3 er FORKERT som skrevet**

| kald | rækker | dækker |
|---|---|---|
| `startdate=2026-03-15&enddate=2026-03-16` | **192** | begge døgn |
| `startdate=2026-03-15&enddate=2026-03-15` | **96** | kun den 15. |
| `startdate=2026-03-15&enddate=2026-03-16 00:00:00` | **96** | kun den 15. |

Reglen er: **en bar dato i `enddate` udvides til hele døgnet (inklusivt); et
eksplicit tidsstempel er eksklusivt.** Spec'en siger det direkte —
*"En dato alene udvides til hele døgnet"* — men §10.3 punkt 1 gengiver det som
rent halvåbent og konkluderer:

> *"ved migration skal `enddate` sættes til dagen **efter** den ønskede sidste
> dag, ellers mistes et døgn i hver kørsel"*

**Målingen viser det modsatte.** Følger man §10.3 med bare datoer, får man et
døgn for **meget** — ikke for lidt. Det er samme fejlklasse som B4 i F1: en
usikker antagelse om et højre endepunkt, blot med modsat fortegn.

## B2 — `enddate` udeladt for kapacitetstabellerne

| datasæt | uden `enddate` | med `enddate` |
|---|---|---|
| `mfrr_capacity` | 190 rækker, til **2026-08-08 21:00** | 48 |
| `afrr_capacity` | 190 rækker, til **2026-08-08 21:00** | 48 |

`meta.to_exclusive_source` **findes** og er præcis den advarsel §10.3 beder om:

```
"MAX(time_utc) in table + 1s — NOT the wall clock, because this table
 reaches 26-29 hours into the future"
```

Med `enddate` sat: `to_exclusive_source: "enddate parameter"`. §10.3's krav om
at verificere feltet er dermed **gennemførligt som beskrevet**.

> **Uenighed med §10.3.** Den skriver at `mfrr_capacity` rækker 26 timer frem
> og `afrr_capacity` 29 timer. Målt kl. ~15:20 UTC den 2026-08-07 rækker
> **begge** til 2026-08-08 21:00 — **29,7 timer frem, ens for begge**. Enten er
> 26/29-skellet historisk, eller også er det aldrig blevet målt. Spec'ens egen
> meta-tekst siger "26-29 hours" som ét interval for begge tabeller.

Meta indeholder desuden `forward_looking: true` og en `time_dk_note`:
*"time_dk is the source filter axis and is NOT unique across the autumn DST
transition. Never use it as a key."* — API'et advarer altså selv mod præcis
den fejl F8 målte.

## B3 — Ukendte parametre: **holder kun for det strenge endpoint**

| endpoint | ukendt parameter | udfald |
|---|---|---|
| `api_eds_balance.php` | `vrøvleparameter=42` | **400** |
| `api_eds_balance.php` | `auction` på `imbalance_price` | **400** |
| `api_energinet_prices.php` | `vrøvleparameter=42` | **200, 96 rækker — ignoreret** |

Fejlkroppen fra det strenge endpoint:

```json
{"status":"error","message":"Unknown query parameter(s): vrøvleparameter.
 This endpoint rejects unknown parameters rather than ignoring them, because a
 silently ignored filter returns a plausible but wrong answer.
 Allowed: dataset, startdate, enddate, area, auction, format, fields, limit, offset.",
 "code":"INVALID_REQUEST"}
```

og for `auction` på forkert datasæt:

```json
{"status":"error","message":"Parameter 'auction' applies only to
 dataset=mfrr_capacity, not to 'imbalance_price'. Rejecting rather than ignoring it.",
 "code":"INVALID_REQUEST"}
```

§10.3 punkt 3 holder for `api_eds_balance.php`, men **ikke** for
`api_energinet_prices.php`. De to endpoints har ikke samme kontrakt.

## B4 — `tz`: **§10.3 holder for balance, men endpointene er ikke ens**

| endpoint | `tz` | default |
|---|---|---|
| `api_eds_balance.php` | **findes ikke** → 400 | UTC-only |
| `api_energinet_prices.php` | findes | **`dk`** |
| `api_entsoe_prices.php` | findes | `utc` |
| `api_dmi_obs_ny.php` | findes | **`dk`** (målt i F8) |

§10.3's *"Kun UTC, ingen `tz`-parameter"* er korrekt **for
`api_eds_balance.php`** og må ikke generaliseres. To af de fire endpoints vi
skal bruge defaulter til dansk tid, og hentescriptet sætter ikke parameteren
noget sted.

## B5 — Pagination

| kald | `total_records` | `returned` | `limit` i meta | `has_more` | `next_offset` |
|---|---|---|---|---|---|
| `limit=100&offset=0` | 192 | 100 | 100 | **true** | **100** |
| `limit=100&offset=100` | 192 | 92 | 100 | false | null |
| `limit=10001` | 192 | 192 | **1000** | false | null |

`has_more`/`next_offset` **virker som beskrevet**.

**Men en fælde §10.3 ikke nævner:** `limit=10001` afvises ikke — den falder
tilbage til **default 1000**, ikke til maksimum 10000. Et hentescript der beder
om 10001 får altså 1000 ad gangen uden en lyd. Det bryder endpointets egen
"afvis frem for at ignorere"-linje netop dér hvor konsekvensen er tavs
underhentning.

---

# DEL C — DE_LU-HYPOTESEN

## C1 — Hvad `update_data.py` faktisk gør

`data/df-data/scripts/update_data.py:192-213`:

```python
def update_spot(start: str, end: str, force: bool):
    print("  spot (DayAheadPrices):")
    df = fetch_eds("DayAheadPrices", start, end)
    ...
    rename = {"TimeUTC": "hour_utc", "TimeDK": "hour_dk", "PriceArea": "price_area",
              "DayAheadPriceDKK": "spot_price_dkk", "DayAheadPriceEUR": "spot_price_eur"}
    df = df.rename(columns=rename)
    split_and_write(df, "hour_utc", "price_area", REPO_ROOT / "spot", force=force)
```

**Den sender ingen områdekode overhovedet**, og den kalder **ikke**
`api_entsoe_prices.php`. Grep efter `entsoe`, `NO2`, `SE3`, `SE4` i filen:
**nul træffere**.

Spot hentes fra EDS `DayAheadPrices` **uden områdefilter**, og
`split_and_write` splitter på hvilke `price_area`-værdier der end kommer
tilbage. Filnavnene `DE_*.csv`, `NO2_*.csv` osv. bærer derfor **EDS's**
områdekoder, ikke ENTSO-E's.

## C2/C3 — Korte vs. lange koder mod `api_entsoe_prices.php`

| kode | HTTP | rækker |
|---|---|---|
| `DE` | **400** | — |
| `DE_LU` | 200 | **96** |
| `NO2` | **400** | — |
| `NO_2` | 200 | **0** |
| `SE3` | **400** | — |
| `SE_3` | 200 | **0** |
| `SE4` | **400** | — |
| `SE_4` | 200 | **0** |

Fejlkroppen for en kort kode:

```json
{"status":"error","message":"Invalid area 'DE'. Valid areas: DE_LU, DK_1, DK_2,
 FR, NO_2, SE_3, SE_4, NL, BE","code":"INVALID_REQUEST"}
```

Uden `area`-filter samme dag: **384 rækker fordelt på `DE_LU`, `DK_1`, `DK_2`,
`FR` — 96 hver.** `NO_2`, `SE_3`, `SE_4`, `NL`, `BE` står i
`available_areas`, men har ingen rækker.

## C4 — Konklusion: **navnekonventionen forklarer ingen af delene**

**Nej for DE.** Hypotesen kræver at en forkert kode gav et tavst hul. Målt
giver en forkert kode **400 med en eksplicit fejlbesked** — ikke et tomt svar.
Og mere grundlæggende: `api_entsoe_prices.php` er **aldrig blevet kaldt** af
hentescriptet. Hullet i `DE_*.csv` stammer fra at EDS `DayAheadPrices` holdt op
med at levere DE i den periode, ikke fra en kodefejl mod et endpoint der ikke
var i brug.

**Nej for NO_2/SE_3/SE_4, og her er det en anden årsag.** De giver 0 rækker med
den korrekte kode, også på datoer hvor klonen har data. Deres data findes
hverken i ENTSO-E-endpointet nu eller i den korte kode.

**Det er altså to forskellige årsager:**

| | hul i klonen | findes i `api_entsoe_prices.php` | årsag |
|---|---|---|---|
| DE | 2025-09-30 21:00 → 2026-03-31 22:00 | **ja** (96 rækker 2025-12-15) | EDS-dækning ophørte; entsoe kan dække hullet |
| NO2/SE3/SE4 | samme grænser | **nej** (0 rækker overalt) | begge kilder mangler |

§10.4's *"sandsynligvis også hullet"* holder derfor **kun for DE**, og af en
anden grund end den foreslåede.

---

# DEL D — DMI MED `unixtime` SOM NØGLE

## D1 — Entydighed pr. tz

| station | tz | rækker | unikke `unixtime` | unikke `hour_utc` | unikke `hour_dk` |
|---|---|---|---|---|---|
| alle tre | `utc` | 48 | **48** | 47 | 47 |
| alle tre | `dk` | 49 | **49** | 48 | 48 |

`unixtime` er entydig i **alle** kombinationer. `hour_utc` og `hour_dk` taber
begge præcis én i begge tz.

`tz=dk` giver flest **rækker** (49 mod 48), men det er fordi filtervinduet
dækker 25 lokale timer mod 24+24 UTC-timer — ikke fordi datagrundlaget er
større. **For et givet UTC-vindue er de to tz lige komplette.** Valget af tz
løser altså ikke problemet; valget af nøgle gør.

## D2 — Kan korrekt `hour_utc` udledes klientside? **JA**

| periode | `pd.Timestamp(unixtime, unit="s")` == `hour_utc` |
|---|---|
| 2025-06-10/11 (ingen DST) | **48/48** |
| 2025-10-25/26 (DST-tilbagestilling) | **47/48** |

Den ene afvigelse er den kendte:

```
unixtime=1761440400   API=2025-10-26 00:00:00   KORREKT=2025-10-26 01:00:00
```

Udledningen er altså identisk med API'ets egen i alle normale timer og
**korrigerer** den ene time hvor API'et tager fejl. En rettet hentning kan
derfor:

1. dedupe på `unixtime`, ikke `hour_utc`,
2. beregne `hour_utc = pd.Timestamp(unixtime, unit="s")` klientside,

og dermed lukke DST-hullet uden at afvente en serverrettelse.

## D3 — Forårets skift: **rent, ingen kollaps**

| dato | station | rækker | unikke `unixtime` | dubl. `hour_utc` | dubl. `hour_dk` | `unixtime`→UTC == `hour_utc` |
|---|---|---|---|---|---|---|
| 2025-03-30 | fyn / karup / vestkyst | 24 | 24 | **0** | **0** | **24/24** |
| 2026-03-29 | fyn / karup / vestkyst | 24 | 24 | **0** | **0** | **24/24** |

Forårsskiftet er ubelastet. En time springes over i lokal tid, men da UTC er
kontinuert, opstår der ingen kollision. **Kun efterårets tilbagestilling er
ramt** — hvilket matcher at Gate 0.5 kun fandt oktober-huller.

---

# MÅLT vs. USIKKERT

## MÅLT

- 5 354 talsammenligninger på tværs af fem datasæt: **nul afvigelser**.
- §11.1's syv mapping-rækker: alle bekræftede.
- `auction` findes på `mfrr_capacity` og mangler i klonen.
- DECIMAL → JSON-streng, INT → tal. `format=csv` nødvendig.
- Bar `enddate`-dato er inklusiv hele døgnet; eksplicit tidsstempel er eksklusivt.
- Uden `enddate` når begge kapacitetstabeller 29,7 timer frem;
  `to_exclusive_source` findes og skifter korrekt.
- Ukendt parameter: 400 på `api_eds_balance.php`, **ignoreret** på
  `api_energinet_prices.php`.
- `tz` afvises af `api_eds_balance.php`; de tre øvrige endpoints har den, to
  med default `dk`.
- `has_more`/`next_offset` virker; `limit=10001` falder tavst tilbage til 1000.
- `update_spot` kalder EDS `DayAheadPrices` uden områdefilter og rører aldrig
  `api_entsoe_prices.php`.
- Korte områdekoder giver 400 med eksplicit besked.
- 2025-12-15: kun `DE_LU`, `DK_1`, `DK_2`, `FR` har data.
- `unixtime` entydig i alle målte tilfælde; `hour_utc` udledbar klientside.
- Forårsskiftene 2025-03-30 og 2026-03-29 er fejlfrie i alle tre stationer.
- df-data urørt; 28 tests grønne; 48 kald, ingen PHP-fejl i nogen krop.

## USIKKERT

1. **Om `auction='extra'` nogensinde optræder.** Spec'en har enum'en, og
   spec-teksten siger *"Pr. august 2026 findes kun `main` i data"*. Kun ét
   vindue er målt. Optræder `extra`, fordobles rækker pr. tidsstempel.
2. **Om værdiidentiteten holder uden for 2026-03-15/16.** Ét vindue pr.
   datasæt er målt. Perioder hvor EDS har revideret data efter klonens
   hentning kunne afvige.
3. **Om 26/29-timers-skellet nogensinde har været reelt.** Målt ens for begge
   tabeller på én dag.
4. **Hvorfor `NO_2`/`SE_3`/`SE_4` er tomme i entsoe-endpointet.** Ikke
   undersøgt — ville kræve kald uden for de navngivne endpoints.
5. **Om EDS `DayAheadPrices` stadig leverer DE/NO2/SE3/SE4.** Ikke målt; EDS er
   ikke blandt de navngivne endpoints i denne gate. Det er den måling der
   endeligt afgør om DE-hullet er en EDS-mangel eller en hentefejl.
6. **`id`-kolonnens afvigelse i spot.** Målt at den afviger, ikke undersøgt
   hvorfor. §11.3 dropper den alligevel.

---

# KONKLUSIONER

## 1. Holder §11.1's mapping?

**Ja — alle syv rækker er bekræftet, ingen er forkerte.** Men tabellen dækker
7 af 59 kolonner og udelader tre ting der har konsekvenser: `auction` på
`mfrr_capacity` (ny dimension), `created_at`/`updated_at` (skal droppes), og
at akronym-konverteringen ikke er mekanisk og derfor skal skrives eksplicit ud.

## 2. Er værdierne identiske, eller er eget API et andet datasæt?

**Identiske. Samme datasæt, celle for celle.** 5 354 talsammenligninger, nul
afvigelser, max Δ = 0. Tomme felter er tomme begge steder. `time_dk` og
`price_area` matcher også. F6 er derfor en ren omdøbning for balance og spot —
ikke et kildeskifte med indholdsrisiko.

## 3. Hvilke af §10.3's fem kontraktforskelle holder?

| # | påstand | udfald |
|---|---|---|
| 1 | Halvåbent `[startdate, enddate)` | **FORKERT som skrevet.** Bar dato er inklusiv hele døgnet. Rådet om at sætte `enddate` til dagen efter ville give et døgn for meget. |
| 2 | `enddate` må ikke udelades for kapacitetstabellerne | **Holder.** `to_exclusive_source` findes og virker. Men 26/29-skellet er ikke genfundet — begge når 29,7 t frem. |
| 3 | Ukendte parametre giver 400 | **Holder kun for `api_eds_balance.php`.** `api_energinet_prices.php` ignorerer dem. |
| 4 | Kun UTC, ingen `tz` | **Holder for `api_eds_balance.php`.** Må ikke generaliseres — to af de fire endpoints defaulter til `dk`. |
| 5 | Pagination via `has_more`/`next_offset`, `limit` maks. 10000 | **Holder,** men `limit>10000` falder tavst tilbage til default 1000 i stedet for at afvise. |

## 4. Hvad F6 Gate 1 kan tage for givet — og ikke

**Kan tages for givet:**

- Værdierne er identiske. Migrationen skal ikke validere indhold, kun navne.
- §11.1's syv mapping-rækker er korrekte.
- `format=csv` løser typeproblemet.
- `unixtime` er en entydig nøgle for DMI, og `hour_utc` kan udledes klientside.
- Forårets DST-skift kræver ingen særbehandling.
- `to_exclusive_source` kan bruges som den assert §10.3 foreslår.

**Kan ikke tages for givet:**

- **`enddate`-semantikken.** Skal implementeres efter målingen, ikke efter
  §10.3. Anbefaling: send altid eksplicit tidsstempel, aldrig bar dato — så er
  reglen entydigt eksklusiv og der er intet at huske.
- **At endpointene har samme kontrakt.** De har det ikke: `tz`, ukendte
  parametre og default-tidszone varierer. Hvert endpoint skal kaldes efter sin
  egen spec.
- **`auction`-dimensionen.** Skal håndteres eksplicit i skema og dedup-nøgle.
- **`limit`-fælden.** Send aldrig >10000; valider `meta.limit` mod det sendte.
- **At mappingen kan genereres.** Den skal skrives i hånden og testes.

---

# HVILKE DATASÆT KAN IKKE MIGRERES

**Tre, og de skal navngives hver for sig fordi årsagerne er forskellige.**

### 1. `spot/NO2_*.csv`, `spot/SE3_*.csv`, `spot/SE4_*.csv` — **kan ikke migreres**

`api_entsoe_prices.php` returnerer **0 rækker** for `NO_2`, `SE_3` og `SE_4` på
alle testede datoer, inklusive datoer hvor klonen har fulde data. En migration
til dette endpoint ville erstatte eksisterende historik med ingenting.

**Dette er en regression forklædt som oprydning i sin reneste form.** Filerne
skal bevares som de er, og hentevejen for dem må ikke pege på
`api_entsoe_prices.php` før nogen har fundet en kilde der faktisk leverer dem.

### 2. `spot/DE_*.csv` — **kan migreres, men skifter skema og taber DKK**

`api_entsoe_prices.php` har data for `DE_LU`, også midt i klonens hul. Men
skemaet er `timestamp, area, price_eur_mwh, resolution_minutes` — **ingen
DKK-kolonne**, mens `DE_2026.csv` har `spot_price_dkk`. Migrationen kræver at
Q6 besvares først: med hvilken kurs er den eksisterende DKK-kolonne beregnet?
Uden det svar er migrationen et tab af information, ikke en oprydning.

### 3. `spot/SYSTEM_*.csv` — **har ingen migrationsvej overhovedet**

Ikke nævnt i §10.2's kildetabel. `api_energinet_prices.php` har enum
`['DK1','DK2']`; `api_entsoe_prices.php` har ikke SYSTEM i sin
`available_areas`. Filerne findes i klonen (2022–2025-02-06). **Der er ingen
kilde i den nye kildetabel der kan levere dem.** Enten skal de bevares
uændret, eller også skal det besluttes eksplicit at de udgår.

### Fuldt migrerbare

`imbalance`, `mfrr_act`, `mfrr_cap`, `afrr` (alle DK1/DK2), `spot/DK1`,
`spot/DK2`, og `dmi` (alle tre stationer) — værdiidentitet bekræftet eller
uændret endpoint.
