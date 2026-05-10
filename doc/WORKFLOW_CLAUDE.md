# Claude i skyen — workflow

Denne guide er til værker der vil bruge modellen *uden at installere Python
lokalt*. Det er den arbejdsform pilotprojektet i Billund blev udviklet i —
hele kodebasen er bygget af en domæneekspert uden programmeringsbaggrund i
samtale med Claude.

Forudsætningen er en **Claude.ai-konto** (Pro anbefales — den giver
væsentligt højere brugsgrænser og adgang til Code Execution).

## Hurtig opsætning

1. **Hent koden som ZIP**. På GitHub-siden: tryk det grønne *"Code"*-knap →
   *"Download ZIP"*. Pak ud lokalt — typisk i `Documents/`.

2. **Opret et nyt Project i Claude.ai**. Gå til [claude.ai](https://claude.ai),
   tryk *"+ New Project"*, giv det et navn som *"Driftsoptimering — &lt;jeres
   værk&gt;"*. Et Project er en samtalesamling der deler en fælles
   "knowledge base".

3. **Upload alle filer fra ZIP'en til projektets knowledge.** Træk og slip
   hele mappen ind i *Project knowledge*-feltet. Claude får så modellen,
   konfigurationen, rapporten og data tilgængelige i hver ny chat i
   projektet.

4. **Slå Code Execution til** under chat-indstillingerne. Det giver Claude
   adgang til en isoleret Python-sandbox hvor modellen kan køres.

5. **Stil dit første spørgsmål.** Eksempler:
   - *"Kan du give mig et resumé af hvad denne model gør, baseret på rapporten?"*
   - *"Kør baseline-scenariet C for et par måneder og vis mig resultatet."*
   - *"Hvad sker der hvis halmprisen stiger til 400 DKK/MWh?"*

## Hvad Claude kan gøre i denne form

| Opgave | Hvordan |
|---|---|
| Forklare modellen, antagelser, valg | Læser fra `doc/rapport_billund_v3.docx` og kildekoden |
| Køre modellen | Code Execution — installerer pakker og kører `run_case.py` |
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
