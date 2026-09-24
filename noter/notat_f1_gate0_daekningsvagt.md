# F1 Gate 0 — Kortlægning af dækningsvagter og fyldning

**Status:** Read-only kortlægning. Ingen kode ændret, intet kørt.
**Formål:** Fastlægge hvor en dæknings-assert skal placeres, så en kørsel over
en periode uden data fejler i stedet for at blive grøn med fremskrevne priser
og nul balanceindtægt.
**Dato for aflæsning:** 2026-08-07

---

## 1. HEAD

| | |
|---|---|
| SHA | `3ea03994649d5f90f8510c18723570857bd68931` |
| Dato | 2026-08-07 11:55:48 +0200 |
| Besked | `Flyt DMI-hentningen til api_dmi_obs_ny.php` |
| Branch | `main` |

Working tree: rent bortset fra én utracket mappe, `out/`. Ingen modificerede
eller staged filer.

Filstørrelser ved HEAD: `src/data_loader_github.py` 520 linjer,
`src/data_loader.py` 1029 linjer, `run_case.py` 566 linjer.

---

# MÅLT

## 2. Vagter i `data_loader_github.py`

Alle otte påståede vagter **findes**. Fire ligger på det påståede linjenummer,
fire er drevet +4.

| Påstået | Ved HEAD | Funktion | Betingelse (ordret) | Exception |
|---|---|---|---|---|
| 187 | **187** | `fetch_spot_prices_github` | `if df.empty or missing:` | `RuntimeError` (188) — "Uventet spot-CSV-format" |
| 194 | **194** | `fetch_spot_prices_github` | `if df.empty:` (efter `price_area`-filter) | `RuntimeError` (195) — "Ingen spot-data for zone=..." |
| 220 | **220** | `fetch_dmi_obs_github` | `if df.empty or "hour_utc" not in df.columns or shortname not in df.columns:` | `RuntimeError` (221) |
| 245 | **245** | `fetch_dmi_weather_github` | `if df.empty or "hour_utc" not in df.columns:` | `RuntimeError` (246) |
| 274 | **278** (+4) | `fetch_balance_prices_github` | `if df_cap.empty:` | `RuntimeError` (279) — aFRR |
| 291 | **295** (+4) | `fetch_balance_prices_github` | `if df_imb.empty:` | `RuntimeError` (296) — imbalance |
| 354 | **358** (+4) | `fetch_balance_prices_github` | `if df_mcap.empty:` | `RuntimeError` (359) — mFRR-cap |
| 366 | **370** (+4) | `fetch_balance_prices_github` | `if df_mact.empty:` | `RuntimeError` (371) — mFRR-act |

### 2.1 Præmis-korrektion

Præmissen "samtlige eksisterende vagter tester `df.empty`" er ikke helt korrekt.
Der findes **én vagt mere**, som ikke er en tom-tjek, og den er central for
opgaven. I `_read_dataset`, linje 142–147:

```python
    if not frames:
        raise FileNotFoundError(
            f"Ingen CSV'er fundet for {folder}/{zone_or_area} i {start}..{end}. "
```

Den fanger kun tilfældet hvor **ingen** årsfil findes. Den delvise ikke-dækning
håndteres tre linjer senere — og printes:

```python
148	    if missing:
149	        # Ikke en fejl — fx aFRR DK1 har ikke 2023-data. Bare informér.
150	        print(
151	            f"    ({folder}/{zone_or_area}: spring over {', '.join(missing)} "
152	            f"— ikke til stede i repo)"
153	        )
```

Det er hullet i ren form: mangler `DK1_2024.csv` men `DK1_2025.csv` findes, går
kørslen videre med et print, og `df.empty` er falsk. Kommentaren på linje 149 er
en eksplicit designbeslutning om ikke at fejle. Vagten skal enten erstatte eller
supplere dette sted.

Bemærk også at `df.empty`-vagterne på 278/295/358/370 kører **efter**
`_read_dataset`s tidsfilter (168). En frame med ét enkelt døgn ud af et helt år
passerer alle fire.

---

## 3. Fyldningssteder — udtømmende

Grep kørt for: `fillna`, `ffill`, `bfill`, `pad`, `backfill`, `interpolate`,
`reindex`, `resample`, `asfreq`, `fill_value`, `combine_first`, `align`,
`merge(how=)`, `join(`, `nan_to_num`, `dropna`, `or 0`, `clip`, plus
`duplicated` og `errors="coerce"` (samme fejlklasse: tavs værdi→NaN).

