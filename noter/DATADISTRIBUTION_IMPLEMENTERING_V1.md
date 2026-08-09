# Datadistribution til tredjepart — implementeringsudkast v1

**Dato:** 2026-08-07
**Status:** udkast til nyt projekt. Ikke eksekveret. Ingen ændringer foretaget.
**Repos i scope:** `skj-1964/fjernvarme-businesscase`, `skj-1964/df-data`, ny `skj-1964/df-mcp`
**Uden for scope:** DK1-forecastmodellen — en separat forecastmodel uden for dette projekts scope. Dette dokument rører den ikke.

---

## 0. Formål

Gøre det muligt for andre fjernvarmeværker at bygge driftsøkonomiske modeller
sammen med Claude, på Steens datagrundlag, uden at de skal installere noget —
og uden at de kan komme til at bygge en forkert model uden at opdage det.

Dokumentet samler beslutninger og målinger fra forarbejdet, så CC kan arbejde
videre uden at genudlede dem.

---

## 1. Arkitektur — tre kanaler, klar arbejdsdeling

Der findes tre veje til data. De konkurrerer ikke; de løser hver sit.

| Kanal | Til hvad | Målgruppe | Status |
|---|---|---|---|
| **`df-data`-repo** | Modelinput: flerårig, stabil, versioneret historik | Claude-brugere uden installation + lokale kørsler | Bygget, men ubefæstet |
| **REST-API (`api.sysapp.dk`)** | Direkte integration | Værkernes egne systemer: SCADA, dispatch, EnergyPRO | Live |
| **MCP-connector** | Live-opslag og ad hoc-spørgsmål i en samtale | Claude-brugere, senere live lastfordeling | Ikke bygget |

### 1.1 Hvorfor repoet — ikke MCP — er kanalen for modeldata

Tre egenskaber, MCP ikke kan levere:

1. **Nul friktion.** Enhver Claude-bruger kan bruge repoet i dag. En
   MCP-connector skal hver enkelt bruger selv tilføje og have token til. Det er
   en installation pr. person, ikke en delt ressource.
2. **Reproducerbarhed.** En bestyrelsesrapport skal kunne genudledes om to år.
   Et commit-SHA pinner datasættet eksakt; et live-API kan ikke. Derfor er den
   eksisterende beslutning i `_ensure_df_data_cache` om **ikke** at lave
   automatisk `git pull` korrekt og skal bevares.
3. **Volumen.** Et års 15-minutters balancedata er ~35.000 rækker. Det kan ikke
   passere et kontekstvindue. MCP er ikke en transportvej for modelinput.

### 1.2 Hvad MCP så er til

Vilkårlige datointervaller, dagsaktuelle tal, opslag der ikke er en modelkørsel.
Senere: live lastfordeling. MCP er et tyndt lag oven på REST-API'et, til den ene
overflade hvor et menneske sidder og spørger en sprogmodel.

**Præmis der skal fastholdes:** et værks eget system kalder REST-API'et direkte.
MCP eksisterer udelukkende for sprogmodellen.

### 1.3 Rækkefølge

MCP er **ikke** næste skridt. Rækkefølgen er:

1. Dæknings-assert i `fjernvarme-businesscase` (F1)
2. `DATA_VERSION` genereret af samme kodevej som skriver filerne (F2)
3. Migration af `update_data.py` til eget API (F6, se §10) — inkl. den
   navnekonvention-beslutning i §11 der er breaking for businesscase-loaderen
4. Hul i DE/NO2/SE3/SE4 lukket (F3) — afhænger af F6, se §10.4
5. Fast opdateringskadence + synlig heartbeat (F4)
6. Nye datasæt fra API'et (F7, se §12)
7. MCP-referenceserver (F5)

Begrundelse: F1 er det eneste punkt hvor den nuværende tilstand producerer
*forkerte svar der ser rigtige ud*. Alt andet er mindre alvorligt. F6 ligger
før F3, fordi hullet i DE/NO2/SE3/SE4 sandsynligvis er et symptom på netop den
kildeblanding F6 fjerner.

