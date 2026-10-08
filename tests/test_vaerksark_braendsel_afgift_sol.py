"""Midtfyns Fjernvarme (5.-7. oktober 2026): et ark med flis- og pillekedler,
gasafgifter i kr/m³ og egne soltimeværdier kunne ikke udtrykkes i arket, og
konverteringen enten tav eller pegede det forkerte sted hen.

  1. Priser blev læst på faste rækkenumre. Deltageren omdøbte `halm` til
     `træpiller`, og pilleprisen blev til halmpris uden et ord. Da deltageren
     siden indsatte seks afgiftsrækker, stoppede konverteringen med
     "DMI-område '4.74' er ikke kendt" — et tarifbånd læst som område.
  2. Alle biomassekedler fik samme brændsel. Var halmprisen udfyldt, blev også
     fliskedlen regnet på den (ca. 25 % for høj årsomkostning på arket).
  3. Gasafgifter pr. m³, hvoraf én kun gælder gasmotorer, havde ingen plads.
  4. Arket Solvarme med målte timeværdier blev ikke læst; modellen fik den
     syntetiske profil med halv spidseffekt.
  5. En formel i Anlaeg uden beregnet værdi (fil gemt uden om Excel) blev til
     startomkostning 0 uden besked.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from src.config import Prices, load_case
from tests.test_cop_tabel import _byg_og_fyld, _konverter


def _kør(tmp_path, rediger=None):
    return _konverter(tmp_path, _byg_og_fyld(tmp_path, rediger))


def _ud(r):
    return r.stdout + r.stderr


# --------------------------------------------------------------- hjælpere
def _traepiller_raekke(wb, pris=408.0):
    """Indsæt en række 'træpiller' under 'halm' i brændselsblokken."""
    ws = wb["Priser"]
    ws.insert_rows(8)
    ws["A8"], ws["B8"], ws["C8"] = "træpiller", pris, "kr/MWh"


def _to_biomassekedler(wb, flis="flis", piller="træpiller"):
    """Skabelonens halmkedel bliver til en fliskedel og en pillekedel, og
    kolonne N siger, hvad hver af dem fyrer med."""
    ws = wb["Anlaeg"]
    ws["N4"] = "brændsel"
    ws["A7"], ws["N7"] = "fliskedel", flis
    for kol, v in zip("ABCDEFGHIJKLMN",
                      ["pillekedel", "biomass_boiler", 4.5, 3.0, 0.90, None,
                       None, 15.0, 4000, 24, 2, "nej", None, piller]):
        ws[f"{kol}12"] = v


def _gasafgifter(wb, raekker, braendvaerdi=11.0, start=34):
    """Blokken 'Gasafgifter og gastariffer' nederst på arket Priser."""
    ws = wb["Priser"]
    ws[f"A{start}"] = "Gasafgifter og gastariffer"
    for kol, v in zip("ABCD", ["post", "sats", "enhed", "gælder for"]):
        ws[f"{kol}{start + 1}"] = v
    r = start + 2
    if braendvaerdi is not None:
        ws[f"A{r}"], ws[f"B{r}"], ws[f"C{r}"] = "brændværdi naturgas", braendvaerdi, "kWh/m3"
        r += 1
    for post, sats, enhed, hvem in raekker:
        for kol, v in zip("ABCD", [post, sats, enhed, hvem]):
            ws[f"{kol}{r}"] = v
        r += 1


def _solark(wb, tomme_til_sidst=2, natspids=None, gwh_b3=None):
    """Arket Solvarme: samme opbygning som Timedata, UTC, timestart."""
    ws = wb.create_sheet("Solvarme")
    ws["A1"] = "Solvarme — ét års timeværdier"
    ws["A2"], ws["B2"] = "tidszone:", "UTC"
    ws["A3"], ws["B3"] = "årsproduktion solvarme:", gwh_b3
    ws["A5"], ws["B5"] = "tidsstempel", "solvarme_mw"
    t = pd.date_range("2025-07-01", "2026-06-30 23:00", freq="h")
    # Simpel dagbue: sol mellem kl. 6 og 16 UTC, højest om sommeren.
    dag = np.clip(np.sin((t.hour - 6) / 10 * np.pi), 0, None) * (t.hour >= 6) * (t.hour <= 16)
    saeson = 0.25 + 0.75 * (1 + np.cos((t.dayofyear - 172) / 365 * 2 * np.pi)) / 2
    v = np.round(np.asarray(18.0 * dag * saeson, dtype=float), 3)
    for i, (a, b) in enumerate(zip(t, v)):
        ws.cell(row=6 + i, column=1, value=a.to_pydatetime())
        ws.cell(row=6 + i, column=2, value=float(b))
    for i in range(len(t) - tomme_til_sidst, len(t)):
        ws.cell(row=6 + i, column=2).value = None
    if natspids:
        for ts, mw in natspids:
            ws.cell(row=6 + int(t.get_loc(pd.Timestamp(ts))), column=2, value=mw)
    return float(v[: len(t) - tomme_til_sidst].sum() / 1000.0)


# ------------------------------------------------- 1. Priser læses på etiket
def test_indsatte_raekker_over_tarifblokken_flytter_ikke_tallene(tmp_path):
    """To tomme rækker over 'Elafgift og faste tarifled' må ikke ændre noget."""
    _, ref = _kør(tmp_path / "ref")
    r, case = _kør(tmp_path / "ny", lambda wb: wb["Priser"].insert_rows(12, 2))
    assert r.returncode == 0, _ud(r)
    a, b = (yaml.safe_load(c.read_text()) for c in (ref, case))
    for noegle in ("prices", "electricity", "data"):
        assert a[noegle] == b[noegle], noegle


def test_ukendt_raekke_i_braendselsblokken_naevnes_med_raekke_og_tekst(tmp_path):
    def afgift_blandt_braendsler(wb):
        ws = wb["Priser"]
        ws.insert_rows(10)
        ws["A10"], ws["B10"], ws["C10"] = "Volumentarif", 0.134, "kr/m3"
    r, case = _kør(tmp_path, afgift_blandt_braendsler)
    assert r.returncode != 0 and case is None
    ud = _ud(r)
    assert "Volumentarif" in ud and "række 10" in ud
    assert "DMI" not in ud and "Traceback" not in r.stderr


def test_manglende_etiket_giver_besked_om_raekken(tmp_path):
    def uden_priszone(wb):
        wb["Priser"]["A29"] = None
    r, case = _kør(tmp_path, uden_priszone)
    assert r.returncode != 0
    assert "priszone" in _ud(r) and "Traceback" not in r.stderr


# --------------------------------------------- 2. træpiller og brændsel pr. kedel
def test_prices_kender_traepiller():
    p = Prices(co2_eua=0.0, wood_pellets=408.0)
    assert p.fuel_price("wood_pellets") == 408.0
    with pytest.raises(ValueError, match="træpiller"):
        Prices(co2_eua=0.0).fuel_price("wood_pellets")


def test_flis_og_pillekedel_faar_hver_sit_braendsel(tmp_path):
    def rediger(wb):
        _traepiller_raekke(wb, 408.0)
        wb["Priser"]["B7"] = None          # ingen halm
        wb["Priser"]["B9"] = 247.0         # flis (rykket én række ned)
        _to_biomassekedler(wb)
    r, case = _kør(tmp_path, rediger)
    assert r.returncode == 0, _ud(r)
    raa = yaml.safe_load(case.read_text())
    assert raa["units"]["fliskedel"]["fuel"] == "flis"
    assert raa["units"]["pillekedel"]["fuel"] == "wood_pellets"
    assert "straw" not in raa["prices"]
    cfg = load_case(str(case))
    assert cfg.prices.fuel_price("flis") == pytest.approx(247.0)
    assert cfg.prices.fuel_price("wood_pellets") == pytest.approx(408.0)


def test_braendsel_uden_pris_stopper(tmp_path):
    def rediger(wb):
        _traepiller_raekke(wb, None)       # rækken findes, prisen er tom
        _to_biomassekedler(wb)
    r, case = _kør(tmp_path, rediger)
    assert r.returncode != 0 and case is None
    assert "træpiller" in _ud(r) and "pris" in _ud(r)


def test_ukendt_braendsel_i_kolonnen_stopper(tmp_path):
    r, case = _kør(tmp_path, lambda wb: _to_biomassekedler(wb, flis="koks", piller="flis"))
    assert r.returncode != 0
    assert "koks" in _ud(r) and "Traceback" not in r.stderr


def test_to_biomassepriser_uden_braendselskolonne_tier_ikke(tmp_path):
    """Skabelon v4: halm og flis er begge udfyldt med forskellig pris, og kedlen
    har intet brændsel. Valget (halm) skal stå i loggen med pris — ikke tages
    tavst."""
    def flis_dyrere(wb):
        wb["Priser"]["B8"] = 250.0
    r, case = _kør(tmp_path, flis_dyrere)
    assert r.returncode == 0, _ud(r)
    assert yaml.safe_load(case.read_text())["units"]["halmkedel"]["fuel"] == "straw"
    assert "ADVARSEL" in r.stdout and "halmkedel" in r.stdout
    assert "232" in r.stdout and "250" in r.stdout


def test_samme_pris_paa_halm_og_flis_naevnes_uden_advarsel(tmp_path):
    """Skabelonens eksempel har 232 på begge. Valget ændrer intet og må ikke
    drukne de advarsler, der betyder noget."""
    r, case = _kør(tmp_path)
    assert r.returncode == 0, _ud(r)
    assert "ADVARSEL" not in r.stdout
    assert "halmkedel" in r.stdout and "samme pris" in r.stdout


def test_traepiller_og_flis_uden_braendselskolonne_stopper(tmp_path):
    def rediger(wb):
        _traepiller_raekke(wb, 408.0)
        wb["Priser"]["B7"] = None          # ingen halm; træpiller og flis tilbage
    r, case = _kør(tmp_path, rediger)
    assert r.returncode != 0 and case is None
    ud = _ud(r)
    assert "halmkedel" in ud and "brændsel" in ud and "Traceback" not in r.stderr


# ----------------------------------------------------------- 3. gasafgifter
AFGIFTER = [("energiafgift", 1.1, "kr/m3", "alle"),
            ("transporttarif", 22.0, "kr/MWh", "alle"),
            ("metanafgift", 0.33, "kr/m3", "motorer"),
            ("kedelafgift", 0.55, "kr/m3", "kedler"),
            ("bruges ikke", None, "kr/m3", "alle")]


def test_gasafgifter_fordeles_paa_kedler_og_motorer(tmp_path):
    _, ref = _kør(tmp_path / "ref")
    r, case = _kør(tmp_path / "ny", lambda wb: _gasafgifter(wb, AFGIFTER))
    assert r.returncode == 0, _ud(r)
    a, b = (yaml.safe_load(c.read_text()) for c in (ref, case))
    # Fælles led lægges på gasprisen: 1,1 kr/m3 ved 11 kWh/m3 = 100 kr/MWh, plus 22.
    assert b["prices"]["natural_gas"]["value"] == pytest.approx(
        a["prices"]["natural_gas"]["value"] + 100.0 + 22.0)
    # Led for én enhedstype lægges på D&V pr. MWh varme: afgift / virkningsgrad.
    eta_m = a["units"]["gasmotor"]["eta_fuel_to_heat"]
    eta_k = a["units"]["gaskedel"]["eta_fuel_to_heat"]
    assert b["units"]["gasmotor"]["var_om"] == pytest.approx(
        a["units"]["gasmotor"]["var_om"] + 30.0 / eta_m, abs=0.01)
    assert b["units"]["gaskedel"]["var_om"] == pytest.approx(
        a["units"]["gaskedel"]["var_om"] + 50.0 / eta_k, abs=0.01)
    assert "gasafgift" in b["units"]["gasmotor"]["notes"].lower()
    load_case(str(case))


def test_kr_pr_m3_uden_braendvaerdi_stopper(tmp_path):
    r, case = _kør(tmp_path, lambda wb: _gasafgifter(wb, AFGIFTER, braendvaerdi=None))
    assert r.returncode != 0 and case is None
    assert "brændværdi" in _ud(r) and "Traceback" not in r.stderr


def test_ukendt_modtager_af_afgift_stopper(tmp_path):
    r, case = _kør(tmp_path, lambda wb: _gasafgifter(
        wb, [("metanafgift", 0.33, "kr/m3", "gas - kun ved gasmotorer")]))
    assert r.returncode != 0
    assert "gælder for" in _ud(r) and "metanafgift" in _ud(r)


# ------------------------------------------------------- 4. arket Solvarme
def test_maalt_solprofil_bruges_i_stedet_for_syntese(tmp_path):
    sol = {}
    r, case = _kør(tmp_path, lambda wb: sol.update(gwh=_solark(wb)))
    assert r.returncode == 0, _ud(r)
    u = yaml.safe_load(case.read_text())["units"]["solvarme"]
    assert u["production_profile_path"].endswith("_solvarme_maalt.csv")
    p = pd.read_csv(u["production_profile_path"], parse_dates=["time"])
    assert p["power_mw"].sum() / 1000 == pytest.approx(sol["gwh"], rel=1e-6)
    assert p["power_mw"].max() > 15            # målt spids, ikke syntesens
    # De to tomme sluttimer er nat og skrives som 0, så profilen dækker perioden.
    assert len(p) == 8760 and p["power_mw"].iloc[-2:].tolist() == [0.0, 0.0]
    assert "2 timer" in r.stdout
    load_case(str(case))


def test_solproduktion_om_natten_giver_advarsel(tmp_path):
    spidser = [("2025-12-24 23:00", 6.5), ("2025-12-25 01:00", 5.0)]
    r, case = _kør(tmp_path, lambda wb: _solark(wb, natspids=spidser))
    assert r.returncode == 0, _ud(r)
    assert "ADVARSEL" in r.stdout and "nat" in r.stdout.lower()
    assert "2025-12-24" in r.stdout


def test_uden_solark_bruges_syntesen_som_foer(tmp_path):
    r, case = _kør(tmp_path)
    u = yaml.safe_load(case.read_text())["units"]["solvarme"]
    assert u["production_profile_path"].endswith("_solvarme_profil.csv")


def test_solark_og_aarstal_i_anlaeg_sammenlignes(tmp_path):
    """Anlaeg siger 12 GWh, serien noget andet: det skal stå i loggen."""
    r, case = _kør(tmp_path, lambda wb: _solark(wb))
    assert "12" in r.stdout and "Solvarme" in r.stdout and "Anlaeg" in r.stdout


# ------------------------------------- 5. formel i Anlaeg uden beregnet værdi
def test_formel_i_anlaeg_uden_vaerdi_stopper_i_stedet_for_nul(tmp_path):
    def formel(wb):
        wb["Anlaeg"]["I7"] = "=8*600+15000"   # openpyxl gemmer ingen værdi
    r, case = _kør(tmp_path, formel)
    assert r.returncode != 0 and case is None
    ud = _ud(r)
    assert "I7" in ud and "formel" in ud and "Traceback" not in r.stderr