Den oprindeligt påståede liste (398, 401, 459) er **ufuldstændig og drevet**.
Faktisk: 402, 405, 459–463 — plus 17 øvrige steder.

### 3A. `src/data_loader_github.py`

| Linje | Funktion | Kode (ordret) | Rammer | Betinget? |
|---|---|---|---|---|
| 168 | `_read_dataset` | `return df.loc[mask].reset_index(drop=True)` | alle 7 datasæt | ubetinget — rækkefilter, ikke fyldning, men **her forsvinder beviset for manglende dækning** |
| 201 | `fetch_spot_prices_github` | `pd.to_numeric(df["spot_price_dkk"], errors="coerce").values` | spot | ubetinget — ugyldig værdi → NaN |
| 207 | `fetch_spot_prices_github` | `return s[~s.index.duplicated(keep="first")]` | spot | ubetinget — tavs rækkebortfald |
| 227 | `fetch_dmi_obs_github` | `pd.to_numeric(df[shortname], errors="coerce").values` | temperatur | ubetinget |
| 233 | `fetch_dmi_obs_github` | `return s[~s.index.duplicated(keep="first")]` | temperatur | ubetinget |
| 256 | `fetch_dmi_weather_github` | `.apply(pd.to_numeric, errors="coerce")` | alle DMI-var | ubetinget |
| 259 | `fetch_dmi_weather_github` | `return out.loc[~out.index.duplicated(keep="first")].sort_index()` | alle DMI-var | ubetinget |
| 285 | `fetch_balance_prices_github` | `df_cap = df_cap[~df_cap.index.duplicated(keep="first")]` | aFRR-cap | ubetinget |
| 302 | `fetch_balance_prices_github` | `df_imb = df_imb[~df_imb.index.duplicated(keep="first")]` | imbalance | ubetinget |
| **317** | `fetch_balance_prices_github` | `s = df_imb[src_name].astype(float).fillna(0.0)` | 5 prisserier + 2 volumener | ubetinget |
| **318** | `fetch_balance_prices_github` | `hourly[out_name] = s.resample("1h").mean()` | samme | ubetinget — timer uden 15-min-rækker bliver NaN, ikke fejl |
| **339** | `fetch_balance_prices_github` | `p15 = df_imb[price_col].astype(float).fillna(0.0)` | aFRR/mFRR akt.pris til av(t) | **betinget** (`av_params is not None`, dvs. `balancing_method == "activation_value"`) |
| 362 | `fetch_balance_prices_github` | `df_mcap = df_mcap[~df_mcap.index.duplicated(keep="first")]` | mFRR-cap | ubetinget |
| 374 | `fetch_balance_prices_github` | `df_mact = df_mact[~df_mact.index.duplicated(keep="first")]` | mFRR-act | ubetinget |
| **376** | `fetch_balance_prices_github` | `df_mact["TotalmFRRUpMW"].astype(float).fillna(0.0).resample("1h").mean()` | mFRR aktiveret MW | ubetinget |
| **385** | `fetch_balance_prices_github` | `merged = xr.merge(datasets, join="outer")` | alle balance-var | ubetinget — union af 4 tidsakser, huller → NaN |
| 390–392 | `fetch_balance_prices_github` | `safe_cap_up = cap_up.where(cap_up > 0, 1.0)` / `.where(cap_up > 0, 0.0)` / `.clip(min=0.0, max=1.0)` | α-aFRR | ubetinget — "ingen kapacitet" ⇒ α=0 |
| 397–399 | `fetch_balance_prices_github` | samme mønster for `mfrr_cap_up` | α-mFRR | ubetinget |
| **402** | `fetch_balance_prices_github` | `merged = merged.fillna(0.0)` | **alle balance-var** | **ubetinget** |
| **405** | `fetch_balance_prices_github` | `merged = merged.reindex(time=target_index, fill_value=0.0)` | **alle balance-var** | formelt betinget (`if target_index is not None`, 404) — men kaldes altid med non-None fra linje 506. Reelt ubetinget. |
| **460–461** | `load_external_data_github` | `t_raw.reindex(idx.union(t_raw.index)).sort_index()` `.interpolate(method="time").reindex(idx).ffill().bfill()` | `t_ambient` → hele varmesyntesen | ubetinget |
| **463** | `load_external_data_github` | `spot = spot_raw.reindex(idx).ffill().bfill()` | `spot_price` | ubetinget |
| 509 | `load_external_data_github` | `ds = xr.merge([ds, bal])` | hele ds | betinget (`with_balancing`) — default outer-join |

