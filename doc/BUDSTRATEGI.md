# Budstrategi i balancemarkedet

Sådan vælger du, hvordan modellen byder ind i aFRR og mFRR, og hvorfor valget betyder mere for resultatet end markedet selv. Filen er skrevet, så Claude kan læse den og sætte en budprofil ind i din case.

Se også [`KOERSEL.md`](KOERSEL.md) for kørsler som differens og solvergab.

---

## 1. Hvorfor budstrategien er det vigtigste valg

Modellen kan regne på balancemarkedet på flere måder, og det er især **budstrategien** der bestemmer, hvor stort tallet bliver. På samme værk, samme år og samme data kan modellen give alt fra få millioner til et tal, der er større end hele værkets varmeproduktionsomkostning. Det sidste er en sikker indikator på, at noget er forkert.

Forskellen ligger ikke i markedet, men i de antagelser, man giver modellen om tre ting:

1. **Hvornår byder værket**, og til hvilken pris.
2. **Hvor meget byder værket ind**, og hvad der begrænser det.
3. **Hvad værket ved**, når det byder.

Et balancetal skal derfor altid stå sammen med den budstrategi, det er regnet med. Ellers kan det ikke sammenlignes med noget.

---

## 2. Kort om markederne

Modellen dækker **opregulering fra forbrugssiden**. Det betyder, at elkedel og varmepumpe tilbyder at *stoppe* deres elforbrug, hvis Energinet kalder dem. Nedregulering og gasmotorens elproduktion er ikke med endnu.

Der er to indtægter:

| Indtægt | Hvad betales der for | Hvornår afgøres det |
|---|---|---|
| **Kapacitet** | At holde effekten klar i en given time | Auktion dagen før. Accepteres hvis kapacitetsprisen er mindst lige så høj som buddet |
| **Aktivering** | Den energi, der faktisk bliver reguleret | I driftsdøgnet, når Energinet har brug for den |

Der er to markeder, aFRR (automatisk, hurtig) og mFRR (manuel). Samme fysiske MW kan bydes ind i begge, men summen må ikke overstige det, enheden kan levere.

**Det fysiske krav:** For at kunne stoppe 5 MW elforbrug skal enheden *bruge* mindst 5 MW i den time. Et accepteret bud tvinger altså enheden til at køre, og den varme skal kunne afsættes, enten i nettet eller i tanken. Det er her, tanken får betydning for balancemarkedet.

---

## 3. De tre valg

### 3.1 Hvornår byder værket? (budprisen på kapacitet)

| Valgmulighed | Hvad det betyder i drift | YAML |
|---|---|---|
| **Fast budpris pr. marked** | Værket byder hver dag til samme pris, fx 100 kr./MW/h. Buddet går igennem i de timer, hvor kapacitetsprisen er højere | `reservation_gate:` med `cm_threshold_dkk_mw_h` |
| **Beregnet budpris** | Budprisen følger værkets alternativomkostning time for time: hvad det koster at køre elkedel/varmepumpe, minus hvad varmen ellers ville have kostet. Dyr gas på marginalen giver en højere budpris | `reservation_gate:` med `opportunity_cost: {reference_unit: …, floor_dkk_mw_h: …}` |
| **Ingen budpris** | Modellen byder i alle timer, hvor det kan betale sig. Kun til at finde en teoretisk øvre grænse | `reservation_gate: {enabled: false}` |

### 3.2 Hvor meget byder værket ind? (budstørrelsen)

Der er to principielt forskellige måder at fastlægge mængden på:

| Valgmulighed | Hvad det betyder i drift | YAML |
|---|---|---|
| **Fast blok, altid** | Værket melder samme mængde ind, hver gang buddet går igennem, uanset om det passer med driften. Modellen *skal* så køre enheden | `mode: driven` + `block_mw` |
| **Op til en blok** | Værket melder op til en fast mængde ind, og mindre når driften ikke kan bære det | `mode: bound` + `block_mw` |
| **Alt hvad fysikken tillader** | Ingen blok. Mængden bestemmes af, hvad enhederne kan og hvad prækvalificeringen tillader | `mode: bound` + `block_mw` = prækvalificeret effekt |

Uanset hvad der vælges ovenfor, gælder disse lofter altid, og det strammeste binder:

