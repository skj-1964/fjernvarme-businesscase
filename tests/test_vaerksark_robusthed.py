"""Give Fjernvarme (29/9 2026): første rigtige ark afslørede fem steder, hvor
konverteringen enten gættede en fast række, gav et traceback eller tav.

  1. tankblok, enhedsblok og varmepumpeblok stod på faste rækker. Slettede
     deltageren de grå rækker (som vejledningen beder om), rykkede tankene op,
     og konverteringen sagde "ingen akkumuleringstanke".
  2. tekst (`???`) i talkolonnen gav traceback i stedet for en besked med række.
  3. dækning blev målt mod seriens eget interval, så en serie uden juni og
     med 24 timer for lidt i enderne fik "dækning 99,9 %" og ingen advarsel.
  4. formelceller i Priser (`=65*3.6`) blev læst som en manglende pris.
  5. tidszonen skal tåle mellemrum og store bogstaver, men aldrig gættes.
"""
from __future__ import annotations

import datetime as dt

import pytest
import yaml

from src.config import load_case
from tests.test_cop_tabel import _byg_og_fyld, _konverter


def _kør(tmp_path, rediger=None):
    return _konverter(tmp_path, _byg_og_fyld(tmp_path, rediger))


# ------------------------------------------------------------------ fejl 1
def _flyt_tanke_med_tre_slettede_raekker(wb):
    for ws in (wb["Anlaeg"], wb["Varmepumpe"]):
        ws.delete_rows(9, 3)


def test_slettede_raekker_flytter_ikke_tankene_ud_af_syne(tmp_path):
    r, case = _kør(tmp_path, _flyt_tanke_med_tre_slettede_raekker)
    assert r.returncode == 0, r.stdout + r.stderr
    raa = yaml.safe_load(case.read_text())
    assert set(raa["storage"]) == {"tank_stor", "tank_lille"}
    assert "Enheder: 4" in r.stdout          # syv minus tre slettede
    load_case(str(case))


def test_manglende_tankoverskrift_giver_klar_besked(tmp_path):
    def uden_overskrift(wb):
        wb["Anlaeg"]["A51"] = None
    r, case = _kør(tmp_path, uden_overskrift)
    assert r.returncode != 0
    assert "tank" in (r.stdout + r.stderr) and "overskrift" in (r.stdout + r.stderr)
    assert "Traceback" not in r.stderr


# ------------------------------------------------------------------ fejl 2
def test_tekst_i_talkolonnen_giver_raekkenummer_ikke_traceback(tmp_path):
    def tekst(wb):
        wb["Timedata"]["B556"] = "???"
    r, case = _kør(tmp_path, tekst)
    assert r.returncode != 0
    ud = r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    assert "556" in ud and "???" in ud


# ------------------------------------------------------------------ fejl 3
def _fjern_foerste_og_sidste_dag(wb):
    ws = wb["Timedata"]
    ws.delete_rows(6, 11)                     # 1/7 kl. 0-10
    for r in range(ws.max_row, ws.max_row - 13, -1):   # 30/6 kl. 11-23
        ws.cell(r, 1).value = None
        ws.cell(r, 2).value = None


def test_daekning_maales_mod_den_faste_periode(tmp_path):
    r, case = _kør(tmp_path, _fjern_foerste_og_sidste_dag)
    assert r.returncode == 0, r.stdout + r.stderr
    ud = r.stdout
    assert "11 timer" in ud and "13 timer" in ud     # start og slut, hver for sig
    assert "1. juli 2025" in ud and "30. juni 2026" in ud


def test_tidsstempel_uden_for_perioden_stopper_med_raekke(tmp_path):
    def gammelt(wb):
        wb["Timedata"]["A8000"] = dt.datetime(1900, 1, 4)
    r, case = _kør(tmp_path, gammelt)
    assert r.returncode != 0
    assert "8000" in r.stdout + r.stderr
    assert "Traceback" not in r.stderr