### 3B. Delte funktioner (defineret i `data_loader.py`, kaldt fra begge loadere)

| Linje | Funktion | Kode (ordret) | Rammer | Betinget? |
|---|---|---|---|---|
| 790 | `apply_heat_csv_override` | `series = df[column].reindex(model_idx)` | `heat_demand` | betinget (`heat_csv is not None`) |
| 802 | `apply_heat_csv_override` | `series = series.interpolate(method="linear").ffill().bfill()` | `heat_demand` | betinget — **kun hvis huller ≤ 5 %; over 5 % rejses `ValueError` (794–800)** |
| **855** | `_attach_unit_profiles` | `.reindex(target_idx, fill_value=0.0)` | `profile_<unit>` (fx solvarme) | ubetinget for hver aktiv enhed med `production_profile_path` |

`apply_heat_csv_override` linje 791–800 er **den eneste rigtige dækningsvagt i
hele kodebasen** og er den model vagten bør følge:

```python
791	    n_missing = int(series.isna().sum())
792	    if n_missing > 0:
793	        coverage = (1 - n_missing / len(model_idx)) * 100
794	        if n_missing > len(model_idx) * 0.05:
795	            raise ValueError(
```

`_attach_unit_profiles` har ingen — kun en advarsel i docstringen (841–843):
*"Gotcha: profilen reindekseres på EKSAKT tidsstempel. CSV'en skal derfor dække
kørslens periode/år — ellers bliver loftet 0 (fill) for de timer."* Det er en
dokumenteret, uvogtet nul-fyldning.

---

## 4. Rækkefølge

### 4.0 Kaldkæde, `--data-source github`

```
main()                                    run_case.py:483
 ├ _parse_args()                                       484
 ├ args.external = True  (github impliserer external)  490-491
 ├ load_case()                                         505
 ├ _apply_time_override(cfg, year, start, end)         517   ← sætter cfg.time.start/end
 ├ _load_data(args, cfg)                               529
 │   └ load_external_data_github(cfg, ...)             351 → data_loader_github.py:414
 │       ├ _ensure_df_data_cache()                                 442   (git clone, ingen pull)
 │       ├ idx = make_time_index(cfg)                              444   ← ØNSKET akse
 │       ├ start/end = idx.min()/idx.max() .strftime("%Y-%m-%d")   445-446
 │       ├ fetch_dmi_obs_github()                                  448
 │       │   └ _read_dataset()                                     219 → 116
 │       │       ├ FileNotFoundError hvis INGEN fil                143
 │       │       ├ print() hvis NOGEN filer mangler                150   ← ikke en vagt
 │       │       └ df.loc[mask]                                    168   [FYLD 168]
 │       │   └ vagt df.empty                                       220
 │       │   └ coerce + dedupe                                     227,233  [FYLD]
 │       ├ fetch_spot_prices_github()                              452 → 175
 │       │   └ _read_dataset() / vagter 187,194 / 201,207  [FYLD]
 │       ├ t_ambient = ...interpolate().ffill().bfill()            459-462  [FYLD]
 │       ├ spot = spot_raw.reindex(idx).ffill().bfill()            463      [FYLD]
 │       ├ synthesize_heat_load(t_ambient, heat_load)              465
 │       ├ ds = xr.Dataset(..., coords={"time": idx})              467
 │       ├ if with_balancing:                                      488
 │       │   └ fetch_balance_prices_github(target_index=...)       501 → 262
 │       │       └ 4 × _read_dataset / vagter 278,295,358,370
 │       │       └ [FYLD 285,302,317,318,339,362,374,376,385,390-399,402,405]
 │       │   └ xr.merge([ds, bal])                                 509      [FYLD]
 │       ├ apply_heat_csv_override()   (hvis --heat-csv)           514      [vagt 794]
 │       └ _attach_unit_profiles(cfg, ds)                          518      [FYLD 855]
 ├ build_model(cfg, data)                              533
 └ solve_and_extract()                                 538
```

