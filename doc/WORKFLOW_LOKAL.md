# Lokal udvikling — workflow

Denne guide er til værker eller konsulenter der vil køre modellen lokalt,
typisk på en bærbar med Python installeret. Hvis du ikke har Python eller
ikke er fortrolig med kommandolinjen, så start i stedet med
[`WORKFLOW_CLAUDE.md`](WORKFLOW_CLAUDE.md).

## Forudsætninger

- **Python 3.10 eller nyere** — tjek med `python --version`
- **git** — tjek med `git --version`
- **Visual Studio Code** anbefales (gratis, indbygget git-integration)
- ~5 GB ledig disk (Python-pakker + cachet markedsdata)

På Windows: installér Python fra [python.org](https://www.python.org/downloads/)
og marker *"Add Python to PATH"*. Installér git fra [git-scm.com](https://git-scm.com/).

## Første gang — fork eller klon

**Hvis I bare vil køre modellen** og lave lokale eksperimenter:

```bash
git clone https://github.com/<org>/fjernvarme-businesscase.git
cd fjernvarme-businesscase
```

**Hvis I vil bidrage tilbage eller har egne tilpasninger** I vil holde
synkroniseret med upstream: brug **fork** først (tryk *"Fork"* på GitHub),
klon jeres egen fork, og tilføj upstream som remote:

```bash
git clone https://github.com/<jeres-værk>/fjernvarme-businesscase.git
cd fjernvarme-businesscase
git remote add upstream https://github.com/<org>/fjernvarme-businesscase.git
```

## Opsætning af miljø

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Test at det virker:

```bash
python run_case.py cases/billund_baseline.yaml --dummy
```

Med `--dummy` bruges syntetiske data — ingen API-kald, kører på sekunder.
Når den fungerer, kan du skifte til `--external` for rigtige Energinet- og
DMI-data.

## Daglig brug

### Når I vil eksperimentere

Lav en branch så jeres ændringer ikke ryger ind i `main` ved et uheld:

```bash
git checkout -b eksperiment-halmpris-følsomhed
# ... ændr i YAML, kør modellen, tolkning ...
git add cases/
git commit -m "Test af halmpris 350-450 DKK/MWh"
```

Hvis eksperimentet ikke fører nogen vegne, er det bare en branch der ligger
til side. Hvis det er en god idé I vil beholde, merge tilbage til main:

```bash
git checkout main
git merge eksperiment-halmpris-følsomhed
```

### Når I vil dele en ændring tilbage

Push jeres branch til jeres egen fork og lav en *pull request* på GitHub:

```bash
git push origin eksperiment-halmpris-følsomhed
# Gå til GitHub og opret PR mod upstream/main
```

Vedhæft i PR-beskrivelsen:
- Hvad ændringen gør (én sætning)
- Hvilken case den blev testet på
- Eventuelt en før/efter-graf

### Når I vil hente nyeste version

```bash
git fetch upstream
git checkout main
git merge upstream/main
```

## Claude som kodepartner — lokalt

Også når I udvikler lokalt er Claude meget brugbar. Tre måder:

**1. Copy-paste i claude.ai** — den simple form. Vedhæft den fil du arbejder
på, beskriv hvad du vil ændre, kopier svaret tilbage. God til afgrænsede
ændringer.

**2. Claude Code i terminalen** — installeres med `npm install -g @anthropic-ai/claude-code`
og køres direkte i projektmappen. Claude læser, redigerer og kører kode
selv. Bedst til større ændringer der spænder flere filer.

**3. Claude for VS Code** — udvidelse til VS Code der giver Claude som
sidepanel. Godt til at forklare eksisterende kode mens du læser den.

For vores type projekt anbefales **Claude Code** når en ændring er
substantiel (fx tilføje et nyt marked) og **claude.ai-chat** når det er en
afgrænset YAML-justering eller en figur der skal laves.

## Versionering af jeres egne tilpasninger

Når I bygger en lokal variant til jeres eget værk, anbefales:

```bash
# Lav en case-fil med jeres navn
cp cases/billund_baseline.yaml cases/<jeres_værk>_baseline.yaml
git add cases/<jeres_værk>_baseline.yaml
git commit -m "Initial baseline for <jeres værk>"
```

Hold case-filen og evt. egne data under git, og tag jævnligt et "snapshot"
af kørsler I rapporterer videre fra:

```bash
git tag v2026-bestyrelsesmøde-april
git push --tags origin
```

Så kan I altid spole tilbage til præcis den version der lå til grund for et
bestemt notat eller møde.

## Typiske faldgruber

- **Forskellige Python-versioner mellem maskiner** — pin Python-version i
  README hvis I deler. Vi har testet på 3.10–3.13.
- **Glemt at aktivere virtual env** — symptomet er `ModuleNotFoundError:
  linopy`. Aktivér med `source .venv/bin/activate`.
- **API-rate limits** — Energinet/DMI har grænser på antal kald per minut.
  Cachen i `data/raw/` gør at I kun rammer dem første gang.
- **Store output-filer i git** — `output/` er gitignored med vilje. Hvis I
  vil dele specifikke kørsler, så zip dem og vedhæft dem til en GitHub
  Release i stedet.
