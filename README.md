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
git clone https://github.com/<din-org>/fjernvarme-businesscase.git
cd fjernvarme-businesscase
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run_case.py cases/billund_baseline.yaml --external \
    --start 2025-04-01 --end 2026-03-31 --with-balancing
```

Resultater lander i `output/` efter ~30 sekunder.
Se [`doc/WORKFLOW_LOKAL.md`](doc/WORKFLOW_LOKAL.md) for fuldt setup og
typiske udviklingsmønstre.

### Vej B — Claude i skyen (kræver ingen installation)

1. Hent koden som ZIP via *Code → Download ZIP* på GitHub-siden
2. Opret et nyt **Project** på [claude.ai](https://claude.ai)
3. Upload alle filer fra ZIP'en til projektets *knowledge*
4. Stil dit første spørgsmål — fx *"Kan du forklare hvad scenarie C i rapporten
   viser?"* eller *"Vis mig hvordan jeg kører modellen med en gaspris på 500"*

Claude kan både læse modellen, køre den (med Code Execution), forklare resultater,
og skrive opdaterede konfigurationer ud som filer du kan downloade.
Se [`doc/WORKFLOW_CLAUDE.md`](doc/WORKFLOW_CLAUDE.md) for hvordan workflow,
projektopsætning og status-dokumenter bruges i praksis.

---

## Hovedkørsler — 2×2 scenariematrix

```bash
# A — med tank, uden balancemarked
python run_case.py cases/billund_baseline.yaml --external \
    --start 2025-04-01 --end 2026-03-31

# B — uden tank, uden balancemarked
python run_case.py cases/billund_baseline.yaml --external \
    --start 2025-04-01 --end 2026-03-31 --disable tank_eksisterende

# C — med tank, med balancemarked (hovedscenariet)
python run_case.py cases/billund_baseline.yaml --external \
    --start 2025-04-01 --end 2026-03-31 --with-balancing

# D — uden tank, med balancemarked
python run_case.py cases/billund_baseline.yaml --external \
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
│   ├── balancing.py        # aFRR + mFRR
│   ├── unit_commitment.py  # halmens min-uptime
│   └── reporting.py        # KPI'er og plots
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
3. Erstat `data/billund_abvaerk_hourly.csv` med din egen ab-værk-måling
4. Re-kalibrér `heat_load_params_v2.yaml` mod din måling (Claude kan hjælpe)
5. Kør `run_case.py` og tjek at dispatch-mønsteret ligner virkeligheden

Pilotrapportens §10 og bilag C beskriver fremgangsmåden i detaljer.

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
