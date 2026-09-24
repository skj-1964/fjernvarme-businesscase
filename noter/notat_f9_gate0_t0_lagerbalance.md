# F9 Gate 0 — t=0's ubundne lagerbalance

**Status:** Read-only kortlægning. **Intet skrevet i `src/` eller `tests/`,
ingen rettelse foreslået valgt.** Fjorten målekørsler, alle til en engangsmappe
uden for repoet.
**Forudsætning:** [F1b+F1c](notat_f1bc_akse_og_rapport.md) §1c og §6 — den
efterlod defekten åben i `model.py` og navngav den.
**Modelrepo:** HEAD `8fe528a`, rent arbejdstræ.
**df-data-klon:** `6c95bde` (2026-08-07), urørt før og efter.
**Dato:** 2026-08-09

**Hovedfund, i rækkefølge efter hvad de ændrer:**

1. **Mekanismen skal navngives præcist.** `discharge[0]` er **ikke** ubundet —
   den står i `heat_balance[0]`. Den mangler i **energiregnskabet**. En
   rettelse der binder variablen "fordi den er fri" rammer ved siden af.
2. **Biasset er bevisbart ensrettet.** Δobjektiv ≥ 0 med nødvendighed, ikke
   kun målt. Optimeringen kan aldrig overvurdere omkostningen ved t=0.
3. **Størrelsen er uafhængig af `e_initial`.** Ved tom tank leverer tanken
   stadig hele timens varme. Målt til øren på fire beholdninger.
4. **0,02 % er ikke en konstant.** Den absolutte fejl er én times
   omkostning uanset horisont; andelen skalerer omvendt med horisonten:
   0,02 % over to måneder, 1,75 % over tre døgn.
5. **Et selvstændigt fund i samme klasse:** `uc_minup_fliskedel` binder
   **nul** variable på horisonter under 168 timer, og er uhåndhævet i den
   første uge af enhver kørsel.

---

# 1. DEL A — BINDINGEN

## 1.1 Energibalance-constrainten (A1)

To constraints hedder noget med balance. Forskellen er hele sagen, så begge
gengives.

**`build_model()` i `src/model.py`, blok [2] "Lagerdynamik":**

```python
        e_prev = storage_energy.shift(time=1)
        dyn = storage_energy - (1 - delta) * e_prev - charge + discharge
        m.add_constraints(
            dyn.sel(time=time_coord[1:]) == 0,
            name="storage_dynamics",
        )
```

Indekset er `time_coord[1:]` — **t = 1 … T−1**. t=0 er ude.

**Samme funktion, blok [1] "Varmebalance":**

```python
        m.add_constraints(
            prod_side + discharge.sum("storage") - charge.sum("storage")
            == data["heat_demand"],
            name="heat_balance",
        )
```

Ingen `.sel(time=…)`. Den løber over **hele aksen, t = 0 … T−1**.

**Linjenumre:** `dyn.sel(...)` står på linje 234 og `storage_initial` på
243–246 pr. `8fe528a`. De var ikke driftet siden F1c. Der henvises alligevel
til funktionsnavne herefter — numrene skal ikke bæres videre.

## 1.2 Variable på t=0 og hvad der binder dem (A2)

Målt strukturelt: for hver variabelblok er labels ved t=0 slået op i **hver**
constraint-bloks variabelliste. Case `billund_sporB_q1_2026`, balancing + UC
aktivt, t₀ = 2026-01-01 02:00.

| variabel @ t=0 | constraints der rører den |
|---|---|
| `heat_prod` | uc_minload/maxload (flis, halm), r_up_footroom (elkedel_gl, vp), **heat_balance** |
| `storage_energy` | **storage_dynamics** (som `e_prev` for t=1), **storage_initial** |
| **`charge`** | **heat_balance — og intet andet** |
| **`discharge`** | **heat_balance — og intet andet** |
| `commit` | uc_state_transition, uc_initial_u, uc_minload/maxload |
| `startup` | uc_initial_v, uc_startup_shutdown_excl, uc_minup_halmkedel |
| `shutdown` | uc_initial_w, uc_startup_shutdown_excl, uc_mindown (flis, halm) |
| `r_afrr_*`, `r_mfrr_*` | footroom, per_unit_cap, shared_reserve_cap, gate_driven, heat_balance |

