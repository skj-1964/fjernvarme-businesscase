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

## Hovedkørsler — 2×2 scenariematrix

```bash
# A — med tank, uden balancemarked
python run_case.py cases/billund_baseline.yaml --data-source github \
    --start 2025-04-01 --end 2026-03-31

# B — uden tank, uden balancemarked
python run_case.py cases/billund_baseline.yaml --data-source github \
    --start 2025-04-01 --end 2026-03-31 --disable tank_eksisterende

# C — med tank, med balancemarked (hovedscenariet)
python run_case.py cases/billund_baseline.yaml --data-source github \
    --start 2025-04-01 --end 2026-03-31 --with-balancing

# D — uden tank, med balancemarked
python run_case.py cases/billund_baseline.yaml --data-source github \
    --start 2025-04-01 --end 2026-03-31 --with-balancing \
    --disable tank_eksisterende
```

Ad-hoc-sensitiviteter via `--set`, `--enable`, `--disable` — se rapportens
bilag C for fulde eksempler.

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
