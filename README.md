# crap-score

A [Claude Code](https://claude.com/claude-code) skill that regenerates a Python project's
`METRICS.md` with **CRAP scores** (cyclomatic complexity × test coverage risk) and a static
**test-quality scan** (assertion density, mock usage) — computed by actually running your
test suite under coverage and radon, not guessed.

```
CRAP(m) = complexity(m)^2 * (1 - coverage(m))^3 + complexity(m)
```

A fully-covered function's score collapses to just its complexity, so a high score on a
100%-covered function is a **refactor** signal, while a high score on a low-coverage
function is a **testing-gap** signal. The original [CRAP4J](https://www.softwaretestpro.com/wp-content/uploads/2008/12/attachment.pdf)
tool (Savoia/Evans, ~2007) flags anything scoring above **30** as "needs attention."

The test-quality scan closes a blind spot coverage alone can't see: a test that calls a
function and asserts nothing still counts as full coverage. It statically counts
`assert`/`pytest.raises(...)` per test, flags assertion-free tests individually, and reports
how much of the suite relies on mocking versus exercising real code.

## Install

Claude Code skills can be installed globally (available in every project) or per-project
(bundled into one repo, e.g. so teammates get it just by cloning that repo).

### All projects on this machine

Clone this repo, then symlink it into your Claude Code skills directory:

```bash
git clone https://github.com/foomoon/crap-score.git ~/Documents/Projects/Code/crap-score
ln -s ~/Documents/Projects/Code/crap-score ~/.claude/skills/crap-score
```

Or just clone it directly into `~/.claude/skills/crap-score` if you don't need a separate
copy on disk.

### A single project only

Skills also work project-scoped, at `<project>/.claude/skills/<name>/` — pick one:

**Vendored (simplest, no submodule mechanics, but won't auto-update):**

```bash
git clone https://github.com/foomoon/crap-score.git .claude/skills/crap-score
rm -rf .claude/skills/crap-score/.git
git add .claude/skills/crap-score
```

**Git submodule (stays linked to this repo, teammates run `git submodule update --init`
after cloning):**

```bash
git submodule add https://github.com/foomoon/crap-score.git .claude/skills/crap-score
```

Either way, `/crap-score` is then available in Claude Code sessions started in that project,
without needing the global install above.

## Use

Inside a Claude Code session in any Python project using `pytest` + `pytest-cov` + `radon`:

```
/crap-score
```

Or run it directly, outside of Claude Code:

```bash
python3 ~/.claude/skills/crap-score/scripts/regen_metrics.py [path/to/project]
```

Source dirs, test files, the interpreter, and where `METRICS.md` lives are all
auto-detected from the target project's layout — no config required for a typical
single-package project. See [`SKILL.md`](SKILL.md) for the full auto-detection rules, the
`[tool.crap_score]` `pyproject.toml` override for unusual layouts (monorepos, `src/`
layouts, custom test dirs), and a known limitation around nested Python subprojects.

## Requirements

- Python 3.11+ to run `regen_metrics.py` itself (needs `tomllib` from the standard library).
- The **target project** needs `pytest`, `pytest-cov`, and `radon` installed in its own
  environment — this tool shells out to that project's own interpreter to run them.

## How it works

- `scripts/common.py` — repo-root detection, `pyproject.toml` config loading, and
  auto-detection of source dirs / test files / interpreter.
- `scripts/compute_crap.py` — runs the suite under `pytest-cov`, runs `radon cc`, joins
  per-function coverage against per-function complexity, computes CRAP scores.
- `scripts/test_quality.py` — a static AST scan of every `test_*` function for assertion
  density and mock usage.
- `scripts/regen_metrics.py` — ties the above together and writes the results directly into
  `METRICS.md`'s `<!-- AUTOGEN:... -->`-delimited regions, leaving any hand-written analysis
  around them untouched. Bootstraps a minimal `METRICS.md` if one doesn't exist yet.

Each script is also runnable standalone if you just want the data printed to stdout without
touching a file.

## License

MIT — see [LICENSE](LICENSE).
