# Claude i skyen — workflow

Denne guide er til værker der vil bruge modellen *uden at installere Python
lokalt*. Det er den arbejdsform pilotprojektet i Billund blev udviklet i —
hele kodebasen er bygget af en domæneekspert uden programmeringsbaggrund i
samtale med Claude.

Forudsætningen er en **Claude Pro- eller Max-konto**. Gratiskontoen rækker
ikke til at klone repoet og køre modellen. Kodekørsel skal være slået til under
indstillingerne, og netværksadgangen skal nå github.com. [BEKRÆFT efter K1]

## Hurtig opsætning

1. **Hent modellen og kør et kort vindue.** Første prompt:

   > Klon https://github.com/skj-1964/fjernvarme-businesscase, installér
   > requirements.txt, og kør `cases/andeby.yaml` med `--data-source github`
   > på vintervinduet `--start 2026-01-05 --end 2026-01-17`. Vis mig
   > dispatch-plottet og KPI-tabellen.

   Første kørsel kloner også datarepoet `df-data`. Et vindue på knap to uger
   løser på under et minut; et helt år tager fra et halvt minut til over et
   kvarter og bør regnes på forhånd.

2. **Stil dit næste spørgsmål.** Eksempler:
   - *"Hvad gør tanken i den dyreste time i vinduet?"*
   - *"Slå tankene fra, kør vinduet igen, og vis mig forskellen i objektivet."*
   - *"Hvad sker der, hvis halmprisen stiger til 400 kr/MWh?"*

3. **Dit eget værk.** Vedhæft dit udfyldte regneark og bed Claude lægge det i
   `deltagere/` og konvertere det med `scripts/vaerksark_til_yaml.py`. Se
   [`EGET_VAERK.md`](EGET_VAERK.md). Dit ark bliver i din egen session og
   kan ikke committes til repoet.

Skriv altid `--data-source github` i kommandoerne. Der er ingen
standard-datakilde, og `api` giver nul aktiveringsindtægt i balancemarkedet.

## Hvad Claude kan gøre i denne form

| Opgave | Hvordan |
|---|---|
| Forklare modellen, antagelser, valg | Læser kildekoden, README, `doc/` og rapport v4 |
| Køre modellen | Kodekørsel i sandkassen: kloner repoet, installerer pakker og kører `run_case.py` |
| Modificere YAML-konfiguration | Genererer en ny `.yaml` du kan downloade |
| Lave nye figurer | Genererer matplotlib-plots inline eller som download |
| Tolke resultater | Læser dine output-CSV'er og forklarer |
| Tilpasse kode | Foreslår patches du kan teste; ved større ændringer producerer den filer |
| Skrive dokumentation til bestyrelse/kolleger | Genererer notater i Word eller markdown |

## Hvad Claude *ikke* kan gøre i denne form

- **Pushe direkte til jeres GitHub** — I skal selv uploade ændrede filer
  (det tager 30 sekunder via web-UI'en, se næste afsnit).
- **Læse jeres SCADA-system, fjernlæse målere, kalde interne API'er** —
  data skal eksporteres som CSV og uploades til projektet.
- **Huske ting på tværs af projekter** — kontekst lever inde i ét Project.

## Versionering — hvordan I holder styr på ændringer

Den mest praktiske rytme er:

**1. Brug status-dokumenter.** Efter hver chat-session af betydning, bed
Claude om at skrive en kort `STATUS_sessionN.md` der opsummerer:
hvad blev opnået, hvilke filer blev ændret, hvad er næste skridt.
Upload den til projektets knowledge. Det er den mekanisme der gjorde det
muligt at strække Billund-projektet over 12+ sessioner uden at miste
sammenhæng.

Eksempel-prompt:

> *"Skriv en STATUS_session3.md der opsummerer hvad vi har gjort i denne
> session. Følg samme struktur som de tidligere status-filer."*

**2. Periodisk sync til GitHub.** Når I har et meningsfuldt sæt ændringer
(typisk efter 1-3 sessioner), så:

- Bed Claude pakke de ændrede filer til en ZIP, du kan downloade
- Pak ud lokalt
- Brug GitHub's web-UI til at uploade dem — *Add file → Upload files* i din
  fork's hovedmappe. Skriv en commit-besked.
- **Verificér efter push.** Klon repo'et på ny, sammenlign de uploadede filer
  med dem Claude leverede, kør `pytest` og tjek filtilstande
  (`git ls-files --stage`). Det fanger fejl, der ellers først ses senere — fx en
  fil der ikke blev uploadet, eller rettigheder der er ændret.

Hvis I vil bidrage tilbage til upstream-repoet, lav en *Pull Request* fra
jeres fork.

**3. Tag stable versioner.** Når I har et resultat I rapporterer videre på
(bestyrelse, ansøgning, beslutningsoplæg), opret en *Release* på GitHub med
et meningsfuldt navn (`v2026-bestyrelsesmøde-april`). Vedhæft den ZIP der
indeholder konfiguration + output-filer. Så er den specifikke version
permanent reproducerbar.

## Praktiske tips fra Billund-pilotprojektet

- **Vedhæft altid relevant kontekst i prompten.** Hvis du har ændret en YAML
  i forrige tur og nu beder om en kørsel, så vedhæft YAML'en igen — Claude
  skal kunne se nøjagtigt den version du arbejder med.

- **Vær specifik om hvad du vil have.** *"Kan du lave en graf?"* giver
  middelmådige resultater. *"Lav et stablet søjlediagram med månedlig
  varmeproduktion per enhed; halm nederst, gas øverst, med varmebehovet som
  sort streg ovenpå"* giver præcis det du tænkte på.

- **Verificér overraskende tal.** Claude tager fejl, særligt på detaljer.
  Når et resultat overrasker, så bed Claude vise mellemregningen eller kør
  selv en sanity check. Det er hurtigt og det fanger fejl tidligt.

- **Hold sessioner afgrænsede.** En chat der fylder hele kontekstvinduet
  bliver gradvist sløvere og mere upålidelig. Når et arbejdsemne er
  færdigt, lav en STATUS-fil og start en ny chat.

- **Læs fejlmeddelelser før du klager.** Når noget fejler, kopier *hele*
  fejlmeddelelsen tilbage til Claude. Den er meget god til at læse stack
  traces.

## Når noget bliver for stort til Claude i chatten

Nogle ændringer kræver flere ture med kode-rettelser, kørsler, debugging.
Hvis du oplever at en chat bliver for langsom eller du rammer brugsgrænser,
har du to muligheder:

- **Skift til Claude Code i terminalen** — kræver en let installation
  (`npm install -g @anthropic-ai/claude-code`), men giver Claude adgang til
  hele projektmappen direkte. Beskrevet i [`WORKFLOW_LOKAL.md`](WORKFLOW_LOKAL.md).

- **Bryd opgaven i mindre dele** — hver chat tackler én afgrænset opgave.
  STATUS-filen er broen mellem dem.

Pilotprojektet brugte begge: store strukturændringer i Claude Code,
domænediskussioner og analyser i claude.ai-chat med projektet.