---

## 2. Målt tilstand pr. 2026-08-07

Alt i dette afsnit er **målt**, ikke læst i dokumentation. Metoden var: shallow
clone af begge repos, og direkte aflæsning af første/sidste række i hver CSV.

### 2.1 Dækning i `df-data`

| Fund | Værdi |
|---|---|
| Nyeste række i **alle** datasæt | 2026-06-27 21:45 UTC |
| `DATA_VERSION.md` påstår senest opdateret | 2026-06-29 |
| Sidste commit i repoet | 2026-08-04, "Hent fra api.sysapp.dk i stedet for www.sysapp.dk" |
| Repoets størrelse | ~62 MB |

Commit'et 4. august ændrede kun host og kørte ikke `scripts/update_data.py`.
Repoet er derfor ~6 uger bagud, og `DATA_VERSION.md` er hverken enig med
repoet eller med filerne.

### 2.2 Huller og mangler

| Datasæt | Fund |
|---|---|
| spot DE, NO2, SE3, SE4 | Hul fra **2025-09-30 22:00** til **2026-03-31 22:00** — seks måneder, netop vinteren 2025/26 |
| spot SYSTEM | Stopper 2025-02-06. Reelt dødt datasæt |
| afrr | Kun DK1. Ingen DK2 |
| mfrr_act, imbalance | Starter først marts 2025 |

### 2.3 Skema-inkonsistens

- DK1/DK2-spot har 8 kolonner (`id, hour_utc, hour_dk, price_area,
  spot_price_dkk, spot_price_eur, created_at, updated_at`).
- DE/NO2/SE3/SE4-spot har 5 (`hour_utc, hour_dk, price_area, spot_price_eur,
  spot_price_dkk`).
- `hour_dk` skifter mellem `T`- og mellemrums-separator — både mellem områder
  **og** mellem årgange inden for samme område (fx `DK1_2023.csv` bruger `T`,
  `DK1_2026.csv` bruger mellemrum).
- DMI-filer bruger unix-epoch heltal, ikke tekst-timestamps.
- Årsfilerne er navngivet efter **UTC**-året. Derfor indeholder hver
  `*_2022.csv` præcis 1 række (2022-12-31 23:00 UTC = 1. januar 2023 lokal tid).
  Det er korrekt opførsel, men skal dokumenteres, ikke opdages.

### 2.4 Målefejl jeg selv lavede — så CC ikke gentager den

Ved første gennemløb aflæste jeg kolonne 0 som tidsstempel. Det er forkert for
DK1/DK2-filerne, hvor kolonne 0 er `id`. Det gav en falsk melding om, at
DK1/DK2 manglede timestamps. **Aflæs efter kolonnenavn, aldrig efter position** —
skemaet er ikke ensartet på tværs af områder.

---

## 3. F1 — Dæknings-assert (højeste prioritet)

### 3.1 Defekten

I `src/data_loader_github.py` tester samtlige vagter `df.empty`:

```
linje 187, 194, 220, 245, 274, 291, 354, 366   →  if df.empty: raise
```

Ingen af dem tester **dækning**. Længere nede fyldes der ubetinget:

```
398:  merged = merged.fillna(0.0)
401:  merged = merged.reindex(time=target_index, fill_value=0.0)
459:  spot = spot_raw.reindex(idx).ffill().bfill()
```

> **Linjenumre skal verificeres ved HEAD før ændring.** De er aflæst i en shallow
> clone 2026-08-07 og drifter.

### 3.2 Konsekvensen

Kører en bruger i dag:

```bash
python run_case.py cases/billund_baseline.yaml --data-source github \
    --start 2025-08-01 --end 2026-07-31 --with-balancing
```

...er ingen frame tom. Kørslen bliver grøn. Men:

