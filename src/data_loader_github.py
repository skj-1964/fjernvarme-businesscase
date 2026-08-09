"""
Github-baseret data-loader — parallel til `data_loader.py`.

Bygger samme xr.Dataset som `load_external_data`, men læser markeds- og
vejrdata fra det offentlige `df-data`-repo i stedet for at kalde
Energinet/DMI API'er direkte. Det gør modellen kørbar i miljøer uden
udadgående netværk til EDS/DMI (fx Anthropic-sandkassen), så længe
github.com er nået.

Strategi:
  1. Klon df-data ved første kald til en lokal cache-mappe (default
     ``data/df-data``) via ``git clone --depth 1``. Senere kald
     genbruger cache-mappen.
  2. Læs års-CSV'er for [start, end] fra de relevante undermapper
     (spot/, afrr/, mfrr_cap/, mfrr_act/, imbalance/, dmi/).
  3. Returnér DataFrames med præcis samme kolonner som de tilsvarende
     API-svar, og spejl derefter parsing-logikken fra `data_loader.py`
     1:1.

Funktionssignaturer for `fetch_*_github` og `load_external_data_github`
matcher deres pendanter i `data_loader.py` så de kan udskiftes ét-til-ét
af `run_case.py`.

Bemærk om opløsning og duplikater:
  * spot DK1 leveres som timesopløst frem til ~2025-10-01 og 15-min
    derefter (ISP15-introduktion). Vi bevarer alle entries og lader
    `load_external_data_github` om at reindexe til modellens tidsakse.
  * afrr, mfrr_cap er timesopløste hele perioden.
  * mfrr_act, imbalance er 15-min — resamples til timesopløsning her
    præcis som i `fetch_balance_prices`.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import xarray as xr

from .config import CaseConfig
from .data_loader import (
    DEFAULT_EUR_DKK,
    HeatLoadParams,
    _attach_unit_profiles,
    apply_heat_csv_override,
    assert_coverage,
    make_time_index,
    synthesize_heat_load,
)


# ------------------------------------------------------------------------------
# Konstanter
# ------------------------------------------------------------------------------

DEFAULT_DF_DATA_URL = "https://github.com/skj-1964/df-data.git"
DEFAULT_DF_DATA_CACHE = "data/df-data"

# Krævede observationer pr. time, pr. datasæt. Tabellen er en påstand om
# KILDENS native opløsning og hører derfor her hos den der ved hvilket
# datasæt der læses — ikke inde i assert_coverage.
#
# Målt i noter/notat_f1_gate05_oploesning_akse.md §A1 mod df-data 6c95bde:
#   afrr, mfrr_cap        3600 s hele levetiden          → 1
#   dmi                   3600 s hele levetiden          → 1
#   spot                  3600 s → 900 s (2025-09-30 22:00); timesbuckets
#                         gør skiftet ligegyldigt        → 1
#   imbalance, mfrr_act   900 s hele levetiden           → 4
#
# 4 for de to 15-min-datasæt, fordi fetch_balance_prices_github efterfølgende
# kører resample("1h").mean() på dem: en time med færre end fire kvarter
# giver et gennemsnit over et ufuldstændigt grundlag uden at det ses.
_MIN_OBS_PER_HOUR = {
    "spot":      1,
    "dmi":       1,
    "afrr":      1,
    "mfrr_cap":  1,
    "imbalance": 4,
    "mfrr_act":  4,
}


# ------------------------------------------------------------------------------
# Repo-cache: clone-on-first-use, ingen automatisk pull
# ------------------------------------------------------------------------------

def _ensure_df_data_cache(
    repo_url: str = DEFAULT_DF_DATA_URL,
    cache_dir: str | Path = DEFAULT_DF_DATA_CACHE,
    force_refresh: bool = False,
) -> Path:
    """
    Sørg for at df-data er klonet til cache_dir. Returnér root.

    - Hvis cache_dir ikke eksisterer eller mangler .git: clone fra repo_url.
    - Hvis force_refresh: slet og clone igen.
    - Ellers: brug eksisterende klon uden netværkskald (ingen `git pull`,
      så sandkassekørsler er reproducerbare; eksplicit refresh kræves).
    """
    cache_dir = Path(cache_dir)
    git_dir = cache_dir / ".git"

    if force_refresh and cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)

    if cache_dir.exists() and git_dir.exists():
        return cache_dir

    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Kloner {repo_url} → {cache_dir} ...")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(cache_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"git clone fejlede for {repo_url}:\n{e.stderr}"
        ) from e
    return cache_dir


# ------------------------------------------------------------------------------
# CSV-læser: koncatenerer års-filer og filtrerer på tids-range
# ------------------------------------------------------------------------------

def _years_in_range(idx: pd.DatetimeIndex) -> list[int]:
    """Kalenderår som aksen rører, begge endepunkter inklusive.

    Årsfilerne er navngivet efter UTC-året, og `idx` er UTC (tz-strippet i
    `make_time_index`), så år udledes direkte af endepunkterne. Det sidste
    bucket slutter før `idx.max() + step`, så et år mere er aldrig nødvendigt.
    """
    return list(range(idx.min().year, idx.max().year + 1))


def _axis_step(idx: pd.DatetimeIndex) -> pd.Timedelta:
    """Aksens skridtlængde.

    Bruger `idx.freq` når den er sat (det er den fra `make_time_index`), og
    falder ellers tilbage til den entydige differens. Rejser hvis aksen er
    uregelmæssig — så er der ikke ét bucket-span at måle dækning i.
    """
    if idx.freq is not None:
        return pd.Timedelta(idx.freq.nanos, unit="ns")
    if len(idx) < 2:
        raise ValueError(
            "Kan ikke udlede skridtlængde af en akse med under to punkter."
        )
    diffs = pd.Series(idx).diff().dropna().unique()
    if len(diffs) != 1:
        raise ValueError(
            f"Uregelmæssig tidsakse: fandt {len(diffs)} forskellige skridt "
            f"({sorted(pd.to_timedelta(diffs))[:5]}). Dækning kan kun måles "
            "i buckets af ét span."
        )
    return pd.Timedelta(diffs[0])


# Skridtlængde → bucket-navn som `assert_coverage` forstår. Ukendte skridt
# sendes videre som deres str(), så vagten kan afvise dem med et læsbart navn.
_STEP_BUCKET = {
    pd.Timedelta("1h"): "1h",
    pd.Timedelta("15min"): "15min",
}


def _read_dataset(
    repo_root: Path,
    folder: str,
    zone_or_area: str,
    idx: pd.DatetimeIndex,
    time_col: str,
) -> pd.DataFrame:
    """
    Læs én eller flere års-CSV'er for et dataset og koncatener, afgrænset til
    modellens akse. Kolonnesæt bevares som i kilde-CSV.

    Args:
        repo_root:    df-data-klonens rod.
        folder:       'spot', 'afrr', 'mfrr_cap', 'mfrr_act', 'imbalance', 'dmi'
        zone_or_area: 'DK1', 'DK2', 'fyn', 'vestkyst', ...
        idx:          Modellens tidsakse fra `make_time_index`. IKKE en
                      datostreng — se noten om afgrænsning nedenfor.
        time_col:     'hour_utc' (proxy-datasets) eller 'TimeUTC' (EDS-datasets).

    Afgrænsning — én regel, brugt både af masken og af vagten:

        vindue = [idx.min(), idx.max() + step)

    Bucket-etiketterne er lukkede i begge ender (`idx.min()` .. `idx.max()`),
    mens selve tidsvinduet er HALVÅBENT til højre. De to udsagn er det samme:
    bucket `idx.max()` spænder `[idx.max(), idx.max() + step)`, og alle
    observationer i det span hører til den bucket.

    Det er netop dét den gamle kode tog fejl af. Den modtog to omformaterede
    datostrenge og gættede sig til højre endepunkt: en bar dato blev udvidet
    til 23:59:59, mens 'YYYY-MM-DDTHH:MM' ikke blev udvidet. Balance-stien
    sendte det sidste format, så de sidste tre kvarter af hver kørsel blev
    skåret væk og sidste time resamplet fra 1 af 4 kvarter (målt i Gate 0.5
    §B4). Med en eksplicit akse er der intet at gætte, og gætteriet kan ikke
    genopstå: signaturen tager en DatetimeIndex og kan ikke fodres med en
    datostreng.

    Raises:
        FileNotFoundError: Hvis ingen årsfil findes.
        CoverageError:     Hvis de indlæste data ikke dækker aksen.
        KeyError:          Hvis `folder` ikke har en dækningsantagelse.
    """
    if not isinstance(idx, pd.DatetimeIndex):
        raise TypeError(
            f"_read_dataset kræver en pd.DatetimeIndex som akse, fik "
            f"{type(idx).__name__}. Send make_time_index(cfg) — ikke en "
            "datostreng. En streng ville genindføre gætteriet om hvad "
            "'end' betyder (jf. Gate 0.5 §B4)."
        )
    if len(idx) == 0:
        raise ValueError("_read_dataset: tom tidsakse.")

    if folder not in _MIN_OBS_PER_HOUR:
        raise KeyError(
            f"_read_dataset: ingen dækningsantagelse for datasættet "
            f"{folder!r}. Kendte: {sorted(_MIN_OBS_PER_HOUR)}. "
            "En dækningsantagelse er en påstand om kildens native opløsning "
            "og skal træffes bevidst: et 15-min-datasæt målt med "
            "min_per_bucket=1 ville blive godkendt for slapt uden en lyd. "
            f"Tilføj {folder!r} til _MIN_OBS_PER_HOUR med et målt tal."
        )

    step = _axis_step(idx)
    window_start = idx.min()
    window_end = idx.max() + step        # eksklusiv

    years = _years_in_range(idx)
    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    for year in years:
        path = repo_root / folder / f"{zone_or_area}_{year}.csv"
        if not path.exists():
            missing.append(path.name)
            continue
        frames.append(pd.read_csv(path))

    if not frames:
        raise FileNotFoundError(
            f"Ingen CSV'er fundet for {folder}/{zone_or_area} i "
            f"{window_start}..{idx.max()}. "
            f"Forventede filer: {', '.join(f'{zone_or_area}_{y}.csv' for y in years)}. "
            f"Kontrollér df-data-cache i {repo_root}."
        )
    if missing:
        # Ikke en fejl i sig selv — vagten nedenfor afgør om det betød noget.
        # Print'et siger hvilken FIL der manglede; vagten hvilke TIMER.
        print(
            f"    ({folder}/{zone_or_area}: spring over {', '.join(missing)} "
            f"— ikke til stede i repo)"
        )

    df = pd.concat(frames, ignore_index=True)

    ts = pd.to_datetime(df[time_col])
    mask = (ts >= window_start) & (ts < window_end)
    out = df.loc[mask].reset_index(drop=True)

    # Dækningsvagt på det MASKEREDE ts — den mængde der faktisk går videre til
    # reindeksering og nul-fyldning. Bucket-navnet kommer fra aksen selv, så
    # 15-minutters-grænsen håndhæves ét sted: inde i assert_coverage.
    assert_coverage(
        ts.loc[mask],
        window_start,
        idx.max(),
        label=f"{folder}/{zone_or_area}",
        bucket=_STEP_BUCKET.get(step, str(step)),
        min_per_bucket=_MIN_OBS_PER_HOUR[folder],
    )
    return out


# ------------------------------------------------------------------------------
# Fetch-spejlinger
# ------------------------------------------------------------------------------

def fetch_spot_prices_github(
    zone: str,
    idx: pd.DatetimeIndex,
    *,
    repo_root: Path,
    eur_dkk: float = DEFAULT_EUR_DKK,  # bagudkompatibel, bruges ikke
) -> pd.Series:
    """Spejl af `fetch_spot_prices` der læser fra df-data/spot/."""
    df = _read_dataset(repo_root, "spot", zone, idx, time_col="hour_utc")
    required = {"hour_utc", "price_area", "spot_price_dkk"}
    missing = required - set(df.columns)
    if df.empty or missing:
        raise RuntimeError(
            f"Uventet spot-CSV-format. Mangler kolonner: {missing}. "
            f"Fik: {list(df.columns)}"
        )

    df = df[df["price_area"] == zone]
    if df.empty:
        raise RuntimeError(
            f"Ingen spot-data for zone={zone!r} i {idx.min()}..{idx.max()} efter filtrering."
        )

    s = (
        pd.Series(
            pd.to_numeric(df["spot_price_dkk"], errors="coerce").values,
            index=pd.to_datetime(df["hour_utc"]),
            name="spot_dkk_mwh",
        )
        .sort_index()
    )
    return s[~s.index.duplicated(keep="first")]


def fetch_dmi_obs_github(
    shortname: str,
    idx: pd.DatetimeIndex,
    *,
    area: str,
    repo_root: Path,
) -> pd.Series:
    """Spejl af `fetch_dmi_obs` der læser fra df-data/dmi/."""
    df = _read_dataset(repo_root, "dmi", area, idx, time_col="hour_utc")
    if df.empty or "hour_utc" not in df.columns or shortname not in df.columns:
        raise RuntimeError(
            f"Ingen brugbar DMI-data for shortname={shortname!r}, area={area!r}, "
            f"{idx.min()}..{idx.max()}. Kolonner: {list(df.columns)}"
        )
    s = (
        pd.Series(
            pd.to_numeric(df[shortname], errors="coerce").values,
            index=pd.to_datetime(df["hour_utc"]),
            name=shortname,
        )
        .sort_index()
    )
    return s[~s.index.duplicated(keep="first")]


def fetch_dmi_weather_github(
    idx: pd.DatetimeIndex,
    *,
    area: str = "fyn",
    repo_root: Path,
) -> pd.DataFrame:
    """Spejl af `fetch_dmi_weather` — alle DMI-variabler i wide-format."""
    df = _read_dataset(repo_root, "dmi", area, idx, time_col="hour_utc")
    if df.empty or "hour_utc" not in df.columns:
        raise RuntimeError(f"Ingen DMI-data for area={area!r}, {idx.min()}..{idx.max()}")
    idx = pd.to_datetime(df["hour_utc"])
    # Samme udeladelser som `fetch_dmi_weather`: `area` er en streng, og
    # `unixtime`/`timestamp` er tidsstempler. Uden dette blev `area` til en
    # ren NaN-kolonne i den numeriske frame.
    drop_cols = [c for c in ("hour_utc", "hour_dk", "area", "unixtime", "timestamp")
                 if c in df.columns]
    out = (
        df.drop(columns=drop_cols)
          .set_index(idx)
          .apply(pd.to_numeric, errors="coerce")
    )
    out.index.name = "time"
    return out.loc[~out.index.duplicated(keep="first")].sort_index()


def fetch_balance_prices_github(
    idx: pd.DatetimeIndex,
    zone: str = "DK1",
    *,
    repo_root: Path,
    target_index: Optional[pd.DatetimeIndex] = None,
    av_params: Optional[dict] = None,
) -> xr.Dataset:
    """
    Spejl af `fetch_balance_prices` — læser de fire balancemarkedsdatasæt
    fra df-data, beregner α-fraktioner og returnerer time-opløst xr.Dataset
    med samme variabel-skema.
    """
    # ----- aFRR-kapacitet (time-opløst) -----
    df_cap = _read_dataset(repo_root, "afrr", zone, idx, time_col="TimeUTC")
    if df_cap.empty:
        raise RuntimeError(
            f"aFRR-data tom for {zone} i {idx.min()}..{idx.max()}. "
            "DK1 har data fra oktober 2024."
        )
    df_cap["time"] = pd.to_datetime(df_cap["TimeUTC"])
    df_cap = df_cap.set_index("time").sort_index()
    df_cap = df_cap[~df_cap.index.duplicated(keep="first")]
    cap_ds = xr.Dataset({
        "afrr_cap_up_dkk":        df_cap["UpPriceDKK"].astype(float),
        "afrr_cap_down_dkk":      df_cap["DownPriceDKK"].astype(float),
        "afrr_cap_procured_up":   df_cap["UpProcuredMW"].astype(float),
        "afrr_cap_procured_down": df_cap["DownProcuredMW"].astype(float),
    })

    # ----- ImbalancePrice (15-min → time) -----
    df_imb = _read_dataset(repo_root, "imbalance", zone, idx, time_col="TimeUTC")
    if df_imb.empty:
        raise RuntimeError(
            f"imbalance-data tom for {zone} i {idx.min()}..{idx.max()}. "
            "DK1 har data fra marts 2025."
        )
    df_imb["time15"] = pd.to_datetime(df_imb["TimeUTC"])
    df_imb = df_imb.set_index("time15").sort_index()
    df_imb = df_imb[~df_imb.index.duplicated(keep="first")]

    price_cols = {
        "afrr_act_up_dkk":     "aFRRVWAUpDKK",
        "afrr_act_down_dkk":   "aFRRVWADownDKK",
        "mfrr_act_up_dkk":     "mFRRMarginalPriceUpDKK",
        "mfrr_act_down_dkk":   "mFRRMarginalPriceDownDKK",
        "imbalance_price_dkk": "ImbalancePriceDKK",
    }
    volume_cols = {
        "afrr_act_up_mw":   "aFRRUpMW",
        "afrr_act_down_mw": "aFRRDownMW",
    }
    hourly = {}
    for out_name, src_name in {**price_cols, **volume_cols}.items():
        s = df_imb[src_name].astype(float).fillna(0.0)
        hourly[out_name] = s.resample("1h").mean()

    imb_ds = xr.Dataset({
        k: xr.DataArray(v, dims=["time"]) for k, v in hourly.items()
    })

    # ----- av(t): kovarians-korrekt aktiveringsværdi (activation_value-metode) ---
    # Beregnes på 15-min df_imb FØR time-aggregering, så scarcity-spikene bevares.
    av_ds = None
    if av_params is not None:
        from .activation_value import compute_activation_value
        spot15 = av_params["spot_15min"]
        el_flat = float(av_params["el_cost_flat"])
        markup_up = float(av_params["markup_up"])
        av_vars = {}
        for price_col, av_key, pay_key, clear_key in (
            ("aFRRVWAUpDKK", "afrr_activation_value_up",
             "afrr_activation_payment_up", "afrr_clear_fraction_up"),
            ("mFRRMarginalPriceUpDKK", "mfrr_activation_value_up",
             "mfrr_activation_payment_up", "mfrr_clear_fraction_up"),
        ):
            p15 = df_imb[price_col].astype(float).fillna(0.0)
            res = compute_activation_value(
                p15, spot15, markup=markup_up, el_cost_flat=el_flat,
                dt_h=0.25, direction="up",
            )
            av_vars[av_key] = xr.DataArray(res.av, dims=["time"])
            # Netto aktiveringsbetaling (kun p_act) — diagnostik/rapportering.
            av_vars[pay_key] = xr.DataArray(res.av_payment, dims=["time"])
            av_vars[clear_key] = xr.DataArray(res.clear_fraction, dims=["time"])
        av_ds = xr.Dataset(av_vars)
        print(
            f"  av(t) beregnet (markup={markup_up:.0f}, el_flat={el_flat:.0f}): "
            f"aFRR av-gns={float(av_ds['afrr_activation_value_up'].mean()):.1f}, "
            f"mFRR av-gns={float(av_ds['mfrr_activation_value_up'].mean()):.1f} "
            f"DKK/MW/time"
        )

    # ----- mFRR kapacitet (time-opløst) -----
    df_mcap = _read_dataset(repo_root, "mfrr_cap", zone, idx, time_col="TimeUTC")
    if df_mcap.empty:
        raise RuntimeError(f"mFRR-cap data tom for {zone} i {idx.min()}..{idx.max()}.")
    df_mcap["time"] = pd.to_datetime(df_mcap["TimeUTC"])
    df_mcap = df_mcap.set_index("time").sort_index()
    df_mcap = df_mcap[~df_mcap.index.duplicated(keep="first")]
    mcap_ds = xr.Dataset({
        "mfrr_cap_up_dkk":      df_mcap["UpPriceDKK"].astype(float),
        "mfrr_cap_procured_up": df_mcap["UpProcuredMW"].astype(float),
    })

    # ----- mFRR aktiveret volumen (15-min → time, kun TotalmFRRUpMW) -----
    df_mact = _read_dataset(repo_root, "mfrr_act", zone, idx, time_col="TimeUTC")
    if df_mact.empty:
        raise RuntimeError(f"mFRR-act data tom for {zone} i {idx.min()}..{idx.max()}.")
    df_mact["time15"] = pd.to_datetime(df_mact["TimeUTC"])
    df_mact = df_mact.set_index("time15").sort_index()
    df_mact = df_mact[~df_mact.index.duplicated(keep="first")]
    mfrr_up_mw_hourly = (
        df_mact["TotalmFRRUpMW"].astype(float).fillna(0.0).resample("1h").mean()
    )
    mact_ds = xr.Dataset({
        "mfrr_act_up_mw": xr.DataArray(mfrr_up_mw_hourly, dims=["time"]),
    })

    datasets = [cap_ds, imb_ds, mcap_ds, mact_ds]
    if av_ds is not None:
        datasets.append(av_ds)
    merged = xr.merge(datasets, join="outer")

    # ----- α-aFRR(t) og α-mFRR(t) — identisk med fetch_balance_prices -----
    cap_up = merged["afrr_cap_procured_up"]
    act_up = merged["afrr_act_up_mw"]
    safe_cap_up = cap_up.where(cap_up > 0, 1.0)
    alpha_up = (act_up / safe_cap_up).where(cap_up > 0, 0.0)
    alpha_up = alpha_up.clip(min=0.0, max=1.0)
    merged["afrr_activation_fraction_up"] = alpha_up

    mfrr_cap_up = merged["mfrr_cap_procured_up"]
    mfrr_act_up = merged["mfrr_act_up_mw"]
    safe_mfrr_cap_up = mfrr_cap_up.where(mfrr_cap_up > 0, 1.0)
    mfrr_alpha_up = (mfrr_act_up / safe_mfrr_cap_up).where(mfrr_cap_up > 0, 0.0)
    mfrr_alpha_up = mfrr_alpha_up.clip(min=0.0, max=1.0)
    merged["mfrr_activation_fraction_up"] = mfrr_alpha_up

    merged = merged.fillna(0.0)

    if target_index is not None:
        merged = merged.reindex(time=target_index, fill_value=0.0)

    return merged


# ------------------------------------------------------------------------------
# Top-level loader
# ------------------------------------------------------------------------------

def load_external_data_github(
    cfg: CaseConfig,
    *,
    heat_load: Optional[HeatLoadParams] = None,
    dmi_area: str = "fyn",
    dmi_temp_shortname: str = "temp_mean_past1h",
    price_zone: str = "DK1",
    eur_dkk: float = DEFAULT_EUR_DKK,
    with_balancing: bool = False,
    repo_url: str = DEFAULT_DF_DATA_URL,
    cache_dir: str | Path = DEFAULT_DF_DATA_CACHE,
    force_refresh: bool = False,
    heat_csv: Optional[str | Path] = None,
    heat_csv_column: str = "heat_mw_abvaerk",
    heat_csv_tz: str = "UTC",
) -> xr.Dataset:
    """
    Spejl af `load_external_data` der læser fra df-data GitHub-repo.

    Retursignatur er identisk med `load_external_data`:
        xr.Dataset med heat_demand, heat_gaf, heat_guf, heat_nettab,
        spot_price, t_ambient (+ balance-variabler hvis with_balancing).
    """
    if heat_load is None:
        raise ValueError(
            "heat_load (HeatLoadParams) skal angives. Brug load_heat_load_params()."
        )

    repo_root = _ensure_df_data_cache(repo_url, cache_dir, force_refresh)

    # Aksen er den ENE periodedefinition. Den sendes uændret hele vejen ned;
    # ingen omformatering til datostrenge undervejs. 15-minutters-grænsen
    # håndhæves af assert_coverage, som får bucket-navnet fra aksens egen
    # skridtlængde — ét sted, ikke to.
    idx = make_time_index(cfg)

    t_raw = fetch_dmi_obs_github(
        dmi_temp_shortname, idx,
        area=dmi_area, repo_root=repo_root,
    )
    spot_raw = fetch_spot_prices_github(
        price_zone, idx,
        eur_dkk=eur_dkk, repo_root=repo_root,
    )

    # Reindeks til modellens akse — samme logik som load_external_data:
    # temperatur interpoleres, spot forward-fyldes.
    t_ambient = (
        t_raw.reindex(idx.union(t_raw.index)).sort_index()
             .interpolate(method="time").reindex(idx).ffill().bfill()
    )
    spot = spot_raw.reindex(idx).ffill().bfill()

    load_df = synthesize_heat_load(t_ambient, heat_load)

    ds = xr.Dataset(
        data_vars={
            "heat_demand": ("time", load_df["total"].values, {"units": "MW"}),
            "heat_gaf":    ("time", load_df["gaf"].values,   {"units": "MW"}),
            "heat_guf":    ("time", load_df["guf"].values,   {"units": "MW"}),
            "heat_nettab": ("time", load_df["nettab"].values,{"units": "MW"}),
            "spot_price":  ("time", spot.values,             {"units": "DKK/MWh"}),
            "t_ambient":   ("time", t_ambient.values,        {"units": "degC"}),
        },
        coords={"time": idx},
        attrs={
            "source": "df-data (github) + synthetic_heat_load_v2",
            "df_data_repo": repo_url,
            "dmi_area": dmi_area,
            "price_zone": price_zone,
            "eur_dkk": eur_dkk,
            "heat_load_params": json.dumps(heat_load.to_serializable()),
            "heat_load_version": "v2_dual_slope",
        },
    )

    if with_balancing:
        # Samme `idx` som spot/DMI fik. Tidligere blev cfg.time her formateret
        # til "%Y-%m-%dT%H:%M", hvilket gav balance-stien et andet højre
        # endepunkt end spot/DMI-stien og skar de sidste tre kvarter væk
        # (Gate 0.5 §B4). Aksen sendes nu uændret begge veje.
        av_params = None
        if getattr(cfg, "balancing_method", "legacy") == "activation_value":
            bs = cfg.bid_strategy
            av_params = {
                "spot_15min": spot_raw,   # native opløsning (15-min for 2026)
                "markup_up": bs.up_markup_dkk_mwh,
                "el_cost_flat": (cfg.electricity.tariff_consumption_flat
                                 + cfg.electricity.electricity_tax),
            }
        bal = fetch_balance_prices_github(
            idx,
            zone=cfg.electricity.spot_area,
            repo_root=repo_root,
            target_index=pd.DatetimeIndex(ds.time.values),
            av_params=av_params,
        )
        ds = xr.merge([ds, bal])

    # Heat-CSV-override (suspenderer syntese) — samme adfærd som
    # load_external_data, anvendt efter balancing-merge.
    if heat_csv is not None:
        ds = apply_heat_csv_override(
            ds, heat_csv, column=heat_csv_column, tz=heat_csv_tz,
        )

    ds = _attach_unit_profiles(cfg, ds)

    return ds
