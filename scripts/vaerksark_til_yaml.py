#!/usr/bin/env python3
"""
vaerksark_til_yaml.py — deltagerens udfyldte Excelark til en gyldig casefil.

    python scripts/vaerksark_til_yaml.py mit_vaerk.xlsx

Skriver som standard i den git-ignorerede mappe deltagere/:

    deltagere/cases/<slug>.yaml                  casefilen
    deltagere/data/<slug>_abvaerk_hourly.csv     varmelasten fra arket Timedata

Et værks timedata må ikke ende i det offentlige repo. Scriptet stopper derfor,
hvis det skulle skrive en fil — eller læse arket — et sted inde i repoet, som
git ikke ignorerer. Læg arket i deltagere/ (eller uden for repoet).
--tillad-offentlig slår vagten fra; den er til egne referencecases som Andeby,
aldrig til en deltagers data.

Varmepumper læses fra arket Varmepumpe som målepunkter (udetemperatur,
varme, el) og bliver en cop_curve af typen 'table' med et varmeloft, der
følger udetemperaturen. Uden målepunkter bruges COP ved 0 °C fra Anlaeg og
den gamle lineære kurve med fast varmeloft, og konverteringen siger det.

Er arket Timedata tomt, men årsproduktionen i B3 udfyldt, skrives kun
casefilen, og varmelasten syntetiseres af modellen ud fra DMI-vejrdata.

Arket Priser læses på etiketterne i kolonne A, ikke på rækkenumre: rækker
må indsættes og flyttes, men posterne må ikke omdøbes. Brændselsblokken
kender naturgas, halm, træpiller, flis, overskudsvarme og CO2.

Tre ting er valgfrie og findes ikke i skabelon v4:
  * Anlaeg, kolonne N 'brændsel': halm, træpiller eller flis pr.
    biomassekedel. Uden kolonnen bruges det ene biomassebrændsel, der har en
    pris; har flere en pris, siges valget højt eller kørslen stopper.
  * Priser, blokken 'Gasafgifter og gastariffer': én række pr. afgift eller
    tarif med sats, enhed (kr/m3 eller kr/MWh) og hvem den gælder for (alle,
    kedler, motorer). Det, der gælder alle, lægges på gasprisen. Det, der
    kun gælder kedler eller motorer, lægges på enhedens D&V pr. MWh varme,
    fordi modellen ikke har en afgift pr. enhed.
  * Arket 'Solvarme': målte timeværdier for solvarmen, opbygget som
    Timedata. Findes det, bruges det i stedet for den syntetiske profil.

og kører derefter:

    python run_case.py deltagere/cases/<slug>.yaml --data-source github \
        --heat-csv deltagere/data/<slug>_abvaerk_hourly.csv

Scriptet SKRIVER ALDRIG hen over en eksisterende fil uden --overskriv, og det
stopper højlydt på alt, det ikke kan tolke. En case, der bygger på et ark med
en tom kolonne, er værre end ingen case: tallene ser rigtige ud.

Skabelonen ligger i doc/vaerksdata_skabelon.xlsx.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import unicodedata
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Området kommer fra config, ikke fra en kopi her: skabelonens dropdown, modellens
# indlæsning og denne konvertering skal altid kende de samme DMI-områder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import KENDTE_DMI_OMRAADER  # noqa: E402

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

# Biomassebrændsler: arkets ord -> modellens nøgle under prices.
BIOMASSE = {"halm": "straw", "træpiller": "wood_pellets", "flis": "flis"}
BIOMASSE_DANSK = {v: k for k, v in BIOMASSE.items()}
# Hvad kolonnen 'brændsel' må sige for de øvrige typer (den bruges ikke, men
# en gaskedel, der står til flis, er en fejl i arket og ikke noget at tie om).
BRAENDSEL_ORD = {
    "gas_boiler": {"naturgas", "gas"}, "gas_engine_chp": {"naturgas", "gas"},
    "heat_pump": {"el"}, "electric_boiler": {"el"},
    "solar_thermal": {"sol", "solvarme"}, "waste_heat": {"overskudsvarme"},
}


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


def find_raekke(sti: Path, ark: str, start: str, *, praefiks=False,
                efter: int = 0) -> int | None:
    """1-baseret rækkenummer for første celle i kolonne A, der er `start`
    (uden hensyn til store/små bogstaver og mellemrum omkring), eller — med
    praefiks — begynder med den. Rækker til og med `efter` springes over.

    Blokkene i arkene (enheder, tanke, målepunkter) findes på deres overskrift
    og ikke på et fast rækkenummer: vejledningen beder deltageren slette de
    grå rækker, og så rykker alt under dem op."""
    raa = pd.read_excel(sti, sheet_name=ark, header=None, usecols=[0])
    for i, v in enumerate(raa.iloc[:, 0], start=1):
        if i <= efter or not isinstance(v, str):
            continue
        t = " ".join(v.split()).lower()
        if t == start or (praefiks and t.startswith(start)):
            return i
    return None


def _norm(v) -> str:
    """Etiket til sammenligning: små bogstaver, ét mellemrum, ingen kanter."""
    return " ".join(v.split()).lower() if isinstance(v, str) else ""


def tjek_formler_uden_vaerdi(sti: Path, ark: str = "Anlaeg") -> None:
    """Stop, hvis en formel i arket ikke har en beregnet værdi i filen.

    pandas læser den værdi, Excel sidst regnede ud. En fil, der er gemt af et
    script eller et program, der ikke regner formler, har ingen — og så blev
    en startomkostning skrevet som formel til 0 kr. uden besked."""
    import openpyxl
    try:
        wf = openpyxl.load_workbook(sti, read_only=True, data_only=False)
        wv = openpyxl.load_workbook(sti, read_only=True, data_only=True)
    except Exception:
        return
    try:
        if ark not in wf.sheetnames:
            return
        uden = []
        for rf, rv in zip(wf[ark].iter_rows(max_col=14), wv[ark].iter_rows(max_col=14)):
            for cf, cv in zip(rf, rv):
                if isinstance(cf.value, str) and cf.value.startswith("=") \
                        and cv.value is None:
                    uden.append(f"{cf.coordinate} ({cf.value})")
    finally:
        wf.close()
        wv.close()
    if uden:
        raise ArkFejl(
            f"Arket {ark} har {len(uden)} celler med en formel, som filen ikke "
            f"har en beregnet værdi for: {', '.join(uden[:6])}"
            + (" …" if len(uden) > 6 else "") + ". Det sker, når arket er gemt "
            "af et program, der ikke regner formler ud. Åbn arket i Excel og gem "
            "det igen, eller skriv tallene i cellerne i stedet for formlerne.")


def _regn_formel(f: str):
    """Ren talformel som `=65*3,6`: kun tal og + - * / ( ). Alt andet → None."""
    import ast
    import operator
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
                and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        raise ValueError
    try:
        return ev(ast.parse(f.lstrip("=").strip().replace(",", "."), mode="eval"))
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None


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
def laes_tidszone(sti: Path, ark: str = "Timedata") -> str:
    """Deltagerens erklæring, ikke vores gæt.

    Modellen regner i UTC, og skabelonen beder om UTC. Men et SRO-udtræk kommer
    ofte i dansk tid, og en deltager, der konverterer i hånden, rammer forkert
    oftere end scriptet gør. Derfor er feltet et valg mellem to værdier — og
    alt andet stopper kørslen frem for at blive tolket."""
    raa = pd.read_excel(sti, sheet_name=ark, header=None, nrows=3)
    try:
        v = raa.iat[1, 1]
        v = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip().lower()
    except IndexError:
        v = ""
    # Store/små bogstaver og mellemrum (også Excels hårde mellemrum) er ikke
    # en tolkning. 'Dansk lokal' er ikke 'dansk lokaltid' og bliver ikke gættet.
    k = "".join(v.split())
    if k in ("utc", "utc+0", "z", "gmt"):
        return "UTC"
    if k in ("dansklokaltid", "dansktid", "lokaltid", "europe/copenhagen",
             "cet", "cest"):
        return "Europe/Copenhagen"
    raise ArkFejl(
        f"Tidszonefeltet i {ark} (celle B2) siger {v!r}. Det skal stå som "
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
                  tz: str, aars_gwh: float | None = None,
                  timeslut: bool = False
                  ) -> tuple[Path | None, str, str, float, "pd.DataFrame | None"]:
    df = pd.read_excel(sti, sheet_name="Timedata", skiprows=4, usecols=[0, 1])
    df.columns = ["timestamp", "heat_mw_abvaerk"]
    df = df.dropna(how="all")
    df["raekke"] = df.index + 6          # rækkenummeret i Excel, til fejlbeskeder

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
        return None, "2025-07-01T00:00:00Z", "2026-06-30T23:00:00Z", aars_gwh, None

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

    # Tekst i talkolonnen ('???', '-', 'n/a', et tal med komma som tekst) skal
    # stoppe med række og indhold, ikke give et traceback længere nede.
    maalt = pd.to_numeric(df["heat_mw_abvaerk"], errors="coerce")
    tekst = maalt.isna()
    if tekst.any():
        eks = "; ".join(f"række {int(r.raekke)}: {r.heat_mw_abvaerk!r}"
                        for r in df[tekst].head(5).itertuples())
        raise ArkFejl(
            f"{int(tekst.sum())} værdier i kolonne B i Timedata er tekst og ikke "
            f"tal — {eks}. Slet indholdet af cellen, så den står tom (tomme "
            "timer udfyldes af modellen), eller skriv tallet.")
    df["heat_mw_abvaerk"] = maalt

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
        lokal = df["timestamp"].dt
        if dubletter.any():
            # Kun efterårets dobbelttime (kl. 02 den sidste søndag i oktober)
            # må stå to gange. Alt andet er en fejl i udtrækket, fx en række
            # med forkert dato, og må ikke ende som dublet i timefilen.
            tvetydig = lokal.tz_localize("Europe/Copenhagen", ambiguous="NaT",
                                         nonexistent="shift_forward").isna()
            uventet = dubletter & ~tvetydig
            if uventet.any():
                eks = "; ".join(
                    f"række {int(r.raekke)}: {r.timestamp:%Y-%m-%d %H:%M}"
                    for r in df[uventet].head(5).itertuples())
                raise ArkFejl(
                    f"{int(uventet.sum())} tidsstempler i Timedata går igen uden at "
                    f"være efterårets dobbelttime — {eks}. Kun timen kl. 02 den "
                    "sidste søndag i oktober må stå to gange i dansk tid. Er det en "
                    "række med forkert dato eller år, så ret den (eller slet den).")
            print(f"    {int(dubletter.sum())} gentagne tidsstempler — det er "
                  "efterårets dobbelttime i dansk tid, som forventet.")
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

    if timeslut:
        # Stemplet er timens SLUT (01:00 = kl. 00-01). Modellen bruger timens
        # start. Flyttes først efter omregning til UTC, så efterårets
        # dobbelttime ikke bliver til to ens timer.
        df["timestamp"] = df["timestamp"] - timedelta(hours=1)
        print("    Tidsstempler læst som timeslut og flyttet én time tilbage "
              "(01:00 betyder kl. 00-01).")

    df = df.sort_values("timestamp").reset_index(drop=True)

    # Perioden er fast: 1. juli 2025 kl. 00 til 30. juni 2026 kl. 23, i den
    # tidszone arket er skrevet i. Dækning måles mod den — ikke mod seriens eget
    # første og sidste tidsstempel, for så ser en serie uden juni fuldstændig ud.
    if tz == "UTC":
        v_start = pd.Timestamp("2025-07-01 00:00")
        v_slut = pd.Timestamp("2026-06-30 23:00")
    else:
        v_start = (pd.Timestamp("2025-07-01 00:00", tz="Europe/Copenhagen")
                   .tz_convert("UTC").tz_localize(None))
        v_slut = (pd.Timestamp("2026-06-30 23:00", tz="Europe/Copenhagen")
                  .tz_convert("UTC").tz_localize(None))
    vindue_timer = int((v_slut - v_start) / timedelta(hours=1)) + 1
    uden_for = (df["timestamp"] < v_start) | (df["timestamp"] > v_slut)
    if uden_for.any():
        eks = "; ".join(f"række {int(r.raekke)}: {r.timestamp:%Y-%m-%d %H:%M}"
                        for r in df[uden_for].head(5).itertuples())
        raise ArkFejl(
            f"{int(uden_for.sum())} tidsstempler i Timedata ligger uden for "
            f"perioden 1. juli 2025 – 30. juni 2026 — {eks}. Et tidsstempel som "
            "1900 betyder som regel, at cellen ikke er en dato. Ret eller slet "
            "rækkerne.")
    spaend = df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]
    fulde_timer = int(spaend / timedelta(hours=1)) + 1
    huller = fulde_timer - len(df)
    i_vinduet = int(df["timestamp"].nunique())
    daekning = i_vinduet / vindue_timer

    negative = (df["heat_mw_abvaerk"] < 0).sum()
    if negative:
        raise ArkFejl(f"{negative} værdier i Timedata er negative. "
                      "Varmeproduktion ab værk kan ikke være under nul.")

    ud = ud_dir / f"{slugnavn}_abvaerk_hourly.csv"
    if ud.exists() and not overskriv:
        raise ArkFejl(f"{ud} findes allerede. Kør med --overskriv, hvis den skal erstattes.")
    # Selve filen skrives først i main(), når hele arket er valideret, så en
    # fejl længere nede ikke efterlader en timefil (og kræver --overskriv).

    start = df["timestamp"].iloc[0].strftime("%Y-%m-%dT%H:00:00Z")
    slut = df["timestamp"].iloc[-1].strftime("%Y-%m-%dT%H:00:00Z")
    maalt_gwh = float(df["heat_mw_abvaerk"].sum() / 1000.0)
    aarsvolumen = maalt_gwh * (vindue_timer / max(i_vinduet, 1))

    print(f"  Timedata: {len(df)} timer, {df['timestamp'].iloc[0]:%Y-%m-%d} til "
          f"{df['timestamp'].iloc[-1]:%Y-%m-%d} (UTC), dækning af perioden "
          f"1. juli 2025 – 30. juni 2026: {daekning:.1%}")
    i_start = int((df["timestamp"].iloc[0] - v_start) / timedelta(hours=1))
    i_slut = int((v_slut - df["timestamp"].iloc[-1]) / timedelta(hours=1))
    if i_start > 0 or i_slut > 0:
        dele = []
        if i_start > 0:
            dele.append(f"{i_start} timer i starten (serien begynder "
                        f"{df['timestamp'].iloc[0]:%d/%m %H:%M} UTC, ikke {v_start:%d/%m %H:%M} UTC)")
        if i_slut > 0:
            dele.append(f"{i_slut} timer i slutningen (serien slutter "
                        f"{df['timestamp'].iloc[-1]:%d/%m %H:%M} UTC, ikke {v_slut:%d/%m %H:%M} UTC)")
        print("    ADVARSEL: perioden er ikke dækket. Der mangler " + " og ".join(dele) +
              ". Enderne kan modellen ikke interpolere; kørslen regner på det, der er.")
    if i_vinduet < vindue_timer:
        print(f"    Årsvolumen er {maalt_gwh:.1f} GWh i de {i_vinduet} timer, der er, "
              f"og regnes op til {aarsvolumen:.1f} GWh for {vindue_timer} timer.")

    # Krydstjek mod det årstal, deltageren selv har skrevet. De to tal kommer
    # fra hver sin kilde — SRO-udtrækket og årsopgørelsen — og er de uenige,
    # er det som regel enheden (MW mod MWh) eller en manglende måler.
    if aars_gwh is not None:
        afvig = (aarsvolumen - aars_gwh) / aars_gwh
        if abs(afvig) <= 0.05:
            print(f"    Timeserien svarer til {aarsvolumen:.1f} GWh/år; B3 siger "
                  f"{aars_gwh:.1f} GWh ({afvig:+.1%}). Modellen bruger timeserien.")
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
    return ud, start, slut, aarsvolumen, df[["timestamp", "heat_mw_abvaerk"]]


# --------------------------------------------------------------- varmepumpe
# Arket Varmepumpe: overskrift i række 5, målepunkter fra række 6, kolonne
# A-D (navn, udetemperatur, varmeproduktion, eloptag). Kolonne E er en
# COP-formel til deltageren selv og læses ikke.
VP_FOERSTE_RAEKKE = 6
VP_MAKS_RAEKKER = 18          # række 6-23; noteboksen står i række 25
VP_COP_MIN, VP_COP_MAX = 1.5, 6.0


def laes_varmepumper(sti: Path) -> dict[str, list[dict]]:
    """Målepunkter pr. varmepumpe, nøglet på slug(navn).

    Et ark fra før v4 har ikke arket Varmepumpe. Så returneres {}, og
    varmepumper falder tilbage på COP ved 0 °C i arket Anlaeg.
    """
    try:
        hr = find_raekke(sti, "Varmepumpe", "navn")
    except ValueError:                      # ark uden arket Varmepumpe
        return {}
    if hr is None:
        raise ArkFejl("Arket Varmepumpe: overskriften 'navn' i kolonne A er ikke "
                      "til at finde. Slet ikke overskriftsrækken.")
    foerste = hr + 1
    note = find_raekke(sti, "Varmepumpe", "tjek cop", praefiks=True, efter=hr)
    try:
        df = pd.read_excel(sti, sheet_name="Varmepumpe", header=None,
                           skiprows=foerste - 1, usecols=range(4),
                           nrows=(note - foerste) if note else VP_MAKS_RAEKKER)
    except ValueError:
        return {}
    # Tomme kolonner i bunden af arket kan falde helt ud af indlæsningen.
    df = df.reindex(columns=range(4))
    df.columns = ["navn", "t", "varme", "el"]

    tabeller: dict[str, list[dict]] = {}
    for i, r in df.iterrows():
        raekke = int(i) + foerste
        tom_navn = pd.isna(r["navn"]) or str(r["navn"]).strip() == ""
        tal_felter = [r["t"], r["varme"], r["el"]]
        if tom_navn and all(pd.isna(v) for v in tal_felter):
            continue
        if tom_navn:
            raise ArkFejl(f"Varmepumpe række {raekke}: der står tal, men intet "
                          "navn. Skriv varmepumpens navn, som det står i Anlaeg.")
        felt = f"Varmepumpe række {raekke}"
        t = tal(r["t"], f"{felt}, udetemperatur", kraev=True)
        q = tal(r["varme"], f"{felt}, varmeproduktion", kraev=True)
        e = tal(r["el"], f"{felt}, eloptag", kraev=True)
        if not -30 <= t <= 40:
            raise ArkFejl(f"{felt}: udetemperaturen {t} °C ser forkert ud.")
        if q <= 0 or e <= 0:
            raise ArkFejl(f"{felt}: varmeproduktion og eloptag skal begge være "
                          "større end nul.")
        cop = q / e
        if not VP_COP_MIN <= cop <= VP_COP_MAX:
            raise ArkFejl(
                f"{felt}: {q:g} MW varme og {e:g} MW el giver COP {cop:.2f}. "
                f"En luft/vand-varmepumpe ligger typisk på 2–4. Er varme og el "
                "byttet om, eller står et af tallene i kW?")
        tabeller.setdefault(slug(r["navn"]), []).append(
            {"t_ambient": t, "heat_mw": q, "el_mw": e, "raekke": raekke})

    for navn, pkt in tabeller.items():
        temps = [p["t_ambient"] for p in pkt]
        if len(pkt) < 2:
            raise ArkFejl(
                f"Varmepumpe: '{navn}' har kun ét målepunkt (række "
                f"{pkt[0]['raekke']}). Der skal mindst to til — gerne en kold "
                "dag, omkring 0 °C og en varm dag.")
        if len(set(temps)) != len(temps):
            raise ArkFejl(f"Varmepumpe: '{navn}' har samme udetemperatur to "
                          f"gange ({sorted(temps)}).")
        pkt.sort(key=lambda p: p["t_ambient"])
        varme = [p["heat_mw"] for p in pkt]
        if any(b < a for a, b in zip(varme, varme[1:])):
            print(f"    Varmepumpe '{navn}': varmeproduktionen falder med "
                  "stigende udetemperatur. For luft/vand er det normalt "
                  "omvendt — tjek tallene.")
    return tabeller


def _vp_kurve(navn: str, punkter: list[dict]) -> tuple[dict, float, float]:
    """cop_curve-blok, største varme og COP ved 0 °C for én varmepumpe."""
    ren = [{k: round(p[k], 3) for k in ("t_ambient", "heat_mw", "el_mw")}
           for p in punkter]
    ts = [p["t_ambient"] for p in ren]
    q0 = float(np.interp(0.0, ts, [p["heat_mw"] for p in ren]))
    e0 = float(np.interp(0.0, ts, [p["el_mw"] for p in ren]))
    return ({"type": "table", "points": ren},
            max(p["heat_mw"] for p in ren), q0 / e0)


# -------------------------------------------------------------------- anlæg
def _hele_timer(v) -> int:
    """Min drifts-/stoptid i hele timer, mindst 1 (tom eller 0 → 1)."""
    return max(1, math.ceil(v)) if v else 1


def laes_enheder(sti: Path, priser: dict,
                 vp_tabeller: dict[str, list[dict]] | None = None,
                 gasafgift: dict | None = None) -> dict:
    hr = find_raekke(sti, "Anlaeg", "navn")
    if hr is None:
        raise ArkFejl("Arket Anlaeg: overskriften 'navn' i kolonne A er ikke til at "
                      "finde. Slet ikke overskriftsrækken over enhederne.")
    slut = find_raekke(sti, "Anlaeg", "lovlige værdier", praefiks=True, efter=hr)
    # Kolonne N 'brændsel' er valgfri (findes ikke i skabelon v4).
    hoved = pd.read_excel(sti, sheet_name="Anlaeg", header=None,
                          skiprows=hr - 1, nrows=1)
    har_braendsel = hoved.shape[1] > 13 and _norm(hoved.iat[0, 13]).startswith("brændsel")
    df = pd.read_excel(sti, sheet_name="Anlaeg", skiprows=hr - 1,
                       usecols=range(14 if har_braendsel else 13),
                       nrows=(slut - hr - 1) if slut else 19)
    df.columns = ["navn", "type", "p_max", "p_min", "eta", "cop", "eta_el",
                  "var_om", "start_cost", "min_up", "min_down", "balance",
                  "sol_gwh"] + (["braendsel"] if har_braendsel else [])
    if not har_braendsel:
        df["braendsel"] = None
    df = df.dropna(subset=["navn", "type"])
    if df.empty:
        raise ArkFejl("Arket Anlaeg har ingen enheder med både navn og type.")

    units: dict = {}
    for i, r in df.iterrows():
        raekke = int(i) + hr + 1
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
            "p_max_heat": tal(r["p_max"], f"række {raekke}, maks varme",
                              kraev=(type_ != "heat_pump")),
            "p_min_heat": tal(r["p_min"], f"række {raekke}, min varme") or 0.0,
            "var_om": tal(r["var_om"], f"række {raekke}, D&V") or 0.0,
            "start_cost": tal(r["start_cost"], f"række {raekke}, startomkostning") or 0.0,
            # Modellen regner i hele timer og kræver mindst 1. Brøkdele rundes OP
            # (0,15 t → 1 t, 2,5 t → 3 t); int() ville give 0 og en case, der
            # ikke kan indlæses.
            "min_uptime": _hele_timer(tal(r["min_up"], f"række {raekke}, min driftstid")),
            "min_downtime": _hele_timer(tal(r["min_down"], f"række {raekke}, min stoptid")),
        }
        punkter = vp_tabeller.pop(navn, None) if vp_tabeller is not None else None
        if type_ == "heat_pump" and punkter:
            kurve, q_maks, cop0 = _vp_kurve(navn, punkter)
            if u["p_max_heat"] is None:
                u["p_max_heat"] = q_maks
            elif u["p_max_heat"] < q_maks:
                # Hvor varmt skal det være, før maks varme klipper tabellen?
                # Varmen stiger med temperaturen, så første krydsning er grænsen.
                ts = [p["t_ambient"] for p in punkter]
                qs = [p["heat_mw"] for p in punkter]
                graense = None
                for (t0, q0), (t1, q1) in zip(zip(ts, qs), zip(ts[1:], qs[1:])):
                    if q0 <= u["p_max_heat"] < q1:
                        graense = t0 + (u["p_max_heat"] - q0) / (q1 - q0) * (t1 - t0)
                        break
                hvor = (f"over ca. {graense:.0f} °C" if graense is not None
                        else "ved alle temperaturer")
                print(f"\n    ADVARSEL række {raekke}: maks varme i Anlaeg er "
                      f"{u['p_max_heat']:g} MW, men målepunkterne i arket "
                      f"Varmepumpe når {q_maks:g} MW. Varmepumpen holdes på "
                      f"{u['p_max_heat']:g} MW {hvor}. Er det en reel "
                      "begrænsning (pumper, net), så lad det stå. Er det "
                      "typeskiltets tal, så slet det i Anlaeg.\n")
        elif type_ == "heat_pump" and u["p_max_heat"] is None:
            andre = ", ".join(f"'{n}'" for n in (vp_tabeller or {}))
            raise ArkFejl(
                f"Række {raekke}: varmepumpen '{r['navn']}' har hverken maks "
                "varme eller målepunkter i arket Varmepumpe."
                + (f" Arket Varmepumpe har punkter for {andre} — står navnet "
                   "ens i de to ark?" if andre else ""))
        if u["p_min_heat"] > u["p_max_heat"]:
            raise ArkFejl(f"Række {raekke}: min varme er større end maks varme.")

        if type_ not in TYPER_UDEN_BRAENDSEL:
            eta = tal(r["eta"], f"række {raekke}, virkningsgrad", kraev=True)
            if not 0 < eta <= 1.2:
                raise ArkFejl(f"Række {raekke}: virkningsgrad {eta} ser forkert ud. "
                              "Den skal være en brøkdel, fx 0,95 — ikke 95.")
            u["eta_fuel_to_heat"] = eta

        valg = _norm(r["braendsel"])
        if type_ == "biomass_boiler":
            # Før oktober 2026 fik ALLE biomassekedler halm, hvis halmprisen var
            # udfyldt. Et værk med flis- og pillekedler fik fliskedlen regnet
            # på pilleprisen, uden at lastfordelingen så forkert ud.
            med_pris = [k for k in ("straw", "wood_pellets", "flis") if priser.get(k)]
            if valg:
                if valg not in BIOMASSE:
                    raise ArkFejl(
                        f"Række {raekke}: brændslet '{r['braendsel']}' i kolonnen "
                        "'brændsel' er ikke kendt. Skriv halm, træpiller eller flis.")
                u["fuel"] = BIOMASSE[valg]
                if not priser.get(u["fuel"]):
                    raise ArkFejl(
                        f"Række {raekke}: '{r['navn']}' fyrer med {valg}, men "
                        f"prisen for {valg} er ikke udfyldt på arket Priser.")
            elif not med_pris:
                raise ArkFejl(
                    f"Række {raekke}: '{r['navn']}' er en biomassekedel, men "
                    "hverken halm-, træpille- eller flisprisen er udfyldt på "
                    "arket Priser.")
            elif len(med_pris) == 1:
                u["fuel"] = med_pris[0]
            elif "wood_pellets" in med_pris:
                raise ArkFejl(
                    f"Række {raekke}: '{r['navn']}' er en biomassekedel uden "
                    "brændsel, og arket Priser har pris for "
                    + " og ".join(BIOMASSE_DANSK[k] for k in med_pris)
                    + ". Skriv halm, træpiller eller flis i kolonnen 'brændsel' "
                    "(kolonne N) ud for kedlen.")
            elif priser["straw"]["value"] == priser["flis"]["value"]:
                # Samme pris: valget ændrer ikke resultatet (skabelonens
                # eksempel står sådan), så det nævnes uden at råbe.
                u["fuel"] = "straw"
                print(f"    Række {raekke}: '{r['navn']}' regnes på halm. Halm og "
                      "flis har samme pris, så valget ændrer ikke resultatet.")
            else:
                u["fuel"] = "straw"
                print(f"\n    ADVARSEL række {raekke}: '{r['navn']}' regnes på halm "
                      f"({priser['straw']['value']:g} kr/MWh). Både halm og flis "
                      f"har en pris på arket Priser (flis "
                      f"{priser['flis']['value']:g}), og kedlen har intet brændsel "
                      "i kolonne N. Er det en fliskedel, så skriv flis i kolonnen "
                      "'brændsel' — eller slet den pris, værket ikke bruger.\n")
        else:
            if valg and valg not in BRAENDSEL_ORD.get(type_, set()):
                raise ArkFejl(
                    f"Række {raekke}: '{r['navn']}' er en {type_}, men kolonnen "
                    f"'brændsel' siger '{r['braendsel']}'. Kolonnen bruges kun "
                    "for biomassekedler — lad cellen stå tom, eller ret typen.")
            u["fuel"] = BRAENDSEL_PR_TYPE[type_]

        # Gasafgifter og -tariffer, der kun gælder kedler eller kun motorer.
        # Modellen har ikke en afgift pr. enhed, så de lægges på D&V pr. MWh
        # varme: afgift pr. MWh gas delt med varmevirkningsgraden.
        saerlig = (gasafgift or {}).get(
            {"gas_boiler": "kedler", "gas_engine_chp": "motorer"}.get(type_), 0.0)
        if saerlig:
            tillaeg = round(saerlig / u["eta_fuel_to_heat"], 2)
            hvem = "gaskedler" if type_ == "gas_boiler" else "gasmotorer"
            u["notes"] = (
                f"var_om er D&V {u['var_om']:g} + {tillaeg:.2f} kr/MWh varme i "
                f"gasafgift og -tarif, som kun gælder {hvem} ({saerlig:.2f} kr/MWh "
                f"gas delt med varmevirkningsgraden {u['eta_fuel_to_heat']:g}).")
            u["var_om"] = round(u["var_om"] + tillaeg, 2)
            print(f"    Række {raekke}: '{r['navn']}' får {tillaeg:.2f} kr/MWh varme "
                  f"lagt på D&V for afgifter, der kun gælder {hvem}.")

        if type_ in ("gas_boiler", "gas_engine_chp") and "co2_eua" not in priser:
            raise ArkFejl(
                f"Række {raekke}: '{r['navn']}' bruger gas, men CO2-cellen på "
                "arket Priser er tom. Indeholder gasprisen allerede "
                "CO2-afgiften, så skriv 0; ellers skriv CO2-prisen i kr pr. ton.")

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

        if type_ == "heat_pump" and punkter:
            # Målt ydelse: varmeloftet og COP følger udetemperaturen.
            u["cop_curve"] = kurve
            u["alpha"] = round(-1.0 / cop0, 4)
            if tal(r["cop"], f"række {raekke}, COP") is not None:
                print(f"    Række {raekke}: COP ved 0 °C bruges ikke — "
                      "målepunkterne i arket Varmepumpe har forrang.")
            print(f"    Række {raekke}: '{r['navn']}' fra {len(punkter)} "
                  f"målepunkter, COP ved 0 °C {cop0:.2f}, maks varme "
                  f"{u['p_max_heat']:g} MW")

        elif type_ == "heat_pump":
            print(f"    Række {raekke}: '{r['navn']}' har ingen målepunkter i "
                  "arket Varmepumpe. Den regnes med COP ved 0 °C og et fast "
                  "varmeloft, som overvurderer eloptaget i kulde.")
            cop = tal(r["cop"], f"række {raekke}, COP", kraev=True)
            if not 1.5 <= cop <= 6.0:
                raise ArkFejl(
                    f"Række {raekke}: COP på {cop} ser forkert ud. Det skal være "
                    "COP ved 0 °C udetemperatur, typisk 2,5–3,5 for luft/vand. "
                    "En årsvirkningsgrad eller en COP ved 7 °C hører ikke til her.")
            u["cop_curve"] = {"type": "linear", "a": round(cop, 3), "b": 0.08,
                              "cop_min": 1.8, "cop_max": 4.0}
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
    hr = find_raekke(sti, "Anlaeg", "tank")
    if hr is None:
        raise ArkFejl("Arket Anlaeg: overskriften 'tank' i kolonne A er ikke til at "
                      "finde. Slet ikke overskriftsrækken over tankene — ryd "
                      "kun indholdet af de rækker, du ikke bruger.")
    df = pd.read_excel(sti, sheet_name="Anlaeg", skiprows=hr - 1, usecols=range(5), nrows=6)
    df.columns = ["navn", "volumen", "e_max", "lade", "aflade"]
    df = df.dropna(subset=["navn", "volumen"])
    if df.empty:
        raise ArkFejl("Arket Anlaeg har ingen akkumuleringstanke. "
                      "Uden lager er der ingen businesscase at regne på.")

    storage: dict = {}
    for i, r in df.iterrows():
        raekke = int(i) + hr + 1
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


# ----------------------------------------------------------------- solvarme
def _solen_er_nede(idx: "pd.DatetimeIndex") -> "np.ndarray":
    """True for timer (UTC, timestart), hvor solen står mere end 6 grader under
    horisonten midt i timen. Regnet for 56° N, 10,5° Ø — hele Danmark ligger
    inden for en halv time af det, og grænsen på 6 grader giver luft."""
    doy = idx.dayofyear.to_numpy().astype(float)
    soltid = idx.hour.to_numpy() + 0.5 + 10.5 / 15.0
    decl = np.deg2rad(23.45 * np.sin(np.deg2rad(360.0 / 365.0 * (doy - 81))))
    lat = math.radians(56.0)
    sin_h = (np.sin(lat) * np.sin(decl)
             + np.cos(lat) * np.cos(decl) * np.cos(np.deg2rad(15.0 * (soltid - 12.0))))
    return sin_h < math.sin(math.radians(-6.0))


def laes_solvarme(sti: Path, timeslut: bool = False):
    """Målte timeværdier for solvarmen fra arket 'Solvarme', hvis det findes.

    Arket er opbygget som Timedata: tidszone i B2, årsproduktion i B3 (valgfri),
    overskriften 'tidsstempel' i kolonne A og data under den. Returnerer
    (serie i UTC med timestart, årstal fra B3) eller (None, None), når arket
    ikke findes eller er tomt — så bruges den syntetiske profil som hidtil."""
    try:
        top = pd.read_excel(sti, sheet_name="Solvarme", header=None, nrows=4)
    except ValueError:
        return None, None
    hr = find_raekke(sti, "Solvarme", "tidsstempel")
    if hr is None:
        raise ArkFejl("Arket Solvarme: overskriften 'tidsstempel' i kolonne A er "
                      "ikke til at finde. Arket skal være opbygget som Timedata.")
    df = pd.read_excel(sti, sheet_name="Solvarme", header=None, skiprows=hr,
                       usecols=[0, 1])
    df.columns = ["timestamp", "mw"]
    df["raekke"] = df.index + hr + 1
    df = df.dropna(subset=["timestamp", "mw"], how="all")
    if df["mw"].dropna().empty:
        print("    Arket Solvarme er tomt. Solvarmen får den syntetiske profil.")
        return None, None
    tz = laes_tidszone(sti, "Solvarme")
    try:
        b3 = tal(top.iat[2, 1], "Solvarme: årsproduktion (celle B3)")
    except IndexError:
        b3 = None

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=False)
    if df["timestamp"].isna().any():
        foerste = int(df.loc[df["timestamp"].isna(), "raekke"].iloc[0])
        raise ArkFejl(f"Arket Solvarme har tidsstempler, der ikke kan læses som "
                      f"en dato — første gang i række {foerste}.")
    df = df.dropna(subset=["mw"])
    maalt = pd.to_numeric(df["mw"], errors="coerce")
    if maalt.isna().any():
        eks = "; ".join(f"række {int(r.raekke)}: {r.mw!r}"
                        for r in df[maalt.isna()].head(5).itertuples())
        raise ArkFejl(f"{int(maalt.isna().sum())} værdier i kolonne B i Solvarme er "
                      f"tekst og ikke tal — {eks}. Lad cellen stå tom, eller skriv "
                      "tallet.")
    df["mw"] = maalt
    if (df["mw"] < 0).any():
        r = df[df["mw"] < 0].iloc[0]
        raise ArkFejl(f"{int((df['mw'] < 0).sum())} værdier i Solvarme er negative, "
                      f"første gang i række {int(r.raekke)}. Varme sendt ud i "
                      "solfeltet (frostsikring) er ikke produktion — sæt de timer "
                      "til 0, eller lad dem stå tomme.")
    df = df.sort_values("timestamp").reset_index(drop=True)
    if tz == "UTC":
        if df["timestamp"].duplicated().any():
            r = df[df["timestamp"].duplicated()].iloc[0]
            raise ArkFejl(f"Tidsstempler går igen i Solvarme, første gang "
                          f"{r.timestamp} (række {int(r.raekke)}).")
        if getattr(df["timestamp"].dt, "tz", None) is not None:
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
    else:
        try:
            ts = df["timestamp"].dt.tz_localize(
                "Europe/Copenhagen", nonexistent="shift_forward", ambiguous="infer")
        except Exception:
            ts = df["timestamp"].dt.tz_localize(
                "Europe/Copenhagen", nonexistent="shift_forward", ambiguous=True)
        df["timestamp"] = ts.dt.tz_convert("UTC").dt.tz_localize(None)
        print("    Solvarme: tidsstempler konverteret fra dansk lokaltid til UTC.")
    if timeslut:
        df["timestamp"] = df["timestamp"] - timedelta(hours=1)
    return df.set_index("timestamp")["mw"], b3


def skriv_maalt_solprofil(sti: Path, serie: "pd.Series", start: str, slut: str,
                          navn: str, p_max: float, anlaeg_gwh: float,
                          b3_gwh: float | None) -> str:
    """Skriv den målte solserie som profil for hele kørselsvinduet.

    Vinduet rundes ud til hele døgn, så et kald med --end på periodens sidste
    dag ikke stopper på to manglende nattetimer. Huller inde i serien udfyldes
    lineært (højst 5 %); manglende timer i enderne sættes kun til 0, hvis
    solen er nede i dem alle. Returnerer teksten til enhedens notes."""
    t0 = pd.Timestamp(start[:10] + " 00:00")
    t1 = pd.Timestamp(slut[:10] + " 23:00")
    idx = pd.date_range(t0, t1, freq="h")
    uden_for = int((~serie.index.isin(idx)).sum())
    if uden_for:
        print(f"    Solvarme: {uden_for} timer ligger uden for kørselsvinduet "
              f"{t0:%d/%m/%Y}–{t1:%d/%m/%Y} og bruges ikke.")
    s = serie[serie.index.isin(idx)].reindex(idx)
    if s.notna().sum() == 0:
        raise ArkFejl("Arket Solvarme har ingen værdier inden for den periode, "
                      "Timedata dækker.")
    foerste, sidste = s.first_valid_index(), s.last_valid_index()
    ender = (idx < foerste) | (idx > sidste)
    nede = _solen_er_nede(idx)
    if ender.any():
        n_start, n_slut = int((idx < foerste).sum()), int((idx > sidste).sum())
        if not nede[ender].all():
            raise ArkFejl(
                f"Arket Solvarme dækker ikke perioden: der mangler {n_start} timer "
                f"i starten og {n_slut} i slutningen (serien går fra "
                f"{foerste:%d/%m/%Y %H:%M} til {sidste:%d/%m/%Y %H:%M} UTC), og "
                "nogle af dem er dagtimer. Solprofilen nulfyldes ikke.")
        s[ender] = 0.0
        dele = ([f"{n_start} timer først" ] if n_start else []) + \
               ([f"{n_slut} timer sidst"] if n_slut else [])
        print(f"    Solvarme: {' og '.join(dele)} i perioden står tomme. Det er "
              "nattetimer, og de er sat til 0.")
    huller = int(s.isna().sum())
    if huller:
        if huller > 0.05 * len(idx):
            raise ArkFejl(f"Arket Solvarme mangler {huller} timer inde i serien "
                          f"({huller / len(idx):.1%}). Over 5 % udfyldes ikke.")
        s = s.interpolate(limit_area="inside")
        print(f"    Solvarme: {huller} tomme timer inde i serien er udfyldt ved "
              "lineær interpolation.")

    gwh, spids = float(s.sum() / 1000.0), float(s.max())
    linje = (f"  Solvarmeprofil (målt, arket Solvarme): {len(s)} timer, "
             f"{gwh:.2f} GWh, spids {spids:.1f} MW. Anlaeg siger {anlaeg_gwh:g} GWh "
             f"({(gwh - anlaeg_gwh) / anlaeg_gwh:+.0%})")
    if b3_gwh:
        linje += f", Solvarme!B3 siger {b3_gwh:g} GWh"
    print(linje + ". Modellen bruger timeserien.")
    if spids > p_max + 1e-9:
        print(f"    ADVARSEL: solserien når {spids:.1f} MW, men maks varme i Anlaeg "
              f"er {p_max:g} MW. Modellen klipper profilen ved {p_max:g} MW.")

    # Sol om natten er frostsikring eller en måler, der tæller begge veje.
    nat = s[nede]
    if nat.sum() > 0.002 * s.sum() or nat.max() > 0.05 * spids:
        top3 = "; ".join(f"{ts:%Y-%m-%d %H:%M} ({v:.1f} MW)"
                         for ts, v in nat.nlargest(3).items())
        print(f"\n    ADVARSEL: solserien har produktion om natten — "
              f"{int((nat > 0.01 * spids).sum())} timer med i alt {nat.sum():.0f} MWh, "
              f"mens solen er nede (UTC). Størst: {top3}. Er det frostsikring "
              "(varme sendt UD i solfeltet) eller en måler, der tæller begge veje, "
              "er det ikke produktion. Modellen regner timerne som gratis varme, "
              "som de står i arket.\n")

    sti.parent.mkdir(parents=True, exist_ok=True)
    ud = pd.DataFrame({"time": idx.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "power_mw": s.to_numpy()})
    ud.to_csv(sti, index=False, float_format="%.6f")
    print(f"    → {sti}")
    return ("p_max_heat er værkets tal for største soleffekt. Profilen er "
            f"værkets egne timeværdier fra arket Solvarme ({gwh:.2f} GWh, spids "
            f"{spids:.1f} MW) — ikke syntese.")


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

    # Formelceller: pandas læser den cachede værdi, og en fil, der er gemt uden
    # om Excel (fx af et script), har ingen. Så læses formlen selv. En ren
    # talformel som =65*3,6 regnes ud; alt med cellehenvisninger afvises.
    import openpyxl
    formler = {}
    try:
        wsf = openpyxl.load_workbook(sti, data_only=False)["Priser"]
        for raekke in wsf.iter_rows():
            for c in raekke:
                if isinstance(c.value, str) and c.value.startswith("="):
                    formler[(c.row - 1, c.column - 1)] = (c.coordinate, c.value)
    except Exception:
        pass

    def celle(r, c):
        try:
            v = raa.iat[r, c]
        except IndexError:
            v = None
        f = formler.get((r, c))
        if f and (v is None or (isinstance(v, float) and pd.isna(v))
                  or (isinstance(v, str) and v.startswith("="))):
            regnet = _regn_formel(f[1])
            if regnet is None:
                raise ArkFejl(
                    f"Priser {f[0]} indeholder en formel ({f[1]}), som ikke kan "
                    "læses, uden at arket er regnet igennem i Excel. Skriv tallet "
                    "i cellen i stedet for formlen.")
            return regnet
        return v

    # Posterne findes på etiketten i kolonne A. Før oktober 2026 blev de læst
    # på faste rækkenumre: en omdøbt række (halm -> træpiller) blev læst som
    # halm, og seks indsatte rækker gav "DMI-område '4.74' er ikke kendt".
    etiketter = [_norm(v) for v in raa.iloc[:, 0]]

    def find(tekst, *, praefiks=False, kraev=True, efter=-1, hvad=None):
        for i, e in enumerate(etiketter):
            if i > efter and (e.startswith(tekst) if praefiks else e == tekst):
                return i
        if kraev:
            raise ArkFejl(
                f"Priser: rækken '{hvad or tekst}' er ikke til at finde i kolonne A. "
                "Rækker må flyttes, men posterne må ikke slettes eller omdøbes — "
                "lad værdien stå tom, hvis posten ikke bruges.")
        return None

    def blok(hoved_raekke):
        """Rækkerne under en overskriftsrække, til første tomme celle i A."""
        i = hoved_raekke + 1
        while i < len(etiketter) and etiketter[i]:
            yield i
            i += 1

    navne = {"naturgas": "natural_gas", "halm": "straw", "træpiller": "wood_pellets",
             "flis": "flis", "overskudsvarme": "waste_heat"}
    # CO2 opgives pr. ton CO2. Modellen ganger selv med enhedens
    # co2_emissions_per_mwh_fuel (0,2 t CO2 pr. MWh naturgas), så et tal pr.
    # MWh gas her ville blive ganget med 0,2 én gang for meget.
    enheder = {"co2_eua": "DKK/t_CO2"}
    priser = {}
    for i in blok(find("brændsel", hvad="brændsel (overskriften over brændselspriserne)")):
        noegle = "co2_eua" if etiketter[i].startswith("co2") else navne.get(etiketter[i])
        if noegle is None:
            raise ArkFejl(
                f"Priser række {i + 1}: '{raa.iat[i, 0]}' står blandt "
                "brændselspriserne, men er ikke et brændsel, konverteringen "
                "kender (naturgas, halm, træpiller, flis, overskudsvarme, CO2). "
                "Gasafgifter og -tariffer hører til i blokken 'Gasafgifter og "
                "gastariffer'. Er det et andet brændsel, så skriv til os.")
        if noegle in priser:
            raise ArkFejl(f"Priser række {i + 1}: '{raa.iat[i, 0]}' står to gange.")
        v = tal(celle(i, 1), f"Priser: {raa.iat[i, 0]}")
        if v is not None:
            priser[noegle] = {"value": v,
                              "unit": enheder.get(noegle, "DKK/MWh_fuel")}

    # ------------------------------------------------ gasafgifter og -tariffer
    # Valgfri blok. Værker opgør gassens afgifter pr. m3, og nogle af dem
    # gælder kun motorer (metanafgift) eller kun kedler. 'alle' lægges på
    # gasprisen; 'kedler' og 'motorer' føres videre til laes_enheder.
    gasafgift = {"alle": 0.0, "kedler": 0.0, "motorer": 0.0}
    ga = find("gasafgifter", praefiks=True, kraev=False)
    if ga is not None:
        gh = find("post", efter=ga, kraev=False)
        if gh is None or not _norm(celle(gh, 3)).startswith("gælder"):
            raise ArkFejl(
                "Priser: blokken 'Gasafgifter og gastariffer' mangler sin "
                "overskriftsrække: post, sats, enhed, gælder for.")
        hvem_ord = {"alle": "alle", "alle gasenheder": "alle",
                    "kedler": "kedler", "gaskedler": "kedler",
                    "motorer": "motorer", "gasmotorer": "motorer"}
        kwh_m3, poster = None, []
        for i in blok(gh):
            post = str(raa.iat[i, 0]).strip()
            sats = tal(celle(i, 1), f"Priser række {i + 1}: {post}")
            if sats is None:
                continue
            enhed = _norm(celle(i, 2)).replace("³", "3").replace(" ", "")
            if etiketter[i].startswith("brændværdi"):
                if enhed not in ("kwh/m3", "kwh/nm3"):
                    raise ArkFejl(f"Priser række {i + 1}: brændværdien skal stå i "
                                  f"kWh/m3, ikke '{celle(i, 2)}'.")
                if not 9.0 <= sats <= 13.0:
                    raise ArkFejl(
                        f"Priser række {i + 1}: brændværdien {sats:g} kWh/m3 ser "
                        "forkert ud. Naturgas ligger omkring 11,0 (nedre) til "
                        "12,2 (øvre) kWh/m3.")
                kwh_m3 = sats
                continue
            hvem = hvem_ord.get(_norm(celle(i, 3)))
            if hvem is None:
                raise ArkFejl(
                    f"Priser række {i + 1}: 'gælder for' for posten '{post}' er "
                    f"'{celle(i, 3)}'. Skriv alle, kedler eller motorer.")
            if enhed not in ("kr/m3", "kr/nm3", "kr/mwh"):
                raise ArkFejl(
                    f"Priser række {i + 1}: enheden for '{post}' er "
                    f"'{celle(i, 2)}'. Skriv kr/m3 eller kr/MWh.")
            poster.append((i, post, sats, enhed, hvem))
        for i, post, sats, enhed, hvem in poster:
            if enhed != "kr/mwh":
                if kwh_m3 is None:
                    raise ArkFejl(
                        f"Priser række {i + 1}: '{post}' står i kr/m3, men "
                        "blokken har ingen række 'brændværdi naturgas' i kWh/m3. "
                        "Uden den kan satsen ikke regnes om til kr/MWh gas.")
                sats = sats / kwh_m3 * 1000.0
            gasafgift[hvem] += sats
        if poster:
            if "natural_gas" not in priser:
                raise ArkFejl("Priser: der er gasafgifter, men naturgasprisen er "
                              "ikke udfyldt.")
            print(f"  Gasafgifter og -tariffer ({len(poster)} poster"
                  + (f", {kwh_m3:g} kWh/m3" if kwh_m3 else "") + "): "
                  f"alle gasenheder {gasafgift['alle']:.2f}, kun kedler "
                  f"{gasafgift['kedler']:.2f}, kun motorer "
                  f"{gasafgift['motorer']:.2f} kr/MWh gas.")
            if gasafgift["alle"]:
                uden = priser["natural_gas"]["value"]
                priser["natural_gas"]["value"] = round(uden + gasafgift["alle"], 2)
                priser["natural_gas"]["note"] = (
                    f"{uden:g} kr/MWh ekskl. afgifter + {gasafgift['alle']:.2f} "
                    "kr/MWh i afgifter og tariffer, der gælder alle gasenheder.")
                print(f"    Gasprisen i modellen: {uden:g} + "
                      f"{gasafgift['alle']:.2f} = "
                      f"{priser['natural_gas']['value']:.2f} kr/MWh.")

    # De faste elled søges under deres egen overskrift, så en gaspost som
    # 'Energinet transmissionstarif' i blokken ovenfor ikke bliver til eltarif.
    el_fra = find("elafgift og", praefiks=True, kraev=False)
    el_fra = -1 if el_fra is None else el_fra
    afgift = tal(celle(find("elafgift efter", praefiks=True, efter=el_fra,
                            hvad="elafgift efter elvarmegodtgørelse"), 1),
                 "Priser: elafgift", kraev=True)
    energinet = tal(celle(find("energinet", praefiks=True, efter=el_fra,
                               hvad="Energinet (transmission+system+balance)"), 1),
                    "Priser: Energinet-tarif", kraev=True)
    dv = tal(celle(find("netselskabets", praefiks=True, efter=el_fra,
                        hvad="netselskabets drift og vedligehold"), 1),
             "Priser: drift og vedligehold") or 0.0
    prod = tal(celle(find("indfødningstarif", praefiks=True, efter=el_fra,
                          hvad="indfødningstarif"), 1),
               "Priser: produktionstarif") or 0.0

    # Ét sæt tidsperioder (N1's inddeling, se byg_skabelon.py), men satserne
    # må være forskellige vinter og sommer. Sommerens bånd får da egne navne
    # (lav_sommer, hoej_sommer), så tarifmodulet slår den rigtige sats op.
    # Før september 2026 gemte konverteringen kun én sats pr. båndnavn og
    # brugte vintertallet hele året — arket spurgte om sommersatsen og
    # smed svaret væk.
    baand_raekker = {"lav": find("lavlast"), "hoej": find("højlast"),
                     "spids": find("spidslast", kraev=False)}
    vinter_v, sommer_v = {}, {}
    for b, rk in baand_raekker.items():
        if rk is None:
            continue
        vi = tal(celle(rk, 1), f"Priser: {b}, vinter")
        so = tal(celle(rk, 2), f"Priser: {b}, sommer")
        if vi is not None:
            vinter_v[b] = vi
        if so is not None:
            sommer_v[b] = so
    for b in ("lav", "hoej"):
        if b not in vinter_v and b not in sommer_v:
            raise ArkFejl("Priser: lavlast og højlast skal begge udfyldes i "
                          "tarifskemaet — mindst én af kolonnerne vinter og sommer.")
        # Mangler én sæson, gælder den anden hele året — og det siges.
        if b not in vinter_v:
            vinter_v[b] = sommer_v[b]
            print(f"    Priser: {b} har kun sommersats; den bruges også om vinteren.")
        if b not in sommer_v:
            sommer_v[b] = vinter_v[b]
    if "spids" in sommer_v:
        print("    Priser: spidslast har en sommersats, men spidslast findes kun "
              "på vinterhverdage i modellens tidsperioder. Sommersatsen bruges ikke.")
    if "spids" not in vinter_v and "spids" in sommer_v:
        print("    Priser: spidslast har kun en sommersats. Vinterhverdage kl. "
              "06–21 regnes derfor som højlast.")

    bands = {b: v for b, v in vinter_v.items()}
    sommer_navn = {}
    for b in ("lav", "hoej"):
        if sommer_v[b] == vinter_v[b]:
            sommer_navn[b] = b
        else:
            sommer_navn[b] = f"{b}_sommer"
            bands[sommer_navn[b]] = sommer_v[b]
    forskellige = [b for b in ("lav", "hoej") if sommer_navn[b] != b]
    if forskellige:
        print(f"    Priser: egne sommersatser for {', '.join(forskellige)} "
              "(april–september).")

    vinter_spids = "spids" if "spids" in vinter_v else "hoej"
    s_lav, s_hoej = sommer_navn["lav"], sommer_navn["hoej"]
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
                    "weekday": {"00-06": s_lav, "06-24": s_hoej},
                    "weekend": {"00-06": s_lav, "06-24": s_lav},
                },
            },
        },
    }

    def tekst(v):
        return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()

    omraade = tekst(celle(find("nærmeste dmi", praefiks=True,
                               hvad="nærmeste DMI-område"), 1)).lower()
    if omraade not in KENDTE_DMI_OMRAADER:
        raise ArkFejl(f"Priser: DMI-område '{omraade}' er ikke kendt. "
                      f"Vælg {', '.join(KENDTE_DMI_OMRAADER[:-1])} eller "
                      f"{KENDTE_DMI_OMRAADER[-1]}.")
    zone = tekst(celle(find("priszone"), 1)).upper()
    if zone not in ("DK1", "DK2"):
        raise ArkFejl(f"Priser: priszone '{zone}' er ikke kendt. Vælg DK1 eller DK2.")
    vaerk = tekst(celle(find("værkets navn"), 1))

    el = {"spot_area": zone, "tariff_consumption_flat": round(
        energinet + dv + bands.get("hoej", 0.0), 1),
        "tariff_consumption": tarif,
        "tariff_production_flat": prod,
        "electricity_tax": afgift}
    data = {"dmi_area": omraade, "price_zone": zone}
    return priser, el, {"data": data, "vaerk": vaerk, "gasafgift": gasafgift}


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

    if any(str(u.get("production_profile_path", "")).endswith("_maalt.csv")
           for u in d["units"].values()):
        punkt5 = ("#   5. solvarmeprofilen er værkets egne timeværdier fra arket Solvarme,\n"
                  "#      ikke syntese. Står der produktion om natten i serien, regner\n"
                  "#      modellen den som gratis varme — se konverteringens advarsel.")
    else:
        punkt5 = ("#   5. solvarmeprofilen er syntetisk: plausibel fysik skaleret til den\n"
                  "#      årsproduktion, du opgav. Har I egne soltimeværdier, så læg dem i\n"
                  "#      et ark 'Solvarme' (opbygget som Timedata), eller erstat filen —\n"
                  "#      kolonnerne er time (UTC, ISO 8601) og power_mw.")
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
{punkt5}
# ==============================================================================
"""
    with sti.open("w", encoding="utf-8") as f:
        f.write(hoved)
        yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False,
                       default_flow_style=False, width=88)


