# Varmepumpe, varmelast og nettab

---

## Varmepumpens ydelse — `cop_curve`

En luft/vand-varmepumpe leverer mindre varme, når det er koldt. Modellen kan
beskrive det på to måder, valgt pr. enhed i casen.

**`type: table` — målt ydelse (anbefalet).** Punkter med udetemperatur, varme
og eloptag ved fuld last. Varme og el interpoleres hver for sig, COP er
`varme(T) / el(T)`, og uden for punkterne holdes yderværdien.

```yaml
cop_curve:
  type: table
  points:
    - { t_ambient: -10.0, heat_mw: 12.0, el_mw: 5.0 }   # COP 2,40
    - { t_ambient:   0.0, heat_mw: 16.0, el_mw: 5.5 }   # COP 2,91
    - { t_ambient:  16.0, heat_mw: 21.0, el_mw: 6.2 }   # COP 3,39
```

- Varmeloftet følger udetemperaturen time for time. `p_max_heat` gælder
  ovenpå som ekstra loft; sæt det til tabellens største varme, medmindre noget
  andet end varmepumpen selv begrænser ydelsen.
- Reservationsloftet i balancemarkedet er tabellens største eloptag.
- Mindst to punkter, gerne tre (omkring −10 °C, 0 °C og +15 °C).
- Punkterne er *udetemperatur*. Har du kun data mod fremløbs- eller
  kildetemperatur (fx en borehulsvarmepumpe), så brug en fast COP i stedet.

**`type: linear` — COP ved 0 °C.** Kun når der ikke findes målepunkter. COP
stiger lineært med udetemperaturen (mellem 1,8 og 4,0), og varmeloftet er fast
hele året. Det giver størst eloptag i frost, det omvendte af en luft/vand-
varmepumpe, så tallene er mindre præcise.

Billund-casene bruger værkets målte ydelse. Det flyttede Spor A-ankeret fra
5,19 til 4,70 mio. kr.

---

## Målt varmelast eller syntese

Den sikreste varmelast er målt: timeværdier ab værk givet med `--heat-csv`.
Sådan kører deltagercases fra regnearket og Billund-casene.

Uden `--heat-csv` syntetiseres varmelasten af DMI-temperaturen med parametrene
i casens `heat_load_params`. Det bruges af Andeby og af værker, der kun har
årsproduktionen.

### Rekalibrér syntesen

`scripts/calibrate_heat_load.py` genfitter `heat_load_params` mod målt
varmeproduktion og en DMI-station (mindste kvadraters metode) og skriver en
YAML, der kan bruges direkte med `run_case.py --heat-params`. Perioden tages fra
den målte fil, medmindre `--start`/`--end` er givet.

```bash
# Dit eget værks måling
python scripts/calibrate_heat_load.py \
    --measured deltagere/data/<navn>_abvaerk_hourly.csv \
    --measured-col heat_mw_abvaerk \
    --dmi-area karup --data-source github \
    --thermal-inertia 48 \
    --output deltagere/cases/heat_load_params_<navn>.yaml

# Usikker på den termiske inerti? Søg over flere, og den med højest R² vælges
python scripts/calibrate_heat_load.py \
    --measured deltagere/data/<navn>_abvaerk_hourly.csv \
    --dmi-area karup --data-source github \
    --thermal-inertia-grid 24,36,48,72,96 \
    --output deltagere/cases/heat_load_params_<navn>_optimal.yaml
```

Brug resultatet:

```bash
python run_case.py deltagere/cases/<navn>.yaml --data-source github \
    --heat-params deltagere/cases/heat_load_params_<navn>.yaml \
    --start 2026-01-05 --end 2026-01-17
```

Filen indeholder fitstatistik (`_fit_r2`, `_fit_rmse`, `_n_observations`),
kilde og dato, så det er sporbart, hvilken kalibrering en kørsel bygger på.
Vælg DMI-område efter beliggenhed: stationsvalget alene kan flytte
objektivet med nogle procent. Uden `--measured` bruges Billunds måling.

---

## Nettab

Modellen har to nettabsformuleringer.

**Hældningsmodellen (bruges af alle cases i repoet i dag).** Et lineært led,
`nettab_slope_mw_per_k × max(0, T_net − T_ude)`, som en del af
varmelastsyntesen.

**Den fysiske to-ledsmodel (valgfri).** Aktiveres, når casens
`heat_load_params` har en `nettab:`-blok:

```yaml
heat_load_params:
  # ... øvrige parametre ...
  nettab:
    aarligt_nettab_pct: 0.146      # eller: aarligt_nettab_mwh: 17875
    sommer:
      t_frem: 64                    # °C, kundeside (juli–august)
      t_retur: 41
      t_ude: 16                     # valgfri, standard 16
    vinter:
      t_frem: 71                    # °C, kundeside (januar–februar)
      t_retur: 41
      t_ude: 1                      # valgfri, standard 1
    konduktiv_andel: 0.75           # valgfri, standard 0,75 (Billund-fit 0,77)
    t_jord_avg: 9.0                 # valgfri, standard 9,0
    t_jord_amp: 4.0                 # valgfri, standard 4,0
```

Modellen udleder et konduktivt led `a` (isolations- og jordtab) og et
flowled `c` (tab i armaturer og substationer) af de typiske værksværdier:
`nettab_MW(t) = a · (T_rør(t) − T_jord(t)) + c · last_MW(t)`. Se
`src/nettab.py`.

**Dynamisk jordtemperatur (valgfri).** Som standard er T_jord en fast
sæsonkurve efter kalendermåneden. Med

```yaml
    t_jord_dynamic: true
    t_jord_ema_days: 30             # tidskonstant, standard 30 dage
    t_jord_damping: 0.5             # standard 0,5
    t_jord_t_out_ref: 8.0           # klimanormal, standard 8,0 °C
```

følger den udetemperaturen: `t_jord_avg + damping · (EMA(T_ude, τ) − t_out_ref)`.
Årssummen af nettab er den samme; kun fordelingen inden for året ændres.

**Sammenligning.** `--legacy-nettab` tvinger hældningsmodellen, selvom casen
har en `nettab:`-blok. Filnavnet får markøren `__legnet`, så de to kørsler ikke
kolliderer. Nettabsmodellen påvirker kun den syntetiske varmelast; med
`--heat-csv` er nettabet allerede i målingen.
