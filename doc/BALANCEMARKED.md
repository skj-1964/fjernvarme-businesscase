# Balancemarked — aFRR og mFRR

Med `--with-balancing` udvides MILP'en med op-reguleringsreserver på **aFRR**
(automatisk) og **mFRR** (manuel). Reserverne leveres af de **el-forbrugende**
enheder (varmepumpe og elkedler): en enhed, der forbruger el, kan byde
op-regulering ved at *kunne stoppe* forbruget, hvis den kaldes. Kun enheder med
`fuel: electricity` byder (`_eligible_units_for_market`), også selvom
`afrr_qualified` er sat på en anden enhed.

**Ikke med:** gasmotorernes balanceindtægt og nedregulering. Hos Billund
var motorerne en væsentlig del af den samlede balanceindtægt i marts–juni 2026,
så modellens balancetal er ikke værkets samlede balancetal.

Kræver `--data-source github` (med `api` bliver aktiveringsindtægten nul) og
en periode efter ca. april 2025 (PICASSO).

---

## Bud, kvalifikation og lofter

For hver kvalificeret enhed `i` og time `t` er der to budvariable `r_afrr[i,t]`
og `r_mfrr[i,t]` (elektriske MW). De styres af:

- **Kvalifikation** pr. enhed og marked: `ancillary.afrr_qualified` og
  `ancillary.mfrr_qualified`.
- **Footroom:** produktionen skal kunne dække fuld aktivering af summen af
  begge bud, `heat_prod[i,t] ≥ COP(t)·(r_afrr[i,t] + r_mfrr[i,t])`. Det er den
  fysiske binding, der kobler reserven til varmedriften og tanken.
- **Lofter:** reservationen overstiger aldrig enhedens største eloptag (for en
  varmepumpe med ydelsestabel: tabellens største eloptag). Ovenpå gælder, i
  prioriteret rækkefølge:
  - `balancing.ancillary_caps` (anbefalet): `per_unit_mw` pr. enhed (aFRR +
    mFRR, altid håndhævet) og `total_mw`, ét samlet loft over alle bud og begge
    markeder pr. time, fx værkets prækvalifikation. Billund: varmepumpe
    5,52 MW, i alt 17,52 MW (marts–juni 2026) og 47,52 MW med den nye elkedel.
- **Nettilslutning:** `grid: {max_consumption_mw: ...}` er et loft over det
  samlede eloptag fra varmepumper og elkedler pr. time (Σ varme/COP). Det
  gælder driften før aktivering og, med robust reservation, planen uden
  aktivering, og det begrænser dermed også reservationen gennem footroom.
  Elproduktion modregnes ikke. Billund: 33 MW.
  - `balancing.shared_reserve_cap_mw`: ældre form af det samlede loft.
  - `ancillary.afrr_max_bid_mw` / `mfrr_max_bid_mw` pr. enhed og
    `ancillary_groups`: pris-tager-beskyttelse, når intet samlet loft er sat.

---

## Indtægt — `balancing.method`

Begge metoder trækker reserveindtægten fra omkostningsobjektivet. Den består af
en **kapacitetsdel** (`π_cap(t)·r`) og en **aktiveringsdel**.

- **`activation_value` (anbefalet, kræver `bid_strategy`).** En
  aktiveringsværdi beregnes direkte fra kvarterpriserne:

  ```
  av(t) = Σ_{τ ∈ t}  Δτ · f(τ) · ( p_act(τ) + spot(τ) + el_cost_flat )
  ```

  Pris og aktivering evalueres i samme kvarter, så samvariationen fanges.
  Parentesen er den fulde værdi af én MWh op-reguleret el: aktiveringsprisen
  **plus** den sparede forbrugsomkostning (spot, tarif og elafgift).
  Aktiveringsindtægten forbliver lineær: `Σ_t av(t)·r(t)`.
- **`legacy` — `E[α]×E[p]`.** Timegennemsnit gange timegennemsnit. Enkel, men
  undervurderer systematisk, når aktivering og pris hænger sammen inden for
  timen. Til sammenligning.

