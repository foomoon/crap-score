#!/usr/bin/env python3
"""
Regenerates the data-derived sections of a project's METRICS.md in place.

Runs the target project's test suite under coverage once, runs radon, runs
the static test-quality scan, and splices freshly computed markdown into
three marker-delimited regions of METRICS.md:

    <!-- AUTOGEN:SUMMARY:START -->     .. <!-- AUTOGEN:SUMMARY:END -->
    <!-- AUTOGEN:QUALITY:START -->     .. <!-- AUTOGEN:QUALITY:END -->
    <!-- AUTOGEN:CRAP_TABLE:START -->  .. <!-- AUTOGEN:CRAP_TABLE:END -->

Everything outside those markers is left untouched, so hand-written analysis
prose survives regeneration. If METRICS.md doesn't exist yet, a minimal
skeleton is created around those markers.

Source dirs, test paths, the interpreter, and the METRICS.md location are all
auto-detected (see common.py) -- override any of them via a
`[tool.crap_score]` table in the target project's pyproject.toml.

Usage:
    python regen_metrics.py [repo_root]
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import compute_crap
import test_quality

SKELETON = """# Test Metrics

Auto-generated CRAP scores and test-quality signals. Regions marked
`<!-- AUTOGEN:... -->` are rewritten by `regen_metrics.py` on every run --
everything else in this file is yours to edit and will be preserved.

## Suite summary

<!-- AUTOGEN:SUMMARY:START -->
<!-- AUTOGEN:SUMMARY:END -->

## CRAP score methodology

CRAP (Change Risk Analyzer and Predictor) combines cyclomatic complexity and
test coverage into a single per-function risk score:

```
CRAP(m) = complexity(m)^2 * (1 - coverage(m))^3 + complexity(m)
```

A fully-covered function's score collapses to just its complexity -- high
CRAP on a 100%-covered function is a refactor signal, not a testing-gap
signal. The original CRAP4J tool (Savoia/Evans, ~2007) flags any method
scoring **CRAP > 30** as "needs attention"; that's a single binary cutoff,
not a graduated scale. The table below adds an informal 🟡 watch tier below
that cutoff (CRAP > 15) purely as a visual early-warning gradient -- it is
not part of CRAP4J's actual definition.

## Findings

_Add notes here on anything the tables below surface -- functions worth
refactoring, real coverage gaps worth closing, etc. This section is
hand-maintained and untouched by regeneration._

## Test quality

CRAP measures whether a line ran during the suite, not whether anything
checked the result. The scan below counts `assert`/`pytest.raises` signals
per test and flags mock-heavy or assertion-free tests.

<!-- AUTOGEN:QUALITY:START -->
<!-- AUTOGEN:QUALITY:END -->

## Full function/method table

Sorted by CRAP score, descending (highest risk first).