**Svar: nej.** Ingen dækningsrelateret kontrol kører før nogen af
fyldningsstederne. Det eneste der ligger foran er `_read_dataset`s
`if not frames`-tjek (143), som kun fanger total-fravær af filer, samt
`df.empty`-vagterne, som kun fanger nul rækker.

### 4a) Hvor kommer `target_index` fra?

**Fra det ønskede `[start, end)`, ikke fra data.** Kæde:

`run_case.py:517` → `_apply_time_override` sætter `cfg.time.start/end` →
`data_loader.py:58-62`:

```python
def make_time_index(cfg: CaseConfig) -> pd.DatetimeIndex:
    freq = {"1h": "h", "15min": "15min"}[cfg.time.resolution]
    idx = pd.date_range(cfg.time.start, cfg.time.end, freq=freq, tz="UTC")
    return idx.tz_localize(None)
```

→ `data_loader_github.py:444` `idx = make_time_index(cfg)`
→ `data_loader_github.py:467-476` `coords={"time": idx}`
→ `data_loader_github.py:506` `target_index=pd.DatetimeIndex(ds.time.values)`
→ `data_loader_github.py:405` `merged = merged.reindex(time=target_index, fill_value=0.0)`

Det er den præcise mekanisme bag den grønne kørsel: `target_index` er den
*ønskede* akse, `merged` er den *faktiske*, og `fill_value=0.0` udligner
differencen uden at tælle den. Differencen
`len(target_index) − len(merged.time ∩ target_index)` er nøjagtigt det tal
vagten skal måle — og det er tilgængeligt lige der på linje 404, én linje før
det bliver kastet væk.

### 4b) Afgrænsning vs. fyldning

Afgrænsningen sker **to gange, og fyldningen ligger midt imellem**:

1. **Før** (github): `_read_dataset:161-168` maskerer rækker til
   `[start_ts, end_ts]`. Bemærk end-udvidelsen 163–164 — hvis `end` er en bar
   dato uden `:` udvides den til 23:59:59. For balance-stien passeres `end_iso`
   med `T%H:%M` (linje 490), så udvidelsen **ikke** slår til dér, mens den slår
   til for spot/DMI (linje 446 giver `%Y-%m-%d`). To forskellige
   afgrænsningsregler i samme kørsel.
2. **Samtidig med** fyldningen: `reindex(time=target_index, fill_value=0.0)`
   (405) er både afgrænsning til den ønskede akse og fyldning i én operation.

Der findes intet punkt i kæden hvor mængden
"ønsket periode ∖ faktisk dækning" beregnes.

### 4c) pandas eller xarray?

**Begge — fordelt således. Bekræftet.**

- **pandas**: 168, 201, 207, 227, 233, 256, 259, 285, 302, **317**, **318**,
  **339**, 362, 374, **376**, **460–463**, samt 790/802/855 i `data_loader.py`.
- **xarray**: **385** (`xr.merge`), 390–399 (`DataArray.where/.clip`),
  **402** (`Dataset.fillna`), **405** (`Dataset.reindex(time=...)`),
  509 (`xr.merge`).

`reindex(time=target_index, fill_value=0.0)` er xarray — `time` er et
dim-keyword, ikke et positionsargument. Overgangen pandas→xarray sker på
286–291 / 320–322 / 363–366 / 378–380, hvor pandas-Series pakkes i
`xr.Dataset`; dim-navnet `time` kommer fra index-navnet (`set_index("time")`)
hhv. eksplicit `dims=["time"]`.

---

## 5. Filudvælgelse

**Filer udvælges efter år. Der globbes ikke.** `data_loader_github.py:109-140`:

```python
109	def _years_in_range(start: str, end: str) -> list[int]:
110	    """Liste af kalenderår som [start, end] dækker (begge endpoints inklusive)."""
111	    s = pd.Timestamp(start)
112	    e = pd.Timestamp(end)
113	    return list(range(s.year, e.year + 1))
```

```python
132	    years = _years_in_range(start, end)
133	    frames: list[pd.DataFrame] = []
134	    missing: list[str] = []
135	    for year in years:
136	        path = repo_root / folder / f"{zone_or_area}_{year}.csv"
137	        if not path.exists():
138	            missing.append(path.name)
139	            continue
140	        frames.append(pd.read_csv(path))
```

Konsekvenser for hvad vagten kan måle:

- Sæt af forventede filer er **deterministisk og kendt før læsning** (linje 145
  formaterer det allerede til fejlbeskeden). En vagt kan derfor køre pre-flight
  på filniveau uden at læse en eneste CSV.
