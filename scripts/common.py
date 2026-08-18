"""
Shared repo-root/config/auto-detection helpers for the crap-score scripts.

No dependency on any specific project layout -- these scripts are meant to be
dropped into any Python project using pytest + coverage.py + radon. Override
any auto-detected value with a `[tool.crap_score]` table in pyproject.toml:

    [tool.crap_score]
    source_dirs = ["src/myapp"]      # dirs to run radon/coverage over
    python = ".venv/bin/python"      # interpreter to run pytest with
    metrics_file = "tests/METRICS.md"
    test_paths = ["tests"]           # explicit pytest target(s); omit to let
                                      # pytest auto-discover from repo root

All keys are optional; anything not set falls back to auto-detection.
"""
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None

# Never descend into these for *any* purpose (source dirs or test discovery).
COMMON_IGNORE_DIR_NAMES = {
    ".venv", "venv", "env", ".git", "node_modules", "dist", "build",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".claude", "site-packages", "egg-info",
}

# Additionally excluded when looking for *source* packages -- these are
# exactly the directories test files (which we don't want radon/coverage
# treating as "source") tend to live in. Must NOT be applied when searching
# for test files themselves.
SOURCE_ONLY_IGNORE_DIR_NAMES = COMMON_IGNORE_DIR_NAMES | {"tests", "test", "docs", "scripts"}


def find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return start.resolve()


def load_config(repo_root: Path) -> dict:
    pyproject = repo_root / "pyproject.toml"
    if not tomllib or not pyproject.exists():
        return {}
    data = tomllib.loads(pyproject.read_text())
    return data.get("tool", {}).get("crap_score", {})


def find_python(repo_root: Path, config: dict) -> str:
    if "python" in config:
        p = repo_root / config["python"]
        return str(p) if p.exists() else config["python"]
    for candidate in [".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe"]:
        p = repo_root / candidate
        if p.exists():
            return str(p)
    return sys.executable


def _has_ignored_component(path: Path, repo_root: Path, ignore: set[str]) -> bool:
    rel = path.relative_to(repo_root)
    return any(part in ignore or part.startswith(".") for part in rel.parts)


def find_source_dirs(repo_root: Path, config: dict) -> list[str]:
    if "source_dirs" in config:
        return list(config["source_dirs"])

    found = []
    for depth1 in sorted(repo_root.iterdir()):
        if not depth1.is_dir() or depth1.name in SOURCE_ONLY_IGNORE_DIR_NAMES or depth1.name.startswith("."):
            continue
        if (depth1 / "__init__.py").exists():
            found.append(depth1)
            continue
        for depth2 in sorted(depth1.iterdir()):
            if not depth2.is_dir() or depth2.name in SOURCE_ONLY_IGNORE_DIR_NAMES:
                continue
            if (depth2 / "__init__.py").exists():
                found.append(depth2)

    if not found:
        # Nothing that looks like a package -- fall back to src/ or repo root
        # itself so the tool still produces *something* rather than erroring.
        src = repo_root / "src"
        found = [src] if src.is_dir() else [repo_root]

    return [str(p.relative_to(repo_root)) for p in found]


def find_test_files(repo_root: Path, config: dict) -> list[Path]:
    if "test_paths" in config:
        roots = [repo_root / p for p in config["test_paths"]]
    else:
        roots = [repo_root]

    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        for pattern in ("test_*.py", "*_test.py"):
            for f in root.rglob(pattern):
                if not _has_ignored_component(f.parent, repo_root, COMMON_IGNORE_DIR_NAMES):
                    files.append(f)
    return sorted(set(files))


def find_metrics_path(repo_root: Path, config: dict, test_files: list[Path]) -> Path:
    if "metrics_file" in config:
        return repo_root / config["metrics_file"]

    if test_files:
        # Most common parent directory among discovered test files.
        parents = [f.parent for f in test_files]
        common = max(set(parents), key=parents.count)
        return common / "METRICS.md"

    return repo_root / "METRICS.md"
