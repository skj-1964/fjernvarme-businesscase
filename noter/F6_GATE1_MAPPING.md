# F6 Gate 1 — kolonne-mappingen v1 → v2, skrevet i hånden

**Status:** Read-only med netværk. 40 API-kald, alle 200 undtagen ét bevidst
400 (auction-enum-probe). Ingen PHP-fejl i nogen krop.
df-data-klonen urørt: `6c95bde` før og efter, tom `git status`.
**Tests:** 104 passed, 1 skipped — de 28 eksisterende er fortsat grønne.
**Leverancer:** `src/schema_v2.py`, `tests/test_schema_v2_mapping.py`.
**Opslagsværk:** `noter/DATADISTRIBUTION_IMPLEMENTERING_V1.md` — brugt som
opslagsværk, ikke facit.
**Referencedag for alle API-kald:** **2026-03-15**, `format=csv`, samme dag som
Gate 0.
**Dato:** 2026-08-08

**Hovedfund:** Mappingen er komplet — alle 59+ kolonner på tværs af otte
datasæt er gjort rede for. Men tre ting kom frem undervejs som ingen tidligere
gate har haft:

1. **B2's andet regnestykke kan ikke gå op som formuleret.** Det rammer 7 af 8
   datasæt. Se afsnittet nedenfor — det er gatens vigtigste fund.
2. **Klonens `spot/` har tre forskellige headere, ikke én.** Gate 0's referat
   siger API og klon er identiske for spot; det gælder kun 6 af 34 spotfiler.
   `DE_2026.csv` har **EUR før DKK** hvor `DE_2025.csv` har **DKK før EUR**.
3. **DMI's DST-tab er målt i klonen, ikke kun i API'et.** Klonen mangler
   UTC-time 0 på 2023-10-29, 2024-10-27 **og** 2025-10-26.

---
---

# GATE 1g — BLOKKEREN LUKKET

**Status:** Kun `noter/` ændret. Ingen netværkskald, ingen kodeændringer.
Klonen urørt: `6c95bde` før og efter, tom `git status`.
**Tests:** 219 passed, 1 skipped — uændret fra Gate 1e.
**Dato:** 2026-08-09

Gate 1f fandt én blokker for udgivelse: denne fil gengav to af Billunds
faktiske afregningsbeløb — skrevet ind i Gate 1e som *bevis* for hvorfor
facit skulle holdes ude af hvidlisten, i en fil der selv står på hvidlisten.
Argumentet var rigtigt; eksemplet var selvmodsigende.

**Fire indgreb, alle i `noter/`:**

| # | fil | hvad |
|---|---|---|
| A1 | `F6_GATE1_MAPPING.md` L53–54 | de to beløb erstattet af en beskrivelse af filernes form. Hvidliste-argumentet står uændret. |
| A3 | `F6_GATE1_MAPPING.md` L1029, L1035–37 | `/var/spool/cron/crontabs/`-stien og rettighedsfejlen udgår. Målingen — **0 træffere**, ingen scheduler — bevares, og forbeholdet om ikke-læsbare job står stadig, uden sti. |
| A4 | `DATADISTRIBUTION_IMPLEMENTERING_V1.md` L6 | forecastmodellens placering på filsystemet erstattet af en neutral formulering. Afgrænsningen står. |

**Eftermåling (A2).** Alle beløb ≥ 1000 fra de fire
`billund_balance_facit_*.csv` (162 forekomster, 157 unikke, læst som
CSV-celler — periodekolonnen `maaned` tæller ikke som beløb) søgt mod alle ti
hvidlistede noter i tre passager:

| passage | træf |
|---|---|
| råt (med og uden tusindseparator: `.` `,` mellemrum, hårdt mellemrum) | **0** |
| separatorer fjernet, snævert (kun ægte tusindgrupper) | **0** |
| separatorer fjernet, bredt (enhver separator mellem to cifre) | 25 |

De 25 er alle den **samme** værdi og den samme falsk-positiv-klasse: én
firecifret MWh-celle hvis cifre genfindes på tværs af mellemrummet mellem dato
og klokkeslæt i et tidsstempel, når det mellemrum fjernes. Ingen af dem er et
beløb i en note. (Værdien gengives ikke her — det var netop fejlen A1 lukkede.)

Alle søgninger krævede ciffergrænse, så et tal ikke kan matche inde i et
længere tal.

---
---

# GATE 1e — OPRYDNING FØR MIGRATION

**Status:** Små, afgrænsede skriv. **Ingen netværkskald.**
Klonen urørt: `6c95bde` før og efter, tom `git status`.
**Tests: 219 passed, 1 skipped** (udgangspunkt 201/1).
**Leverancer:** `.gitignore`, `src/schema_v2.py`, `tests/test_schema_v2_mapping.py`.
**Dato:** 2026-08-09

## ⚠ AFVIGELSE FRA A1 — noter/ er IKKE frigivet i sin helhed

A1 siger: *"Ret .gitignore, så noter/ versioneres."* Det har jeg ikke gjort
ubetinget, og grunden står i den linje jeg fjernede:

> `# Lokale noter, STATUS-filer og Billunds kommercielle afregningsdata (facit).`

`noter/` rummer fire filer med **Billunds faktiske månedsindtægter i DKK**:

```
noter/billund_balance_facit_H2_2025_oversigt.csv
noter/billund_balance_facit_H2_2025_tidy.csv
noter/billund_balance_facit_Q1_2026_oversigt.csv     (mode 0600)
noter/billund_balance_facit_Q1_2026_tidy.csv         (mode 0600)
```

Indholdet er ikke afledt eller anonymiseret: én række pr. måned pr. post,
med aktiverings-, kapacitets- og balancebeløb i hele kroner, direkte fra
afregningen. Dertil gengiver
mindst `notat_capture_rate_q1_2026.md` tallene i tabelform (*"Facit akt EAM
(DKK)"*).

At un-ignorere `noter/` ville lægge en navngiven tredjeparts kommercielle
afregningsdata i et repo der pushes til GitHub. **Det er ikke min beslutning
at træffe på dine vegne**, og det er heller ikke det A1 er ude efter — A1 vil
redde det målte grundlag.

**Hvad jeg gjorde i stedet:** hvidliste. `noter/*` er fortsat ignoreret, og de
ti F-spors-dokumenter er undtaget eksplicit. Jeg har verificeret at ingen af
dem nævner `facit` i talmæssig forstand og at "Billund" kun optræder som
case- og confignavn (`billund_sporB_q1_2026.yaml`).

**Hvorfor hvidliste og ikke sortliste:** en sortliste (`noter/*facit*`) ville
slippe den næste facit-fil igennem i tavshed. Hvidlisten fejler i den sikre
retning: en ny fil i `noter/` er ignoreret indtil nogen aktivt tilføjer den.

**Vil du have resten med alligevel**, er det én linje — erstat blokken med
`!noter/` under `noter/*`. Så er beslutningen truffet af den der må træffe den.

Bemærk formen `noter/*` frem for `noter/`: med skråstreg descender git ikke ned
i mappen, og en `!`-undtagelse under den ville aldrig virke. Det er den
klassiske fælde ved at un-ignorere en mappe.

---

# DEL A (1e) — REDNING AF DET MÅLTE GRUNDLAG

## A1 — `noter/` hvidlistet

Ti dokumenter undtaget: `DATADISTRIBUTION_IMPLEMENTERING_V1.md`,
`F6_GATE1_MAPPING.md`, `notat_f1_gate0_daekningsvagt.md`,
`notat_f1_gate05_oploesning_akse.md`, `notat_f1_gate1_test.md`,
`notat_f1_gate2_implementering.md`, `notat_f1_gate3_akse_ned.md`,
`notat_f1bc_akse_og_rapport.md`, `notat_f6_gate0_api_vs_klon.md`,
`notat_f8_gate0_kildemaaling.md`.

Fortsat ignoreret: de fire facit-CSV'er, alle `STATUS_*`, alle balance-/Spor
B-notater, `prompt_claude_code_cap14_backtest.md`. Verificeret med
`git check-ignore`.

## A2 — `out/` tilføjet

`.gitignore` dækkede kun `output/`. `run_case.py`'s `--outdir` er brugt med
begge navne, så 41 filer — heraf 7 `.nc`-binærer — lå utrackede og ville være
røget med. Verificeret ignoreret efter ændringen.

## A3 — hvad et push nu ville medtage

**Ændrede sporede filer — 5, +428/−79:**

| fil | ± |
|---|---|
| `.gitignore` | 33 |
| `run_case.py` | 81 |
| `src/data_loader.py` | 135 |
| `src/data_loader_github.py` | 228 |
| `src/reporting.py` | 30 |

**Utrackede — 17 (var 48):**

* `src/schema_v2.py`
* `tests/` — 6 filer: `__init__.py`, `conftest.py`, `test_coverage_guard.py`,
  `test_coverage_guard_e2e.py`, `test_schema_v2_mapping.py`,
  `test_time_axis.py`
* `noter/` — de 10 hvidlistede F-spors-dokumenter

**Ikke længere med:** 41 filer under `out/`, 20 filer under `noter/`.

Testsuiten er stadig det tungeste: **219 tests findes kun på denne maskine**
indtil de committes.

---

# DEL B (1e) — MÅLEINSTRUMENT KONTRA ARBEJDSKOPI

## B1 — hvem bruger stien, og til hvad

`data/df-data` (68 MB) tjener **fire** formål gennem **fire uafhængige**
stiangivelser. Kun én af dem er en konstant:

| sted | form | rolle |
|---|---|---|
| `src/data_loader_github.py:60` | `DEFAULT_DF_DATA_CACHE = "data/df-data"` | **konstanten** |
| `scripts/calibrate_heat_load.py:182` | `default="data/df-data"` | **hardkodet dublet** |
| `tests/conftest.py:17` | `REPO_ROOT / "data" / "df-data"` | **hardkodet dublet** |
| `tests/test_schema_v2_mapping.py:36` | `parents[1] / "data" / "df-data"` | **hardkodet dublet** |

**Læsevejen (produktion).** `_ensure_df_data_cache` (`:90`) kloner `--depth 1`
ved første kald og returnerer derefter mappen uden netværkskald.
`load_external_data_github` (`:552`) kalder den og læser `spot/`, `dmi/`,
`afrr/`, `mfrr_cap/`, `mfrr_act/`, `imbalance/`. `run_case.py:130` eksponerer
den som `--df-data-cache`.

**Målevejen (tests).** `conftest.py` giver to session-fixtures: `df_data`
(stien) og `df_data_head` (kort SHA + dato, brugt i assert-beskeder fordi
manifestet ikke registrerer dataversionen). En autouse-fixture **skipper** alt
hvis `.git` mangler. `test_schema_v2_mapping.py` har sin egen `pytestmark`-skip
og bruger slet ikke fixturen.

**Skrivevejen (menneske).** Reflog'en viser `commit` + `update by push` fra
mappen 2026-08-04 og 2026-08-07. `6c95bde` — det commit alle målinger hviler
på — blev skabt dér.

**Målt tal der afgør sagen: 208 af 220 tests (95 %) læser klonen, og de
skipper alle i tavshed hvis den mangler.**

## B2 — forslag til adskillelse (forslag, ikke bygget)

**Kernen:** to mapper med hver sin rolle, og en pin der er en *påstand*, ikke
et tilfælde.

| | sti | rolle | skrives i |
|---|---|---|---|
| måleinstrument | `data/df-data-pin/` | pinnet til `6c95bde` | **aldrig** |
| arbejdskopi | `data/df-data/` | commit/push, `update_data.py` | frit |

**Hvad der skal ændres:**

1. **`tests/conftest.py`** — én sandhed for testenes sti og pin:
   ```
   DF_DATA_PIN_SHA = "6c95bde23ecaaf5d2feabbd74ec4345778e775a1"
   DF_DATA_DIR = Path(os.environ.get("DF_DATA_PIN", REPO_ROOT / "data/df-data-pin"))
   ```
2. **Pin-kontrol i den eksisterende autouse-fixture.** Findes mappen, skal
   `HEAD` være `DF_DATA_PIN_SHA` — ellers **fail**, ikke skip. Det er hele
   pointen: en klon på et andet commit er ikke et fravær, det er et forkert
   måleinstrument.
3. **`tests/test_schema_v2_mapping.py:36`** — importér `CLONE` fra `conftest`
   i stedet for at regne stien ud igen. Så findes stien ét sted i tests.
4. **`scripts/calibrate_heat_load.py:182`** — brug `DEFAULT_DF_DATA_CACHE`
   i stedet for strengen. Uafhængigt af resten, og en ren forbedring.
5. **`.gitignore`** — tilføj `data/df-data-pin`.
6. **Bootstrap.** `git clone --depth 1` giver ikke nødvendigvis `6c95bde`, når
   `main` er rykket videre. Vejen er
   `git clone --filter=blob:none <url> data/df-data-pin && git -C … checkout 6c95bde`,
   eller `git fetch origin <sha> --depth 1`. Det skal stå i `conftest`'s
   skip-besked, ligesom den nuværende gør.
7. **CI-knap.** `DF_DATA_REQUIRED=1` → skip bliver til fail. Uden den er
   forslaget halvt: en manglende pin lader 208 tests forsvinde lydløst, og det
   er den fejl adskillelsen skal fjerne, ikke flytte.

**Hvad der går i stykker hvis stien ikke findes:**

* **I dag:** 208 tests skipper. Suiten er grøn. Ingen siger noget. Det er
  tilstanden i dag og den værste af mulighederne.
* **Efter forslaget uden punkt 7:** det samme — derfor er punkt 7 ikke valgfri.
* **Efter forslaget med punkt 7:** lokalt skipper de med en besked der viser
  den præcise klonkommando; i CI fejler de.
* **Produktionsvejen er upåvirket.** `run_case.py` bruger `--df-data-cache`
  og rører ikke pin-mappen.

**Pris:** 68 MB ekstra på disk, og et ekstra klonetrin ved opsætning. Til
gengæld kan `update_data.py` køres i arbejdskopien uden at flytte grundlaget
under 208 tests — hvilket i dag kun er forhindret af at ingen har gjort det.

**Ikke bygget.** Ændringen rører `tests/conftest.py`, som denne gates
afgrænsning ikke omfatter, og pinnen bør indføres i samme greb som Gate 2's
loader — ikke før.

## B3 — fraværet af automatisk pull, skrevet ind som egenskab

`schema_v2.NO_AUTO_PULL`. Tre begrundelser (klonen er måleinstrument for 201+
tests målt mod ét commit; datarepoet versioneres uafhængigt og manifestet
registrerer det ikke; reproducerbarhed uden udgående net) og to konkrete
skader hvis nogen "retter" det (`force_refresh=True` som default → `rmtree` på
klonen ved hver kørsel; et `git pull` i `_ensure_df_data_cache` → testene måler
mod et andet commit end deres indfrosne tal, og fejlbeskederne peger på koden).

En test (`test_fravaeret_af_auto_pull_er_beskrevet_som_egenskab`) kræver at
`MÅLEINSTRUMENT`, `6c95bde` og `force_refresh` stadig står i teksten.

---

# DEL C (1e) — SPOT_ENTSOE DEGRADERET

## C1 — spærret, med en anden grund end spot_system

`DatasetSchema` har nu `migratable: bool` og `not_migratable: str`, og
`MIGRATIONSSPAERRER` udleder listen. To datasæt står der, og forskellen er
afgørende for hvad der skal gøres:

| datasæt | grund | kan spærren åbnes? |
|---|---|---|
| `spot_system` | **INGEN KILDE** — intet endpoint har området, og EDS `Elspotprices` dækker ikke perioden | nej, ikke uden en ny kilde |
| `spot_entsoe` | **MÅLET DUER IKKE** — kilden findes og svarer forkert | ja, ved at rette et endpoint |

En test kræver at de to begrundelser forbliver forskellige. Smelter de sammen,
forsvinder netop den skelnen.

## C2 — `api_to_v2` er UBRUGELIG, ikke uafklaret

Forskellen er handlingsbærende: **en uafklaret mapping ligger og ser rigtig ud,
indtil den bliver brugt.** Derfor er den tømt, ikke mærket.

* `SPOT_ENTSOE.api_to_v2` er nu `{}` — bruger nogen den, får de **intet**,
  ikke noget forkert
* alle fire API-kolonner står i `api_dropped` med samme begrundelse,
  `_WHY_ENTSOE_REJECTED`, fordi det er **én** beslutning og ikke fire
* den målte mapping er bevaret i det nye felt `api_to_v2_rejected`, hvor den
  kan læses uden at kunne bruges
* `api_path_rejected` bærer begrundelsen

Fire tests dækker det: `api_to_v2` skal være tom, begrundelsen skal findes,
API-siden skal være fuldt gjort rede for, og intet v2-navn må kunne stamme fra
den forkastede vej uden også at kunne komme fra klonen.

**Følgen ingen bad om, men som fulgte med:** `resolution_minutes` stod i
`ADDED` — altså *"kun API'et kan levere den"*. Da vejen blev forkastet, var der
ingen kilde tilbage. **Kolonnen er udgået af `spot_entsoe.v2_columns`.** En
kolonne uden kilde må ikke blive stående; så skulle Gate 2 finde på den, og
det er præcis den syntetisering `ENDPOINTS_WITH_RESOLUTION_MINUTES` findes for.
Målingen af at endpointet *leverer* den står stadig — det er en sand oplysning
om et endpoint vi bare ikke bruger.

Det flytter enhedstallene: **74 v2-kolonner, 41 uden enhed** (var 75/42).

## C3 — målingen bevaret som begrundelse

`SPOT_ENTSOE.notes` bærer stadig +1 t i marts, +2 t i juli,
`Europe/Copenhagen`, og 96/96 mod 1/96 og 0/88. En test
(`test_maalingen_bag_forkastelsen_staar_i_modulet`) kræver hvert af de fire
spor.

Uden tallene er forkastelsen en påstand, og den næste der ser endpointet vil
prøve igen. `UNRESOLVED` skelner nu mellem **følgen** (afgjort: vejen
forkastes) og **årsagen** (ikke fundet — og bør meldes til den der
vedligeholder endpointet, ellers rammer den nogen igen).

---

# DEL D (1e) — DE TO BESLUTNINGER SKREVET IND

Ny tuple `schema_v2.DECISIONS`. Ikke forslag længere — men heller ikke bygget:
alt nedenfor er Gate 2's arbejde.

## D1 — proveniens

**Kildekolonne pr. række**, med **header-fingeraftryk** som sekundær vagt.
De to erstatter ikke hinanden: headeren fanger et skift **over** stregen,
kildekolonnen et skift **under** den — og det er den sidste vi beviseligt har
haft (`spot/DK1_2026.csv`, to skemaer under én header).

**Forudsætningen er skrevet ind som forudsætning:** kolonnen kan kun bæres hvis
API'et leverer den — **krav 3.4 i API-udvidelsen**. Leverer det den ikke, er
beslutningen ikke gennemførlig, og header-fingeraftrykket står alene. Det er
svagere, og det skal siges højt frem for at blive opdaget. En test kræver at
både `3.4` og `FORUDSÆTNING` stadig står i teksten.

Historiske rækker backfilles ikke, af samme grund som `auction` ikke gør.

## D2 — versionsvagt

`update_data.py` læser `DATA_VERSION.md` **før ethvert netværkskald** og
afbryder ved uenighed. Fejlbeskeden skal nævne **begge** versioner og hvilken
vej uenigheden går — *"scriptet er nyere end repoet"* og *"repoet er nyere end
scriptet"* kræver forskellig handling af mennesket.

**Manglende eller tomt felt** — og feltet findes i dag **slet ikke** i
`DATA_VERSION.md` — **afbryder**, med en engangsudvej `--adopt-schema=v1` der
skriver feltet og ikke gør andet. Mennesket erklærer versionen; værktøjet
gætter den ikke. At antage v1 automatisk ville være samme fejl som at
backfille `auction`, og ville skrive `v1` oven på `DK1_2026.csv`, som
beviseligt ikke er rent v1.

**Læs før hentning, ikke efter:** afbryder vagten bagefter, er der brugt kvote
hos EDS på et svar der kastes væk, og EDS' rate limit er ukendt.

**Kan ikke bygges herfra:** `update_data.py` ligger i df-data.

---

# DEL E (1e) — REGRESSION

## E1 — de fire relationer

```
datasæt            v1           L1  API           L2  v2           L3   L3-spejlet  ok
--------------------------------------------------------------------------------------
imbalance_price    18      17+1=18   20      17+3=20  17    17+0+0=17    17+0+0=17  ✓
mfrr_activation    19      18+1=19   21      18+3=21  18    18+0+0=18    18+0+0=18  ✓
mfrr_capacity      11      10+1=11   14      11+3=14  11    10+1+0=11    11+0+0=11  ✓
afrr_capacity      11      10+1=11   13      10+3=13  10    10+0+0=10    10+0+0=10  ✓
spot_dk           5/8        4+4=8    8        4+4=8   4      4+0+0=4      4+0+0=4  ✓
spot_entsoe       5/5        4+1=5    4        0+4=4   4      4+0+0=4      0+4+0=4  ✓  ← spærret
dmi_obs            11       9+2=11   11       9+2=11  10     9+0+1=10     9+0+1=10  ✓
spot_system         5        0+5=5    0        0+0=0   0      0+0+0=0      0+0+0=0  ✓
```

**Alle fire holder for alle otte datasæt.** Kun `spot_entsoe` har flyttet sig,
og bevægelsen er hele C-beslutningen aflæst i tal:

| | Gate 1d | Gate 1e |
|---|---|---|
| L2 (API) | `4+0=4` | **`0+4=4`** — intet mappes, alt droppes |
| v2 | 5 | **4** — `resolution_minutes` mistede sin kilde |
| L3-spejlet | `4+1+0=5` | **`0+4+0=4`** — API-vejen bidrager intet, klonen alt |

L3-spejlet siger nu det samme som `migratable=False`: **API-vejen kan ikke
producere en eneste v2-kolonne.**

## E2 — testsuiten

**219 passed, 1 skipped.** Udgangspunktet var 201/1.

Fem eksisterende tests fejlede undervejs, alle som direkte følge af
C-beslutningen. Jeg rettede dem ikke for at få grønt, men fordi den påstand de
håndhævede var blevet forkert:

| test | var | er |
|---|---|---|
| `test_resolution_minutes_syntetiseres_ikke` | endpointet leverer den → skal være i v2 | vejen er forkastet → må **ikke** være i v2 |
| `test_kun_spot_entsoe_har_en_ikke_triviel_api_mapping` | præcis én ikke-identitet | **ingen** — undtagelsen lever i `api_to_v2_rejected` |
| `test_spot_mappen_har_eet_navn_pr_akse_og_pr_maal` | slår op i `api_to_v2` | slår op i `api_to_v2_rejected` |
| `test_antallet_uden_enhed_er_frosset` | 42/75 | **41/74** |
| `test_enheden_udledes_ikke_af_navnet` | nævnte `resolution_minutes` | kolonnen findes ikke længere |

18 nye tests. De to der bærer mest: `test_forkastet_api_vej_er_ubrugelig_ikke_uafklaret`
(C2) og `test_de_to_spaerrer_har_forskellig_grund` (C1).

Den ene skip er uændret: `test_A2_documents_what_head_returns_instead`.

---

# USIKKERT (1e)

1. **Hvilke `noter/`-filer du faktisk vil dele.** Jeg har hvidlistet de ti
   F-spors-dokumenter, fordi de er det målte grundlag A1 vil redde, og
   udeladt alt der rører facit. Grænsen er min vurdering, ikke en måling.
   `STATUS_2026-08-07.md` er et grænsetilfælde — projektstatus, ikke facit,
   men heller ikke gate-måling.
2. **Om `fjernvarme-businesscase` er et privat eller offentligt repo.** Gaten
   forbød netværkskald, så jeg kunne ikke slå det op. Det ændrer alvoren af
   punkt 1 markant, ikke retningen.
3. **Om `out/` skal ignoreres eller committes.** Prompten kalder de 41 filer
   "målt ubrugelige som baseline"; jeg har ikke selv målt det og har fulgt
   instruktionen. Er nogen af dem et referenceresultat nogen vil sammenligne
   mod senere, er de nu usynlige for git.
4. **C2's form.** "UBRUGELIG, ikke uafklaret" kunne også være læst som en ren
   markering med `api_to_v2` intakt. Jeg tømte den, fordi en test ikke kan
   opdage fremtidig brug — men en tom mapping gør brugen virkningsløs. Det er
   en fortolkning, og den er større end en markering.
5. **`resolution_minutes`' bortfald** fulgte af C1/C2 og var ikke bedt om.
   Alternativet var at lade en kolonne uden kilde stå i `v2_columns`, hvilket
   er værre. Skal opløsningen med over, må den komme fra API-udvidelsen.
6. **B2 er ikke bygget og ikke prøvet.** Særligt punkt 6 (bootstrap af en
   pinnet, shallow klon på et bestemt SHA) er skrevet ud fra hvordan git
   opfører sig, ikke fra en kørsel — gaten forbød netværkskald.

---
---

# GATE 1d — A4 LUKKET, ENDPOINT-KONTRAKTEN SOM DATA, ENHEDER

**Status:** Read-only undersøgelse + skriv i `src/schema_v2.py` og `tests/`.
~70 netværkskald, alle mod `api.sysapp.dk` og `api.github.com`. Ingen EDS-kald,
altså **ingen 429 i denne gate**. Ingen PHP-fejl i nogen krop.
Klonen urørt: `6c95bde` før og efter, tom `git status`.
**Tests: 201 passed, 1 skipped** (udgangspunkt 141/1 — 60 nye, ingen brudt).
**Dato:** 2026-08-08

## HOVEDFUND: `api_entsoe_prices.php` leverer dansk lokaltid, ikke UTC

`SPOT_ENTSOE.api_to_v2` afbilder `timestamp` → `hour_utc`. **Det er målt
forkert.** Kolonnen er dansk lokaltid.

Målt tre gange, mod to uafhængige kilder, på både en vinter- og en sommerdag:

| krydstjek | join på UTC-aksen | join på dansk-aksen |
|---|---|---|
| mod `api_energinet_prices.php`, 2026-03-15 | 92 rækker, **1/92** identiske, maks Δ = 39,92 | 96 rækker, **96/96**, maks Δ = **0** |
| mod `api_energinet_prices.php`, 2026-07-15 | 88 rækker, **0/88** identiske, maks Δ = 70,01 | 96 rækker, **96/96**, maks Δ = **0** |
| mod klonens `spot/DK1_2026.csv` | 96 rækker, **1/96** identiske, maks Δ = 41,15 | 96 rækker, **96/96**, maks Δ = **0** |

Forskydningen er **+1 t i marts og +2 t i juli** — altså `Europe/Copenhagen`,
ikke fast CET.

Endpointets eget `meta` hævder `"timezone": "utc"`. Målingen vinder.

**Mappingen er IKKE rettet her**, og det er med vilje. Begge udveje er
beslutninger, ikke oprydning:

* konvertér til UTC → en **beregnet kolonne**, som Gate 1 forbød
* omdøb til `hour_dk` → **lokaltid i v2**, som `_WHY_LOCAL_TIME` forbyder

Den står derfor i `UNRESOLVED` med en test der forhindrer at den forsvinder
derfra. **Gate 2 må ikke bruge `SPOT_ENTSOE.api_to_v2`, før valget er truffet.**

---

# DEL A (1d) — A4 LUKKET

## A1 — cachen: bekræftet mekanisme, men den er også en arbejdskopi

`src/data_loader_github.py:90` `_ensure_df_data_cache` er som beskrevet:

* eksisterer `cache_dir/.git` → **returnér straks, uden netværkskald**
* ellers → `git clone --depth 1`
* `force_refresh` → `shutil.rmtree` og klon igen

Docstringen siger det selv: *"brug eksisterende klon uden netværkskald (ingen
`git pull`, så sandkassekørsler er reproducerbare)"*. Grep bekræfter det:
**der findes ingen `git pull` eller `git fetch` nogen steder i koden.** Det
eneste `subprocess`-git-kald i loaderen er `clone`.