def test_b3_sammenlignes_altid_med_serien(tmp_path):
    r, case = _kør(tmp_path)                   # B3 = 150 i testarket
    assert "B3" in r.stdout


# ------------------------------------------------------------------ fejl 4
def test_formel_i_priser_uden_cachet_vaerdi_regnes_ud(tmp_path):
    def formel(wb):
        wb["Priser"]["B8"] = "=65*3.6"
    r, case = _kør(tmp_path, formel)
    assert r.returncode == 0, r.stdout + r.stderr
    assert yaml.safe_load(case.read_text())["prices"]["flis"]["value"] == pytest.approx(234)


def test_formel_med_cellehenvisning_afvises_med_besked(tmp_path):
    def formel(wb):
        wb["Priser"]["B8"] = "=B7*2"
    r, case = _kør(tmp_path, formel)
    assert r.returncode != 0
    ud = r.stdout + r.stderr
    assert "B8" in ud and "formel" in ud and "Traceback" not in r.stderr


# ------------------------------------------------------------------ fejl 5
@pytest.mark.parametrize("skrevet", ["Dansk lokaltid", "DANSK  LOKALTID ",
                                     "dansk lokaltid"])
def test_tidszone_tolererer_mellemrum_og_store_bogstaver(tmp_path, skrevet):
    def tz(wb):
        wb["Timedata"]["B2"] = skrevet
    r, case = _kør(tmp_path, tz)
    assert r.returncode == 0, r.stdout + r.stderr


def test_tidszone_gaettes_aldrig(tmp_path):
    def tz(wb):
        wb["Timedata"]["B2"] = "Dansk lokal"
    r, case = _kør(tmp_path, tz)
    assert r.returncode != 0 and case is None


# ------------------------------------------------- Aulum (30/9 2026)
# Aulums ark havde en sidste række (8765) med samme tidsstempel som første række.
# Konverteren kaldte to gentagelser for "efterårets dobbelttime, som forventet",
# og CSV'en fik en reel dublet. Og en fejl sent i konverteringen (varmepumpe-
# arket) efterlod en timefil, så andet forsøg krævede --overskriv.
def _lokal_aarsserie(wb, stray=False):
    import pandas as pd
    ws = wb["Timedata"]
    ws["B2"] = "dansk lokaltid"
    t = (pd.date_range("2025-06-30 22:00", "2026-06-30 21:00", freq="h", tz="UTC")
         .tz_convert("Europe/Copenhagen").tz_localize(None))
    for i, a in enumerate(t):
        ws.cell(6 + i, 1).value = a.to_pydatetime()
        ws.cell(6 + i, 2).value = 3.0
    if stray:
        ws.cell(6 + len(t) - 1, 1).value = t[0].to_pydatetime()   # som Aulum række 8765


def test_efteraarets_dobbelttime_er_stadig_tilladt_i_dansk_tid(tmp_path):
    r, case = _kør(tmp_path, _lokal_aarsserie)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dobbelttime" in r.stdout


def test_dublet_uden_for_dobbelttimen_stopper_med_raekke(tmp_path):
    r, case = _kør(tmp_path, lambda wb: _lokal_aarsserie(wb, stray=True))
    assert r.returncode != 0, r.stdout
    ud = r.stdout + r.stderr
    assert "8765" in ud and "Traceback" not in r.stderr
    assert not list((tmp_path / "data").glob("*_abvaerk_hourly.csv"))


def test_sen_fejl_efterlader_ingen_timefil(tmp_path):
    def vp_uden_navn(wb):
        wb["Varmepumpe"]["B20"] = 5.0            # tal uden navn
    r, case = _kør(tmp_path, vp_uden_navn)
    assert r.returncode != 0
    assert "Varmepumpe" in r.stdout + r.stderr
    assert not list((tmp_path / "data").glob("*_abvaerk_hourly.csv"))