| Loft | Hvad det beskriver | YAML |
|---|---|---|
| **Pr. enhed** | Hvad enheden er prækvalificeret til, samlet over begge markeder | `ancillary_caps.per_unit_mw` |
| **Pr. enhed pr. marked** | Værkets egen fordeling mellem aFRR og mFRR | `ancillary_caps.per_unit_market_mw` |
| **Samlet for værket** | Den samlede prækvalificerede reservekapacitet pr. time | `ancillary_caps.total_mw` |
| **Gruppe** | Flere enheder, der er prækvalificeret samlet (fx to elkedler) | `ancillary_groups` |
| **Budvindue** | Måneder og timer, hvor enheden overhovedet byder, fx ikke elkedlen om sommeren | `ancillary.bid_window` på enheden |
| **Fra dato** | Enheden kan først byde fra idriftsættelsen | `ancillary.available_from` på enheden |
| **Månedsloft** | Det, værket faktisk har stillet til rådighed pr. måned. Beskriver adfærd og kræver egne afregningsdata | `balancing.availability` |

### 3.3 Hvad ved værket, når det byder? (beslutningsgrundlaget)

Kapacitetsbuddet afgives dagen før. Værket kender kapacitetsprisen, når auktionen er afgjort, men ikke hvornår eller hvor meget det bliver aktiveret. Hvis modellen kender aktiveringerne på forhånd, vælger den lige præcis de timer, hvor der kommer en prisspids, og så bliver tallet alt for højt.

| Valgmulighed | Hvad modellen ser, når den byder | Ser den ind i fremtiden? |
|---|---|---|
| `realized` | De faktiske aktiveringer | Ja, fuldt. Kun som øvre grænse |
| `profile` | Gennemsnit for kalendermåneden pr. time på døgnet | Delvist, resten af måneden |
| `trailing30` | Gennemsnit af de seneste 30 døgn pr. time på døgnet | Nej |
| `lag24` | Samme time i går | Nej |
| `lag168` | Samme time sidste uge | Nej |

Med `settle: realized` afregnes buddet bagefter på det, der faktisk skete: Modellen løses først på prognosen, reservationerne låses, og driften løses igen på de realiserede aktiveringer. Forskellen mellem de to løsninger viser, hvor meget prognosen lovede for meget (eller for lidt).

De to løsninger skrives begge ud: `Trin 1-objektiv (på prognose)` og `Objektiv` (afregnet på det realiserede).

### 3.4 Skal driften holde, hvis buddet ikke aktiveres?

En reserveret elkedel skal køre for at kunne stoppe. Modellen regner med den *forventede* aktivering, og uden en ekstra betingelse kan den lægge en plan, hvor elkedlen producerer mere varme, end nettet kan aftage, fordi aktiveringen forventes at fjerne forskellen. Udebliver aktiveringen, er der ingen steder at gøre af varmen.

Med `robust_reservation: true` skal driften også holde, hvis buddet *ikke* aktiveres: varmen fra de reserverede enheder skal kunne afsættes i nettet eller i tanken. Det er sådan, værkerne planlægger i dag, med og uden tank. Uden tank begrænser det, hvor meget værket kan byde om sommeren, og det er en del af tankens værdi i balancemarkedet. Indstillingen er standard, så den behøver ikke stå i casen.

| Valg | Betydning |
|---|---|
| `robust_reservation: true` (standard) | Driften holder med og uden aktivering. Anbefalet |
| `robust_reservation: false` | Driften holder kun med den forventede aktivering. Kun til sammenligning. Kan give "Modellen kan ikke løses" med `settle: realized` uden tank om sommeren |

### 3.5 Aktiveringsbuddet: jeres eget valg

Et accepteret kapacitetsbud forpligter værket til også at give et **aktiveringsbud**: den pris pr. MWh, værket vil have for at stoppe sit elforbrug, når Energinet kalder. Aktiveringsbuddet er en del af budstrategien, og værket fastsætter det selv. Modellen sætter det som spotprisen plus et tillæg.

| Valg | Valgmuligheder | YAML |
|---|---|---|
| **Aktiveringsbud** | Spotprisen plus et tillæg, som værket selv vælger. Modellen bruger 500 kr./MWh i alle cases, men det er en antagelse, ikke en regel. Højt tillæg: sjældnere kaldt, til en højere pris. Lavt tillæg: oftere kaldt, til en lavere pris | `bid_strategy.up_markup_dkk_mwh` |
| **Hvor meget aktiveres** | `clear`: hele buddet aktiveres, når prisen er over buddet. `system_share`: kun en andel, der følger, hvor meget af markedet der faktisk bliver kaldt (skaleret med k). `ramp`: andelen vokser, jo længere prisen ligger over buddet | `activation.afrr.model` / `activation.mfrr.model` |

