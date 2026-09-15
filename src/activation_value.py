"""
src/activation_value.py — kovarians-korrekt aktiveringsværdi (E[α·p]).

Erstatter den gamle E[α]×E[p]-tilgang, hvor en time-midlet aktiveringsfraktion
ganges med en time-midlet aktiveringspris. Produktet af to time-gennemsnit
undervurderer systematisk indtægten når aktivering og pris hænger sammen inden
for timen (scarcity-timer): de få sub-intervaller med ekstreme priser er præcis
dem hvor enheden aktiveres.

Modellen for værkets budstrategi (jf. interview med John/Jens, Billund):
en aktiveringspris sættes som spot + et tillæg (markup). Enheden aktiveres i et
sub-interval τ når den realiserede aktiveringspris clearer buddet:

    aktiveret(τ)  ⇔  p_act(τ) ≥ spot(τ) + markup

Aktiveringsværdi-koefficienten per time t (DKK pr. reserveret MW pr. time):

    av(t) = Σ_{τ ∈ t}  Δτ · 1[ p_act(τ) ≥ spot(τ) + markup ] · ( p_act(τ) + spot(τ) + el_cost_flat )

hvor (p_act + spot + el_cost_flat) er den fulde værdi pr. MWh op-reguleret el:
aktiveringsprisen plus den sparede forbrugsomkostning (spot + tarif + elafgift),
identisk med den gamle models pr.-MWh-værdi — kun aggregeringen ændres.

Indikator og pris evalueres i SAMME sub-interval, så kovariansen fanges eksakt.
Resultatet er en forudberegnet konstant per time, så optimeringen forbliver
lineær: activation_revenue = Σ_t av(t) · r(t).

Funktionen returnerer også clear_fraction(t) ∈ [0,1] — andelen af timen hvor
buddet clearer — der bruges som den effektive aktiveringsfraktion på varmesiden
(forventet varmereduktion = clear_fraction · COP · r), konsistent med revenue.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ActivationValue:
    """Time-opløste serier udledt af sub-time-priser.

    av:             DKK pr. reserveret MW pr. time (BRUTTO indtægtskoefficient,
                    p_act + spot + el_cost_flat — bruges uændret i objektivet)
    av_payment:     DKK pr. reserveret MW pr. time (NETTO aktiveringsbetaling,
                    kun p_act — samme aggregering og clearing som av, men uden
                    forbrugsmodregningen spot + el_cost_flat). Diagnostik/
                    rapportering; objektivet rører den ikke.
    clear_fraction: andel af timen hvor buddet clearer [0,1] (varmeside-α)
    """
    av: pd.Series
    av_payment: pd.Series
    clear_fraction: pd.Series


def compute_activation_value(
    price_act: pd.Series,
    spot: pd.Series,
    *,
    markup: float,
    el_cost_flat: float,
    dt_h: float = 0.25,
    direction: str = "up",
    model: str = "clear",
    system_share: pd.Series | None = None,
    k: float = 1.0,
    ramp_dkk_mwh: float | None = None,
) -> ActivationValue:
    """Beregn kovarians-korrekt aktiveringsværdi fra sub-time-serier.

    Args:
        price_act:    aktiveringspris [DKK/MWh], sub-time (typisk 15-min),
                      DatetimeIndex.
        spot:         spotpris [DKK/MWh], reindekseres til price_act's indeks
                      (forward-fill — spot er konstant inden for sit kvarter).
        markup:       budtillæg [DKK/MWh]. Op: spot + markup. Ned: spot − markup.
        el_cost_flat: tarif + elafgift [DKK/MWh] (sparet forbrug udover spot).
        dt_h:         sub-interval-længde i timer (0.25 for 15-min).
        direction:    "up" (clearer når p_act ≥ spot+markup) eller
                      "down" (clearer når p_act ≤ spot−markup).
        model:        aktiveret andel f(τ) af reserveret MW (se
                      config.ActivationMarket): 'clear' (default, uændret),
                      'system_share' eller 'ramp'.
        system_share: α(τ) ∈ [0,1], systemets aktiverede volumen / indkøbt
                      kapacitet. Kræves af 'system_share'.
        k:            skalering af α ('system_share').
        ramp_dkk_mwh: rampebredde ('ramp').

    Returns:
        ActivationValue med time-opløste av og clear_fraction.
    """
    if direction not in ("up", "down"):
        raise ValueError(f"direction skal være 'up'/'down', fik {direction!r}")

    p = price_act.astype(float).sort_index()
    p = p[~p.index.duplicated(keep="first")]

    # Reindeks spot til aktiveringsprisens grid (ffill: spot konstant i kvarteret)
    s = spot.astype(float).sort_index()
    s = s[~s.index.duplicated(keep="first")]
    s = s.reindex(p.index).ffill().bfill()

    bid = s + markup if direction == "up" else s - markup
    clears = (p >= bid) if direction == "up" else (p <= bid)
    clears = clears.astype(float)

    # Aktiveret andel f(τ). 'clear' er den oprindelige indikator — uændret.
    if model == "clear":
        pass
    elif model == "system_share":
        if system_share is None:
            raise ValueError("model='system_share' kræver system_share-serien")
        a = system_share.astype(float).sort_index()
        a = a[~a.index.duplicated(keep="first")]
        a = a.reindex(p.index).ffill().fillna(0.0).clip(0.0, 1.0)
        clears = clears * (k * a).clip(0.0, 1.0)
    elif model == "ramp":
        if ramp_dkk_mwh is None or ramp_dkk_mwh <= 0:
            raise ValueError("model='ramp' kræver ramp_dkk_mwh > 0")
        afstand = (p - bid) if direction == "up" else (bid - p)
        clears = (afstand / ramp_dkk_mwh).clip(0.0, 1.0)
    else:
        raise ValueError(f"ukendt aktiveringsmodel {model!r}")

    # Fuld (brutto) værdi pr. MWh op-reguleret el i de clearende intervaller.
    value_per_mwh = p + s + el_cost_flat
    value_sub = dt_h * clears * value_per_mwh          # DKK pr. MW pr. sub-interval
    # Netto aktiveringsbetaling: kun aktiveringsprisen p, samme clearing/grid.
    # Differensen (av − av_payment) = forbrugsmodregningen (spot + el_cost_flat).
    payment_sub = dt_h * clears * p                    # DKK pr. MW pr. sub-interval
    cleared_h_sub = dt_h * clears                      # aktiverede timer pr. sub-interval

    av_hourly = value_sub.resample("1h").sum()
    av_payment_hourly = payment_sub.resample("1h").sum()
    clear_fraction_hourly = cleared_h_sub.resample("1h").sum().clip(0.0, 1.0)

    return ActivationValue(
        av=av_hourly,
        av_payment=av_payment_hourly,
        clear_fraction=clear_fraction_hourly,
    )
