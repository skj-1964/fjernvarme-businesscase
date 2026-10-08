#!/usr/bin/env python3
"""
solprofil_fra_dmi.py — solvarmeprofil ud fra MÅLT globalstråling i df-data.

    python scripts/solprofil_fra_dmi.py

Skriver data/solar_andeby_dmi_karup.csv med kolonnerne

    time        UTC-tidsstempel for timens START (ISO 8601 med Z)
    power_mw    leverbar solvarmeeffekt i MW

Afløser den syntetiske profil (scripts/generate_solar_andeby.py), som lagde
sol ind på alle årets dage og gav 2-3 gange for meget solvarme om vinteren.
Her kommer vejret fra DMI's målinger (df-data/dmi/<område>_<år>.csv):
globalstråling på vandret (radia_glob_past1h) og udetemperatur
(temp_mean_past1h). Profilen har derfor gråvejrsdage, og den følger de samme
timer som spotprisen og varmelasten i kørslen.

FYSIKKEN, i den rækkefølge den regnes
-------------------------------------
 1. Solens position midt i timen (deklination og tidsligning efter Spencer).
 2. Vandret globalstråling deles i direkte og diffus (Erbs).
 3. Strålingen flyttes til solfangerens plan, sydvendt med hældning --tilt
    (Hay-Davies: direkte + cirkumsolar, isotrop diffus, jordreflektion).
 4. Rækkeskygge: den del af solfangerens højde, som rækken foran skygger for
    den direkte stråling, når solen står lavt (--raekkeafstand,
    --solfangerhoejde). Det er det, der tager det meste af midvinteren.
 5. Indfaldsvinkelkorrektion for den direkte stråling (b0-formlen).
 6. Solfangerligningen (EN ISO 9806):
        q = eta0·G_plan − a1·(Tm − Tude) − a2·(Tm − Tude)²      [W/m²], q ≥ 0
    Tm er solfangervæskens middeltemperatur. Leddet med Tm − Tude er grunden
    til, at svag vintersol ikke giver noget: tabet skal dækkes først.
 7. Hele serien ganges med ÉN faktor, så summen over --skaler-vindue bliver
    --aars-gwh. Faktoren dækker det, ligningen ikke har med (rørtab,
    opvarmning af feltet om morgenen, snavs, driftsstop) og skrives ud. Den
    skal ligge under 1; ligger den langt fra 0,7-0,95, passer areal og
    årsproduktion ikke sammen.

TIDSSTEMPLER — læs det her
--------------------------
DMI's "past1h"-værdier er stemplet med timens SLUT: værdien kl. 12:00 er
middel for kl. 11-12. Det er kontrolleret på dataene selv (strålingens
tyngdepunkt over dagen ligger 0,47 time efter sand middag, målt på
stemplerne). Modellens tidsakse er timens START, som spotprisen. Profilen
flyttes derfor én time: stråling stemplet 12:00 står i profilen kl. 11:00.

HULLER
------
Mangler strålingen i en time, hvor solen er nede, er den nul. Mangler den om
dagen, hentes timen fra naboområderne i den rækkefølge, de følger området
bedst (korrelation på dagtimer). Enkelte timer uden nabo interpoleres (højst
--maks-interpolation timer i træk). Kan en time ikke fyldes, stopper scriptet;
profilen nulfyldes ikke. Alt, der er fyldt, skrives ud pr. måned.

FORBEHOLD
---------
 * Et DMI-område er et gennemsnit af flere stationer. Det glatter skyerne lidt.
 * Hældning 38°, rækkeafstand 5,5 m og Tm 60 °C følger det referencefelt, DTU
   regner danske anlæg på (IEA SHC Task 55, faktaark C-D.1.1: hældning mest
   35-40°, rækkeafstand 5,5 m, 60 °C). Solfangerhøjden 2,27 m er den
   almindelige danske storsolfanger.
 * eta0, a1 og a2 er typiske størrelser for store plane fjernvarmesolfangere,
   ikke et bestemt fabrikat. Har værket et datablad, så brug dets tal.
 * Tm er konstant. I et rigtigt anlæg følger den fremløb og retur.
 * November-februar er følsomme for rækkeafstand og Tm (januar 2026 svinger
   mellem ca. 15 og 50 MWh for Andeby, når de to ændres inden for det
   rimelige), men månederne er små uanset hvad. Marts-oktober flytter sig
   under et par procent.
 * Profilen dækker kun den periode, df-data har målinger for. Kør scriptet
   igen, når df-data er opdateret, og kørselsvinduet skal længere frem.

Brug:
    python scripts/solprofil_fra_dmi.py
    python scripts/solprofil_fra_dmi.py --dmi-area fyn --aars-gwh 8 \\
        --areal-m2 20000 --out deltagere/data/mit_vaerk_solvarme_profil.csv
    python scripts/solprofil_fra_dmi.py --start 2023-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Omtrentligt tyngdepunkt for stationerne i hvert DMI-område (df-data/README).
# Bredden bestemmer solhøjden, længden hvornår det er middag (4 min pr. grad).
OMRAADE_POSITION = {
    "karup": (56.2, 9.15),
    "fyn": (55.3, 10.4),
    "vestkyst": (56.0, 8.3),
    "ringsted": (55.4, 11.8),
}
SOLKONSTANT = 1367.0      # W/m²
MIN_SOLHOEJDE_GRADER = 3.0  # under den regnes al stråling som diffus


class ProfilFejl(Exception):
    """Profilen kan ikke bygges. Beskeden går direkte til brugeren."""


# ------------------------------------------------------------------ indlæsning
def laes_dmi(df_data: Path, omraade: str) -> pd.DataFrame:
    """Alle år for ét område. Indeks = timens START (UTC, naiv)."""
    filer = sorted((df_data / "dmi").glob(f"{omraade}_*.csv"))
    if not filer:
        raise ProfilFejl(
            f"Ingen DMI-filer for '{omraade}' i {df_data / 'dmi'}. Er df-data "
            "hentet? Kør modellen én gang med --data-source github, eller "
            "angiv stien med --df-data.")
    df = pd.concat([pd.read_csv(f) for f in filer], ignore_index=True)
    for kol in ("hour_utc", "radia_glob_past1h", "temp_mean_past1h"):
        if kol not in df.columns:
            raise ProfilFejl(f"{omraade}: kolonnen '{kol}' mangler i df-data.")
    df["slut"] = pd.to_datetime(df["hour_utc"])
    df = df.drop_duplicates("slut").set_index("slut").sort_index()
    ud = pd.DataFrame({
        "g": pd.to_numeric(df["radia_glob_past1h"], errors="coerce"),
        "t": pd.to_numeric(df["temp_mean_past1h"], errors="coerce"),
    })
    # "past1h" er stemplet med timens slut; modellen bruger timens start.
    ud.index = ud.index - pd.Timedelta(hours=1)
    ud.index.name = "time"
    return ud


# ------------------------------------------------------------------- geometri
def solposition(idx: pd.DatetimeIndex, lat: float, lon: float) -> dict:
    """Solens position midt i hver time. idx er timens start i UTC."""
    midt = idx + pd.Timedelta(minutes=30)
    doy = midt.dayofyear.to_numpy().astype(float)
    time_utc = midt.hour.to_numpy() + midt.minute.to_numpy() / 60.0

    g = 2.0 * np.pi * (doy - 1.0) / 365.0                     # Spencer
    dekl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g)
            - 0.006758 * np.cos(2 * g) + 0.000907 * np.sin(2 * g)
            - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    tidsligning_min = 229.18 * (0.000075 + 0.001868 * np.cos(g)
                                - 0.032077 * np.sin(g)
                                - 0.014615 * np.cos(2 * g)
                                - 0.040849 * np.sin(2 * g))
    e0 = 1.0 + 0.033 * np.cos(2.0 * np.pi * doy / 365.0)

    soltid = time_utc + lon / 15.0 + tidsligning_min / 60.0
    timevinkel = np.deg2rad(15.0 * (soltid - 12.0))
    phi = np.deg2rad(lat)
    cos_z = (np.sin(phi) * np.sin(dekl)
             + np.cos(phi) * np.cos(dekl) * np.cos(timevinkel))
    return {"dekl": dekl, "timevinkel": timevinkel, "cos_z": cos_z,
            "e0": e0, "phi": phi}


def straaling_i_solfangerplan(g_vandret: np.ndarray, sol: dict, *, tilt: float,
                              pitch_forhold: float, albedo: float,
                              b0: float) -> dict:
    """Vandret globalstråling → direkte og diffus i en sydvendt, hældende
    solfangers plan, med rækkeskygge og indfaldsvinkelkorrektion."""
    beta = np.deg2rad(tilt)
    cos_z, dekl, w, phi = sol["cos_z"], sol["dekl"], sol["timevinkel"], sol["phi"]
    g = np.clip(g_vandret, 0.0, None)

    sol_oppe = cos_z > np.sin(np.deg2rad(MIN_SOLHOEJDE_GRADER))
    g0 = SOLKONSTANT * sol["e0"] * np.clip(cos_z, 0.0, None)   # uden for atmosfæren

    # Erbs: klarhedsindeks → diffus andel
    kt = np.where(g0 > 1.0, np.clip(g / np.where(g0 > 1.0, g0, 1.0), 0.0, 1.0), 0.0)
    diffus_andel = np.where(
        kt <= 0.22, 1.0 - 0.09 * kt,
        np.where(kt <= 0.80,
                 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3
                 + 12.336 * kt**4,
                 0.165))
    diffus_andel = np.where(sol_oppe, diffus_andel, 1.0)
    g_diffus = g * diffus_andel
    g_direkte = g - g_diffus

    # Indfaldsvinkel på sydvendt flade med hældning beta
    cos_i = (np.sin(dekl) * np.sin(phi - beta)
             + np.cos(dekl) * np.cos(phi - beta) * np.cos(w))
    cos_i = np.clip(cos_i, 0.0, None)
    rb = np.where(sol_oppe, cos_i / np.where(sol_oppe, cos_z, 1.0), 0.0)

    # Hay-Davies: en del af den diffuse stråling kommer fra solens retning
    ai = np.where(g0 > 1.0, g_direkte / np.where(g0 > 1.0, g0, 1.0), 0.0)
    plan_direkte = (g_direkte + g_diffus * ai) * rb
    plan_diffus = (g_diffus * (1.0 - ai) * (1.0 + np.cos(beta)) / 2.0
                   + g * albedo * (1.0 - np.cos(beta)) / 2.0)

    # Rækkeskygge. Profilvinklen er solhøjden set i nord-syd-snittet.
    # Skygget andel af solfangerens højde:  1 − (P/L)·sin(ap)/sin(ap + beta)
    sin_h = np.clip(cos_z, 1e-6, 1.0)
    cos_h = np.sqrt(1.0 - sin_h**2)
    cos_az = np.where(cos_h > 1e-6,
                      (sin_h * np.sin(phi) - np.sin(dekl))
                      / (np.where(cos_h > 1e-6, cos_h, 1.0) * np.cos(phi)),
                      1.0)
    cos_az = np.clip(cos_az, -1.0, 1.0)            # +1 = stik syd
    foran = cos_az > 1e-3
    profil = np.where(foran,
                      np.arctan2(sin_h, cos_h * np.where(foran, cos_az, 1.0)),
                      np.pi / 2.0)
    skygge = np.clip(
        1.0 - pitch_forhold * np.sin(profil) / np.sin(profil + beta), 0.0, 1.0)
    skygge = np.where(sol_oppe & (cos_i > 0), skygge, 0.0)

    # Indfaldsvinkelkorrektion for den direkte del
    kb = np.where(cos_i > 0.087,                       # under ca. 85 grader
                  np.clip(1.0 - b0 * (1.0 / np.where(cos_i > 0.087, cos_i, 1.0)
                                      - 1.0), 0.0, 1.0),
                  0.0)
    return {"direkte": plan_direkte, "diffus": plan_diffus, "skygge": skygge,
            "kb": kb, "sol_oppe": cos_z > 0.0}


# --------------------------------------------------------------- hulfyldning
def fyld_huller(omraade: str, serier: dict[str, pd.DataFrame],
                idx: pd.DatetimeIndex, sol_oppe: np.ndarray,
                maks_interpolation: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stråling og temperatur uden huller på idx, samt en log over det fyldte.

    kilde: 'maalt', 'nat' (sol nede, sat til 0), '<nabo>' eller 'interpoleret'.
    """
    egen = serier[omraade].reindex(idx)
    g = egen["g"].copy()
    kilde = pd.Series("maalt", index=idx)

    nat = g.isna() & ~sol_oppe
    g[nat] = 0.0
    kilde[nat] = "nat"

    if g.isna().any():
        dag = sol_oppe & egen["g"].notna()
        naboer = {}
        for navn, df in serier.items():
            if navn == omraade:
                continue
            ng = df["g"].reindex(idx)
            faelles = dag & ng.notna()
            if faelles.sum() > 200:
                naboer[navn] = (float(np.corrcoef(egen["g"][faelles],
                                                  ng[faelles])[0, 1]), ng)
        for navn, (_, ng) in sorted(naboer.items(), key=lambda kv: -kv[1][0]):
            tag = g.isna() & ng.notna()
            g[tag] = ng[tag]
            kilde[tag] = navn

    if g.isna().any():
        mangler = g.isna()
        g = g.interpolate(limit=maks_interpolation, limit_area="inside")
        kilde[mangler & g.notna()] = "interpoleret"

    if g.isna().any():
        m = g[g.isna()]
        raise ProfilFejl(
            f"{len(m)} dagtimer uden globalstråling kan ikke fyldes, første "
            f"{m.index[0]}, sidste {m.index[-1]}. Hverken naboområderne eller "
            f"interpolation over højst {maks_interpolation} timer dækker dem. "
            "Profilen nulfyldes ikke. Vælg et kortere vindue (--start/--slut).")

    # Temperaturen indgår kun i varmetabet; korte huller interpoleres, lange
    # hentes fra naboerne.
    t = egen["t"].interpolate(limit=6, limit_area="inside")
    for navn, df in serier.items():
        if navn != omraade and t.isna().any():
            t = t.fillna(df["t"].reindex(idx))
    if t.isna().any():
        m = t[t.isna()]
        raise ProfilFejl(f"{len(m)} timer uden udetemperatur kan ikke fyldes, "
                         f"første {m.index[0]}.")
    return pd.DataFrame({"g": g, "t": t}), kilde.to_frame("kilde")


