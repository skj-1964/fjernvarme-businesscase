# F8 Gate 0 + Q2 — Måling mod kilden

**Status:** Read-only med netværk. 26 API-kald, alle gemt i `/tmp/f8_gate0/`.
df-data-klonen er urørt (`6c95bde`, tom `git status`). 28 tests stadig grønne.
**Forudsætninger:** [Gate 0.5](notat_f1_gate05_oploesning_akse.md), [Gate 1](notat_f1_gate1_test.md), [F1b/F1c](notat_f1bc_akse_og_rapport.md).
**Dato:** 2026-08-07

**Hovedfund:** F8's tre huller har **to forskellige årsager**, og de tre huller
er tre forskellige sager. DST-hullet er genopretteligt; 2026-hullerne er ikke.
Q2's hul er også to sager: DE_LU er genopretteligt, NO_2/SE_3/SE_4 er ikke.

---

## Præmis-korrektioner

1. **`scripts/update_data.py` findes ikke i dette repo.** Den ligger i
   df-data-klonen: `data/df-data/scripts/update_data.py`. Linje 114 er
   verificeret dér.
2. **`openapi.json` findes ikke lokalt.** Den er hentet fra
   `https://api.sysapp.dk/openapi.json` (84 814 B, `Sysapp Energy Data API`
   v1.5.2, OpenAPI 3.1.0). Det er ét kald ud over de nævnte endpoints, men
   prompten navngiver den eksplicit.
3. **De refererede §5.5, §10.4 og §12 findes ikke i noget dokument i repoet.**
   Jeg har fulgt deres operationelle anvisninger (redirect-tjek, PHP-fejl i
   200-kroppe, verifikation af områdekoder mod spec) uden at kunne verificere
   selve påstandene mod en kilde.

---

# DEL 3 — NÅELIGHED (rapporteres først, da alt andet afhænger af den)

| | |
|---|---|
| Vej | **Direkte**. Ingen proxy nødvendig. |
| Server | `Apache/2.4.58 (Ubuntu)`, HTTP/2 |
| Auth | **Ingen krævet**. Alle kald gik igennem uden headers ud over `User-Agent`. |
| Redirects | **Ingen.** `curl -sI` på alle fire stier: `redirect_url` tom i alle tilfælde. §5.5's advarsel om tabt `Authorization` er derfor ikke relevant her — der er hverken redirect eller auth. |
| Svartider | 0,01–0,15 s. Rodsiden svarede på 0,03 s. |
| PHP-fejl i 200-kroppe | **Ingen.** Alle 26 kald tjekket for `<br />`, `Fatal error`, `Warning:`, `Notice:`, `Parse error`, `<b>` i kroppen. Nul træffere. Alle svar var gyldig JSON med `status: "success"`. |

Statuskoder på de kaldte stier uden parametre: `api_dmi_obs_ny.php`,
`api_entsoe_prices.php` og `api_energinet_prices.php` gav alle **400** med
125 B — korrekt afvisning af manglende `startdate`, ikke et udfald.
`openapi.json` gav 200.

Rodsiden `https://api.sysapp.dk/` svarer 200 med 62 B statisk HTML
(*"Ingenting her…"*, `last-modified: 2018-01-17`). Ikke en fejl — bare en
tom forside.

Fuld kaldslog: `/tmp/f8_gate0/calls.log`. Rå svar: `/tmp/f8_gate0/raw/`.

---

# DEL 1 — F8: FINDES DST-TIMEN I KILDEN?

## Kaldesyntaks

Fra `data/df-data/scripts/update_data.py:105-114`:

```python
params = {
    "shortname": "all", "startdate": start, "enddate": end,
    "area": area, "limit": limit, "offset": offset, "format": "json",
}
url = f"{BASE_URL_PROXY}/api_dmi_obs_ny.php?" + urllib.parse.urlencode(params)
```

**Krydstjek mod `openapi.json` afslører to ting update_data.py gør forkert:**