Det er mekanismen der har holdt `6c95bde` stille gennem alle gates.
**Fjernes den `if cache_dir.exists()`-gren, eller sættes `force_refresh` som
default, mister 28 dækningstests deres måleinstrument uden at fejle først.**

**Men præmissen i A1 holder ikke helt.** Klonens egen reflog viser at mappen
også bruges som arbejdskopi — af et menneske, ikke af koden:

```
6c95bde HEAD@{2026-08-07 12:03:17}: commit: Ret tidsmaerkningen i dmi/*.csv
decd48f HEAD@{2026-08-04 09:36:01}: rebase (finish): returning to refs/heads/main
ff04514 HEAD@{2026-08-04 09:35:56}: commit: Hent fra api.sysapp.dk i stedet for www.sysapp.dk
1b813de HEAD@{2026-06-17 15:58:37}: clone: from https://github.com/skj-1964/df-data.git
```

```
6c95bde origin/main@{2026-08-07 12:03:28}: update by push
decd48f origin/main@{2026-08-04 09:36:07}: update by push
137011b origin/main@{2026-08-04 09:34:25}: fetch origin: fast-forward
```

Klonen er skabt af `_ensure_df_data_cache` (dybde 1, 2026-06-17, samme sti,
`.git/shallow` peger på `1b813de`). Derefter er der **committet og pushet fra
den to gange** — 2026-08-04 og 2026-08-07. Begge df-data's nyeste commits er
altså skrevet **på denne server**.

Det ændrer ikke A1's konklusion om automatik: der er ingen. Det ændrer hvem der
rører mappen.

## A2 — `scripts/update_data.py` har aldrig ligget i businesscase-repoet

Prompten beder om historikken for `scripts/update_data.py` **i
businesscase-repoet**. Den findes ikke:

* businesscase-historikken er **fuld**, ikke shallow (`.git/shallow` findes
  ikke), 34 commits, 4 refs
* `git log --all --diff-filter=A -- '*update_data.py'` → **tomt**
* `git log --all --name-only | grep update_data` → **tomt**
* `HEAD`-træets `scripts/` indeholder seks filer, ingen af dem `update_data.py`

Filen har kun nogensinde ligget i **df-data**. Hypotesen om "workstationen
kører businesscase fra en ældre pushet commit — en ældre `update_data.py`" kan
derfor ikke være rigtig som formuleret: businesscase har aldrig båret filen.

Eneste businesscase-commit der overhovedet nævner `api_energinet_prices` er
`b2f6418` (initial import) — det er `src/data_loader.py`'s **læsevej**, ikke en
skrivevej.

## A3 — hvad et push fra serveren ville medtage

**HEAD:** `3ea0399` "Flyt DMI-hentningen til api_dmi_obs_ny.php", branch `main`.

**HEAD er allerede pushet.** `HEAD...origin/main` = `0 0`, og reflog'en viser
`update by push` fra denne maskine 2026-08-07 12:03:35. Præmis 2's "aldrig
pushet" gælder ikke det committede — kun arbejdstræet.

*(Forbehold: `origin/main` er den lokalt kendte ref. Seneste `fetch` var
2026-08-04; jeg har ikke hentet for at se efter nyere fjern-commits.)*

**Ændrede, sporede filer (398 indsatte, 76 slettede):**

| fil | ± |
|---|---|
| `run_case.py` | 81 |
| `src/data_loader.py` | 135 |
| `src/data_loader_github.py` | 228 |
| `src/reporting.py` | 30 |

**Utrackede: 48 filer.** Fordelt:

* **41 filer under `out/`** — modelresultater, heraf 7 `.nc`-binærer.
  `.gitignore` ignorerer `output/`, **ikke `out/`**. De ville altså komme med.
* **`src/schema_v2.py`** — Gate 1's leverance
* **hele `tests/`-mappen, 6 filer** — `__init__.py`, `conftest.py`,
  `test_coverage_guard.py`, `test_coverage_guard_e2e.py`,
  `test_schema_v2_mapping.py`, `test_time_axis.py`

**Det sidste er værd at standse ved: hele testsuiten er utrackket.** De 201
tests findes kun på denne server. En workstation, der puller businesscase, har
ingen af dem.

`noter/` er gitignoreret — denne fil kommer aldrig med i et push.

## A4 — konklusion: **HYPOTESEN AFKRÆFTET.** Skriveren ligger før git.

Ikke "kan ikke afgøres". GitHub-historikken rækker hele vejen, og den lukker
spørgsmålet.

**Målt via GitHub-API'et (klonen urørt).** `skj-1964/df-data` har **9 commits i
alt**. `spot/DK1_2026.csv` er rørt af tre af dem:

| sha | dato | besked |
|---|---|---|
| `137011b` | 2026-06-29 | juni kørsel |
| `2c743ae` | 2026-05-11 | Data until 9th of May 2026 |
| `6cc7a69` | 2026-05-10 | Initial release: 2023-2026 data for DK1/DK2 + fyn/vestkyst |

**`spot/DK1_2026.csv` i allerførste commit `6cc7a69`:**

```
id,hour_utc,hour_dk,price_area,spot_price_dkk,spot_price_eur,created_at,updated_at
2001010,2026-01-01 00:00:00,2026-01-01 01:00:00,DK1,448.21,60.01,2025-12-31 13:15:02,2026-01-16 01:15:02
…
8383105,2026-03-31 21:45:00,2026-03-31 23:45:00,DK1,1056.61,141.39,2026-03-30 13:15:02,2026-04-16 01:15:02
```

8 632 rækker, **alle med `id`**, heltal, hele vejen fra 2026-01-01 til
2026-03-31 21:45. Variant C ligger der fra dag ét.

I næste commit `2c743ae` er filen vokset til 12 376 rækker, `id` er blevet
**flydende** (`2001010.0`) og de nye rækker fra 2026-03-31 22:00 har **tomme**
`id`/`created_at`/`updated_at` med `hour_dk` i ISO-`T`-format. Det er
`pd.concat`'s aftryk, og det er `update_data.py`'s `DayAheadPrices`-tilføjelse.

**Og ingen version af `update_data.py` kalder nogensinde proxyen for spot.**
Alle fem versioner i repoets historik hentet og læst:

