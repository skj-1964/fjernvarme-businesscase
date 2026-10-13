# Lokal udvikling — workflow

Denne guide er til værker eller konsulenter der vil køre modellen lokalt,
typisk på en bærbar med Python installeret. Hvis du ikke har Python eller
ikke er fortrolig med kommandolinjen, så start i stedet med
[`WORKFLOW_CLAUDE.md`](WORKFLOW_CLAUDE.md).

## Forudsætninger

- **Python 3.10–3.13** (testet) — tjek med `python --version`
- **git** — tjek med `git --version`
- **Visual Studio Code** anbefales (gratis, indbygget git-integration)
- ~5 GB ledig disk (Python-pakker + cachet markedsdata)
- 8 GB RAM, hvis I vil regne helår: Andeby med balancering bruger ca. 3,5 GB

### Windows: brug WSL

Modellen er udviklet og testet på Linux. På Windows anbefales WSL 2 med
Ubuntu (`wsl --install` i en PowerShell som administrator; kræver typisk en
genstart, og værkets IT kan have blokeret det). Installér derefter Python og
git inde i Ubuntu (`sudo apt install python3 python3-venv git`).

Læg klonen i Linux-hjemmemappen (`~/`), ikke under `/mnt/c`. Det er
hurtigere, og git ser ikke falske ændringer af filrettigheder (se
**Typiske faldgruber**).

Vil I køre direkte i Windows uden WSL, så installér Python fra
[python.org](https://www.python.org/downloads/) med *"Add Python to PATH"* og
git fra [git-scm.com](https://git-scm.com/). Det er ikke testet lige så
grundigt.

## Første gang — fork eller klon

**Hvis I bare vil køre modellen** og lave lokale eksperimenter:

```bash
git clone https://github.com/skj-1964/fjernvarme-businesscase.git
cd fjernvarme-businesscase
```

**Hvis I vil bidrage tilbage eller har egne tilpasninger** I vil holde
synkroniseret med upstream: brug **fork** først (tryk *"Fork"* på GitHub),
klon jeres egen fork, og tilføj upstream som remote:

```bash
git clone https://github.com/<jeres-værk>/fjernvarme-businesscase.git
cd fjernvarme-businesscase
git remote add upstream https://github.com/skj-1964/fjernvarme-businesscase.git
```

## Opsætning af miljø

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Test at det virker:

```bash
python run_case.py cases/billund_sporA.yaml --dummy
```

Med `--dummy` bruges syntetiske data — ingen API-kald, kører på sekunder.
Tallene ligner rigtige, men er det ikke. Når den fungerer, skift til
`--data-source github` for rigtige markeds- og vejrdata fra `df-data`:

```bash
python run_case.py cases/andeby.yaml --data-source github \
    --start 2026-01-05 --end 2026-01-17
```

Første kørsel kloner `df-data` til `data/df-data/`. Vinduet løser på
sekunder. Et helt år med balancering tager 8–15 minutter afhængigt af case
og maskine; se referencetallene i README. Hent friske data med
`git -C data/df-data pull`.

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

**2. Claude Code i terminalen** — kræver en Pro-, Max-, Team- eller
Enterprise-konto (eller API-adgang). Installeres i macOS, Linux og WSL med
`curl -fsSL https://claude.ai/install.sh | bash` og i Windows PowerShell med
`irm https://claude.ai/install.ps1 | iex`; se
[installationsvejledningen](https://code.claude.com/docs/en/setup) for andre
måder. Start med `claude` i projektmappen. Claude læser, redigerer og kører
kode selv. Bedst til større ændringer, der spænder over flere filer.

**3. Claude Code i VS Code** — udvidelse, der giver Claude som sidepanel i
editoren. Godt til at forklare eksisterende kode, mens du læser den.

For vores type projekt anbefales **Claude Code** når en ændring er
substantiel (fx tilføje et nyt marked) og **claude.ai-chat** når det er en
afgrænset YAML-justering eller en figur der skal laves.

## Versionering af jeres egne tilpasninger

Når I bygger en lokal variant til jeres eget værk, anbefales:

Start fra regnearket (`doc/vaerksdata_skabelon.xlsx`, se `doc/EGET_VAERK.md`) og læg
alt, der hører til jeres værk, i `deltagere/`:

```bash
python scripts/vaerksark_til_yaml.py deltagere/<jeres_værk>.xlsx
```

**`deltagere/` er git-ignoreret med vilje: jeres værks timedata må aldrig
committes eller pushes til det offentlige repo.** Konverteringen nægter at
skrive eller læse data et sted, git kan committe. Brug ikke `git add -f`. Vil I
versionere jeres egen case, så gør det i et privat repo uden for dette.

Tag jævnligt et "snapshot" af kørsler I rapporterer videre fra (kun af
modelkoden og de offentlige cases):

```bash
git tag v2026-bestyrelsesmøde-april
git push --tags origin
```

Så kan I altid spole tilbage til præcis den version der lå til grund for et
bestemt notat eller møde.

## Typiske faldgruber

- **Filrettigheder under WSL** — ligger klonen under `/mnt/c`, viser git
  filer som ændret fra `644` til `755`. Slå det fra med
  `git config core.fileMode false`. Filer, der allerede står som `755` i
  historikken, rettes med `git update-index --chmod=-x <fil>`.
- **Forskellige Python-versioner mellem maskiner** — hold jer til samme
  version på alle maskiner. Vi har testet på 3.10–3.13.
- **Glemt at aktivere virtual env** — symptomet er `ModuleNotFoundError:
  linopy`. Aktivér med `source .venv/bin/activate`.
- **Gammel `df-data`-klon** — en test eller kørsel, der fejler på et
  DMI-område (fx `ringsted`), skyldes ofte en klon fra før området kom ind.
  Kør `git -C data/df-data pull`.
- **API-rate limits** — kun med `--data-source api`: Energinet/DMI har
  grænser på antal kald pr. minut. Cachen i `data/raw/` gør, at I kun rammer
  dem første gang. Med `--data-source github` er der ingen grænser.
- **Store output-filer i git** — `output/` er gitignored med vilje. Hvis I
  vil dele specifikke kørsler, så zip dem og vedhæft dem til en GitHub
  Release i stedet.