- `missing` (134/138) er allerede den præcise liste over ikke-dækkede år. Den
  bruges i dag kun til et `print`.
- Årsafgrænsningen bruger `pd.Timestamp(start).year`. Da årsfilerne er navngivet
  efter **UTC-året** og `make_time_index` producerer UTC (tz-strippet, linje
  61–62), er der ingen tz-forskydning i filudvælgelsen. Dækning ved årsskifte i
  lokal tid er derimod ikke garanteret af filnavnet alene.

### 5.1 Faktisk indhold i cachen

Fra mappelisting af `data/df-data/` ved HEAD. Ingen CSV læst.

| Mappe | Filer |
|---|---|
| `spot/` | DE, DK1, DK2, NO2, SE3, SE4 × 2022–2026; SYSTEM 2022–2025 |
| `afrr/` | **DK1 kun, 2024–2026** |
| `mfrr_cap/` | DK1, DK2 × 2023–2026 |
| `mfrr_act/` | **DK1, DK2 kun 2025–2026** |
| `imbalance/` | **DK1, DK2 kun 2025–2026** |
| `dmi/` | fyn, karup, vestkyst × 2022–2026 |

En kørsel `--year 2023 --with-balancing` mod DK1 rammer `FileNotFoundError` på
afrr (ingen filer). En kørsel `--start 2024-01-01 --end 2025-12-31` finder
`afrr/DK1_2024.csv` og passerer — men `imbalance` og `mfrr_act` mangler 2024
helt og printer blot "spring over", hvorefter hele 2024's aktiveringsindtægt
bliver 0 via linje 402/405. Det er nøjagtigt det scenarie gaten beskriver, og
det er **reproducerbart uden netværk** med de filer der ligger i cachen nu.

> Bemærk om skemaet: kolonnesættet er ikke ensartet på tværs af områder —
> DK1/DK2-spot har id i kolonne 0, DE/NO2/SE3/SE4 har ikke. Al aflæsning skal
> ske efter kolonnenavn, aldrig efter position.

---

## 6. `--external`-vejen (`data_loader.py`)

Mønstret er **ikke** det samme som i github-vejen. Målt, ikke antaget.

### 6.1 Vagter

| Linje | Funktion | Betingelse | Exception |
|---|---|---|---|
| 100–101 | `_api_get` | `if payload.get("status") != "success":` | `RuntimeError` — API-statusfelt, ikke dækning |
| 165–169 | `_eds_get` | `if total > len(records):` | `RuntimeError` — pagineringsvagt |
| 220 | `fetch_balance_prices` | `if df_cap.empty:` | `RuntimeError` |
| 241 | `fetch_balance_prices` | `if df_imb.empty:` | `RuntimeError` |
| 280 | `fetch_balance_prices` | `if df_mcap.empty:` | `RuntimeError` |
| 302 | `fetch_balance_prices` | `if df_mact.empty:` | `RuntimeError` |
| 394 | `fetch_dmi_obs` | `if df.empty or "hour_utc" not in ... or shortname not in ...:` | `RuntimeError` |
| 432 | `fetch_dmi_weather` | `if df.empty or "hour_utc" not in df.columns:` | `RuntimeError` |
| 468 | `fetch_spot_prices` | `if df.empty or missing:` | `RuntimeError` |
| 475 | `fetch_spot_prices` | `if df.empty:` | `RuntimeError` |
| **791–800** | `apply_heat_csv_override` | `if n_missing > len(model_idx) * 0.05:` | `ValueError` — **eneste ægte dækningsvagt** |

### 6.2 Forskelle fra github-vejen

1. Der er **ingen `_read_dataset`-analog** og dermed intet enkelt chokepoint.
   To uafhængige læsere: `_api_get` (77) mod `api.sysapp.dk` og `_eds_get`
   (124) mod EDS.
2. `_eds_get` har en pagineringsvagt som `_api_get` ikke har (`_api_get` løkker
   selv, 95–107).
3. Afgrænsningen sker **serverside** via query-parametre (`startdate`/`enddate`
   på 386–387, `start`/`end` på 155) — der er intet lokalt tidsfilter svarende
   til `_read_dataset:161-168`. Vagten kan derfor ikke pre-flighte; den skal
   måle på det returnerede indeks.