- Juli og august får **juni-prisen båret frem** af `ffill`.
- Balanceindtægten bliver **0** for de samme uger.

Konsekvensen er ikke støj — den er **retningsbestemt**. Balancemarkedets bidrag
er per repoets egen README forskellen mellem to kørsler, og nulfyldning kan kun
trække den forskel nedad. Modellen svarer altså systematisk, at balancemarkedet
er mindre værd end det er, med et tal der ser fuldstændig plausibelt ud.

Samme mønster som B11 i forecast-projektet: en tavs no-op der ikke kan skelnes
fra succes.

### 3.3 Kravet

En vagt der kører **før** enhver fyldning:

1. Mål faktisk `min(hour_utc)`, `max(hour_utc)` og huller pr. datasæt og område,
   ud fra de filer der rent faktisk indlæses.
2. Sammenlign med det ønskede `[start, end)`.
3. Rejs fejl med **begge** intervaller i beskeden — ønsket og målt — samt hvilket
   datasæt der fejlede.
4. Fyld aldrig uden for målt dækning. Hverken `ffill`, `bfill` eller `0.0`.

Inden for målt dækning er interpolation over enkelthuller acceptabel, men skal
rapporteres i kørselsloggen med antal fyldte punkter pr. datasæt.

### 3.4 Testkrav (P3: untested guards are not guards)

Vagten skal have en test der:

- beder om en periode der rækker ud over `max(hour_utc)` → forventer exception
- beder om en periode der falder i DE-hullet (fx 2025-11-01 til 2026-01-31)
  → forventer exception
- beder om en periode helt inden for dækning → forventer succes

Testen skal fejle på nuværende HEAD, før rettelsen. Det er beviset for at den
måler noget.

### 3.5 Åbent spørgsmål Q1

Skal `--external` (direkte Energinet/DMI-kald) have samme assert? Sandsynligvis
ja, men `data_loader.py` er ikke gennemgået i dette forarbejde. **Ikke antag —
mål først.**

---

## 4. F2–F4 — `df-data`-hygiejne

### F2. `DATA_VERSION.md` genereret af skrivevejen

`DATA_VERSION.md` skal skrives af den samme kodevej som skriver CSV-filerne, og
ud fra de faktisk skrevne rækker — ikke af et separat pass. Så kan den ikke
påstå 29. juni om et repo der blev rørt 4. august.

Tilføj felterne: `generated_at`, `commit_sha`, og pr. datasæt `first`, `last`,
`rows`, `gaps` (liste af intervaller).

### F3. Hullet i DE/NO2/SE3/SE4

Genhent 2025-10-01 → 2026-03-31 for de fire områder. Verificér mod
`api_entsoe_prices.php` at data faktisk findes i kilden før der konkluderes på
årsagen — hullet kan skyldes både fetch-fejl og kildemangel, og de to kræver
forskellig handling.

Beslut samtidig hvad der skal ske med `spot SYSTEM` (dødt siden 2025-02-06):
enten genoptag eller fjern. Et halvdødt datasæt i mappen er en fælde.

### F4. Kadence og heartbeat

- Fast opdateringskadence. **Ugentligt er nok** til businesscase-brug; kravet er
  ikke "dagligt", men "ikke ældre end den periode nogen spørger om" — og det
  krav håndhæves af F1, ikke af kadencen.
- **Friskhed er ikke en vagt.** Dør cron'en, fryser repoet, og kørslerne bliver
  grønne alligevel. Derfor er F1 forudsætning for at F4 giver mening — ikke
  omvendt.
- Heartbeat: commit skal ske også når intet nyt data er hentet, med tydelig
  markering, så stilstand kan skelnes fra tavshed. Alternativt en
  `LAST_RUN.json` med tidsstempel og udfald.

---

## 5. F5 — MCP-referenceserver (`df-mcp`)

### 5.1 Hvad der er værd at dele