**Ingen variabel er helt uden constraint.** Fejlen er skarpere end "ubundet":
`discharge[0]` leverer MWh til nettet **uden at trække dem fra nogen
beholdning**. Den står i varmebalancen og mangler i energiregnskabet.

Tællingen bekræfter det uafhængigt: `storage_dynamics` rører 496 distinkte
variable på en 166-timers akse = 166 `storage_energy` + 165 `charge` + 165
`discharge`. De to manglende er `charge[0]` og `discharge[0]`.

## 1.3 Er `storage_energy[0]` pinnet? (A3)

Ja. **`build_model()`, umiddelbart efter `storage_dynamics`:**

```python
        # Startbetingelse: e[t=0] = e_initial
        e_init = xr.DataArray(
            [cfg.storage[s].e_initial_mwh for s in storage_names],
            coords={"storage": storage_names}, dims="storage",
        )
        m.add_constraints(
            storage_energy.sel(time=time_coord[0]) == e_init,
            name="storage_initial",
        )
```

Pinningen er præcis **halvdelen** af en startbetingelse: den binder
*niveauet* ved t=0, men ikke *strømmene* ved t=0. De to hører sammen, og kun
den ene blev skrevet.

## 1.4 Samme fejlklasse andre steder (A4)

Første metode spurgte "optræder variablen i mindst én constraint?". Den gav
"OK" på alt, inklusive `discharge[0]`, fordi den står i varmebalancen.
Spørgsmålet var forkert stillet. Metoden blev skrevet om til: **for hver
constraint-blok, hvilke tidsindekser dækker den, sammenholdt med den fulde
akse.** Kørt på både en kort (166 t) og en lang (1401 t) akse.

**Seks blokke ud af 23 dækker ikke hele aksen:**

| blok | mangler | kompenseret? |
|---|---|---|
| `storage_dynamics` | t=0 | **NEJ** — `storage_initial` pinner kun niveauet |
| `uc_state_transition` | t=0 | **JA** — `uc_initial_u/v/w` pinner alle tre variable |
| `uc_minup_fliskedel` | de første **167** skridt (UT=168) | delvist |
| `uc_mindown_fliskedel` | de første 5 (DT=6) | delvist |
| `uc_minup_halmkedel` | de første 3 (UT=4) | delvist |
| `uc_mindown_halmkedel` | de første 5 (DT=6) | delvist |

**Kontrasten er pointen.** UC-modulet gør ved t=0 præcis det lagermodulet
undlader: det pinner *alle* variable på t=0, ikke kun én. Rettelsens form
findes allerede i repoet, i nabomodulet.

**Selvstændigt fund, samme klasse, anden virkning:** `uc_minup_fliskedel` er
**tom** på horisonter under 168 timer. `valid = time_coord[UT-1:]` bliver en
tom liste, `add_constraints` accepterer den lydløst, og blokken binder nul
variable. Målt: **0** variable på 166-timers aksen, **1234** på 1401-timers
aksen. Fliskedlens Billund-bekræftede min-uptime på én uge er derfor slet
ikke håndhævet i den første uge af nogen kørsel, og slet ikke i kørsler
kortere end en uge. Det er ikke gratis energi — `v`/`w` er stadig bundet af
tilstandsovergangen — men det er et loft der forsvinder uden en lyd.

