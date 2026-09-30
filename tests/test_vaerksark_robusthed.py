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