Plumbingen er få hundrede linjer og kan skrives af enhver. **Det genbrugelige er
kontrakten**: halvåbent interval, UTC-only, `raw` vs. `final`, opløsning, og at
et filter aldrig må ignoreres tavst. Det er det, ingen får rigtigt fra bunden.

Artefaktet er derfor et MIT-licenseret template-repo hvor **base-URL er
konfiguration**, så et værk med egen API kan pege det et andet sted hen. Plus én
referencedeployment Steen selv hoster, som on-ramp.

### 5.2 Fem designvalg

1. **Tools er ikke 1:1 med endpoints.** En HTTP-proxy er ubrugelig for en
   sprogmodel. Byg værktøjer der besvarer spørgsmål og lad serveren aggregere.
2. **Hårdt rækkeloft med tvungen aggregering over det** — aldrig tavs
   trunkering. `meta` med i hvert svar: faktisk anvendt interval, opløsning,
   kollaps.
3. **Ingen default der aggregerer.** `mode` skal være eksplicit. En aggregering
   er en påstand om nøglen, og påstanden skal kalderen fremsætte — det gælder
   dobbelt når kalderen er en model der gætter defaults.
4. **Værktøjsbeskrivelsen er dokumentationen.** Modellen læser den, og kun den.
   At `time_dk` ikke er entydig, at balancedata er 15-minutters, at `request_mw`
   er fortegnsbærende — det hører i `description`-feltet, ikke i en README.
5. **Read-only, uden undtagelse.** Med live lastfordeling forude: et
   skriveværktøj i en connector er en dispatch-ordre en sprogmodel kan afgive.
   Grænsen trækkes nu, mens den er gratis.

### 5.3 Foreslået værktøjskatalog (udkast)

| Tool | Formål |
|---|---|
| `coverage` | Dækning og friskhed pr. datasæt og område. **Skal kaldes før alt andet.** |
| `spot_summary` | Aggregeret spot for periode/område: statistik og båndfordeling |
| `spot_series` | Rå/resamplet spotserie, med rækkeloft |
| `balance_summary` | mFRR/aFRR/ubalance aggregeret for periode |
| `mfrr_request` | Realtids-mFRR-request, med eksplicit `mode` |
| `weather_series` | DMI obs/forecast for område |

`coverage` er den vigtigste. Det er samme lektie som F1, bare flyttet et lag op:
modellen skal kunne tjekke dækning **før** den svarer, ikke bagefter.

### 5.4 Transport og hosting

- **Streamable HTTP**: JSON-RPC over POST på én sti. Ikke de nuværende
  GET-endpoints. Kan implementeres statsløst, også i PHP — det er et nyt lag ved
  siden af, ikke en omskrivning.
- **Egen sti eller subdomæne**: `api.sysapp.dk/mcp` eller `mcp.sysapp.dk`,
  adskilt fra REST-fladen. Så kan auth, rate limits og logging sættes på
  MCP-trafikken uden at røre det API værkernes systemer kalder direkte — og
  MCP'en kan tages ned uden at data tages ned.
- **Auth**: bearer-token via Request headers i connector-dialogen er nok til en
  reference. OAuth først hvis der bliver behov for pr.-bruger-adgang.

### 5.5 Nåelighed — hvad der er verificeret og hvad der ikke er

**Verificeret:** `api.sysapp.dk` er offentligt nåelig over HTTPS med gyldig TLS
fra Anthropics infrastruktur. Bevis: `web_fetch` hentede `swagger.html` og
`openapi.json` 2026-08-07. Den vej går netop gennem Anthropics infrastruktur,
som er den samme der brokerer connector-trafik.

**Ikke evidens om serveren:** kodesandkassen får `HTTP/2 403,
x-deny-reason: host_not_allowed`. Det er sandkassens egen egress-allowlist,
ikke Steens firewall. De to må ikke sammenblandes.

**Stadig uafklaret — skal tjekkes ved opsætning:**

