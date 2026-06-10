"""Nettab — temperatur- og flow-drevet netværkstabsmodel.

Afleder den to-led fysiske model:

    nettab_MW(t) = a · (T_pipe(t) − T_jord(t)) + c · load_MW(t)

ud fra værkets typiske oplysninger: årligt nettab (MWh eller %) samt
sommer- og vinter-temperaturforhold. Beregner a og c eksakt, givet en
antagelse om fordelingen mellem konduktivt og flow-led (default 0,75).

Det konduktive led repræsenterer isolations- og jordtab; flow-leddet
repræsenterer konvektive tab i armaturer, brønde og substationer, der
skalerer med massestrømmen (proxyet ved load).

T_jord understøtter to modes:
  - Statisk (default): sæson-cosinus baseret på kalender-måned alene.
    Samme T_jord for alle januar-dage uanset år.
  - Dynamisk: T_jord = avg + damping · (EMA(T_out, τ) − T_out_ref).
    Aktivér med `t_jord_dynamic: true` i YAML. Tidskonstant default 30 dage,
    dæmpning 0.5 — matcher fysisk diffusion ved ~1 m dybde i dansk jord.
    Giver kolde januar-dage med, varme januar-dage uden.

Default-fordelingen 0,75 (konduktiv andel) er valgt ud fra Billund-fittet
(faktisk 0,77), og er typisk for et dansk fjernvarmenet.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional
import numpy as np
import pandas as pd


@dataclass
class NettabCoefficients:
    """Afledte koefficienter og hjælpefunktioner til nettabsmodellen."""
    a_konduktiv: float           # MW/K
    c_flow: float                # dimensionsløs
    Q_target_mwh: float          # årligt nettabs-måltal
    konduktiv_andel: float       # faktisk realiseret andel (≈ input)
    T_pipe_fn: Callable          # T_out -> T_pipe
    T_jord_series: np.ndarray    # præberegnet T_jord per time (statisk el. dynamisk)
    t_jord_mode: str             # 'static' eller 'dynamic' — diagnose-info


def compute_T_jord(
    cfg: dict,
    t_out: np.ndarray,
    timestamps: pd.DatetimeIndex,
) -> tuple[np.ndarray, str]:
    """Beregn T_jord-tidsserie ud fra cfg, T_out og timestamps.

    Statisk mode (default): sæson-cosinus på kalender-måned.
        T_jord(måned) = t_jord_avg − t_jord_amp · cos(2π · (måned − 2)/12)

    Dynamisk mode (t_jord_dynamic: true): EMA-baseret damped-følger.
        T_jord(t) = t_jord_avg + damping · (EMA(T_out, τ) − t_out_ref)
        med EMA warm-startet på t_out_ref for at undgå initialiseringsbias.

    Returns
    -------
    (T_jord_series, mode_label) hvor mode_label er 'static' eller 'dynamic'
    """
    t_jord_avg = float(cfg.get('t_jord_avg', 9.0))

    if cfg.get('t_jord_dynamic', False):
        ema_days = float(cfg.get('t_jord_ema_days', 30.0))
        damping = float(cfg.get('t_jord_damping', 0.5))
        t_out_ref = float(cfg.get('t_jord_t_out_ref', 8.0))

        if not (0.0 <= damping <= 1.0):
            raise ValueError("t_jord_damping skal være mellem 0 og 1")
        if ema_days <= 0:
            raise ValueError("t_jord_ema_days skal være positiv")

        # EMA i timer; warm-start på klimanormal for at undgå initialiseringsbias
        ema_span_hours = ema_days * 24.0
        warmup_n = int(ema_span_hours * 5)   # 5 tidskonstanter ~ fuld konvergens
        full = np.concatenate([np.full(warmup_n, t_out_ref), t_out])
        ema_full = pd.Series(full).ewm(span=ema_span_hours, adjust=False).mean().values
        t_out_ema = ema_full[warmup_n:]

        T_jord = t_jord_avg + damping * (t_out_ema - t_out_ref)
        return T_jord, 'dynamic'
    else:
        # Statisk cosinus — koldest i februar (måned 2), varmest i august
        t_jord_amp = float(cfg.get('t_jord_amp', 4.0))
        months = timestamps.month.values.astype(float)
        T_jord = t_jord_avg - t_jord_amp * np.cos(2 * np.pi * (months - 2.0) / 12.0)
        return T_jord, 'static'


def build_nettab_model(
    cfg: dict,
    annual_production_mwh: float,
    t_out: np.ndarray,
    timestamps: pd.DatetimeIndex,
) -> NettabCoefficients:
    """Afled nettab-koefficienter fra YAML-config + årsproduktion + T_out.

    Parameters
    ----------
    cfg : dict
        Indholdet af YAML-sektionen 'nettab'.
    annual_production_mwh : float
        Total ab værk-produktion = solgt + nettab (inkl. nettab).
    t_out : np.ndarray
        Hourly udetemperaturer (samme længde som timestamps).
    timestamps : pd.DatetimeIndex
        Tidsindeks for t_out.

    Returns
    -------
    NettabCoefficients
    """
    # --- 1) Årligt nettabs-måltal ---
    if 'aarligt_nettab_mwh' in cfg:
        Q = float(cfg['aarligt_nettab_mwh'])
    elif 'aarligt_nettab_pct' in cfg:
        Q = float(cfg['aarligt_nettab_pct']) * annual_production_mwh
    else:
        raise ValueError(
            "Konfiguration mangler. Angiv enten 'aarligt_nettab_mwh' "
            "eller 'aarligt_nettab_pct' i nettab-sektionen."
        )

    # --- 2) T_pipe-kurve (lineær mellem sommer- og vinter-anker) ---
    T_pipe_sum = (cfg['sommer']['t_frem'] + cfg['sommer']['t_retur']) / 2.0
    T_pipe_win = (cfg['vinter']['t_frem'] + cfg['vinter']['t_retur']) / 2.0
    T_out_sum = float(cfg['sommer'].get('t_ude', 16.0))
    T_out_win = float(cfg['vinter'].get('t_ude', 1.0))

    if T_out_sum <= T_out_win:
        raise ValueError("sommer.t_ude skal være højere end vinter.t_ude.")

    def T_pipe(T_out):
        T_out = np.asarray(T_out, dtype=float)
        T_clip = np.clip(T_out, T_out_win, T_out_sum)
        frac = (T_clip - T_out_win) / (T_out_sum - T_out_win)
        return T_pipe_win + frac * (T_pipe_sum - T_pipe_win)

    # --- 3) T_jord-tidsserie (statisk eller dynamisk) ---
    T_jord_series, mode = compute_T_jord(cfg, t_out, timestamps)

    # --- 4) Beregn drive-integral over hele perioden (faktisk T_out) ---
    T_pipe_series = T_pipe(t_out)
    drive_series = T_pipe_series - T_jord_series
    drive_hours_sum = float(drive_series.sum())  # K·h
    if drive_hours_sum <= 0:
        raise ValueError(
            f"Drive-integral ikke-positiv ({drive_hours_sum:.1f} K·h). "
            f"Tjek sommer/vinter-anker og T_jord-parametre."
        )

    # --- 5) Afled a og c ---
    ka = float(cfg.get('konduktiv_andel', 0.75))
    if not 0.0 < ka < 1.0:
        raise ValueError("konduktiv_andel skal være mellem 0 og 1.")

    annual_load_mwh = annual_production_mwh - Q
    if annual_load_mwh <= 0:
        raise ValueError(
            f"Inkonsistent input: nettab Q ({Q:.0f} MWh) er ≥ "
            f"annual_production_mwh ({annual_production_mwh:.0f} MWh)."
        )

    a = ka * Q / drive_hours_sum
    c = (1.0 - ka) * Q / annual_load_mwh

    return NettabCoefficients(
        a_konduktiv=a,
        c_flow=c,
        Q_target_mwh=Q,
        konduktiv_andel=ka,
        T_pipe_fn=T_pipe,
        T_jord_series=T_jord_series,
        t_jord_mode=mode,
    )


def nettab_MW(
    coef: NettabCoefficients,
    T_out: np.ndarray,
    load_MW: np.ndarray,
) -> np.ndarray:
    """Beregn nettab i MW for hele tidsperioden.

    T_jord hentes fra præberegnet serie i coef (matchet til timestamps
    der blev brugt under build_nettab_model). Indeks skal være konsistent
    mellem build og evaluering.
    """
    drive = coef.T_pipe_fn(T_out) - coef.T_jord_series
    return coef.a_konduktiv * drive + coef.c_flow * np.asarray(load_MW)


def hourly_profile(
    coef: NettabCoefficients,
    timestamps: pd.DatetimeIndex,
    T_out: np.ndarray,
    load_MW: np.ndarray,
) -> pd.DataFrame:
    """Producer en time-DataFrame med temperaturer, drive og nettab."""
    nt = nettab_MW(coef, T_out, load_MW)
    return pd.DataFrame({
        'timestamp': timestamps,
        'T_out': T_out,
        'load_MW': load_MW,
        'T_pipe': coef.T_pipe_fn(T_out),
        'T_jord': coef.T_jord_series,
        'drive_K': coef.T_pipe_fn(T_out) - coef.T_jord_series,
        'nettab_MW': nt,
    })


def monthly_summary(profile_df: pd.DataFrame) -> pd.DataFrame:
    """Aggreger time-profilen til månedlig nettab MW/MWh/%."""
    df = profile_df.copy()
    df['ym'] = df['timestamp'].dt.to_period('M')
    g = df.groupby('ym', observed=True)
    out = pd.DataFrame({
        'load_MWh': g['load_MW'].sum(),
        'nettab_MWh': g['nettab_MW'].sum(),
        'nettab_MW_middel': g['nettab_MW'].mean(),
        'T_jord_middel': g['T_jord'].mean(),
        'T_out_middel': g['T_out'].mean(),
    })
    out['nettab_pct'] = out['nettab_MWh'] / out['load_MWh']
    return out


def describe(coef: NettabCoefficients, annual_production_mwh: float) -> str:
    """Menneskelæselig sammenfatning af de afledte koefficienter."""
    return (
        f"Nettab-model afledt ({coef.t_jord_mode} T_jord):\n"
        f"  a (konduktiv)    = {coef.a_konduktiv:.4f} MW/K\n"
        f"  c (flow)         = {coef.c_flow:.4f}\n"
        f"  Konduktiv andel  = {coef.konduktiv_andel:.0%}\n"
        f"  T_jord min/max   = {coef.T_jord_series.min():.1f} / "
        f"{coef.T_jord_series.max():.1f} °C\n"
        f"  Årligt måltal    = {coef.Q_target_mwh:,.0f} MWh "
        f"({coef.Q_target_mwh / annual_production_mwh * 100:.1f}% af produktion)\n"
    )
