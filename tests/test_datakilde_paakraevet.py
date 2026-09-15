"""Datakilden har ingen default.

Tidligere var --dummy default: en deltager, der glemte flaget, fik syntetiske
tal, som lignede rigtige. Testene her låser, at kørslen stopper højlydt uden
datakilde, og at hver gyldig datakilde fortsat accepteres -- så testen også
kan blive rød, hvis tjekket blev for strengt.

Kræver ikke df-data og kalder ingen solver.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import run_case
from run_case import DATA_SOURCE_MISSING_MSG, _parse_args, _require_data_source

CASE = "cases/billund_sporA.yaml"


def _parse(monkeypatch, *flags):
    monkeypatch.setattr(sys, "argv", ["run_case.py", CASE, *flags])
    return _parse_args()


def test_uden_datakilde_stopper(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _parse(monkeypatch)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "Ingen datakilde valgt" in err
    assert "--data-source github" in err


def test_data_source_api_alene_er_ikke_et_valg(monkeypatch):
    # 'api' er argparse-defaulten og betyder kun noget sammen med --external.
    with pytest.raises(SystemExit):
        _parse(monkeypatch, "--data-source", "api")


@pytest.mark.parametrize(
    "flags",
    [
        ("--dummy",),
        ("--external",),
        ("--data-source", "github"),
        ("--external", "--data-source", "api"),
        ("--data-path", "et/sted"),
    ],
)
def test_gyldige_datakilder_accepteres(monkeypatch, flags):
    args = _parse(monkeypatch, *flags)
    assert args is not None


def test_dummy_er_ikke_laengere_sat_af_sig_selv(monkeypatch):
    args = _parse(monkeypatch, "--data-source", "github")
    assert args.dummy is False


def test_require_kalder_fail_med_beskeden():
    kald = []
    args = SimpleNamespace(dummy=False, external=False, data_path=None,
                           data_source="api")
    _require_data_source(args, kald.append)
    assert kald == [DATA_SOURCE_MISSING_MSG]


def test_load_data_falder_ikke_tavst_tilbage_til_dummy(monkeypatch):
    # Selv hvis parse-tjekket omgås, må _load_data ikke generere syntetiske
    # data uden --dummy.
    monkeypatch.setattr(run_case, "generate_dummy_data",
                        lambda cfg: pytest.fail("dummy-data genereret tavst"))
    args = SimpleNamespace(dummy=False, external=False, data_path=None,
                           data_source="api")
    with pytest.raises(ValueError, match="Ingen datakilde valgt"):
        run_case._load_data(args, cfg=None)
