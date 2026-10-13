# Kørsel — `run_case.py`, scenarier og output

`run_case.py` tager én case-YAML og en række flag. Kør
`python run_case.py --help` for den autoritative liste. Denne side forklarer
flagene og, vigtigere, hvordan to kørsler stilles op mod hinanden.

---

## Sådan læses en kørsel — forskellen mellem to scenarier

Modellen giver sjældent et interessant svar i sig selv. Værdien ligger i
**forskellen mellem to kørsler**, der er ens på nær én knap: hvad koster det at
undvære tanken, hvad bidrager balancemarkedet, hvor følsom er økonomien for
gasprisen. Kør derfor altid en reference og et scenarie med samme case,
periode og datakilde, og sammenlign deres KPI'er.

```bash
# Fælles base, gentages i begge kørsler. Strammere gab, fordi resultatet
# læses som en differens (se Solvergab nedenfor).
BASE="cases/andeby.yaml --data-source github --start 2026-01-05 --end 2026-01-17 --mip-gap 0.0002"

# Reference
python run_case.py $BASE

# Scenarie — uden de to tanke
python run_case.py $BASE --disable tank_lav --disable tank_hoej
```

Forskellen i objektivet (`noegletal.objektiv_dkk` i `_manifest.json`, og
linjen `Objektiv:` i skærmudskriften) mellem de to kørsler *er* tankenes værdi
i vinduet. `_kpi.csv` og `_monthly.csv` viser, hvilke enheder der overtager.
Filnavnene er deterministiske, så de to kørsler lander i hver sin fil.

| Spørgsmål | Knap, der ændres mellem de to kørsler |
| --------- | ------------------------------------ |
| Hvad bidrager balancemarkedet? | tilføj `--with-balancing` |
| Hvad er tankens værdi? | `--disable tank_eksisterende` (Billund) eller `--disable tank_lav --disable tank_hoej` (Andeby) |
| Hvad er en enhed værd? | `--disable <enhed>` eller `--enable <enhed>` |
| Følsomhed for brændsels- eller CO₂-pris? | `--set prices.natural_gas.value=…`, `--set prices.straw.value=…`, `--set prices.co2_eua.value=…` |
| Legacy mod kovarians-korrekt balanceindtægt? | `--balancing-method legacy` mod `activation_value` |
| Ny mod gammel nettabsmodel? | tilføj `--legacy-nettab` |

Flere knapper kan kombineres i samme kørsel, men så er forskellen den
*samlede* effekt. Vil du isolere hvert bidrag, så skift én ad gangen.
Enhedernes og tankenes navne står i casefilen under `units:` og `storage:`.

---

## Solvergab

Solveren stopper, når den har bevist, at løsningen ligger inden for et gab af
det bedst mulige. Standard er 0,5 % eller 5.000 kr (`solver:`-blokken i casen,
ellers kodens standard).

- **Absolutte tal:** 0,5 % er fint; det er lille mod usikkerheden i
  antagelserne.
- **Differenser:** brug `--mip-gap 0.0002` eller lavere. På et objektiv
  omkring 5 mio. kr er 0,5 % ca. 26.000 kr, mens et scenarie kan flytte
  2.000–14.000 kr. Med det løse gab kan differensen drukne i solverens egen
  tolerance, og fortegnet kan vende.
