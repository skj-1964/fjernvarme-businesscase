"""Lagerbalancen skal også gælde i periodens første time (generalprøven 19/10-2026).

Fundet: startbetingelsen låste lagerets niveau i første time til startværdien,
mens dynamikken først gjaldt fra time 2. Op- og afladning i første time indgik
derfor ikke i lagerbalancen, og tanken kunne levere gratis varme. Det gjorde
Andebys tankværdi i vintervinduet dobbelt så høj (44.220 mod 21.916 kr.).

Med cyklusbindingen (slut = start) og varmetab i lageret skal der over hele
perioden lades mindst lige så meget ind, som der tages ud. Testen er set fejle
på koden før rettelsen (+31 MWh mere afladet end opladet).
"""
import subprocess
import sys

import xarray as xr


def test_lageret_leverer_ikke_gratis_varme(tmp_path):
    r = subprocess.run(
        [sys.executable, "run_case.py", "cases/andeby.yaml", "--data-source", "github",
         "--start", "2026-01-05", "--end", "2026-01-06", "--out-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    nc = next(tmp_path.glob("*_dispatch.nc"))
    ds = xr.open_dataset(nc)
    netto_afladet = float(ds["discharge"].sum() - ds["charge"].sum())
    # Varmetab gør tallet negativt; gratis varme i første time gør det positivt.
    assert netto_afladet <= 1e-3, f"lageret afladede {netto_afladet:.1f} MWh mere, end det blev ladet"