| commit | dato | `update_spot` bruger |
|---|---|---|
| `6cc7a69` | 2026-05-10 | `fetch_eds("Elspotprices", …)` |
| `2c743ae` | 2026-05-11 | `fetch_eds("DayAheadPrices", …)` |
| `c07010d` | 2026-05-13 | (rører kun `DMI_AREAS`) |
| `1b813de` | 2026-05-13 | `fetch_eds("DayAheadPrices", …)` |
| `decd48f` | 2026-08-04 | `fetch_eds("DayAheadPrices", …)` |

`BASE_URL_PROXY` bruges **kun** til `api_dmi_obs.php` / `api_dmi_obs_ny.php`.

**Konklusion.** Proxy-rækkerne blev ikke skrevet af `update_data.py` — i nogen
version, på nogen maskine. De lå i filerne **da repoet blev oprettet**, lagt ind
ved den første import. Skriveren er dermed en engangshandling forud for git:
et udtræk fra sysapp-databasen (rækkernes `id` og `created_at` er databasens
egne), lagt i mappen inden `git init`.

Der er ikke noget mere at finde i git. **A5 er ikke nødvendig** som
tilbagefald — men dens måling er alligevel udført ovenfor og gav svaret.

Hvad der stadig ikke vides: hvilket værktøj der lavede det udtræk. Det spor
ligger uden for begge repoer.

---

# DEL B (1d) — ENDPOINT-KONTRAKTEN, SOM DEN STÅR I MODULET

`ENDPOINT_CONTRACTS` i `src/schema_v2.py`. Hvert felt bærer sin egen status.

| endpoint | filter_tz | end_boundary | ukendt param | limit (default/max) | resolution |
|---|---|---|---|---|---|
| `/api_eds_balance.php` | **utc** | inklusiv-hele-døgnet | **400** | 1000 / **10000** | nej |
| `/api_energinet_prices.php` | **dk** | inklusiv-hele-døgnet | **ignoreres tavst** | 1000 / *uafklaret* | nej |
| `/api_entsoe_prices.php` | *uafklaret* | inklusiv-hele-døgnet | ignoreres tavst | 1000 / *uafklaret* | **ja** |
| `/api_dmi_obs_ny.php` | **dk** | inklusiv-hele-døgnet | ignoreres tavst | 1000 / *uafklaret* | nej |
| EDS `DayAheadPrices` | **dk** | **eksklusiv** | *uafklaret* | – / *uafklaret* | nej |
| EDS `Elspotprices` | **dk** | *uafklaret* | *uafklaret* | – / *uafklaret* | nej |

`bare_date_semantics` er en fritekst pr. endpoint; de vigtigste er:

* **`api_eds_balance.php`**: `enddate=D` udvides til `D+1T00:00:00` eksklusiv.
  Målt: `startdate=enddate=2026-03-15` → 96 rækker, `time_utc` 00:00–23:45, og
  `meta.range_utc.to_exclusive = "2026-03-16 00:00:00"` med
  `to_exclusive_source: "enddate parameter"`. Et **eksplicit** tidsstempel er
  eksklusivt: `enddate=2026-03-16T00:00:00` → 96, `…T12:00:00` → 48.
* **EDS**: bar dato = `T00:00` **dansk tid**, udvides **ikke**.
  `start=end=D` → **0 rækker**. Det modsatte af proxyen.

## Fire ting kontrakten fanger, som ingen regel kunne

**1. `zone` findes ikke på `api_energinet_prices.php`.**
`zone=DK1` og `zone=DK2` giver **begge** 192 rækker med **både** DK1 og DK2.
Parameteren ignoreres uden fejl, og svaret ser gyldigt ud. Filteret hedder
`area`; `area=DK1` giver 96 rækker med kun DK1. Docstringen i
`src/data_loader.py:588` er dermed **målt korrekt**.

**2. `api_eds_balance.php` gør det stik modsatte** og forklarer selv hvorfor:

> `Unknown query parameter(s): zone. This endpoint rejects unknown parameters
> rather than ignoring them, because a silently ignored filter returns a
> plausible but wrong answer. Allowed: dataset, startdate, enddate, area,
> auction, format, fields, limit, offset.`

Samme vært, samme datoformat, modsat opførsel. Derfor en tabel, ikke en regel.

**3. `limit` over 10000 falder tavst tilbage til 1000.**
Bisekteret på `api_eds_balance.php` over et vindue med 8 640 rækker:

| limit | rækker |
|---|---|
| udeladt | 1 000 |
| 2 000 | 2 000 |
| 5 000 | 5 000 |
| **10 000** | **8 640** (alt i vinduet) |
| **10 001** | **1 000** ← |
| 20 000 / 999 999 | 1 000 |

`HTTP 200`, `"status": "success"`, og `meta` siger ingenting om det. **En
genhentning der beder om 20 000 rækker får 1 000 og et succes-svar.**
`offset=0/1000/2000` gav sammenhængende blokke, så paginering virker.

**4. Et tomt svar er ikke altid en tom CSV.**
`api_entsoe_prices.php?area=SE_3` og `NO_2` svarer `HTTP 200` med **0 bytes** —
ingen header. `pandas.read_csv` rejser `EmptyDataError`; en "ingen rækker"-gren
rammes aldrig.

## Sidegevinst: områdekoderne er nu målt udtømmende

`api_entsoe_prices.php` afviser `DK1` og `DE` med 400 og lister enum'en:
`DE_LU, DK_1, DK_2, FR, NO_2, SE_3, SE_4, NL, BE`. Den står også maskinlæsbart
i `meta.available_areas` og nu i `ENDPOINT_CONTRACTS[…].area_values`.

**Målsiden er dermed afklaret. Kildesiden er det ikke** — hvad klonens `DE`
skal afbildes til, og hvad der sker med `SYSTEM`, er stadig et valg.
`OPEN_QUESTIONS` er opdateret, ikke lukket.

## B2 — hvad 1c ikke fik målt

`Elspotprices`' **sub-daglige** eksklusivitet. Kaldet ramte 429 efter 6 forsøg,
og **et 429 er en udeblevet måling, ikke et tomt svar**. Døgnniveauet ER målt.
I kontrakten står `end_boundary=None` med status `uafklaret` — bevidst **ikke**
`"eksklusiv"`, selv om nabotabellen `DayAheadPrices` er målt til det. En test
(`test_elspotprices_arver_ikke_dayaheadprices`) forhindrer at de smelter sammen.

## B3 — EDS' rate limit

Uafklaret, og skrevet ind som sådan. **Hverken kvote eller vindue er kendt.**
Målt er kun at afstand mellem kald ikke er nok i sig selv: Gate 1b ramte 429 to
gange med 4 s, Gate 1c to gange med 8 s (den ene lykkedes efter 60 s pause).
Gate 2 skal have backoff **før** en genhentning, ikke opdage det midtvejs.

---

# DEL C (1d) — ENHEDER

`DatasetSchema.units` dækker nu **præcis** `v2_columns` for alle otte datasæt.
Reglen står i modulets docstring: en enhed sættes **kun** hvis endpointets eget
OpenAPI-rækkeskema dokumenterer den, eller Gate 1d har målt den. Aldrig udledt
af navnet.

Kilde: `https://api.sysapp.dk/openapi.json`, **v1.5.2**, 84 814 B, OpenAPI 3.1.0.

| datasæt | v2-kolonner | uden enhed |
|---|---|---|
| imbalance_price | 17 | 10 |
| mfrr_activation | 18 | **16** |
| mfrr_capacity | 11 | 6 |
| afrr_capacity | 10 | 6 |
| spot_dk | 4 | **0** |
| spot_entsoe | 5 | 4 |
| dmi_obs | 10 | **0** |
| spot_system | 0 | 0 |
| **i alt** | **75** | **42** |

**42 af 75 kolonner har `units=None`.** Tallet er frosset i en test, så en
enhed ikke kan snige sig ind uden at nogen skriver hvor den er målt.

Hvad tallet består af:

* **`EdsMfrrActivationRow` dokumenterer ingenting** — alle 16 måletal er `None`.
  At `total_mfrr_up_mw` og `mfrr_sa_up_eur` bærer enheden i navnet er ikke en
  måling.
* **`EntsoePriceRow.price_eur_mwh` har ingen `description`** i specen. Derfor er
  `spot_entsoe.spot_price_eur` `None`, mens `spot_dk.spot_price_eur` er
  `"EUR/MWh"` — specen dokumenterer den ene og ikke den anden. Asymmetrien er
  ægte og skal blive stående.
* **`resolution_minutes`** har kun `example: 60` i specen. Målt **værdi** 15 på
  alle prøvede dage — men en værdi er ikke en enhed, og "minutter" ville være
  læst ud af navnet.
* **`down_price_eur`/`down_price_dkk`** er `None` selv om `up_price_eur` er
  `"EUR/MW"`: specen dokumenterer kun op-siden. Det er næsten sikkert samme
  enhed. "Næsten sikkert" er ikke målt.
* **DMI er komplet dokumenteret** — °C, W/m², m/s, mm, hPa, %, og
  `unixtime` som "Unix timestamp (UTC seconds)" → `s`.

**C1's egentlige svar:** `spot_price_eur` beholder sit navn. Enheden hører i
kontrakten, ikke i navnet — og netop derfor kan de to forekomster af navnet
have hver sin enhedsstatus uden at nogen skal gætte.

To ikke-fysiske enheder er egne konstanter, fordi `None` betyder *uafklaret* og
disse er *afklarede*: `_U_TS_UTC = "UTC-tidsstempel"` og `_U_ENUM = "tekst-enum"`.

---

# DEL D (1d) — DEN MANUELLE SKRIVEVEJ

## D1 + D2 — skrevet ind i `UNRESOLVED`

To poster, ordret i modulet. Kernen:

**Vejen.** Der findes ingen automatik. `update_data.py` køres i hånden. De to
seneste df-data-commits blev ifølge reflog'en begået **og pushet fra denne
server**, fra samme mappe som loaderens cache. Kørslen logges ikke ud over
`DATA_VERSION.md`'s dato, og intet registrerer hvilken version af
`update_data.py` der skrev hvad. Vejen kan ikke migreres herfra —
`update_data.py` ligger i df-data, som denne gate ikke må skrive i.

**Konsekvensen.** Kører en ældre `update_data.py` mod et v2-repo — eller den
migrerede mod et v1-repo — appenderes den nye kørsels rækker til de
eksisterende årsfiler med kildens egne navne. Resultatet er **én fil med to
skemaer**.

**Det er allerede sket én gang.** `spot/DK1_2026.csv` bærer 8 632 proxy-rækker
med `id`/`created_at`/`updated_at` og 8 448 EDS-rækker uden, i samme fil under
samme header. `id` blev til flydende tal (`2001010.0`) — `pd.concat`'s aftryk
når en kolonne mangler i den ene ramme.

**Og `DATA_VERSION.md` har intet `schema_version`-felt i dag.** Målt: ordet
forekommer ikke i filen. `update_data.py`'s `update_version_file()` skriver
dato og dækningstabel, intet andet. Der er altså ikke bare et tomt felt — der
er **intet felt**. Fejlen er tavs og rammer en tredjepart, der kloner repoet og
læser filen som ét skema.

## D3 — hvordan en LOADER kan opdage det (forslag, ikke bygget)

`schema_version` alene rækker ikke, netop fordi **én fil kan bære begge
skemaer**. Fire forslag, svageste først:

**a) Header-fingeraftryk mod `schema_v2.v1_columns`.**
Loaderen læser headeren og kræver at den matcher en indfrosset variant.
*Fordel:* nul omkostning, og datastrukturen findes allerede — det er præcis
hvad `test_klon_headere_er_uaendrede` gør.
*Ulempe:* fanger **ikke** dagens fejl. `DK1_2026.csv` har én header og to
skemaer. Headeren er ærlig; rækkerne er ikke.

**b) Kolonne-nullitet pr. blok.**
Efter indlæsning: for hver kolonne der er `NaN` i et sammenhængende bagerste
eller forreste udsnit — men udfyldt i resten — rejs en fejl.
*Fordel:* fanger den faktiske fejl, uden nyt format og uden at kilden skal
ændres. Virker med det samme på eksisterende filer.
*Ulempe:* heuristik. En kolonne der ægte er tom i en periode (fx `mfrr_da_*`,
som Gate 0 målte tom i både API og klon) giver falsk alarm. Kræver en
undtagelsesliste, som selv skal vedligeholdes.

**c) Formatfingeraftryk på en kendt kolonne.**
`hour_dk` er ISO-`T` fra EDS og mellemrumssepareret fra proxyen. Kræv ét format
pr. fil.
*Fordel:* det er sådan Gate 1b faktisk fandt blandingen — kendt effektivt på
den ene fejl vi har set.
*Ulempe:* virker kun så længe formaterne tilfældigvis afviger. Det er held, ikke
design. Og `hour_dk` er droppet i v2, så vagten ville hænge på en kolonne v2
ikke bærer.

**d) Proveniens pr. række** (Gate 1c's Form 1, gentaget her fordi den er
svaret på D3 såvel som på D1).
En `source`-kolonne pr. række.
*Fordel:* den eneste form der gør blandingen **synlig i stedet for gættet**.
Loaderen skal kun tælle distinkte værdier. Svarer også på "hvilke rækker kom
hvorfra" for en tredjepart.
*Ulempe:* ændrer skemaet — altså præcis den handling der udløser problemet den
skal fange. Skal indføres i én kontrolleret kørsel, og historiske rækker kan
ikke backfilles ærligt (samme argument som for `auction`).

**Bemærkning uden at vælge:** (a) og (d) er de eneste to der er *afgørelser*
frem for *gæt*, og de dækker hver sin fejl. (a) fanger et skift i headeren,
(d) fanger et skift under headeren. Ingen af dem fanger den anden.

## D4 — tovejs versionsvagt (forslag, ikke bygget)

`update_data.py` bærer sin egen `SCHEMA_VERSION` og **nægter at skrive**, hvis
`DATA_VERSION.md`'s `schema_version` ikke matcher.

Formen:

1. `update_data.py` læser `DATA_VERSION.md` som **første** handling, før noget
   netværkskald.
2. Matcher feltet dens egen `SCHEMA_VERSION` → kør, og skriv feltet tilbage
   uændret.
