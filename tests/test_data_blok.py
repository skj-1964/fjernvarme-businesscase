"""Tests til den paakraevede data-blok (dmi_area, price_zone).

Laegges i tests/test_data_blok.py.

Baggrund: dmi_area og price_zone laa som CLI-defaults (`--dmi-area fyn`,
`--price-zone DK1`). Den 9. september 2026 blev Andeby lagt om til et rullende
aar juli 2025 - juni 2026, hvor fyn og vestkyst mangler 28. februar 2026.
Casen fejlede paa coverage, med mindre man huskede et flag, der ikke stod
nogen steder i casen. Blokken er derfor paakraevet og har ingen default --
flytter man blot defaulten til YAML, er faelden den samme, bare rykket et lag
ind.
"""
import re
import tempfile
from pathlib import Path

import pytest

from src.config import DataOptions, load_case

CASES = Path("cases")
BASE = CASES / "billund_sporA.yaml"


def _med_data_blok(blok: str) -> str:
    """Erstat data-blokken i referencecasen med `blok` (tom = fjernet)."""
    tekst = BASE.read_text()
    ny = re.sub(r"^data:\n(?:  .*\n)+", blok, tekst, count=1, flags=re.M)
    p = Path(tempfile.mkdtemp()) / "case.yaml"
    p.write_text(ny)
    return str(p)


# --- GROENNE: blokken virker -------------------------------------------------

def test_alle_cases_har_data_blok():
    """Ingen case maa mangle blokken — den er ikke valgfri."""
    for sti in sorted(CASES.glob("*.yaml")):
        if "\nunits:" not in sti.read_text():
            continue                      # params-fil, ikke en case
        cfg = load_case(str(sti))
        assert cfg.data.dmi_area
        assert cfg.data.price_zone


def test_andeby_bruger_karup():
    """Andebys rullende aar kan ikke koere paa fyn: 28. februar 2026 mangler."""
    assert load_case(str(CASES / "andeby.yaml")).data.dmi_area == "karup"


def test_billund_bruger_fyn():
    """Billund-ankrene er produceret med fyn og skal blive ved med det."""
    assert load_case(str(BASE)).data.dmi_area == "fyn"


def test_defaults_paa_de_valgfri_felter():
    d = DataOptions(dmi_area="fyn", price_zone="DK1")
    assert d.dmi_temp_shortname == "temp_mean_past1h"
    assert d.eur_dkk == 7.45


# --- ROEDE: kontrollerne skal kunne fejle ------------------------------------

def test_manglende_blok_afvises():
    with pytest.raises(ValueError, match="mangler en 'data'-blok"):
        load_case(_med_data_blok(""))


@pytest.mark.parametrize("blok,fragment", [
    ('data:\n  price_zone: "DK1"\n',                     "data.dmi_area mangler"),
    ('data:\n  dmi_area: "fyn"\n',                       "data.price_zone mangler"),
    ('data:\n  dmi_area: "fyen"\n  price_zone: "DK1"\n', "ikke en kendt DMI-station"),
    ('data:\n  dmi_area: "fyn"\n  price_zone: "DK3"\n',  "ikke en kendt priszone"),
    ('data:\n  dmi_area: "fyn"\n  price_zone: "DK1"\n  eur_dkk: 0\n', "eur_dkk"),
])
def test_ugyldig_blok_afvises(blok, fragment):
    with pytest.raises(ValueError, match=fragment):
        load_case(_med_data_blok(blok))


def test_tastefejl_i_noegle_afvises():
    """`dmi_aera` maa ikke ignoreres tavst — saa ville casen falde tilbage paa
    en vaerdi, brugeren troede, han havde overskrevet."""
    blok = 'data:\n  dmi_area: "fyn"\n  price_zone: "DK1"\n  dmi_aera: "karup"\n'
    with pytest.raises(ValueError, match="ukendte noegler i data-blokken"):
        load_case(_med_data_blok(blok))
