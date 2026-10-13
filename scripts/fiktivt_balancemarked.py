"""fiktivt_balancemarked.py — byg et FIKTIVT balancemarked ud fra df-data.

Kopierer df-data-klonen og skalerer balancepriserne i en valgt periode, så hver
måned får samme gennemsnit som en referenceperiode. Standard: juli–december
2025 skaleres til snittet for januar–juni 2026 ("2026-niveau hele året").

    python scripts/fiktivt_balancemarked.py
    python run_case.py cases/billund_idag.yaml --data-source github \\
        --df-data-cache data/df-data-2026niveau --with-balancing \\
        --heat-csv data/billund_abvaerk_hourly_splejset_jun2026.csv

Hvad der skaleres (priszonen, standard DK1):

* aFRR- og mFRR-kapacitetspris for opregulering (afrr/, mfrr_cap/, kolonnerne
  UpPriceDKK og UpPriceEUR) ganges med én faktor pr. måned:
  faktor = snit(reference) / snit(måneden).
* Aktiveringspriserne for opregulering (imbalance/, aFRRVWAUp* og
  mFRRMarginalPriceUp*) skaleres på PRÆMIEN over spot: pris' = spot +
  faktor · (pris − spot), kun i kvarterer hvor prisen ligger over spot.
  faktor = snit af præmien (positiv del) i reference / samme i måneden.

Hvad der IKKE røres: spot, vejr, mængder (indkøbt og aktiveret MW),
nedregulering og alle måneder uden for perioden. Timingen inden for måneden og
sammenhængen med spotprisen bevares. Måneder regnes i dansk tid.

Resultatet er IKKE data. Det er et scenarie. Målmappen får en FIKTIVT_MARKED.md
og en faktorer.json, så det altid kan ses, hvad der er ændret.

Kilden ændres aldrig. Målmappen skal ligge uden for kilden og overskrives kun
med --overskriv. Kopien beholder .git, fordi run_case.py ellers kloner df-data
ned over den.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_EUR_DKK = 7.45
KAP = [("afrr", "aFRR-kapacitet"), ("mfrr_cap", "mFRR-kapacitet")]
AKT = [("aFRRVWAUpDKK", "aFRRVWAUpEUR", "aFRR-aktivering"),
       ("mFRRMarginalPriceUpDKK", "mFRRMarginalPriceUpEUR", "mFRR-aktivering")]


def maaneder(spec: str) -> list[str]:
    """'2025-07..2025-12' -> ['2025-07', ..., '2025-12']."""
    a, _, b = spec.partition("..")
    if not b:
        raise ValueError(f"Periode skal skrives som ÅÅÅÅ-MM..ÅÅÅÅ-MM, fik {spec!r}")
    return [p.strftime("%Y-%m") for p in pd.period_range(a, b, freq="M")]


def _dk_maaned(utc: pd.Series) -> pd.Series:
    t = pd.to_datetime(utc)
    if t.dt.tz is None:
        t = t.dt.tz_localize("UTC")
    return t.dt.tz_convert("Europe/Copenhagen").dt.strftime("%Y-%m")


def _aar(mdr: list[str]) -> list[int]:
    return sorted({int(m[:4]) for m in mdr})


def _laes(mappe: Path, ds: str, zone: str, aar: list[int]) -> dict[int, pd.DataFrame]:
    ud = {}
    for y in aar:
        f = mappe / ds / f"{zone}_{y}.csv"
        if not f.exists():
            raise FileNotFoundError(f"Mangler {f}. Er df-data hentet og opdateret (git -C data/df-data pull)?")
        d = pd.read_csv(f)
        d["_mdr"] = _dk_maaned(d["TimeUTC"])
        ud[y] = d
    return ud


def byg(kilde: Path, maal: Path, periode: list[str], reference: list[str],
        zone: str = "DK1", eur_dkk: float = DEFAULT_EUR_DKK, overskriv: bool = False) -> dict:
    kilde, maal = kilde.resolve(), maal.resolve()
    if maal == kilde or kilde in maal.parents or maal in kilde.parents:
        raise ValueError("Målmappen må hverken være kilden, ligge i den eller indeholde den.")
    if not (kilde / ".git").exists():
        raise FileNotFoundError(f"{kilde} er ikke en df-data-klon (mangler .git).")
    if set(periode) & set(reference):
        raise ValueError("Periode og reference må ikke overlappe.")
    if maal.exists():
        if not overskriv:
            raise FileExistsError(f"{maal} findes. Brug --overskriv for at bygge den igen.")
        shutil.rmtree(maal)
    shutil.copytree(kilde, maal, symlinks=False)

    aar = sorted(set(_aar(periode)) | set(_aar(reference)))
    rapport: dict = {"kilde": str(kilde), "zone": zone, "periode": periode,
                     "reference": reference, "eur_dkk": eur_dkk, "faktorer": {}}

    for ds, navn in KAP:
        frames = _laes(maal, ds, zone, aar)
        alle = pd.concat(frames.values())
        ref = alle[alle._mdr.isin(reference)]["UpPriceDKK"].mean()
        fak = {}
        for m in periode:
            snit = alle[alle._mdr == m]["UpPriceDKK"].mean()
            fak[m] = float(ref / snit) if snit and snit > 0 else 1.0
        for y, d in frames.items():
            for m, f in fak.items():
                sel = d._mdr == m
                for c in ("UpPriceDKK", "UpPriceEUR"):
                    if c in d:
                        d.loc[sel, c] = d.loc[sel, c] * f
            d.drop(columns="_mdr").to_csv(maal / ds / f"{zone}_{y}.csv", index=False)
        rapport["faktorer"][navn] = {"reference_snit": round(float(ref), 2),
                                     **{m: round(f, 4) for m, f in fak.items()}}

    frames = _laes(maal, "imbalance", zone, aar)
    alle = pd.concat(frames.values())
    for col_dkk, col_eur, navn in AKT:
        praemie = lambda d: (d[col_dkk] - d["SpotPriceEUR"] * eur_dkk).clip(lower=0)
        ref = praemie(alle[alle._mdr.isin(reference)]).mean()
        fak = {}
        for m in periode:
            snit = praemie(alle[alle._mdr == m]).mean()
            fak[m] = float(ref / snit) if snit and snit > 0 else 1.0
        for d in frames.values():
            for m, f in fak.items():
                spot_dkk = d["SpotPriceEUR"] * eur_dkk
                sel = (d._mdr == m) & d[col_dkk].notna() & (d[col_dkk] > spot_dkk)
                d.loc[sel, col_dkk] = spot_dkk[sel] + f * (d.loc[sel, col_dkk] - spot_dkk[sel])
                if col_eur in d:
                    sp = d["SpotPriceEUR"]
                    sel_e = sel & d[col_eur].notna()
                    d.loc[sel_e, col_eur] = sp[sel_e] + f * (d.loc[sel_e, col_eur] - sp[sel_e])
        rapport["faktorer"][navn] = {"reference_praemie_snit": round(float(ref), 2),
                                     **{m: round(f, 4) for m, f in fak.items()}}
    for y, d in frames.items():
        d.drop(columns="_mdr").to_csv(maal / "imbalance" / f"{zone}_{y}.csv", index=False)

    (maal / "faktorer.json").write_text(json.dumps(rapport, indent=1, ensure_ascii=False), encoding="utf-8")
    linjer = ["# FIKTIVT BALANCEMARKED — ikke data", "",
              f"Bygget af `scripts/fiktivt_balancemarked.py` ud fra `{kilde}`.", "",
              f"Balancepriserne for opregulering i {zone} er skaleret i {periode[0]}–{periode[-1]}, "
              f"så hver måned har samme gennemsnit som {reference[0]}–{reference[-1]}. "
              "Kapacitetspriser ganges med en faktor; aktiveringspriser skaleres på præmien over spot. "
              "Spot, vejr, mængder og alle andre måneder er urørt.", "",
              "| Måned | " + " | ".join(rapport["faktorer"]) + " |",
              "|---|" + "---:|" * len(rapport["faktorer"])]
    for m in periode:
        linjer.append(f"| {m} | " + " | ".join(f"{rapport['faktorer'][k][m]:.3f}" for k in rapport["faktorer"]) + " |")
    linjer += ["", "Tal regnet på dette marked er et scenarie og må ikke præsenteres som data."]
    (maal / "FIKTIVT_MARKED.md").write_text("\n".join(linjer) + "\n", encoding="utf-8")
    return rapport


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kilde", default=str(REPO / "data/df-data"), help="df-data-klonen (default: data/df-data)")
    ap.add_argument("--maal", default=str(REPO / "data/df-data-2026niveau"),
                    help="målmappe (default: data/df-data-2026niveau, git-ignoreret)")
    ap.add_argument("--periode", default="2025-07..2025-12", help="måneder der skaleres (default 2025-07..2025-12)")
    ap.add_argument("--reference", default="2026-01..2026-06", help="referenceperiode (default 2026-01..2026-06)")
    ap.add_argument("--zone", default="DK1")
    ap.add_argument("--eur-dkk", type=float, default=DEFAULT_EUR_DKK)
    ap.add_argument("--overskriv", action="store_true", help="byg målmappen igen, hvis den findes")
    a = ap.parse_args(argv)
    try:
        r = byg(Path(a.kilde), Path(a.maal), maaneder(a.periode), maaneder(a.reference),
                zone=a.zone, eur_dkk=a.eur_dkk, overskriv=a.overskriv)
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        print(f"FEJL: {e}", file=sys.stderr)
        return 1
    print(f"Fiktivt marked bygget i {a.maal}")
    for navn, f in r["faktorer"].items():
        mdr = ", ".join(f"{m[5:]}: {v:.2f}" for m, v in f.items() if m[:2] == "20")
        print(f"  {navn:16s} {mdr}")
    print("Brug det med:  --df-data-cache", a.maal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
