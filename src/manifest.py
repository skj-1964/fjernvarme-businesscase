"""
manifest.py — skriver en selvbeskrivende følgeseddel (JSON) per kørsel.

Hver kørsel lægger — ud over CSV/PNG — også {stem}_manifest.json i output/.
Manifestet er den fælles kontrakt mellem modellen og varmeflex.dk:
hjemmesiden og run_scenario læser udelukkende herfra, aldrig fra filnavne
eller skærm-output. Samme mekanisme i fase 1 (manuelle kørsler) og fase 2
(live solver) — kun bagsiden af run_scenario skifter.

Feltnavnene i den økonomiske dekomponering er bekræftet mod kildekoden:
  - balanceindtægt: balancing.summarize_reserves → capacity_revenue_dkk +
    activation_price_revenue_dkk, summeret per marked (aFRR/mFRR).
  - tank-arbitrage: −storage_net · shadow_price_heat · dt (spejler
    reporting._tank_value_hourly; kun ved LP-duals).
  - CO2: brændsel_MWh · co2_emissions_per_mwh_fuel for brændselsenheder.
"""
from __future__ import annotations
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .balancing import summarize_reserves


def _git_commit() -> str:
    """Kort git-hash til sporbarhed. 'ukendt' hvis ikke et git-repo."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "ukendt"


def _datakilde_label(args) -> str:
    if getattr(args, "data_source", None) == "github":
        return "github"
    if getattr(args, "external", False):
        return "external"
    return "dummy"


def _date10(v) -> str:
    """Returnér YYYY-MM-DD. cfg.time.start/end kan være datetime (fra YAML)
    eller str (efter --start/--end-override) — begge håndteres."""
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    return str(v)[:10]


def _clean_status(raw) -> str:
    """Modellen gemmer status som tuple ('ok', 'optimal') (str i .nc-attrs).
    Til sporbarhed er den rene tilstand mere brugbar end den rå tuple."""
    s = str(raw)
    return "optimal" if "optimal" in s else s


def _balance_income(result, data) -> dict | None:
    """aFRR/mFRR-indtægt per marked = kapacitet + aktiveringspris.

    Henter de bekræftede felter fra balancing.summarize_reserves, som
    returnerer {"aFRR": {unit: {...}}, "mFRR": {unit: {...}}}.
    """
    summ = summarize_reserves(result, data)
    if not summ:
        return None
    pr_market = {}
    total = 0.0
    for label, units in summ.items():            # label: "aFRR" / "mFRR"
        m = 0.0
        for entry in units.values():
            m += float(entry.get("capacity_revenue_dkk", 0.0))
            m += float(entry.get("activation_price_revenue_dkk", 0.0))
        pr_market[label.lower()] = round(m, 0)
        total += m
    return {
        "i_alt": round(total, 0),
        "afrr": pr_market.get("afrr"),
        "mfrr": pr_market.get("mfrr"),
    }


def _tank_arbitrage_dkk(result, dt: float) -> float | None:
    """Dual-baseret arbitrageværdi, summeret over alle lagre.

    Kun tilgængelig når duals er udtrukket (LP-kørsel) og lager er aktivt.
    Returnerer None ved MILP (ingen duals) — det er forventet og ærligt.
    """
    if ("shadow_price_heat" not in result.data_vars
            or "storage_net" not in result.data_vars):
        return None
    sp = result["shadow_price_heat"]
    net = result["storage_net"]
    return float((-net * sp * dt).sum())


def _co2_ton(result, cfg, dt: float) -> float:
    """Fysiske CO2-udledninger fra brændselsenheder (biomasse = neutralt).

    For hver enabled enhed med co2_emissions_per_mwh_fuel > 0:
        brændsel_MWh = varme_MWh / eta_fuel_to_heat
        CO2_ton      = brændsel_MWh · co2_emissions_per_mwh_fuel
    """
    hp = result["heat_prod"]
    total = 0.0
    for name in hp.unit.values:
        unit = cfg.units[str(name)]
        factor = getattr(unit, "co2_emissions_per_mwh_fuel", 0.0) or 0.0
        eta = getattr(unit, "eta_fuel_to_heat", None)
        if factor <= 0 or not eta:
            continue
        heat_mwh = float(hp.sel(unit=name).sum()) * dt
        total += (heat_mwh / eta) * factor
    return round(total, 1)


def write_manifest(result, data, cfg, kpi, args, stem: str, out_dir: Path) -> dict:
    """Skriv {stem}_manifest.json til out_dir og returnér manifestet."""
    dt = pd.to_timedelta(
        data.time.diff("time").mean().values).total_seconds() / 3600.0

    demand_mwh = float((data["heat_demand"] * dt).sum())
    production_mwh = float((result["heat_prod"].sum("time") * dt).sum())
    nettab_mwh = (float((data["heat_nettab"] * dt).sum())
                  if "heat_nettab" in data.data_vars else None)

    aktive = [u for u, unit in cfg.units.items() if unit.enabled]
    inaktive = [u for u, unit in cfg.units.items() if not unit.enabled]

    har_balance = any(
        str(v).startswith(("r_afrr_", "r_mfrr_", "r_up_el_"))
        for v in result.data_vars
    )

    tank_arb = _tank_arbitrage_dkk(result, dt)

    manifest = {
        "schema_version": "1.0",
        "scenarie_id": stem,
        "meta": {
            "case_name": cfg.meta.get("case_name", stem),
            "titel": cfg.meta.get("titel", cfg.meta.get("case_name", stem)),
            "beskrivelse": cfg.meta.get("description", ""),
            "gruppe": cfg.meta.get("gruppe"),
            "rolle_i_gruppe": cfg.meta.get("rolle"),
        },
        "koersel": {
            "datakilde": _datakilde_label(args),
            "periode": {
                "start": _date10(cfg.time.start),
                "slut": _date10(cfg.time.end),
                "oploesning": getattr(cfg.time, "resolution", "1h"),
            },
            "med_balancering": har_balance,
            "enheder_til": aktive,
            "enheder_fra": inaktive,
            "overrides": list(getattr(args, "set_overrides", []) or []),
            "foresight_haircut_pct": None,   # sættes i fortolkningslaget, ikke her
        },
        "sporbarhed": {
            "model_commit": _git_commit(),
            "koert_tidspunkt": datetime.now(timezone.utc).isoformat(),
            "solve_status": _clean_status(result.attrs.get("status", "ukendt")),
            "model_type": "MILP" if result.attrs.get("is_milp", 0) else "LP",
        },
        "noegletal": {
            "objektiv_dkk": round(float(result.attrs.get("objective_value", 0)), 0),
            "varmeefterspoergsel_mwh": round(demand_mwh, 1),
            "samlet_produktion_mwh": round(production_mwh, 1),
            "nettab_mwh": round(nettab_mwh, 1) if nettab_mwh is not None else None,
            "nettab_pct": (round(nettab_mwh / demand_mwh * 100, 1)
                           if nettab_mwh and demand_mwh else None),
            "balanceindtaegt_dkk": _balance_income(result, data),
            "tank_arbitrage_dkk": round(tank_arb, 0) if tank_arb is not None else None,
            "co2_ton": _co2_ton(result, cfg, dt),
            # spotresultat_dkk udelades bevidst i v1.0 — tilføjes i v1.1 når den
            # reneste kilde til spot-dekomponeringen er bekræftet (el-flow ×
            # spotpris). Objektiv, balance og tank dækker den differentielle
            # business case i mellemtiden.
        },
        "enheder": [
            {
                "navn": r["unit"],
                "p_max_mw": float(r["p_max_mw"]),
                "produktion_mwh": float(r["production_mwh"]),
                "andel_pct": float(r["share_pct"]),
                "fuldlasttimer": int(r["operating_hours"]),
                "kapacitetsfaktor_pct": float(r["capacity_factor_pct"]),
            }
            for _, r in kpi.iterrows()
        ],
        "filer": {
            "manifest":     f"{stem}_manifest.json",
            "hourly_csv":   f"{stem}_hourly.csv",
            "kpi_csv":      f"{stem}_kpi.csv",
            "monthly_csv":  f"{stem}_monthly.csv",
            "dispatch_png": f"{stem}_dispatch.png",
        },
    }

    path = out_dir / f"{stem}_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"Manifest gemt: {path.name}")
    return manifest