- WAF/CDN/rate-limiter foran serveren kan afvise med 403/429 før applikationen
  ser kaldet. Tjek edge-logs for svar applikationen ikke selv genererede.
  Anthropics udgående IP-range: `platform.claude.com/docs/en/api/ip-addresses`.
- **Ingen redirect på MCP-stien.** Returnerer den registrerede URL 301/302/307/308
  til en anden vært, tabes Authorization-headeren. Reel risiko her, fordi
  `www.sysapp.dk` og `api.sysapp.dk` er separate værter med forskellig dækning.
  Verificér med `curl -sI` på den endelige MCP-URL.

---

## 6. Sikkerhed og drift

- **Read-only** på alle værktøjer (5.2.5).
- **Rate limiting** på MCP-stien. Ukendt belastning fra fremmede brugere er ny
  risiko; REST-API'et har i dag ingen.
- **Ingen hemmeligheder i `df-data`.** Repoet er offentligt. Alt der lægges der,
  ligger der permanent i historikken.
- **Note:** `doc/notat_bestyrelse_datasikkerhed.docx` findes allerede i
  businesscase-repoet og er ikke læst i dette forarbejde. Den bør gennemgås for
  konflikter med ovenstående før publicering.

---

## 7. Principper der gælder på tværs

Arvet fra forecast-projektet, og alle bekræftet af fundene her:

- **P3** — Untested guards are not guards. Gælder F1's test (3.4).
- **P7** — Aggregation is a claim about the key. Gælder MCP's `mode` (5.2.3).
- **Fail-visible er ikke arkitektonisk** — det skal asserteres, ikke antages.
  `df.empty` er ikke en dækningstjek; en tom-tjek beviser ikke fuldstændighed.
- **Separation af målt vs. argumenteret.** Alt i afsnit 2 er målt. Alt i afsnit
  3.5 og 4/F3 er åbent og skal måles før der handles.
- **Et datasæt uddelt uden sin kontrakt er ikke en tjeneste** — det er
  distribution af de fejl, man selv brugte måneder på at finde.

---

## 8. Åbne spørgsmål

| Nr. | Spørgsmål |
|---|---|
| Q1 | Skal `--external`-vejen have samme dæknings-assert? `data_loader.py` er ikke gennemgået. |
| Q2 | Hullet i DE/NO2/SE3/SE4 — fetch-fejl eller kildemangel? Afgøres mod ENTSO-E før handling. |
| Q3 | `spot SYSTEM`: genoptag eller fjern? |
| Q4 | Skal `df-data` skifte fra CSV til parquet? Størrelse og indlæsningstid taler for; diff-barhed i git taler imod. |
| Q5 | Hvem hoster referencedeploymentet på sigt, hvis det får brugere ud over pilotkredsen? |
| Q6 | Hvilken EUR/DKK-kurs er brugt til `spot_price_dkk` for DE/NO2/SE3/SE4, og er den konstant? Se §10.4. |
| Q7 | `resolution_minutes` fra ENTSO-E: hvad sker der ved skifte 60→15? Se §10.4. |
| Q8 | Skal `mfrr_request` arkiveres i `df-data`? Kilden har kun 7 dages retention. Se §12. |

---

## 9. Første konkrete opgave til CC

**F1, gate-opdelt:**

- **Gate 0 (read-only):** Verificér linjenumrene i 3.1 ved HEAD. Kortlæg
  præcist hvor fyldning sker, og om `data_loader.py` (`--external`) har samme
  mønster. Rapportér — skriv intet.
- **Gate 1:** Skriv testen fra 3.4. Bekræft at den **fejler** på nuværende HEAD.
- **Gate 2:** Implementér vagten. Testen skal derefter bestå, og de eksisterende
  kørsler i README'ens eksempler skal fortsat virke inden for dækket periode.

---

## 10. F6 — Al hentning gennem eget API

### 10.1 Målt udgangspunkt

`scripts/update_data.py` henter i dag fra **to** kilder:

