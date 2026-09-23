"""Tests til solver-gap-konfigurationen.

Laegges i tests/test_solver_gap.py.

Baggrund: standardgappet paa 0,5 % er ca. 26.000 DKK paa et objektiv omkring
5 mio, mens de marginale trin i et tanksweep er 2.000-14.000 DKK. Maalt
9. september 2026 blev objektivet 1.262 DKK DAARLIGERE af at tilfoeje en
30 MW elkedel — umuligt, og alene solverstoej. Testene her bevogter, at
tolerancen kan saettes, at den valideres, og at standarden er uaendret.
"""
import tempfile
from pathlib import Path

import pytest
import yaml

from src.config import Solver, load_case

CASE = "cases/billund_sporA.yaml"


def _case_med_solver(blok):
    raw = yaml.safe_load(Path(CASE).read_text())
    if blok is None:
        raw.pop("solver", None)
    else:
        raw["solver"] = blok
    p = Path(tempfile.mkdtemp()) / "case.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True))
    return str(p)


def test_standard_er_uaendret():
    """Bagudkompatibilitet: en case uden solver-blok skal give de gamle vaerdier."""
    cfg = load_case(_case_med_solver(None))
    assert cfg.solver.mip_rel_gap == 0.005
    assert cfg.solver.mip_abs_gap == 5000.0
    assert cfg.solver.time_limit == 600.0


def test_blok_laeses_fra_yaml():
    cfg = load_case(_case_med_solver({"mip_rel_gap": 0.0002, "mip_abs_gap": 200.0}))
    assert cfg.solver.mip_rel_gap == 0.0002
    assert cfg.solver.mip_abs_gap == 200.0
    # ikke-angivne felter beholder standarden
    assert cfg.solver.time_limit == 600.0


def test_as_options_indeholder_alle_noegler():
    o = Solver().as_options()
    assert set(o) == {"mip_rel_gap", "mip_abs_gap", "time_limit", "presolve", "parallel"}


# --- ROEDE tests: valideringen skal kunne fejle -------------------------------

@pytest.mark.parametrize("blok,fragment", [
    ({"mip_rel_gap": 1.5},   "mip_rel_gap"),
    ({"mip_rel_gap": -0.1},  "mip_rel_gap"),
    ({"mip_abs_gap": -1.0},  "mip_abs_gap"),
    ({"time_limit": 0.0},    "time_limit"),
])
def test_ugyldige_vaerdier_afvises(blok, fragment):
    with pytest.raises(ValueError, match=fragment):
        load_case(_case_med_solver(blok))


def test_stavefejl_i_noegle_afvises():
    """En tastefejl maa ikke blive tavst ignoreret — saa ville man tro, man
    koerte stramt, mens man koerte loest."""
    with pytest.raises(ValueError, match="ukendte noegler"):
        load_case(_case_med_solver({"mip_relgap": 0.0002}))