# ------------------------------------------------- Aulum: timeslut-stempler
# Aulums SRO stempler timen med dens SLUT (01:00 = kl. 00-01). Uden en
# korrektion ligger hele året en time forkert i forhold til elpriser og vejr,
# og sidste række (1/7-2026 00:00) falder uden for perioden.
def _timeslut_serie(wb):
    import pandas as pd
    ws = wb["Timedata"]
    ws["B2"] = "dansk lokaltid"
    start_utc = pd.date_range("2025-06-30 22:00", periods=8760, freq="h", tz="UTC")
    stempel = (start_utc + pd.Timedelta(hours=1)).tz_convert("Europe/Copenhagen")
    for i, (a, s) in enumerate(zip(stempel.tz_localize(None), start_utc)):
        ws.cell(6 + i, 1).value = a.to_pydatetime()
        ws.cell(6 + i, 2).value = 1.0 + (s.hour % 24) / 10    # kendeligt mønster


def _kør_med(tmp_path, rediger, *flag):
    import subprocess, sys
    from tests.test_cop_tabel import REPO_ROOT
    ark = _byg_og_fyld(tmp_path, rediger)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "vaerksark_til_yaml.py"),
         str(ark), "--cases-dir", str(tmp_path / "cases"),
         "--data-dir", str(tmp_path / "data"), *flag],
        capture_output=True, text=True, cwd=REPO_ROOT)


def test_timeslut_stempler_flyttes_en_time_tilbage(tmp_path):
    import pandas as pd
    r = _kør_med(tmp_path, _timeslut_serie, "--timeslut")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ADVARSEL" not in r.stdout                 # perioden er dækket helt
    d = pd.read_csv(next((tmp_path / "data").glob("*_abvaerk_hourly.csv")),
                    parse_dates=["timestamp"])
    assert len(d) == 8760 and not d.timestamp.duplicated().any()
    assert d.timestamp.iloc[0] == pd.Timestamp("2025-06-30 22:00")   # 1/7 00:00 dansk
    assert d.timestamp.iloc[-1] == pd.Timestamp("2026-06-30 21:00")  # 30/6 23:00 dansk
    # værdien er den, der stod ved timens slut: hver time har sit eget mønster
    assert d.heat_mw_abvaerk.iloc[0] == pytest.approx(1.0 + 22 / 10)


def test_timeslut_uden_flag_stopper_i_stedet_for_at_flytte_tavst(tmp_path):
    r = _kør_med(tmp_path, _timeslut_serie)
    assert r.returncode != 0
    assert "uden for perioden" in r.stdout + r.stderr


# ------------------------------------------------- Aulum: brøkdele af en time
# Aulum skrev min driftstid 0,15 t (9 minutter) og min last 1,3 MW for elkedlen.
# Konverteren lavede int(0,15) = 0, og casen kunne ikke indlæses i modellen
# ("min_uptime/min_downtime skal være ≥ 1") — først ved kørsel, ikke ved konvertering.
def test_brøkdele_af_en_time_rundes_op_og_casen_kan_indlæses(tmp_path):
    def ret(wb):
        ws = wb["Anlaeg"]
        assert ws["A6"].value == "elkedel"
        ws["D6"] = 1.3                            # min last > 0 → unit commitment
        ws["J6"] = 0.15
        ws["K6"] = 0.5
    r, case = _kør(tmp_path, ret)
    assert r.returncode == 0, r.stdout + r.stderr
    u = yaml.safe_load(case.read_text())["units"]["elkedel"]
    assert u["min_uptime"] == 1 and u["min_downtime"] == 1
    load_case(str(case))                           # skal ikke kaste


def test_halve_timer_over_en_rundes_op(tmp_path):
    def ret(wb):
        ws = wb["Anlaeg"]
        ws["J6"] = 2.5
    r, case = _kør(tmp_path, ret)
    assert r.returncode == 0, r.stdout + r.stderr
    assert yaml.safe_load(case.read_text())["units"]["elkedel"]["min_uptime"] == 3