4. **Cachen er range-keyet**: `_cache_path` (69–74) hasher endpoint + alle
   params inkl. datoer; `_eds_get` (148–150) hasher `dataset|start|end|filter`.
   En cache-fil kan derfor ikke genbruges for et bredere interval — men den kan
   indeholde et **delvist** svar for det korrekte interval, og det genindlæses
   uden nogen validering (90, 152–153).
5. `fetch_balance_prices` mangler `duplicated`-oprensningen som
   github-versionen har (285/302/362/374). Ellers er 316/352/355
   linje-for-linje identiske med github 385/402/405.
6. Linje 476, `available = sorted(set(df["price_area"].dropna()))`, læser fra
   `df` **efter** at `df` er overskrevet med den tomme filtrerede frame på 474 —
   listen er altid tom. Kosmetisk fejl i en fejlbesked, ingen
   adfærdskonsekvens. Nævnt for fuldstændighed; ikke rettet.

### 6.3 Delte hjælpefunktioner

`data_loader_github.py:44-51` importerer eksplicit seks navne fra
`data_loader`:

```python
44	from .data_loader import (
45	    DEFAULT_EUR_DKK,
46	    HeatLoadParams,
47	    _attach_unit_profiles,
48	    apply_heat_csv_override,
49	    make_time_index,
50	    synthesize_heat_load,
51	)
```

Heraf er tre relevante for vagten:

- **`make_time_index`** — definerer den ønskede akse for begge veje.
- **`apply_heat_csv_override`** — har allerede en dækningsvagt.
- **`_attach_unit_profiles`** — fylder 0.0 uden vagt (linje 855); rammer begge veje.

`_eds_get`, `_api_get` og `_read_dataset` er **ikke** delt.

### 6.4 Rækkefølge, `--external`

```
load_external_data()                              data_loader.py:865
 ├ idx = make_time_index(cfg)                                  898   ← ØNSKET akse
 ├ start/end = idx.min()/idx.max()                             899-900
 ├ fetch_dmi_obs()   → _api_get()                              902 → 383
 ├ fetch_spot_prices() → _api_get()                            906 → 460
 ├ t_ambient = ...interpolate().ffill().bfill()                913-916  [FYLD]
 ├ spot = spot_raw.reindex(idx).ffill().bfill()                917      [FYLD]
 ├ synthesize_heat_load()                                      919
 ├ ds = xr.Dataset(..., coords={"time": idx})                  921
 ├ if with_balancing: fetch_balance_prices(target_index=...)   945 → 176
 │     └ 4 × _eds_get / vagter 220,241,280,302
 │     └ [FYLD 263,264,310,316,324-326,338-340,352,355]
 │   └ xr.merge([ds, bal])                                     953      [FYLD]
 ├ apply_heat_csv_override()                                   958      [vagt 794]
 └ _attach_unit_profiles()                                     962      [FYLD 855]
```

Samme konklusion: ingen dækningskontrol foran nogen fyldning. Bemærk især at
fyldningen på 913–917 ligger **før** `fetch_balance_prices` — en vagt placeret
inde i balance-hentningen kommer for sent for temperatur og spot.

---

## 7. Testopsætning (forberedelse til Gate 1)

| Spørgsmål | Måling |
|---|---|
| Framework | `pytest>=7.0` i `requirements.txt` (linje 9). Installeret i `.venv`. |
| Testmappe | **Findes ikke.** `find` efter `test_*.py`, `*_test.py`, `conftest.py` uden for `.git`/`.venv`: nul træffere. |
| Konfiguration | Ingen `pytest.ini`, `pyproject.toml`, `setup.cfg` eller `tox.ini` i repoet. |
| Sporede testfiler i git | `git ls-files \| grep -i test` giver kun tre YAML-cases (`billund_backtest_jan_apr_2026.yaml`, `billund_energypro_backtest_H2_2025.yaml`, `..._fase2.yaml`) — backtest-konfigurationer, ikke enhedstests. |
| `.pytest_cache` | Findes (utracket, i `.gitignore`). `v/cache/nodeids` indeholder `[]` — pytest er kørt, men har aldrig indsamlet en eneste test. |
| Eksisterende tests der rører loaderne | **Ingen.** |
| Nuværende testpraksis | `CONTRIBUTING.md:33-34` definerer den som en manuel smoke-test: *"Test at den kørte 2×2-matrix stadig virker før I sender — det er den primære smoke-test"*. |

