#!/usr/bin/env python3
"""
Static test-quality scan for a Python project's test suite.

CRAP scores measure coverage, but coverage is blind to whether a test that
touches a line actually verifies anything -- a test that calls a function and
asserts nothing still counts as "covering" every line it runs. This script
covers the gap by statically analyzing each `test_*` function for:

  - assertion density: `assert` statements and `pytest.raises(...)` blocks
    (an exception check is a verification signal even with no bare `assert`)
  - assertion-free tests: a test with zero of the above is a real smell --
    flagged individually, not just averaged away
  - mock usage: whether a test uses `monkeypatch` or `unittest.mock`
    (Mock/MagicMock/patch) rather than exercising real implementation code

This is purely static (no test execution, no mutation testing) -- it counts
verification *signals*, not whether those signals would actually catch a
regression.

Test files are auto-discovered (see common.py); override via `test_paths` in
a `[tool.crap_score]` pyproject.toml table.

Usage:
    python test_quality.py [repo_root]
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

MOCK_NAMES = {"Mock", "MagicMock", "AsyncMock", "patch", "PropertyMock", "call"}


def _is_raises_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "raises"
    )


def _uses_mock(node: ast.FunctionDef) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == "monkeypatch":
            return True
        if isinstance(n, ast.Name) and n.id in MOCK_NAMES:
            return True
        if isinstance(n, ast.Attribute) and n.attr in MOCK_NAMES:
            return True
    return False


def analyze_function(node: ast.FunctionDef) -> dict:
    asserts = sum(1 for n in ast.walk(node) if isinstance(n, ast.Assert))
    raises = sum(1 for n in ast.walk(node) if _is_raises_call(n))
    return {
        "name": node.name,
        "lineno": node.lineno,
        "asserts": asserts,
        "raises": raises,
        "signals": asserts + raises,
        "mocked": _uses_mock(node),
    }


def analyze_file(path: Path) -> list[dict]:
    tree = ast.parse(path.read_text())
    return [
        analyze_function(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def gather(repo_root: Path, config: dict) -> tuple[dict[str, list[dict]], list[dict]]:
    """Returns (per_file: {relative_path: [test_info, ...]}, all_tests: [test_info, ...])."""
    test_files = common.find_test_files(repo_root, config)
    all_tests = []
    per_file = {}

    for path in test_files:
        tests = analyze_file(path)
        per_file[str(path.relative_to(repo_root))] = tests
        all_tests.extend(tests)

    return per_file, all_tests


def main() -> None:
    repo_root = common.find_repo_root(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())
    config = common.load_config(repo_root)
    per_file, all_tests = gather(repo_root, config)

    total = len(all_tests)
    if total == 0:
        print("No test_* functions found.", file=sys.stderr)
        return

    total_signals = sum(t["signals"] for t in all_tests)
    zero_signal = [t for t in all_tests if t["signals"] == 0]
    mocked = [t for t in all_tests if t["mocked"]]

    print("# Test Quality Scan\n")
    print(f"- **{total} test functions** across {len(per_file)} files (distinct `def test_*`, "
          f"not expanded `@pytest.mark.parametrize` cases)")
    print(f"- **{total_signals} verification signals** (assert + pytest.raises), "
          f"{total_signals / total:.2f} average per test")
    print(f"- **{len(zero_signal)} assertion-free tests** (0 signals -- verify nothing)")
    print(f"- **{len(mocked)} tests use mocking** ({100 * len(mocked) / total:.0f}%), "
          f"**{total - len(mocked)} exercise real implementation code**\n")

    print("## Per-file breakdown\n")
    print("| File | Tests | Signals | Avg/test | Zero-signal | Mocked |")
    print("|:---|---:|---:|---:|---:|---:|")
    for rel, tests in per_file.items():
        if not tests:
            continue
        n = len(tests)
        sig = sum(t["signals"] for t in tests)
        zero = sum(1 for t in tests if t["signals"] == 0)
        mock_n = sum(1 for t in tests if t["mocked"])
        print(f"| `{rel}` | {n} | {sig} | {sig/n:.2f} | {zero} | {mock_n} ({100*mock_n/n:.0f}%) |")

    if zero_signal:
        print("\n## Assertion-free tests (flagged)\n")
        for rel, tests in per_file.items():
            for t in tests:
                if t["signals"] == 0:
                    print(f"- `{rel}:{t['lineno']}` `{t['name']}`")
    else:
        print("\nNo assertion-free tests found.", file=sys.stderr)


if __name__ == "__main__":
    main()