```
42:  BASE_URL_PROXY = "https://api.sysapp.dk"          → kun DMI
43:  BASE_URL_EDS   = "https://api.energidataservice.dk/dataset"
```

Fem af seks datasæt går uden om eget API, direkte til Energinet:

| Kaldes i dag | Linje | Dataset |
|---|---|---|
| `fetch_eds("DayAheadPrices")` | 194 | spot |
| `fetch_eds("AfrrReservesNordic")` | 219 | afrr |
| `fetch_eds("MfrrCapacityMarket")` | 226 | mfrr_cap |
| `fetch_eds("MfrrEnergyActivationMarket")` | 233 | mfrr_act |
| `fetch_eds("ImbalancePrice")` | 240 | imbalance |
| `api_dmi_obs_ny.php` | 114 | dmi |

Det er den kildeblanding, F6 fjerner. Den er også den direkte årsag til
skema-inkonsistensen i §2.3 og formentlig til hullet i §2.2.

### 10.2 Ny kildetabel

| Datasæt | Nyt endpoint | Kontrakt |
|---|---|---|
| spot DK1/DK2 | `api_energinet_prices.php` | løs |
| spot DE/NO2/SE3/SE4 | `api_entsoe_prices.php` | løs, **kun EUR** — se 10.4 |
| imbalance | `api_eds_balance.php?dataset=imbalance_price` | streng |
| mfrr_act | `api_eds_balance.php?dataset=mfrr_activation` | streng |
| mfrr_cap | `api_eds_balance.php?dataset=mfrr_capacity` | streng |
| afrr | `api_eds_balance.php?dataset=afrr_capacity` | streng |
| dmi | `api_dmi_obs_ny.php` | løs — uændret |

Efter F6 er `BASE_URL_EDS` slettet. Ingen kodevej i `df-data` må kende
`api.energidataservice.dk`.

### 10.3 Fem kontraktforskelle der skal håndteres i migrationen

De strenge endpoints opfører sig bevidst anderledes end EDS. Hver forskel er en
potentiel tavs fejl:

1. **Halvåbent interval `[startdate, enddate)`.** EDS-kaldene i dag bruger
   `start`/`end`. Ved migration skal `enddate` sættes til dagen **efter** den
   ønskede sidste dag, ellers mistes et døgn i hver kørsel — usynligt, fordi
   filen stadig ser fyldt ud.
2. **`enddate` må aldrig udelades for kapacitetstabellerne.** `mfrr_capacity`
   rækker 26 timer frem, `afrr_capacity` 29 timer. Uden `enddate` er øvre
   grænse `MAX(time_utc)+1s`, ikke "nu" — og arkivet forurenes med
   fremtidsrækker der senere revideres. Sæt altid eksplicit `enddate` og
   verificér `meta.to_exclusive_source == "enddate parameter"`.
3. **Ukendte parametre giver 400.** Det er en feature: gammel kaldekode fejler
   højlydt i stedet for at blive ignoreret. Fang ikke 400 bredt — lad den
   boble op.
4. **Kun UTC, ingen `tz`-parameter.** `time_dk` følger med, men er ikke entydig
   hen over efterårets sommertidsskift og må aldrig bruges som nøgle eller
   som sorteringsakse i fletningen.
5. **Pagination gennem `meta.has_more` / `meta.next_offset`,** ikke gennem
   "tom side"-mønstret i den nuværende `fetch_eds`-løkke. `limit` maks. 10000.

Brug `format=csv`. Det omgår at DECIMAL-kolonner serialiseres som JSON-strenge
i JSON-svaret.

### 10.4 Konsekvens: spot for udlandet er ikke samme datasæt

`api_energinet_prices.php` understøtter kun `area=DK1|DK2`. DE/NO2/SE3/SE4 skal
hentes fra `api_entsoe_prices.php`, som returnerer et **andet skema**:

```
timestamp, area, price_eur_mwh, resolution_minutes
```

