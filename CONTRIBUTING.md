# Sådan bidrager I tilbage

Tak fordi I overvejer at dele en ændring tilbage. Modellen bliver kun
bedre af at andre værker bygger ovenpå.

## Hvad bidrager I med?

Vi tager imod alt der gør modellen mere brugbar for danske fjernvarme­selskaber:

- **Nye markedsmoduler** — fx FCR-D, intraday, regulerkraft
- **Nye værkstopologier som referencecases** — særligt hvis I har et anlæg
  der adskiller sig væsentligt fra Billund (geotermi, varmelagre i jorden,
  store solvarmeanlæg, kombineret KV/varmepumpe)
- **Bedre kalibreringsrutiner** — fx hvis I finder en mere robust måde at
  fitte varmelast end den nuværende dual-slope
- **Dokumentation, eksempler, fejlrettelser** — alt fra typo-fixes til
  bedre forklaringer er velkomne
- **Sammenligning mod faktiske drift** — backtests af modellens dispatch
  mod jeres SCADA er ekstremt værdifulde

## Sådan gør I det

1. **Fork repoet** på GitHub (tryk *Fork*)
2. **Klon jeres fork** og opret en branch:
   ```bash
   git clone https://github.com/<jer>/fjernvarme-businesscase.git
   cd fjernvarme-businesscase
   git checkout -b min-tilføjelse
   ```
3. **Lav ændringen.** Hvis det er en ny case, lægges den i `cases/`. Hvis
   det er en model-udvidelse, kommer ændringerne i `src/`. Tilpas
   dokumentation hvor relevant.
4. **Test at den kørte 2×2-matrix stadig virker** før I sender — det er den
   primære smoke-test:
   ```bash
   python run_case.py cases/billund_baseline.yaml --external \
       --start 2025-04-01 --end 2026-03-31 --with-balancing
   ```
5. **Commit og push:**
   ```bash
   git add .
   git commit -m "Tilføj <kort beskrivelse>"
   git push origin min-tilføjelse
   ```
6. **Åbn en Pull Request** mod upstream `main`-branchen. Beskriv kort:
   - Hvad ændringen gør
   - Hvorfor (hvilket problem løser den)
   - Hvordan I har testet den

## Stil og konventioner

- **Sprog:** dokumentation og kommentarer på dansk, kode-identifiers på
  engelsk (det matcher resten af kodebasen).
- **YAML:** følg strukturen i `cases/billund_baseline.yaml`. Brug `[TBC]`
  som markering for værdier der afventer bekræftelse.
- **Python:** følg den eksisterende stil (PEP-8 i grove træk). Hold linjer
  under ~100 tegn. Tilføj docstrings på nye funktioner.
- **Filnavne:** lowercase med understreger, undgå mellemrum og særtegn.

## Bidrag fra Claude-genererede ændringer

Det er fuldt fint at bruge Claude (eller en anden AI) til at generere
ændringer. Vi forventer dog at I:

- **Læser ændringen igennem selv** før I sender den. AI tager fejl,
  særligt på detaljer.
- **Tester at den virker** med 2×2-matrixen ovenfor.
- **Beskriver i PR'en at den er AI-genereret** hvis det er hovedparten af
  ændringen — så vi ved at fagligt review behøves.

## Kontakt

Spørgsmål eller usikkerhed? Åbn et *Issue* på GitHub før I bygger noget
stort — så undgår vi dobbeltarbejde og I får tidligt input.

For større arkitektur-ændringer er det også muligt at kontakte Dansk
Fjernvarme direkte; se hjemmesiden.
