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

    av:             DKK pr. reserveret MW pr. time (indtægtskoefficient)
    clear_fraction: andel af timen hvor buddet clearer [0,1] (varmeside-α)
    """
    av: pd.Series
    clear_fraction: pd.Series


def compute_activation_value(
    price_act: pd.Series,
    spot: pd.Series,
    *,
    markup: float,
    el_cost_flat: float,
    dt_h: float = 0.25,
    direction: str = "up",
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

    # Fuld værdi pr. MWh op-reguleret el i de clearende intervaller.
    value_per_mwh = p + s + el_cost_flat
    value_sub = dt_h * clears * value_per_mwh          # DKK pr. MW pr. sub-interval
    cleared_h_sub = dt_h * clears                      # timer clearet pr. sub-interval

    av_hourly = value_sub.resample("1h").sum()
    clear_fraction_hourly = cleared_h_sub.resample("1h").sum().clip(0.0, 1.0)

    return ActivationValue(av=av_hourly, clear_fraction=clear_fraction_hourly)