**Hvor lavt må tillægget være?** Når værket stopper elkedlen eller varmepumpen, mangler varmen og skal laves på anden vis. Aktiveringen skal betale mere, end den varme koster. Det betyder mest for varmepumpen, der mister tre MWh varme for hver MWh el, den stopper, og i timer med lav spotpris, hvor spotprisen plus tillægget er lavt.

**Fast pris pr. enhed.** I praksis kan et værk også sætte aktiveringsbuddet som en fast pris for hver enhed, der svarer til, hvad varmen koster fra alternativet, fx biomassen. Kan alternativet ikke følge med, hæves prisen til gaskedlens marginalpris. Varmepumpen får en højere pris end elkedlen, fordi den mister mere varme for hver MWh el, den stopper. Modellen kan ikke det endnu. Den bruger spotprisen plus ét tillæg for alle enheder.

**Prøv jeres eget tillæg.** Sig til Claude: "vi byder energien til spotprisen plus 300 kr.", og bed om samme kørsel med jeres tillæg og med 500. Forskellen viser, hvad valget betyder. Kommandoen er `--set balancing.bid_strategy.up_markup_dkk_mwh=300`.

`clear` overvurderer aktiveret energi markant, når der ikke er et loft på mængden. For aFRR anbefales `system_share`. For mFRR, som afregnes til marginalpris, er `clear` et rimeligt udgangspunkt.

---

## 4. Seks budprofiler at vælge imellem

Profilerne er bygget, så de ligner måder, værker faktisk byder på. Find den, der ligner jeres praksis mest.

| # | Profil | Ligner det værk, der … | Budpris | Mængde | Bruges til |
|---|---|---|---|---|---|
| **0** | **Vi byder ikke** | ikke er prækvalificeret | – | – | Referencen. Alle balancetal er en differens til denne |
| **1** | **Fast melding** | melder samme mængde ind hver dag uden at se på prisen | Lav, fast (fx 50 kr./MW/h) | Fast blok, altid (`driven`) | Konservativt skøn for en simpel praksis |
| **2** | **Fast pris, fast mængde** | byder en fast mængde til en fast pris og lader auktionen afgøre | Fast pr. marked | Op til fast blok (`bound`) | Almindeligt udgangspunkt, når varmepumpen kan byde |
| **3** | **Fast pris, alt vi kan** | byder hele den prækvalificerede effekt til en fast pris | Fast pr. marked | Alt hvad fysikken tillader | Viser hvad værket kan, hvis det byder fuldt |
| **4** | **Beregnet pris** | regner sin budpris ud fra driften og brændslerne hver dag | Alternativomkostning | Op til fast blok eller alt | Et tal, der holder: værket byder kun, når det betaler sig |
| **5** | **Teoretisk loft** | – | Ingen | Alt hvad fysikken tillader | Kun som øvre grænse. Aldrig som forventning |

For alle profiler 1–4 anbefales:

- `foresight: trailing30` (eller `lag24`), så modellen ikke kender aktiveringerne på forhånd
- `settle: realized`, så tallet er det, værket faktisk ville have fået
- aFRR `system_share` med k = 4 og mFRR `clear` (Andeby-kalibreringen, marts–juni 2026)

Aktiveringsbuddet (spotprisen plus tillæg, afsnit 3.5) er det samme i alle profiler. **Profilerne adskiller sig kun på kapacitetsbuddet.**

**Kan kun elkedlen byde?** Har værket biomasse som alternativ, og er elkedlen den eneste enhed, der kan byde, så start med profil 4. At stå klar med elkedlen koster typisk mere, end kapacitetsprisen betaler (afsnit 4.3), og profil 2 kan derfor give et tab, selvom prognosen lover en gevinst. Det skete for et flisværk i generalprøven til kurset.

### 4.1 Sådan foregår en indmelding

Værket giver to bud med hver sin pris:

|  | Kapacitetsbud | Aktiveringsbud |
|---|---|---|
| **Pris for** | At stå klar | Den energi, der faktisk bliver kaldt |
| **Enhed** | kr. pr. MW pr. time | kr. pr. MWh |
| **Hvornår** | Dagen før, i en auktion | I driftsdøgnet: senest 45 minutter før kvarteret i mFRR og 25 minutter før i aFRR |
| **Betaling** | Når auktionens pris er mindst buddet. Værket får auktionens pris, ikke sit eget bud | I de kvarterer, hvor prisen for opregulering er mindst buddet |
| **I modellen** | Det, profilerne 1–5 handler om | Spotprisen plus tillæg, det samme i alle profiler |

