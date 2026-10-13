# Dit eget værk — fra regneark til model

Den letteste vej er Excel-skabelonen
[`vaerksdata_skabelon.xlsx`](vaerksdata_skabelon.xlsx). Du udfylder fire ark,
og et script bygger casefilen og varmelasten. Du skal ikke skrive YAML.

**Værkets data må ikke komme i det offentlige repo.** Mappen `deltagere/` er
git-ignoreret, og konverteringen nægter at læse et ark eller skrive en fil et
sted i repoet, som git kan committe. Læg arket i `deltagere/` eller uden for
repoet. `--tillad-offentlig` slår vagten fra og er kun til egne
referencecases som Andeby, aldrig til en andens data.

---

## 1. Udfyld arket

**Timedata.** Samlet varmeproduktion ab værk (MW) time for time for
1. juli 2025 – 30. juni 2026, og årsproduktionen i GWh i B3.

- **Tidszonen er et felt**, der skal stå som `UTC` eller `dansk lokaltid`.
  Den gættes ikke: en forkert tidszone flytter hele året en eller to timer i
  forhold til elprisen, uden at noget ser forkert ud.
- **Timens start eller slut?** Starter serien 1. juli kl. 01:00 og slutter
  1. juli kl. 00:00, er stemplerne timens slut. Så skal konverteringen have
  `--timeslut`; uden flaget stopper den.
- Manglende timer står som tomme celler, aldrig som nul (nul er en gyldig
  måling).
- Er Timedata tom, men B3 udfyldt, skrives kun casefilen, og modellen
  syntetiserer varmelasten ud fra DMI-vejret.

**Anlaeg.** Produktionsenheder og akkumuleringstanke. Alle syv enhedstyper kan
bruges: `heat_pump`, `electric_boiler`, `biomass_boiler`, `gas_boiler`,
`gas_engine_chp`, `solar_thermal` og `waste_heat`. De grå rækker er eksempler:
slet dem, du ikke har, eller skriv hen over. Overskrifterne (`navn` over
enhederne, `tank` over tankene) skal blive stående; konverteringen finder
blokkene på dem. Formler skal have en beregnet værdi (gem arket i Excel), ellers
stopper konverteringen.