### Budstrategi (`balancing.bid_strategy`)

Værkets bud på aktiveringsmarkedet er spot plus et tillæg:

```yaml
balancing:
  method: activation_value
  bid_strategy:
    up_markup_dkk_mwh: 500        # bud op = spot + 500
    up_markup_max_dkk_mwh: 2000   # øvre bånd (dokumentation)
```

### Aktiveret andel (`balancing.activation`)

At buddet ligger i merit, er ikke det samme som at det aktiveres. Blokken
styrer, hvor stor en andel `f(τ)` af den reserverede MW der regnes aktiveret i
et kvarter:

| model | f(τ) |
|---|---|
| `clear` (standard) | `1[p ≥ bud]`. Gav 4–5 gange for meget aktiveret energi mod Billunds afregning. |
| `system_share` | `1[p ≥ bud] · min(1, k·α(τ))`, α = systemets aktiverede volumen / indkøbt kapacitet |
| `ramp` | `min(1, max(0, (p − bud) / ramp_dkk_mwh))` |

`activation.foresight` vælger, hvad optimeringen ved om aktiveringen, når
den reserverer. Kapacitetsbuddet afgives dagen før, så den realiserede
aktivering er ikke kendt:

| foresight | optimeringen ser | kigger frem |
|---|---|---|
| `realized` (standard) | den realiserede aktiveringsværdi | ja, fuldt |
| `profile` | gennemsnit pr. kalendermåned og time på døgnet | delvist (resten af måneden) |
| `trailing30` | gennemsnit af samme time de seneste 30 døgn før i dag | nej |
| `lag24` / `lag168` | samme time i går / sidste uge | nej |

`activation.settle` afgør, hvad tallet afregnes på. `forecast` (standard)
rapporterer prognosens værdi. `realized` løser først på prognosen, låser
reservationerne og løser driften igen på de realiserede aktiveringer; begge
objektiver skrives ud. `balancing.robust_reservation: true` kræver desuden, at
driften holder, hvis buddet ikke aktiveres (standard fra 15. oktober 2026).
Valget af budstrategi og profiler til eget værk:
[`BUDSTRATEGI.md`](BUDSTRATEGI.md).

---

## Spor A og Spor B

| | Spor A — normativ | Spor B — beskrivende |
|---|---|---|
| case | `billund_sporA.yaml` (marts–juni 2026), `billund_sporA_rullende.yaml` (jul 2025–jun 2026) | `billund_sporB.yaml` (marts–juni 2026) |
| spørgsmål | Hvad *kunne* værket tjene med fuld tilgængelighed? | Hvad gav modellen med den reservation, værket faktisk stillede til rådighed? |
| reservation | frit inden for lofterne og en kapacitetsprisgate (`reservation_gate`, `mode: bound`) | loftet `availability` med Billunds reserverede MW pr. måned; gaten er slået fra |
| aktivering | `clear` | aFRR `system_share` (k = 4), mFRR `clear`, `foresight: profile` |
| brug | **øvre grænse**, ikke en prognose | validering mod afregning; forudsiger ikke |

### Kapacitetsprisgaten (`reservation_gate`)

Gaten åbner reservationen i et marked kun i timer, hvor day-ahead
kapacitetsprisen er over en tærskel, med en fast blok:

```yaml
balancing:
  reservation_gate:
    enabled: true
    mode: bound                  # loft: Σ r ≤ gate(t)·blok
    afrr: { cm_threshold_dkk_mw_h: 75, block_mw: 2.82 }
    mfrr: { cm_threshold_dkk_mw_h: 300, block_mw: 4.46 }
```

`mode: driven` gør gaten til en lighed (reservationen *er* blokken, når gaten
er åben). Den blev brugt til Spor B, men er afløst af tilgængelighedsloftet og
er slået fra i `billund_sporB.yaml`. `billund_sporB_rullende.yaml` bruger den
stadig.

### Tilgængelighedsloftet (`balancing.availability`)

