"""Forhåndsberegning af helår for deltagerværkerne (kursus 22. oktober 2026).

Kører run_case.py for hver case i en jobfil, enten som ét helårsløb eller
som tolv månedsløb, og samler objektiv, status, gap og løsetid i én oversigt.

Køres fra repoets rod, på en maskine med repoet klonet og requirements
installeret (se doc/WORKFLOW_LOKAL.md):

    # 1. Pak casezip'er ud og konvertér regnearkene i deltagere/
    python scripts/aarsberegning.py --forbered

    # 2. Lav en jobfil ud fra det, der nu ligger i deltagere/cases/
    python scripts/aarsberegning.py --lav-jobfil

    # 3. Ret deltagere/aarsberegning.yaml (særtilfælde står øverst i filen)

    # 4. Se kommandoerne uden at køre noget
    python scripts/aarsberegning.py --proeve

    # 5. Kør alt (kørsler, der allerede er færdige, springes over)
    python scripts/aarsberegning.py

    # Kun nogle værker, eller kun enkelte måneder
    python scripts/aarsberegning.py --kun midtfyn --maaned 2026-01 --maaned 2026-02

Output lægges i deltagere/output/aarsberegning/, som git ignorerer, fordi
resultaterne indeholder værkernes data. Oversigten står i
deltagere/output/aarsberegning/oversigt.csv og oversigt.md.

OM MÅNEDSLØB
Et månedsløb er tolv uafhængige optimeringer. Hver måned starter og slutter
med tankene på start-indholdet, og enhedernes startstatus nulstilles. Summen
er derfor lidt højere end et ægte helårsoptimum og må ikke blandes med et
helårstal for samme værk i en differens. Brug månedsløb, når helår ikke løser
(fx Midtfyn), og regn begge sider af en differens på samme måde.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROD = Path(__file__).resolve().parent.parent
JOBFIL = ROD / "deltagere" / "aarsberegning.yaml"
UD = ROD / "deltagere" / "output" / "aarsberegning"

STANDARD = {
    "mip_gap": None,       # None = casens eget gap; differenser kræver 0.0002
    "time_limit": 1800,    # sekunder pr. løb
    "timeout": 3600,       # sekunder pr. løb, før scriptet giver op
}

JOBFIL_HOVED = """\
# Jobfil til scripts/aarsberegning.py. Ligger i deltagere/ og kommer aldrig i git.
#
# Felter pr. job:
#   navn        mappenavn i output (kort, uden mellemrum)
#   case        sti til casefilen
#   heat_csv    sti til målt varmelast (udelad for syntetisk last, fx Andeby)
#   mode        helaar | maaneder
#   ekstra      ekstra argumenter til run_case.py, fx ["--set", "units.fliskedel.initial_status=1"]
#   mip_gap     overskriver det fælles mip_gap for dette job (valgfrit)
#   kontroltal  forventet objektiv i kr (valgfrit); scriptet melder afvigelse over 0,5 %
#
# heat_csv: MANGLER betyder, at der ikke blev fundet en timeserie. Ret stien,
# eller slet linjen, hvis casen skal bruge syntetisk last.
#
# Kendte særtilfælde (instruktion_deltagercases_22okt.md):
#   Hedensted: case deltagere/cases/hedensted_kalibreret.yaml,
#              heat_csv deltagere/data/hedensted_fjernvarme_tilnet_hourly.csv, kontroltal 33759170
#   Aulum:     case og data fra aulum_case.zip (kopieret ind i deltagere/), kontroltal 6888659
#   Midtfyn:   mode maaneder (helår løser ikke i ét løb)
#   Verdo Randers (KVR): kør som helaar. Konverteringen sætter fliskedlerne slukket
#              ved start; det løser fra 1. juli, men et månedsløb, der starter om
#              vinteren, bliver infeasible. Konverteringen giver ingen elproduktion
#              (alpha 0) og startomkostning 0. Vil du regne med kraftvarme, så tilføj
#              fx ekstra: ["--set", "units.k1_flis_kraftvarme.alpha=0.133",
#                          "--set", "units.k2_flis_kraftvarme.alpha=0.133"]
#   Brædstrup: Energinet-tariffen i arket ser ca. 5 gange for høj ud (afventer svar).
#   Vinderup:  konverterer ikke endnu (Biogas står blandt brændselspriserne).
"""


# ---------------------------------------------------------------------------
# Forberedelse: pak casezip'er ud og konvertér regneark
# ---------------------------------------------------------------------------

def _sikker_sti(navn: str) -> bool:
    p = Path(navn)
    return not p.is_absolute() and ".." not in p.parts


def pak_zip_ud(zf_sti: Path) -> set[str]:
    """Pak en casezip ud i deltagere/. Returnér de værksnavne, den dækker.

    To former er kendt: zip'en har selv mappen deltagere/ (Hedensted), eller
    en mappe <navn>_case/ med cases/ og data/ (Aulum). Eksisterende filer
    overskrives ikke.
    """
    import zipfile
    daekker, skrevet, sprunget = set(), 0, 0
    with zipfile.ZipFile(zf_sti) as zf:
        for info in zf.infolist():
            if info.is_dir() or not _sikker_sti(info.filename):
                continue
            dele = Path(info.filename).parts
            if dele[0] == "deltagere" and len(dele) >= 3 and dele[1] in ("cases", "data"):
                maal = ROD.joinpath(*dele)
            elif len(dele) >= 3 and dele[1] in ("cases", "data"):
                maal = ROD / "deltagere" / Path(*dele[1:])
            else:
                continue  # fx LAESMIG.txt
            if dele[-2] == "cases" and maal.suffix == ".yaml":
                daekker.add(maal.stem.split("_")[0].lower())
            if maal.exists():
                sprunget += 1
                continue
            maal.parent.mkdir(parents=True, exist_ok=True)
            maal.write_bytes(zf.read(info))
            skrevet += 1
    print(f"  {zf_sti.name}: {skrevet} filer pakket ud, {sprunget} fandtes allerede "
          f"(dækker: {', '.join(sorted(daekker)) or 'ingen cases'})")
    return daekker


def forbered() -> None:
    mappe = ROD / "deltagere"
    if not mappe.is_dir():
        sys.exit("Mappen deltagere/ findes ikke i repoets rod.")
    print("Casezip'er:")
    daekket: set[str] = set()
    for zf in sorted(mappe.glob("*.zip")):
        daekket |= pak_zip_ud(zf)
    print("\nRegneark:")
    ok, fejl = [], []
    for ark in sorted(mappe.glob("*.xlsx")):
        if ark.name.startswith("~$"):
            continue
        ord_ = {w for w in re.split(r"[^a-zæøå]+", ark.stem.lower()) if w}
        if ord_ & daekket:
            print(f"  {ark.name}: springes over, casezip'en bruges i stedet")
            continue
        p = subprocess.run([sys.executable, "scripts/vaerksark_til_yaml.py",
                            ark.relative_to(ROD).as_posix()],
                           cwd=ROD, capture_output=True, text=True)
        tekst = p.stdout + p.stderr
        if "findes allerede" in tekst:
            print(f"  {ark.name}: allerede konverteret")
            ok.append(ark.name)
        elif p.returncode == 0 and "Skrevet" in tekst:
            print(f"  {ark.name}: konverteret")
            ok.append(ark.name)
        else:
            linjer = [l.strip() for l in tekst.strip().splitlines() if l.strip()]
            print(f"  {ark.name}: KAN IKKE KONVERTERES\n      {linjer[-1] if linjer else ''}")
            fejl.append(ark.name)
        advarsler = [l.strip() for l in tekst.splitlines() if "ADVARSEL" in l]
        for a in advarsler:
            print(f"      {a}")
    print(f"\n{len(ok)} ark klar, {len(fejl)} kan ikke konverteres. "
          f"Næste skridt: python scripts/aarsberegning.py --lav-jobfil")


# ---------------------------------------------------------------------------
# Jobfil
# ---------------------------------------------------------------------------

def lav_jobfil(tving: bool) -> None:
    if JOBFIL.exists() and not tving:
        sys.exit(f"{JOBFIL.relative_to(ROD)} findes allerede. Brug --tving for at overskrive.")
    cases = sorted((ROD / "deltagere" / "cases").glob("*.yaml"))
    if not cases:
        sys.exit("Ingen cases i deltagere/cases/. Kør først "
                 "python scripts/aarsberegning.py --forbered")
    jobs = []
    for c in cases:
        slug = c.stem
        if slug == "hedensted_fjernvarme" and (c.parent / "hedensted_kalibreret.yaml").exists():
            continue  # den rå konvertering; den kalibrerede bruges i stedet
        job = {"navn": slug.replace("_kalibreret", ""), "case": c.relative_to(ROD).as_posix()}
        kandidater = [ROD / "deltagere" / "data" / f"{slug}_abvaerk_hourly.csv"]
        if slug == "hedensted_kalibreret":
            kandidater.insert(0, ROD / "deltagere" / "data" / "hedensted_fjernvarme_tilnet_hourly.csv")
            job["kontroltal"] = 33759170
        if slug == "aulum_fjernvarme":
            job["kontroltal"] = 6888659
        for k in kandidater:
            if k.exists():
                job["heat_csv"] = k.relative_to(ROD).as_posix()
                break
        else:
            job["heat_csv"] = "MANGLER"  # ret stien, eller slet linjen for syntetisk last
        job["mode"] = "maaneder" if "midtfyn" in slug else "helaar"
        job["ekstra"] = []
        jobs.append(job)
    indhold = {**STANDARD, "jobs": jobs}
    JOBFIL.write_text(JOBFIL_HOVED + "\n" + yaml.safe_dump(indhold, allow_unicode=True,
                                                          sort_keys=False), encoding="utf-8")
    print(f"Skrev {JOBFIL.relative_to(ROD)} med {len(jobs)} job:")
    for j in jobs:
        print(f"  {j['navn']:<28} {j['mode']:<9} heat_csv={j['heat_csv']}")
    print("\nTjek filen, før du kører.")


def laes_jobfil() -> dict:
    if not JOBFIL.exists():
        sys.exit(f"{JOBFIL.relative_to(ROD)} findes ikke. Lav den med --lav-jobfil.")
    cfg = yaml.safe_load(JOBFIL.read_text(encoding="utf-8")) or {}
    for k, v in STANDARD.items():
        cfg.setdefault(k, v)
    for j in cfg.get("jobs", []):
        for felt in ("navn", "case"):
            if felt not in j:
                sys.exit(f"Et job i jobfilen mangler feltet '{felt}': {j}")
        if str(j.get("heat_csv", "")).startswith("MANGLER"):
            sys.exit(f"Job {j['navn']}: heat_csv er ikke udfyldt i jobfilen.")
        if j.get("mode", "helaar") not in ("helaar", "maaneder"):
            sys.exit(f"Job {j['navn']}: mode skal være helaar eller maaneder.")
    return cfg


# ---------------------------------------------------------------------------
# Perioder
# ---------------------------------------------------------------------------

def case_periode(case: Path) -> tuple[datetime, datetime]:
    """Casens periode som naive UTC-tidspunkter (time.start/time.end)."""
    raw = yaml.safe_load(case.read_text(encoding="utf-8"))
    t = raw.get("time", {})
    try:
        return tuple(datetime.fromisoformat(str(t[k]).replace("Z", "").split("+")[0])
                     for k in ("start", "end"))
    except (KeyError, ValueError):
        sys.exit(f"{case}: kunne ikke læse time.start/time.end.")


def maaneder(start: datetime, slut: datetime) -> list[tuple[str, str, str]]:
    """Del perioden i kalendermåneder (UTC). Stumper under to døgn i enderne
    lægges til nabomåneden; konverterede cases starter typisk 30/6 kl. 22 UTC,
    som er 1/7 kl. 00 dansk tid."""
    segs, cur = [], start
    while cur <= slut:
        ny = datetime(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        segs.append([f"{cur.year}-{cur.month:02d}", cur, min(slut, ny - timedelta(hours=1))])
        cur = ny
    if len(segs) > 1 and segs[0][2] - segs[0][1] < timedelta(days=2):
        segs[1][1] = segs[0][1]
        segs.pop(0)
    if len(segs) > 1 and segs[-1][2] - segs[-1][1] < timedelta(days=2):
        segs[-2][2] = segs[-1][2]
        segs.pop()
    return [(lab, s.strftime("%Y-%m-%dT%H:%M"), e.strftime("%Y-%m-%dT%H:%M"))
            for lab, s, e in segs]


# ---------------------------------------------------------------------------
# Kørsel
# ---------------------------------------------------------------------------

GAP_RE = re.compile(r"^\s*Gap\s+([0-9.]+)%", re.M)


def koer_et(job: dict, cfg: dict, etiket: str, start: str | None, slut: str | None,
            proeve: bool, forfra: bool) -> dict:
    ud_dir = UD / job["navn"] / etiket
    log = ud_dir / "koersel.log"
    faerdig = ud_dir / "resultat.json"
    if faerdig.exists() and not forfra and not proeve:
        r = json.loads(faerdig.read_text(encoding="utf-8"))
        r["sprunget_over"] = True
        return r

    cmd = [sys.executable, "run_case.py", job["case"], "--data-source", "github"]
    gap = job.get("mip_gap", cfg["mip_gap"])
    if gap is not None:
        cmd += ["--mip-gap", str(gap)]
    cmd += ["--set", f"solver.time_limit={cfg['time_limit']}",
           "--out-dir", ud_dir.relative_to(ROD).as_posix()]
    if job.get("heat_csv"):
        cmd += ["--heat-csv", job["heat_csv"]]
    if start and slut:
        cmd += ["--start", start, "--end", slut]
    cmd += [str(a) for a in job.get("ekstra", [])]

    if proeve:
        print("    " + " ".join(cmd))
        return {}

    ud_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROD, capture_output=True, text=True,
                           timeout=cfg["timeout"])
        tekst, kode = p.stdout + "\n" + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        tekst = (e.stdout or "") if isinstance(e.stdout, str) else ""
        tekst += f"\n[aarsberegning] Afbrudt efter {cfg['timeout']} s."
        kode = -1
    sek = time.time() - t0
    log.write_text(" ".join(cmd) + "\n\n" + tekst, encoding="utf-8")

    r = {"job": job["navn"], "periode": etiket, "start": start or "",
         "slut": slut or "", "sekunder": round(sek),
         "objektiv_dkk": None, "status": "fejl", "gap_pct": None,
         "varmebehov_mwh": None, "produktion_mwh": None, "enheder": {}}
    gaps = GAP_RE.findall(tekst)
    if gaps:
        r["gap_pct"] = float(gaps[-1])
    manifester = sorted(ud_dir.glob("*_manifest.json"))
    if kode == 0 and manifester:
        mf = json.loads(manifester[-1].read_text(encoding="utf-8"))
        r["objektiv_dkk"] = mf["noegletal"]["objektiv_dkk"]
        r["status"] = mf["sporbarhed"]["solve_status"]
        r["varmebehov_mwh"] = mf["noegletal"]["varmeefterspoergsel_mwh"]
        r["produktion_mwh"] = mf["noegletal"]["samlet_produktion_mwh"]
        r["enheder"] = {e["navn"]: round(e["produktion_mwh"], 1) for e in mf["enheder"]}
        r["model_commit"] = mf["sporbarhed"]["model_commit"]
        faerdig.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        sidste = [l for l in tekst.strip().splitlines() if l.strip()][-3:]
        r["fejl"] = " | ".join(sidste)
    return r


def vis(r: dict) -> None:
    if not r:
        return
    if r.get("sprunget_over"):
        print(f"    {r['periode']:<8} allerede regnet: {r['objektiv_dkk']:>14,.0f} kr  ({r['status']})")
        return
    if r["objektiv_dkk"] is None:
        print(f"    {r['periode']:<8} FEJL efter {r['sekunder']} s: {r.get('fejl', '')}")
        return
    gap = f"gap {r['gap_pct']:.3f} %" if r["gap_pct"] is not None else "gap ?"
    print(f"    {r['periode']:<8} {r['objektiv_dkk']:>14,.0f} kr  {r['status']:<14} {gap:<14} {r['sekunder']:>5} s")


# ---------------------------------------------------------------------------
# Oversigt
# ---------------------------------------------------------------------------

def skriv_oversigt(alle: dict[str, list[dict]], jobs: list[dict]) -> None:
    UD.mkdir(parents=True, exist_ok=True)
    rows, md = [], ["# Forhåndsberegnede helår", "",
                    "| Værk | Mode | Objektiv (kr) | Status | Største gap | Løsetid | Kontrol |",
                    "|---|---|---:|---|---:|---:|---|"]
    for job in jobs:
        res = [r for r in alle.get(job["navn"], []) if r]
        if not res:
            continue
        for r in res:
            rows.append({k: r.get(k) for k in ("job", "periode", "start", "slut", "objektiv_dkk",
                                               "status", "gap_pct", "sekunder", "varmebehov_mwh",
                                               "produktion_mwh")})
        ok = [r for r in res if r["objektiv_dkk"] is not None]
        forventet = 1
        if job.get("mode") == "maaneder":
            forventet = len(maaneder(*case_periode(ROD / job["case"])))
        mangler = forventet - len(ok)
        total = sum(r["objektiv_dkk"] for r in ok) if ok else None
        gaps = [r["gap_pct"] for r in ok if r["gap_pct"] is not None]
        statusser = sorted({r["status"] for r in ok})
        kontrol = ""
        if job.get("kontroltal") and total is not None and not mangler:
            afv = (total - job["kontroltal"]) / job["kontroltal"] * 100
            kontrol = f"{'OK' if abs(afv) <= 0.5 else 'AFVIGER'} ({afv:+.2f} %)"
        if mangler:
            kontrol = f"{mangler} af {forventet} løb mangler; summen er ufuldstændig"
        md.append(f"| {job['navn']} | {job.get('mode', 'helaar')} | "
                  f"{total:,.0f} | {', '.join(statusser) or 'fejl'} | "
                  f"{(max(gaps) if gaps else float('nan')):.3f} % | "
                  f"{sum(r['sekunder'] for r in res if 'sekunder' in r) // 60} min | {kontrol} |"
                  if total is not None else
                  f"| {job['navn']} | {job.get('mode', 'helaar')} | – | fejl | – | – | {kontrol} |")
    md += ["", "Månedsløb er summen af tolv uafhængige optimeringer og ligger lidt over et "
           "ægte helårsoptimum. Brug kun differenser regnet på samme måde.",
           "Status 'time_limit' betyder, at solveren stoppede ved tidsgrænsen med den bedste "
           "løsning, den havde; se gappet."]
    with (UD / "oversigt.csv").open("w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
            w.writeheader()
            w.writerows(rows)
    (UD / "oversigt.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n" + "\n".join(md))
    print(f"\nOversigt: {(UD / 'oversigt.md').relative_to(ROD)} og oversigt.csv")


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--forbered", action="store_true",
                    help="Pak casezip'er ud og konvertér regnearkene i deltagere/")
    ap.add_argument("--lav-jobfil", action="store_true", help="Lav deltagere/aarsberegning.yaml")
    ap.add_argument("--tving", action="store_true", help="Overskriv en eksisterende jobfil")
    ap.add_argument("--proeve", action="store_true", help="Vis kommandoerne uden at køre")
    ap.add_argument("--kun", action="append", default=[], help="Kun dette job (kan gentages)")
    ap.add_argument("--maaned", action="append", default=[],
                    help="Kun denne måned i månedsløb, fx 2026-01 (kan gentages)")
    ap.add_argument("--forfra", action="store_true", help="Regn også færdige løb igen")
    a = ap.parse_args()

    if not (ROD / "run_case.py").exists():
        sys.exit("Scriptet skal ligge i scripts/ i fjernvarme-businesscase.")
    if a.forbered:
        forbered()
        return
    if a.lav_jobfil:
        lav_jobfil(a.tving)
        return

    cfg = laes_jobfil()
    jobs = [j for j in cfg["jobs"] if not a.kun or j["navn"] in a.kun]
    if not jobs:
        sys.exit("Ingen job matcher --kun.")
    print(f"mip_gap {cfg['mip_gap'] if cfg['mip_gap'] is not None else 'fra casen'}, tidsgrænse {cfg['time_limit']} s pr. løb\n")

    alle: dict[str, list[dict]] = {}
    for job in jobs:
        case = ROD / job["case"]
        if not case.exists():
            print(f"{job['navn']}: casen findes ikke ({job['case']}), springes over")
            continue
        if job.get("heat_csv") and not (ROD / job["heat_csv"]).exists():
            print(f"{job['navn']}: heat_csv findes ikke ({job['heat_csv']}), springes over")
            continue
        start, slut = case_periode(case)
        mode = job.get("mode", "helaar")
        print(f"{job['navn']}  ({mode}, {start} til {slut})")
        res = []
        if mode == "helaar":
            r = koer_et(job, cfg, "helaar", None, None, a.proeve, a.forfra)
            vis(r)
            res.append(r)
        else:
            for etiket, s, e in maaneder(start, slut):
                if a.maaned and etiket not in a.maaned:
                    continue
                r = koer_et(job, cfg, etiket, s, e, a.proeve, a.forfra)
                vis(r)
                res.append(r)
        alle[job["navn"]] = res
    if not a.proeve:
        # Tag også tidligere færdige måneder med, når --maaned begrænser kørslen
        for job in jobs:
            if job.get("mode") == "maaneder" and job["navn"] in alle:
                fundet = {r["periode"] for r in alle[job["navn"]] if r}
                for f in sorted((UD / job["navn"]).glob("*/resultat.json")):
                    r = json.loads(f.read_text(encoding="utf-8"))
                    if r["periode"] not in fundet:
                        alle[job["navn"]].append(r)
                alle[job["navn"]].sort(key=lambda r: r.get("periode", ""))
        skriv_oversigt(alle, jobs)


if __name__ == "__main__":
    main()