Gate 1 starter altså fra bar bund: `tests/` skal oprettes, og der er intet
eksisterende mønster at følge. Positivt: begge loadere har kaldbare, rene
funktioner (`_read_dataset`, `_years_in_range`, `make_time_index`) der kan
testes uden netværk mod den lokale `data/df-data`-cache.

### 7.1 Yderligere kaldere end `run_case.py`

Vagten skal sidde i loaderen, ikke i `run_case.py`. Fem scripts kalder
`load_external_data_github` direkte uden om CLI'en:

- `scripts/capture_rate.py:71`
- `scripts/capture_rate_q1_2026.py:78`
- `scripts/calibrate_gate.py:72`
- `scripts/diag_sweep.py:62`
- `scripts/calibrate_heat_load.py:99` (og `load_external_data` på 103)

De tre første kalder med `with_balancing=True` — netop de kørsler hvor
nul-fyldt balanceindtægt er farligst, da de producerer kalibrerings- og
capture-rate-tal.

---

# USIKKERT

Følgende kan **ikke** afgøres ved læsning alene. Hvert punkt angiver præcist
hvad der mangler.

1. **Om `missing`-printet nogensinde har været udløst i en produktionskørsel.**
   Kræver: gennemgang af gemte kørselslogs eller `out/`-manifester.
   `src/manifest.py` er ikke gennemgået i denne gate; det kan indeholde et felt
   der registrerer indlæste filer. Afklares ved at læse `manifest.py` og en
   eksisterende `out/*/manifest.*`.

2. **Den native tidsopløsning pr. datasæt pr. periode.**
   Vagten skal sammenligne faktiske tidsstempler mod en forventet akse, og det
   kræver en forventet frekvens. Docstringen (linje 25–27) angiver at DK1-spot
   skifter fra 1h til 15-min omkring 2025-10-01, og at `mfrr_act`/`imbalance`
   er 15-min mens `afrr`/`mfrr_cap` er 1h. Det er kildekode-påstande, ikke
   målinger. Kræver: aflæsning af `hour_utc`/`TimeUTC`-kolonnen i de faktiske
   CSV'er (efter kolonnenavn, aldrig position) for at fastlægge om
   `_read_dataset` skal have en `expected_freq`-parameter eller udlede
   frekvensen. Ikke gjort — ligger uden for read-only-grænsen for denne gate.

3. **Om `xr.merge(..., join="outer")` på linje 385/316 nogensinde udvider aksen
   ud over de fire kildedatasæt.** Afhænger af om de fire filers tidsstempler er
   identiske efter resampling. Kræver en kørsel eller en dataaflæsning.

4. **Semantikken i "det ønskede `[start, end)`".**
   `make_time_index` bruger `pd.date_range(cfg.time.start, cfg.time.end)`, som
   er **inklusiv i begge ender**. Med `--year 2025` bliver
   `cfg.time.end = "2025-12-31"` (`run_case.py:415`), og aksen ender på
   `2025-12-31 00:00` — altså **hverken** `[start, end)` **eller** hele
   kalenderåret; sidste døgns 23 timer mangler i selve modelaksen. Om det er
   tilsigtet er ikke afgjort. Det har direkte betydning for hvad vagten skal
   påstå at have dækket. Kræver en beslutning, ikke en måling. Vagten bør under
   alle omstændigheder måle mod `make_time_index(cfg)` og ikke mod en
   selvstændigt udledt akse, så den ikke indfører en tredje periodedefinition.

5. **Om `_ensure_df_data_cache` kan levere en forældet cache uden at det
   opdages.** Linje 76–77 dokumenterer eksplicit at der ikke køres `git pull`.
   En cache klonet før et års data blev tilføjet til `df-data` giver "fil
   mangler" og dermed nul-fyldning, uden at det er en repo-fejl. Kræver:
   sammenligning af `data/df-data`-klonens HEAD mod remote — et netværkskald,
   ikke foretaget. Relevant fordi vagtens fejlbesked bør skelne "data findes
   ikke" fra "din cache er gammel".

6. **Om `_attach_unit_profiles` reelt er i brug på de kørsler der betyder
   noget.** Kræver gennemgang af `cases/*.yaml` for `production_profile_path`.
   Ikke gjort — uden for afgrænsningen af punkt 3–6. Andeby-referenceværket
   antyder at solvarmeprofiler bruges, hvilket ville gøre linje 855 til et
   aktivt fyldningssted og ikke kun et teoretisk.