3. Ellers → afbryd med en fejl der nævner **begge** versioner og hvilken vej
   uenigheden går ("scriptet er nyere end repoet" vs. "repoet er nyere end
   scriptet"). De to kræver forskellig handling af mennesket.

**Ved et tomt eller manglende felt — som er tilstanden i dag:**

Feltet findes ikke i `DATA_VERSION.md`. Tre mulige svar:

* **Afbryd.** Sikrest. Men det brækker den eksisterende arbejdsgang ved første
  kørsel, på hver maskine, og et værktøj der ikke kan køre bliver omgået.
* **Behandl som v1 og skriv feltet.** Bekvemt, og rigtigt for repoet som det
  ser ud nu. Men det er en **antagelse om historiske data** — præcis samme
  fejl som at backfille `auction`. Og den ville skrive "v1" oven på
  `DK1_2026.csv`, som beviseligt ikke er rent v1.
* **Afbryd, men med en engangsflag-udvej** (`--adopt-schema=v1`), der skriver
  feltet og ikke gør andet. Mennesket erklærer versionen; værktøjet gætter den
  ikke.

Den tredje er den eneste der hverken gætter eller blokerer permanent. **Men
valget er ikke truffet her**, og de to første er ikke uforsvarlige — det
afhænger af, om `DK1_2026.csv`'s blanding skal ryddes op før eller efter vagten
indføres.

**Uanset form:** vagten skal læse **før** den henter. Afbryder den efter
hentningen, har den brugt kvote hos EDS på et kald hvis resultat kastes væk —
og EDS' rate limit er, jf. B3, ukendt.

---

# DEL E (1d) — REGRESSION

## E1 — de fire relationer, alle otte datasæt

```
datasæt            v1           L1  API           L2  v2           L3   L3-spejlet  ok
--------------------------------------------------------------------------------------
imbalance_price    18      17+1=18   20      17+3=20  17    17+0+0=17    17+0+0=17  ✓
mfrr_activation    19      18+1=19   21      18+3=21  18    18+0+0=18    18+0+0=18  ✓
mfrr_capacity      11      10+1=11   14      11+3=14  11    10+1+0=11    11+0+0=11  ✓
afrr_capacity      11      10+1=11   13      10+3=13  10    10+0+0=10    10+0+0=10  ✓
spot_dk           5/8        4+4=8    8        4+4=8   4      4+0+0=4      4+0+0=4  ✓
spot_entsoe       5/5        4+1=5    4        4+0=4   5      4+1+0=5      4+1+0=5  ✓
dmi_obs            11       9+2=11   11       9+2=11  10     9+0+1=10     9+0+1=10  ✓
spot_system         5        0+5=5    0        0+0=0   0      0+0+0=0      0+0+0=0  ✓
```

**Alle fire relationer holder for alle otte datasæt. Tallene er uændrede fra
Gate 1c** — 1d tilføjede beskrivelse (kontrakt, enheder), ikke mapping.

## E2 — testsuiten

**201 passed, 1 skipped.** Udgangspunktet var 141/1. 60 nye tests, ingen brudt,
ingen rettet undervejs.

De nye deler sig i to:

* **Kontrakt-vagten.** Den bærende er
  `test_maalt_betyder_vaerdi_og_uafklaret_betyder_none`: står der "målt", ER
  der en værdi; står der "uafklaret", er værdien `None`. Uden den kan et felt
  se besvaret ud uden at være det. Dertil
  `test_de_to_sysapp_endpoints_er_stadig_uenige` og
  `test_eds_har_modsat_datosemantik_af_proxyen`, som holder de **målte
  modsigelser** i live — harmoniserer nogen dem, forsvinder præcis den fælde
  kontrakten findes for.
* **Enheds-vagten.** `test_enheden_udledes_ikke_af_navnet` navngiver de
  kolonner der frister mest (`afrr_up_mw`, `total_mfrr_up_mw`,
  `resolution_minutes`) og kræver at de forbliver `None`.

Den ene skip er uændret: `test_A2_documents_what_head_returns_instead` i
`tests/test_coverage_guard_e2e.py`, dokumenteret i Gate 1c DEL C1.

---

# USIKKERT (1d)

1. **`api_entsoe_prices.php`'s FILTER-akse.** Jeg har målt hvad **kolonnen**
   `timestamp` indeholder (dansk lokaltid, tre uafhængige krydstjek). Jeg har
   **ikke** målt hvilken akse `startdate`/`enddate` skærer på. De to behøver
   ikke være ens — `api_energinet_prices.php` filtrerer på dk og leverer både
   utc og dk. Derfor står `filter_timezone` som *uafklaret*, ikke som `"dk"`.
2. **`limit_max` for tre af fire proxy-endpoints.** Kun
   `api_eds_balance.php` er bisekteret (10 000). De øvrige gav 1 000 ved
   `limit=999999`, hvilket ligner samme opførsel — men **10 000 må ikke lånes
   fra naboen**, og det står som uafklaret.
3. **`api_dmi_obs_ny.php`'s `area`-enum.** Et ugyldigt `area` gav 200 med tom
   krop, ikke en 400 med en liste. `area_values` er derfor **tom**. Klonen har
   `fyn`, `vestkyst`, `karup`, men det er filnavne, ikke en målt enum.
4. **`origin/main` for businesscase kan være forældet.** Sammenligningen
   `HEAD...origin/main = 0 0` bruger den lokalt kendte ref; seneste `fetch` var
   2026-08-04. Jeg har ikke hentet for at se efter nyere fjern-commits.
   `git fetch --dry-run` ville afgøre det.
5. **Hvilket værktøj der lavede det oprindelige sysapp-udtræk.** A4 afgør at
   det ikke var `update_data.py` og at det skete før repoet fandtes. Selve
   værktøjet ligger uden for begge repoer og kan ikke ses herfra.
6. **`down_price_eur`/`down_price_dkk`'s enhed.** Næsten sikkert `EUR/MW` og
   `DKK/MW` som op-siden. Specen dokumenterer kun op-siden, så de står som
   `None`. Et enkelt spørgsmål til den der vedligeholder `openapi.json` ville
   flytte to kolonner ud af de 42.

---
---

# GATE 1c — DEN UKENDTE SKRIVER, EDS' DATOSEMANTIK, TO NORMALISERINGER

**Status:** Read-only + to schema-rettelser. 7 EDS-kald, hvoraf **2 endte i 429
og tælles ikke som målinger**. Klonen urørt: `6c95bde` før og efter.
**Tests: 141 passed, 1 skipped.**
**Dato:** 2026-08-08

**Tilbagetrukket:** beslutningen om at `spot_entsoe` skulle være EUR only. Den
byggede på at DKK var vores eget regnestykke; Gate 1b afkræftede præmissen.
`spot_price_dkk` bæres nu med.

## Det den retablering afslørede

Med DKK i v2 kan `api_entsoe_prices.php` **ikke længere producere en komplet
`spot_entsoe`-række.** Klonen har kolonnen, endpointet har den ikke.

Det er `ADDED`'s spejlbillede, og der fandtes ingen spand til det. Jeg har
tilføjet **`V1_ONLY`** — v2-navne kun klonen kan levere — og en fjerde relation:

```
v2_columns == api_to_v2.values() ⊎ V1_ONLY ⊎ DERIVED
```

Den er ikke den samme som ligning 3. Er begge spande tomme, når begge kilder
hele v2-skemaet. Er de ikke, kan den ene kilde ikke danne en komplet række — og
så skal det stå skrevet, ikke opdages i Gate 3. Tilføjelsen er additiv og rører
ingen måling.

---

# DEL A (1c) — DEN UKENDTE SKRIVER

## A1 — klonens historik rækker ikke

**Klonen er shallow: 4 commits, grænse `1b813de` (2026-05-13).**

| commit | dato | forfatter | besked |
|---|---|---|---|
| `6c95bde` | 2026-08-07 | Steen Kramer Jensen | Ret tidsmaerkningen i dmi/*.csv — hour_utc bar lokal tid |
| `decd48f` | 2026-08-04 | Steen Kramer Jensen | Hent fra api.sysapp.dk i stedet for www.sysapp.dk |
| `137011b` | 2026-06-29 | Steen Kramer Jensen | juni kørsel |
| `1b813de` | 2026-05-13 | Steen Kramer Jensen | Brug api_dmi_obs_ny.php as endpoint ← **shallow-grænse** |

To commits rører `spot/DK1_2026.csv` og `DK2_2026.csv`: `137011b` og `1b813de`.
Men `1b813de` er den graftede rod — den *ser ud* til at have oprettet alle
filer, hvilket er en artefakt af den shallow klon, ikke en måling af hvad der
skete.

**Ved shallow-grænsen findes proxy-rækkerne allerede:**

```
$ git show 1b813de:spot/DK1_2026.csv | head -2
id,hour_utc,hour_dk,price_area,spot_price_dkk,spot_price_eur,created_at,updated_at
2001010.0,2026-01-01 00:00:00,2026-01-01 01:00:00,DK1,448.21,60.01,2025-12-31 13:15:02,2026-01-16 01:15:02
```

12 376 datarækker, variant C, allerede på plads 2026-05-13. **Rækkerne blev
skrevet før historikken begynder.** De commits der ville navngive skriveren er
ikke i klonen.

Den ene commit der *kan* aflæses bekræfter til gengæld Gate 1b's mekanisme
direkte i diffen. `137011b` ("juni kørsel") tilføjede 4 704 rækker:

```
+,2026-05-09 22:00:00,2026-05-10T00:00:00,DK1,996.919596,133.410004,,
+,2026-06-27 21:45:00,2026-06-27T23:45:00,DK1,1021.105113,136.610001,,
```

Tomt førstefelt (`id`), tomme sidste to (`created_at`, `updated_at`) — præcis
hvad `merge_into_yearfile`'s `pd.concat` gør når 5-kolonners EDS-rækker flettes
ind i en 8-kolonners fil. Målt i diffen, ikke udledt.

## A2 — ingen skrivevej i businesscase-repoet

Grep over hele repoet efter `to_csv`, `merge_into_yearfile`, `df-data`-stier,
`git add/commit/push`, `subprocess`, `os.system`, `api_energinet_prices`.

Fire `to_csv`-kald findes, **ingen af dem peger på df-data**:

| sted | mål |
|---|---|
| `run_case.py:604` | `out_dir/` — kørslens KPI-output |
| `src/data_loader.py:248` | API-cache |
| `src/data_loader.py:307` | API-cache |
| `scripts/capture_rate_q1_2026.py:181` | analyse-output |

`merge_into_yearfile` findes kun i klonens eget `update_data.py`. Ingen
`git add`/`commit`/`push` uden for `CONTRIBUTING.md`'s dokumentation. Ingen
`subprocess`, ingen `os.system`. `api_energinet_prices.php` kaldes ét sted
(`src/data_loader.py:596`) — en læsende hentning ind i en pandas-Series, aldrig
skrevet til disk uden for API-cachen.

**Der findes ingen anden skrivevej end `update_data.py`. Og `update_data.py`
kalder ikke proxyen for spot** — kun EDS.

## A3 — ingen scheduler på denne maskine

Alt læst, intet ændret.

| kilde | resultat |
|---|---|
| `crontab -l` (denne bruger) | tom — kun Ubuntus standardkommentarer |
| `/etc/cron.d/` | `certbot`, `e2scrub_all`, `logwatch`, `php`, `roundcube-core` |
| `/etc/cron.daily/` | `logwatch`, `apache2`, `apport`, `apt-compat`, `dpkg`, `logrotate` |
| grep i cron-konfigurationen efter `df-data`/`update_data`/`fjernvarme` | **0 træffere** |
| `systemctl list-timers --all` | 19 timere: pmlogger, prometheus, roundcube, certbot, backup-restic, backup-local-rsync, logrotate m.fl. |
| grep i `/etc/systemd/`, `/lib/systemd/system/`, `~/.config/systemd` efter samme | **0 træffere** |
| `find / -type d -name df-data` | **kun** `/opt/fjernvarme-businesscase/data/df-data` |
| `find / -name update_data.py` | **kun** klonens egen kopi |

**Forbehold:** andre brugeres og roots planlagte job er ikke læsbare for mig
uden at eskalere rettigheder, og det har jeg ikke gjort. Målingen dækker det
læsbare.

Klonen har hverken `.github/workflows/` eller anden CI-konfiguration.
`DATA_VERSION.md` registrerer dækning, men **ikke kilde** — den kan derfor ikke
svare på spørgsmålet.

## A4 — konklusion: **IKKE FUNDET, og delvist uden for min rækkevidde**

> ⚠ **AFLØST AF GATE 1d.** Konklusionen "ikke fundet" var korrekt for det jeg
> kunne se dengang, men ufuldstændig: jeg søgte kun i den shallow klon.
> GitHub-API'et rækker hele vejen tilbage, og Gate 1d's DEL A4 lukker
> spørgsmålet — rækkerne lå i df-data's **allerførste commit** `6cc7a69`
> (2026-05-10), og **ingen** af de fem versioner af `update_data.py` kalder
> proxyen for spot. Punkterne nedenfor står ved magt; de er blot ikke længere
> alt hvad der kan siges.

Jeg gætter ikke. Det jeg kan sige med sikkerhed:

- Rækkerne blev skrevet **før 2026-05-13**, uden for den shallow historik.
- De blev **ikke** skrevet af `update_data.py` — den kalder ikke proxyen for spot.
- De blev **ikke** skrevet af noget i businesscase-repoet.
- Ingen scheduler **på denne maskine** rører df-data.
- df-data ligger på GitHub (`skj-1964/df-data`), så skrivningen er sket et
  andet sted — en anden maskine, eller i hånden.

**Hvad der ville afgøre det, i rækkefølge efter pris:**

1. **Den fulde git-historik.** `git log --follow spot/DK1_2026.csv` på det
   komplette repo ville navngive commit, dato og forfatter direkte. Jeg har
   **ikke** kørt `git fetch --unshallow`, fordi det skriver i klonens `.git` og
   dermed bryder gatens vigtigste regel. Historikken kan læses på
   github.com uden at røre klonen — det er den billigste vej.
2. **Commit-beskederne omkring 2026-01 og 2026-04.** Proxy-rækkerne dækker
   2026-01-01 → 2026-03-31 21:45; en commit i det vindue vil sandsynligvis
   sige hvad der blev gjort.
3. **Roots og andre brugeres crontabs** på den maskine der faktisk kører
   opdateringen — kræver rettigheder jeg ikke har og ikke har taget.

Bemærk at spørgsmålet ikke kun er arkæologi. `DATA_VERSION.md` viser at
proxy-vinduet begynder omkring 2025-10-01 for DK1/DK2 (15 390 rækker i 2025 mod
DE's 6 550) — altså præcis da `Elspotprices` holdt op. Nogen har lappet
DK-hullet manuelt og ikke de udenlandske zoner. **Den beslutning er ikke
dokumenteret noget sted i klonen.**

---

# DEL B (1c) — EDS' DATOSEMANTIK, MÅLT

Min 88/96-udledning i Gate 1b var netop det: udledt. Her er den målt.

## B1 — bar dato vs. eksplicit tidsstempel

Alle **HTTP 200**, ingen fejl i kroppen. `DayAheadPrices`, DK1:

| `start` | `end` | rækker | UTC-spænd | DK-spænd |
|---|---|---|---|---|
| `2026-06-01` | `2026-06-02` | 96 | 2026-05-31 22:00 .. 2026-06-01 21:45 | **00:00 .. 23:45** |
| `2026-06-01T00:00` | `2026-06-02T00:00` | 96 | 2026-05-31 22:00 .. 2026-06-01 21:45 | **00:00 .. 23:45** |
| `2026-06-01T00:00` | `2026-06-01T12:00` | **48** | 2026-05-31 22:00 .. 2026-06-01 09:45 | **00:00 .. 11:45** |
| `2026-06-01` | `2026-06-01` | **0** | — | — |

## B2 — reglen

> **EDS filtrerer på DANSK LOKALTID (`TimeDK`/`HourDK`), og intervallet er
> halvåbent `[start, end)`. En bar dato betyder `T00:00` dansk tid — den
> udvides IKKE til hele døgnet.**

Aflæsningen, punkt for punkt:

- **Zonen er dansk, ikke UTC.** Alle fire kald returnerer DK-tider der begynder
  præcis `00:00` og slutter præcis `23:45`. UTC-spændet er forskudt to timer om
  sommeren. Filteraksen er altså `TimeDK`.
- **`end` er eksklusiv.** `T12:00` gav sidste række `11:45` DK — ikke `12:00`.
- **En bar dato udvides ikke.** `start=end=2026-06-01` gav **0 rækker**. Havde
  en bar dato betydet "hele døgnet", ville den have givet 96.
- **Bar dato ≡ `T00:00`.** De to heldagskald gav bit for bit samme svar.

**For Gate 2, uden noget at huske: sæt `end` til dagen efter (`start=D`,
`end=D+1`) for ét dansk døgn — eller send et eksplicit `T00:00`-tidsstempel.
De to er ækvivalente.**

### ⚠ Det er MODSAT `api_eds_balance.php`

Dette er samme fældeklasse som §10.3.1, med modsat fortegn. De to API'er deler
navn på datasættene og deler intet i datosemantik:

| | `api.sysapp.dk/api_eds_balance.php` | `api.energidataservice.dk` |
|---|---|---|
| filterakse | **UTC** | **dansk lokaltid** |
| bar `enddate`-dato | **inklusiv hele døgnet** | **`T00:00`, eksklusiv** |
| `start=end=D` | hele døgnet D | **0 rækker** |
| eksplicit tidsstempel | eksklusiv | eksklusiv |

**Den eneste regel der holder på begge: send altid et eksplicit tidsstempel som
`end`; det er eksklusivt begge steder.** Zonen skal man stadig vide — og de er
ikke ens.

## B3 — `Elspotprices` opfører sig ens (men det er målt, ikke antaget)

| `start` | `end` | rækker | DK-spænd |
|---|---|---|---|
| `2025-06-15` | `2025-06-16` | 24 | **00:00 .. 23:00** |
| `2025-06-15T00:00` | `2025-06-16T00:00` | 24 | **00:00 .. 23:00** |
| `2025-06-15` | `2025-06-15` | **0** | — |

Samme halvåbne interval, samme danske akse, samme ikke-udvidelse af en bar dato.
Timeopløsning, som Gate 1b målte.

**Ikke målt:** et sub-dagligt eksplicit vindue på `Elspotprices`
(`T00:00 → T12:00`). Kaldet ramte **429 to gange**, også efter 6 forsøg med
10–50 s backoff og 60 s ventetid imellem. Eksklusiviteten *inde i* et døgn er
derfor kun målt på `DayAheadPrices`. Se USIKKERT.

### 429'erne, rapporteret som ikke-målinger

| kald | udfald |
|---|---|
| `Elspotprices 2025-06-15T00:00 → 2025-06-16T00:00` (1. forsøg) | **429 efter 6 retries — ikke en måling.** Gentaget efter 60 s → **200, 24 rækker** ✓ |
| `Elspotprices 2025-06-15T00:00 → 2025-06-15T12:00` | **429 efter 6 retries — ikke en måling.** Ikke gentaget. |

Ingen af dem tælles som tomme svar.

---

# DEL C (1c) — TO NORMALISERINGER

## C1 — `price_eur_mwh` → `spot_price_eur`

Samme begrundelse som A3's akse-normalisering, nu anvendt på målet: **samme
mappe må ikke rumme to navne for samme størrelse.** `spot_dk.spot_price_eur` og
`spot_entsoe`'s pris er den samme størrelse i den samme enhed.

Efter C1 er de to spot-datasæt navnemæssigt uskelnelige på alt de deler:

```
spot_dk      : hour_utc, price_area, spot_price_dkk, spot_price_eur
spot_entsoe  : hour_utc, price_area, spot_price_eur, spot_price_dkk, resolution_minutes
KEY (begge)  : (hour_utc, price_area)
```

En omkostning, skrevet ind i modulet: **enheden forsvinder ud af navnet.** MWh
stod i `price_eur_mwh` og står ikke i `spot_price_eur`. Men `spot_dk` har aldrig
båret enheden, og to navne for én størrelse er den dyrere fejl. En test fanger
det hvis nogen af API'ets egne navne senere slipper igennem til v2.

## C2 — `auction` backfilles ikke

Skrevet eksplicit i modulet, og håndhævet af en test der kræver at ordene står
der:

> **INGEN BACKFILL.** Værdien kommer fra kilden ved genhentning, eller også
> kommer den ikke. En v1-fil uden kolonnen forbliver v1 — den skal hverken have
> `'main'` skrevet ind, en tom streng, eller NULL. At udfylde den ville påstå at
> vi havde målt hvilken udbudsrunde en historisk række tilhørte; det har vi ikke.

Følgen er noteret samme sted, fordi den bider i Gate 2: **en v1-række kan ikke
danne en fuld KEY** for `mfrr_capacity`. To rækker fra hver sin kilde er derfor
ikke sammenlignelige på nøglen, før nogen beslutter hvad en manglende `auction`
betyder ved join og dedup. Den beslutning er ikke truffet her.

## C3 — de tre ligninger, kørt igen

| datasæt | v1 | **L1** `v1→v2 + DROP` | API | **L2** `api→v2 + APIDROP` | v2 | **L3** `v1→v2 + ADD + DERIV` | L3 spejlet `api→v2 + V1_ONLY + DERIV` |
|---|---|---|---|---|---|---|---|
| `imbalance_price` | 18 | 17+1 = **18** ✓ | 20 | 17+3 = **20** ✓ | 17 | 17+0+0 = **17** ✓ | 17+0+0 = **17** ✓ |
| `mfrr_activation` | 19 | 18+1 = **19** ✓ | 21 | 18+3 = **21** ✓ | 18 | 18+0+0 = **18** ✓ | 18+0+0 = **18** ✓ |
| `mfrr_capacity` | 11 | 10+1 = **11** ✓ | 14 | 11+3 = **14** ✓ | 11 | 10+1+0 = **11** ✓ | 11+0+0 = **11** ✓ |
| `afrr_capacity` | 11 | 10+1 = **11** ✓ | 13 | 10+3 = **13** ✓ | 10 | 10+0+0 = **10** ✓ | 10+0+0 = **10** ✓ |
| `spot_dk` | 5/8 | 4+4 = **8** ✓ | 8 | 4+4 = **8** ✓ | 4 | 4+0+0 = **4** ✓ | 4+0+0 = **4** ✓ |
| **`spot_entsoe`** | 5/5 | **4+1 = 5** ✓ | 4 | 4+0 = **4** ✓ | **5** | **4+1+0 = 5** ✓ | **4+1+0 = 5** ✓ |
| `dmi_obs` | 11 | 9+2 = **11** ✓ | 11 | 9+2 = **11** ✓ | 10 | 9+0+1 = **10** ✓ | 9+0+1 = **10** ✓ |
| `spot_system` | 5 | 0+5 = **5** ✓ | 0 | 0+0 = **0** ✓ | 0 | 0+0+0 = **0** ✓ | 0+0+0 = **0** ✓ |

Kun `spot_entsoe` flyttede sig: v2 gik fra 4 til 5 kolonner, `DROPPED` fra 2 til
1, og `V1_ONLY` fik sit ene medlem.

**`spot_entsoe` er nu det eneste datasæt hvor de to kilder ikke er ligeværdige.**
Klonen kan levere alle fem v2-kolonner på nær `resolution_minutes`; endpointet
kan levere alle fem på nær `spot_price_dkk`. Ingen af dem alene giver et komplet
datasæt.

---

# DEL D (1c) — PROVENIENS: TO FORSLAG, INGEN BESLUTNING

Klonens `spot/`-filer blander tre kildetabeller (`Elspotprices`,
`DayAheadPrices`, `api_energinet_prices.php`) med to opløsninger (time og
15 minutter), og **intet i repoet registrerer hvilke rækker der kom hvorfra.**
I dag kan det kun udledes af fingeraftryk: tilstedeværelsen af `id`, og om
`hour_dk` bruger ISO-`T` eller mellemrum. Det er ikke en registrering, det er
retsmedicin.

Jeg foreslår to former. **Jeg har ikke skrevet nogen af dem.**

## Form 1 — kolonne pr. række

En `source`-kolonne i hver spotfil: `elspotprices` / `dayaheadprices` /
`api_energinet_prices`.

**Fordele.** Præcis pr. række — også når to kilder overlapper på samme
tidsstempel, hvilket er tilfældet i `DK1_2026.csv`. Overlever splitning,
filtrering og join, fordi den rejser med rækken. Gør Gate 3's diff triviel: en
uventet værdi er synlig med det samme. Og den kan **udledes bagudrettet** fra de
fingeraftryk der allerede findes, så historikken ikke går tabt.

**Ulemper.** Ændrer skemaet for alle 34 spotfiler og bryder derfor
fastfrysningen i `test_schema_v2_mapping.py` — den skal opdateres bevidst.
Koster plads i filer der allerede fylder. Vigtigst: det er **metadata i
datalaget**, og hver ny sådan kolonne gør det sværere at sige hvad en "ren"
måledatarække er. `created_at`/`updated_at` blev droppet af netop den grund, og
en `source`-kolonne er samme kategori.

## Form 2 — datointerval → kildetabel i `DATA_VERSION.md`

En tabel: område, fra, til, kildetabel, opløsning.

**Fordele.** Rører ikke en eneste datafil, bryder ingen test, koster ingen plads.
`DATA_VERSION.md` findes allerede og opdateres allerede af `update_data.py` ved
hver kørsel, så der er et naturligt sted at generere den. Menneskeligt læsbar —
en tredjepart kan se hele billedet på ét skærmbillede i stedet for at aggregere
34 filer.

**Ulemper.** Kan ikke udtrykke overlap på række-niveau, og der ER overlap:
`DK1_2026.csv` skifter kilde midt i filen ved 2026-03-31 22:00. Den ville skulle
være interval-baseret og dermed sårbar over for at nogen genhenter et vindue
uden at opdatere tabellen — så lyver den, tavst. Og den rejser ikke med dataene:
kopierer nogen en enkelt CSV ud af repoet, følger proveniensen ikke med.

## Bemærkning

De to udelukker ikke hinanden, og de svarer på forskellige spørgsmål. Form 2
svarer *"hvad indeholder dette repo"*; form 1 svarer *"hvor kom netop denne
række fra"*. Kun form 1 kan besvare det andet spørgsmål ved overlap, og kun ved
overlap er det spørgsmål svært.

**Der er også en tredje mulighed jeg ikke vil kalde et forslag, men som bør
nævnes:** proveniensen kan udledes maskinelt af fingeraftrykkene og genereres
som en rapport uden at gemme noget som helst. Det koster ingen skemaændring,
men gør udledningen til kode nogen skal vedligeholde — og fingeraftrykkene er
tilfældige egenskaber ved kilderne, ikke garantier.

---
---

# GATE 1b — TILFØJELSE OG TO RETTELSER

**Status:** Read-only. 20 EDS-kald + 40 fra Gate 1. Klonen urørt: `6c95bde` før
og efter, tom `git status`. **Tests: 132 passed, 1 skipped.**
**Dato:** 2026-08-08

Gate 1b lukkede mappingens tre huller (eksplicit `v2_columns`, to
mappingretninger, `DERIVED`) og målte hvor klonens `spot_price_dkk` kommer fra.
Målingen **omstøder to af Gate 1's konklusioner nedenfor.** De er ikke slettet —
de står som skrevet, med rettelsen her.

## RETTELSE 1 — der findes ingen "DKK-kurs". Der er aldrig blevet omregnet.

Gate 1's Del E skriver at klonens DKK er *"beregnet med en kurs der varierer fra
dag til dag"* og at kursen *"ikke kan rekonstrueres for hullet"*. **Præmissen er
forkert.** `spot_price_dkk` er EDS' egen kolonne, overtaget uændret. Ingen i
vores pipeline har ganget med noget.

Målt på to måder, se DEL B nedenfor. De 23 "dagsrater" jeg rapporterede i Gate 1
er ikke vores omregning — det er Nord Pools egen, aflæst indirekte gennem to
kolonner EDS leverer side om side.

**Konsekvens:** Q6 (*"med hvilken kurs er DKK-kolonnen beregnet?"*) er ikke et
åbent spørgsmål. Det er et forkert spørgsmål. Det reelle valg er et
**kildevalg**: EDS leverer DKK, `api_entsoe_prices.php` gør ikke.

## RETTELSE 2 — NO2/SE3/SE4's "kildemangel" gjaldt kun ét endpoint

Gate 1's Del E skriver at NO2/SE3/SE4 *"ikke kan migreres"* fordi kilden er tom,
og at *"begge kilder mangler"* (Gate 0 §4.2). **Målt forkert.**

`api_entsoe_prices.php` har 0 rækker for dem — det er korrekt. Men EDS
`DayAheadPrices` har **alle fire områder gennem hele hullet**, 96 rækker pr.
område pr. dag. Manglen sad i endpointet, ikke i dataene.

---

# DEL A (1b) — DE TRE HULLER, LUKKET

## A1 — `v2_columns` er nu sandheden

Hvert datasæt har en ordnet, autoritativ output-header. `v1_to_v2.values()` er
det ikke: den mangler `ADDED` (kun API'et har dem) og `DERIVED` (genereres).
Skal Gate 2 vide hvordan en v2-fil ser ud, læses `v2_columns`.

## A2 — to retninger ind til v2

| retning | hvad |
|---|---|
| `v1_to_v2` | klonens CSV-filer → v2 |
| `api_to_v2` | nye API-hentninger → v2 |

**Seks datasæt har ren identitets-mapping på API-vejen** — API'et *er*
v2-navngivningen. `spot_system` har ingen (intet endpoint). Kun **`spot_entsoe`**
afviger, og det håndhæves af en test: bliver et andet endpoint pludselig
ikke-identisk, er det et skifte i kildens kontrakt og ikke en detalje.

## A3 — `spot_entsoe` normaliseret

```
timestamp → hour_utc
area      → price_area
```

`spot/`-mappen må ikke rumme to kolonnenavne for samme akse. Efter
normaliseringen har `spot_dk` og `spot_entsoe` **samme akse-navne og samme
KEY** `(hour_utc, price_area)`.

**IKKE omfattet — og eksplicit ikke løst: område-VÆRDIERNE.** Klonen bruger
`DE`/`NO2`/`SE3`/`SE4`; `api_entsoe_prices.php` kræver
`DE_LU`/`NO_2`/`SE_3`/`SE_4` og svarer 400 på de korte. **Filnavne og
kolonneværdier beholder klonens koder.** En værdimapping er en anden opgave end
en navnemapping. Den står i `OPEN_QUESTIONS` i modulet, så Gate 2 ikke gætter.

En residual jeg ikke har rørt, fordi A3 kun nævnte akserne: prismålet hedder
`price_eur_mwh` i `spot_entsoe` og `spot_price_eur` i `spot_dk`. Samme størrelse,
to navne, samme mappe. Det er samme fældeklasse som akserne, men A3 normaliserede
akserne og ikke målene. Også i `OPEN_QUESTIONS`.

## A4 — `DERIVED`, ét medlem

```python
dmi_obs.hour_utc = pd.Timestamp(unixtime, unit="s")
```

Kildens egen `hour_utc` er målt forkert i én time om året — **i begge kilder**.
Derfor:

| | hvor den ender |
|---|---|
| API'ets `hour_utc` | `API_DROPPED` |
| Klonens `hour_utc` | `DROPPED` |
| v2's `hour_utc` | `DERIVED`, fra `unixtime` |

**KEY forbliver `(unixtime, area)`.** Nøglen skal pege på kolonnen der bærer
entydigheden i sig selv, ikke på en afledning af den — ændrer nogen udtrykket,
må nøglen ikke følge med i faldet. En test håndhæver det.

To yderligere invarianter er testet: en `DERIVED`-kolonnes kilder skal kunne nås
fra **begge** retninger (ellers producerer de to loadere forskellige skemaer), og
`dmi_obs` skal være det eneste datasæt med `DERIVED` — kommer der flere, skal den
der tilføjer dem også røre testen.

## A5 — de tre ligninger, tal pr. datasæt

```
v1  == v1_to_v2.keys  ⊎ DROPPED
API == api_to_v2.keys ⊎ API_DROPPED
v2  == v1_to_v2.values ⊎ ADDED ⊎ DERIVED
```

| datasæt | v1 | `v1→v2 + DROP` | API | `api→v2 + APIDROP` | v2 | `v1→v2 + ADD + DERIV` |
|---|---|---|---|---|---|---|
| `imbalance_price` | 18 | 17+1 = **18** ✓ | 20 | 17+3 = **20** ✓ | 17 | 17+0+0 = **17** ✓ |
| `mfrr_activation` | 19 | 18+1 = **19** ✓ | 21 | 18+3 = **21** ✓ | 18 | 18+0+0 = **18** ✓ |
| `mfrr_capacity` | 11 | 10+1 = **11** ✓ | 14 | 11+3 = **14** ✓ | 11 | 10+1+0 = **11** ✓ |
| `afrr_capacity` | 11 | 10+1 = **11** ✓ | 13 | 10+3 = **13** ✓ | 10 | 10+0+0 = **10** ✓ |
| `spot_dk` | 5/8 † | 4+4 = **8** ✓ | 8 | 4+4 = **8** ✓ | 4 | 4+0+0 = **4** ✓ |
| `spot_entsoe` | 5/5 † | 3+2 = **5** ✓ | 4 | 4+0 = **4** ✓ | 4 | 3+1+0 = **4** ✓ |
| `dmi_obs` | 11 | 9+2 = **11** ✓ | 11 | 9+2 = **11** ✓ | 10 | 9+0+1 = **10** ✓ |
| `spot_system` | 5 | 0+5 = **5** ✓ | 0 | 0+0 = **0** ✓ | 0 | 0+0+0 = **0** ✓ |

† To v1-varianter; ligning 1 kontrolleres mod unionen, og hver variant skal være
en delmængde af den.

**Ingen kolonne står uden for noget regnskab på noget datasæt.** Alle tre
ligninger håndhæves som disjunkte unioner, ikke som talsammenligninger.

---

# DEL B (1b) — HVOR KOMMER DKK FRA

**Hypotese:** klonens `spot_price_dkk` er EDS' egen kolonne fra
`DayAheadPrices`, ikke noget `update_data.py` har beregnet.

## B1 — kodesiden: ingen aritmetik overhovedet

`data/df-data/scripts/update_data.py:192-213`, hele spot-vejen:

```python
def update_spot(start: str, end: str, force: bool):
    print("  spot (DayAheadPrices):")
    df = fetch_eds("DayAheadPrices", start, end)
    if df.empty:
        print("    ingen data returneret")
        return
    rename = {"TimeUTC": "hour_utc", "TimeDK": "hour_dk", "PriceArea": "price_area",
              "DayAheadPriceDKK": "spot_price_dkk", "DayAheadPriceEUR": "spot_price_eur"}
    df = df.rename(columns=rename)
    split_and_write(df, "hour_utc", "price_area", REPO_ROOT / "spot", force=force)
```

Hent → omdøb → skriv. **Ingen multiplikation, ingen kursvariabel, ingen
EUR→DKK.** Skrivevejen nedenunder rører heller ikke tal:

- `split_and_write` (l. 152-171): `to_datetime`, `dropna`, `groupby`, `drop`
- `merge_into_yearfile` (l. 125-150): `to_datetime`, `dropna`, `concat`,
  `sort_values`, `drop_duplicates`, `to_csv`

Grep for `*`, `kurs`, `rate`, `fx`, `eur_dkk`, `7.4`, `round`, `float(` over hele
filen (353 linjer) giver **nul** træffere på en prisberegning.

**Hypotesen er bekræftet på kodesiden.**

Filens egen kommentar forklarer desuden noget Gate 1 ikke kunne:

> `DayAheadPrices` afløser `Elspotprices` fra april 2026 sammenfaldende med
> ISP15-fuld-overgangen. `TimeUTC ← var HourUTC`, `DayAheadPriceDKK ← var
> SpotPriceDKK`, `DayAheadPriceEUR ← var SpotPriceEUR`.

## B2 — datasiden: identisk celle for celle

`GET https://api.energidataservice.dk/dataset/DayAheadPrices?start=2026-06-01&end=2026-06-02&limit=400&filter={"PriceArea":["DE"]}`
→ **HTTP 200, 96 rækker**, ingen fejl i kroppen.

Kolonner: `TimeUTC, TimeDK, PriceArea, DayAheadPriceEUR, DayAheadPriceDKK`

Join mod `spot/DE_2026.csv` på tidsstempel — 88 fælles rækker (EDS' `start/end`
er dansk tid, klonens filter er UTC-dato; overlappet er 00:00–21:45 UTC, præcis
88 kvarter — ikke et datahul):

| EDS | klon | identiske | max abs. Δ |
|---|---|---|---|
| `DayAheadPriceDKK` | `spot_price_dkk` | **88 / 88** | **0** |
| `DayAheadPriceEUR` | `spot_price_eur` | **88 / 88** | **0** |

```
TimeUTC              PriceArea  DayAheadPriceEUR  spot_price_eur  DayAheadPriceDKK  spot_price_dkk
2026-06-01T21:45:00  DE           147.080002      147.080002       1099.231811     1099.231811
2026-06-01T21:30:00  DE           156.979996      156.979996       1173.221396     1173.221396
2026-06-01T21:15:00  DE           164.600006      164.600006       1230.171065     1230.171065
```

**Hypotesen er bekræftet på datasiden.** Ikke afrundet, ikke omregnet — kopieret.

Og kolonneORDENEN følger med:

```
EDS DayAheadPrices : TimeUTC, TimeDK, PriceArea, DayAheadPriceEUR, DayAheadPriceDKK
klon DE_2026.csv   : hour_utc, hour_dk, price_area, spot_price_eur, spot_price_dkk
```

Klonens "byttede" valutakolonner er **kildens egen nøgleorden**, ført igennem
`pd.DataFrame(records)` → `rename` → `to_csv`. Ikke en fejl. Ikke et uheld.

## B3 — EDS inde i hullet: alle fire områder har data

Kald uden områdefilter, så alle områder tælles i ét kald. Alle **HTTP 200**,
ingen fejl i kroppen.

| dag | dataset | rækker | pr. område |
|---|---|---|---|
| 2025-11-15 | `DayAheadPrices` | **576** | DE 96, DK1 96, DK2 96, **NO2 96, SE3 96, SE4 96** |
| 2025-12-15 | `DayAheadPrices` | **576** | DE 96, DK1 96, DK2 96, **NO2 96, SE3 96, SE4 96** |
| 2026-02-15 | `DayAheadPrices` | **576** | DE 96, DK1 96, DK2 96, **NO2 96, SE3 96, SE4 96** |

Kolonner ens på alle tre dage: `TimeUTC, TimeDK, PriceArea, DayAheadPriceEUR,
DayAheadPriceDKK`.

**§4.2's "kildemangel" for NO2/SE3/SE4 er målt forkert. Sagt eksplicit: den
gjaldt kun `api_entsoe_prices.php`.** EDS har alle fire områder, i 15-minutters
opløsning, gennem hele hullet — inklusive DKK-kolonnen.

*Note om metoden:* jeg tilføjede en `Elspotprices`-kontrol for at et 0-svar fra
`DayAheadPrices` ikke skulle læses som "ingen data findes" når det kunne skyldes
at datasættet ikke dækker perioden. Kontrollen viste sig unødvendig, fordi
`DayAheadPrices` svarede positivt. To af de tre kontrolkald ramte **429
(rate limit)** og er derfor **ikke** målinger; det tredje (2026-02-15) gav 200
med 0 rækker. Jeg tæller ingen af dem som resultater.

## B4 — kildens egen udvikling forklarer alle tre headere

`DayAheadPrices`, DK1, ét kald pr. dag omkring de to grænser:

| dag | HTTP | rækker | skridt | kolonner |
|---|---|---|---|---|
| 2025-09-29 | 200 | **0** | — | — |
| 2025-09-30 | 200 | **0** | — | — |
| 2025-10-01 | 200 | 96 | 15 min | `TimeUTC,TimeDK,PriceArea,DayAheadPriceEUR,DayAheadPriceDKK` |
| 2026-03-30 | 200 | 96 | 15 min | samme |
| 2026-03-31 | 200 | 96 | 15 min | samme |
| 2026-04-01 | 200 | 96 | 15 min | samme |

**`DayAheadPrices` begynder præcis 2025-10-01 og er 15-minutters fra første
dag.** Der er *ingen* opløsnings- eller kolonneændring ved 2026-03-31 — den dato
er ikke en kildeændring, den er datoen hvor *vi* skiftede endpoint.

`Elspotprices`, DE, 2025-06-15: **HTTP 200, 24 rækker**, kolonner
`HourUTC, HourDK, PriceArea, SpotPriceDKK, SpotPriceEUR` — **DKK før EUR**,
timeopløsning.

### De tre headere, hver med sin målte kilde

| variant | klon-header | kilde | målt bevis |
|---|---|---|---|
| **A** (24 filer) | `hour_utc,hour_dk,price_area,spot_price_dkk,spot_price_eur` | EDS `Elspotprices` | `SpotPriceDKK` før `SpotPriceEUR`, timeopløsning |
| **B** (4 filer) | `…,spot_price_eur,spot_price_dkk` | EDS `DayAheadPrices` | `DayAheadPriceEUR` før `DayAheadPriceDKK`, 15-min |
| **C** (6 filer) | `id,…,created_at,updated_at` | `api_energinet_prices.php` | endpointets egen header, enum `['DK1','DK2']` |

**Der er altså en kilde mere end `update_data.py`'s spot-vej kender** — men den
er ikke ukendt: det er vores egen proxy. Den forklarer præcis hvorfor kun
DK1/DK2 har variant C: proxyens enum er `['DK1','DK2']`.

**Dobbeltbekræftet i `spot/DK1_2026.csv`, som er en blanding af to kilder:**

| | rækker | spænd |
|---|---|---|
| MED `id`/`created_at`/`updated_at` | 8 632 | 2026-01-01 00:00 → 2026-03-31 21:45 |
| UDEN | **8 448** | **2026-03-31 22:00** → 2026-06-27 21:45 |

De 8 448 er nøjagtigt antallet af rækker i `DE_2026.csv`, og skiftetidspunktet
er nøjagtigt hvor DE-hullet slutter. `hour_dk`-formatet er fingeraftrykket:
ISO-`T` = EDS, mellemrum = proxy.

### Hullet, forklaret

| periode | DK1/DK2 | DE/NO2/SE3/SE4 |
|---|---|---|
| → 2025-09-30 | EDS `Elspotprices` | EDS `Elspotprices` |
| 2025-10-01 → 2026-03-31 21:45 | **proxy** (17 376 rækker) | **ingen** (0 rækker) |
| 2026-03-31 22:00 → | EDS `DayAheadPrices` | EDS `DayAheadPrices` |

`Elspotprices` holdt op, `update_data.py` skiftede først til `DayAheadPrices`
2026-03-31, og proxyen dækker kun DK. Derfor mistede netop de fire ikke-danske
områder præcis det vindue. Hullet er en **hentepause**, ikke en kildemangel.

## B5 — konklusion: **BEKRÆFTET**

Klonens `spot_price_dkk` er EDS' egen kolonne, overtaget uændret — bekræftet
uafhængigt på kodesiden (ingen aritmetik findes) og på datasiden (88/88 celler
identiske, max Δ = 0). **Der er aldrig blevet omregnet, og der findes derfor
ingen kurs at identificere eller rekonstruere.**

Jeg foreslår intet endpoint. Kildevalget for DE/NO2/SE3/SE4 er noteret som åbent
i `OPEN_QUESTIONS`.

---

# DEL C (1b) — TO SMÅ TING

## C1 — den skippede test

```
SKIPPED [1] tests/test_coverage_guard_e2e.py:77
  "vagten findes nu — dagens tavse adfærd er væk (Gate 2)"
```

**Navn:** `test_A2_documents_what_head_returns_instead`.

**Hvorfor den skipper:** den er en *dokumentationstest*, ikke en vagt. Den
kører kun så længe `src.data_loader.CoverageError` **ikke** findes, og skipper
i det øjeblik vagten er bygget:

```python
if getattr(data_loader, "CoverageError", None) is not None:
    pytest.skip("vagten findes nu — dagens tavse adfærd er væk (Gate 2)")
```

Den er beviset for at søstertestens *"DID NOT RAISE"* skyldes en **delvist
dækket** frame (2 186 rækker returneret uden en lyd, hvor 8 784 var forventet)
og ikke en tom frame — `df.empty` er falsk, så `df.empty`-vagten fanger den ikke.

**Den skipper altså fordi `CoverageError` allerede findes i `src/data_loader.py`.
Vagten er bygget; testen har gjort sit arbejde.** Det er ikke et hul i
mapping-suiten — den hører til dækningsvagten (F1), ikke til F6, og
`test_schema_v2_mapping.py` har **nul** skips.

## C2 — positionsbaseret CSV-læsning i businesscase-repoet

Grep over `src/`, `scripts/`, `tests/`, `cases/`, `run_case.py` efter `usecols`,
`header=`, `names=[`, `skiprows`, `.iloc[:, …]`, `.columns[n]`, `csv.reader`,
`np.loadtxt`, `genfromtxt`.

**Ét sted læser efter position:**

| sted | kode | rører det df-data/spot? |
|---|---|---|
| `src/data_loader.py:989` | `df.set_index("time").sort_index().iloc[:, 0]` | **Nej** |

Det er indlæsning af brugerens egen `production_profile_path`-CSV, ikke
klonens spotfiler. Den tager "hvad der end står i første kolonne efter `time`" —
en reel latent fælde hvis nogen tilføjer en kolonne til en profilfil, men den er
uden for F6's flade.

**Alt andet er navnebaseret.** `src/data_loader_github.py`, som faktisk læser
klonens `spot/`, adresserer udelukkende ved navn (`df["spot_price_dkk"]`,
`df["price_area"]`, `time_col="hour_utc"`) og validerer mod et
`required`-sæt. `usecols`, `header=None`, `names=` og `skiprows` optræder
**intetsteds**. `reporting.py:483`'s `df.iloc[1:]` er et rækkeudsnit, ikke et
kolonneopslag.

**Målt, ikke antaget — `pd.concat` aligner på navn:**

```
DE_2025 kolonner: ['hour_utc','hour_dk','price_area','spot_price_dkk','spot_price_eur']
DE_2026 kolonner: ['hour_utc','hour_dk','price_area','spot_price_eur','spot_price_dkk']
concat →          ['hour_utc','hour_dk','price_area','spot_price_dkk','spot_price_eur']

2025-01-01 00:00:00     dkk=   11.930000   eur=   1.600000
2026-03-31 22:00:00     dkk= 1188.292882   eur= 159.020004
```

`_read_dataset` samler netop årsfiler med `pd.concat(frames, ignore_index=True)`
— og de byttede kolonner havner korrekt.

**Afgørelse: nej, ingen læser klonens spotfiler efter position.
`DE_2026`-ombytningen er i dag ufarlig.** Den er stadig værd at fastfryse —
testen gør det med rækkefølgen — fordi en fremtidig loader der bruger `usecols`
med heltal eller `iloc[:, 3]` ville bytte de to valutaer uden at fejle på noget.

---
---

# FEJL I OPGAVEN — B2's andet regnestykke

Opgaven definerer tre spande og to ligninger:

```
ADDED:  v2-navne API'et leverer, som klonen ikke har
        antal v1-kolonner  = len(COLUMN_MAP) + len(DROPPED)
        antal API-kolonner = len(COLUMN_MAP) + len(ADDED)
```

De kan ikke holde samtidig. B3 beordrer `created_at`, `updated_at`,
`time_dk`/`hour_dk` og `id` droppet — og **API'et leverer dem alle**. Med tre
spande findes der intet sted at skrive "API'et sender den, vi bærer den ikke
med". De må enten:

- stå i `ADDED` — hvor Gate 2 læser `created_at` som *"tilføj denne kolonne"*,
  stik imod B3; eller
- falde helt ud af regnskabet, hvorved ligningen ikke går op og kravet om at
  være udtømmende brydes.

Det er ikke en detalje. Ligningen fejler på **7 af 8 datasæt**. Kun
`spot_entsoe` går op som skrevet, og kun fordi `api_entsoe_prices.php` som det
eneste endpoint ikke sender revisionsstempler.

**Jeg har ikke stoppet, fordi rettelsen er rent additiv og ikke rører nogen
måling.** `schema_v2.py` har en fjerde spand:

```
API_DROPPED:  v2-navne API'et leverer, som IKKE bæres med over
```

og regnskabet bliver:

```
v1-kolonner  == COLUMN_MAP.keys()   ⊎ DROPPED.keys()          (uændret)
API-kolonner == COLUMN_MAP.values() ⊎ ADDED ⊎ API_DROPPED      (rettet)
```

Begge tal er rapporteret nedenfor, både i rettet og oprindelig form. Sig til
hvis den skal kollapses tilbage til tre spande — men så skal Gate 2 have
droppelisten et andet sted fra.

**En anden, mindre justering:** B1 skriver *"COLUMN_MAP: v1-navn → v2-navn (kun
omdøbninger)"*. Læses "kun omdøbninger" som "kun rækker hvor navnet ændrer
sig", bliver `COLUMN_MAP` **tom** for `spot_dk` og `dmi_obs`, hvor klonen
allerede er på snake_case — og så siger ligning 1 at alle kolonner er droppet.
`COLUMN_MAP` indeholder derfor også identitets-par. "Kun omdøbninger" er læst
som "kun navnesvar, ingen transformationer".

---

# DEL A — HEADERNE, GENMÅLT

Alle headere nedenfor er hentet i **denne** gate, ikke afskrevet fra Gate 0
eller §11.1.

## A1 — API'ets headere, ordret

Reference: `2026-03-15`, `format=csv`, `limit=5`, base `https://api.sysapp.dk`.
Balance-kaldene bruger `area=DK1&fields=all`.

**`api_eds_balance.php?dataset=imbalance_price` — 200, 5 rækker, 20 kolonner**
```
time_utc,time_dk,price_area,satisfied_demand,imbalance_price_eur,imbalance_price_dkk,spot_price_eur,dominating_direction,afrr_up_mw,afrr_vwa_up_eur,afrr_vwa_up_dkk,afrr_down_mw,afrr_vwa_down_eur,afrr_vwa_down_dkk,mfrr_marginal_price_up_eur,mfrr_marginal_price_up_dkk,mfrr_marginal_price_down_eur,mfrr_marginal_price_down_dkk,created_at,updated_at
```

**`api_eds_balance.php?dataset=mfrr_activation` — 200, 5 rækker, 21 kolonner**
```
time_utc,time_dk,price_area,mfrr_sa_up_req_mw,mfrr_sa_up_eur,mfrr_sa_down_req_mw,mfrr_sa_down_eur,mfrr_da_up_mw,mfrr_da_up_eur,mfrr_da_down_mw,mfrr_da_down_eur,total_mfrr_up_mw,total_mfrr_down_mw,mfrr_offered_up_mw,mfrr_offered_down_mw,mfrr_local_up_mw,mfrr_local_down_mw,mfrr_special_up_mw,mfrr_special_down_mw,created_at,updated_at
```

**`api_eds_balance.php?dataset=mfrr_capacity` — 200, 5 rækker, 14 kolonner**
```
time_utc,time_dk,price_area,auction,up_demand_mw,up_procured_mw,up_price_eur,up_price_dkk,down_demand_mw,down_procured_mw,down_price_eur,down_price_dkk,created_at,updated_at
```

**`api_eds_balance.php?dataset=afrr_capacity` — 200, 5 rækker, 13 kolonner**
```
time_utc,time_dk,price_area,up_demand_mw,up_procured_mw,up_price_eur,up_price_dkk,down_demand_mw,down_procured_mw,down_price_eur,down_price_dkk,created_at,updated_at
```

**`api_energinet_prices.php?area=DK1` — 200, 5 rækker, 8 kolonner**
```
id,hour_utc,hour_dk,price_area,spot_price_dkk,spot_price_eur,created_at,updated_at
```

**`api_dmi_obs_ny.php?area=fyn` — 200, 5 rækker, 11 kolonner**
```
unixtime,hour_utc,hour_dk,area,temp_mean_past1h,radia_glob_past1h,wind_speed_past1h,precip_past1h,pressure,humidity_past1h,cloud_cover
```

**`api_entsoe_prices.php?area=DE_LU` — 200, 5 rækker, 4 kolonner**
```
timestamp,area,price_eur_mwh,resolution_minutes
```

**Kontrolmåling:** `fields=all` blev også sendt til `api_energinet_prices.php`,
`api_dmi_obs_ny.php` og `api_entsoe_prices.php`, og `fields` blev **udeladt** på
to eds_balance-datasæt. Headerne var i alle seks tilfælde uændrede. Kolonne­sættene
er altså stabile og ikke afhængige af `fields`.

## A2 — Klonens headere, ordret (`6c95bde`)

**`imbalance/*.csv` — 18 kolonner, én variant over alle 4 filer**
```
TimeUTC,TimeDK,PriceArea,SatisfiedDemand,ImbalancePriceEUR,ImbalancePriceDKK,SpotPriceEUR,DominatingDirection,aFRRUpMW,aFRRVWAUpEUR,aFRRVWAUpDKK,aFRRDownMW,aFRRVWADownEUR,aFRRVWADownDKK,mFRRMarginalPriceUpEUR,mFRRMarginalPriceUpDKK,mFRRMarginalPriceDownEUR,mFRRMarginalPriceDownDKK
```

**`mfrr_act/*.csv` — 19 kolonner, én variant over alle 4 filer**
```
TimeUTC,TimeDK,PriceArea,mFRRSAUpReqMW,mFRRSAUpEUR,mFRRSADownReqMW,mFRRSADownEUR,mFRRDAUpMW,mFRRDAUpEUR,mFRRDADownMW,mFRRDADownEUR,TotalmFRRUpMW,TotalmFRRDownMW,mFRROfferedUpMW,mFRROfferedDownMW,mFRRLocalUpMW,mFRRLocalDownMW,mFRRSpecialUpMW,mFRRSpecialDownMW
```

**`mfrr_cap/*.csv` — 11 kolonner, én variant over alle 8 filer**
```
TimeUTC,TimeDK,PriceArea,UpDemandMW,UpProcuredMW,UpPriceEUR,UpPriceDKK,DownDemandMW,DownProcuredMW,DownPriceEUR,DownPriceDKK
```

**`afrr/*.csv` — 11 kolonner, én variant over alle 3 filer. Identisk med `mfrr_cap`.**
```
TimeUTC,TimeDK,PriceArea,UpDemandMW,UpProcuredMW,UpPriceEUR,UpPriceDKK,DownDemandMW,DownProcuredMW,DownPriceEUR,DownPriceDKK
```

**`dmi/*.csv` — 11 kolonner, én variant over alle 15 filer**
```
unixtime,hour_utc,hour_dk,area,temp_mean_past1h,radia_glob_past1h,wind_speed_past1h,precip_past1h,pressure,humidity_past1h,cloud_cover
```

### `spot/` — TRE headere, ikke én

Dette modsiger Gate 0's referat, som skriver at API og klon har *"identiske
kolonner i identisk rækkefølge"* for spot. Det gælder **6 af 34 filer**.

**Variant A — 5 kolonner, DKK før EUR (24 filer)**
```
hour_utc,hour_dk,price_area,spot_price_dkk,spot_price_eur
```
> `DE_2022–2025`, `NO2_2022–2025`, `SE3_2022–2025`, `SE4_2022–2025`,
> `SYSTEM_2022–2025`, `DK1_2022`, `DK1_2024`, `DK2_2022`, `DK2_2024`

**Variant B — 5 kolonner, EUR før DKK (4 filer)**
```
hour_utc,hour_dk,price_area,spot_price_eur,spot_price_dkk
```
> `DE_2026`, `NO2_2026`, `SE3_2026`, `SE4_2026`

**Variant C — 8 kolonner (6 filer)**
```
id,hour_utc,hour_dk,price_area,spot_price_dkk,spot_price_eur,created_at,updated_at
```
> `DK1_2023`, `DK1_2025`, `DK1_2026`, `DK2_2023`, `DK2_2025`, `DK2_2026`

**Ombytningen i variant B er reel og navnene er ærlige.** Kontrolleret på
værdier:

| fil | header-rækkefølge | første datarække |
|---|---|---|
| `DE_2025.csv` | `…,spot_price_dkk,spot_price_eur` | `DE,11.93,1.6` → DKK=11,93 EUR=1,60 |
| `DE_2026.csv` | `…,spot_price_eur,spot_price_dkk` | `DE,159.020004,1188.292882` → EUR=159,02 DKK=1188,29 |

Forholdet er 7,47 begge steder — altså står den store værdi i DKK-kolonnen i
begge filer. **Kolonnenavnene er korrekte; kun positionen flytter.** En
positionsbaseret indlæsning i Gate 2 ville bytte de to valutaer for 2026-filerne
uden at fejle på noget. Det er præcis derfor opgaven siger *"aflæs efter navn,
aldrig efter position"* — og det er nu målt at reglen har en konkret fælde i
klonen, ikke kun i teorien.

## A3 — Leverer endpointet `resolution_minutes`?

| endpoint | `resolution_minutes` |
|---|---|
| `api_eds_balance.php?dataset=imbalance_price` | **nej** |
| `api_eds_balance.php?dataset=mfrr_activation` | **nej** |
| `api_eds_balance.php?dataset=mfrr_capacity` | **nej** |
| `api_eds_balance.php?dataset=afrr_capacity` | **nej** |
| `api_energinet_prices.php` | **nej** |
| `api_dmi_obs_ny.php` | **nej** |
| `api_entsoe_prices.php` | **JA** |

**Ét ud af syv.** `eds_balance` opfører sig altså **ikke** som `entsoe_prices`
her — antagelsen opgaven advarede mod ville have været forkert. Bekræftet med
og uden `fields=all` på alle syv.

`api_entsoe_prices.php` leverede `resolution_minutes = 15` på alle tre prøvede
dage (2025-12-15, 2026-03-15, 2026-06-27).

Konsekvensen er ubehagelig og skal siges højt: `imbalance_price` og
`mfrr_activation` er 15-minutters data, `mfrr_capacity` og `afrr_capacity` er
timedata, og klonens spotfiler skifter fra time til 15 minutter inde i filerne
— **og ingen af dem har en kolonne der siger det.** Opløsningen skal udledes
af tidsstemplerne, og den må ikke syntetiseres som en kolonne der lader som om
API'et sagde det. `schema_v2.py` håndhæver det via
`ENDPOINTS_WITH_RESOLUTION_MINUTES`, og testen fejler hvis nogen tilføjer
kolonnen til et datasæt der ikke får den fra kilden.

---

# DEL B — MAPPINGEN

Fuld kildekode i `src/schema_v2.py`. Den er eneste sandhedskilde; Gate 2 og
Gate 3 skal importere derfra og ikke gentage navne lokalt.

## Sådan læses tabellerne

- **COLUMN_MAP** — bevares, v1-navn → v2-navn. Indeholder også identitets-par.
- **DROPPED** — v1-kolonner der udgår.
- **ADDED** — API-kolonner klonen ikke har, som **bevares**.
- **API_DROPPED** — API-kolonner der **ikke** bæres med over.

Tre begrundelser går igen og er skrevet én gang i `schema_v2.py`:

| kolonne | begrundelse |
|---|---|
| `TimeDK` / `time_dk` / `hour_dk` | Lokal tid er ikke entydig over efterårets DST-tilbagestilling. API'et advarer selv mod det som nøgle (`meta.time_dk_note`). Al tidslogik kører på UTC-aksen. |
| `created_at` / `updated_at` | Kildesystemets hentetidsstempel, ikke måledata. Ændrer sig ved enhver revision og gør ellers identiske rækker uens. |
| `id` | Databaseintern nøgle uden betydning uden for kildedatabasen. Gate 0 målte at den afviger mellem API og klon selv hvor alle måleværdier er identiske. |

## 1. `imbalance_price` — klon `imbalance/`

**KEY:** `(time_utc, price_area)`

| v1 | → v2 |
|---|---|
| `TimeUTC` | `time_utc` |
| `PriceArea` | `price_area` |
| `SatisfiedDemand` | `satisfied_demand` |
| `ImbalancePriceEUR` | `imbalance_price_eur` |
| `ImbalancePriceDKK` | `imbalance_price_dkk` |
| `SpotPriceEUR` | `spot_price_eur` |
| `DominatingDirection` | `dominating_direction` |
| `aFRRUpMW` | `afrr_up_mw` |
| `aFRRVWAUpEUR` | `afrr_vwa_up_eur` |
| `aFRRVWAUpDKK` | `afrr_vwa_up_dkk` |
| `aFRRDownMW` | `afrr_down_mw` |
| `aFRRVWADownEUR` | `afrr_vwa_down_eur` |
| `aFRRVWADownDKK` | `afrr_vwa_down_dkk` |
| `mFRRMarginalPriceUpEUR` | `mfrr_marginal_price_up_eur` |
| `mFRRMarginalPriceUpDKK` | `mfrr_marginal_price_up_dkk` |
| `mFRRMarginalPriceDownEUR` | `mfrr_marginal_price_down_eur` |
| `mFRRMarginalPriceDownDKK` | `mfrr_marginal_price_down_dkk` |

**DROPPED (1):** `TimeDK`
**ADDED (0):** —
**API_DROPPED (3):** `time_dk`, `created_at`, `updated_at`

## 2. `mfrr_activation` — klon `mfrr_act/`

**KEY:** `(time_utc, price_area)`

| v1 | → v2 |
|---|---|
| `TimeUTC` | `time_utc` |
| `PriceArea` | `price_area` |
| `mFRRSAUpReqMW` | `mfrr_sa_up_req_mw` |
| `mFRRSAUpEUR` | `mfrr_sa_up_eur` |
| `mFRRSADownReqMW` | `mfrr_sa_down_req_mw` |
| `mFRRSADownEUR` | `mfrr_sa_down_eur` |
| `mFRRDAUpMW` | `mfrr_da_up_mw` |
| `mFRRDAUpEUR` | `mfrr_da_up_eur` |
| `mFRRDADownMW` | `mfrr_da_down_mw` |
| `mFRRDADownEUR` | `mfrr_da_down_eur` |
| `TotalmFRRUpMW` | `total_mfrr_up_mw` |
| `TotalmFRRDownMW` | `total_mfrr_down_mw` |
| `mFRROfferedUpMW` | `mfrr_offered_up_mw` |
| `mFRROfferedDownMW` | `mfrr_offered_down_mw` |
| `mFRRLocalUpMW` | `mfrr_local_up_mw` |
| `mFRRLocalDownMW` | `mfrr_local_down_mw` |
| `mFRRSpecialUpMW` | `mfrr_special_up_mw` |
| `mFRRSpecialDownMW` | `mfrr_special_down_mw` |

**DROPPED (1):** `TimeDK`
**ADDED (0):** —
**API_DROPPED (3):** `time_dk`, `created_at`, `updated_at`

De tre akronym-fælder står samlet her: `mFRRSAUpReqMW → mfrr_sa_up_req_mw`
(ikke `m_frrsa_…`), `TotalmFRRUpMW → total_mfrr_up_mw` (ikke `totalm_frr_…`),
og på forrige datasæt `aFRRUpMW → afrr_up_mw` (ikke `a_frr_…`).

## 3. `mfrr_capacity` — klon `mfrr_cap/`

**KEY:** `(time_utc, price_area, auction)` ← tre led

| v1 | → v2 |
|---|---|
| `TimeUTC` | `time_utc` |
| `PriceArea` | `price_area` |
| `UpDemandMW` | `up_demand_mw` |
| `UpProcuredMW` | `up_procured_mw` |
| `UpPriceEUR` | `up_price_eur` |
| `UpPriceDKK` | `up_price_dkk` |
| `DownDemandMW` | `down_demand_mw` |
| `DownProcuredMW` | `down_procured_mw` |
| `DownPriceEUR` | `down_price_eur` |
| `DownPriceDKK` | `down_price_dkk` |

**DROPPED (1):** `TimeDK`
**ADDED (1):** `auction` — se Del C
**API_DROPPED (3):** `time_dk`, `created_at`, `updated_at`

## 4. `afrr_capacity` — klon `afrr/`

**KEY:** `(time_utc, price_area)` ← to led, **ingen `auction`**

COLUMN_MAP er identisk med `mfrr_capacity`'s ti rækker ovenfor.

**DROPPED (1):** `TimeDK`
**ADDED (0):** — API'et har ingen `auction` her og afviser parameteren med 400.
**API_DROPPED (3):** `time_dk`, `created_at`, `updated_at`

Klonen har kun DK1 for dette datasæt; der findes ingen `afrr/DK2_*.csv`.

## 5. `spot_dk` — klon `spot/DK1_*`, `spot/DK2_*` — `api_energinet_prices.php`

**KEY:** `(hour_utc, price_area)`

| v1 | → v2 |
|---|---|
| `hour_utc` | `hour_utc` |
| `price_area` | `price_area` |
| `spot_price_dkk` | `spot_price_dkk` |
| `spot_price_eur` | `spot_price_eur` |

**Nul omdøbninger.** Klonen er allerede på API'ets navngivning, fordi
`update_data.py` omdøbte EDS-navnene allerede ved hentning.

**DROPPED (4):** `hour_dk`, `id`, `created_at`, `updated_at`
**ADDED (0):** —
**API_DROPPED (4):** `hour_dk`, `id`, `created_at`, `updated_at`

To v1-varianter (A og C fra A2). Variant A mangler `id`/`created_at`/
`updated_at` — alle tre står alligevel i DROPPED, så en loader der dropper
efter navn håndterer begge varianter uden særtilfælde.

**Målt sidegevinst:** `area=DK1` **respekteres** af endpointet (96 rækker, kun
`DK1` i svaret). Docstringen i `src/data_loader.py:588` hævder det modsatte —
men den taler om parameteren `zone`, ikke `area`. Jeg har ikke genmålt `zone`
med et rækketal der kunne afgøre det, så påstanden står uimodsagt for `zone`.

## 6. `spot_entsoe` — klon `spot/DE_*`, `NO2_*`, `SE3_*`, `SE4_*` — `api_entsoe_prices.php`

**KEY:** `(timestamp, area)` — målt entydig, 0 dubletter på tre dage

| v1 | → v2 |
|---|---|
| `hour_utc` | `timestamp` |
| `price_area` | `area` |
| `spot_price_eur` | `price_eur_mwh` |

**DROPPED (2):** `hour_dk`, **`spot_price_dkk`**
**ADDED (1):** `resolution_minutes`
**API_DROPPED (0):** —

Det eneste datasæt hvor API'et er **smallere** end klonen, og det eneste hvor
B2's oprindelige ligning går op.

`spot_price_dkk` droppes fordi endpointet ikke har den — se Del E.

## 7. `dmi_obs` — klon `dmi/` — `api_dmi_obs_ny.php`

**KEY:** `(unixtime, area)`

Elleve kolonner i klonen, elleve i API'et, identiske navne og rækkefølge.

| v1 | → v2 |
|---|---|
| `unixtime` | `unixtime` |
| `hour_utc` | `hour_utc` |
| `area` | `area` |
| `temp_mean_past1h` | `temp_mean_past1h` |
| `radia_glob_past1h` | `radia_glob_past1h` |
| `wind_speed_past1h` | `wind_speed_past1h` |
| `precip_past1h` | `precip_past1h` |
| `pressure` | `pressure` |
| `humidity_past1h` | `humidity_past1h` |
| `cloud_cover` | `cloud_cover` |

**DROPPED (1):** `hour_dk`
**ADDED (0):** —
**API_DROPPED (1):** `hour_dk`

### `unixtime` bliver — og hvorfor det ikke er en forglemmelse

Begrundelsen står også i `schema_v2.py`, så undtagelsen ikke ser tilfældig ud
for den der åbner filen uden at have læst dette notat.

Ved efterårets DST-tilbagestilling leverer API'et to forskellige
observationer med **samme `hour_utc`**. Gate 0 målte det konkret:
`unixtime=1761440400` kommer ud som `2025-10-26 00:00`, men er i virkeligheden
`01:00`. En hentning der deduperer på `hour_utc` taber derfor den ene.

**Det ER sket. Målt i denne gate, i klonen:**

| dato | `dmi/fyn_*.csv` rækker | forventet | manglende UTC-time |
|---|---|---|---|
| 2023-10-29 | **23** | 24 | 0 |
| 2024-10-27 | **23** | 24 | 0 |
| 2025-10-26 | **23** | 24 | 0 |

**Vigtig konsekvens for læsning af tallene:** klonen har **0 dubletter** på
`(hour_utc, area)` over alle 91 725 DMI-rækker. Det ser ud som om `hour_utc` er
en fin nøgle. Det er den ikke — nul-tallet er *sporet efter* at rækkerne
allerede er tabt, ikke bevis for at nøglen holder. `unixtime` er entydig i alle
målte tilfælde (91 725 rækker, 0 dubletter) og er den eneste nøgle der ikke
skjuler tabet.

`hour_utc` bevares som leveret. Den er kendt forkert i netop den ene time om
året. Gate 0 målte at `pd.Timestamp(unixtime, unit="s")` retter den — men det
er en **beregnet kolonne**, og denne gate laver ingen beregninger. Rettelsen
hører til Gate 2 eller senere, som en bevidst beslutning.

## 8. `spot_system` — klon `spot/SYSTEM_*` — **intet endpoint**

Står med for at være udtømmende, ikke fordi den kan migreres. Alle fem
v1-kolonner er i DROPPED, fordi der ikke er noget at afbilde dem **på** — ikke
fordi de skal slettes. **Gate 2 må ikke røre disse filer.**

---

## B2 — Regnskabet, tal pr. datasæt

| datasæt | v1-kol. | `MAP+DROPPED` | API-kol. | `MAP+ADDED+API_DROPPED` | B2's eq. 2 **som skrevet** |
|---|---|---|---|---|---|
| `imbalance_price` | 18 | 17+1 = **18** ✓ | 20 | 17+0+3 = **20** ✓ | 17+0 = 17 ✗ (≠20) |
| `mfrr_activation` | 19 | 18+1 = **19** ✓ | 21 | 18+0+3 = **21** ✓ | 18+0 = 18 ✗ (≠21) |
| `mfrr_capacity` | 11 | 10+1 = **11** ✓ | 14 | 10+1+3 = **14** ✓ | 10+1 = 11 ✗ (≠14) |
| `afrr_capacity` | 11 | 10+1 = **11** ✓ | 13 | 10+0+3 = **13** ✓ | 10+0 = 10 ✗ (≠13) |
| `spot_dk` | 5 / 8 † | 4+4 = **8** ✓ | 8 | 4+0+4 = **8** ✓ | 4+0 = 4 ✗ (≠8) |
| `spot_entsoe` | 5 / 5 † | 3+2 = **5** ✓ | 4 | 3+1+0 = **4** ✓ | 3+1 = 4 **✓** |
| `dmi_obs` | 11 | 10+1 = **11** ✓ | 11 | 10+0+1 = **11** ✓ | 10+0 = 10 ✗ (≠11) |
| `spot_system` | 5 | 0+5 = **5** ✓ | 0 | 0+0+0 = **0** ✓ | 0+0 = 0 ✓ (trivielt) |

† To v1-varianter. Ligning 1 kontrolleres mod **unionen** af varianterne, og
hver variant skal være en delmængde af unionen — sådan holder den også for
`spot_dk`, hvor variant A mangler tre af unionens otte kolonner.

**Ingen kolonne står uden for regnskabet på noget datasæt.** Både ligninger
håndhæves maskinelt af `tests/test_schema_v2_mapping.py` som disjunkte
unioner, ikke som talsammenligninger — en talsammenligning kan gå op ved et
tilfælde hvis en kolonne både mangler og en anden er dublet.

---

# DEL C — AUCTION-ENUM

## C1 — Distinkte værdier over det bredeste vindue

Metode: i stedet for at trække hele tabellen hjem (52 000+ rækker, i strid med
"kun lille limit") er `auction`-parameteren brugt som prober. Den er
gyldighedstjekket først:

```
GET api_eds_balance.php?dataset=mfrr_capacity&…&auction=vroevl   →  400
{"status":"error","message":"Invalid auction. Use 'main' or 'extra',
 or omit to include both.","code":"INVALID_REQUEST"}
```

Domænet er altså **præcis** `{main, extra}` — endpointet afviser alt andet, så
en prober på begge værdier er udtømmende.

Vindue: `startdate=2015-01-01`, `enddate=2026-08-10 00:00:00` (eksplicit
tidsstempel, jf. Gate 0's måling af at en bar dato er inklusiv hele døgnet).
Tabellen begynder faktisk **2023-06-20 22:00 UTC**, målt som første række.

| kald | HTTP | rækker |
|---|---|---|
| `auction=main`, `area=DK1` | 200 | 5 (limit) |
| `auction=main`, `area=DK2` | 200 | 5 (limit) |
| `auction=main`, uden `area` | 200 | 5 (limit) |
| **`auction=extra`, `area=DK1`** | 200 | **0** |
| **`auction=extra`, `area=DK2`** | 200 | **0** |
| **`auction=extra`, uden `area`** | 200 | **0** |

## C2 — Optræder andet end `main` nogensinde?

**Nej.** `auction=extra` giver **0 rækker over hele tabellens levetid**
(2023-06-20 → 2026-08-10), i begge prisområder og uden områdefilter.
`main` er den eneste værdi der findes i data.

Krydskontrol at filteret ikke bare er i stykker: for otte dage spredt over hele
spændet er `mfrr_capacity` hentet **både** uden `auction`-parameter og med
`auction=main`. Rækketallene er identiske i alle otte par — altså er hver
eneste række `main`:

| dag | uden filter | `auction=main` |
|---|---|---|
| 2023-06-21 (første hele dag) | 24 | 24 |
| 2023-10-29 (DST efterår) | 24 | 24 |
| 2024-03-31 (DST forår) | 24 | 24 |
| 2024-10-27 (DST efterår) | 24 | 24 |
| 2025-10-26 (DST efterår) | 24 | 24 |
| 2026-03-15 (referencedag) | 24 | 24 |
| 2026-03-29 (DST forår) | 24 | 24 |
| 2026-06-27 (klonens sidste) | 24 | 24 |

Spørgsmålet *"hvor mange rækker deler tidsstempel"* er derfor tomt: der findes
ingen sådanne rækker i dag.

**Beslutningen om at have `auction` med og i KEY står ved magt, og målingen
taler ikke imod den.** Kolonnen er en dimension uanset at den er konstant lige
nu; nøglen skal beskytte mod den fremtid hvor den ikke er det. Men det skal
siges præcist hvad der er målt: risikoen er i dag **latent, ikke realiseret**.

## C3 — Er `(time_utc, price_area)` alene entydig?

**Ja, i hele det målte vindue. Nul dubletter.**

To uafhængige målinger:

**API'et,** de otte dage ovenfor: 24 rækker pr. dag pr. område, hver
tidsstempel én gang, ingen dubletter.

**Klonen** (fuld audit, `6c95bde`, gratis fordi Gate 0 beviste værdiidentitet):

| datasæt | rækker | spænd | dubletter på `(TimeUTC, PriceArea)` |
|---|---|---|---|
| `mfrr_cap` | 52 896 | 2023-06-20 → 2026-06-27 | **0** |
| `afrr` | 15 216 | 2024-10-01 → 2026-06-27 | **0** |
| `imbalance` | 92 240 | 2025-03-04 → 2026-06-27 | **0** |
| `mfrr_act` | 92 344 | 2025-03-03 → 2026-06-27 | **0** |

**Forbehold der skal med:** klonens nul er *ikke* uafhængigt bevis. Klonen har
ingen `auction`-kolonne, så havde der været `extra`-rækker, ville hentningen
have kollapset dem — nøjagtigt som den kollapsede DMI's DST-time. Det er
API-målingen (`extra` = 0 rækker over hele levetiden) der bærer konklusionen;
klonens audit bekræfter kun at der heller ikke er dubletter af andre årsager.

Tilsvarende for spot og DMI, fuld klon-audit, alle **0 dubletter**:
`spot/DK1` og `DK2` (50 015 rækker hver), `spot/DE`, `NO2`, `SE3`, `SE4`
(32 543 hver), `spot/SYSTEM` (18 432), `dmi` på `(unixtime, area)` (91 725).

---

# DEL D — TEST

`tests/test_schema_v2_mapping.py` — 76 tests, alle grønne. Ingen netværkskald,
ingen skrivning.

Den gør fire ting:

1. **Fastfryser klonens faktiske headere**, ordret og med rækkefølgen. Hver af
   de 68 klonfiler skal matche en indfrossen variant. Fryses kun *mængden*,
   går EUR/DKK-ombytningen i `spot/DE_2026.csv` upåagtet hen.
2. **Fanger døde varianter** — en variant der bliver stående i `schema_v2.py`
   efter at filen der havde den er væk, beskytter ikke længere det den påstår.
3. **Asserterer B2's to ligninger** som disjunkte unioner, ikke som
   talsammenligninger. En talsammenligning kan gå op ved et tilfælde hvis én
   kolonne mangler og en anden er dublet.
4. **Håndhæver B3's beslutninger:** `auction` med og i KEY, `unixtime` bevaret
   som DMI-nøgle, `time_dk`/`hour_dk`/`created_at`/`updated_at`/`id` droppet på
   begge sider, `resolution_minutes` kun hvor endpointet leverer den, og ingen
   v2-kolonne uden en målt kilde i API-svaret.

Punkt 4's sidste led er den mekaniske version af *"ingen beregnede kolonner"*:
kan et v2-navn ikke peges tilbage på et faktisk API-svar, er det en beregning.
Sætter nogen `spot_price_dkk` tilbage i `spot_entsoe`'s COLUMN_MAP, fejler
testen — fordi endpointet ikke har kolonnen, og den eneste vej frem så er en
valutaomregning.

## D2 — Hele suiten

```
104 passed, 1 skipped in 1.21s
```

28 eksisterende + 76 nye. **De 28 er fortsat grønne.** Den ene skip er den
samme som før gaten.

---

# DEL E — HVAD GATE 2 KAN, OG HVAD DER ER BLOKERET

## Kan gøres nu

| datasæt | grundlag |
|---|---|
| `imbalance_price` (DK1, DK2) | Mapping komplet. Værdiidentitet bevist i Gate 0. Ren omdøbning. |
| `mfrr_activation` (DK1, DK2) | Samme. |
| `mfrr_capacity` (DK1, DK2) | Samme, **plus** `auction` som ny dimension i KEY. |
| `afrr_capacity` (DK1) | Samme. Ingen DK2 i klonen. |
| `spot_dk` (DK1, DK2) | Nul omdøbninger. To v1-varianter, begge dækket. |
| `dmi_obs` (fyn, karup, vestkyst) | Kolonner identiske. `unixtime` som nøgle. |

Seks af otte datasæt. For alle seks gælder at Gate 2 kan skrive loaderen alene
ud fra `schema_v2.py` uden at slå noget op.

**Tre ting Gate 2 skal huske, som ikke er kolonner:**

1. **Sæt altid eksplicit `enddate` med tidsstempel.** En bar dato er inklusiv
   hele døgnet (Gate 0's måling, som modsiger §10.3.1). Med et tidsstempel er
   reglen entydigt eksklusiv, og der er intet at huske.
2. **Send aldrig `limit > 10000`.** `limit=10001` afvises ikke — den falder
   tavst tilbage til default **1000** (Gate 0). Valider `meta.limit` mod det
   sendte.
3. **Læs efter navn, aldrig efter position.** Dokumenteret fælde i
   `spot/DE_2026.csv` m.fl., se A2.

## Blokeret

> **⚠ RETTET AF GATE 1b OG 1c.** Punkt 1 og 2 nedenfor står som skrevet i
> Gate 1, men begge er omstødt. Gate 1c trak desuden hele beslutningen om at
> droppe `spot_price_dkk` tilbage — kolonnen bæres med. Punkt 1's præmis er forkert: der findes ingen kurs, fordi
> der aldrig er blevet omregnet. Punkt 2's kildemangel gælder kun
> `api_entsoe_prices.php` — EDS `DayAheadPrices` har alle fire områder gennem
> hele hullet. Se «GATE 1b» øverst i dokumentet. Punkt 3 (SYSTEM) står ved magt.

### 1. `spot/DE_*` — DKK-kursen  ← **præmissen er forkert, se Gate 1b**

`api_entsoe_prices.php` leverer `timestamp, area, price_eur_mwh,
resolution_minutes`. **Ingen DKK-kolonne.** Klonens `DE_*.csv` har
`spot_price_dkk`.

Målt i denne gate, på klonens egne tal: **kursen er ikke en konstant.** Den er
en dagsrate der ændrer sig.

| fil | implicit EUR→DKK-kurs, min .. maks |
|---|---|
| `DE_2026.csv` | 7,4716 .. 7,4755 |
| `NO2_2026`, `SE3_2026`, `SE4_2026` | 7,4716 .. 7,4755 (identiske med DE) |
| `DK1_2026`, `DK2_2026` | 7,4661 .. 7,4756 † |
| `DE_2025.csv` | 7,4551 .. 7,4692 |
| `DK1_2024.csv` | 7,4513 .. 7,4660 |

† Bredere spænd fordi DK-filerne er afrundet til 2 decimaler; forholdet bliver
derfor støjende. De øvrige har 6 decimaler på DKK og giver kursen eksakt.

Kursen er **konstant inden for hvert kalenderdøgn** — målt over `DE_2026`'s 89
dage er den intra-daglige spredning ~1e-8 (flydende tals-støj) på 85 af dem, og
~1e-4 på fire, hvor skiftet formentlig falder ved dansk midnat og ikke UTC-midnat.
23 distinkte dagsrater på 89 dage.

**Hvorfor det blokerer:** kursen kan aflæses for de dage klonen allerede har.
Den kan **ikke** rekonstrueres for hullet 2025-09-30 21:00 → 2026-03-31 22:00 —
og det er netop hullet `api_entsoe_prices.php` skulle fylde. En migration ville
enten give en DE-serie uden DKK, eller en DKK-kolonne beregnet med en kurs
nogen har fundet på. Begge dele er informationstab forklædt som oprydning.

**Q6 skal besvares først:** med hvilken kurs, fra hvilken kilde, for hvilke
datoer? Indtil da bliver `spot_price_dkk` droppet, og `DE_*.csv` migreres ikke.

### 2. `spot/NO2_*`, `SE3_*`, `SE4_*` — kilden er tom  ← **kun for ét endpoint, se Gate 1b**

Gate 0 målte 0 rækker fra `api_entsoe_prices.php` for `NO_2`, `SE_3` og `SE_4`
på alle prøvede datoer, **også datoer hvor klonen har fulde data** (32 543
rækker pr. område). En migration ville erstatte eksisterende historik med
ingenting.

Dertil kommer et navneskift Gate 2 ikke må gætte på: klonen bruger
`NO2`/`SE3`/`SE4`, API'et kræver `NO_2`/`SE_3`/`SE_4` og svarer 400 på de
korte. Mappingen af **områdekoder** er en anden opgave end mappingen af
kolonnenavne, og den er ikke løst i denne gate.

**Filerne skal bevares som de er.** Hentevejen må ikke pege på
`api_entsoe_prices.php` før nogen har fundet en kilde der faktisk leverer dem.

### 3. `spot/SYSTEM_*` — ingen kilde overhovedet

`api_energinet_prices.php` har enum `['DK1','DK2']`; `api_entsoe_prices.php`
har ikke SYSTEM i `available_areas`. 18 432 rækker (2022 → 2025-02-06) uden
migrationsvej. Enten bevares de uændret, eller det besluttes eksplicit at
datasættet udgår. Det er ikke Gate 2's beslutning at træffe stiltiende.

---

# MÅLT vs. USIKKERT

## MÅLT i denne gate

- Alle syv endpoint-headere, ordret, 2026-03-15, `format=csv`.
- `fields=all` ændrer ingen af de syv headere; kolonnesættene er stabile.
- `resolution_minutes` leveres af **ét** af syv endpoints (`api_entsoe_prices.php`),
  værdi 15 på alle tre prøvede dage.
- Klonens `spot/` har **tre** headere; `DE_2026` m.fl. har EUR før DKK.
  Navnene er ærlige, kun positionen flytter.
- `auction=extra`: **0 rækker** over 2015-01-01 → 2026-08-10, begge områder og
  uden områdefilter. Domænet er præcis `{main, extra}` (bogus værdi → 400).
- Rækketal uden `auction`-filter == med `auction=main` på 8 dage spredt over
  hele spændet.
- `mfrr_capacity` begynder 2023-06-20 22:00 UTC, sorteret stigende på
  `(time_utc, price_area)`.
- 0 dubletter på nøglen i alle fire balancedatasæt, alle syv spotområder og
  DMI — fuld klon-audit, 355 000+ rækker.
- Klonens DMI mangler UTC-time 0 på 2023-10-29, 2024-10-27 **og** 2025-10-26.
- Implicit EUR→DKK-kurs i klonen er en **dagsrate**, ikke en konstant;
  7,4661–7,4756 i 2026, 7,4513–7,4692 i 2024/2025.
- `area=DK1` respekteres af `api_energinet_prices.php` (96 rækker, kun DK1).
- `(timestamp, area)` entydig for `api_entsoe_prices.php` på tre dage.
- 40 API-kald, ingen PHP-fejl i nogen krop. Klonen urørt, `6c95bde` før og efter.

## USIKKERT

1. **Om `auction='extra'` nogensinde kommer.** Målt 0 rækker over hele
   tabellens levetid — stærkere end Gate 0's ene vindue, men det er en
   udtalelse om fortiden. Enum'en findes i spec'en, og et fremtidigt
   extra-udbud ville fordoble rækker pr. tidsstempel. Derfor er `auction` i
   KEY, og derfor er risikoen **latent, ikke realiseret**.
2. **`DominatingDirection → dominating_direction`** er mappet på navnelighed og
   position, ikke på værdisammenligning. Gate 0's værdiaudit dækkede den
   (2 880 sammenligninger på `imbalance_price` uden afvigelser), men jeg har
   ikke selv genmålt værdierne i denne gate. Samme forbehold gælder alle
   omdøbninger uden for §11.1's syv bekræftede rækker: de hviler på Gate 0's
   værdiaudit af **ét** vindue (2026-03-15/16).
3. **Om `zone`-parameteren på `api_energinet_prices.php` respekteres.**
   `area` gør. `data_loader.py`'s docstring hævder `zone` ikke gør. Jeg målte
   kun `zone` med `limit=5`, hvilket ikke kan afgøre det. Ikke relevant for
   mappingen, men det står i koden som en påstand ingen har efterprøvet.
4. **Hvorfor klonens spot har tre skemaer.** Målt at de findes og hvilke filer
   der har hvilket. Ikke undersøgt om det skyldes forskellige hentescripts over
   tid, eller om 2026-filerne kommer fra en anden kilde end 2022–2025. Sidste
   mulighed er værd at forfølge: 2026-filerne har 15-minutters opløsning og 6
   decimaler på DKK, hvor 2025-filerne har timeopløsning og 2 decimaler.
5. **Hvilken kurs klonens DKK-kolonner er beregnet med.** Målt at det er en
   dagsrate og hvilket interval den ligger i. Ikke fundet hvor den kommer fra,
   og derfor ikke rekonstruérbar for hullet. Blokerer DE-migrationen.
6. **Om nogen af de otte datasæts kolonnesæt ændrer sig over tid i API'et.**
   Kun 2026-03-15 er målt for headerne. `spot_dk`'s to klonvarianter viser at
   skemaer *har* ændret sig historisk uden at nogen bemærkede det.
7. **Områdekode-mappingen** (`NO2`↔`NO_2` osv.) er ikke løst her. Denne gate
   mapper kolonnenavne, ikke værdier inde i kolonnerne.

---

# KONKLUSION

Mappingen er udtømmende: 8 datasæt, alle v1- og API-kolonner gjort rede for,
begge regnestykker går op, håndhævet maskinelt af 76 tests. Seks af otte
datasæt er klar til Gate 2 uden forbehold.

Det der skal tages stilling til inden Gate 2 begynder:

1. **B2's fjerde spand.** `API_DROPPED` er tilføjet fordi de tre spande ikke
   kan rumme B3's beslutninger. Skal den kollapses tilbage, skal Gate 2 have
   droppelisten et andet sted fra.
2. **DE/DKK-kursen (Q6).** Blokerer `spot/DE_*`. Kursen er en dagsrate, ikke en
   konstant — det er nu målt, og det gør spørgsmålet sværere end antaget.
3. **NO2/SE3/SE4.** Kilden er tom. Filerne skal bevares.
4. **SYSTEM.** Ingen kilde findes. Kræver en eksplicit beslutning, ikke en
   stiltiende.
