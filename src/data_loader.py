"""
Data indlæsning og dummy-generatorer.

Til sandbox-brug i trin 1 bygger vi enten:
  - Rent syntetiske tidsserier (generate_dummy_data), eller
  - "Halvrigtige" serier (load_external_data): rigtig udetemperatur fra DMI
    og rigtig DK1-spot fra Energinet, med varmelasten syntetiseret via
    dual-slope v2 ovenpå den rigtige temperatur.

Varmesyntese v2 (session 10, kalibreret mod Billund ab værk 2025-2026):
    Q(t) = baseline(h) + β_gaf · max(0, T_ref - EMA(T_out))
                       + β_net · max(0, T_net - T_out)

Parametre indlæses fra cases/*.yaml under nøglen `heat_load_params`.
Tidligere v1-felter (annual_gwh, guf_mean_mw, nettab_mw) er droppet.

Design: returnerer altid en xarray.Dataset med koordinat 'time' i UTC (tz-naive).
Tidsopløsning matcher CaseConfig.time.resolution.

API-kilder:
  - DMI observationer:   https://www.sysapp.dk/api_dmi_obs.php
  - Energinet elspot:    https://www.sysapp.dk/api_energinet_prices.php
  - Energi Data Service: https://api.energidataservice.dk (balance-markeder)
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
import xarray as xr

from .config import CaseConfig


# ------------------------------------------------------------------------------
# Konstanter
# ------------------------------------------------------------------------------

API_BASE = "https://www.sysapp.dk"
API_LIMIT_MAX = 10_000
API_TIMEOUT_S = 60
DEFAULT_EUR_DKK = 7.45  # brug daglig kurs i produktionskørsler


# ------------------------------------------------------------------------------
# Tidsakse
# ------------------------------------------------------------------------------

def make_time_index(cfg: CaseConfig) -> pd.DatetimeIndex:
    """Timestemplede index i UTC, tz-naive internt for nem alignment."""
    freq = {"1h": "h", "15min": "15min"}[cfg.time.resolution]
    idx = pd.date_range(cfg.time.start, cfg.time.end, freq=freq, tz="UTC")
    return idx.tz_localize(None)


# ------------------------------------------------------------------------------
# API-klient med paginering + disk-cache
# ------------------------------------------------------------------------------

def _cache_path(cache_dir: Path, endpoint: str, params: dict) -> Path:
    """Deterministisk sti baseret på endpoint + parametre."""
    key_src = {"endpoint": endpoint, **{k: v for k, v in params.items() if v is not None}}
    key = hashlib.md5(json.dumps(key_src, sort_keys=True).encode()).hexdigest()[:12]
    stem = endpoint.strip("/").replace(".php", "").replace("/", "_")
    return cache_dir / f"{stem}__{key}.csv"


def _api_get(
    endpoint: str,
    params: dict,
    *,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Hent alle sider fra et endpoint. Cacher rå respons som CSV."""
    params = {k: v for k, v in params.items() if v is not None}

    if cache_dir is not None and not force_refresh:
        cf = _cache_path(cache_dir, endpoint, params)
        if cf.exists():
            return pd.read_csv(cf)

    url = API_BASE.rstrip("/") + endpoint
    rows: list[dict] = []
    offset = 0
    while True:
        q = {**params, "limit": API_LIMIT_MAX, "offset": offset, "format": "json"}
        r = requests.get(url, params=q, timeout=API_TIMEOUT_S)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != "success":
            raise RuntimeError(f"API-fejl på {endpoint}: {payload}")
        rows.extend(payload.get("data", []))
        meta = payload.get("meta") or {}
        if not meta.get("has_more"):
            break
        offset = meta.get("next_offset") or (offset + API_LIMIT_MAX)
        time.sleep(0.1)

    df = pd.DataFrame(rows)

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(_cache_path(cache_dir, endpoint, params), index=False)

    return df

# ---------------------------------------------------------------------------
# Energi Data Service — rå klient + balancemarked
# ---------------------------------------------------------------------------

EDS_BASE = "https://api.energidataservice.dk/dataset"


def _eds_get(
    dataset: str,
    start: str,
    end: str,
    filter_obj: dict | None = None,
    cache_dir: str = "data/raw",
    force_refresh: bool = False,
    page_size: int = 100000,
) -> "pd.DataFrame":
    """Hent et EDS-datasæt med simpel cache og paginering.

    Cacher som CSV keyet på md5 af parametrene. Fejler højlydt hvis
    svaret overskrider page_size (paginering ikke implementeret — ikke
    nødvendigt for årsdata under limit=100000).
    """
    import hashlib
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import urlopen
    import pandas as pd

    os.makedirs(cache_dir, exist_ok=True)

    key_source = f"{dataset}|{start}|{end}|{json.dumps(filter_obj, sort_keys=True)}"
    key = hashlib.md5(key_source.encode()).hexdigest()[:12]
    cache_path = os.path.join(cache_dir, f"api_eds_{dataset.lower()}__{key}.csv")

    if os.path.exists(cache_path) and not force_refresh:
        return pd.read_csv(cache_path)

    params = {"start": start, "end": end, "limit": page_size}
    if filter_obj:
        params["filter"] = json.dumps(filter_obj)

    url = f"{EDS_BASE}/{dataset}?{urlencode(params)}"
    with urlopen(url, timeout=120) as r:
        payload = json.loads(r.read().decode("utf-8"))

    records = payload.get("records", [])
    total = payload.get("total", len(records))
    if total > len(records):
        raise RuntimeError(
            f"EDS-paginering ikke implementeret: {dataset} har {total} rækker, "
            f"fik {len(records)}. Udvid page_size eller tilføj offset-loop."
        )

    df = pd.DataFrame(records)
    df.to_csv(cache_path, index=False)
    return df