**Frivillige bud.** Værket kan også give aktiveringsbud uden at have vundet kapacitet, med samme frister (45 minutter før kvarteret i mFRR, 25 i aFRR) og for den effekt, det alligevel kører med. Der er ingen betaling for at stå klar og ingen pligt til at køre. Modellen regner ikke på frivillige bud endnu. Den kan kun blive aktiveret gennem en reservation.

### 4.2 Én time, ét bud

Eksemplet bruger runde tal og ikke data fra Andeby eller Billund. Spotprisen i timen er 800 kr./MWh, tarif og elafgift er 150 kr./MWh, og alternativet til elvarmen er halm til 250 kr./MWh varme. Elkedlen giver 1 MWh varme pr. MWh el.

**Kapacitet.** Dagen før byder værket 3 MW aFRR til 100 kr./MW/h for timen 18–19. Auktionens pris bliver 240 kr./MW/h. Buddet er accepteret, og værket får 3 × 240 = **720 kr.** for timen, uanset om det bliver kaldt. Var prisen blevet 80 kr., var buddet afvist: 0 kr. og ingen forpligtelse.

**Forpligtelsen.** Elkedlen skal køre mindst 3 MW hele timen, og værket giver et aktiveringsbud på de 3 MW: spotprisen 800 + tillæg 500 = **1.300 kr./MWh**.

**Aktivering.** Prisen for opregulering i timens fire kvarterer:

| Kvarter | Pris for opregulering | Over buddet på 1.300? |
|---|---|---|
| 1 | 900 kr./MWh | Nej |
| 2 | 1.100 kr./MWh | Nej |
| 3 | 2.500 kr./MWh | Ja |
| 4 | 1.600 kr./MWh | Ja |

Hvor meget bliver kaldt? Kaldes hele buddet (`clear`), er det 3 MW i to kvarterer. Kaldes kun en andel (`system_share`, det realistiske for aFRR), følger andelen systemet: kaldte Energinet 10 % og 5 % af den indkøbte kapacitet, bliver det med k = 4 til 40 % og 20 % af de 3 MW.

| Timen 18–19 | Hele buddet kaldes | En andel kaldes |
|---|---|---|
| Kapacitetsbetaling | 720 kr. | 720 kr. |
| Kaldt energi | 1,5 MWh | 0,45 MWh |
| Aktiveringsbetaling | 0,75 × 2.500 + 0,75 × 1.600 = 3.075 kr. | 0,30 × 2.500 + 0,15 × 1.600 = 990 kr. |
| Sparet tarif og elafgift | 225 kr. | 68 kr. |
| Varme, der skal laves på anden vis | 1,5 MWh | 0,45 MWh |

Kapacitetsbetalingen er sikker, når buddet er accepteret. Aktiveringsbetalingen afhænger af, hvor meget der bliver kaldt, og den kendes først bagefter.

### 4.3 Hvad koster det at stå klar? (budprisen i profil 4)

For at kunne stoppe 1 MW skal værket bruge 1 MW el hele timen, også når det ikke kan betale sig. Prisen for at stå klar er elprisen med tarif og afgift minus det, varmen sparer på det billigste alternativ. Profil 4 byder kun, når kapacitetsprisen er højere.

| Enhed og alternativ | El pr. MW i timen | Varmen sparer | At stå klar koster | Byder ved 240 kr.? |
|---|---|---|---|---|
| Elkedel, halm til 250 | 950 kr. | 250 kr. | 700 kr./MW/h | Nej |
| Varmepumpe (COP 3), halm til 250 | 950 kr. | 750 kr. | 200 kr./MW/h | Ja |
| Varmepumpe (COP 3), gas til 600 | 950 kr. | 1.800 kr. | under 0, gulvet 50 kr./MW/h | Ja |

Derfor byder varmepumpen oftere end elkedlen, og oftest om vinteren, når gaskedlen er alternativet. Modellen finder alternativet som den ikke-elektriske enhed, der er på marginalen ved den aktuelle varmelast. Den bruger den faktiske spotpris, mens værket kun kender en prognose, når det byder.

### 4.4 Sådan regner modellen hver profil