# --------------------------------------------------------- vagt mod læk (K9)
def _git_top(sti: Path) -> Path | None:
    """Rod for den git-arbejdskopi, stien ligger i — eller None."""
    forfader = sti.resolve()
    while not forfader.exists():
        forfader = forfader.parent
    if forfader.is_file():
        forfader = forfader.parent
    try:
        r = subprocess.run(["git", "-C", str(forfader), "rev-parse",
                            "--show-toplevel"], capture_output=True, text=True)
    except FileNotFoundError:                       # git ikke installeret
        return None
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def kan_komme_med_i_git(sti: Path) -> bool:
    """True, hvis stien ligger i en git-arbejdskopi og IKKE er ignoreret.

    Uden for et repo kan intet ryge med i et commit. Inde i et repo afgør
    git check-ignore det: 0 = ignoreret, 1 = ikke ignoreret. Alt andet (fx en
    ødelagt .gitignore) behandles som risiko — vagten fejler i den sikre
    retning.
    """
    top = _git_top(sti)
    if top is None:
        return False
    r = subprocess.run(["git", "-C", str(top), "check-ignore", "-q",
                        str(sti.resolve())], capture_output=True)
    return r.returncode != 0


def tjek_ingen_laek(stier: list[tuple[str, Path]]) -> None:
    aabne = [(hvad, s) for hvad, s in stier if kan_komme_med_i_git(s)]
    if not aabne:
        return
    linjer = "\n".join(f"    {hvad}: {s}" for hvad, s in aabne)
    raise ArkFejl(
        "Deltagerdata må ikke ligge et sted, hvor git kan få dem med i et "
        "commit til det offentlige repo:\n" + linjer + "\n"
        "  Læg arket i deltagere/ og brug standardmapperne (udelad --cases-dir "
        "og --data-dir). Er det en egen referencecase og ikke en deltagers "
        "data, så brug --tillad-offentlig.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ark", type=Path, help="Den udfyldte vaerksdata_skabelon.xlsx")
    p.add_argument("--cases-dir", type=Path, default=Path("deltagere/cases"))
    p.add_argument("--data-dir", type=Path, default=Path("deltagere/data"))
    p.add_argument("--tillad-offentlig", action="store_true",
                   help="Slå vagten mod deltagerdata i git fra. Kun til egne "
                        "referencecases, aldrig til en deltagers data.")
    p.add_argument("--timeslut", action="store_true",
                   help="Tidsstemplerne i Timedata er timens SLUT (01:00 = kl. "
                        "00-01). De flyttes én time tilbage. Uden flaget læses de "
                        "som timens start.")
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
        # Før noget som helst skrives: kan arket eller output ryge med i git?
        if not a.tillad_offentlig:
            tjek_ingen_laek([
                ("arket", a.ark),
                ("casefil", a.cases_dir / f"{s}.yaml"),
                ("timedata", a.data_dir / f"{s}_abvaerk_hourly.csv"),
                ("profiler", a.data_dir / f"{s}_solvarme_profil.csv"),
                ("profiler", a.data_dir / f"{s}_solvarme_maalt.csv"),
            ])
        tz = laes_tidszone(a.ark)
        aars_gwh = laes_aarsproduktion(a.ark)
        csv_sti, start, slut, aarsvolumen, timedf = laes_timedata(
            a.ark, s, a.data_dir, a.overskriv, tz, aars_gwh,
            timeslut=a.timeslut)
        tjek_formler_uden_vaerdi(a.ark, "Anlaeg")
        vp_tabeller = laes_varmepumper(a.ark)
        units = laes_enheder(a.ark, priser, vp_tabeller, meta["gasafgift"])
        solserie, sol_b3 = laes_solvarme(a.ark, timeslut=a.timeslut)
        sol_enheder = [n for n, u in units.items() if "_sol_gwh" in u]
        if solserie is not None and len(sol_enheder) != 1:
            raise ArkFejl(
                "Arket Solvarme har timeværdier, men Anlaeg har "
                + ("ingen solvarmeenhed (type solar_thermal)." if not sol_enheder
                   else f"{len(sol_enheder)} solvarmeenheder. Arket kan kun "
                        "bruges, når der er præcis én — læg dem sammen i Anlaeg."))
        # Ingen gasenhed (laes_enheder har ellers stoppet): CO2 spiller ingen
        # rolle, men casen skal have feltet for at kunne indlæses.
        priser.setdefault("co2_eua", {"value": 0.0, "unit": "DKK/t_CO2"})
        if vp_tabeller:
            raise ArkFejl(
                "Arket Varmepumpe har målepunkter for "
                + ", ".join(f"'{n}'" for n in vp_tabeller)
                + ", men der er ingen varmepumpe med det navn i Anlaeg. "
                "Navnet skal stå ens i de to ark, og typen skal være heat_pump.")
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
    yaml_sti = a.cases_dir / f"{s}.yaml"
    if yaml_sti.exists() and not a.overskriv:
        print(f"\nFEJL: {yaml_sti} findes allerede. Brug --overskriv.", file=sys.stderr)
        return 1
    for navn, u in units.items():
        if "_sol_gwh" in u and solserie is not None:
            profil = a.data_dir / f"{s}_{navn}_maalt.csv"
            if profil.exists() and not a.overskriv:
                print(f"\nFEJL: {profil} findes allerede. Brug --overskriv.",
                      file=sys.stderr)
                return 1
            try:
                u["notes"] = skriv_maalt_solprofil(
                    profil, solserie, start, slut, navn, u["p_max_heat"],
                    u.pop("_sol_gwh"), sol_b3)
            except ArkFejl as e:
                print(f"\nArket kan ikke bruges endnu:\n  {e}\n", file=sys.stderr)
                return 1
            u["production_profile_path"] = profil.as_posix()
        elif "_sol_gwh" in u:
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

    if csv_sti is not None:
        csv_sti.parent.mkdir(parents=True, exist_ok=True)
        timedf.to_csv(csv_sti, index=False, date_format="%Y-%m-%d %H:%M:%S")
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
