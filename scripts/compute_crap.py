#!/usr/bin/env python3
"""
Computes CRAP (Change Risk Analyzer and Predictor) scores for every function
and method in a Python project, by joining radon's cyclomatic complexity
output with coverage.py's per-function coverage output.

    CRAP(m) = complexity(m)^2 * (1 - coverage(m))^3 + complexity(m)

Source dirs, the pytest target, and the interpreter are auto-detected (see
common.py); override any of them via a `[tool.crap_score]` table in
pyproject.toml. Requires `pytest`, `pytest-cov`, and `radon` installed in the
target project's environment (not this skill's).

Prints a markdown table sorted by CRAP score (highest risk first) to stdout;
summary stats go to stderr.

Usage:
    python compute_crap.py [repo_root]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# CRAP4J's own flagging threshold (Savoia/Evans, ~2007) -- methods scoring
# above this are marked "needs attention" in the original tool. CRAP4J does
# not define any further official tier below this; it's a binary cutoff, not
# a graduated scale.
CRAP4J_THRESHOLD = 30


def _risk(crap: float) -> str:
    return "Needs attention" if crap > CRAP4J_THRESHOLD else "OK"


def run_tests_with_coverage(repo_root: Path, python: str, source_dirs: list[str],
                             config: dict, coverage_json: Path) -> int:
    """Runs the suite under coverage; returns the number of tests pytest reports passed."""
    cmd = [python, "-m", "pytest", "-q"]
    cmd += config.get("test_paths", [])
    cmd += [f"--cov={d}" for d in source_dirs]
    cmd += [f"--cov-report=json:{coverage_json}"]

    result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    print(result.stdout, file=sys.stderr)
    if result.returncode != 0:
        print("warning: test suite did not pass cleanly; CRAP data may be incomplete", file=sys.stderr)

    m = re.search(r"(\d+) passed", result.stdout)
    if not m:
        raise SystemExit("error: could not parse pytest's test count from its output -- "
                          "the suite may have errored before collecting any tests")
    return int(m.group(1))


def run_radon(repo_root: Path, python: str, source_dirs: list[str]) -> list[dict]:
    cmd = [python, "-m", "radon", "cc", *source_dirs, "-j"]
    out = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=True)
    per_file = json.loads(out.stdout)
    blocks = []
    for path, file_blocks in per_file.items():
        for b in file_blocks:
            b["file"] = path
            blocks.append(b)
    return blocks


def compute_crap_rows(radon_blocks: list[dict], coverage_files: dict) -> list[dict]:
    rows = []
    for b in radon_blocks:
        if b["type"] == "class":
            continue

        path = b["file"]
        file_cov = coverage_files.get(path)
        functions_cov = file_cov["functions"] if file_cov else {}
        file_total_cov = file_cov["summary"]["percent_covered"] if file_cov else None

        if b["type"] == "method":
            key = f"{b['classname']}.{b['name']}"
        else:
            key = b["name"]

        comp = b["complexity"]
        fc = functions_cov.get(key)
        cov_pct = fc["summary"]["percent_covered"] if fc is not None else (file_total_cov or 0.0)

        crap = comp ** 2 * (1 - cov_pct / 100) ** 3 + comp
        rows.append({
            "file": path, "lineno": b["lineno"], "name": key,
            "complexity": comp, "coverage": cov_pct, "crap": crap,
            "matched": fc is not None,
        })

    rows.sort(key=lambda r: -r["crap"])
    return rows


def print_table(rows: list[dict]) -> None:
    print("| CRAP | Complexity | Coverage | Risk | Function | File |")
    print("|---:|---:|---:|:---|:---|:---|")
    for r in rows:
        print(f"| {r['crap']:.1f} | {r['complexity']} | {r['coverage']:.0f}% | "
              f"{_risk(r['crap'])} | `{r['name']}` | `{r['file']}:{r['lineno']}` |")

    unmatched = [r for r in rows if not r["matched"]]
    if unmatched:
        print(f"\n{len(unmatched)} function(s) had no direct coverage.py entry "
              "and fell back to file-level coverage:", file=sys.stderr)
        for r in unmatched:
            print(f"  {r['file']}:{r['lineno']} {r['name']}", file=sys.stderr)

    flagged = sum(1 for r in rows if r["crap"] > CRAP4J_THRESHOLD)
    print(f"\n{len(rows)} gradeable functions/methods: "
          f"{flagged} flagged (CRAP > {CRAP4J_THRESHOLD}).", file=sys.stderr)


def main() -> None:
    repo_root = common.find_repo_root(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())
    config = common.load_config(repo_root)
    python = common.find_python(repo_root, config)
    source_dirs = common.find_source_dirs(repo_root, config)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        coverage_json = Path(tmp) / "coverage.json"
        run_tests_with_coverage(repo_root, python, source_dirs, config, coverage_json)
        coverage_files = json.loads(coverage_json.read_text())["files"]
        radon_blocks = run_radon(repo_root, python, source_dirs)
        rows = compute_crap_rows(radon_blocks, coverage_files)

    print_table(rows)


if __name__ == "__main__":
    main()