Ingen DKK-kolonne. Områdekoderne er `DE_LU`, `NO_2`, `SE_3`, `SE_4` — ikke `DE`,
`NO2`, `SE3`, `SE4`. Det forklarer både 5-kolonne-skemaet og `T`-separatoren i
de nuværende filer, og sandsynligvis også hullet.

To ting skal afgøres, ikke antages:

- **Q6 — hvilken EUR/DKK-kurs?** `DE_2026.csv` har en `spot_price_dkk`-kolonne,
  som API'et ikke leverer. Den er altså beregnet et sted. Med hvilken kurs, og
  er den konstant over hele perioden? En businesscase i DKK hviler på det svar.
  Anbefaling: gem **kun** `price_eur_mwh` i repoet og lad omregningen ske i
  modellen med en eksplicit, konfigurerbar kurs. En hardcodet kurs bagt ind i
  et datasæt er en skjult antagelse.
- **Q7 — `resolution_minutes`.** Feltet findes i svaret, fordi ENTSO-E er på vej
  mod 15-minutters day-ahead. Skifter det fra 60 til 15, bryder
  time-antagelsen i `df-data` tavst. Skriv feltet med i filen, og assertér på
  det ved indlæsning. Det er B31 (resolution conflation) i ny indpakning.

---

## 11. Output-kontrakt mod `fjernvarme-businesscase`

### 11.1 Den målte kollision

`data_loader_github.py` læser i dag **rå EDS-PascalCase** for balancedatasættene.
Eget API leverer snake_case. De to sæt navne står side om side her:

| Loader forventer (linje) | API leverer |
|---|---|
| `TimeUTC` (279, 296, 356, 368) | `time_utc` |
| `UpPriceDKK` / `DownPriceDKK` (283-284, 360) | `up_price_dkk` / `down_price_dkk` |
| `UpProcuredMW` / `DownProcuredMW` (285-286, 361) | `up_procured_mw` / `down_procured_mw` |
| `aFRRVWAUpDKK` / `aFRRVWADownDKK` (301-302) | `afrr_vwa_up_dkk` / `afrr_vwa_down_dkk` |
| `mFRRMarginalPriceUpDKK` / `...DownDKK` (303-304) | `mfrr_marginal_price_up_dkk` / `..._down_dkk` |
| `ImbalancePriceDKK` (305) | `imbalance_price_dkk` |
| `TotalmFRRUpMW` (372) | `total_mfrr_up_mw` |

**F6 er derfor breaking for businesscase-repoet.** Migrationen kan ikke laves i
`df-data` alene. Det er den vigtigste enkeltoplysning i dette afsnit.

Spot og DMI kolliderer derimod ikke: loaderen bruger allerede `hour_utc`,
`price_area`, `spot_price_dkk` (linje 184-203), hvilket matcher
`api_energinet_prices.php` og `api_dmi_obs_ny.php` præcist. Kun de fire
balancedatasæt skifter vokabular.

### 11.2 Beslutning

**Normalisér til snake_case i `df-data`, og ret loaderen tilsvarende.**

Alternativet — at `update_data.py` oversætter tilbage til PascalCase — betyder,
at `df-data` permanent bærer rundt på et leverandørskema, det ikke længere rører.
Loaderens egen docstring (linje 130) beskriver allerede den dobbelte
navnekonvention som en undtagelse, der skal huskes. Migrationen er anledningen
til at fjerne den, ikke til at cementere den.

Prisen er et koordineret, brydende skifte. Det skal håndteres eksplicit:

- `DATA_VERSION.md` får `schema_version: 2` med kolonne-mapping fra v1.
- Ændringen i begge repos i samme arbejdsgang, med krydsreference i
  commit-beskeden.
- Loaderen læser `schema_version` og **rejser en klar fejl** ved v1-data i
  stedet for at fejle på en manglende kolonne dybt i en `astype`.

Punkt tre er det egentlige krav. Uden det bliver et repo-skifte til en
`KeyError` femten kald nede i kaldstakken, hos en bruger der ikke ved hvad
`df-data` er.