| parameter | i spec | hvad update_data.py sender |
|---|---|---|
| `tz` | enum `['dk','utc']`, **default `dk`** | **sendes ikke** ⇒ får `dk` |
| `fields` | komma-sep. liste eller `all` | sender `shortname=all` — **ikke en dokumenteret parameter** |

`tz` defaulter til **`dk`** på dette endpoint. Til sammenligning defaulter
`api_entsoe_prices.php` til `utc`. De tre endpoints har altså ikke samme
tz-default, og hentescriptet sætter den ikke.

Jeg har kaldt med `tz=utc` **og** `tz=dk` for at kunne skelne.

## 1.1 — DST-tilbagestillingen 2025-10-25/26

| kald | rækker |
|---|---|
| `fyn` / `karup` / `vestkyst`, `tz=utc` | **48** (= 2 × 24 UTC-timer) |
| `fyn` / `karup` / `vestkyst`, `tz=dk` | **49** (= 24 + 25 lokale timer) |

Begge er interne konsistente og komplette. Kilden mangler ingenting.

**Felter i svaret:** `unixtime`, `hour_utc`, `hour_dk`, `area`,
`temp_mean_past1h`, `radia_glob_past1h`, `wind_speed_past1h`,
`precip_past1h`, `pressure`, `humidity_past1h`, `cloud_cover`.

**Vinduet 2025-10-25 20:00 .. 2025-10-26 04:00, `fyn`, `tz=utc`, ordret:**

```
hour_utc=2025-10-25 20:00:00  hour_dk=2025-10-25 22:00:00  unixtime=1761422400  temp=9.55
hour_utc=2025-10-25 21:00:00  hour_dk=2025-10-25 23:00:00  unixtime=1761426000  temp=9.5
hour_utc=2025-10-25 22:00:00  hour_dk=2025-10-26 00:00:00  unixtime=1761429600  temp=9.375
hour_utc=2025-10-25 23:00:00  hour_dk=2025-10-26 01:00:00  unixtime=1761433200  temp=9.2
hour_utc=2025-10-26 00:00:00  hour_dk=2025-10-26 02:00:00  unixtime=1761436800  temp=9.025   ←┐ samme
hour_utc=2025-10-26 00:00:00  hour_dk=2025-10-26 02:00:00  unixtime=1761440400  temp=9.0     ←┘ etiket
hour_utc=2025-10-26 02:00:00  hour_dk=2025-10-26 03:00:00  unixtime=1761444000  temp=8.775
hour_utc=2025-10-26 03:00:00  hour_dk=2025-10-26 04:00:00  unixtime=1761447600  temp=8.6
hour_utc=2025-10-26 04:00:00  hour_dk=2025-10-26 05:00:00  unixtime=1761451200  temp=8.4
```

Identisk mønster i `karup` og `vestkyst`, og identisk for `tz=dk`.

### Kernespørgsmålet: JA — kilden har begge observationer

To rækker med **forskellig `unixtime`**, præcis 3600 s fra hinanden, men
**samme `hour_utc` og samme `hour_dk`**. `hour_utc=2025-10-26 01:00` findes
slet ikke i svaret.

`unixtime` er korrekt og entydig:

| unixtime | korrekt UTC | korrekt DK |
|---|---|---|
| 1761433200 | 2025-10-25 23:00 | 2025-10-26 01:00 **+02:00** |
| 1761436800 | 2025-10-26 00:00 | 2025-10-26 02:00 **+02:00** (CEST) |
| **1761440400** | **2025-10-26 01:00** | 2025-10-26 02:00 **+01:00** (CET) |
| 1761444000 | 2025-10-26 02:00 | 2025-10-26 03:00 +01:00 |

De to rækker ER de to lokale 02:00-timer — den før og den efter
tilbagestillingen. Kilden har dem begge. **`hour_utc` kollapser dem til
samme etiket, og `hour_dk` gør det også.**

