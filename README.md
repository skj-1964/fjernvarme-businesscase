# Fjernvarme Businesscase — driftsoptimering med spot- og balancemarkeder

> En åben MILP-driftsmodel for fjernvarmeværker, udviklet sammen med
> **Billund Fjernvarme** og **Dansk Fjernvarme**. Frigivet under MIT-licens,
> så andre værker kan regne på deres eget anlæg og bygge videre.

Modellen regner driften time for time over et helt år: hvilken enhed skal
producere hvornår, hvordan bruges akkumuleringstanken, og hvad kan
el-forbrugende enheder tjene på balancemarkederne (aFRR og mFRR) ved siden af
spotmarkedet. Den er skrevet i Python med open source-værktøjer (Linopy og
HiGHS), og den konfigureres i en tekstfil (YAML) eller fra et regneark.

**Rapporten [`doc/rapport_billund_v4.pdf`](doc/rapport_billund_v4.pdf)
([Word](doc/rapport_billund_v4.docx)) beskriver metode, antagelser,
validering og Billund som gennemgående case.** Læs den først, hvis det er
første gang, du møder modellen. Rapport v3 (april 2026) og dens figurer
ligger i [`doc/arkiv/`](doc/arkiv/) som historik; tal og kommandoer dér gælder
ikke længere.

---

## Hvad modellen kan, og hvad den ikke kan

| Kan | Kan ikke (endnu) |
|---|---|
| Et helt år time for time, dispatch mod spotprisen over alle enheder og tanke (MILP) | Planlægge fremad: den kender spotprisen på forhånd (perfekt foresight) |
| Scenarier som én linje: enheder og tanke slås til og fra | Gasmotorernes balanceindtægt; kun el-forbrugende enheder byder |
| Investering som differens mellem to kørsler: tank, varmepumpe, overskudsvarme | Nedregulering på forbrugssiden |
| aFRR og mFRR, kapacitet og aktivering | Forudsige balanceindtægten: Spor B er kalibreret på ét værk i én periode |
| Varmepumpe som målt ydelsestabel, varmeloft efter udetemperatur | mFRR præcist: kapaciteten overvurderes med ca. 30 %, fordi kapacitetsprisen er kendt på forhånd |
| Kører fra to offentlige repos uden API-nøgler | Løse et helt år på sekunder: det tager fra et halvt minut til over et kvarter |

---

## Kom i gang

### Vej B — Claude i browseren (ingen installation)

Det er den vej, kurset 22. oktober 2026 kører ad, og den vej modellen
blev udviklet: en fagperson uden programmeringsbaggrund i samtale med Claude.

**Du skal have:** en Claude Pro- eller Max-konto (gratiskontoen rækker ikke
til at klone repoet og køre modellen) med kodekørsel slået til under
indstillingerne, og netværksadgang, der når github.com. [BEKRÆFT efter K1]

**Første prompt:**

> Klon https://github.com/skj-1964/fjernvarme-businesscase, installér
> requirements.txt, og kør `cases/andeby.yaml` med `--data-source github`
> på vintervinduet `--start 2026-01-05 --end 2026-01-17`. Vis mig dispatch-plottet og
> KPI-tabellen.

Claude kører så:

```bash
python run_case.py cases/andeby.yaml --data-source github \
    --start 2026-01-05 --end 2026-01-17
```

