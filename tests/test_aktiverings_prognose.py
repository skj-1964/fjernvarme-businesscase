"""Tests af prognosen for aktiveringsværdi (balancing.activation.foresight).

Det vigtigste krav: trailing30, lag24 og lag168 må ikke kigge ind i
fremtiden. Kapacitetsbuddet afgives dagen før, så prognosen for en time må
kun bygge på timer før det døgn, timen ligger i. profile kigger bevidst frem
(resten af måneden) — den test viser samtidig, at kig-frem-testen kan fejle.
"""
import numpy as np
import pandas as pd
import pytest

from src.config import Activation
from src.data_loader_github import aktiverings_prognose

UDEN_KIG_FREM = ["trailing30", "lag24", "lag168"]


@pytest.fixture
def serie():
    rng = np.random.default_rng(42)
    tider = pd.date_range("2025-07-01 00:00", periods=24 * 60, freq="h")
    return pd.Series(rng.gamma(0.5, 200.0, len(tider)), index=tider)


def _forstyr_fra(ser, skaering):
    """Kopi af serien, hvor alt fra og med skæringen er ændret voldsomt."""
    ny = ser.copy()
    ny[ny.index >= skaering] = ny[ny.index >= skaering] * 50 + 10_000
    return ny


@pytest.mark.parametrize("foresight", UDEN_KIG_FREM)
def test_prognosen_kigger_ikke_frem(serie, foresight):
    # Ændres alt fra 15. august kl. 00, må prognosen til og med 15. august
    # kl. 23 ikke flytte sig: den time er budt dagen før.
    skaering = pd.Timestamp("2025-08-15 00:00")
    foer = aktiverings_prognose(serie, foresight)
    efter = aktiverings_prognose(_forstyr_fra(serie, skaering), foresight)
    kendt = serie.index < skaering + pd.Timedelta(days=1)
    pd.testing.assert_series_equal(foer[kendt], efter[kendt])


def test_profile_kigger_frem(serie):
    # Dokumenterer at profile bruger resten af måneden — og at testen ovenfor
    # faktisk kan blive rød, når en metode kigger frem.
    skaering = pd.Timestamp("2025-08-15 00:00")
    foer = aktiverings_prognose(serie, "profile")
    efter = aktiverings_prognose(_forstyr_fra(serie, skaering), "profile")
    kendt = serie.index < skaering + pd.Timedelta(days=1)
    assert not np.allclose(foer[kendt], efter[kendt])


def test_lag24_er_samme_time_i_gaar(serie):
    prog = aktiverings_prognose(serie, "lag24")
    t = pd.Timestamp("2025-08-10 17:00")
    assert prog[t] == serie[t - pd.Timedelta(hours=24)]


def test_lag168_er_samme_time_sidste_uge(serie):
    prog = aktiverings_prognose(serie, "lag168")
    t = pd.Timestamp("2025-08-10 17:00")
    assert prog[t] == serie[t - pd.Timedelta(hours=168)]


def test_trailing30_er_snit_af_de_30_foregaaende_doegn(serie):
    prog = aktiverings_prognose(serie, "trailing30")
    t = pd.Timestamp("2025-08-20 10:00")
    forrige = [t - pd.Timedelta(days=d) for d in range(1, 31)]
    assert prog[t] == pytest.approx(serie[forrige].mean())


def test_ingen_historik_giver_nul(serie):
    # Første døgn kender intet: prognosen er 0, ikke en månedsprofil.
    for foresight in UDEN_KIG_FREM:
        prog = aktiverings_prognose(serie, foresight)
        assert (prog[serie.index < "2025-07-02"] == 0.0).all(), foresight


def test_realized_er_uaendret(serie):
    pd.testing.assert_series_equal(aktiverings_prognose(serie, "realized"), serie)


def test_ukendt_foresight_afvises(serie):
    with pytest.raises(ValueError):
        aktiverings_prognose(serie, "lag12")


@pytest.mark.parametrize("foresight", ["realized", "profile", *UDEN_KIG_FREM])
def test_config_accepterer_foresight(foresight):
    assert Activation(foresight=foresight).foresight == foresight


def test_config_afviser_ukendt_foresight_og_settle():
    with pytest.raises(ValueError):
        Activation(foresight="i_morgen")
    with pytest.raises(ValueError):
        Activation(settle="gaet")


def test_settle_default_er_forecast():
    # Default må ikke ændre eksisterende cases.
    assert Activation().settle == "forecast"


def test_loft_paa_ukendt_enhed_afvises(tmp_path):
    # Før blev et loft på en enhed, der ikke findes, ignoreret tavst.
    import yaml
    from src.config import load_case
    d = yaml.safe_load(open("cases/andeby.yaml", encoding="utf-8"))
    d["balancing"]["ancillary_caps"]["per_unit_mw"] = {"varmepumpe_findes_ikke": 6.0}
    sti = tmp_path / "forkert_navn.yaml"
    sti.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="findes ikke i casen"):
        load_case(str(sti))


def test_alle_cases_kan_indlaeses():
    import glob
    from src.config import load_case
    for sti in glob.glob("cases/*.yaml"):
        if "heat_load_params" in sti:
            continue
        load_case(sti)


def test_budprofilerne_i_dokumentationen_kan_indlaeses(tmp_path):
    # doc/BUDSTRATEGI.md er det, deltagerne kopierer fra. Hver profil skal
    # kunne indlæses sammen med den fælles blok, ellers er dokumentet forkert.
    import copy
    import re
    import yaml
    from src.config import load_case
    tekst = open("doc/BUDSTRATEGI.md", encoding="utf-8").read()
    blokke = re.findall(r"```yaml\n(.*?)```", tekst, re.S)
    faelles = yaml.safe_load(blokke[0])["balancing"]
    profiler = [b for b in blokke[1:] if b.lstrip().startswith("reservation_gate")]
    assert len(profiler) == 5
    base = yaml.safe_load(open("cases/andeby.yaml", encoding="utf-8"))
    for i, blok in enumerate(profiler, 1):
        d = copy.deepcopy(base)
        bal = copy.deepcopy(faelles)
        bal.update(yaml.safe_load(blok))
        d["balancing"] = bal
        sti = tmp_path / f"profil{i}.yaml"
        sti.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        load_case(str(sti))
