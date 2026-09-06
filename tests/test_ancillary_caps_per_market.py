"""Vagt om ancillary_caps.per_unit_market_mw.

Loftet blev indført for at kunne udtrykke Johns oplysning af 26/8 2026: VP'en
bydes med 2 MW eloptag i aFRR-CM og 3 MW i mFRR-CM inden for de 5,52 MW, der
er prækvalificeret i alt. Det gamle per_unit_mw er ét tal for summen af begge
markeder og kan ikke bære en fordeling.

Testen rører ingen data, kalder ingen solver og laver ingen netværkskald.
Den holder tre ting fast:

1. Feltet parses fra YAML og lander på AncillaryCaps.
2. Ukendte markedsnøgler og forkert type afvises ved indlæsning, ikke ved
   modelopbygning. En stavefejl som `mrfr` skal fejle højlydt — et loft, der
   stiltiende ikke håndhæves, ser ud som en adfærdsændring i resultatet.
3. Cases uden feltet er upåvirkede. Bagudkompatibiliteten er ikke kosmetisk:
   samtlige eksisterende cases i cases/ bruger den gamle form.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.config import AncillaryCaps, load_case

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES = REPO_ROOT / "cases"


def test_v3_cases_baerer_johns_fordeling():
    """v3-casene skal have præcis 2 MW aFRR / 3 MW mFRR på VP'en."""
    for navn in ("billund_sporA_v3.yaml", "billund_sporB_v3.yaml"):
        cfg = load_case(str(CASES / navn))
        caps = cfg.ancillary_caps
        assert caps is not None, f"{navn}: ancillary_caps mangler"
        assert caps.per_unit_market_mw == {
            "vp_luft_vand": {"afrr": 2.0, "mfrr": 3.0}
        }, f"{navn}: per_unit_market_mw afviger fra Johns oplysning"
        # Prækvalificeringen skal stadig stå ved siden af — de to lofter er
        # ikke alternativer, og summen 2+3 ligger under 5,52 med vilje.
        assert caps.per_unit_mw["vp_luft_vand"] == pytest.approx(5.52)


def test_ukendt_markedsnoegle_afvises():
    with pytest.raises(ValueError, match="ukendt marked"):
        AncillaryCaps(per_unit_market_mw={"vp_luft_vand": {"mrfr": 3.0}})


def test_ikke_map_afvises():
    with pytest.raises(ValueError, match="skal være et map"):
        AncillaryCaps(per_unit_market_mw={"vp_luft_vand": 3.0})


def test_delvist_loft_er_lovligt():
    """Kun ét marked nævnt = kun det marked begrænses. Ikke en fejl."""
    caps = AncillaryCaps(per_unit_market_mw={"elkedel_gl": {"afrr": 4.0}})
    assert caps.per_unit_market_mw["elkedel_gl"] == {"afrr": 4.0}


def test_bagudkompatibilitet_alle_eksisterende_cases():
    """Cases uden feltet skal indlæses med tomt map, ikke None og ikke fejl."""
    rørte = 0
    for sti in sorted(CASES.glob("*.yaml")):
        if sti.name.startswith("heat_load_params"):
            continue  # parameterfiler, ikke cases
        cfg = load_case(str(sti))
        caps = getattr(cfg, "ancillary_caps", None)
        if caps is None:
            continue
        assert isinstance(caps.per_unit_market_mw, dict)
        if "_v3" not in sti.name and sti.name != "andeby.yaml":
            assert caps.per_unit_market_mw == {}, (
                f"{sti.name} har uventet per_unit_market_mw — kun v3-casene og "
                f"referencecasen andeby.yaml skal bære fordelingen"
            )
        rørte += 1
    assert rørte > 0, "ingen cases med ancillary_caps fundet — testen måler intet"
