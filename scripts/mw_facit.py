"""Sammenlign en kørsel med Billunds facit for 2. marts–30. juni 2026.
Brug: python mw_facit.py trin_d/driven_med.log"""
import re, sys
import pandas as pd

log = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"Filnavn-stem: (\S+)", log)
if not m:
    print(f"{sys.argv[1]}: ingen output — " +
          ("modellen kunne ikke løses" if "kan ikke løses" in log else "kørslen er ikke færdig"))
    sys.exit(1)
x = pd.read_csv(f"output/{m.group(1)}_hourly.csv", parse_dates=["timestamp"])
x = x[(x.timestamp >= "2026-03-02") & (x.timestamp < "2026-07-01")]
facit = {"afrr": (1.48, 0.743), "mfrr": (1.70, 0.509)}   # mio. kr., MW-snit
tot_m = tot_f = 0.0
for mk, (f_mio, f_mw) in facit.items():
    mw = x[[c for c in x if c.startswith(f"r_{mk}_") and c.endswith("_mw") and "reduction" not in c]].sum(axis=1)
    k = x[[c for c in x if c.startswith(f"r_{mk}_") and c.endswith("cap_revenue_dkk")]].sum().sum()
    a = x[[c for c in x if c.startswith(f"r_{mk}_") and c.endswith("act_revenue_dkk")]].sum().sum()
    mwh = mw.sum()
    pr_mw = (k + a) / mwh if mwh else 0
    f_pr_mw = f_mio * 1e6 / (f_mw * len(x))
    print(f"{mk}: indtægt {(k+a)/1e6:.2f} / facit {f_mio:.2f} mio ({(k+a)/1e6/f_mio:.0%})  |  "
          f"MW-snit {mw.mean():.3f} / {f_mw:.3f} ({mw.mean()/f_mw:.0%})  |  "
          f"kr. pr. MW-time {pr_mw:,.0f} / {f_pr_mw:,.0f} ({pr_mw/f_pr_mw:.0%})")
    tot_m += (k + a) / 1e6; tot_f += f_mio
print(f"i alt: {tot_m:.2f} / {tot_f:.2f} mio ({tot_m/tot_f:.0%})")
