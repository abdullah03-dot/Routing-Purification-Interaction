#!/usr/bin/env python3
"""Rebuild every table, in-text number and figure of the paper from the stored results,
check them, and (optionally) compile the paper and its supplement.

    python reproduce.py            # tables, numbers, figures, checks        (~2 min)
    python reproduce.py --pdf      # ... and compile paper/main.pdf and paper/supplement.pdf
    python reproduce.py --tests    # ... and run the oracle brute-force tests

Run it from anywhere. It reads results_tqe/ and des_validation/results_des/ and overwrites the
generated files in paper/ and figs/. To regenerate the raw results themselves, see README.md.
Works on Linux, macOS and Windows (no shell scripts needed).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DES_FILES = ("des_numbers.tex", "des_extra.tex", "tab_des_regime.tex", "tab_des_designchart.tex",
             "tab_des_routing.tex", "tab_des_gate.tex", "tab_des_six.tex", "tab_des_latency.tex",
             "tab_des_soft.tex", "tab_des_dejmps.tex")


def run(args, cwd=ROOT, quiet=False):
    t0 = time.time()
    label = " ".join("python" if a == PY else a for a in args)
    print(f"--> {label}", flush=True)
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stdout.write(r.stdout[-4000:])
        sys.stderr.write(r.stderr[-4000:])
        sys.exit(f"FAILED: {label} (exit {r.returncode})")
    if not quiet:
        for line in [l for l in r.stdout.splitlines() if l.strip() and not l.startswith(("ok ", "saved "))][-12:]:
            print("    " + line)
    print(f"    done in {time.time() - t0:.0f} s", flush=True)
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", action="store_true", help="also compile the paper and supplement with pdflatex")
    ap.add_argument("--tests", action="store_true", help="also run the oracle brute-force tests")
    a = ap.parse_args()

    for d in ("results_tqe/trials", "des_validation/results_des", "paper", "figs", "code"):
        if not os.path.isdir(os.path.join(ROOT, d)):
            sys.exit(f"missing folder {d}/ -- run this from a complete checkout")

    print("== Monte Carlo study: physics validation, closed form, tables, figures ==")
    run([PY, "code/validate_physics.py"], quiet=True)
    run([PY, "code/design_law.py"])
    run([PY, "code/counterexample.py"], quiet=True)
    run([PY, "code/sensitivity_closed_form.py"])
    run([PY, "code/make_dejmps_tables.py"])
    run([PY, "code/causal_router.py"], quiet=True)
    run([PY, "code/make_tables.py"])
    run([PY, "code/make_figures.py"], quiet=True)

    print("\n== Independent checks of the paper's numbers and universal claims ==")
    out = run([PY, "code/check_numbers.py"], quiet=True)
    tail = [l for l in out.splitlines() if l.strip()][-3:]
    for l in tail:
        print("    " + l)
    if "FAIL" in out:
        sys.exit("FAILED: check_numbers.py reports a failed check")

    print("\n== Discrete-event validation: analysis of the stored full run ==")
    out = run([PY, "des_validation/analyze.py", "--results", "des_validation/results_des"], quiet=True)
    if "WARNING" in out:
        sys.exit("FAILED: des_validation/results_des holds a --quick run; the paper needs the full run")
    last = [l for l in out.splitlines() if "FAIL" in l][-1:]
    print("    " + (last[0] if last else "(no summary line)"))
    if not last or not last[0].rstrip().endswith("0 FAIL"):
        sys.exit("FAILED: des_validation/analyze.py reports failed checks (see results_des/summary.md)")
    run([PY, "des_validation/paper_extra.py", "--results", "des_validation/results_des"], quiet=True)
    rd = os.path.join(ROOT, "des_validation", "results_des")
    for f in DES_FILES:
        shutil.copy2(os.path.join(rd, f), os.path.join(ROOT, "paper", f))
    shutil.copy2(os.path.join(rd, "fig_des_profiles.pdf"), os.path.join(ROOT, "figs", "fig_des_profiles.pdf"))
    print("    copied the DES tables and macros to paper/ and fig_des_profiles.pdf to figs/")

    if a.tests:
        print("\n== Tests: oracles vs brute-force enumeration, Bell-diagonal algebra ==")
        for t in ("test_oracle.py", "test_oracle2.py", "test_belldiag.py", "test_qunet_bd.py"):
            run([PY, t], cwd=os.path.join(ROOT, "code"))

    if a.pdf:
        print("\n== Compile ==")
        if shutil.which("pdflatex") is None:
            sys.exit("pdflatex not found (install TeX Live or MiKTeX, or upload paper/ and figs/ to Overleaf)")
        figs = os.path.join(ROOT, "figs")
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "fig_architecture.tex"], cwd=figs, capture_output=True)
        paper = os.path.join(ROOT, "paper")
        link = os.path.join(paper, "figs")
        if not os.path.exists(link):
            try:
                os.symlink(os.path.join("..", "figs"), link)
            except OSError:          # Windows without symlink rights: copy instead
                shutil.copytree(figs, link)
        # main and supplement cross-reference each other (xr-hyper), so alternate until both resolve
        for doc in ("main", "supplement", "main", "supplement", "main"):
            subprocess.run(["pdflatex", "-interaction=nonstopmode", doc + ".tex"], cwd=paper, capture_output=True)
        nbad = 0
        for doc in ("main", "supplement"):
            log = open(os.path.join(paper, doc + ".log"), encoding="latin-1").read()
            bad = [l for l in log.splitlines() if l.startswith("!") or "Overfull" in l or "undefined" in l]
            nbad += len(bad)
            print(f"    paper/{doc}.pdf written; {len(bad)} errors/overfull/undefined lines in {doc}.log")
            for l in bad[:10]:
                print("    " + l)
        if nbad:
            sys.exit("FAILED: LaTeX errors, overfull boxes or undefined references")

    print("\nAll steps passed.")


if __name__ == "__main__":
    main()
