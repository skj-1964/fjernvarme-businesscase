#!/usr/bin/env python3
"""
vaerksark_til_yaml.py — deltagerens udfyldte Excelark til en gyldig casefil.

    python scripts/vaerksark_til_yaml.py mit_vaerk.xlsx

Skriver to filer ved siden af arket:

    cases/<slug>.yaml                  casefilen
    data/<slug>_abvaerk_hourly.csv     varmelasten fra arket Timedata

Er arket Timedata tomt, men årsproduktionen i B3 udfyldt, skrives kun
casefilen, og varmelasten syntetiseres af modellen ud fra DMI-vejrdata.

og kører derefter:

    python run_case.py cases/<slug>.yaml --data-source github \
        --heat-csv data/<slug>_abvaerk_hourly.csv

Scriptet SKRIVER ALDRIG hen over en eksisterende fil uden --overskriv, og det
stopper højlydt på alt, det ikke kan tolke. En case, der bygger på et ark med
en tom kolonne, er værre end ingen case: tallene ser rigtige ud.

Skabelonen ligger i doc/vaerksdata_skabelon.xlsx.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import timedelta
from pathlib import Path

import pandas as pd

TYPER_UDEN_BRAENDSEL = {"heat_pump", "electric_boiler", "solar_thermal"}
BRAENDSEL_PR_TYPE = {
    "heat_pump": "electricity",
    "electric_boiler": "electricity",
    "biomass_boiler": None,       # afgøres af halm/flis-pris, se nedenfor
    "gas_boiler": "natural_gas",
    "gas_engine_chp": "natural_gas",
    "solar_thermal": "solar",
    "waste_heat": "waste_heat",
}
GYLDIGE_TYPER = set(BRAENDSEL_PR_TYPE)


class ArkFejl(Exception):
    """Noget i arket kan ikke tolkes. Beskeden går direkte til deltageren."""


def slug(navn: str) -> str:
    s = unicodedata.normalize("NFKD", str(navn))
    s = s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s:
        raise ArkFejl("Værkets navn på arket Priser er tomt.")
    return s


def tal(v, felt: str, *, kraev=False):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        if kraev:
            raise ArkFejl(f"{felt} er tom og skal udfyldes.")
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ArkFejl(f"{felt} er ikke et tal: {v!r}")


# ------------------------------------------------------------------ timedata
def laes_tidszone(sti: Path) -> str:
    """Deltagerens erklæring, ikke vores gæt.

    Modellen regner i UTC, og skabelonen beder om UTC. Men et SRO-udtræk kommer
    ofte i dansk tid, og en deltager, der konverterer i hånden, rammer forkert
    oftere end scriptet gør. Derfor er feltet et valg mellem to værdier — og
    alt andet stopper kørslen frem for at blive tolket."""
    raa = pd.read_excel(sti, sheet_name="Timedata", header=None, nrows=3)
    try:
        v = str(raa.iat[1, 1] or "").strip().lower()
    except IndexError:
        v = ""
    if v in ("utc", "utc+0", "z", "gmt"):
        return "UTC"
    if v in ("dansk lokaltid", "dansk tid", "lokaltid", "lokal tid",
             "europe/copenhagen", "cet", "cest"):
        return "Europe/Copenhagen"
    raise ArkFejl(
        f"Tidszonefeltet i Timedata (celle B2) siger {v!r}. Det skal stå som "
        "enten 'UTC' eller 'dansk lokaltid'. Feltet gættes ikke: en forkert "
        "tidszone flytter hele året en eller to timer i forhold til elprisen, "
        "uden at noget ser forkert ud.")


def laes_aarsproduktion(sti: Path) -> float | None:
    """Årsproduktion ab værk i GWh — Timedata!B3.

    Feltet er tilføjet, fordi kollegerne bad om én samlet tidsserie plus et
    årstal, så en varmelast kan syntetiseres fra DMI-data, når SRO ikke kan
    levere timeværdier. Tallet bruges to steder: som krydstjek mod den målte
    timeserie, og som eneste grundlag når timeserien mangler helt."""
    raa = pd.read_excel(sti, sheet_name="Timedata", header=None, nrows=3)
    try:
        v = raa.iat[2, 1]
    except IndexError:
        return None
    gwh = tal(v, "Timedata: årsproduktion (celle B3)")
    if gwh is None:
        return None
    if not 0.5 < gwh < 5000:
        raise ArkFejl(
            f"Årsproduktionen i Timedata!B3 er {gwh}. Den skal stå i GWh pr. år "
            "— fx 42,5 for et værk, der leverer 42.500 MWh. Et tal i MWh eller "
            "kWh her gør hele businesscasen forkert uden at se forkert ud.")
    return float(gwh)


def laes_timedata(sti: Path, slugnavn: str, ud_dir: Path, overskriv: bool,
                  tz: str, aars_gwh: float | None = None
                  ) -> tuple[Path | None, str, str, float]:
    df = pd.read_excel(sti, sheet_name="Timedata", skiprows=4, usecols=[0, 1])
    df.columns = ["timestamp", "heat_mw_abvaerk"]
    df = df.dropna(how="all")

    # Helt tomt ark → kør på årsproduktionen alene, hvis den er udfyldt.
    if df.dropna(how="all").empty:
        if aars_gwh is None:
            raise ArkFejl(
                "Arket Timedata er tomt, og årsproduktionen i B3 er heller ikke "
                "udfyldt. Modellen skal have mindst ét af de to: timeværdier fra "
                "række 6, eller årsproduktionen i GWh.")
        print("    Ingen timeserie i arket. Varmelasten syntetiseres ud fra "
              f"årsproduktionen på {aars_gwh:.1f} GWh og DMI-vejrdata. "
              "Resultatet er et regneeksempel med værkets anlæg og priser — "
              "ikke en model af værkets faktiske drift.")
        return None, "2025-07-01T00:00:00Z", "2026-06-30T23:00:00Z", aars_gwh

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=False)
    ubrugelige = df["timestamp"].isna()
    if ubrugelige.all():
        raise ArkFejl("Arket Timedata har ingen læsbare tidsstempler. "
                      "Står dine data fra række 6?")
    if ubrugelige.any():
        foerste = int(ubrugelige.idxmax()) + 6
        raise ArkFejl(
            f"{int(ubrugelige.sum())} rækker i Timedata har et tidsstempel, der "
            f"ikke kan læses som en dato — første gang omkring række {foerste}. "
            "Formatér kolonne A som dato/tid i Excel og prøv igen.")

    df = df.dropna(subset=["heat_mw_abvaerk"])
    if df.empty:
        raise ArkFejl("Arket Timedata har tidsstempler, men ingen værdier i kolonne B.")

    # Under fire uger er det ikke et udtræk, men eksempelrækkerne eller et
    # halvt indsat ark. Det skal stoppe, ikke blive til en case, der ser rigtig ud.
    if len(df) < 24 * 28:
        raise ArkFejl(
            f"Timedata har kun {len(df)} timer. Det ligner eksempelrækkerne eller "
            "et ufuldstændigt udtræk. Indsæt jeres timeværdier for 1. juli 2025 – "
            "30. juni 2026 fra række 6, og slet eksempelrækkerne.")

    df = df.sort_values("timestamp").reset_index(drop=True)
    dubletter = df["timestamp"].duplicated()
    if dubletter.any() and tz == "UTC":
        raise ArkFejl(
            f"{int(dubletter.sum())} tidsstempler går igen i Timedata, første gang "
            f"{df.loc[dubletter.idxmax(), 'timestamp']}. I UTC findes ingen "
            "gentagne timer, så det er enten to udtræk klistret sammen, eller "
            "også er dataene faktisk i dansk tid.")

    if tz == "UTC":
        # Allerede det, modellen regner i. Et tz-mærket udtræk normaliseres.
        if getattr(df["timestamp"].dt, "tz", None) is not None:
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
    else:
        if dubletter.any():
            print(f"    {int(dubletter.sum())} gentagne tidsstempler — det er "
                  "efterårets dobbelttime i dansk tid, som forventet.")
        lokal = df["timestamp"].dt
        try:
            ts = lokal.tz_localize("Europe/Copenhagen",
                                   nonexistent="shift_forward", ambiguous="infer")
        except Exception:
            # Et år skåret til 8760 timer mangler dobbelttimen helt. Almindeligt,
            # og ikke en fejl — men én time havner forkert, og det skal siges.
            ts = lokal.tz_localize("Europe/Copenhagen",
                                   nonexistent="shift_forward", ambiguous=True)
            print("    Efterårets dobbelttime står kun én gang i arket. Den er "
                  "læst som sommertid. Det flytter én time i året.")
        df["timestamp"] = ts.dt.tz_convert("UTC").dt.tz_localize(None)
        print("    Tidsstempler konverteret fra dansk lokaltid til UTC.")

    df = df.sort_values("timestamp").reset_index(drop=True)
    spaend = df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]
    fulde_timer = int(spaend / timedelta(hours=1)) + 1
    huller = fulde_timer - len(df)
    daekning = len(df) / fulde_timer

    negative = (df["heat_mw_abvaerk"] < 0).sum()
    if negative:
        raise ArkFejl(f"{negative} værdier i Timedata er negative. "
                      "Varmeproduktion ab værk kan ikke være under nul.")

    ud = ud_dir / f"{slugnavn}_abvaerk_hourly.csv"
    if ud.exists() and not overskriv:
        raise ArkFejl(f"{ud} findes allerede. Kør med --overskriv, hvis den skal erstattes.")
    ud.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ud, index=False, date_format="%Y-%m-%d %H:%M:%S")

    start = df["timestamp"].iloc[0].strftime("%Y-%m-%dT%H:00:00Z")
    slut = df["timestamp"].iloc[-1].strftime("%Y-%m-%dT%H:00:00Z")
    aarsvolumen = float(df["heat_mw_abvaerk"].sum() / 1000.0 * (8760 / max(fulde_timer, 1)))

    print(f"  Timedata: {len(df)} timer, {df['timestamp'].iloc[0]:%Y-%m-%d} til "
          f"{df['timestamp'].iloc[-1]:%Y-%m-%d} (UTC), dækning {daekning:.1%}")

    # Krydstjek mod det årstal, deltageren selv har skrevet. De to tal kommer
    # fra hver sin kilde — SRO-udtrækket og årsopgørelsen — og er de uenige,
    # er det som regel enheden (MW mod MWh) eller en manglende måler.
    if aars_gwh is not None:
        afvig = (aarsvolumen - aars_gwh) / aars_gwh
        if abs(afvig) > 0.05:
            print(f"    Timeserien svarer til {aarsvolumen:.1f} GWh/år, men B3 "
                  f"siger {aars_gwh:.1f} GWh — {afvig:+.0%}. Tjek om udtrækket "
                  "dækker hele værket, og om kolonne B er MW og ikke MWh eller "
                  "kWh. Modellen bruger timeserien.")
    else:
        print("    Årsproduktionen i Timedata!B3 er ikke udfyldt. Den bruges "
              "som kontrol af timeserien — udfyld den gerne.")
    if huller:
        # Modellen (apply_heat_csv_override) interpolerer lineært op til 5 %
        # af vinduet og stopper først derover. På et år er det op til 438
        # timer — 18 døgn med en ret linje, og kun én linje i loggen.
        laengste = int((df["timestamp"].diff() / timedelta(hours=1)).max() - 1)
        print(f"    {huller} timer mangler ({huller / fulde_timer:.1%}), længste "
              f"hul {laengste} timer. Under 5 % af kørselsvinduet udfylder "
              "modellen hullerne ved lineær interpolation uden at stoppe; "
              "over 5 % stopper den.")
        if laengste > 48:
            print("    Et hul på over to døgn bliver en ret linje hen over vejrskift. "
                  "Kør et vindue uden om hullet, eller bed om DMI-syntese for det.")
    if spaend < timedelta(days=300):
        print(f"    Arket dækker {spaend.days} dage, ikke et helt år. "
              "Kørslen virker, men årsøkonomien er ikke et årstal.")
    return ud, start, slut, aarsvolumen


# -------------------------------------------------------------------- anlæg
def laes_enheder(sti: Path, priser: dict) -> dict:
    df = pd.read_excel(sti, sheet_name="Anlaeg", skiprows=3, usecols=range(13), nrows=19)
    df.columns = ["navn", "type", "p_max", "p_min", "eta", "cop", "eta_el",
                  "var_om", "start_cost", "min_up", "min_down", "balance",
                  "sol_gwh"]
    df = df.dropna(subset=["navn", "type"])
    if df.empty:
        raise ArkFejl("Arket Anlaeg har ingen enheder med både navn og type.")

    units: dict = {}
    for i, r in df.iterrows():
        raekke = int(i) + 5
        navn = slug(r["navn"])
        if navn in units:
            raise ArkFejl(f"Enhedsnavnet '{r['navn']}' står to gange (række {raekke}).")
        type_ = str(r["type"]).strip()
        if type_ not in GYLDIGE_TYPER:
            raise ArkFejl(
                f"Række {raekke}: '{type_}' er ikke en kendt type. "
                f"Vælg en af: {', '.join(sorted(GYLDIGE_TYPER))}.")

        u: dict = {
            "enabled": True,
            "type": type_,
            "p_max_heat": tal(r["p_max"], f"række {raekke}, maks varme", kraev=True),
            "p_min_heat": tal(r["p_min"], f"række {raekke}, min varme") or 0.0,
            "var_om": tal(r["var_om"], f"række {raekke}, D&V") or 0.0,
            "start_cost": tal(r["start_cost"], f"række {raekke}, startomkostning") or 0.0,
            "min_uptime": int(tal(r["min_up"], f"række {raekke}, min driftstid") or 1),
            "min_downtime": int(tal(r["min_down"], f"række {raekke}, min stoptid") or 1),
        }
        if u["p_min_heat"] > u["p_max_heat"]:
            raise ArkFejl(f"Række {raekke}: min varme er større end maks varme.")

        if type_ not in TYPER_UDEN_BRAENDSEL:
            eta = tal(r["eta"], f"række {raekke}, virkningsgrad", kraev=True)
            if not 0 < eta <= 1.2:
                raise ArkFejl(f"Række {raekke}: virkningsgrad {eta} ser forkert ud. "
                              "Den skal være en brøkdel, fx 0,95 — ikke 95.")
            u["eta_fuel_to_heat"] = eta

        if type_ == "biomass_boiler":
            if not priser.get("straw") and not priser.get("flis"):
                raise ArkFejl(
                    f"Række {raekke}: '{r['navn']}' er en biomassekedel, men "
                    "hverken halm- eller flisprisen er udfyldt på arket Priser.")
            u["fuel"] = "straw" if priser.get("straw") else "flis"
        else:
            u["fuel"] = BRAENDSEL_PR_TYPE[type_]

        if type_ == "waste_heat" and not priser.get("waste_heat"):
            raise ArkFejl(
                f"Række {raekke}: '{r['navn']}' er overskudsvarme, men prisen "
                "for overskudsvarme er ikke udfyldt på arket Priser.")

        if type_ == "solar_thermal":
            gwh = tal(r["sol_gwh"], f"række {raekke}, solvarme årsproduktion",
                      kraev=True)
            if not 0 < gwh < 500:
                raise ArkFejl(f"Række {raekke}: solvarme-årsproduktion {gwh} GWh "
                              "ser forkert ud. Skriv den i GWh, fx 12.")
            # Selve profilen skrives senere — den kræver kørslens tidsvindue.
            u["_sol_gwh"] = gwh

        # ------------------------------------------------------------------
        # El-til-varme-forholdet (alpha) er IKKE et arkfelt. Deltageren opgiver
        # virkningsgrader, som anlægsfolk kender fra typeskilt og årsopgørelse,
        # og alpha udledes herfra. Det fjerner den fejlkilde, at arket og
        # modellen kan komme til at sige to forskellige ting om samme enhed.
        #
        #   varmepumpe:   alpha = −1/COP        (dispatch bruger cop_curve)
        #   elkedel:      alpha = −1/η_varme    (η_varme = MWh varme pr. MWh el)
        #   gasmotor:     alpha = η_el/η_varme  (begge pr. MWh brændsel)
        #   øvrige:       alpha = 0
        # ------------------------------------------------------------------
        eta_el = tal(r["eta_el"], f"række {raekke}, elvirkningsgrad")
        if eta_el is not None and type_ != "gas_engine_chp":
            raise ArkFejl(
                f"Række {raekke}: elvirkningsgrad er udfyldt for en {type_}. "
                "Feltet gælder kun gasmotorer. For varmepumper regnes der på "
                "COP, for elkedler på varme virkningsgrad.")

        if type_ == "heat_pump":
            cop = tal(r["cop"], f"række {raekke}, COP", kraev=True)
            if not 1.5 <= cop <= 6.0:
                raise ArkFejl(
                    f"Række {raekke}: COP på {cop} ser forkert ud. Det skal være "
                    "COP ved 0 °C udetemperatur, typisk 2,5–3,5 for luft/vand. "
                    "En årsvirkningsgrad eller en COP ved 7 °C hører ikke til her.")
            u["cop_curve"] = {"type": "linear", "a": round(cop, 3), "b": 0.08,
                              "cop_min": 1.8, "cop_max": 4.5}
            # Dispatch og balancering bruger cop_curve; alpha er fallback og
            # skal pege samme vej, så casefilen ikke modsiger sig selv.
            u["alpha"] = round(-1.0 / cop, 4)

        elif type_ == "electric_boiler":
            eta_kedel = tal(r["eta"], f"række {raekke}, varme virkningsgrad")
            if eta_kedel is None:
                eta_kedel = 0.99
                print(f"    Række {raekke}: elkedlens virkningsgrad er tom — "
                      "regnet som 0,99 MWh varme pr. MWh el.")
            if not 0.80 <= eta_kedel <= 1.0:
                raise ArkFejl(
                    f"Række {raekke}: elkedlens virkningsgrad er {eta_kedel}. "
                    "Den skal være MWh varme pr. MWh el, typisk 0,98–0,99.")
            u["alpha"] = round(-1.0 / eta_kedel, 4)

        elif type_ == "gas_engine_chp":
            if eta_el is None:
                raise ArkFejl(
                    f"Række {raekke}: gasmotoren mangler elvirkningsgrad. "
                    "Skriv MWh el pr. MWh brændsel, fx 0,41. Uden den kender "
                    "modellen ikke elindtægten, og hele pointen med en gasmotor "
                    "forsvinder.")
            if not 0 < eta_el < 0.60:
                raise ArkFejl(
                    f"Række {raekke}: elvirkningsgrad {eta_el} ser forkert ud. "
                    "Den skal være en brøkdel, fx 0,41 — ikke 41.")
            eta_varme = u["eta_fuel_to_heat"]
            samlet = eta_el + eta_varme
            if not 0.70 <= samlet <= 1.05:
                raise ArkFejl(
                    f"Række {raekke}: el- og varmevirkningsgrad giver tilsammen "
                    f"{samlet:.2f}. En gasmotor ligger typisk på 0,85–0,95. Står "
                    "de to tal på samme grundlag (nedre brændværdi), og er "
                    "varmen målt ab motor?")
            u["alpha"] = round(eta_el / eta_varme, 4)
            print(f"    Række {raekke}: alpha = {u['alpha']:.3f} "
                  f"(el {eta_el:.2f} ÷ varme {eta_varme:.2f})")

        else:
            u["alpha"] = 0.0
        if type_ in ("gas_boiler", "gas_engine_chp"):
            u["co2_emissions_per_mwh_fuel"] = 0.2

        # Unit commitment kun hvor det betyder noget: enheder med en reel
        # minimumslast eller en bindende driftstid.
        # Solvarme er vejrbestemt og har intet start/stop at optimere; en
        # bunden min-last på en solfanger gør modellen infeasible om natten.
        u["uc_enabled"] = (type_ != "solar_thermal"
                           and bool(u["p_min_heat"] > 0 or u["min_uptime"] > 1))
        if u["uc_enabled"]:
            u["initial_status"] = 0

        byder = str(r["balance"]).strip().lower() in ("ja", "true", "1", "x")
        u["ancillary"] = {"afrr_qualified": byder, "mfrr_qualified": byder,
                          "fcr_qualified": False}
        units[navn] = u

    if not any(u["fuel"] == "electricity" for u in units.values()):
        print("    Ingen elforbrugende enhed. Uden varmepumpe eller elkedel er der "
              "hverken spotarbitrage eller balancemarked at hente — casen kører, "
              "men businesscasen bliver tynd.")
    return units


def laes_tanke(sti: Path) -> dict:
    df = pd.read_excel(sti, sheet_name="Anlaeg", skiprows=50, usecols=range(5), nrows=6)
    df.columns = ["navn", "volumen", "e_max", "lade", "aflade"]
    df = df.dropna(subset=["navn", "volumen"])
    if df.empty:
        raise ArkFejl("Arket Anlaeg har ingen akkumuleringstanke. "
                      "Uden lager er der ingen businesscase at regne på.")

    storage: dict = {}
    for i, r in df.iterrows():
        raekke = int(i) + 52
        vol = tal(r["volumen"], f"tank række {raekke}, volumen", kraev=True)
        e_max = tal(r["e_max"], f"tank række {raekke}, maks fyldning", kraev=True)
        if not 0.5 < e_max < 5000:
            raise ArkFejl(
                f"Tank række {raekke}: maks fyldning på {e_max} MWh ser forkert "
                "ud. En tank på 5.000 m³ rummer typisk 150–250 MWh. Står tallet "
                "i kWh eller i m³?")
        # Temperaturspringet spørger vi ikke om — men modellen skal have det,
        # og det er samtidig den eneste kontrol af, at volumen og MWh passer
        # sammen. 1 m³ vand pr. K er 1,163 kWh.
        dt = e_max * 1000.0 / (1.163 * vol)
        if not 10 <= dt <= 80:
            raise ArkFejl(
                f"Tank række {raekke}: {vol:.0f} m³ og {e_max:.0f} MWh svarer "
                f"til et temperaturspring på {dt:.0f} K mellem frem og retur. "
                "Det ligger uden for det fysisk rimelige (typisk 25–60 K), så "
                "et af de to tal er forkert — oftest volumen i liter eller "
                "fyldningen i kWh.")
        if not 20 <= dt <= 70:
            print(f"    Tank række {raekke}: volumen og maks fyldning svarer til "
                  f"{dt:.0f} K. Det er i den yderlige ende — tjek begge tal.")
        storage[slug(r["navn"])] = {
            "enabled": True,
            "volume_m3": int(vol),
            "delta_t_k": round(dt, 2),
            "e_max_mwh": round(e_max, 1),
            "e_initial_mwh": round(e_max * 0.5, 1),
            "p_max_charge_mw": tal(r["lade"], f"tank række {raekke}, ladeeffekt") or 25.0,
            "p_max_discharge_mw": tal(r["aflade"], f"tank række {raekke}, afladeeffekt") or 25.0,
            "self_discharge_per_hour": 0.0005,
            "cycle_binding": True,
        }
    return storage


def skriv_solprofil(sti: Path, start: str, slut: str, aars_gwh: float) -> None:
    """Syntetisk solvarmeprofil, der dækker HELE kørselsvinduet.

    Samme fysik som scripts/generate_solar_andeby.py — daglængde på 56° N,
    sinusbue over dagen, sæsonintensitet og skydække — men skaleret til
    deltagerens egen årsproduktion og skrevet for netop de kalenderår,
    tidsvinduet rører. Dækker profilen ikke hele perioden, stopper modellen;
    den nulfyldes ikke.

    Det er en PLAUSIBEL profil, ikke måledata. Har værket sine egne
    soltimeværdier, er de bedre, og filen kan erstattes uden andre ændringer.
    """
    import math

    import numpy as np

    aar = sorted({int(start[:4]), int(slut[:4])})
    rammer = []
    for y in aar:
        idx = pd.date_range(f"{y}-01-01 00:00", f"{y}-12-31 23:00", freq="h", tz="UTC")
        doy = idx.dayofyear.to_numpy().astype(float)
        time_paa_dogn = idx.hour.to_numpy().astype(float)

        decl = np.deg2rad(23.45 * np.sin(np.deg2rad(360.0 / 365.0 * (doy - 81))))
        cos_omega = np.clip(-np.tan(math.radians(56.0)) * np.tan(decl), -1.0, 1.0)
        daglaengde = 24.0 / math.pi * np.arccos(cos_omega)

        theta = 2.0 * math.pi * (doy - 172) / 365.0
        saeson = 0.20 + 0.80 * (1.0 + np.cos(theta)) / 2.0

        opgang = 12.0 - daglaengde / 2.0
        nedgang = 12.0 + daglaengde / 2.0
        dag = (time_paa_dogn >= opgang) & (time_paa_dogn <= nedgang)
        sikker = np.where(daglaengde > 0, daglaengde, 1.0)
        dogn = np.where(dag, np.sin(np.pi * np.clip(
            (time_paa_dogn - opgang) / sikker, 0.0, 1.0)), 0.0)

        rng = np.random.default_rng(1964 + y)
        sky = np.clip(1.0 - np.abs(rng.normal(0.0, 0.15 + 0.20 * saeson)), 0.05, 1.0)

        raa = np.clip(saeson * dogn * sky, 0.0, None)
        effekt = raa * (aars_gwh * 1000.0 / raa.sum())
        rammer.append(pd.DataFrame({"time": idx, "power_mw": effekt}))

    df = pd.concat(rammer, ignore_index=True).drop_duplicates("time").sort_values("time")
    sti.parent.mkdir(parents=True, exist_ok=True)
    ud = df.copy()
    ud["time"] = ud["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    ud.to_csv(sti, index=False, float_format="%.6f")
    print(f"  Solvarmeprofil: {len(df)} timer, {aars_gwh:.1f} GWh/år, "
          f"peak {df['power_mw'].max():.1f} MW → {sti}")


# ------------------------------------------------------------------- priser
def laes_priser(sti: Path) -> tuple[dict, dict, dict]:
    raa = pd.read_excel(sti, sheet_name="Priser", header=None)

    def celle(r, c):
        try:
            return raa.iat[r, c]
        except IndexError:
            return None

    navne = {"naturgas": "natural_gas", "halm": "straw", "flis": "flis",
             "overskudsvarme": "waste_heat", "CO2": "co2_eua"}
    # CO2 opgives pr. ton CO2. Modellen ganger selv med enhedens
    # co2_emissions_per_mwh_fuel (0,2 t CO2 pr. MWh naturgas), så et tal pr.
    # MWh gas her ville blive ganget med 0,2 én gang for meget.
    enheder = {"co2_eua": "DKK/t_CO2"}
    priser = {}
    for i, (dansk, noegle) in enumerate(navne.items()):
        v = tal(celle(5 + i, 1), f"Priser: {dansk}")
        if v is not None:
            priser[noegle] = {"value": v,
                              "unit": enheder.get(noegle, "DKK/MWh_fuel")}

    afgift = tal(celle(13, 1), "Priser: elafgift", kraev=True)
    energinet = tal(celle(14, 1), "Priser: Energinet-tarif", kraev=True)
    dv = tal(celle(15, 1), "Priser: drift og vedligehold") or 0.0
    prod = tal(celle(16, 1), "Priser: produktionstarif") or 0.0

    baand_navne = ["lav", "hoej", "spids"]
    vinter_v, sommer_v, bands = {}, {}, {}
    for i, b in enumerate(baand_navne):
        vi = tal(celle(21 + i, 1), f"Priser: {b}, vinter")
        so = tal(celle(21 + i, 2), f"Priser: {b}, sommer")
        if vi is not None:
            vinter_v[b] = vi
        if so is not None:
            sommer_v[b] = so
        if vi is not None or so is not None:
            bands[b] = vi if vi is not None else so
    if "lav" not in bands or "hoej" not in bands:
        raise ArkFejl("Priser: lavlast og højlast skal begge udfyldes i "
                      "tarifskemaet — mindst én af kolonnerne vinter og sommer.")

    vinter_spids = "spids" if "spids" in vinter_v else "hoej"
    sommer_hoej = "hoej" if "hoej" in sommer_v else "hoej"
    tarif = {
        "unit": "kr_per_mwh",
        "source": "Deltagerens eget prisblad, indtastet i vaerksdata_skabelon.xlsx",
        "fixed_components": {"energinet": energinet, "dv": dv,
                             "elafgift_net": afgift},
        "net_tariff": {
            "bands": bands,
            "seasons": {
                "vinter": {
                    "months": [10, 11, 12, 1, 2, 3],
                    "weekday": {"00-06": "lav", "06-21": vinter_spids, "21-24": "hoej"},
                    "weekend": {"00-06": "lav", "06-21": "hoej", "21-24": "hoej"},
                },
                "sommer": {
                    "months": [4, 5, 6, 7, 8, 9],
                    "weekday": {"00-06": "lav", "06-24": sommer_hoej},
                    "weekend": {"00-06": "lav", "06-24": "lav"},
                },
            },
        },
    }
    uenige = [b for b in vinter_v if b in sommer_v and vinter_v[b] != sommer_v[b]]
    if uenige:
        print(f"    Båndene {', '.join(uenige)} har forskellig sats vinter og "
              "sommer. Skemaet bruger ét sæt satser pr. båndnavn, og vintertallene "
              "er brugt. Skal sommeren have egne satser, så tilføj bånd med andre "
              "navne i casefilen.")

    omraade = str(celle(27, 1) or "").strip().lower()
    if omraade not in ("fyn", "vestkyst", "karup"):
        raise ArkFejl(f"Priser: DMI-område '{omraade}' er ikke kendt. "
                      "Vælg fyn, vestkyst eller karup.")
    zone = str(celle(28, 1) or "").strip().upper()
    if zone not in ("DK1", "DK2"):
        raise ArkFejl(f"Priser: priszone '{zone}' er ikke kendt. Vælg DK1 eller DK2.")
    vaerk = str(celle(29, 1) or "").strip()

    el = {"spot_area": zone, "tariff_consumption_flat": round(
        energinet + dv + bands.get("hoej", 0.0), 1),
        "tariff_consumption": tarif,
        "tariff_production_flat": prod,
        "electricity_tax": afgift}
    data = {"dmi_area": omraade, "price_zone": zone}
    return priser, el, {"data": data, "vaerk": vaerk}


# --------------------------------------------------------------------- YAML
def _rent(v):
    """numpy-skalarer ind, almindelige Python-typer ud.

    pandas leverer np.float64, og PyYAML nægter at serialisere dem. Fejlen kom
    først til syne som en halvskrevet casefil, så den ryddes ét sted for hele
    træet frem for felt for felt."""
    if isinstance(v, dict):
        return {k: _rent(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_rent(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        return v.item()
    return v


def skriv_yaml(sti: Path, d: dict, vaerk: str, kilde: Path,
               csv_sti: Path | None) -> None:
    import yaml

    d = _rent(d)

    hoved = f"""\