- **Store cases:** et helt år med mange start/stop-enheder kan være for tungt
  i ét løb. Se [`EGET_VAERK.md`](EGET_VAERK.md#helår-og-løsetid).

Casefiler fra konverteringen og `andeby.yaml` har selv en `solver:`-blok
(gab 0,1 %, tidsgrænse 3.600 s). Billund-casene bruger kodens standard
(0,5 %, 5.000 kr, 600 s).

---

## Parametre

### Positionsargument

| Argument | Beskrivelse |
| -------- | ----------- |
| `case` | Sti til case-YAML. Definerer enheder, lagre, priser, afgifter, data og balancemarked. |

### Datakilde (vælg præcis én — ingen standard)

| Flag | Beskrivelse |
| ---- | ----------- |
| `--data-source github` | **Brug denne.** DMI-temperatur og markedspriser fra `df-data`-klonen. Tæller alene som valg af datakilde. |
| `--external` | Det samme som `--data-source github`. |
| `--data-source api` | Henter direkte fra Energinet og DMI uden om `df-data`. Med `--with-balancing` giver den **nul aktiveringsindtægt**. |
| `--dummy` | Fuldt syntetiske serier. Kun til strukturtests uden net; tallene ligner rigtige, men er det ikke. |
| `--data-path PATH` | Værkets egne målerdata (ikke aktiveret). |

Til datakilden:

| Flag | Uden flag | Beskrivelse |
| ---- | --------- | ----------- |
| `--dmi-area` | `data.dmi_area` i casen (påkrævet) | `fyn`, `vestkyst`, `karup` eller `ringsted`. Flaget overskriver casen. |
| `--price-zone` | `data.price_zone` i casen (påkrævet) | `DK1` eller `DK2`. |
| `--dmi-temp-shortname` | `data.dmi_temp_shortname` (`temp_mean_past1h`) | DMI-variabel for temperatur. |
| `--eur-dkk` | `data.eur_dkk` (`7.45`) | EUR→DKK-kurs til spotprisen. |
| `--df-data-url` | `https://github.com/skj-1964/df-data.git` | Git-URL til `df-data`. |
| `--df-data-cache` | `data/df-data` | Lokal sti til `df-data`-klonen. |
| `--cache-dir` | `data/raw` | Cache for API-svar (kun `api`). |
| `--force-refresh` | — | Ignorér cachen og hent igen (kun `api`). |

### Periode (overskriver `time:` i casen)

| Flag | Beskrivelse |
| ---- | ----------- |
| `--start YYYY-MM-DD` | Startdato (kræver `--end`). |
| `--end YYYY-MM-DD` | Slutdato (kræver `--start`), **inklusive** hele dagen. `--start 2026-01-05 --end 2026-01-17` giver 5. januar kl. 00 til 17. januar kl. 23 (UTC). Et klokkeslæt (`2026-01-17T12:00`) respekteres som det står. |
| `--year YYYY` | Hele kalenderåret. Kan ikke kombineres med `--start`/`--end`. |

Kursets faste vinduer er `--start 2026-01-05 --end 2026-01-17` (vinter) og
`--start 2026-06-08 --end 2026-06-20` (sommer). DMI-området `fyn` mangler timer 1. januar og
28. februar–1. marts 2026; et vindue hen over dem stopper på dækningen.

### Varmelast

| Flag | Standard | Beskrivelse |
| ---- | -------- | ----------- |
| `--heat-csv PATH` | — | Brug målt varmebehov fra CSV i stedet for syntesen. Sådan kører alle deltagercases og Billund-casene. |
| `--heat-csv-column COL` | `heat_mw_abvaerk` | Kolonnen i CSV'en med varme i MW. |
| `--heat-csv-tz TZ` | `UTC` | Tidszone for CSV'ens stempler (fx `Europe/Copenhagen`). |
| `--heat-params PATH` | — | Alternativ `heat_load_params`-YAML, fx fra `scripts/calibrate_heat_load.py`. |
| `--legacy-nettab` | — | Den gamle hældningsbaserede nettabsmodel, til sammenligning. |

Se [`VARMELAST_OG_NETTAB.md`](VARMELAST_OG_NETTAB.md).

### Balancemarked

| Flag | Beskrivelse |
| ---- | ----------- |
| `--with-balancing` | aFRR- og mFRR-priser og reservemodellen. Perioden skal ligge efter ca. april 2025 (PICASSO). Kræver `--data-source github` for aktiveringsindtægten. |
| `--balancing-method {legacy,activation_value}` | Overskriver `balancing.method` i casen. |

Se [`BALANCEMARKED.md`](BALANCEMARKED.md).

### Enheder og parametre

| Flag | Beskrivelse |
| ---- | ----------- |
| `--enable NAVN` | Slå en enhed eller et lager til. Kan gentages. |
| `--disable NAVN` | Slå en enhed eller et lager fra. Kan gentages. |
| `--set PATH=VALUE` | Overskriv en vilkårlig værdi i YAML'en. Værdien læses som YAML. Kan gentages. Fx `--set prices.co2_eua.value=800`, `--set storage.tank_eksisterende.volume_m3=4000`. |

### Solver og output

| Flag | Standard | Beskrivelse |
| ---- | -------- | ----------- |
| `--mip-gap` | `solver.mip_rel_gap` (0,005) | Relativt gab. 0,0002 til differenser. |
| `--mip-abs-gap` | `solver.mip_abs_gap` (5.000 kr) | Absolut gab i kr. |
| `--solver` | `highs` | MILP-solver. |
| `--days` | `7` | Antal dage i dispatch-plottet. |
| `--out-dir` | `output` | Output-mappe. |

---

## Output

Hver kørsel skriver filer med et deterministisk præfiks, der afspejler
kørslen:
`{case}__{data}__{periode}[__bal-{metode}][__legnet][__heatcsv][__overrides]`.
Overrides sorteres alfabetisk, så samme scenarie altid giver samme filnavn.

| fil | indhold |
|---|---|
| `_manifest.json` | objektiv, varmebehov, nettab, balanceindtægt, tankarbitrage, CO₂; kørslens flag, overrides, commit og solverstatus |
| `_kpi.csv` | pr. enhed: produktion, andel, kapacitetsfaktor og driftstimer |
| `_monthly.csv` | produktion pr. enhed og måned, varmebehov, gennemsnitlig spotpris og udetemperatur |
| `_hourly.csv` | timeværdier for alle enheder, tanke og priser |
| `_dispatch.png` | dispatch-plot for de første `--days` dage |
| `_dispatch.nc` | hele løsningen (bruges af `scripts/capture_rate.py`) |

Skærmudskriften slutter med objektivet, status og det opnåede gab. Gem den,
hvis gabet skal dokumenteres; manifestet har kun status.
