"""K9: en deltagers timedata må aldrig kunne ende i det offentlige repo.

Før denne vagt skrev vaerksark_til_yaml.py direkte i cases/ og data/, og
filerne stod bagefter som ucommittede. Et `git add .` i uge 41 ville have
lagt et værks timedata offentligt, uden at noget så forkert ud.

Nu skriver konverteringen som standard i den git-ignorerede mappe deltagere/
og stopper, før den skriver noget, hvis arket eller en outputfil ligger et
sted i repoet, som git ikke ignorerer.

Testene kører konverteringen i et midlertidigt git-repo med repoets egen
.gitignore, så den rigtige arbejdskopi aldrig røres.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_cop_tabel import _byg_og_fyld

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "vaerksark_til_yaml.py"


def _git(cwd: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture(scope="module")
def udfyldt_ark(tmp_path_factory) -> Path:
    return _byg_og_fyld(tmp_path_factory.mktemp("ark"))


@pytest.fixture
def repo(tmp_path) -> Path:
    """Et tomt git-repo med fjernvarme-businesscase's .gitignore."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    shutil.copy(REPO_ROOT / ".gitignore", r / ".gitignore")
    return r


def _kør(repo: Path, ark: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), str(ark), *args],
                          cwd=repo, capture_output=True, text=True)


def _sporbare(repo: Path) -> list[str]:
    """Filer, et `git add .` ville tage med (ud over .gitignore selv)."""
    ud = _git(repo, "status", "--porcelain", "--untracked-files=all").stdout
    return [l for l in ud.splitlines() if not l.endswith(".gitignore")]


def test_repoets_gitignore_ignorerer_deltagere():
    for sti in ("deltagere/cases/x.yaml", "deltagere/data/x.csv",
                "deltagere/x.xlsx"):
        assert _git(REPO_ROOT, "check-ignore", "-q", sti).returncode == 0, sti


def test_standard_skriver_i_deltagere_og_intet_kan_committes(repo, udfyldt_ark):
    (repo / "deltagere").mkdir()
    ark = shutil.copy(udfyldt_ark, repo / "deltagere" / "vaerk.xlsx")
    r = _kør(repo, Path(ark))
    assert r.returncode == 0, r.stderr
    assert list((repo / "deltagere" / "cases").glob("*.yaml"))
    assert list((repo / "deltagere" / "data").glob("*_abvaerk_hourly.csv"))
    assert _sporbare(repo) == []


def test_output_i_cases_stoppes_foer_der_skrives(repo, udfyldt_ark):
    (repo / "deltagere").mkdir()
    ark = shutil.copy(udfyldt_ark, repo / "deltagere" / "vaerk.xlsx")
    r = _kør(repo, Path(ark), "--cases-dir", "cases", "--data-dir", "data")
    assert r.returncode == 1
    assert "offentlige repo" in r.stderr
    assert not (repo / "cases").exists() and not (repo / "data").exists()
    assert _sporbare(repo) == []


def test_ark_i_repoets_rod_stoppes(repo, udfyldt_ark):
    ark = shutil.copy(udfyldt_ark, repo / "vaerk.xlsx")
    r = _kør(repo, Path(ark))
    assert r.returncode == 1
    assert "arket" in r.stderr
    assert not (repo / "deltagere").exists()


def test_tillad_offentlig_slaar_vagten_fra(repo, udfyldt_ark):
    ark = shutil.copy(udfyldt_ark, repo / "andeby.xlsx")
    r = _kør(repo, Path(ark), "--cases-dir", "cases", "--data-dir", "data",
             "--tillad-offentlig")
    assert r.returncode == 0, r.stderr
    assert list((repo / "cases").glob("*.yaml"))


def test_uden_ignore_linjen_stoppes_standarden(repo, udfyldt_ark):
    """Vagten stoler ikke på mappenavnet, men på git. Fjernes linjen i
    .gitignore, er deltagere/ ikke længere sikker — og så stopper den."""
    gi = repo / ".gitignore"
    gi.write_text(gi.read_text().replace("/deltagere/\n", ""))
    ark = shutil.copy(udfyldt_ark, repo / "vaerk_udenfor.xlsx")
    r = _kør(repo, Path(ark))
    assert r.returncode == 1
    assert "casefil" in r.stderr and "timedata" in r.stderr


def test_uden_for_et_repo_er_der_intet_at_laekke(tmp_path, udfyldt_ark):
    r = _kør(tmp_path, udfyldt_ark)
    assert r.returncode == 0, r.stderr