De tre øvrige er dokumenterede randafslapninger ("Constraint håndhæves kun
hvor alle shifts er defineret") uden historik at binde imod. Et valg, ikke en
fejl.

---

# 2. DEL B — OMFANGET, MÅLT

**Metode.** Modellen bygges to gange på **identiske** data: én gang som HEAD,
én gang med `charge[0] == 0` og `discharge[0] == 0` lagt oveni **i
hukommelsen**. Forskellen på de to objektiver *er* biasset. Intet i repoet
blev rørt.

**Aksevalg.** Fuld dækning krævede at lægge aksen uden om klonens huller:
`dmi/fyn_2026` starter først 01-01 kl. 02 og mangler 2026-02-28 11:00 →
03-01 15:00 (29 timer). Fulddækkede vinduer i 2026: **A** 01-01 02:00 →
02-28 10:00, **B** 03-01 16:00 → 06-27 21:00.

## 2.1 Aflæsning ved t=0 (B1)

`billund_sporB_q1_2026`, balancing, `--heat-csv`, vindue A, 1401 timer:

| størrelse | værdi |
|---|---|
| `heat_demand[0]` | **22,517 MW** |
| `heat_prod[0]` i alt | **6,500 MW** |
| — fliskedel | 2,500 MW (= `p_min_heat`) |
| — halmkedel | 4,000 MW (= `p_min_heat`) |
| — vp, elkedel_gl, gasmotor, gaskedel | 0 |
| `storage_energy[0]` | **279,0 MWh** (= `e_initial`, uændret) |
| `charge[0]` | **0,0 MW** |
| `discharge[0]` | **16,0167 MW** |
| `storage_net[0]` | **−16,0167 MW** |
| `spot[0]` | 75,29 DKK/MWh |

Identiteten holder i **alle fjorten** kørsler:
**`discharge[0] = heat_demand[0] − heat_prod[0]`**. Tanken dækker præcis
resten, hver gang.

De 6,5 MW er ikke en dispatch-beslutning: det er UC-min-last, tvunget frem af
`uc_initial_u` med `initial_status: 1` på begge kedler. Alt derudover tages
gratis fra tanken. Det er samme 6,5 MW som F1c målte, og som afkræftede den
oprindelige `heat_prod[0] = 0`-begrundelse.

## 2.2 Bidraget til objektivet (B2)

To tal, ikke ét.

**(a) Hvad t=0 koster i objektivet.** 1 568 DKK af 11 435 132 = **0,0137 %**.
I LP-kørslerne (UC slået fra) producerer t=0 **ingenting** — hele timen
dækkes fra tanken — så t=0 bidrager med **0,00 DKK**. En hel time varme,
gratis.

**(b) Hvad fejlen koster — det egentlige tal.** LP, exakte objektiver:

| kørsel | timer | Δobjektiv (DKK) | andel | gratis MWh | implicit DKK/MWh |
|---|---|---|---|---|---|
| LP-a vinter (vindue A) | 1401 | 2 847,55 | +0,0232 % | 22,52 | 126,46 |
| LP-b forår (vindue B) | 1440 | 4 415,40 | +0,0904 % | 18,30 | 241,28 |
| LP-c sommer (vindue B) | 552 | 2 081,40 | +0,3833 % | 8,70 | 239,24 |
| LP-d dyreste time | 76 | 769,70 | +1,7544 % | 3,23 | **238,30** |

Den implicitte pris er ikke et frit tal: **238,30 DKK/MWh er fliskedlens
marginalomkostning på øren**, 241,28 er halmkedlens, 126,46 er en blanding.
Fejlen er nøjagtigt "den time varme som den marginale enhed ellers skulle
have leveret".

**Om de 0,02 %.** Tallet holder som størrelsesorden for en lang vinterkørsel
(målt 0,0232 % LP / 0,0129 % MILP). Men det er **ikke en konstant**. Den
absolutte fejl er én times omkostning uanset horisontens længde, så andelen
skalerer omvendt med horisonten. Et tal at citere er det ikke.

## 2.3 Er fortegnet altid opad? (B3)

**Ja — og det er bevisbart, ikke kun målt.** At tilføje
`charge[0] = discharge[0] = 0` fjerner frihedsgrader fra et
minimeringsproblem. Optimumet kan derfor kun stige eller stå stille.
**Δ ≥ 0 med nødvendighed.** t=0 kan aldrig trække objektivet ned; den kan kun
undervurdere omkostningen. Målt i alle fjorten kørsler: Δ mellem +453,76 og
+112 981,34 DKK, aldrig negativ.

**"Systematisk" og "retningsbestemt" er dog ikke det samme.** Objektivets
fortegn er låst. *Dispatchens* er ikke:

* Fire perioder kørt — vinter uden negative priser; forår med 61 negative
  timer; sommer med 25; samt en akse der **starter** i en time med spot
  −60,45 DKK/MWh. I alle fire: `charge[0] = 0`, `discharge[0] > 0`. Ingen
  enhed havde negativ marginalomkostning ved t=0, heller ikke ved spot −60,
  fordi tarif og afgift løfter elkedlens mc til +75,3.
* **Den anden fejlmåde findes.** I den dyreste time i klonen
  (2026-06-24 18:00, spot ≈ 4 376–5 203 DKK/MWh) er gasmotorens mc
  **−1 417,3 DKK/MWh**. Med gasmotorens loft hævet 2,8 → 50 MW
  (**syntetisk sonde — ikke en driftsrealistisk case**):

  ```
  heat_prod[0] = 50,00   charge[0] = 60,00   discharge[0] = 16,03
  storage_net[0] = +43,97      storage_energy[0] = 279,0 (uændret)
  ```

  Begge variable er positive samtidig. Modellen producerer 50 MW til negativ
  pris, hælder 60 MW i en tank der ikke fyldes, og trækker samtidig 16 MW ud
  af en tank der ikke tømmes, for at få varmebalancen på 6,03 MW til at gå
  op. Δ = 62 317 DKK = **22 % af objektivet**. LP'en er degenereret ved t=0,
  fordi to frie slack-variable står i samme ligning.

  Med ægte parametre (`LP-d`) forbliver `charge[0] = 0`, fordi gasmotorens
  2,8 MW er mindre end timens behov på 6,03 MW. Fejlmåden kræver at
  kapacitet med mc < 0 overstiger varmebehovet ved t=0 — sjældent i Billunds
  flåde, ikke umuligt i en anden.

## 2.4 Afhænger størrelsen af `e_initial`? (B4)

**Nej. Ikke det mindste.** Fire værdier, vindue A, LP:

| `e_initial` (MWh) | `storage_energy[0]` | `discharge[0]` | Δobjektiv (DKK) |
|---|---|---|---|
| 0 (tom) | −0,0 | 22,5167 | **2 847,55** |
| 139,5 | 139,5 | 22,5167 | **2 847,55** |
| 279 (halv) | 279,0 | 22,5167 | **2 847,55** |
| 558 (fuld) | 558,0 | 22,5167 | **2 847,55** |

Identisk til øren. **Ved `e_initial = 0` leverer den tomme tank 22,517 MWh
varme.** Beholdningen indgår ikke i regnestykket, så dens værdi kan ikke
påvirke det. Biasset styres af `heat_demand[0]`, af `p_max_discharge_mw`, og
af marginalomkostningen hos den enhed der ellers skulle have leveret — af
intet andet.

---

# 3. DEL C — HVAD EN RETTELSE VILLE KOSTE

Forslag, ikke valg.

## 3.1 Tre mulige rettelser (C1)

### C1a — udvid constrainten til at dække t=0

Kræver en **prætilstand**: `e₋₁ := e_initial`, hvorefter dynamikken kører fra
t=0 med `e[0] = (1−δ)·e_initial + charge[0] − discharge[0]`.
`storage_initial` skal så **fjernes eller omskrives**: den pinner i dag `e[0]`
og ville gøre systemet overbestemt — to ligninger om `e[0]` der kun kan
opfyldes samtidig hvis `charge[0] = discharge[0]`.

*Frihedsgrader ved t=0:* bevaret og fysisk korrekte.
*Pris:* `e_initial` skifter betydning fra "beholdning ved t=0" til "beholdning
ved t=−1". Cyklusbindingen `e[T−1] == e_initial` sammenligner derefter to
forskellige tidspunkters begreb og skal gennemtænkes med.

### C1b — bind `discharge[0] = charge[0] = 0`

To linjer, ingen semantiske følger. Præcis det der er målt hele vejen
igennem, så virkningen er kendt til øren.

*Frihedsgrader ved t=0:* væk. Tanken er låst i første time.
*Pris:* én times lagerfleksibilitet ud af N — 0,07 % af en 1401-timers
horisont. Modellen bliver en anelse for stram i stedet for løs, altså fejler i
den **rigtige** retning, men med samme absolutte størrelse.

### C1c — lad aksen begynde ét skridt før den rapporterede periode

Modellen kører på [t₋₁, T], rapporten dækker [t₀, T]. Defekten lander på en
opvarmningstime der aldrig vises.

*Frihedsgrader ved t=0 (den rapporterede):* fuldt bevarede og korrekte — t₀ er
nu et indre punkt.
*Pris:* den dyreste. Datalaget skal hente ét skridt mere end brugeren bad om,
og dækningsvagten skal acceptere det. Klonen starter 2026-01-01 02:00 for DMI,
så en kørsel der beder om netop den første dækkede time kan ikke bygges. Og
objektivet indeholder **stadig** den ubundne time; den er blot skjult for
rapporten — den nuværende tilstand med et ekstra trin.

**Bemærkning uden anbefaling:** C1b og C1c fjerner symptomet; kun C1a fjerner
årsagen. C1a er den eneste der efterlader modellen med et energiregnskab der
er komplet på hele sin egen akse.

## 3.2 Hvad sker der med `reporting.py`'s `iloc[1:]`? (C2)

| rettelse | droppet bliver |
|---|---|
| **C1a** | **forkert.** t=0 er nu en fysisk gyldig dispatch-time med korrekt regnskab. Droppet kaster en rigtig time væk og gør rapporten uenig med objektivet i modsat retning af i dag. Kontrakten skal skifte til N. |
| **C1b** | **overflødigt, ikke forkert.** t=0 er gyldig men triviel. Beslutningen bliver kosmetisk — og skal træffes bevidst, ikke arves. |
| **C1c** | **præcis rigtigt, og for første gang selvforklarende.** Den ekstra time modellen fik lagt foran *er* den time rapporten dropper. Begrundelsen ville stå i koden i stedet for i en docstring. |

Under alle tre bliver docstringens begrundelse forældet. Den er i dag korrekt,
grundig og målt, og den skal skrives om i **samme** commit som rettelsen —
ellers efterlader den en forklaring på en fejl der ikke længere findes.

## 3.3 Hvilke eksisterende tests ville fejle? (C3 — læst, ikke kørt)

Kun **én** test i hele suiten rører kontrakten:
`tests/test_time_axis.py::test_hourly_csv_contract_is_n_minus_one`.

```python
    assert len(df) == n - 1, "kontrakten er N−1, ikke N"
    assert df["timestamp"].iloc[0] == idx[1], "første række skal være idx[1]"
    assert df["timestamp"].iloc[-1] == idx[-1], "sidste række skal være idx[-1]"
    assert idx[0] not in set(df["timestamp"]), "t=0 skal være droppet"
```

* **C1a:** fejler på alle fire assertions, hvis droppet fjernes samtidig. Skal
  skrives om, ikke lappes.
* **C1b:** **består uændret.** Testen bygger aldrig modellen — den kalder
  `write_hourly_csv` med en håndlavet `_Cfg` hvor `storage = {}`. Den ser
  ikke lageret.
* **C1c:** **består uændret**, af samme grund.

Testens *docstring* bliver forkert under alle tre; den citerer `model.py:234`
og "charge/discharge[0] er ubundet". Under C1b og C1c fejler testen ikke, men
håndhæver derefter en kontrakt hvis begrundelse er ophørt med at gælde. **Det
er det farligste af de tre udfald, fordi ingenting lyser rødt.**

Ingen anden test i `tests/` bygger en model, kalder `build_model`, eller rører
`storage_*`. `test_coverage_guard*` og `test_schema_v2_mapping` er upåvirkede.

---

# 4. DEL D — TESTEN (beskrevet, ikke skrevet)

## 4.1 Beskrivelse (D1)

**Primær: strukturel test, uden solver.** Byg modellen på en minimal case med
mindst ét aktivt lager og en kort akse. Hent
`m.constraints["storage_dynamics"].vars` og labels for `charge[:, t₀]` /
`discharge[:, t₀]`. Assertér at de to labelmængder **er indeholdt** i
lagerdynamikkens variabelmængde.

* I dag: de er det ikke → **fejler deterministisk**.
* Efter C1a: de er det → består.
* Efter C1b: variablene er stadig ude af `storage_dynamics`, men bundet til
  nul af en ny navngiven constraint. Testen skal da formuleres som
  "`charge[0]` og `discharge[0]` optræder i mindst én constraint **ud over**
  `heat_balance`", hvilket dækker begge rettelser.
* Efter C1c: består, fordi den rapporterede t₀ ikke længere er aksens første
  skridt.

**Sekundær: adfærdstest med solver.** Byg en case hvor alle enheder er dyre og
`heat_demand[0] > 0`, løs, og assertér energi-identiteten ved t=0:

```
storage_energy[0] == (1−δ)·e_initial + charge[0] − discharge[0]
```

I dag: venstre side 279,0, højre side 279,0 − 16,0167 = 262,98. Fejler.

## 4.2 Hvorfor den ikke kan bestå ved et tilfælde (D2)

**Den strukturelle test asserterer en mængdeindeslutning i modellens egen
datastruktur.** Ingen tolerance, ingen solver, ingen priser, ingen data,
intet optimeringsforløb. Mængden af variabellabels i en constraint-blok er en
deterministisk funktion af aksen og af den kode der byggede blokken. Den
eneste måde at få testen til at bestå er at lade `charge[0]`/`discharge[0]`
faktisk indgå i en binding ud over varmebalancen. Et heldigt talsammenfald
findes ikke, fordi der ikke indgår tal.

**Adfærdstesten kan derimod bestå ved et tilfælde** — hvis
`heat_demand[0] = 0`, eller hvis en enhed er gratis, bliver
`discharge[0] = 0` af sig selv og identiteten holder trivielt. Den skal derfor
bygges med eksplicitte forudsætnings-asserts (`heat_demand[0] > 0` og
`min(mc) > 0`) før hovedassertionen, ellers måler den ingenting den dag casen
ændres.

**Derfor må testen ikke måle objektivet.** Det er ikke kun principielt:
MILP-kørslerne løses med `mip_rel_gap = 0.005` og `mip_abs_gap = 5000 DKK`.
Alle fem MILP-målinger har Δ mellem 454 og 2 848 DKK — **under solverens egen
absolutte gap-tolerance**. En objektivbaseret test ville bestå eller fejle
efter hvilken node HiGHS tilfældigvis stoppede i. Det er den konkrete grund
til at hele B-serien blev gentaget som ren LP.

---

# 5. USIKKERT

**Prompten var upræcis ét sted, og det ændrer hvor en rettelse skal lande.**
"Ved t=0 er `discharge[0]` derfor ubundet" — den er bundet, af
`heat_balance[0]`. Det ubundne er koblingen til energiregnskabet. En rettelse
der binder `discharge[0]` "fordi den er fri" kunne ende med at røre
varmebalancen, hvor der ikke er noget galt. Der blev ikke stoppet på det,
fordi konklusionen og retningen i prompten er rigtige — kun mekanismen skulle
skærpes.

**`storage_net[0] = −13,098` reproduceres ikke.** F1c's kørsel starter
2026-01-01 00:00, som dækningsvagten i dag afviser (DMI/fyn begynder 02:00).
Vinterkørslerne her starter 02:00 og giver −16,0167. Samme mekanisme, andet
tal. Om de −13,098 stammer fra en akse før vagten blev indført eller fra
andre flag, er ikke afgjort.

**Én kørsel udeblev.** `B3e` — sporB-casen med start i den dyreste time, uden
`--heat-csv` — blev **infeasible** og gav ingen måling. Formodningen er at
`reservation_gate` i `driven`-mode tvinger en reservation som
footroom-constrainten ikke kan honorere ved sommerens lave varmebehov, men det
er ikke isoleret. Rapporteret som **udeblevet, ikke som nul**. Sonden blev i
stedet lavet på `billund_baseline` (`B3f`) og på sporB med hævet gasmotorloft
(`B3h`).

**`B3h` er syntetisk.** Gasmotorens `p_max_heat` er hævet 2,8 → 50 MW for at
fremkalde `charge[0] > 0`. Tallene derfra siger noget om *modellens* opførsel,
intet om Billund.

**Ikke afgjort:** om `uc_minup_fliskedel`-fundet (tom constraint under 168
timers horisont, uhåndhævet i første uge) har påvirket nogen af de kørsler der
ligger til grund for capture-rate-arbejdet. Det kræver en gennemgang af hvilke
horisonter der faktisk er kørt, og ligger uden for denne gate.

**Ikke besluttet:** hvilken rettelse. Gate 0 kortlægger; valget hører i næste
gate.