**Varmepumpe.** Målepunkter (udetemperatur, varme, el ved fuld last) for hver
varmepumpe, gerne tre punkter omkring −10, 0 og +15 °C. Uden punkter bruges
COP ved 0 °C fra Anlaeg og en lineær kurve, og konverteringen siger det. Se
[`VARMELAST_OG_NETTAB.md`](VARMELAST_OG_NETTAB.md#varmepumpens-ydelse--cop_curve).

**Priser.** Brændsels- og elpriser, elafgift, nettarif pr. bånd og sæson
(vinter oktober–marts, sommer april–september), DMI-område og priszone. Arket
læses på **etiketterne i kolonne A**: rækker må indsættes og flyttes, men
posterne må ikke omdøbes. En ukendt række blandt brændslerne stopper
konverteringen med rækkenummer og tekst. Brændslerne er naturgas, halm,
træpiller, flis, overskudsvarme og CO2.

DMI-området vælges efter beliggenhed: `vestkyst`, `karup` (Midt- og
Vestjylland), `fyn` eller `ringsted` (Sjælland og øerne). Se stationerne i
[`df-data`](https://github.com/skj-1964/df-data#readme).

### Valgfrie tilføjelser

De tre ting findes ikke i skabelonen endnu, men konverteringen læser dem:

- **Brændsel pr. biomassekedel:** kolonne N `brændsel` i Anlaeg med `halm`,
  `træpiller` eller `flis`. Uden kolonnen bruges det ene biomassebrændsel, der
  har en pris. Har flere en pris, skriver konverteringen en advarsel eller
  stopper.
- **Gasafgifter og gastariffer:** en blok på Priser med én række pr. afgift:
  post, sats, enhed (`kr/m3` eller `kr/MWh`) og hvem den gælder for (`alle`,
  `kedler`, `motorer`), plus en række `brændværdi naturgas` i kWh/m³. Det, der
  gælder alle, lægges på gasprisen. Det, der kun gælder kedler eller motorer,
  lægges på enhedens D&V pr. MWh varme, fordi modellen ikke har en afgift pr.
  enhed; det står i enhedens `notes`.
- **Målt solvarme:** et ark `Solvarme`, opbygget som Timedata. Det erstatter
  den syntetiske profil. Huller inde i serien interpoleres op til 5 %, og der
  advares, hvis der er produktion, mens solen er under horisonten (fx
  frostsikring, som modellen ellers regner som gratis varme). `--timeslut`
  gælder også dette ark.

---

## 2. Konvertér

```bash
python scripts/vaerksark_til_yaml.py deltagere/mit_vaerk.xlsx
# timens slut:
python scripts/vaerksark_til_yaml.py deltagere/mit_vaerk.xlsx --timeslut
```

Scriptet skriver `deltagere/cases/<navn>.yaml` og
`deltagere/data/<navn>_abvaerk_hourly.csv` og slutter med den kommando, der
kører casen. Det stopper højlydt på alt, det ikke kan tolke: en case, der
bygger på et ark med en tom kolonne, er værre end ingen case, fordi tallene ser
rigtige ud. Huller i timedata meldes; op til 5 % af vinduet udfyldes ved
lineær interpolation, over det stopper modellen.

Scriptet skriver aldrig hen over en eksisterende fil uden `--overskriv`. Har du
rettet i den genererede case i hånden, så konvertér ikke igen med
`--overskriv`; dine rettelser forsvinder.

Læs blokken øverst i den genererede case. Den siger, hvad der er antaget, og
hvad der skal bekræftes.

---

## 3. Kør et kort vindue først

```bash
python run_case.py deltagere/cases/<navn>.yaml --data-source github \
    --heat-csv deltagere/data/<navn>_abvaerk_hourly.csv \
    --start 2026-01-05 --end 2026-01-17
```

Det er kursets vintervindue. Sommervinduet er `--start 2026-06-08 --end 2026-06-20`.
`--end` tager hele slutdagen med, så vinduerne er 13 døgn. De løser typisk
på sekunder til et halvt minut.

**Tjek før du tror på tallene:** Kører enhederne i den rækkefølge, I faktisk
kører dem? Ligner varmepumpens og elkedlens timer det, I kender? Tom eller fuld
tank hele tiden? Svaret "det kan ikke passe" er det rigtige at give; find så ud
af, om det skyldes data, en antagelse eller modellen.

Balancemarkedet er slået fra i den genererede case. Slå det kun til
(`--with-balancing`) og udfyld lofterne, hvis værket er prækvalificeret hos
Energinet. Se [`BALANCEMARKED.md`](BALANCEMARKED.md).

---

## Helår og løsetid

Et helt år tager fra et halvt minut til over et kvarter, afhængigt af hvor
mange enheder der har start/stop (unit commitment: minimum last, minimum
driftstid, startomkostning). En case med mange sådanne enheder og lange
minimum driftstider kan være for tung til ét løb.

Så er der to veje:

1. **Løsere gab:** `--mip-gap 0.003` til `0.005`. Det flytter objektivet
   ubetydeligt for absolutte tal, men kan gøre en svær måned flere gange
   hurtigere.
2. **Månedsvinduer:** kør hver måned for sig med `--start`/`--end` og læg
   resultaterne sammen. Ulemperne: hver måned starter med enhederne slukket,
   så startomkostninger tælles igen; tanken bindes til halv fyldning ved hvert
   månedsskifte. `--end` med en dato tager hele døgnet med, så januar er
   `--start 2026-01-01 --end 2026-01-31`.

Regn helåret på forhånd, og vis det; kør kun korte vinduer live.

---

## Avanceret: skriv casen i hånden

Vil du ikke bruge regnearket, kan du tilpasse en case direkte:

1. Kopiér `cases/andeby.yaml` til `deltagere/cases/<dit_værk>.yaml`. Andeby er
   et fiktivt værk med syv enhedstyper og to tanke, og dens kommentarer
   forklarer hvert felt.
2. Erstat enheder, kapaciteter, virkningsgrader og priser med dine egne. Sæt
   `data.dmi_area` og `data.price_zone`.
3. Læg din måling ab værk i `deltagere/data/` og brug `--heat-csv`, eller
   rekalibrér syntesen (se [`VARMELAST_OG_NETTAB.md`](VARMELAST_OG_NETTAB.md)).
4. Opdatér `heat_load_params.nettab` med jeres årlige nettab og temperaturer.
5. Kør et kort vindue, og tjek, at dispatchen ligner virkeligheden.

Marker egne antagelser med `[BEKRÆFT]` i casens kommentarer, til de er
bekræftet.