### Serverside-fejlen består

Commit `6c95bde` i df-data forklarer at endpointet brugte
`FROM_UNIXTIME(unixtime)` med session-tz `SYSTEM = Europe/Copenhagen`, og at
det blev **rettet serverside 2026-07-15**. Målingen i dag viser at rettelsen
er **ufuldstændig**: `hour_utc` er korrekt for alle timer undtagen netop
DST-tilbagestillingen, hvor den stadig kollapser to timer til én.

## 1.2 — 29/30-timers-hullet, 2026-02-28/03-01

| station | rækker i kilden | mangler i kilden | interval |
|---|---|---|---|
| `fyn` | **19/48** | **29** | 2026-02-28 11:00 .. 2026-03-01 15:00 |
| `karup` | **48/48** | **0** | — |
| `vestkyst` | **18/48** | **30** | 2026-02-28 11:00 .. 2026-03-01 16:00 |

**Kilden mangler de samme timer som klonen.** `karup` er kontrolgruppen og har
alle 48 — udfaldet er stationsspecifikt, ikke et generelt API-udfald i
perioden.

## 1.3 — Den forskudte start, 2026-01-01

| station | rækker | første | 00:00 til stede | 01:00 til stede |
|---|---|---|---|---|
| `fyn` | **22/24** | 2026-01-01 02:00 | nej | nej |
| `karup` | **24/24** | 2026-01-01 00:00 | ja | ja |
| `vestkyst` | **22/24** | 2026-01-01 02:00 | nej | nej |

Samme billede: kilden mangler dem, `karup` har dem.

## 1.4 — Kilde vs. klon

**Join på `unixtime`, DST-vinduet:**

| station | joinede rækker | ens `hour_utc` | max abs. Δtemp |
|---|---|---|---|
| `fyn` | 47 | 46/47 | **0,000000** |
| `karup` | 47 | 46/47 | **0,000000** |
| `vestkyst` | 47 | 46/47 | **0,000000** |

Værdierne matcher **eksakt**. Den ene uenighed er lærerig:

```
unixtime=1761440400   kildens hour_utc=2025-10-26 00:00   klonens hour_utc=2025-10-26 01:00
```

**Klonen har ret, kilden tager fejl.** Genberegningen fra `unixtime` i
`6c95bde` gav den korrekte etiket, mens API'et stadig leverer den forkerte.

**Hvilken række mangler i klonen?** Præcis én, og den samme i alle tre
stationer:

```
fyn       unixtime der mangler: [1761436800]   korrekt UTC=2025-10-26 00:00   temp=9.025
karup     unixtime der mangler: [1761436800]   korrekt UTC=2025-10-26 00:00   temp=8.3
vestkyst  unixtime der mangler: [1761436800]   korrekt UTC=2025-10-26 00:00   temp=10.2667
```

Klonen i vinduet: `22:00, 23:00, 01:00, 02:00, 03:00` — **00:00 mangler**,
01:00 er der.

### Mekanismen, fuldt fastlagt

1. Ved den oprindelige hentning leverede API'et begge rækker med **samme**
   (dengang forkerte) `hour_utc`.
2. `merge_into_yearfile` dedupliker på `time_col` = `hour_utc`. De to rækker
   kolliderede; én blev kasseret — `unixtime=1761436800`.
3. `6c95bde` genberegnede `hour_utc` fra `unixtime` **uden ny hentning**. Den
   overlevende række fik sin korrekte etiket 01:00. Den kasserede kunne ikke
   genopstå.
4. Resultat: hul ved 00:00, ikke ved 01:00.

Commit-beskedens *"alle raekker joiner paa unixtime, nul afvigelser, ingen
dubletter"* er sand — den kasserede række var allerede væk da verifikationen
blev lavet.

**For 1.2 og 1.3 er kildens og klonens huller identiske:**

