"""Byg en kopi af df-data med en ændret spotpris til scenariekørsler.

Eksempler (køres fra modelrepoets rod):
  python lav_spotscenarie.py --navn spot_plus10 --niveau 1.10
  python lav_spotscenarie.py --navn spot_spredning150 --spredning 1.5

  --niveau k     alle spotpriser ganges med k
  --spredning s  hver måneds gennemsnit bevares; afvigelsen fra gennemsnittet
                 ganges med s (s > 1 giver større udsving, s < 1 mindre)

Kopien lægges i data/df-data-<navn> (git-ignoreret) og bruges med
  --df-data-cache data/df-data-<navn>
Kun spotfilerne for den valgte zone ændres; balance, vejr m.m. er urørt.
"""
import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

p = argparse.ArgumentParser()
p.add_argument("--navn", required=True)
p.add_argument("--zone", default="DK1")
p.add_argument("--niveau", type=float, default=1.0)
p.add_argument("--spredning", type=float, default=1.0)
p.add_argument("--kilde", default="data/df-data")
p.add_argument("--overskriv", action="store_true")
a = p.parse_args()

kilde = Path(a.kilde)
maal = Path(f"data/df-data-{a.navn}")
if maal.exists():
    if not a.overskriv:
        raise SystemExit(f"{maal} findes. Brug --overskriv.")
    shutil.rmtree(maal)
shutil.copytree(kilde, maal, symlinks=False)  # .git med: loaderen kræver en klon

rapport = []
for f in sorted((maal / "spot").glob(f"{a.zone}_*.csv")):
    df = pd.read_csv(f)
    maaned = pd.to_datetime(df["hour_utc"]).dt.to_period("M")
    for kol in ("spot_price_dkk", "spot_price_eur"):
        if kol not in df:
            continue
        x = pd.to_numeric(df[kol], errors="coerce")
        m = x.groupby(maaned).transform("mean")
        ny = a.niveau * (m + a.spredning * (x - m))
        rapport.append({"fil": f.name, "kolonne": kol,
                        "gns_foer": round(x.mean(), 2), "gns_efter": round(ny.mean(), 2),
                        "std_foer": round(x.std(), 2), "std_efter": round(ny.std(), 2)})
        df[kol] = ny.round(4)
    df.to_csv(f, index=False)

(maal / "SPOTSCENARIE.json").write_text(json.dumps(
    {"navn": a.navn, "zone": a.zone, "niveau": a.niveau, "spredning": a.spredning,
     "kilde": str(kilde), "filer": rapport}, indent=2, ensure_ascii=False))
print(f"Scenarie skrevet til {maal}")
for r in rapport:
    if r["kolonne"] == "spot_price_dkk":
        print(f"  {r['fil']}: gns {r['gns_foer']} -> {r['gns_efter']}  std {r['std_foer']} -> {r['std_efter']}")
