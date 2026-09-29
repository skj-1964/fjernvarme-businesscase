# Fjernvarme Businesscase — Driftsoptimering med spot- og balancemarkeder

> En åben MILP-driftsmodel udviklet til **Billund Varmeværk** i samarbejde med
> **Dansk Fjernvarme**. Frigivet under MIT-licens så andre værker kan bygge
> videre på den.

Modellen optimerer driften time-for-time over et helt år: hvilken enhed skal
producere hvornår, hvordan udnyttes akkumuleringstanken, og hvor meget kan der
tjenes på balancemarkederne (aFRR + mFRR) ved siden af spotsalg. Den er bygget
i Python med open source-værktøjer (Linopy + HiGHS) og kører på en almindelig
bærbar.

**Metode, antagelser og matematisk formulering ligger i
[`doc/rapport_billund_v3.docx`](doc/rapport_billund_v3.docx)
([PDF](doc/rapport_billund_v3.pdf)).** Læs den for baggrunden, hvis det er
første gang du møder modellen.

> **Rapport v3 (24. april 2026) er teknisk forældet — brug denne README til
> kommandoer og tal.** Casenavnet `billund_baseline.yaml` findes ikke længere,
> kommandoerne i bilag C bruger `--external` uden `--data-source`,
> filstrukturen hedder ikke længere `district_heating_bc/`, varmepumpen er nu
> en målt ydelsestabel, og hovedtallene (bl.a. "19 mio.") er overhalet af
> valideringen mod Billunds afregning. Se afsnittet **Referencetal**. En ny
> rapport (v4) er under udarbejdelse.

---

## To måder at bruge modellen på

Modellen er designet til at kunne anvendes både af **værker med IT-ressourcer
der vil køre lokalt**, og af **værker uden programmør der vil bruge Claude som
kodepartner**. De to veje er ligeværdige — pilotprojektet i Billund blev
faktisk udviklet i den anden form.

### Vej A — Lokal udvikling (kræver Python)

```bash
git clone https://github.com/skj-1964/fjernvarme-businesscase.git
cd fjernvarme-businesscase
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run_case.py cases/billund_sporA_rullende.yaml --data-source github \
    --with-balancing
```

Periode og DMI-station står i casen. En tidligere version af denne kommando
brugte `billund_sporA.yaml` med `--start 2025-04-01 --end 2026-03-31`; den
fejler nu på dækning, fordi fyn-stationen mangler timer 1. januar og
28. februar–1. marts 2026. Den rullende case bruger karup, som er hel.