```
1.2 fyn       kilde=19 klon=19 | i kilde men ikke klon: [] | i klon men ikke kilde: []
1.2 vestkyst  kilde=18 klon=18 | [] | []
1.3 fyn       kilde=22 klon=22 | [] | []
1.3 vestkyst  kilde=22 klon=22 | [] | []
```

Klonen taber intet dér. Kilden har det ikke.

---

# DEL 2 — Q2: FINDES SPOT-DATA I HULLET?

## Områdekoder verificeret mod spec

`openapi.json` → `/api_entsoe_prices.php` → `area.enum`:

```
['DE_LU', 'DK_1', 'DK_2', 'FR', 'NO_2', 'SE_3', 'SE_4', 'NL', 'BE']
```

§10.4's påstand er **bekræftet**: `DE_LU`, `NO_2`, `SE_3`, `SE_4` — ikke
`DE`, `NO2`, `SE3`, `SE4`. Klonens filnavne bruger de korte former, som ikke
er API'ets koder.

## 2.1 — Midt i hullet, 2025-12-15

| område | HTTP | `status` | `total_records` | PHP-fejl |
|---|---|---|---|---|
| **DE_LU** | 200 | success | **96** | nej |
| NO_2 | 200 | success | **0** | nej |
| SE_3 | 200 | success | **0** | nej |
| SE_4 | 200 | success | **0** | nej |

**DE_LU har data midt i hullet.** 96 rækker, 15-minutters opløsning,
`2025-12-15 00:00 .. 23:45`.

De tre tomme svar er **rene tomme 200'ere, ikke fejl**. Ordret (NO_2):

```json
{
    "status": "success",
    "meta": {
        "startdate": "2025-12-15", "enddate": "2025-12-15",
        "timezone": "utc", "area": "NO_2",
        "fields": ["timestamp","area","price_eur_mwh","resolution_minutes"],
        "total_records": 0, "returned_records": 0,
        "available_areas": ["DE_LU","DK_1","DK_2","FR","NO_2","SE_3","SE_4","NL","BE"]
    },
    "data": []
}
```

`available_areas` bekræfter at koden blev accepteret. Der er simpelthen ingen
rækker.

**Felter og `resolution_minutes`:** `timestamp`, `area`, `price_eur_mwh`,
`resolution_minutes`. Feltet findes og er `15` for DE_LU på denne dag.

## 2.2 — Grænserne

| dato | DE_LU rækker | interval | `resolution_minutes` |
|---|---|---|---|
| 2025-09-30 | **24** | 00:00 .. 23:00 | **60** |
| 2025-12-15 | **96** | 00:00 .. 23:45 | **15** |
| 2026-03-31 | **96** | 00:00 .. 23:45 | **15** |

Opløsningsskiftet 60 → 15 er **bekræftet**, men det skete **inde i hullet**,
ikke ved dets slutning: DE_LU var allerede 15-min 2025-12-15. Klonens data
er hourly før hullet og 15-min efter, hvilket er konsistent — men skiftets
faktiske dato ligger et sted mellem 2025-10-01 og 2025-12-15 og er ikke
indsnævret her.

**NO_2, SE_3, SE_4 giver 0 rækker på alle tre datoer** — også 2025-09-30 og
2026-03-31, hvor klonen **har** data. Kilden kan altså ikke reproducere data
klonen allerede besidder.

## 2.3 — Kontrol, DK1 2025-12-15

| kilde | rækker | interval | opløsning |
|---|---|---|---|
| `api_energinet_prices.php`, DK1 | **96** | 00:00 .. 23:45 | 900 s |
| `api_entsoe_prices.php`, DK_1 | **96** | 00:00 .. 23:45 | 15 min |

DK leverer data den dag fra begge endpoints. **Hullet er områdespecifikt, ikke
et generelt udfald i perioden.**

## 2.4 — DKK-kolonne? NEJ