| Profil | Hvornår reserveres der? | Hvor meget? |
|---|---|---|
| 0 | Aldrig. Kørsel uden balancemarkedet | – |
| 1 | Når kapacitetsprisen er mindst den lave faste budpris | Præcis blokken. Modellen skal køre enheden |
| 2 | Når kapacitetsprisen er mindst den faste budpris | Fra 0 op til blokken. Modellen vælger mængden ud fra driften |
| 3 | Som profil 2 | Op til hele den godkendte effekt |
| 4 | Når kapacitetsprisen er mindst prisen for at stå klar (4.3), time for time | Op til blokken |
| 5 | Altid, når det betaler sig | Alt. Modellen kender aktiveringerne |

Profil 1–4 regnes i to trin:

- **Trin 1, det prognosen lovede.** Reservationen besluttes på en prognose for aktiveringen: gennemsnittet af samme time de seneste 30 døgn.
- **Trin 2, det den gav.** Reservationen låses, og driften regnes igen på det, der faktisk blev kaldt.
Driften skal altid kunne holde, også hvis buddet ikke bliver kaldt. Modellen er stadig optimistisk på to punkter: den kender spotprisen, og i profil 2–4 vælger den mængden, efter at kapacitetsprisen er kendt. Et værk må vælge mængden, før prisen kendes.


---

## 5. Færdige YAML-blokke

Blokkene indsættes i casefilen under den eksisterende konfiguration. Bed Claude om at gøre det, og om at sætte `afrr_qualified: true` / `mfrr_qualified: true` på de enheder, der er prækvalificeret. Tallene er eksempler og skal erstattes med værkets egne.

**Enhedsnavnene skal være værkets egne.** `vp_luft_vand` nedenfor er Andebys navn. Hedder varmepumpen `varmepumpe` i jeres case, skal der stå det. Står der et navn, casen ikke kender, stopper modellen og viser de gyldige navne.

### Fælles del (alle profiler)

```yaml
balancing:
  method: activation_value
  bid_strategy:
    up_markup_dkk_mwh: 500          # aktiveringsbud = spot + 500 kr./MWh
  ancillary_caps:
    per_unit_mw:
      vp_luft_vand: 6.0             # prækvalificeret eloptag pr. enhed
    total_mw: 14.0                  # samlet prækvalificeret kapacitet
  # robust_reservation: true er standard og behøver ikke stå her
  activation:
    foresight: trailing30
    settle: realized
    afrr: {model: system_share, k: 4.0}
    mfrr: {model: clear}
```

### Profil 1 · Fast melding

```yaml
  reservation_gate:
    enabled: true
    mode: driven                    # blokken meldes ind, hver gang buddet går igennem
    # aFRR-blok + mFRR-blok må tilsammen IKKE overstige det, enhederne kan
    # bruge af el på samme tid. Ellers kan modellen ikke løses.
    # Andeby: varmepumpe + elkedel kan bruge ca. 5 MW el, så 2 + 3 MW.
    afrr: {cm_threshold_dkk_mw_h: 50, block_mw: 2.0}
    mfrr: {cm_threshold_dkk_mw_h: 50, block_mw: 3.0}
```

### Profil 2 · Fast pris, fast mængde

```yaml
  reservation_gate:
    enabled: true
    mode: bound                     # op til blokken
    afrr: {cm_threshold_dkk_mw_h: 100, block_mw: 3.0}
    mfrr: {cm_threshold_dkk_mw_h: 250, block_mw: 4.0}
```

### Profil 3 · Fast pris, alt vi kan

```yaml
  reservation_gate:
    enabled: true
    mode: bound
    afrr: {cm_threshold_dkk_mw_h: 100, block_mw: 14.0}   # blok = total_mw
    mfrr: {cm_threshold_dkk_mw_h: 250, block_mw: 14.0}
```

### Profil 4 · Beregnet pris

```yaml
  reservation_gate:
    enabled: true
    mode: bound
    afrr:
      opportunity_cost: {reference_unit: vp_luft_vand, floor_dkk_mw_h: 50}
      block_mw: 3.0
    mfrr:
      opportunity_cost: {reference_unit: vp_luft_vand, floor_dkk_mw_h: 50}
      block_mw: 4.0
```

### Profil 5 · Teoretisk loft

```yaml
  reservation_gate:
    enabled: false
  # og i activation-blokken: foresight: realized
```

### Valgfrit: budvindue på en enhed

```yaml
units:
  elkedel:
    ancillary:
      afrr_qualified: true
      mfrr_qualified: true
      bid_window: {months: [10, 11, 12, 1, 2, 3], hours_local: [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]}
```

---

## 6. Prøv det på Andeby

