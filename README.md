# Fjernvarme Businesscase — Driftsoptimering med spot- og balancemarkeder

> En åben MILP-driftsmodel udviklet til **Billund Varmeværk** i samarbejde med
> **Dansk Fjernvarme**. Frigivet under MIT-licens så andre værker kan bygge
> videre på den.

Modellen optimerer driften time-for-time over et helt år: hvilken enhed skal
producere hvornår, hvordan udnyttes akkumuleringstanken, og hvor meget kan der
tjenes på balancemarkederne (aFRR + mFRR) ved siden af spotsalg. Den er bygget
i Python med open source-værktøjer (Linopy + HiGHS) og kører på en almindelig
bærbar.

**Den fulde dokumentation — antagelser, metode, resultater, brugervejledning og
matematisk formulering — ligger i [`doc/rapport_billund_v3.docx`](doc/rapport_billund_v3.docx)
([PDF](doc/rapport_billund_v3.pdf)).** Læs den først hvis det er første gang
du møder modellen.

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

python run_case.py cases/billund_baseline.yaml --data-source github \
    --start 2025-04-01 --end 2026-03-31 --with-balancing
```

Første kørsel kloner automatisk
[`df-data`](https://github.com/skj-1964/df-data) (~50 MB) til
`data/df-data/`. Efterfølgende kørsler genbruger den lokale cache, så
typisk køretid er ~30 sekunder. Resultater lander i `output/`.

Hvis du i stedet vil hente friske data direkte fra Energinet og DMI (uden
om `df-data`-cachen) brug `--external` i stedet for `--data-source github`.
Det kræver hverken konto eller API-key, men er afhængigt af at API'erne er
oppe og fungerende på kørselstidspunktet.

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
BASE="cases/billund_baseline.yaml --data-source github --start 2025-04-01 --end 2026-03-31"

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
kørsel er `python run_case.py cases/billund_baseline.yaml` (dummy-data).
Kør `python run_case.py --help` for den autoritative liste.

### Positionsargument

| Argument | Beskrivelse |
| -------- | ----------- |
| `case` | Sti til case-YAML (fx `cases/billund_baseline.yaml`). Definerer enheder, lagre, priser, afgifter og balancemarked-opsætning. |

### Datakilde (vælg én — default `--dummy`)

| Flag | Beskrivelse |
| ---- | ----------- |
| `--dummy` | Fuldt syntetiske serier (temperatur, spot, last). Default. Bruges til hurtige struktur-tests uden netadgang. |
| `--external` | Rigtig DMI-temperatur + Energinet-spot + syntetisk varmelast (kalibreret fra `heat_load_params`). |
| `--data-path PATH` | Sti til værkets egne målerdata (endnu ikke aktiveret). |
| `--data-source {api,github}` | Hvorfra `--external` henter data. `api` = Energinet/DMI direkte (default). `github` = `df-data`-cachen (sandkasse-venligt; **impliserer `--external`**). |

Til external-kilden findes desuden:

| Flag | Default | Beskrivelse |
| ---- | ------- | ----------- |
| `--dmi-area` | `fyn` | DMI area-kode (Billund har ikke egen station; fyn er klimatisk tæt). |
| `--dmi-temp-shortname` | `temp_mean_past1h` | DMI-observationsvariabel for temperatur. |
| `--price-zone` | `DK1` | Energinet priszone for spot. |
| `--eur-dkk` | `7.45` | EUR→DKK-kurs til spot-konvertering. |
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

## Balancemarked — modellering af indmelding

Med `--with-balancing` udvides MILP'en med op-regulerings­reserver på
**aFRR** (automatisk) og **mFRR** (manuel) parallelt. Reserverne leveres af
de **el-forbrugende** enheder (varmepumpe, elkedler — og gasmotoren som CHP):
en enhed der forbruger el kan byde op-regulering ved at *kunne stoppe* sit
forbrug hvis kaldt. Ned-regulering er marginal på DK1 og udeladt i nuværende
scope.

### Bud-variable, kvalifikation og lofter

For hver kvalificeret enhed `i` og time `t` oprettes to bud-variable
`r_afrr[i,t]` og `r_mfrr[i,t]` (elektriske MW). De styres af:

- **Kvalifikation** per enhed og marked via YAML: `ancillary.afrr_qualified`
  og `ancillary.mfrr_qualified`.
- **Footroom** — produktionen skal kunne dække fuld aktivering af *summen*
  af begge bud: `heat_prod[i,t] ≥ COP(t)·(r_afrr[i,t] + r_mfrr[i,t])`. Det
  er den fysiske binding der kobler reserven til varmedriften og tanken.
- **Lofter** — i prioriteret rækkefølge:
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

### Eksempel — Spor B-kørsel (Q1 2026)

```bash
python run_case.py cases/billund_sporB_q1_2026.yaml \
    --data-source github --df-data-cache data/df-data --with-balancing \
    --start 2026-01-01 --end 2026-04-30 \
    --heat-csv data/billund_abvaerk_hourly.csv \
    --balancing-method activation_value --out-dir output/sporB_q1_2026