def fetch_balance_prices(
    start: str,
    end: str,
    zone: str = "DK1",
    cache_dir: str = "data/raw",
    force_refresh: bool = False,
    target_index: "pd.DatetimeIndex | None" = None,
) -> "xr.Dataset":
    """Hent balancemarkedspriser og volumener for `zone` i [start, end).

    Kilder (fire EDS-datasæt):
      * AfrrReservesNordic          — aFRR kapacitet, time-opløst, DK1 fra okt 2024
      * ImbalancePrice              — aktiveringspriser (aFRR + mFRR marginal),
                                      15-min → time, DK1 fra marts 2025
      * mFRRCapacityMarket          — mFRR kapacitet, time-opløst
      * MfrrEnergyActivationMarket  — mFRR aktiveret volumen (til α-beregning),
                                      15-min → time

    Returnerer xr.Dataset på time-opløsning med:
      # aFRR (bevarer eksisterende navne for bagudkompatibilitet)
      afrr_cap_up_dkk, afrr_cap_down_dkk        [DKK/MW/h]
      afrr_cap_procured_up, afrr_cap_procured_down  [MW]
      afrr_act_up_dkk, afrr_act_down_dkk        [DKK/MWh, VWA]
      afrr_act_up_mw, afrr_act_down_mw          [MW timegns]
      afrr_activation_fraction_up                [0..1, α(t) for op-reserve]
      # mFRR (tilføjet session 12 trin B)
      mfrr_cap_up_dkk                            [DKK/MW/h]
      mfrr_cap_procured_up                       [MW]
      mfrr_act_up_dkk, mfrr_act_down_dkk         [DKK/MWh, marginal]
      mfrr_act_up_mw                             [MW timegns, TotalmFRRUpMW]
      mfrr_activation_fraction_up                [0..1, α(t) for op-reserve]
      # Reference
      imbalance_price_dkk                        [DKK/MWh]
    """
    import pandas as pd
    import xarray as xr

    # ----- AfrrReservesNordic (time-opløst) -----
    df_cap = _eds_get(
        "AfrrReservesNordic",
        start=start, end=end,
        filter_obj={"PriceArea": [zone]},
        cache_dir=cache_dir, force_refresh=force_refresh,
    )
    if df_cap.empty:
        raise RuntimeError(
            f"AfrrReservesNordic gav 0 rækker for {zone} i {start}..{end}. "
            "Datasættet har data fra oktober 2024 og frem."
        )
    df_cap["time"] = pd.to_datetime(df_cap["TimeUTC"])
    df_cap = df_cap.set_index("time").sort_index()
    cap_ds = xr.Dataset({
        "afrr_cap_up_dkk":        df_cap["UpPriceDKK"].astype(float),
        "afrr_cap_down_dkk":      df_cap["DownPriceDKK"].astype(float),
        "afrr_cap_procured_up":   df_cap["UpProcuredMW"].astype(float),
        "afrr_cap_procured_down": df_cap["DownProcuredMW"].astype(float),
    })

    # ----- ImbalancePrice (15-min → time) -----
    df_imb = _eds_get(
        "ImbalancePrice",
        start=start, end=end,
        filter_obj={"PriceArea": [zone]},
        cache_dir=cache_dir, force_refresh=force_refresh,
    )
    if df_imb.empty:
        raise RuntimeError(
            f"ImbalancePrice gav 0 rækker for {zone} i {start}..{end}. "
            "Datasættet har data fra marts 2025 og frem."
        )
    df_imb["time15"] = pd.to_datetime(df_imb["TimeUTC"])
    df_imb = df_imb.set_index("time15").sort_index()

    price_cols = {
        "afrr_act_up_dkk":       "aFRRVWAUpDKK",
        "afrr_act_down_dkk":     "aFRRVWADownDKK",
        "mfrr_act_up_dkk":       "mFRRMarginalPriceUpDKK",
        "mfrr_act_down_dkk":     "mFRRMarginalPriceDownDKK",
        "imbalance_price_dkk":   "ImbalancePriceDKK",
    }
    volume_cols = {
        "afrr_act_up_mw":   "aFRRUpMW",
        "afrr_act_down_mw": "aFRRDownMW",  # signed — negativ for ned
    }

    hourly = {}
    for out_name, src_name in {**price_cols, **volume_cols}.items():
        s = df_imb[src_name].astype(float).fillna(0.0)
        hourly[out_name] = s.resample("1h").mean()

    imb_ds = xr.Dataset({
        k: xr.DataArray(v, dims=["time"]) for k, v in hourly.items()
    })

    # ----- mFRRCapacityMarket (time-opløst, DKK direkte i UpPriceDKK) -----
    # Schema: TimeUTC, PriceArea, UpDemandMW, UpProcuredMW, UpPriceEUR, UpPriceDKK,
    #         DownDemandMW, DownProcuredMW, DownPriceEUR, DownPriceDKK.
    # Kun op-regulering hentes i trin B — ned håndteres når/hvis relevant.
    df_mcap = _eds_get(
        "mFRRCapacityMarket",
        start=start, end=end,
        filter_obj={"PriceArea": [zone]},
        cache_dir=cache_dir, force_refresh=force_refresh,
    )
    if df_mcap.empty:
        raise RuntimeError(
            f"mFRRCapacityMarket gav 0 rækker for {zone} i {start}..{end}."
        )
    df_mcap["time"] = pd.to_datetime(df_mcap["TimeUTC"])
    df_mcap = df_mcap.set_index("time").sort_index()
    mcap_ds = xr.Dataset({
        "mfrr_cap_up_dkk":      df_mcap["UpPriceDKK"].astype(float),
        "mfrr_cap_procured_up": df_mcap["UpProcuredMW"].astype(float),
    })

    # ----- MfrrEnergyActivationMarket (15-min → time) -----
    # Bruges kun til aktiveret volumen (TotalmFRRUpMW) for α-beregning;
    # aktiveringspris er allerede hentet fra ImbalancePrice ovenfor.
    # Schema inkluderer TotalmFRRUpMW, mFRROfferedUpMW, mFRRSAUpReqMW,
    # mFRRLocalUpMW, mFRRDAUpMW, mFRRSpecialUpMW, mFRRSAUpEUR, mFRRDAUpEUR.
    df_mact = _eds_get(
        "MfrrEnergyActivationMarket",
        start=start, end=end,
        filter_obj={"PriceArea": [zone]},
        cache_dir=cache_dir, force_refresh=force_refresh,
    )
    if df_mact.empty:
        raise RuntimeError(
            f"MfrrEnergyActivationMarket gav 0 rækker for {zone} i {start}..{end}."
        )
    df_mact["time15"] = pd.to_datetime(df_mact["TimeUTC"])
    df_mact = df_mact.set_index("time15").sort_index()

    mfrr_up_mw_hourly = (
        df_mact["TotalmFRRUpMW"].astype(float).fillna(0.0).resample("1h").mean()
    )
    mact_ds = xr.Dataset({
        "mfrr_act_up_mw": xr.DataArray(mfrr_up_mw_hourly, dims=["time"]),
    })

    merged = xr.merge([cap_ds, imb_ds, mcap_ds, mact_ds], join="outer")

    # ----- α_aFRR(t) — aktiveringsfraktion op -----
    # α(t) = aktiveret MW / indkøbt MW per time, clip til [0,1]. Safe division.
    # Jf. STATUS session 8 §7.3: proportional-aktiverings-estimat, rimelig
    # midterantagelse når vi byder nær marginal-erstatningsomkostning.
    cap_up = merged["afrr_cap_procured_up"]
    act_up = merged["afrr_act_up_mw"]
    safe_cap_up = cap_up.where(cap_up > 0, 1.0)
    alpha_up = (act_up / safe_cap_up).where(cap_up > 0, 0.0)
    alpha_up = alpha_up.clip(min=0.0, max=1.0)
    merged["afrr_activation_fraction_up"] = alpha_up

    # ----- α_mFRR(t) — aktiveringsfraktion op for mFRR -----
    # Konceptuelt samme beregning som for aFRR, men med mFRR-kapacitet og
    # TotalmFRRUpMW. Realistisk α for BSP er formentlig ~2/3 af total
    # (jf. STATUS_session11 §4: SA/MARI-andelen er åben for alle BSP'er,
    # Local og DA er delvist TSO-styret). Vi beregner total her og lader
    # modellen anvende den direkte; antagelsen kan korrigeres senere hvis
    # nødvendigt via en skaleringsfaktor.
    mfrr_cap_up = merged["mfrr_cap_procured_up"]
    mfrr_act_up = merged["mfrr_act_up_mw"]
    safe_mfrr_cap_up = mfrr_cap_up.where(mfrr_cap_up > 0, 1.0)
    mfrr_alpha_up = (mfrr_act_up / safe_mfrr_cap_up).where(mfrr_cap_up > 0, 0.0)
    mfrr_alpha_up = mfrr_alpha_up.clip(min=0.0, max=1.0)
    merged["mfrr_activation_fraction_up"] = mfrr_alpha_up

    # ImbalancePrice-datasættet har data fra 18. marts 2025 og frem, mens
    # AfrrReservesNordic har data fra oktober 2024. Ved outer-merge opstår
    # der NaN'er i imb-variablene for perioden før marts 2025 (jan-feb 2025
    # ved årsanalyse). Disse propagerer til objektivet som NaN-koefficienter
    # og får linopy til at afvise modellen. Semantisk betyder "ingen
    # imbalance-data" = "antag ingen aktivering", så 0 er den rigtige default.
    #
    # Gæld til rapporten: Årsanalyser af 2025 vil have aktiveringsindtægt
    # afgrænset til april-dec (ca. 75% af året). Dokumenteres som antagelse.
    merged = merged.fillna(0.0)

    if target_index is not None:
        merged = merged.reindex(time=target_index, fill_value=0.0)

    return merged