# ----------------------------------------------------------------------- main
def byg(a: argparse.Namespace) -> pd.DataFrame:
    if a.dmi_area not in OMRAADE_POSITION:
        raise ProfilFejl(f"Ukendt DMI-område '{a.dmi_area}'. Kendte: "
                         f"{', '.join(OMRAADE_POSITION)}.")
    lat, lon = OMRAADE_POSITION[a.dmi_area]
    if a.lat is not None:
        lat = a.lat
    if a.lon is not None:
        lon = a.lon

    serier = {a.dmi_area: laes_dmi(a.df_data, a.dmi_area)}
    for navn in OMRAADE_POSITION:
        if navn != a.dmi_area:
            try:
                serier[navn] = laes_dmi(a.df_data, navn)
            except ProfilFejl:
                pass                      # naboer er en hjælp, ikke et krav

    egen = serier[a.dmi_area]
    start = pd.Timestamp(a.start)
    # Sidste HELE døgn med data, medmindre --slut er givet.
    sidste = egen.index[-1]
    slut = (pd.Timestamp(a.slut) + pd.Timedelta(hours=23) if a.slut
            else (sidste + pd.Timedelta(hours=1)).normalize()
            - pd.Timedelta(hours=1))
    if start < egen.index[0] or slut > sidste:
        raise ProfilFejl(
            f"Vinduet {start} → {slut} ligger uden for df-datas DMI-dækning for "
            f"{a.dmi_area} ({egen.index[0]} → {sidste}).")
    idx = pd.date_range(start, slut, freq="h")

    sol = solposition(idx, lat, lon)
    data, kilde = fyld_huller(a.dmi_area, serier, idx, sol["cos_z"] > 0.0,
                              a.maks_interpolation)

    plan = straaling_i_solfangerplan(
        data["g"].to_numpy(), sol, tilt=a.tilt,
        pitch_forhold=a.raekkeafstand / a.solfangerhoejde,
        albedo=a.albedo, b0=a.b0)

    dt = a.tm - data["t"].to_numpy()
    optaget = a.eta0 * (plan["kb"] * plan["direkte"] * (1.0 - plan["skygge"])
                        + a.kd * plan["diffus"])
    q = np.clip(optaget - a.a1 * dt - a.a2 * dt**2, 0.0, None)        # W/m²
    q_uden_skygge = np.clip(
        a.eta0 * (plan["kb"] * plan["direkte"] + a.kd * plan["diffus"])
        - a.a1 * dt - a.a2 * dt**2, 0.0, None)

    ud = pd.DataFrame({"q_w_m2": q, "q_uden_skygge": q_uden_skygge,
                       "g_vandret": data["g"].to_numpy(),
                       "g_plan": plan["direkte"] + plan["diffus"],
                       "t_ude": data["t"].to_numpy(),
                       "kilde": kilde["kilde"].to_numpy()}, index=idx)

    # Skalering: én faktor, så vinduets sum bliver årsproduktionen.
    v0, v1 = pd.Timestamp(a.skaler_vindue[0]), (pd.Timestamp(a.skaler_vindue[1])
                                                + pd.Timedelta(hours=23))
    vindue = ud.loc[v0:v1]
    forventet = int((v1 - v0) / pd.Timedelta(hours=1)) + 1
    if len(vindue) != forventet:
        raise ProfilFejl(
            f"Skaleringsvinduet {v0} → {v1} er ikke dækket af profilen "
            f"({len(vindue)} af {forventet} timer). Flyt --start/--slut eller "
            "--skaler-vindue.")
    raa_kwh_m2 = vindue["q_w_m2"].sum() / 1000.0
    maal_kwh_m2 = a.aars_gwh * 1e6 / a.areal_m2
    faktor = maal_kwh_m2 / raa_kwh_m2
    ud["power_mw"] = ud["q_w_m2"] * a.areal_m2 / 1e6 * faktor

    # ------------------------------------------------------------ rapport
    print(f"Solprofil fra målt stråling — DMI-område {a.dmi_area} "
          f"({lat:.2f}° N, {lon:.2f}° Ø)")
    print(f"  Periode: {idx[0]} → {idx[-1]} UTC ({len(idx)} timer, timens start)")
    print(f"  Solfanger: hældning {a.tilt:g}°, rækkeafstand {a.raekkeafstand:g} m, "
          f"højde {a.solfangerhoejde:g} m, eta0 {a.eta0:g}, a1 {a.a1:g}, "
          f"a2 {a.a2:g}, Tm {a.tm:g} °C")

    fyldt = ud[~ud["kilde"].isin(["maalt", "nat"])]
    nat = int((ud["kilde"] == "nat").sum())
    print(f"  Huller: {nat} nattetimer sat til 0; {len(fyldt)} dagtimer fyldt"
          + (":" if len(fyldt) else "."))
    if len(fyldt):
        tab = (fyldt.groupby([fyldt.index.strftime("%Y-%m"), "kilde"]).size()
               .unstack(fill_value=0))
        for linje in tab.to_string().splitlines():
            print("    " + linje)

    skyggetab = 1.0 - vindue["q_w_m2"].sum() / vindue["q_uden_skygge"].sum()
    print(f"  Skaleringsvindue {v0:%Y-%m-%d} → {v1:%Y-%m-%d}:")
    print(f"    vandret globalstråling   {vindue['g_vandret'].sum() / 1000:7.0f} kWh/m²")
    print(f"    i solfangerens plan      {vindue['g_plan'].sum() / 1000:7.0f} kWh/m²")
    print(f"    solfangerligningen giver {raa_kwh_m2:7.0f} kWh/m² "
          f"(rækkeskygge koster {skyggetab:.1%})")
    print(f"    målet er                 {maal_kwh_m2:7.0f} kWh/m² "
          f"({a.aars_gwh:g} GWh på {a.areal_m2:,.0f} m²)".replace(",", "."))
    print(f"    systemfaktor             {faktor:7.3f}")
    if not 0.60 <= faktor <= 1.0:
        print("    ADVARSEL: systemfaktoren ligger uden for 0,60-1,00. Enten "
              "passer areal og årsproduktion ikke sammen, eller også gør "
              "solfangertallene ikke. Tjek dem, før profilen bruges.")

    md = ud.loc[v0:v1, "power_mw"].resample("MS").agg(["sum", "max"])
    dage = ud.loc[v0:v1, "power_mw"].resample("D").sum()
    md["andel"] = md["sum"] / md["sum"].sum() * 100.0
    md["nuldage"] = (dage < 0.01 * dage.max()).resample("MS").sum()
    print("  Måned      MWh   andel   maks MW   dage uden produktion")
    for t, r in md.iterrows():
        print(f"    {t:%Y-%m} {r['sum']:7.0f} {r['andel']:6.1f} % {r['max']:8.1f} "
              f"{int(r['nuldage']):8d}")
    print(f"  Største effekt i hele profilen: {ud['power_mw'].max():.1f} MW — "
          "sæt enhedens p_max_heat mindst så højt.")
    return ud


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dmi-area", default="karup",
                   help="DMI-område i df-data (default: karup)")
    p.add_argument("--df-data", type=Path, default=Path("data/df-data"),
                   help="Sti til df-data-klonen (default: data/df-data)")
    p.add_argument("--out", type=Path,
                   default=Path("data/solar_andeby_dmi_karup.csv"))
    p.add_argument("--start", default="2025-01-01",
                   help="Første dag i profilen (default: 2025-01-01)")
    p.add_argument("--slut", default=None,
                   help="Sidste dag (default: sidste hele døgn i df-data)")
    p.add_argument("--aars-gwh", type=float, default=12.0,
                   help="Solvarmens årsproduktion i skaleringsvinduet (GWh)")
    p.add_argument("--areal-m2", type=float, default=30000.0,
                   help="Solfangerareal (m²). Bruges til systemfaktoren.")
    p.add_argument("--skaler-vindue", nargs=2, metavar=("FRA", "TIL"),
                   default=["2025-07-01", "2026-06-30"],
                   help="De 12 måneder, årsproduktionen gælder for")
    p.add_argument("--tilt", type=float, default=38.0, help="Hældning, grader")
    p.add_argument("--raekkeafstand", type=float, default=5.5,
                   help="Afstand mellem rækkerne, forkant til forkant (m)")
    p.add_argument("--solfangerhoejde", type=float, default=2.27,
                   help="Solfangerens højde langs fladen (m)")
    p.add_argument("--tm", type=float, default=60.0,
                   help="Solfangervæskens middeltemperatur (°C)")
    p.add_argument("--eta0", type=float, default=0.78)
    p.add_argument("--a1", type=float, default=2.5, help="W/m²K")
    p.add_argument("--a2", type=float, default=0.012, help="W/m²K²")
    p.add_argument("--b0", type=float, default=0.10,
                   help="Indfaldsvinkelkorrektion, direkte stråling")
    p.add_argument("--kd", type=float, default=0.90,
                   help="Indfaldsvinkelkorrektion, diffus stråling")
    p.add_argument("--albedo", type=float, default=0.20)
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lon", type=float, default=None)
    p.add_argument("--maks-interpolation", type=int, default=3,
                   help="Højst så mange dagtimer i træk interpoleres")
    p.add_argument("--overskriv", action="store_true",
                   help="Erstat --out, hvis filen findes.")
    a = p.parse_args()

    if a.out.exists() and not a.overskriv:
        print(f"FEJL: {a.out} findes allerede. Brug --overskriv.", file=sys.stderr)
        return 1
    try:
        ud = byg(a)
    except ProfilFejl as e:
        print(f"\nProfilen kan ikke bygges:\n  {e}\n", file=sys.stderr)
        return 1

    a.out.parent.mkdir(parents=True, exist_ok=True)
    skriv = pd.DataFrame({"time": ud.index.strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "power_mw": ud["power_mw"].to_numpy()})
    skriv.to_csv(a.out, index=False, float_format="%.6f")
    print(f"\nSkrevet: {a.out} ({len(skriv)} timer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
