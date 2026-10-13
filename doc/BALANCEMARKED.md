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
    5,52 MW, i alt 17,52 MW.
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

`activation.foresight: profile` lader optimeringen se aktiveringsværdiens
gennemsnit pr. måned og time på døgnet i stedet for den realiserede, fordi
kapacitetsbuddet afgives dagen før. Manifestets aktiveringstal er da
forventede.

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