Uden loft reserverer modellen al den effekt, footroom tillader, for Billund
3–8 gange det realiserede. Loftet er værkets faktiske reservation:

```yaml
balancing:
  availability:
    enabled: true
    mode: energy              # hourly: loft i hver time; energy: på månedens MWh
    afrr:
      mw_by_month: {"2026-03": 1.155, "2026-04": 1.186}
```

Måneder i vinduet uden loft stopper kørslen med vilje. Loftet beskriver én
periode for ét værk og kan ikke overføres til andre værker eller perioder.

---

## Fiktivt 2026-marked (scenarie)

Balancemarkedet skiftede omkring årsskiftet 2025/26: aFRR-kapacitetsprisen faldt
til en fjerdedel, og mFRR blev det største marked. Et år, der går fra juli 2025
til juni 2026, blander derfor to markeder. Vil du regne et helt år på
2026-niveau, kan du bygge et **fiktivt** marked:

```bash
python scripts/fiktivt_balancemarked.py
```

Scriptet kopierer `data/df-data` til `data/df-data-2026niveau` (git-ignoreret)
og skalerer balancepriserne for opregulering i DK1 i juli–december 2025, så hver
måned får samme gennemsnit som januar–juni 2026:

- aFRR- og mFRR-kapacitetspriserne ganges med én faktor pr. måned.
- Aktiveringspriserne skaleres på præmien over spot, kun i kvarterer hvor
  prisen ligger over spot. Timingen og sammenhængen med spotprisen bevares.
- Spot, vejr, mængder, nedregulering og alle andre måneder er urørt.

Faktorerne skrives i `faktorer.json` og `FIKTIVT_MARKED.md` i målmappen. Periode,
reference og priszone kan vælges (`--periode`, `--reference`, `--zone`); se
`--help`.

Kør derefter med `--df-data-cache`:

```bash
python run_case.py cases/billund_idag.yaml --data-source github --with-balancing \
    --df-data-cache data/df-data-2026niveau \
    --heat-csv data/billund_abvaerk_hourly_splejset_jun2026.csv
```

`cases/billund_idag.yaml` er Billunds anlæg i dag (den nye elkedel med,
varmepumpen byder hele året, alle tre el-enheder prækvalificeret, 47,52 MW,
og nettilslutningen begrænset til 33 MW el) og er brugt i rapport v4, afsnit 4.5. Casen og
markedet er scenarier: de er ikke valideret og beskriver ikke et bestemt år.
Tal regnet på dem må ikke præsenteres som data. Byg markedet igen
(`--overskriv`), når `df-data` er opdateret.

## Validering mod Billunds afregning

```bash
python run_case.py cases/billund_sporB.yaml --data-source github --with-balancing \
    --heat-csv data/billund_abvaerk_hourly_splejset_jun2026.csv --out-dir output/sporB

python scripts/capture_rate.py <dispatch.nc> --case cases/billund_sporB.yaml \
    --facit <facit mar–jun> --start 2026-03-02 --end 2026-06-30 --ex-post
```

Brug den splejsede varmelast; `data/billund_abvaerk_hourly.csv` har 161
manglende timer i vinduet. Facit er Billunds afregning og ligger ikke i repoet.

Resultatet er **121 %** af det realiserede (aFRR 108 %, mFRR 132 %). Læs det
med disse forbehold:

- Kalibreringen gælder kun marts–juni 2026 og kun med Billunds reservation pr.
  måned som loft. Markedet skiftede fra aFRR-domineret i 2025 til mFRR-tungt i
  2026; tal fra den ene periode kan ikke bruges om den anden.
- mFRR er overvurderet med ca. 30 %, fordi modellen kender kapacitetsprisen
  på forhånd og samler reservationen i få dyre timer.
- Motorernes balanceindtægt og nedregulering er ikke med.
- Budreglen er ikke backtestet mod priser kendt på budtidspunktet.

**Sådan må tallene bruges:** som differenser, pr. marked og pr. produkt, og
Spor A som øvre grænse.