# ==============================================================================
# {vaerk.upper()}
# ==============================================================================
# Bygget af scripts/vaerksark_til_yaml.py ud fra {kilde.name}.
#
# KØR:
#   python run_case.py {sti.as_posix()} --data-source github \\
#       --heat-csv {csv_sti.as_posix() if csv_sti else "(ingen målt varmelast — se heat_load_params)"}
#
# Tidsvinduet nedenfor er sat af timedataens første og sidste time. Alt andet
# stammer fra arkene Anlaeg og Priser.
#
# TJEK DISSE FIRE, FØR DU STOLER PÅ TALLENE:
#   1. balancing-blokken nedenfor er slået fra. Slå den til, og udfyld lofterne,
#      hvis værket faktisk er prækvalificeret hos Energinet.
#   2. tankenes startfyldning er sat til halvt fuld. Ved korte vinduer betyder
#      det noget; ved et helt år med cycle_binding betyder det lidt.
#   3. min driftstid og startomkostninger er dem, du skrev i arket. De styrer,
#      hvor ofte modellen tør stoppe en kedel.
#   4. p_max_heat er hver enheds loft ifølge typeskiltet, ikke et mål. For
#      solvarme er det nameplate, og profilen binder reelt langt lavere —
#      ser du 22 MW her og 8 MW i resultatet, er det profilen, der virker.
#   5. solvarmeprofilen er syntetisk: plausibel fysik skaleret til den
#      årsproduktion, du opgav. Har I egne soltimeværdier, så erstat filen —
#      kolonnerne er time (UTC, ISO 8601) og power_mw.
# ==============================================================================
"""
    with sti.open("w", encoding="utf-8") as f:
        f.write(hoved)
        yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False,
                       default_flow_style=False, width=88)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ark", type=Path, help="Den udfyldte vaerksdata_skabelon.xlsx")
    p.add_argument("--cases-dir", type=Path, default=Path("cases"))
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--overskriv", action="store_true",
                   help="Erstat filer, der allerede findes.")
    a = p.parse_args()

    if not a.ark.exists():
        print(f"FEJL: {a.ark} findes ikke.", file=sys.stderr)
        return 2

    try:
        print(f"Læser {a.ark.name}")
        priser, el, meta = laes_priser(a.ark)
        vaerk = meta["vaerk"] or a.ark.stem
        s = slug(vaerk)
        tz = laes_tidszone(a.ark)
        aars_gwh = laes_aarsproduktion(a.ark)
        csv_sti, start, slut, aarsvolumen = laes_timedata(
            a.ark, s, a.data_dir, a.overskriv, tz, aars_gwh)
        units = laes_enheder(a.ark, priser)
        storage = laes_tanke(a.ark)
    except ArkFejl as e:
        print(f"\nArket kan ikke bruges endnu:\n  {e}\n", file=sys.stderr)
        return 1

    # heat_load_params kræves af loaderen, også når varmelasten kommer fra CSV.
    # Referencen er Andebys ~100 GWh-kalibrering (selv Billunds v2 × 0,784);
    # den skaleres til deltagerens eget årsvolumen, så casen også kan køre
    # UDEN --heat-csv, fx på et vindue der rækker ud over arkets data.
    aarsvolumen = float(aarsvolumen)
    f = round(aarsvolumen / 100.0, 4) if aarsvolumen > 1 else 1.0
    andeby_profil = [4.437, 4.500, 4.602, 4.767, 4.822, 5.112,
                     5.590, 5.606, 5.355, 4.955, 4.775, 4.696,
                     4.563, 4.469, 4.414, 4.359, 4.430, 4.602,
                     4.728, 4.767, 4.735, 4.728, 4.610, 4.390]
    heat_params = {
        "gaf_mw_per_k": round(0.7653 * f, 4),
        "t_ref": 15.0,
        "thermal_inertia_hours": 24,
        "nettab_slope_mw_per_k": round(0.4768 * f, 4),
        "t_net": 12.0,
        "baseline_profile_mw": [round(v * f, 3) for v in andeby_profil],
        "weekly_dip": 0.02,
        "_source": (f"Andeby-kalibrering skaleret med {f} til {aarsvolumen:.1f} GWh/år. "
                    "BEMÆRK: en skaleret døgnprofil, ikke en kalibrering på jeres "
                    "egne data. Bruges kun ved kørsel uden --heat-csv. Vil I have "
                    "rigtige parametre, så kør scripts/calibrate_heat_load.py."),
    }
    print(f"  Årsvolumen ab værk: {aarsvolumen:.1f} GWh — syntese-profil skaleret med {f}")

    case = {
        "meta": {
            "case_name": s,
            "titel": vaerk,
            "description": (f"{vaerk} — bygget fra deltagerens egen dataskabelon "
                            f"({a.ark.name}) på kurset AI til driftsoptimering i "
                            "fjernvarmen. Varmelasten er målte timeværdier, ikke "
                            "syntese."),
            "gruppe": s,
            "timezone_internal": "UTC",
            "timezone_reporting": "Europe/Copenhagen",
            "discount_rate_real": 0.035,
            "tax_year": int(start[:4]),
        },
        "data": meta["data"],
        "time": {"start": start, "end": slut, "resolution": "1h"},
        "solver": {"mip_rel_gap": 0.001, "mip_abs_gap": 1000.0, "time_limit": 3600.0},
        "heat_load_params": heat_params,
        "prices": priser,
        "electricity": el,
        "units": units,
        "storage": storage,
    }

    # Solvarme: profilen skrives nu, hvor tidsvinduet er kendt, og feltet
    # _sol_gwh byttes ud med den sti, modellen faktisk læser.
    for navn, u in units.items():
        if "_sol_gwh" in u:
            profil = a.data_dir / f"{s}_{navn}_profil.csv"
            if profil.exists() and not a.overskriv:
                print(f"\nFEJL: {profil} findes allerede. Brug --overskriv.",
                      file=sys.stderr)
                return 1
            skriv_solprofil(profil, start, slut, u.pop("_sol_gwh"))
            u["production_profile_path"] = profil.as_posix()
            u["notes"] = (
                "p_max_heat er nameplate. Modellen bruger hver time den laveste "
                "af p_max_heat og profilen, og profilen binder næsten altid — "
                "det er årsproduktionen bag profilen, der bestemmer, hvor meget "
                "sol der kommer ind. Profilen er syntetisk; erstat filen med "
                "egne måledata, hvis I har dem.")

    yaml_sti = a.cases_dir / f"{s}.yaml"
    if yaml_sti.exists() and not a.overskriv:
        print(f"\nFEJL: {yaml_sti} findes allerede. Brug --overskriv.", file=sys.stderr)
        return 1
    yaml_sti.parent.mkdir(parents=True, exist_ok=True)
    skriv_yaml(yaml_sti, case, vaerk, a.ark, csv_sti)

    print(f"  Enheder: {len(units)} · tanke: {len(storage)}")
    if csv_sti is None:
        print(f"\nSkrevet:\n  {yaml_sti}\n")
        print("Kør den med:\n"
              f"  python run_case.py {yaml_sti.as_posix()} --data-source github\n")
        print("Der er INGEN målt varmelast i denne case. Varmen dannes af "
              "heat_load_params ud fra DMI-vejrdata og den årsproduktion, der "
              "stod i arket. Tallene viser, hvad anlægget kunne gøre på et "
              "normalår — ikke hvad det gjorde.")
    else:
        print(f"\nSkrevet:\n  {yaml_sti}\n  {csv_sti}\n")
        print("Kør den med:\n"
              f"  python run_case.py {yaml_sti.as_posix()} --data-source github \\\n"
              f"      --heat-csv {csv_sti.as_posix()}\n")
    print("Balancemarkedet er slået fra i den genererede case. Læs blokken øverst "
          "i filen, før du tilføjer det.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