Den første kørsel kloner datarepoet [`df-data`](https://github.com/skj-1964/df-data)
til `data/df-data/`. Et vindue på knap to uger løser på under et minut.
Se [`doc/WORKFLOW_CLAUDE.md`](doc/WORKFLOW_CLAUDE.md) for arbejdsformen
over flere sessioner.

### Vej A — lokalt (kræver Python 3.10–3.13)

```bash
git clone https://github.com/skj-1964/fjernvarme-businesscase.git
cd fjernvarme-businesscase
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run_case.py cases/andeby.yaml --data-source github \
    --start 2026-01-05 --end 2026-01-17
```

Resultaterne lander i `output/`. Se [`doc/WORKFLOW_LOKAL.md`](doc/WORKFLOW_LOKAL.md)
for WSL, Claude Code og typiske udviklingsmønstre.

**Skriv altid `--data-source github`.** Der er ingen standard-datakilde.
`--data-source api` henter direkte fra Energinet og DMI, men giver nul
aktiveringsindtægt med `--with-balancing`.

---

## Dit eget værk — fra regneark til model

Udfyld [`doc/vaerksdata_skabelon.xlsx`](doc/vaerksdata_skabelon.xlsx)
(timedata, anlæg, varmepumpe, priser), læg det i den git-ignorerede mappe
`deltagere/`, og konvertér:

```bash
python scripts/vaerksark_til_yaml.py deltagere/mit_vaerk.xlsx
python run_case.py deltagere/cases/<navn>.yaml --data-source github \
    --heat-csv deltagere/data/<navn>_abvaerk_hourly.csv \
    --start 2026-01-05 --end 2026-01-17
```

Konverteringen skriver selv kørselskommandoen og stopper højlydt på alt, den
ikke kan tolke. Starter dine timedata 1. juli kl. 01:00, er stemplerne
timens slut: tilføj `--timeslut`. **Værkets data må ikke komme i det
offentlige repo**; konverteringen nægter at skrive dem et sted, git kan
committe.

Alt om arket, de valgfrie blokke (brændsel pr. kedel, gasafgifter, målt
solvarme), vinduer, helår og den håndskrevne case står i
[`doc/EGET_VAERK.md`](doc/EGET_VAERK.md).

---

## Sådan må tallene bruges

1. **Differenser frem for absolutte tal.** En businesscase er scenarie minus
   reference, med samme case, periode og datakilde. Systematiske modelfejl går
   ud i differensen. Læs differenser med `--mip-gap 0.0002`; standardgabet
   (0,5 %) kan være større end selve differensen.
2. **Pr. marked og pr. produkt.** Balancetal vises for aFRR og mFRR, kapacitet
   og aktivering hver for sig, aldrig kun som en total.
3. **Spor A er en øvre grænse, ikke en prognose.** Den bindende begrænsning
   for et værk er budadfærd og tilgængelighed, ikke optimeringen.

Et modeltal gælder for en periode, under nogle antagelser, med en metode.
Skifter en af de tre, skifter tallet.

---

## Referencetal

Kørt på commit `aa4e752` med `df-data` `10be997` (8. oktober 2026). Beløb er
modellens samlede driftsomkostning i kr. (objektiv) for vinduet i casen.

| case | vindue | objektiv | kommando |
|---|---|---:|---|
| Spor A-anker | 2. marts–23. juni 2026 | **4.697.269** | `python run_case.py cases/billund_sporA.yaml --data-source github --with-balancing` |
| Spor B | 2. marts–30. juni 2026 | **3.964.586** | `python run_case.py cases/billund_sporB.yaml --data-source github --with-balancing --heat-csv data/billund_abvaerk_hourly_splejset_jun2026.csv` |
| Billund rullende år | jul 2025–jun 2026 | **20.343.221** | `python run_case.py cases/billund_sporA_rullende.yaml --data-source github --with-balancing --heat-csv data/billund_abvaerk_hourly_splejset_jun2026.csv` |
| Andeby helår, med balancering | jul 2025–jun 2026 | **23.048.152** | `python run_case.py cases/andeby.yaml --data-source github --with-balancing` |
| Andeby helår, uden balancering | jul 2025–jun 2026 | **30.430.965** | `python run_case.py cases/andeby.yaml --data-source github` |

Alle fem er optimale inden for casens gab. På en sandkasse med to kerner tog
Spor A og Spor B ca. 2 minutter, Billunds rullende år 8 minutter og Andeby
6–10 minutter (ca. 3,5 GB hukommelse). Kør ikke helårene live; regn dem på
forhånd. Andeby fik 8. oktober 2026 en solprofil fra målt DMI-globalstråling,
så Andeby-tal fra før den dato kan ikke sammenlignes.

Spor B mod Billunds afregning for marts–juni 2026 (ex post) er **121 %**
(aFRR 108 %, mFRR 132 %). Forbeholdene står i
[`doc/BALANCEMARKED.md`](doc/BALANCEMARKED.md). Andeby er et fiktivt
referenceværk: dets tal viser potentialet ved fuld tilgængelighed, ikke hvad
et værk vil tjene.

---

## Dokumentation

| fil | indhold |
|---|---|
| [`doc/rapport_billund_v4.pdf`](doc/rapport_billund_v4.pdf) | metode, validering, Billund-casen |
| [`doc/KOERSEL.md`](doc/KOERSEL.md) | alle flag til `run_case.py`, output-filer, scenarier som differens, solvergab |
| [`doc/EGET_VAERK.md`](doc/EGET_VAERK.md) | regnearket, konverteringen, vinduer og helår, case i hånden |
| [`doc/BALANCEMARKED.md`](doc/BALANCEMARKED.md) | aFRR/mFRR: bud, lofter, aktiveringsværdi, Spor A og Spor B |
| [`doc/VARMELAST_OG_NETTAB.md`](doc/VARMELAST_OG_NETTAB.md) | varmepumpens ydelsestabel, rekalibrering af varmelasten, nettabsmodellen |
| [`doc/WORKFLOW_CLAUDE.md`](doc/WORKFLOW_CLAUDE.md) | Vej B i praksis |
| [`doc/WORKFLOW_LOKAL.md`](doc/WORKFLOW_LOKAL.md) | Vej A i praksis |
| [`doc/notat_bestyrelse_datasikkerhed.docx`](doc/notat_bestyrelse_datasikkerhed.docx) | GDPR, fortrolighed og jurisdiktion ved brug af Claude. **Udkast fra maj 2026**; vilkårene for de enkelte abonnementer skal tjekkes hos Anthropic |
| [`doc/arkiv/`](doc/arkiv/) | rapport v3 og dens figurer (historik) |

---

## Data

Markeds- og vejrdata hentes fra [`df-data`](https://github.com/skj-1964/df-data),
som opdateres hver mandag: spot (15 minutters opløsning fra 2026), aFRR,
mFRR-kapacitet, mFRR-aktivering, ubalancepris og DMI-observationer. Kilden er
api.sysapp.dk, og Energi Data Service bruges til kontrol. Aktuel dækning står i
[`DATA_VERSION.md`](https://github.com/skj-1964/df-data/blob/main/DATA_VERSION.md).
Friske data: `git -C data/df-data pull`.

Casen skal angive DMI-område og priszone (`data.dmi_area`, `data.price_zone`).
Områderne er `fyn`, `vestkyst`, `karup` og `ringsted` (Sjælland og øerne).
Valget af område alene flytter objektivet med op til ca. 4 %.

---

## Struktur

```
fjernvarme-businesscase/
├── cases/          # andeby.yaml, billund_sporA/B(_rullende).yaml, heat_load_params_*
├── src/            # model, dataloadere, balancemarked, tarif, nettab, rapportering
├── scripts/        # vaerksark_til_yaml.py, byg_skabelon.py, capture_rate.py,
│                   # calibrate_heat_load.py, solprofil_fra_dmi.py m.fl.
├── tests/          # pytest
├── data/           # Billunds måledata, Andebys solprofil; df-data/ hentes automatisk
├── deltagere/      # egne værkers ark, cases og data (git-ignoreret)
├── doc/            # rapport, vejledninger, vaerksdata_skabelon.xlsx; arkiv/ med v3
├── run_case.py     # kørsel fra kommandolinjen
└── requirements.txt
```

`data/df-data/`, `data/raw/`, `output/` og `deltagere/` oprettes ved kørsel og
er git-ignoreret.

---

## Bidrag tilbage

Forbedringer er velkomne, særligt nye markedsmoduler (FCR-D, intraday),
driftsplanlægning fremad og nye referencecases. Se
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licens

MIT — se [`LICENSE`](LICENSE). Frit at bruge, ændre og videredistribuere,
også kommercielt. Modellen er udviklet sammen med Billund Fjernvarme og
Dansk Fjernvarme og deles, så andre værker kan bygge videre på den.