| endpoint | felter |
|---|---|
| `api_entsoe_prices.php` | `timestamp`, `area`, **`price_eur_mwh`**, `resolution_minutes` |
| `api_energinet_prices.php` | `id`, `hour_utc`, `hour_dk`, `price_area`, **`spot_price_dkk`**, `spot_price_eur`, `created_at`, `updated_at` |

**ENTSO-E-endpointet leverer kun EUR.** Skal DE/NO2/SE3/SE4 bruges i DKK, skal
kursen påføres et andet sted. `api_energinet_prices.php` leverer DKK, men kun
for DK1/DK2.

---

# MÅLT vs. USIKKERT

## MÅLT

- Direkte adgang, ingen auth, ingen redirects, ingen PHP-fejl i nogen af
  de 26 kroppe.
- `api_dmi_obs_ny.php` har `tz` med default `dk`; `update_data.py` sender den
  ikke.
- Kilden har **begge** DST-observationer (`unixtime` 1761436800 og
  1761440400), men giver dem samme `hour_utc` og samme `hour_dk`.
- Klonen mangler `unixtime=1761436800` i alle tre stationer; klonens
  `hour_utc` for 1761440400 er korrekt, kildens er ikke.
- Alle joinede temperaturværdier matcher eksakt (Δ = 0,000000).
- Kilden mangler 29 t (`fyn`) / 30 t (`vestkyst`) i 2026-02-28/03-01 og
  2 t 2026-01-01; `karup` mangler intet.
- Kildens og klonens huller er identiske for 1.2 og 1.3.
- DE_LU har 96 rækker 2025-12-15; NO_2/SE_3/SE_4 har 0 på alle tre testdatoer.
- De tomme svar er `status: success`, `total_records: 0` — ikke fejl.
- DE_LU: 60 min på 2025-09-30, 15 min fra senest 2025-12-15.
- DK1 har data 2025-12-15 fra begge endpoints.
- `api_entsoe_prices.php` har ingen DKK-kolonne.
- df-data-klonen er urørt (`6c95bde`, tom `git status`); 28 tests grønne.

## USIKKERT

1. **Om `hour_utc`-kollapset kun rammer efterårets DST-tilbagestilling.**
   Kun 2025-10-26 er målt. 2023-10-29 og 2024-10-27 er ikke hentet, og
   forårsskiftet (hvor en time ikke findes) er ikke undersøgt.
2. **Hvorfor `hour_dk` også er forkert.** Begge rækker får
   `hour_dk=2025-10-26 02:00:00` uden offset-markør, så de to lokale
   02:00-timer kan ikke skelnes i den kolonne heller. Om det er samme
   `FROM_UNIXTIME`-fejl eller en separat, er ikke afgjort.
3. **Hvor NO_2/SE_3/SE_4-dataene i klonen kommer fra.** API'et har dem ikke
   på nogen af de tre testdatoer, men klonen har 2022–2025-09-30 og
   2026-03-31→. En anden kilde eller en siden purget backfill. Ikke
   undersøgt — ville kræve eksplorative kald.
4. **Hvornår DE_LU skiftede fra 60 til 15 min.** Kun tre datoer målt.
   Skiftet ligger mellem 2025-10-01 og 2025-12-15.
5. **Om DE_LU har data i HELE hullet.** Kun 2025-12-15 er testet. En enkelt
   dag beviser at hullet ikke er totalt, ikke at det er tomt hele vejen.
6. **Om `shortname=all` ignoreres eller fortolkes.** Parameteren er ikke i
   spec'en; svaret indeholdt alle felter, men om det skyldes parameteren
   eller `fields=all` som jeg selv sendte, er ikke isoleret.

---

# KONKLUSION F8

**Det er tre huller med to årsager. Prompten forudså muligheden, og den
indtraf.**

### 1.1 — DST-timen: **(a) konverteringsartefakt**

