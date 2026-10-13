"""Tests for scripts/fiktivt_balancemarked.py på et lille syntetisk df-data."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fiktivt_balancemarked as fb  # noqa: E402

EUR = 7.45


def _kap(t, pris):
    return pd.DataFrame({"TimeUTC": t.strftime("%Y-%m-%d %H:%M:%S"), "UpPriceDKK": pris, "UpPriceEUR": pris / EUR,
                         "UpProcuredMW": 100.0})


def _lav_kilde(rod: Path) -> Path:
    k = rod / "df-data"
    (k / ".git").mkdir(parents=True)
    rng = np.random.default_rng(1)
    for y, start, n in [(2025, "2025-06-30 22:00", 24 * 31 * 2), (2026, "2025-12-31 23:00", 24 * 31 * 2)]:
        t = pd.date_range(start, periods=n, freq="h")
        for ds, niveau in [("afrr", 400.0 if y == 2025 else 100.0), ("mfrr_cap", 50.0 if y == 2025 else 120.0)]:
            (k / ds).mkdir(exist_ok=True)
            _kap(t, niveau * (0.5 + rng.random(n))).to_csv(k / ds / f"DK1_{y}.csv", index=False)
        tq = pd.date_range(start, periods=n * 4, freq="15min")
        spot = 80.0 + 20 * rng.random(n * 4)                       # EUR
        a = spot * EUR + (900 if y == 2025 else 300) * (rng.random(n * 4) - 0.3)
        m = spot * EUR + (200 if y == 2025 else 400) * (rng.random(n * 4) - 0.3)
        (k / "imbalance").mkdir(exist_ok=True)
        pd.DataFrame({"TimeUTC": tq.strftime("%Y-%m-%d %H:%M:%S"), "SpotPriceEUR": spot,
                      "aFRRVWAUpDKK": a, "aFRRVWAUpEUR": a / EUR,
                      "mFRRMarginalPriceUpDKK": m, "mFRRMarginalPriceUpEUR": m / EUR,
                      "aFRRUpMW": 3.0}).to_csv(k / "imbalance" / f"DK1_{y}.csv", index=False)
    return k


def _laes(mappe, ds):
    d = pd.concat(pd.read_csv(mappe / ds / f"DK1_{y}.csv") for y in (2025, 2026))
    d["mdr"] = fb._dk_maaned(d.TimeUTC)
    return d


PER, REF = ["2025-07", "2025-08"], ["2026-01", "2026-02"]


@pytest.fixture
def bygget(tmp_path):
    k = _lav_kilde(tmp_path)
    m = tmp_path / "fiktiv"
    r = fb.byg(k, m, PER, REF)
    return k, m, r


def test_kapacitetspris_rammer_referencesnittet(bygget):
    k, m, _ = bygget
    for ds in ("afrr", "mfrr_cap"):
        d = _laes(m, ds)
        ref = d[d.mdr.isin(REF)].UpPriceDKK.mean()
        for mdr in PER:
            assert d[d.mdr == mdr].UpPriceDKK.mean() == pytest.approx(ref, rel=1e-9)
        assert np.allclose(d.UpPriceEUR * EUR, d.UpPriceDKK)


def test_aktiveringspraemie_rammer_referencen_og_under_spot_er_uroert(bygget):
    k, m, _ = bygget
    f, o = _laes(m, "imbalance"), _laes(k, "imbalance")
    for col in ("aFRRVWAUpDKK", "mFRRMarginalPriceUpDKK"):
        pr = lambda d: (d[col] - d.SpotPriceEUR * EUR).clip(lower=0)
        ref = pr(f[f.mdr.isin(REF)]).mean()
        for mdr in PER:
            assert pr(f[f.mdr == mdr]).mean() == pytest.approx(ref, rel=1e-9)
        under = (o[col] <= o.SpotPriceEUR * EUR).values
        assert np.allclose(f[col].values[under], o[col].values[under])


def test_uden_for_perioden_og_maengder_er_uroert(bygget):
    k, m, _ = bygget
    for ds, cols in (("afrr", ["UpPriceDKK", "UpProcuredMW"]), ("imbalance", ["aFRRVWAUpDKK", "aFRRUpMW", "SpotPriceEUR"])):
        f, o = _laes(m, ds), _laes(k, ds)
        uden = ~o.mdr.isin(PER).values
        for c in cols:
            assert np.allclose(f[c].values[uden], o[c].values[uden])
        assert np.allclose(f[cols[-1]].values, o[cols[-1]].values)


def test_kilden_aendres_ikke_og_maerkning_skrives(tmp_path):
    k = _lav_kilde(tmp_path)
    foer = (k / "afrr" / "DK1_2025.csv").read_bytes()
    m = tmp_path / "fiktiv"
    fb.byg(k, m, PER, REF)
    assert (k / "afrr" / "DK1_2025.csv").read_bytes() == foer
    assert (m / ".git").exists()
    assert "FIKTIVT" in (m / "FIKTIVT_MARKED.md").read_text()
    assert set(json.loads((m / "faktorer.json").read_text())["faktorer"]) == {
        "aFRR-kapacitet", "mFRR-kapacitet", "aFRR-aktivering", "mFRR-aktivering"}


def test_vagter(tmp_path):
    k = _lav_kilde(tmp_path)
    with pytest.raises(ValueError):
        fb.byg(k, k, PER, REF)
    with pytest.raises(ValueError):
        fb.byg(k, k / "under", PER, REF)
    with pytest.raises(ValueError):
        fb.byg(k, tmp_path / "x", PER, PER)
    fb.byg(k, tmp_path / "y", PER, REF)
    with pytest.raises(FileExistsError):
        fb.byg(k, tmp_path / "y", PER, REF)
    fb.byg(k, tmp_path / "y", PER, REF, overskriv=True)
    (k / ".git").rmdir()
    with pytest.raises(FileNotFoundError):
        fb.byg(k, tmp_path / "z", PER, REF)


def test_maaneder():
    assert fb.maaneder("2025-11..2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    with pytest.raises(ValueError):
        fb.maaneder("2025-11")
