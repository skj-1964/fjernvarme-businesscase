# Ændringslog

Ændringer i modellen siden kursusversionen fra oktober 2026. Nyeste står
øverst. Hele historikken står i `git log`. Her står det, en bruger skal vide.

Hvert punkt har en linje **Flytter tal**:

- **nej**: samme input giver samme objektiv som før. Skriv kontrolkørslen og
  tallet.
- **ja**: skriv hvilke kørsler der flytter sig og hvorfor, og stil det gamle og
  det nye referencetal op mod hinanden. Ret også referencetallene i README.

Beløb er objektiv i kr.

## Ikke udgivet

### Oliekedel som enhedstype

Ny enhedstype `oil_boiler` med brændslet `fuel_oil` (fyringsolie eller
gasolie). Prisen sættes i `prices.fuel_oil` pr. MWh olie inkl. energiafgift.
Den fysiske udledning er 0,266 t CO2 pr. MWh olie (74 kg/GJ, Energistyrelsens
standardfaktor); ved tung fuelolie rettes `co2_emissions_per_mwh_fuel` til ca.
0,28 i casefilen. CO2 behandles som for naturgas: én CO2-pris for værket.

Værksarket har fået rækken `fyringsolie` på arket Priser (række 10), og typen
`oil_boiler` kan vælges i Anlaeg. Mangler olieprisen eller CO2-prisen med en
oliekedel i arket, stopper konverteringen med en besked på dansk.

**Flytter tal:** nej. Ingen eksisterende case har en oliekedel. Andeby 5.–6.
januar 2026 med `--mip-gap 0.0002 --mip-abs-gap 100`: 866.568 før og efter.

**Kræver noget af brugerne:** Priser-arket i `vaerksdata_skabelon.xlsx` har
fået en række mere, så alt fra CO2-rækken og ned er rykket én række (DMI-område
B28 → B29, priszone B29 → B30). Konverteringen læser på etiketter, så et
værksark fra før kan stadig bruges uændret og giver samme casefil. Programmer,
der skriver i bestemte celler i skabelonen, skal opdateres.

## 0.10.0 (18. november 2026)

### Læs og skriv tekstfiler som UTF-8

På Windows læser Python tekstfiler som cp1252, og derfor stoppede
`run_case.py` med `UnicodeDecodeError` ved indlæsning af casen. Modellen,
scripts og test læser og skriver nu tekstfiler som UTF-8, uanset maskinens
tegnsæt. `PYTHONUTF8=1` er ikke længere nødvendigt, men det skader ikke at
beholde det.

**Flytter tal:** nej. Andeby 5.–6. januar 2026 med
`--mip-gap 0.0002 --mip-abs-gap 100`: 866.568 før og efter.

### Script til spotscenarier (af5bf09)

Nyt script `scripts/lav_spotscenarie.py`, der laver nye elprisserier ud fra
de eksisterende, med valgfrit niveau og spredning.

**Flytter tal:** nej. Scriptet er nyt, og ingen eksisterende kørsel bruger det.

### Spot midles over tidsskridtet (5021a5e og 90fb16e)

Spot er kvarterspris fra 1. oktober 2025 dansk tid. På 1-times-opløsning tog
loaderne kun :00-kvarteret. Nu midler `spot_paa_akse` over tidsskridtet.

**Flytter tal:** ja. Det gælder alle kørsler, der omfatter perioden fra
1. oktober 2025. Kørsler, der slutter før den dato, er uændrede.

| Kørsel | Periode | Før | Efter |
|---|---|---:|---:|
| Spor A-anker, med balancering | 2. marts–23. juni 2026 | 5.069.729 | 5.204.555 |
| Andeby, kun spot | juli 2025–juni 2026 | 30.431.535 | 30.495.431 |
| Billund i dag, kun spot | juli 2025–juni 2026 | 26.609.933 | 26.777.743 |
| Billund i dag, faktisk marked | juli 2025–juni 2026 | 11.101.108 | 11.378.359 |

"Før" er regnet på `eef950a` (v0.9.0), "efter" på `3cf753a`. Begge med samme
`df-data` (`bea2c1e`). Hele forskellen skyldes altså spotrettelsen. Alle
kørsler er optimale inden for casens gab (0,1 %).

Ankeret er rettet i `CONTRIBUTING.md`, README's referencetabel og
kontroltallene i `CLAUDE.md`. Resten af referencetallene i README, `doc/`,
rapport v4 og kursusmaterialet er endnu ikke regnet igen.

## 0.9.0: Kursusversion oktober 2026 (eef950a, 20. oktober 2026)

Udgangspunktet for denne log. Referencetallene står i README's
referencetabel.