Et vindue på 12 dage med balancering løser på få sekunder. Fire kørsler viser forskellen på, hvad modellen ved, når den byder:

```bash
W="cases/andeby.yaml --data-source github --start 2026-01-05 --end 2026-01-16"

python run_case.py $W                                    # (1) uden balance
python run_case.py $W --with-balancing \
    --set balancing.activation.foresight=realized        # (2) byd frit, kender aktiveringerne
python run_case.py $W --with-balancing \
    --set balancing.activation.foresight=trailing30 \
    --set balancing.activation.settle=realized           # (3) byd frit, prognose
python run_case.py $W --with-balancing \
    --set balancing.activation.foresight=trailing30 \
    --set balancing.activation.settle=realized \
    --set balancing.reservation_gate.enabled=true        # (4) beregnet budpris, prognose
```

Kontroltal (19. oktober 2026, robust reservation som standard, lagerbalancen rettet i første time, aktiveringsværdien uden spotpris):

| Kørsel | Prognosen lovede | Afregnet på det realiserede | Balancens værdi |
|---|---:|---:|---:|
| (1) Uden balance | – | 3.446.712 kr. | – |
| (2) Byd frit, kender aktiveringerne | – | 3.025.301 kr. | 421.000 kr. |
| (3) Byd frit, prognose | 2.932.972 kr. | 3.231.194 kr. | 216.000 kr. |
| (4) Beregnet budpris, prognose | 3.303.953 kr. | 3.319.185 kr. | 128.000 kr. |

(2) er et loft, ingen kan nå. (3) lover mest, men skuffer mest: modellen kører elkedlen for at fange aktiveringer, der ikke kommer. (4) lover mindre, men holder.

### På dit eget værk

Bed Claude om at læse denne fil, sætte den fælles blok og en profil ind i din case med dine egne enhedsnavne og din prækvalificerede effekt, og køre et kort vindue med og uden `--with-balancing`. Typiske beskeder:

- **"findes ikke i casen"**: et enhedsnavn i blokken passer ikke. Beskeden viser de gyldige navne.
- **"Modellen kan ikke løses"**: typisk profil 1, hvor aFRR- og mFRR-blokken tilsammen er større end enhedernes eleffekt. Gør blokkene mindre, eller brug profil 2. Profil 1 uden tank om sommeren kan også være uløselig: den faste blok tvinger enhederne til at køre, og varmen kan ikke afsættes, når buddet ikke aktiveres. Brug profil 2 uden tank.
- **Profil 4 giver 0 kr.**: værkets alternativomkostning ligger over kapacitetsprisen i vinduet. Det er ikke en fejl.
- **Et kort vindue kan ikke ganges op til et år.** Brug det til at sammenligne profiler.

---

## 7. Sådan læses resultatet

- **Balancens værdi er altid en differens:** samme case og periode, kørt med og uden `--with-balancing`. Brug `--mip-gap 0.0002`.
- **Tankens værdi i balancemarkedet** findes ved at køre balancekørslen med og uden tanken (`--disable <tanknavn>`) og sammenligne med samme par uden balance. Er de to tankværdier ens, begrænser budstrategien mængden så meget, at tanken ikke kommer i spil.
- **Er årsomkostningen negativ, er noget forkert.** Det betyder næsten altid, at modellen kender aktiveringerne på forhånd (`foresight: realized`) eller aktiverer hele buddet hver gang (`clear` uden loft).
- **Se på timefilen.** Kører elkedlen fuldt i timer med lav varmelast og høj spotpris, så byder modellen efter prisspidser, den ikke kunne kende.
- **Sammenlign med jeres egen afregning,** pr. måned og pr. marked. Ligger modellen langt over, er det oftest mængden, ikke prisen, der er forkert.

---

## 8. Hvad der ikke er med

**Ikke med i modellen:**
- Nedregulering og gasmotorens elproduktion i balancemarkedet
- Risikoen for, at et accepteret bud ikke kan leveres (havari, afrimning af varmepumpe, netbegrænsninger). Brug budvindue eller månedsloft til at beskrive det
- Prisvirkning af værkets egne bud. Modellen antager, at værket ikke flytter prisen
- Kapacitetsprisen kendes stadig på forhånd i modellen, og spotprisen kendes, når timerne vælges
- Frivillige aktiveringsbud uden kapacitet. Modellen bliver kun aktiveret gennem en reservation
- Aktiveringsbud som fast pris pr. enhed. Modellen bruger spotprisen plus ét tillæg for alle enheder