<!-- AUTOGEN:CRAP_TABLE:START -->
<!-- AUTOGEN:CRAP_TABLE:END -->
"""


def build_summary_block(coverage_files: dict, total_tests: int, rows: list) -> str:
    files = sorted(coverage_files)
    total_stmts = sum(coverage_files[p]["summary"]["num_statements"] for p in files)
    total_covered = sum(coverage_files[p]["summary"]["covered_lines"] for p in files)

    lines = [
        f"- **{total_tests} tests**, all passing",
    ]
    if total_stmts:
        lines.append(
            f"- **{100 * total_covered / total_stmts:.1f}% overall line coverage** "
            f"({total_covered} / {total_stmts} statements)"
        )

    emoji, text, worst = compute_crap.overall_rating(rows)
    if worst:
        lines.append(
            f"- **Overall rating: {emoji} {text}** -- highest CRAP score is "
            f"{worst['crap']:.1f} (`{worst['name']}`, {worst['file']}:{worst['lineno']}); "
            f"{len(rows)} gradeable functions/methods total"
        )
    else:
        lines.append(f"- **Overall rating: {emoji} {text}** -- no gradeable functions found")

    lines += ["", "| File | Coverage | Statements |", "|:---|---:|---:|"]
    for p in files:
        s = coverage_files[p]["summary"]
        if s["num_statements"] == 0:
            continue
        lines.append(f"| `{p}` | {s['percent_covered']:.0f}% | {s['num_statements']} |")

    return "\n".join(lines)


def build_quality_block(per_file: dict, all_tests: list) -> str:
    total = len(all_tests)
    if total == 0:
        return "No test functions found."

    total_signals = sum(t["signals"] for t in all_tests)
    zero_signal = [t for t in all_tests if t["signals"] == 0]
    mocked = [t for t in all_tests if t["mocked"]]

    lines = [
        f"**{total} test functions** (distinct `def test_*` -- some may be "
        f"`@pytest.mark.parametrize`d into more cases than this counts), "
        f"**{total_signals} verification signals** "
        f"({total_signals / total:.2f} average per test), "
        f"**{len(zero_signal)} assertion-free tests**. "
        f"**{len(mocked)} tests ({100 * len(mocked) / total:.0f}%) use mocking**; "
        f"the other {total - len(mocked)} exercise real implementation code.",
        "",
        "| File | Tests | Signals | Avg/test | Zero-signal | Mocked |",
        "|:---|---:|---:|---:|---:|---:|",
    ]
    for fname, tests in per_file.items():
        if not tests:
            continue
        n = len(tests)
        sig = sum(t["signals"] for t in tests)
        zero = sum(1 for t in tests if t["signals"] == 0)
        mock_n = sum(1 for t in tests if t["mocked"])
        lines.append(f"| `{fname}` | {n} | {sig} | {sig/n:.2f} | {zero} | {mock_n} ({100*mock_n/n:.0f}%) |")

    return "\n".join(lines)


def build_crap_table(rows: list) -> str:
    if not rows:
        return "No gradeable functions found."
    lines = ["| CRAP | Complexity | Coverage | Risk | Function | File |", "|---:|---:|---:|:---|:---|:---|"]
    for r in rows:
        emoji, text = compute_crap.risk_label(r["crap"])
        lines.append(
            f"| {r['crap']:.1f} | {r['complexity']} | {r['coverage']:.0f}% | {emoji} {text} | "
            f"`{r['name']}` | `{r['file']}:{r['lineno']}` |"
        )
    return "\n".join(lines)


def splice(text: str, marker: str, new_body: str) -> str:
    """Replaces everything between a literal START/END marker pair with new_body,
    reconstructing the surrounding newlines explicitly rather than trying to
    capture them from whatever was there before -- a regex that instead tries
    to capture "the newline before END" breaks the moment START and END ever
    end up on adjacent lines (e.g. a freshly bootstrapped file with nothing
    between them yet), because there's no leftover newline left to capture.
    """
    start_tag = f"<!-- AUTOGEN:{marker}:START -->"
    end_tag = f"<!-- AUTOGEN:{marker}:END -->"
    start_idx = text.find(start_tag)
    end_idx = text.find(end_tag)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise SystemExit(f"error: AUTOGEN:{marker} markers not found or malformed -- refusing to write")
    before = text[:start_idx + len(start_tag)]
    after = text[end_idx:]
    return f"{before}\n{new_body}\n{after}"


def main() -> None:
    repo_root = common.find_repo_root(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())
    config = common.load_config(repo_root)
    python = common.find_python(repo_root, config)
    source_dirs = common.find_source_dirs(repo_root, config)

    with tempfile.TemporaryDirectory() as tmp:
        coverage_json = Path(tmp) / "coverage.json"
        test_count = compute_crap.run_tests_with_coverage(
            repo_root, python, source_dirs, config, coverage_json
        )
        coverage_files = json.loads(coverage_json.read_text())["files"]
        radon_blocks = compute_crap.run_radon(repo_root, python, source_dirs)
        rows = compute_crap.compute_crap_rows(radon_blocks, coverage_files)

    per_file, all_tests = test_quality.gather(repo_root, config)
    metrics_path = common.find_metrics_path(repo_root, config, list(
        (repo_root / f) for f in per_file
    ))

    bootstrapped = not metrics_path.exists()
    original = SKELETON if bootstrapped else metrics_path.read_text()
    text = original
    text = splice(text, "SUMMARY", build_summary_block(coverage_files, test_count, rows))
    text = splice(text, "QUALITY", build_quality_block(per_file, all_tests))
    text = splice(text, "CRAP_TABLE", build_crap_table(rows))

    if text == original and not bootstrapped:
        print(f"{metrics_path}: no changes (already up to date)", file=sys.stderr)
    else:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(text)
        verb = "created" if bootstrapped else "regenerated"
        print(f"{metrics_path}: {verb} ({len(rows)} functions, {len(all_tests)} tests)", file=sys.stderr)


if __name__ == "__main__":
    main()
