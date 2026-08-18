---
name: crap-score
description: Regenerates a Python project's METRICS.md (CRAP scores + test-quality scan) in place by running the suite and radon — auto-detects source/test dirs, works on any pytest project, no per-project setup required.
---

Regenerates the data-derived sections of a Python project's `METRICS.md` — CRAP scores
(cyclomatic complexity × test coverage risk) and a static test-quality scan (assertion
density, mock usage). Works on any project using `pytest` + `pytest-cov` + `radon`; source
dirs, test files, the interpreter, and the METRICS.md location are all auto-detected from
the current project's layout.

## Steps

1. Run:
   ```bash
   python3 ~/.claude/skills/crap-score/scripts/regen_metrics.py [repo_root]
   ```
   Omit `repo_root` to auto-detect it from the current working directory (walks upward for
   the nearest `.git` or `pyproject.toml`). This runs the *target project's* test suite
   using *its own* interpreter (auto-detected from `.venv/bin/python` or `venv/bin/python`
   in the target repo — falls back to `sys.executable` if neither exists), so `pytest`,
   `pytest-cov`, and `radon` must already be installed there. This script itself only needs
   Python 3.11+ (for `tomllib`) — it doesn't need those packages in its own environment.

2. If `METRICS.md` doesn't exist yet for this project, it's created with a minimal skeleton
   (title, methodology blurb, an empty "Findings" section for you to fill in, and the three
   `<!-- AUTOGEN:... -->` regions). On later runs, only those marked regions are rewritten —
   everything else (the "Findings" section, any hand-added prose) is preserved.

3. **Auto-detection, and how to override it** if a project's layout is unusual (monorepo,
   non-standard test dir, etc.) — add a `[tool.crap_score]` table to the target project's
   `pyproject.toml`:
   ```toml
   [tool.crap_score]
   source_dirs = ["src/myapp"]      # dirs to run radon/coverage over
   python = ".venv/bin/python"      # interpreter to run pytest with
   metrics_file = "tests/METRICS.md"
   test_paths = ["tests"]           # explicit pytest target(s); omit for pytest's own discovery
   ```
   Without this, source dirs are found by looking for `__init__.py`-containing directories
   one or two levels deep (skipping `tests/`, `.venv/`, `node_modules/`, `build/`, etc.);
   test files are found by recursively globbing `test_*.py`/`*_test.py`; `METRICS.md` defaults
   to living alongside the most common test directory found.

4. **Known limitation**: auto-detection resolves one project root per run — a monorepo with
   a nested Python subproject (e.g. `backend/` with its own `pyproject.toml`, imported via
   `from backend.x import y` rather than self-relative imports, sitting next to a non-Python
   `frontend/`) needs the `[tool.crap_score]` override in the outer `pyproject.toml`
   (there usually isn't one yet — create it) rather than relying on auto-detection to guess
   which directory is "the" project root.

5. Report back concisely: whether the file changed, and if so, what moved (a new function
   crossed the CRAP4J threshold of 30, coverage shifted, assertion-free-test count changed).
   Don't paste the whole file into the conversation — a one- or two-line delta is enough. Use
   `git diff <path-to-METRICS.md>` if the file is tracked, rather than re-deriving the delta
   by eye.

6. Never hand-edit content inside the `<!-- AUTOGEN:... -->` regions — the script owns them
   and will overwrite manual edits on the next run. Edit the "Findings" section and any other
   prose directly; that's yours to maintain.