Første kørsel kloner automatisk
[`df-data`](https://github.com/skj-1964/df-data) (~50 MB) til
`data/df-data/`. Efterfølgende kørsler genbruger den lokale cache, så
typisk køretid er ~30 sekunder. Resultater lander i `output/`.

`--external` alene betyder det samme som `--data-source github`. Vil du i
stedet hente data direkte fra Energinet og DMI (uden om `df-data`-cachen),
skriv `--external --data-source api`. Det kræver hverken konto eller API-key,
men er afhængigt af at API'erne er oppe, og **med `--with-balancing` giver
`api` nul aktiveringsindtægt** — brug `github`, når balancemarkedet skal med.

Se [`doc/WORKFLOW_LOKAL.md`](doc/WORKFLOW_LOKAL.md) for fuldt setup og
typiske udviklingsmønstre.

### Vej B — Claude i skyen (kræver ingen installation)

1. Bed Claude om at hente modellen fra https://github.com/skj-1964/fjernvarme-businesscase.git
2. Stil dit første spørgsmål — fx *"Kan du forklare hvad scenarie C i rapporten
   viser?"* eller *"Vis mig hvordan jeg kører modellen med en gaspris på 500"*

Claude kan både læse modellen, køre den (med Code Execution), forklare resultater,
og skrive opdaterede konfigurationer ud som filer du kan downloade.
Se [`doc/WORKFLOW_CLAUDE.md`](doc/WORKFLOW_CLAUDE.md) for hvordan workflow,
projektopsætning og status-dokumenter bruges i praksis.

Vil du regne på dit eget værk, så start i afsnittet
[**Dit eget værk — fra regneark til model**](#dit-eget-værk--fra-regneark-til-model).

---

## Sådan læses en kørsel — forskellen mellem to scenarier

Modellen giver sjældent et interessant svar i sig selv. Værdien ligger i
**forskellen mellem to kørsler** der er identiske på nær én knap: hvad koster
det at undvære tanken, hvad bidrager balancemarkedet, hvor følsom er
økonomien for gasprisen. Kør derfor altid en **baseline** og et **kontrafaktisk
scenarie** med samme case, periode og datakilde, og sammenlign deres KPI'er.

Mønsteret er en fælles basiskommando plus præcis det ene flag der adskiller de
to kørsler:

```bash
# Fælles base (gentages i begge kørsler)
BASE="cases/billund_sporA_rullende.yaml --data-source github"

# Baseline — uden balancemarked
python run_case.py $BASE

# Kontrafaktisk — kun balancemarkedet lagt til
python run_case.py $BASE --with-balancing
```

Forskellen i KPI'erne (`*_kpi.csv`) mellem de to kørsler *er* balancemarkedets
bidrag. De deterministiske filnavne sikrer at de to kørsler lander i hver sin
fil (`__bal-…`-markøren tilføjes kun til balance-kørslen), så de kan stilles
side om side.

Den samme isolér-én-knap-tilgang dækker de typiske spørgsmål — skift kun det
flag der svarer til knappen:

| Spørgsmål | Knap der ændres mellem de to kørsler |
| --------- | ------------------------------------ |
| Hvad bidrager balancemarkedet? | tilføj `--with-balancing` |
| Hvad er tankens værdi? | tilføj `--disable tank_eksisterende` |
| Legacy vs. kovarians-korrekt balanceindtægt? | `--balancing-method legacy` vs. `activation_value` |
| Følsomhed for gas-/CO₂-pris? | `--set prices.natural_gas.value=…` |
| Ny vs. gammel nettab-model? | tilføj `--legacy-nettab` |

Flere knaps kan kombineres i samme kørsel (fx både `--with-balancing` og
`--disable tank_eksisterende`), men så fortolkes forskellen som den
*samlede* effekt af begge — vil du isolere hvert bidrag, så ændr én ad gangen.
Se rapportens bilag C for fulde eksempler.

---

## `run_case.py` — parametre

`run_case.py` tager én positionsparameter (case-YAML'en) plus en række
valgfrie flag. Alle flag har fornuftige defaults, så den korteste gyldige
kørsel er `python run_case.py cases/billund_sporA.yaml --data-source github`.
Der er ingen standard-datakilde; uden en af dem stopper kørslen.
Kør `python run_case.py --help` for den autoritative liste.

### Positionsargument

| Argument | Beskrivelse |
| -------- | ----------- |
| `case` | Sti til case-YAML (fx `cases/billund_sporA.yaml`). Definerer enheder, lagre, priser, afgifter og balancemarked-opsætning. |

### Datakilde (vælg præcis én — ingen default)

| Flag | Beskrivelse |
| ---- | ----------- |
| `--dummy` | Fuldt syntetiske serier (temperatur, spot, last). Skal vælges eksplicit. Kun til hurtige struktur-tests uden netadgang — tallene ligner rigtige, men er det ikke. |
| `--external` | Rigtig DMI-temperatur + Energinet-spot + syntetisk varmelast (kalibreret fra `heat_load_params`). Uden `--data-source` hentes fra `df-data` (som `--data-source github`). |
| `--data-path PATH` | Sti til værkets egne målerdata (endnu ikke aktiveret). |
| `--data-source {api,github}` | Hvorfra `--external` henter data. `github` = `df-data`-cachen (default med `--external`; **impliserer `--external`** og tæller alene som valg af datakilde). `api` = Energinet/DMI direkte (med `--with-balancing` giver den nul aktiveringsindtægt). `--data-source api` uden `--external` er ikke et valg. |

Til external-kilden findes desuden:

| Flag | Uden flag | Beskrivelse |
| ---- | --------- | ----------- |
| `--dmi-area` | `data.dmi_area` i casen (påkrævet) | DMI area-kode. Flaget overskriver casen. |
| `--dmi-temp-shortname` | `data.dmi_temp_shortname` (`temp_mean_past1h`) | DMI-observationsvariabel for temperatur. |
| `--price-zone` | `data.price_zone` i casen (påkrævet) | Energinet priszone for spot. |
| `--eur-dkk` | `data.eur_dkk` (`7.45`) | EUR→DKK-kurs til spot-konvertering. |

Loaderne (`load_external_data`, `load_external_data_github`) læser samme
data-blok, når de kaldes direkte fra et script uden disse argumenter.
| `--cache-dir` | `data/raw` | Mappe til cachede API-svar (Parquet). |
| `--force-refresh` | — | Ignorér cache, hent fra API påny. |
| `--df-data-url` | repo-default | Git-URL til `df-data`-repo'et (kun `--data-source github`). |
| `--df-data-cache` | repo-default | Lokal sti til `df-data`-klonen (kun `--data-source github`). |

### Analyseperiode (overrider `cfg.time`)

| Flag | Beskrivelse |
| ---- | ----------- |
| `--year YYYY` | Hele kalenderåret. Kan ikke kombineres med `--start`/`--end`. |
| `--start YYYY-MM-DD` | Startdato (kræver `--end`). |
| `--end YYYY-MM-DD` | Slutdato (kræver `--start`). |

### Varmelast-syntese (kun relevant med `--external`)

| Flag | Default | Beskrivelse |
| ---- | ------- | ----------- |
| `--heat-params PATH` | — | Alternativ `heat_load_params`-YAML der overrider case-filens sektion (fx en kalibrering fra `scripts/calibrate_heat_load.py`). |
| `--heat-csv PATH` | — | Suspendér syntesen og brug målt varmebehov fra CSV. Bruges i valideringskørsler (fx mod EnergyPRO), så syntese-forskelle elimineres som afvigelseskilde. |
| `--heat-csv-column COL` | `heat_mw_abvaerk` | Kolonnenavn i `--heat-csv` med varme i MW. |
| `--heat-csv-tz TZ` | `UTC` | Tidszone for CSV-tidsstempler (brug fx `Europe/Copenhagen` ved lokal tid med sommertid). |

### Nettab-model

| Flag | Beskrivelse |
| ---- | ----------- |
| `--legacy-nettab` | Tving den gamle slope-baserede nettab-model selvom YAML'en har en `nettab:`-blok. Bruges til A/B-sammenligning mod den nye to-led fysiske model (se afsnittet **Nettab-model**). |

### Balancemarked

| Flag | Beskrivelse |
| ---- | ----------- |
| `--with-balancing` | Hent aFRR/mFRR-priser og aktivér reservemodellen. Kræver at perioden ligger i et post-PICASSO-regime (ca. april 2025 og frem). Uden dette flag køres rent spot/varme. |
| `--balancing-method {legacy,activation_value}` | Overruler `balancing.method` i casen. `legacy` = `E[α]×E[p]` (gammel). `activation_value` = kovarians-korrekt `av(t)` (ny — kræver `balancing.bid_strategy` i casen). Se afsnittet nedenfor. |

### Enheds- og parameter-overrides

| Flag | Beskrivelse |
| ---- | ----------- |
| `--enable NAVN` | Aktivér en enhed eller et lager. Kan gentages. |
| `--disable NAVN` | Deaktivér en enhed eller et lager. Kan gentages. |
| `--set PATH=VALUE` | Override en vilkårlig leaf-værdi i YAML'en før dataclass-construction. Værdien parses som YAML (auto type-coercion). Kan gentages. Eksempler: `--set prices.co2_eua.value=800`, `--set storage.tank_eksisterende.volume_m3=4000`, `--set units.vp_luft_vand.ancillary.afrr_max_bid_mw=3.0`. |

### Solver og output

| Flag | Default | Beskrivelse |
| ---- | ------- | ----------- |
| `--solver` | `highs` | MILP-solver. |
| `--days` | `7` | Antal dage i dispatch-plottet. |
| `--out-dir` | `output` | Output-mappe. |

Alle output-filer får et deterministisk præfiks der afspejler kørslen —
`{case}__{data}__{periode}[__bal-{metode}][__legnet][__heatcsv][__overrides]`.
Overrides er alfabetisk sorterede, så samme scenarie altid giver samme filnavn
uanset rækkefølge på kommandolinjen. En kørsel skriver `_kpi.csv`,
`_monthly.csv`, `_hourly.csv`, `_dispatch.nc`, `_dispatch.png` samt et manifest.

---

## Varmepumpens ydelse — `cop_curve`

En luft/vand-varmepumpe leverer mindre varme, når det er koldt. Modellen kan
beskrive det på to måder, vælges pr. enhed i casen:

**`type: table` — målt ydelse (anbefalet).** Punkter med udetemperatur, varme
og eloptag ved fuld last. Varme og el interpoleres hver for sig, COP er
`varme(T) / el(T)`, og uden for punkterne holdes yderværdien.

```yaml
cop_curve:
  type: table
  points:
    - { t_ambient: -10.0, heat_mw: 12.0, el_mw: 5.0 }   # COP 2,40
    - { t_ambient:   0.0, heat_mw: 16.0, el_mw: 5.5 }   # COP 2,91
    - { t_ambient:  16.0, heat_mw: 21.0, el_mw: 6.2 }   # COP 3,39
```

- Varmeloftet følger udetemperaturen time for time. `p_max_heat` gælder
  ovenpå som ekstra loft; sæt det til tabellens største varme, medmindre
  noget andet end varmepumpen selv begrænser ydelsen.
- Reservationsloftet i balancemarkedet er tabellens største eloptag.
- Mindst to punkter; gerne tre (omkring −10 °C, 0 °C og +15 °C).

**`type: linear` — COP ved 0 °C.** Bruges kun, når der ikke findes målepunkter.
COP stiger lineært med udetemperaturen (mellem 1,8 og 4,0), og varmeloftet er
fast hele året. Det giver størst eloptag i frost, det omvendte af en
luft/vand-varmepumpe, så tallene er mindre præcise. Den lineære kurve er
uændret og kan stadig bruges til sammenligning.

Billund-casene bruger Johns målte ydelse. Det flytter tallene: se **Referencetal**.

---

## Balancemarked — modellering af indmelding

Med `--with-balancing` udvides MILP'en med op-regulerings­reserver på
**aFRR** (automatisk) og **mFRR** (manuel) parallelt. Reserverne leveres af
de **el-forbrugende** enheder (varmepumpe og elkedler): en enhed der
forbruger el kan byde op-regulering ved at *kunne stoppe* sit forbrug hvis
kaldt. En gasmotor byder ikke — kun enheder med `fuel: electricity` er med
(`_eligible_units_for_market`), også selvom `afrr_qualified` er sat. Ned-
regulering er marginal på DK1 og udeladt i nuværende scope.

### Bud-variable, kvalifikation og lofter

For hver kvalificeret enhed `i` og time `t` oprettes to bud-variable
`r_afrr[i,t]` og `r_mfrr[i,t]` (elektriske MW). De styres af:

- **Kvalifikation** per enhed og marked via YAML: `ancillary.afrr_qualified`
  og `ancillary.mfrr_qualified`.
- **Footroom** — produktionen skal kunne dække fuld aktivering af *summen*
  af begge bud: `heat_prod[i,t] ≥ COP(t)·(r_afrr[i,t] + r_mfrr[i,t])`. Det
  er den fysiske binding der kobler reserven til varmedriften og tanken.
- **Lofter** — reservationen kan aldrig overstige enhedens største eloptag.
  For en varmepumpe med målt ydelsestabel (`cop_curve` af typen `table`, se
  **Varmepumpens ydelse**) er det tabellens største eloptag; ellers
  `p_max_heat` divideret med den laveste COP. Ovenpå det gælder, i
  prioriteret rækkefølge:
  - `balancing.ancillary_caps` (anbefalet): `per_unit_mw` per enhed (samlet
    aFRR+mFRR, **altid** håndhævet — fx VP ≤ 6 MW) og `total_mw`, ét samlet
    loft over *alle* bud og begge markeder per time (Billunds
    prækvalificering, fx 14 MW frit fordelt). Når sat tilsidesætter den de
    ældre per-enheds- og gruppe-lofter.
  - `balancing.shared_reserve_cap_mw` — ældre form af det samlede loft.
  - `ancillary.afrr_max_bid_mw` / `mfrr_max_bid_mw` per enhed og
    `ancillary_groups` (gruppe-loft) — pris-taker-beskyttelse når intet
    samlet loft er sat.

### Indtægt — to metoder (`balancing.method`)

Begge metoder fratrækker reserveindtægten fra omkostnings­objektivet og består
af en **kapacitetsdel** (`π_cap(t)·r`) og en **aktiveringsdel**:

- **`legacy` — `E[α]×E[p]`.** Aktiveringsindtægt = en time-midlet
  aktiveringsfraktion `α(t)` gange en time-midlet pris. Forventet
  varmereduktion = `α·COP·r`. Enkel, men undervurderer systematisk når
  aktivering og pris hænger sammen *inden i* timen (scarcity).

- **`activation_value` — kovarians-korrekt `av(t)`** (anbefalet, kræver en
  `bid_strategy`). I stedet for at gange to gennemsnit beregnes en
  aktiveringsværdi-koefficient direkte fra sub-time-priserne:

  ```
  av(t) = Σ_{τ ∈ t}  Δτ · 1[ p_act(τ) ≥ spot(τ) + markup ] · ( p_act(τ) + spot(τ) + el_cost_flat )
  ```

  Indikator og pris evalueres i samme sub-interval, så kovariansen fanges
  eksakt. `clear_fraction(t) ∈ [0,1]` (andelen af timen buddet clearer)
  bruges som varmeside-α. Aktiveringsindtægten forbliver lineær:
  `Σ_t av(t)·r(t)`. Parentesen `(p_act + spot + el_cost_flat)` er den fulde
  værdi pr. MWh op-reguleret el — aktiveringsprisen **plus** den sparede
  forbrugsomkostning (spot + tarif + elafgift), fordi op-regulering af en
  el-forbrugende enhed *også* sparer indkøbssiden.

### Budstrategi (`balancing.bid_strategy`)

Værkets indmelding på aktiveringsmarkedet modelleres som et bud relativt til
spot. `up_markup_dkk_mwh` er tillægget (bud op = spot + markup);
`up_markup_max_dkk_mwh` er en øvre båndgrænse (tank-styret positionering,
dokumentation). `av(t)` beregnes i datalaget ud fra netop dette bud.

```yaml
balancing:
  method: activation_value
  bid_strategy:
    up_markup_dkk_mwh: 500
    up_markup_max_dkk_mwh: 2000
```

### Aktiveret andel (`balancing.activation`)

`clear`-indikatoren i `av(t)` siger, at buddet ligger i merit — ikke at det
bliver aktiveret. Uden en gate gav den 4–5 gange for meget aktiveret energi
målt mod Billunds afregning. Blokken styrer, hvor stor en andel `f(τ)` af den
reserverede MW der regnes aktiveret i et kvarter:

```yaml
balancing:
  activation:
    afrr: {model: system_share, k: 1.0}
    mfrr: {model: system_share, k: 1.0}
```

| model | f(τ) |
|---|---|
| `clear` (default) | `1[p ≥ bud]` — den oprindelige antagelse |
| `system_share` | `1[p ≥ bud] · min(1, k·α(τ))`, α = systemets aktiverede volumen / indkøbt kapacitet |
| `ramp` | `min(1, max(0, (p − bud) / ramp_dkk_mwh))` |

Uden blokken regnes aktiveringen som før (`clear`). Spor A-ankeret er
4.697.269 kr med målt varmepumpe (se **Referencetal**). `f(τ)` indgår både i
aktiveringsindtægten og i den forventede varmereduktion. Mod Billund rammer
`system_share` med k=1 aFRR i H2 2025 (7,8 % af reserveret energi mod 8,2 %)
og mFRR i marts–juni 2026 (14,5 % mod 14,2 %); aFRR i marts–juni 2026 kræver
k≈1,6. Kræver `method: activation_value` og `--data-source github`.

### CM-pris-gate på reservationen (Spor B / Spor A)

Den empiriske observation (Q1 2026) er at Billund **ikke** reserverer
kontinuerligt op til loftet, men selektivt: reservations­frekvensen stiger
monotont med markedets day-ahead kapacitetspris (CM). Det modelleres som en
**gate** per marked — reservationen åbnes kun i intervaller hvor CM ≥ tærskel:

```yaml
balancing:
  reservation_gate:
    enabled: true
    mode: driven                 # driven (Spor B) | bound (Spor A)
    afrr: { cm_threshold_dkk_mw_h: 100, block_mw: 3.0 }
    mfrr: { cm_threshold_dkk_mw_h: 421, block_mw: 5.1 }
```

- **`mode: driven` (Spor B — deskriptiv):** reservationen *drives* af gaten,
  `Σ_i r_m[i,t] == gate_m(t)·B_m`. Equality fjerner perfekt-foresight-MILP'ens
  frihed til kun at cherry-picke aktiverings-hale-timerne — reservationen
  følger CM-prisen, præcis som Billund gjorde. Bruges til at reproducere
  værkets faktiske adfærd og lukke foresight-gabet i capture-analysen.
- **`mode: bound` (Spor A — normativ):** gaten er et loft,
  `Σ_i r_m[i,t] ≤ gate_m(t)·B_m`, og MILP'en optimerer frit inden for vinduet.
  Byg-klar, men ikke i brug i nuværende kørsler.

Tærskel og blok er afledte kalibrerings­parametre (Q1-2026-snit), valgt så
`gate-frekvens × blok = realiseret MW-snit`. Når gaten er aktiv binder den
typisk før det samlede `total_mw`-loft, så cap-niveauet bliver ~irrelevant —
en bekræftelse i sig selv. Diagnostikken efter solve splitter
aktiveringsindtægten i **netto** (ren aktiveringsbetaling) og
**forbrugsmodregning** (sparet spot + tarif + afgift); objektivet bruger
brutto, manifestet rapporterer netto.

### Tilgængelighedsloft og foresight (`balancing.availability`, `activation.foresight`)

Uden gate reserverer modellen al den effekt, footroom tillader — for Billund
3–8 gange det realiserede. To felter beskriver værkets faktiske adfærd:

```yaml
balancing:
  activation:
    foresight: profile        # realized (default) | profile
  availability:
    enabled: true
    mode: energy              # hourly | energy
    afrr:
      mw_by_month: {"2026-03": 1.155, "2026-04": 1.186}
```

`foresight: profile` lader optimeringen se aktiveringsværdiens gennemsnit pr.
måned og time på døgnet i stedet for den realiserede — kapacitetsbuddet
afgives dagen før. Manifestets aktiveringstal er da forventede.
`availability` er et loft på den samlede reservation pr. marked: `hourly` i
hver time, `energy` på månedens MWh. Måneder i vinduet uden loft stopper
kørslen. Loftet beskriver én periode for ét værk og er ikke overførbart.

### Eksempel — Spor B-kørsel (marts–juni 2026)

```bash
python run_case.py cases/billund_sporB.yaml \
    --data-source github --with-balancing \
    --heat-csv data/billund_abvaerk_hourly_splejset_jun2026.csv \
    --out-dir output/sporB
```

Brug den splejsede fil. `data/billund_abvaerk_hourly.csv` har 161 manglende
timer i vinduet, og kørslen stopper på dækningen.

Vinduet og kalibreringen står i casen. Et andet vindue kræver nye
månedslofter — se kommentaren i `billund_sporB.yaml`.

Sammenligning mod Billunds afregning (facit, marts–juni 2026) regnes med
`capture_rate.py`. Facit ligger ikke i repoet (det er Billunds afregning),
men skal gives som fil:

```bash
python scripts/capture_rate.py <dispatch.nc> --case cases/billund_sporB.yaml \
    --facit <facit mar–jun> --start 2026-03-02 --end 2026-06-30 --ex-post
```

`--ex-post` sætter modellens tal op mod det realiserede med kendt
reservation. Resultatet er **121 %** (aFRR 108 %, mFRR 132 %). Læs det med
disse forbehold: kalibreringen gælder kun marts–juni 2026 og kun med
Billunds reservation pr. måned som loft (uden loftet reserverer modellen 3–8
gange for meget); mFRR er overvurderet med ca. 30 %, fordi modellen kender
kapacitetsprisen på forhånd; motorernes balanceindtægt og nedregulering er
ikke med; og Spor A er en øvre grænse. Tidligere dokumenter nævner 117 %; det
er regnet med den gamle lineære varmepumpe.

---

## Struktur

```
fjernvarme-businesscase/
├── cases/                  # YAML-konfiguration (antagelser per anlæg)
├── src/                    # model, dataloader, balancing, reporting
│   ├── model.py            # MILP-formulering
│   ├── data_loader.py      # Energinet- og DMI-API'er (--data-source api)
│   ├── data_loader_github.py  # df-data-cachen (--data-source github)
│   ├── nettab.py           # to-led fysisk nettab-model
│   ├── balancing.py        # aFRR + mFRR
│   ├── activation_value.py # aktiveringsværdi og aktiveret andel
│   ├── tariff.py           # tidsvarierende nettarif, sæsonsatser
│   ├── unit_commitment.py  # halmens min-uptime
│   └── reporting.py        # KPI'er og plots
├── scripts/                # vaerksark_til_yaml.py (regneark → case),
│                           # byg_skabelon.py (bygger skabelonen),
│                           # capture_rate.py (mod Billunds facit),
│                           # calibrate_heat_load.py m.fl.
├── tests/                  # pytest
├── data/                   # billund_abvaerk_hourly*.csv (måledata)
│   └── df-data/            # klon af df-data (hentes automatisk, gitignored)
├── deltagere/              # egne værkers ark, cases og data (gitignored)
├── doc/                    # rapport, figurer, workflow-guides,
│                           # vaerksdata_skabelon.xlsx
├── run_case.py             # CLI
└── requirements.txt
```

Når du kører modellen oprettes der automatisk:

- `data/df-data/` — klon af `df-data` (~50 MB), med `--data-source github`
- `data/raw/` — cache af API-svar; bruges kun med `--data-source api`
- `output/` — KPI'er, time-CSV'er, dispatch-plots
- `deltagere/` — oprettes af `vaerksark_til_yaml.py` til egne værkers filer

Alle mapper er gitignored og hentes/regenereres automatisk.

---

## Referencetal

Alle tal er kørt med målt varmepumpe (commit `5428147`, `df-data` 21. september
2026). De erstatter tallene i rapport v3 og i ældre statusnoter.

| case | før (lineær VP) | nu | kommando |
| ---- | ---: | ---: | -------- |
| Spor A-anker | 5.186.698 | **4.697.269** | `python run_case.py cases/billund_sporA.yaml --data-source github --with-balancing` |
| Spor B | 4.485.617 | **3.964.586** | `python run_case.py cases/billund_sporB.yaml --data-source github --with-balancing --heat-csv data/billund_abvaerk_hourly_splejset_jun2026.csv` |
| Spor B mod facit, ex post | 117 % (aFRR 102, mFRR 130) | **121 %** (aFRR 108, mFRR 132) | `scripts/capture_rate.py … --ex-post` (se Spor B ovenfor) |
| Billund rullende år (jul 2025–jun 2026) | 22,85 mio | **20.343.221** ¹ | `python run_case.py cases/billund_sporA_rullende.yaml --data-source github --with-balancing --heat-csv data/billund_abvaerk_hourly_splejset_jun2026.csv` |
| Andeby helår | 23.960.612 | **22.761.390** ¹ | `python run_case.py cases/andeby.yaml --data-source github --with-balancing` |

Beløb i kr. Spor A tager ca. 1 minut. Andeby bruger ca. 3,5 GB hukommelse og 7–15 minutter, så kør den ikke
live.

¹ Kørt på varianter af casene, som siden er foldet ind i de rigtige filer.
Modelmæssigt er de identiske (forskellen er kommentarer og `alpha`, som ikke
bruges med COP-tabel), men de to tal er endnu ikke genkørt fra de endelige
filer.

Med målt varmepumpe leverer Spor A 20,5 GWh varme (før 17,3) for 6,4 GWh el
(før 5,7). Største eloptag er 6,2 MW (før 6,98; 8,9 MW i det rullende helår).

---

## Dit eget værk — fra regneark til model

Den letteste vej er Excel-skabelonen
[`doc/vaerksdata_skabelon.xlsx`](doc/vaerksdata_skabelon.xlsx). Du udfylder
fire ark, og et script bygger casefilen og varmelasten ud fra dem. Du skal
ikke skrive YAML.

1. **Udfyld arkene.**
   - *Timedata*: timeværdier for samlet varmeproduktion ab værk (MW) for
     1. juli 2025 – 30. juni 2026, og årsproduktionen i GWh. **Tidszonen er et
     felt, der skal stå som `UTC` eller `dansk lokaltid`** — den gættes ikke,
     for en forkert tidszone flytter hele året en eller to timer i forhold til
     elprisen uden at noget ser forkert ud. Manglende timer står som tomme
     celler, aldrig som nul (nul er en gyldig måling).
   - *Anlaeg*: produktionsenheder og akkumuleringstanke. Alle syv enhedstyper
     kan bruges: `heat_pump`, `electric_boiler`, `biomass_boiler`, `gas_boiler`,
     `gas_engine_chp`, `solar_thermal` og `waste_heat`.
     De grå rækker er eksempler: slet dem, du ikke har, eller skriv hen over.
     Overskrifterne (`navn` over enhederne, `tank` over tankene) må blive stående;
     konverteringen finder blokkene på dem og ikke på et fast rækkenummer.
   - *Varmepumpe*: målepunkter (udetemperatur, varme, el) for hver varmepumpe,
     som beskrevet under **Varmepumpens ydelse**. Uden punkter bruger
     konverteringen COP ved 0 °C fra *Anlaeg* og den lineære kurve, og siger det.
   - *Priser*: brændsels- og elpriser, elafgift, nettarif pr. bånd og sæson
     (vinter oktober–marts, sommer april–september; tidspunkterne er faste),
     DMI-område og priszone.
2. **Konvertér.** Læg arket i `deltagere/` og kør:

   ```bash
   python scripts/vaerksark_til_yaml.py deltagere/mit_vaerk.xlsx
   ```

   Scriptet stopper højlydt på alt, det ikke kan tolke, og skriver
   `deltagere/cases/<navn>.yaml` og `deltagere/data/<navn>_abvaerk_hourly.csv`.
   Huller i timedata meldes; op til 5 % af vinduet udfyldes ved lineær
   interpolation, over det stopper modellen.
3. **Kør.** Konverteringen skriver selv kommandoen:

   ```bash
   python run_case.py deltagere/cases/<navn>.yaml --data-source github \
       --heat-csv deltagere/data/<navn>_abvaerk_hourly.csv
   ```

   Balancemarkedet er slået fra i den genererede case. Læs blokken øverst i
   filen, før du slår det til (`--with-balancing`) og udfylder lofterne; det
   skal kun gøres, hvis værket er prækvalificeret hos Energinet.

**Værkets data må ikke komme i det offentlige repo.** `deltagere/` er
git-ignoreret, og konverteringen nægter at skrive eller læse et ark et sted i
repoet, som git kan committe. Læg altså arket i `deltagere/` (eller uden for
repoet). `--tillad-offentlig` slår vagten fra og er kun til egne
referencecases som Andeby, aldrig til en andens data. `--overskriv` kræves for
at erstatte en eksisterende fil.

### Avanceret: skriv casen i hånden

Vil du ikke bruge regnearket, kan du tilpasse en case-YAML direkte:

1. Kopiér `cases/billund_sporA_rullende.yaml` til
   `deltagere/cases/<dit_værk>.yaml`
2. Erstat enheder, kapaciteter, virkningsgrader og priser med dine egne
3. Opdater `heat_load_params.nettab`-blokken med jeres typiske værksværdier
   (årligt nettab i % eller MWh, sommer- og vinter-temperaturforhold) — se
   afsnittet **Nettab-model** længere nede.
4. Læg din ab-værk-måling i `deltagere/data/` og brug `--heat-csv`
5. Rekalibrér varmebehovs-syntesen mod din måling — se næste afsnit
6. Kør `run_case.py` og tjek at dispatch-mønsteret ligner virkeligheden

Pilotrapportens §10 og bilag C beskriver fremgangsmåden i detaljer, men
kommandoerne dér er forældede; brug dem i denne README.

---

## Rekalibrér varmebehovs-syntesen

`scripts/calibrate_heat_load.py` genfitter `HeatLoadParams` ved OLS mod
målt varmeproduktion og en valgt DMI-vejrstation. Output er en YAML-fil i
samme format som `cases/heat_load_params_*.yaml` der kan bruges direkte
med `run_case.py --heat-params`.

**Standardkørsel** (fyn-temperatur, termisk inerti 48h — anbefalet default):

```bash
python scripts/calibrate_heat_load.py \
    --dmi-area fyn \
    --thermal-inertia 48 \
    --output cases/heat_load_params_v3_fyn_ti48.yaml
```

**Med dit eget værks data**:

```bash
python scripts/calibrate_heat_load.py \
    --measured data/<dit_værk>_hourly.csv \
    --measured-col heat_mw_total \
    --dmi-area fyn \
    --output cases/heat_load_params_<dit_værk>.yaml
```

**Grid-search over termisk inerti** hvis du er usikker på den rette EMA-bredde:

```bash
python scripts/calibrate_heat_load.py \
    --dmi-area karup \
    --thermal-inertia-grid 24,36,48,72,96 \
    --output cases/heat_load_params_<dit_værk>_optimal.yaml
```

Scriptet vælger automatisk den TI der maksimerer R².

**Brug resultatet** i en model-kørsel:

```bash
python run_case.py cases/<dit_værk>_baseline.yaml --data-source github \
    --heat-params cases/heat_load_params_<dit_værk>.yaml \
    --start 2025-04-01 --end 2026-03-31
```

YAML-output indeholder fit-statistik (`_fit_r2`, `_fit_rmse`,
`_n_observations`) samt kilde og dato, så det er sporbart hvilken
kalibrering en given kørsel bygger på. Kør `python scripts/calibrate_heat_load.py --help`
for fulde CLI-flag.

---

## Nettab-model

Modellen understøtter to nettab-formuleringer. Default er en
**fysisk to-led model**, som aktiveres når YAML'en indeholder en
`nettab:`-sektion under `heat_load_params`:

```yaml
heat_load_params:
  # ... øvrige parametre ...
  nettab:
    aarligt_nettab_pct: 0.146      # eller: aarligt_nettab_mwh: 17875
    sommer:
      t_frem: 64                    # °C, kundeside (juli-august)
      t_retur: 41
      t_ude: 16                     # valgfri, default 16
    vinter:
      t_frem: 71                    # °C, kundeside (januar-februar)
      t_retur: 41
      t_ude: 1                      # valgfri, default 1
    konduktiv_andel: 0.75           # valgfri, default 0,75 (Billund-fit 0,77)
    t_jord_avg: 9.0                 # valgfri, default 9,0
    t_jord_amp: 4.0                 # valgfri, default 4,0
```

Modellen udleder de fysiske koefficienter `a` (konduktivt led, isolations- og
jordtab) og `c` (flow-led, konvektive tab i armaturer og substationer) ud fra
disse typiske værksværdier. Formel: `nettab_MW(t) = a · (T_pipe(t) − T_jord(t))

+ c · load_MW(t)`. Se `src/nettab.py` for detaljer.

### Dynamisk T_jord (valgfri, opt-in)

Default beregner modellen T_jord som en statisk sæson-cosinus baseret på
kalender-måneden. Det betyder at samme måned giver samme T_jord uanset år.
For at få jordtemperaturen til at følge faktiske udetemperaturer (kolde
januar-dage giver lavere T_jord end milde) kan du aktivere dynamisk mode:

```yaml
    t_jord_dynamic: true
    t_jord_ema_days: 30             # tidskonstant, default 30 dage
    t_jord_damping: 0.5             # default 0,5
    t_jord_t_out_ref: 8.0           # klimanormal T_out, default 8,0 °C
```

T_jord beregnes da som `t_jord_avg + damping · (EMA(T_out, τ) − t_out_ref)`.
Parametrene matcher fysisk diffusion ved ~1 m dybde i dansk jord. Årssummen
af nettab er identisk i begge modes — kun fordelingen inden for året ændres.

### A/B-sammenligning mod den gamle slope-baserede model

Den gamle model (`β_net × max(0, T_net − T_out)`, et lineært led) kan stadig
køres for sammenligning ved at tilføje `--legacy-nettab` til kommandolinjen:

```bash
# Ny fysisk model (default)
python run_case.py cases/billund_sporA.yaml --data-source github --year 2025

# Gammel slope-baseret model (samme YAML)
python run_case.py cases/billund_sporA.yaml --data-source github --year 2025 \
    --legacy-nettab
```

Output-filnavn får `__legnet`-markør, så A/B-kørsler ikke kolliderer. For
Billund 2025 er den typiske dispatch-effekt en reduktion på ~10% i halmkedel
og tilsvarende stigning i elkedel, fordi den nye model giver mere realistiske
vinterspidser.

---

## Friske data — automatisk ugentlig opdatering

`df-data` opdateres ugentligt (mandag) af et cron-job hos Dansk Fjernvarme:
spot-, balance- og DMI-data hentes, fletteres ind i års-CSV'erne og pushes til
GitHub. Du får den seneste tilstand ved
enten at klone repo'et på ny eller køre `git pull` i `data/df-data/`.

Aktuel datadækning står i
[`df-data/DATA_VERSION.md`](https://github.com/skj-1964/df-data/blob/main/DATA_VERSION.md).
Spotpriserne hentes fra Energinets `DayAheadPrices`-endpoint, som siden
ISP15-fuld-overgangen i april 2026 har leveret 15-min-opløst spot for hele
det fælles-nordiske marked. Balance-data kommer fra
`AfrrReservesNordic`, `MfrrCapacityMarket`, `MfrrEnergyActivationMarket` og
`ImbalancePrice`.

Hvis du har dit eget API-flow og vil hente friske data direkte uden om
`df-data`-cachen, brug `--external --data-source api` ved modelkørsel
(husk, at det giver nul aktiveringsindtægt med `--with-balancing`).

---

## Bidrag tilbage

Forbedringer er meget velkomne — særligt nye markedsmoduler (FCR-D,
intraday), bedre kalibreringsrutiner, eller andre værkstopologier som
referencecases. Se [`CONTRIBUTING.md`](CONTRIBUTING.md) for hvordan.

---

## Licens

MIT — se [`LICENSE`](LICENSE). Frit at bruge, ændre og videredistribuere,
også kommercielt. Modellen er udviklet til Billund Varmeværk i samarbejde
med Dansk Fjernvarme og deles for at andre værker kan bygge videre på den.