---

# ANBEFALET PLACERING AF VAGTEN

**Der findes ikke ét sted. Der skal fire seler til — men de kan dele én
hjælpefunktion.**

Begrundelse: fyldningsstederne fodres af **fire uafhængige indlæsningsveje**,
og ingen af dem har en fælles forfader der ligger foran alle fyldninger. Den
fælles forfader `load_external_data*` er ikke brugbar, fordi fyldningen sker
*inde i* de kald den foretager, og fordi den ikke ser hvilke filer/svar der
faktisk kom ind.

| # | Sæde | Fil:linje | Dækker fyldningssteder | Hvorfor netop her |
|---|---|---|---|---|
| **1** | `_read_dataset`, umiddelbart før `return` | `data_loader_github.py:168` | 168, 201–207, 227–233, 256–259, 285, 302, 317, 318, 339, 362, 374, 376, 385, 390–399, **402**, **405**, 460–463 | **Det snævreste sted i github-vejen.** Alle syv datasæt-indlæsninger (184, 219, 244, 277, 294, 357, 369) passerer her, og hvert fyldningssted ligger nedstrøms for det kald der producerer dets data. Funktionen har allerede alt den behøver i scope: `years`, `missing` (134/138), `start_ts`, `end_ts` (161–164) og `ts` (166). Vagten er reelt en forfremmelse af `print` på 150 til en `raise`, plus en tjek af at `ts` spænder `[start_ts, end_ts]` uden huller. |
| **2** | `_api_get`, før `return df` | `data_loader.py:115` | 913–917 (via 902, 906) | API-vejens DMI+spot. Kan ikke slås sammen med #3 — anden klient, andet cache-format, andet tidsstempelfelt. Bemærk at cache-grenen på 89–90 returnerer tidligt; vagten skal ligge efter begge grene, altså på 115. |
| **3** | `_eds_get`, før `return df` | `data_loader.py:173` | 263, 264, 310, 316, 324–340, **352**, **355** | API-vejens fire balancedatasæt. Samme forbehold om tidlig cache-retur på 152–153 — vagten skal på 173. |
| **4** | `_attach_unit_profiles`, mellem `read_csv` og `reindex` | `data_loader.py:851-856` | **855** | Rammer **begge** veje (kaldt fra `data_loader.py:962` og `data_loader_github.py:518`). Docstringen 841–843 beskriver allerede fejlen; der mangler kun at den rejses i stedet for at stå skrevet. |

`apply_heat_csv_override` behøver **intet femte sæde** — den har vagten på
`data_loader.py:791-800` allerede, og dens 5 %-tærskel-mønster er den skabelon
de fire andre bør kopiere.

## Fælles hjælpefunktion

Placér én funktion i `data_loader.py` — ikke i `data_loader_github.py`, da
github-modulet allerede importerer fra `data_loader` og ikke omvendt (linje
44–51), så retningen er den etablerede:

```
assert_coverage(actual_index, start, end, *, label, freq=None, max_gap_frac=0.0)
```

Signaturen skal have `label` med, fordi den bliver kaldt fra fire steder for
syv-plus datasæt, og fejlbeskeden skal kunne sige hvilket. Beskeden bør — efter
mønsteret fra 795–800 — angive ønsket interval, faktisk dækket interval, antal
manglende tidsskridt og dækningsprocent.

## Hvis der kun må sættes ét sæde

Så: **`_read_dataset` (`data_loader_github.py:168`)**. Den dækker 18 af de 23
fyldningssteder i github-vejen, herunder begge de kritiske (**402** og **405**)
og hele spot/temperatur-fyldningen (460–463). Den dækker **ikke**
`_attach_unit_profiles:855` og **ingenting** i `--external`-vejen. Sat der
lukker vagten det scenarie gaten beskriver — nul balanceindtægt på en periode
uden data — men lader profil-loftet og hele API-vejen stå åben.

## To ting vagten ikke må bygge på

- **`df.empty` er ubrugelig som dækningsmål** og skal ikke genbruges. Én række
  passerer alle otte eksisterende vagter.
- **Efter linje 402/405 er beviset væk.** En kontrol på det færdige `ds` kan
  ikke skelne en fyldt 0.0 fra en ægte 0.0. Vagten skal ligge opstrøms, hvor
  `merged.time` stadig er den faktiske akse.