### 11.3 Kanonisk filformat efter F6

Uændret struktur — `{datasæt}/{område}_{år}.csv`, årsfiler efter **UTC**-året.
Ændringer:

- Alle tidskolonner hedder `time_utc` (balance) eller `hour_utc` (spot, dmi),
  altid `YYYY-MM-DD HH:MM:SS`, altid mellemrum som separator. `T`-varianten
  udgår.
- `time_dk` / `hour_dk` skrives **ikke** til fil. De er ikke entydige og har
  ingen anvendelse, når aksen er UTC. At udelade dem er billigere end at
  advare mod dem.
- `id`, `created_at`, `updated_at` udgår. De er interne til databasen og siger
  intet om måleværdien.
- `resolution_minutes` skrives med, hvor API'et leverer det.
- Ingen beregnede kolonner. Enhedsomregning og valutakonvertering hører til i
  modellen, ikke i arkivet.

De tre sidste punkter er samme princip: **arkivet gemmer, hvad kilden sagde —
ikke hvad vi mener, den betød.**

---

## 12. F7 — Nye datasæt der bør ind i `df-data`

Tilgængelige på API'et i dag, ikke i repoet, og relevante for en businesscase:

| Endpoint | Hvorfor det betyder noget for en case |
|---|---|
| `api_ngas.php` | TTF-gaspris. Sætter den marginale prisdannelse i timerne hvor gas er på marginalen — altså netop dem, en varmepumpe/kedel-beslutning afhænger af. Brug `period=M1`. |
| `api_magasin_data.php` | Norske magasinfyldninger, ugentligt. Den langsomme driver bag NO2 og dermed DK1-vinterpriser. |
| `api_energinet_grid2.php` | Produktion pr. kilde + CO2-intensitet. Nødvendig for enhver case med et CO2-argument. |
| `api_entsoe_crossborder.php` | Flow over DK1-grænserne. Forklarer prisspring, som spot alene ikke gør. |
| `api_capacity.php` | Installeret kapacitet pr. måned. Til normalisering over flerårige perioder. |
| `api_entsoe_solar_wind.php` | Sol-/vindforecast. Kun relevant, hvis casen skal se på forecast-usikkerhed. |

**Prioritér `ngas` og `magasin` først.** De er små, langsomme og forklarer mest
pr. megabyte. `grid2` og `crossborder` er store og bør vurderes mod repo-vækst
(Q4 om parquet bliver relevant her).

To ting, der ikke skal ind:

- `api_dk1_forecast.php` — hører til forecast-projektet, og tre af dens actions
  er målt i stykker (`forecast`, `runs`, `proxies` returnerer HTTP 200 med
  uparsebar PHP-fejl).
- `api_mfrr_request.php` — **men noter muligheden.** Kilden har kun 7 dages
  retention hos Energinet. Et arkiv i `df-data` ville være den eneste durable
  kopi. Det er en selvstændig beslutning med egen kadence, ikke en del af F7.

---

## 13. Opgaverækkefølge for F6/F7

- **Gate 0 (read-only):** Kald hvert nyt endpoint for én kendt dag, og sammenlign
  række for række mod den eksisterende CSV for samme dag. Rapportér afvigelser
  i værdier, ikke kun i kolonnenavne. Skriv intet.
- **Gate 1:** Skriv kolonne-mappingen v1→v2 ud fra Gate 0's faktiske svar — ikke
  ud fra tabellen i §11.1, som er læst fra OpenAPI-specen og skal verificeres.
- **Gate 2:** Migrér `update_data.py`. Slet `BASE_URL_EDS`. Kør mod en enkelt
  måned i en engangsmappe og diff mod eksisterende filer.
- **Gate 3:** Ret loaderen, tilføj `schema_version`-tjekket, kør begge repos'
  eksempler igennem.

`--force`-genhentning af hele historikken sker **først** når Gate 0-2 er grønne.