```

---

## Struktur

```
fjernvarme-businesscase/
├── cases/                  # YAML-konfiguration (antagelser per anlæg)
├── src/                    # model, dataloader, balancing, reporting
│   ├── model.py            # MILP-formulering
│   ├── data_loader.py      # Energinet- og DMI-API'er
│   ├── nettab.py           # to-led fysisk nettab-model (session 21)
│   ├── balancing.py        # aFRR + mFRR
│   ├── unit_commitment.py  # halmens min-uptime
│   └── reporting.py        # KPI'er og plots
├── scripts/                # hjælpescripts (rekalibrering m.m.)
├── data/                   # billund_abvaerk_hourly.csv (måledata)
├── doc/                    # rapport, figurer, workflow-guides
├── run_case.py             # CLI
└── requirements.txt
```

Når du kører modellen oprettes der automatisk:

- `data/raw/` — cache af spot-, balance- og DMI-data (~30 MB)
- `output/` — KPI'er, time-CSV'er, dispatch-plots

Begge mapper er gitignored og hentes/regenereres automatisk.

---

## Tilpas til dit eget anlæg

1. Kopiér `cases/billund_baseline.yaml` til `cases/<dit_værk>_baseline.yaml`
2. Erstat enheder, kapaciteter, virkningsgrader og priser med dine egne
3. Opdater `heat_load_params.nettab`-blokken med jeres typiske værksværdier
   (årligt nettab i % eller MWh, sommer- og vinter-temperaturforhold) — se
   afsnittet **Nettab-model** længere nede.
4. Erstat `data/billund_abvaerk_hourly.csv` med din egen ab-værk-måling
5. Rekalibrér varmebehovs-syntesen mod din måling — se næste afsnit
6. Kør `run_case.py` og tjek at dispatch-mønsteret ligner virkeligheden

Pilotrapportens §10 og bilag C beskriver fremgangsmåden i detaljer.

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
python run_case.py cases/billund_baseline.yaml --data-source github --year 2025

# Gammel slope-baseret model (samme YAML)
python run_case.py cases/billund_baseline.yaml --data-source github --year 2025 \
    --legacy-nettab
```

Output-filnavn får `__legnet`-markør, så A/B-kørsler ikke kolliderer. For
Billund 2025 er den typiske dispatch-effekt en reduktion på ~10% i halmkedel
og tilsvarende stigning i elkedel, fordi den nye model giver mere realistiske
vinterspidser.

---

## Friske data — automatisk månedlig opdatering

`df-data` opdateres månedligt af et cron-job hos Dansk Fjernvarme: spot-,
balance- og DMI-data for forrige måned hentes fra Energinet og DMI, fletteres
ind i års-CSV'erne og pushes til GitHub. Du får den seneste tilstand ved
enten at klone repo'et på ny eller køre `git pull` i `data/df-data/`.

Aktuel datadækning står i
[`df-data/DATA_VERSION.md`](https://github.com/skj-1964/df-data/blob/main/DATA_VERSION.md).
Spotpriserne hentes fra Energinets `DayAheadPrices`-endpoint, som siden
ISP15-fuld-overgangen i april 2026 har leveret 15-min-opløst spot for hele
det fælles-nordiske marked. Balance-data kommer fra
`AfrrReservesNordic`, `MfrrCapacityMarket`, `MfrrEnergyActivationMarket` og
`ImbalancePrice`.

Hvis du har dit eget API-flow og vil hente friske data direkte uden om
`df-data`-cachen, brug `--external` i stedet for `--data-source github` ved
modelkørsel.

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