Kilden har observationen. `unixtime=1761436800`, `temp=9.025` for `fyn`,
`8.3` for `karup`, `10.2667` for `vestkyst`. Den blev tabt undervejs, fordi
API'ets `hour_utc` kollapser DST-tilbagestillingens to timer til én etiket, og
`merge_into_yearfile` dedupliker netop på den kolonne.

**Handling:** hentbar. Men et naivt genhent løser det ikke — serverfejlen
består, så kollisionen ville opstå igen. Enten skal dedup-nøglen være
`unixtime`, eller `hour_utc` skal udledes af `unixtime` klientside før
dedup, eller endpointet skal rettes.

### 1.2 og 1.3 — 2026-hullerne: **(b) kildemangel**

Kilden mangler de samme timer som klonen, i samme stationer, med samme
grænser. `karup` har alt, så det er stationsudfald hos `fyn` og `vestkyst`,
ikke et hentefejl.

**Handling:** ikke hentbar. Enten skift til `karup`, eller accepter
interpolation, eller vent på at DMI backfiller.

---

# KONKLUSION Q2

**Også to sager.**

### DE_LU: **(a) fetch-fejl — kilden har data**

96 rækker leveret for 2025-12-15, midt i et hul klonen har markeret som tomt
i 4368 timer.

**Betydning for F3:** DE-hullet kan lukkes ved genhentning med den korrekte
områdekode `DE_LU`. Bemærk at klonens filnavn er `DE_*.csv` mens API'ets kode
er `DE_LU` — det er en oplagt kandidat til hvorfor hentningen fejlede i første
omgang, men det er ikke bevist her.

### NO_2, SE_3, SE_4: **(b) kildemangel**

0 rækker på alle tre testdatoer, inklusive datoer hvor klonen har data. Rene
tomme 200'ere med gyldig områdekode.

**Betydning for F3:** kan ikke lukkes ved genhentning fra dette endpoint. F3
må enten finde en anden kilde, eller acceptere at de tre områder ikke er
dækket i perioden. Klonens eksisterende data for dem skal bevares — API'et
kan ikke reproducere dem.

---

# HVAD DETTE BETYDER FOR TOLERANCE-SPØRGSMÅLET

**Tolerance er ikke svaret på DST-timen. Rettelsen er.**

Vagten blokerer i dag alle helårskørsler på præcis den ene time
(`2025-10-26 00:00`, `2024-10-27 00:00`, `2023-10-29 00:00`). Målingen viser
at observationen findes i kilden med en konkret værdi. At indføre en tolerance
for at komme forbi den ville betyde at acceptere interpolation af data vi har.
Det er den forkerte handling, og det er præcis den slags stiltiende opblødning
F1 blev bygget for at forhindre.

**Den rigtige rækkefølge:**

1. Ret hentningen så DST-timen ikke tabes (dedup på `unixtime`, eller udled
   `hour_utc` klientside). Ét hul lukket i alle tre stationer og alle tre år.
2. Genhent DE_LU med korrekt områdekode. Q2's største hul lukket.
3. **Først derefter** står tolerance-spørgsmålet rent — og det gør det kun for
   2026-hullerne i `fyn`/`vestkyst` og for NO_2/SE_3/SE_4, hvor data
   beviseligt ikke findes.

For de resterende, ægte huller er spørgsmålet reelt og skal stilles ordentligt.
Målingerne peger på at det ikke er ét spørgsmål men to, delt efter
datatype:

- **Temperatur** er en fysisk kontinuert størrelse. Lineær interpolation over
  29 timer er en antagelse man kan forsvare og dokumentere — Gate 1 §Trin 0
  viste at det er præcis hvad der skete tavst før F1.
- **Balancepriser og -volumener** er markedsudfald. Et hul er ikke nul, og
  interpolation er ikke meningsfuld. Dér bør tolerancen være nul.

Det er en pr-datasæt-beslutning, ikke en global tærskel. Men den beslutning
bør træffes efter punkt 1 og 2, ikke i stedet for dem.