# ------------------------------------------------------------------------------
# Hentere: DMI-obs og Energinet-spot
# ------------------------------------------------------------------------------

def fetch_dmi_obs(
    shortname: str,
    start: str,
    end: str,
    *,
    area: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> pd.Series:
    """
    Hent én DMI-variabel som pd.Series (UTC, tz-naive).

    Bemærk: /api_dmi_obs.php returnerer wide-format — én række pr. time med
    alle variabler som kolonner. Vi plukker `shortname`-kolonnen ud.
    """
    df = _api_get(
        "/api_dmi_obs.php",
        {"shortname": shortname, "startdate": start, "enddate": end, "area": area},
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    if df.empty or "hour_utc" not in df.columns or shortname not in df.columns:
        raise RuntimeError(
            f"Ingen brugbar DMI-data for shortname={shortname!r}, area={area!r}, "
            f"{start}..{end}. Kolonner fra API: {list(df.columns)}"
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

def fetch_dmi_weather(
    start: str,
    end: str,
    *,
    area: str = "fyn",
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Hent alle DMI-variabler for et område som wide-format DataFrame (UTC).

    Ét API-kald giver typisk: temp_mean_past1h, radia_glob_past1h,
    wind_speed_past1h, precip_past1h, pressure, humidity_past1h.
    Brug denne når du skal bruge mere end én variabel — sparer en HTTP-roundtrip
    og gemmer én samlet cache-fil pr. periode.
    """
    df = _api_get(
        "/api_dmi_obs.php",
        {"shortname": "temp_mean_past1h", "startdate": start, "enddate": end, "area": area},
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    if df.empty or "hour_utc" not in df.columns:
        raise RuntimeError(f"Ingen DMI-data for area={area!r}, {start}..{end}")

    idx = pd.to_datetime(df["hour_utc"])
    drop_cols = [c for c in ("hour_utc", "hour_dk") if c in df.columns]
    out = df.drop(columns=drop_cols).set_index(idx).apply(pd.to_numeric, errors="coerce")
    out.index.name = "time"
    return out.loc[~out.index.duplicated(keep="first")].sort_index()

def fetch_spot_prices(
    zone: str,
    start: str,
    end: str,
    *,
    eur_dkk: float = DEFAULT_EUR_DKK,  # beholdt for bagudkompatibilitet, bruges ikke
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> pd.Series:
    """
    Hent Energinet elspot som DKK/MWh, UTC-tz-naive.

    NB: Endpoint'et returnerer både DK1 og DK2 uanset zone-parameteren, så vi
    filtrerer lokalt på price_area. Vi bruger spot_price_dkk direkte fra API'et
    og ignorerer eur_dkk (kursrisiko er allerede håndteret i kilden).
    """
    df = _api_get(
        "/api_energinet_prices.php",
        {"zone": zone, "startdate": start, "enddate": end},
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    required = {"hour_utc", "price_area", "spot_price_dkk"}
    missing = required - set(df.columns)
    if df.empty or missing:
        raise RuntimeError(
            f"Uventet respons fra spot-API. Mangler kolonner: {missing}. "
            f"Fik: {list(df.columns)}"
        )

    df = df[df["price_area"] == zone]
    if df.empty:
        available = sorted(set(df["price_area"].dropna()))
        raise RuntimeError(
            f"Ingen spotdata for zone={zone!r} i {start}..{end}. "
            f"Tilgængelige zoner i responsen: {available}"
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

# ------------------------------------------------------------------------------
# Varmebelastning: dual-slope syntese v2 (session 10)
# ------------------------------------------------------------------------------

@dataclass
class HeatLoadParams:
    """
    Dual-slope varmelastsyntese kalibreret mod Billund ab værk 2025-2026.

        Q(t) = baseline(h)                             ← empirisk 24h-profil
             + β_gaf × max(0, T_ref − EMA(T_out))      ← rumvarme, termisk inerti
             + β_net × max(0, T_net − T_out)           ← nettab-tillæg, hurtig respons

    Tidligere v1-felter (annual_gwh, guf_mean_mw, nettab_mw) er droppet —
    årsenergien er nu et OUTPUT af syntesen, ikke et kalibreringsmål. Det
    gør modellen fysisk retvisende på tværs af år med forskellige T_out-profiler.

    Navnekonvention i output-dekomponeringen bibeholdes fra v1 for
    bagudkompatibilitet med reporting.py og dispatch-plots:
      - heat_gaf     = rumvarme (GAF-leddet)
      - heat_guf     = baseline-profil (semantisk: brugsvand + konstant nettab)
      - heat_nettab  = temperaturafhængig nettab-tillæg (NYT i v2)
    """
    gaf_mw_per_k: float
    t_ref: float = 15.0
    thermal_inertia_hours: int = 24
    nettab_slope_mw_per_k: float = 0.0     # 0 → single-slope fallback
    t_net: float = 12.0                     # bruges kun hvis nettab_slope_mw_per_k > 0
    baseline_profile_mw: np.ndarray = field(
        default_factory=lambda: np.full(24, 6.0)
    )
    weekly_dip: float = 0.02
    # NY (session 21): to-led fysisk nettab-model, valgfri. Når sat,
    # erstatter den nettab_slope_mw_per_k/t_net-formlen i synthesize_heat_load.
    nettab_cfg: Optional[dict] = None

    def __post_init__(self):
        """Sanity-tjek og type-coercion."""
        self.baseline_profile_mw = np.asarray(self.baseline_profile_mw, dtype=float)
        if self.baseline_profile_mw.shape != (24,):
            raise ValueError(
                f"baseline_profile_mw skal være 24-element array, "
                f"fik shape={self.baseline_profile_mw.shape}"
            )

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "HeatLoadParams":
        """Byg fra YAML-dict; ignorer metadata-felter der begynder med '_'."""
        return cls(
            gaf_mw_per_k=float(d["gaf_mw_per_k"]),
            t_ref=float(d.get("t_ref", 15.0)),
            thermal_inertia_hours=int(d.get("thermal_inertia_hours", 24)),
            nettab_slope_mw_per_k=float(d.get("nettab_slope_mw_per_k", 0.0)),
            t_net=float(d.get("t_net", 12.0)),
            baseline_profile_mw=np.asarray(
                d.get("baseline_profile_mw", [6.0] * 24), dtype=float
            ),
            weekly_dip=float(d.get("weekly_dip", 0.02)),
            nettab_cfg=d.get("nettab"),  # NY: to-led fysisk nettab-model
        )

    def to_serializable(self) -> dict:
        """Ren dict til JSON/YAML-serialisering (np.ndarray → list)."""
        return {
            "gaf_mw_per_k": float(self.gaf_mw_per_k),
            "t_ref": float(self.t_ref),
            "thermal_inertia_hours": int(self.thermal_inertia_hours),
            "nettab_slope_mw_per_k": float(self.nettab_slope_mw_per_k),
            "t_net": float(self.t_net),
            "baseline_profile_mw": self.baseline_profile_mw.tolist(),
            "weekly_dip": float(self.weekly_dip),
            **({"nettab": dict(self.nettab_cfg)} if self.nettab_cfg else {}),
        }


def synthesize_heat_load(t_out: pd.Series, params: HeatLoadParams) -> pd.DataFrame:
    """Returner DataFrame med kolonner gaf, guf, nettab, total (alle MW).

    Kolonnenavne bibeholdt fra v1 så reporting.py ikke skal røres — men den
    semantiske betydning er skiftet:
      - gaf     = rumvarme (GAF-leddet, samme som før)
      - guf     = baseline-profil (ikke længere kun brugsvand)
      - nettab  = temperaturafhængig nettab-tillæg (var konstant før)
    Sum af de tre = total, uændret.
    """
    idx = t_out.index
    if not isinstance(idx, pd.DatetimeIndex):
        raise TypeError("t_out skal have DatetimeIndex")

    # --- GAF med termisk inerti i bygningsmassen ---
    t_smooth = t_out.ewm(span=params.thermal_inertia_hours, adjust=False).mean()
    gaf = (params.gaf_mw_per_k * (params.t_ref - t_smooth).clip(lower=0.0)).rename("gaf")

    # Weekend-reduktion på GAF kun (bygn.-afhængig; nettab reagerer på flow/temp)
    if params.weekly_dip:
        w = np.where(idx.dayofweek >= 5, 1.0 - params.weekly_dip, 1.0)
        gaf = gaf * w

    # --- Baseline: cyklisk hour-of-day lookup (brugsvand + konstant nettab) ---
    baseline = pd.Series(
        params.baseline_profile_mw[idx.hour],
        index=idx,
        name="guf",  # navnet bibeholdt for bagudkompat.; semantik udvidet
    )

    # --- Nettab-tillæg ---
    # Prioritet:
    #   1) nettab_cfg sat (NY session 21): to-led fysisk model
    #      nettab_MW(t) = a·(T_pipe(t) − T_jord(t)) + c·load_MW(t)
    #   2) nettab_slope_mw_per_k > 0: legacy dual-slope v2
    #   3) ellers: ingen nettab-tillæg
    if params.nettab_cfg is not None:
        from .nettab import build_nettab_model, nettab_MW as _nettab_MW
        # Brug gaf+baseline som load-proxy (uden nettab → undgår cirkularitet).
        # Bias er <3% fordi c-koefficienten typisk er ~0,03.
        load_proxy = gaf + baseline
        # Skalér op til 8760h for korrekt pct→MWh på del-årlige kørsler
        period_hours = max(1, len(idx))
        load_proxy_annual = float(load_proxy.sum()) * 8760.0 / period_hours
        # `aarligt_nettab_pct` fortolkes som nettab/total (Billund-konvention),
        # hvor total = ab værk = load + nettab. Vi løser bagud:
        #   pct = nettab/(load + nettab)  →  total = load / (1 − pct)
        nc = params.nettab_cfg
        if "aarligt_nettab_pct" in nc:
            _pct = float(nc["aarligt_nettab_pct"])
            annual_prod_mwh = load_proxy_annual / max(1e-6, 1.0 - _pct)
        elif "aarligt_nettab_mwh" in nc:
            annual_prod_mwh = load_proxy_annual + float(nc["aarligt_nettab_mwh"])
        else:
            annual_prod_mwh = load_proxy_annual
        # T_jord beregnes inde i build (statisk cosinus eller dynamisk EMA
        # afhængigt af t_jord_dynamic i YAML). Drive-integralet beregnes
        # mod faktiske T_out, så a- og c-koefficienter er konsistente med
        # evalueringen.
        coef = build_nettab_model(
            params.nettab_cfg,
            annual_production_mwh=annual_prod_mwh,
            t_out=t_out.values,
            timestamps=idx,
        )
        nettab_arr = _nettab_MW(coef, t_out.values, load_proxy.values)
        nettab = pd.Series(nettab_arr, index=idx, name="nettab")
    elif params.nettab_slope_mw_per_k > 0:
        nettab = (
            params.nettab_slope_mw_per_k
            * (params.t_net - t_out).clip(lower=0.0)
        ).rename("nettab")
    else:
        nettab = pd.Series(0.0, index=idx, name="nettab")

    total = (gaf + baseline + nettab).rename("total")
    return pd.concat([gaf, baseline, nettab, total], axis=1)


def load_heat_load_params(
    case_yaml: Path | str,
    override_yaml: Path | str | None = None,
) -> HeatLoadParams:
    """Læs HeatLoadParams fra YAML. Prioritet: override_yaml > case_yaml.

    case_yaml forventes at indeholde top-level nøglen `heat_load_params`.
    override_yaml kan enten være skrevet på samme format, eller indeholde
    en wrapper-nøgle der starter med `heat_load_params` (fx `heat_load_params_v2_dual`
    som `scripts/calibrate_heat_load.py` genererer).

    Nettab-merge-regel (session 21): hvis override-filen ikke indeholder
    en `nettab:`-blok, men case YAML gør, så bringes case YAML's nettab
    ind i den endelige HeatLoadParams. Det betyder at kalibrerings-output
    fra `calibrate_heat_load.py` (som ikke ved noget om nettab) kan
    bruges som `--heat-params`-override uden at miste case YAML's
    driftskonfiguration.
    """
    import yaml

    def _extract_section(raw: dict, source: str) -> dict:
        if "heat_load_params" in raw:
            return raw["heat_load_params"]
        candidates = [k for k in raw if k.startswith("heat_load_params")]
        if not candidates:
            raise ValueError(
                f"heat_load_params mangler i {source}. "
                "Kør scripts/calibrate_heat_load.py for at generere parametre."
            )
        return raw[candidates[0]]

    if override_yaml is not None:
        # Override-fil leverer kalibrerings-parametre (gaf, t_ref, baseline, …).
        raw_override = yaml.safe_load(Path(override_yaml).read_text())
        section = dict(_extract_section(raw_override, str(override_yaml)))

        # Merge: nettab er driftskonfig (ikke kalibrerings-output), så hvis
        # override ikke har den, hent fra case YAML.
        if "nettab" not in section:
            raw_case = yaml.safe_load(Path(case_yaml).read_text())
            case_section = _extract_section(raw_case, str(case_yaml))
            if "nettab" in case_section:
                section["nettab"] = case_section["nettab"]
    else:
        raw = yaml.safe_load(Path(case_yaml).read_text())
        section = _extract_section(raw, str(case_yaml))

    return HeatLoadParams.from_yaml_dict(section)


# ------------------------------------------------------------------------------
# Override: ekstern varmebehov-CSV (suspenderer syntese)
# ------------------------------------------------------------------------------

def apply_heat_csv_override(
    ds: xr.Dataset,
    csv_path: str | Path,
    *,
    column: str = "heat_mw_abvaerk",
    tz: str = "UTC",
    timestamp_col: Optional[str] = None,
) -> xr.Dataset:
    """Erstat heat_demand i datasættet med målte værdier fra ekstern CSV.

    Suspenderer den syntetiske varmelast-modellering. ``heat_gaf``,
    ``heat_guf`` og ``heat_nettab`` sættes til NaN — dekomponeringen
    giver ikke mening når kilden er målt data.

    Anvendelse i fx EnergyPRO-backtest hvor varmelast-syntese skal
    neutraliseres, så begge modeller får identisk varmebehov-input.

    Args:
        ds: Datasæt med ``time``-koordinat (tz-naive, UTC-internt).
        csv_path: Sti til CSV med målte varmebehov i MW.
        column: Kolonnenavn i CSV med varme i MW.
        tz: Tidszone for tidsstempler i CSV. Default ``"UTC"`` (matcher
            modellens interne format). Sæt fx ``"Europe/Copenhagen"``
            hvis CSV'en indeholder lokal tid med DST-spring.
        timestamp_col: Kolonnenavn for tidsstempler. Hvis None forsøges
            "timestamp", "time", "datetime", "hour_utc", "hour_dk" i den
            rækkefølge.

    Returns:
        Modificeret datasæt med ``heat_demand`` fra CSV og opdaterede
        attrs der dokumenterer kilden.

    Raises:
        FileNotFoundError: Hvis CSV-filen ikke findes.
        ValueError: Hvis kolonner mangler, der er negative værdier,
            eller >5% af modeltidsindekset ikke er dækket af CSV'en.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Heat-CSV ikke fundet: {csv_path}")

    df = pd.read_csv(csv_path)

    # Auto-detect tidsstempel-kolonne hvis ikke angivet
    if timestamp_col is None:
        for cand in ("timestamp", "time", "datetime", "hour_utc", "hour_dk"):
            if cand in df.columns:
                timestamp_col = cand
                break
        else:
            raise ValueError(
                f"Heat-CSV {csv_path.name} mangler tidsstempel-kolonne. "
                f"Tilgængelige: {list(df.columns)}. Angiv eksplicit via "
                f"timestamp_col."
            )

    if column not in df.columns:
        raise ValueError(
            f"Heat-CSV mangler kolonnen {column!r}. "
            f"Tilgængelige: {list(df.columns)}"
        )

    # Parse tidsstempler — strip evt. eksisterende tz, så vi har en
    # konsistent baseline før konvertering
    df[timestamp_col] = pd.to_datetime(df[timestamp_col])
    if df[timestamp_col].dt.tz is not None:
        df[timestamp_col] = df[timestamp_col].dt.tz_convert("UTC").dt.tz_localize(None)
    elif tz != "UTC":
        # Tidszone angivet og input er tz-naivt → tolk som lokal tid
        df[timestamp_col] = (
            df[timestamp_col]
              .dt.tz_localize(tz, ambiguous="infer", nonexistent="shift_forward")
              .dt.tz_convert("UTC")
              .dt.tz_localize(None)
        )

    df = df.set_index(timestamp_col).sort_index()
    # Håndtér evt. duplikater (fx fra DST fall-back i lokal tid)
    df = df[~df.index.duplicated(keep="first")]

    # Validér ikke-negative
    if (df[column] < 0).any():
        n_neg = int((df[column] < 0).sum())
        raise ValueError(
            f"Heat-CSV indeholder {n_neg} negative værdier i {column!r}. "
            f"Tjek datakilden."
        )

    # Reindex til modellens tidsakse
    model_idx = pd.DatetimeIndex(ds.time.values)
    series = df[column].reindex(model_idx)
    n_missing = int(series.isna().sum())
    if n_missing > 0:
        coverage = (1 - n_missing / len(model_idx)) * 100
        if n_missing > len(model_idx) * 0.05:
            raise ValueError(
                f"Heat-CSV mangler {n_missing}/{len(model_idx)} timer "
                f"({coverage:.1f}% dækning). For periode "
                f"{model_idx.min()} → {model_idx.max()} skal CSV'en dække "
                f"hele intervallet. Tjek tidsstempler og tidszone (--heat-csv-tz)."
            )
        # Mindre huller — interpoler lineært
        series = series.interpolate(method="linear").ffill().bfill()
        print(f"  Heat-CSV: {n_missing} huller udfyldt ved interpolation "
              f"(dækning {coverage:.2f}%)")

    # Anvend override
    ds = ds.copy()
    ds["heat_demand"] = (
        ("time",), series.values,
        {"units": "MW", "source": f"external_csv:{csv_path.name}"},
    )
    nan_vals = np.full(len(model_idx), np.nan)
    for varname in ("heat_gaf", "heat_guf", "heat_nettab"):
        if varname in ds.data_vars:
            ds[varname] = (
                ("time",), nan_vals,
                {"units": "MW", "note": "blanked when external heat CSV used"},
            )

    # Opdater attrs så det er sporbart i output
    ds.attrs["heat_load_source"] = f"external_csv:{csv_path}"
    ds.attrs["heat_load_csv_column"] = column
    ds.attrs["heat_load_csv_tz"] = tz
    ds.attrs["heat_load_synthesis_suspended"] = "true"

    return ds


# ------------------------------------------------------------------------------
# Tidsvarierende produktionsprofiler (fx solvarme) — fælles for begge loadere
# ------------------------------------------------------------------------------

def _attach_unit_profiles(cfg: CaseConfig, ds: xr.Dataset) -> xr.Dataset:
    """Tilføj 'profile_<unit>' for hver aktiv enhed med production_profile_path.

    For hver aktiv enhed med en profil-CSV: læs filen, reindekser til ds'
    tidsindeks (fill 0.0 udenfor dækning), og tilføj som datavariabel
    'profile_<unit>' i datasættet. model.build_model bruger disse til at sætte
    et tidsvarierende produktionsloft.

    Gotcha: profilen reindekseres på EKSAKT tidsstempel. CSV'en skal derfor
    dække kørslens periode/år — ellers bliver loftet 0 (fill) for de timer.
    """
    target_idx = pd.DatetimeIndex(ds.time.values)
    for unit_name, unit in cfg.units.items():
        if not unit.enabled or unit.production_profile_path is None:
            continue
        path = Path(unit.production_profile_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        df = pd.read_csv(path, parse_dates=["time"])
        df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert(None)
        s = (
            df.set_index("time").sort_index().iloc[:, 0]
              .reindex(target_idx, fill_value=0.0)
        )
        ds = ds.assign({f"profile_{unit_name}": ("time", s.values)})
    return ds


# ------------------------------------------------------------------------------
# Orkestrator: rigtig temperatur + spot + syntetisk varmelast
# ------------------------------------------------------------------------------

def load_external_data(
    cfg: CaseConfig,
    *,
    heat_load: Optional[HeatLoadParams] = None,
    dmi_area: str = "fyn",
    dmi_temp_shortname: str = "temp_mean_past1h",
    price_zone: str = "DK1",
    eur_dkk: float = DEFAULT_EUR_DKK,
    cache_dir: str | Path = "data/raw",
    force_refresh: bool = False,
    with_balancing: bool = False,
    heat_csv: Optional[str | Path] = None,
    heat_csv_column: str = "heat_mw_abvaerk",
    heat_csv_tz: str = "UTC",
) -> xr.Dataset:
    """
    Byg et halvrealistisk datasæt med rigtig DMI-temperatur og DK1-spot,
    og syntetisk varmebelastning ovenpå via dual-slope v2.

    Returnerer xr.Dataset med samme skema som generate_dummy_data
    plus dekomponeringen (heat_gaf, heat_guf, heat_nettab).

    heat_load SKAL være angivet (v2 har ikke længere default-parametre
    der giver fysisk mening). Brug `load_heat_load_params()` til at læse
    fra cases/*.yaml.
    """
    if heat_load is None:
        raise ValueError(
            "heat_load (HeatLoadParams) skal angives til load_external_data. "
            "Brug load_heat_load_params() til at læse fra case YAML."
        )

    cache_dir = Path(cache_dir)
    idx = make_time_index(cfg)
    start = idx.min().strftime("%Y-%m-%d")
    end = idx.max().strftime("%Y-%m-%d")

    t_raw = fetch_dmi_obs(
        dmi_temp_shortname, start, end,
        area=dmi_area, cache_dir=cache_dir, force_refresh=force_refresh,
    )
    spot_raw = fetch_spot_prices(
        price_zone, start, end,
        eur_dkk=eur_dkk, cache_dir=cache_dir, force_refresh=force_refresh,
    )

    # Reindeks til modellens akse. Temperatur er fysisk — interpolér over huller.
    # Spot er et fast hourly clearing-signal — forward-fill over (sjældne) huller.
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
            "source": "dmi_obs + energinet + synthetic_heat_load_v2",
            "dmi_area": dmi_area,
            "price_zone": price_zone,
            "eur_dkk": eur_dkk,
            "heat_load_params": json.dumps(heat_load.to_serializable()),
            "heat_load_version": "v2_dual_slope",
        },
    )

    if with_balancing:
        import pandas as pd
        start_iso = pd.Timestamp(cfg.time.start).strftime("%Y-%m-%dT%H:%M")
        end_iso = pd.Timestamp(cfg.time.end).strftime("%Y-%m-%dT%H:%M")
        bal = fetch_balance_prices(
            start=start_iso,
            end=end_iso,
            zone=cfg.electricity.spot_area,  # NB: YAML-feltet hedder spot_area
            cache_dir=cache_dir,
            force_refresh=force_refresh,
            target_index=pd.DatetimeIndex(ds.time.values),
        )
        ds = xr.merge([ds, bal])

    # Heat-CSV-override (suspenderer syntese). Anvendes til sidst så det
    # virker uafhængigt af om with_balancing er aktivt.
    if heat_csv is not None:
        ds = apply_heat_csv_override(
            ds, heat_csv, column=heat_csv_column, tz=heat_csv_tz,
        )

    ds = _attach_unit_profiles(cfg, ds)

    return ds


# ------------------------------------------------------------------------------
# Dummy-generator (fuldt offline fallback — uændret adfærd)
# ------------------------------------------------------------------------------

def generate_dummy_data(cfg: CaseConfig, seed: int = 42) -> xr.Dataset:
    """Rent syntetiske tidsserier — bruges når API ikke er tilgængelig."""
    rng = np.random.default_rng(seed)
    t = make_time_index(cfg)
    n = len(t)

    hour_of_year = (t - pd.Timestamp("2024-01-01")).total_seconds() / 3600.0
    year_frac = hour_of_year / 8760.0
    hour_of_day = t.hour + t.minute / 60.0

    t_ambient = (
        8.0
        - 10.0 * np.cos(2 * np.pi * (year_frac - 0.08))
        - 3.0 * np.cos(2 * np.pi * hour_of_day / 24.0)
        + rng.normal(0, 1.5, n)
    )

    base_annual = 12.3
    seasonal = 12.0 * np.cos(2 * np.pi * (year_frac - 0.08))
    daily = 2.5 * np.cos(2 * np.pi * (hour_of_day - 7) / 24.0)
    noise = rng.normal(0, 1.0, n)
    heat_demand = np.clip(base_annual + seasonal + daily + noise, a_min=2.0, a_max=None)

    base = 500.0
    daily_spot = 250.0 * (
        0.6 * np.cos(2 * np.pi * (hour_of_day - 18) / 24.0)
        + 0.4 * np.cos(2 * np.pi * (hour_of_day - 8) / 24.0)
    )
    weekday_multiplier = np.where(t.weekday >= 5, 0.7, 1.0)
    volatility = rng.normal(0, 200.0, n)
    neg_mask = rng.random(n) < 0.03
    volatility[neg_mask] -= 400.0
    spot_price = base + daily_spot * weekday_multiplier + volatility

    return xr.Dataset(
        data_vars={
            "heat_demand": ("time", heat_demand, {"units": "MW"}),
            "spot_price":  ("time", spot_price,  {"units": "DKK/MWh"}),
            "t_ambient":   ("time", t_ambient,   {"units": "degC"}),
        },
        coords={"time": t},
        attrs={"source": "dummy_generator", "seed": seed},
    )


# ------------------------------------------------------------------------------
# Billund-data loader (stub — aktiveres når årsdata modtages)
# ------------------------------------------------------------------------------

def load_billund_data(cfg: CaseConfig, path: str) -> xr.Dataset:
    """
    TODO (når årsdata kommer):
      - Indlæs udpumpningsmålere fra CSV
      - Differentiér akkumulerede målerstande
      - Interpolér uregelmæssige tidsstempler til hele timer
      - Summér korrekt ift. anlægstopologi (serie vs parallelt)
      - Kombinér med fetch_spot_prices() for spot
    """
    raise NotImplementedError("Aktiveres når Billund har leveret årsdata")
