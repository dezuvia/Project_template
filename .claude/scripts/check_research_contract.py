#!/usr/bin/env python3
"""Lint shared /research runtime files for project-specific branching."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHARED_RUNTIME_FILES = (
    ".claude/scripts/research_dispatch_artifacts.py",
    ".claude/scripts/research_dispatch_paths.py",
    ".claude/scripts/research_orchestrate.py",
)
PROJECT_SPECIFIC_PATTERNS = (
    (re.compile(r"\bblockade\b", flags=re.IGNORECASE), "project-specific token `blockade` in shared runtime"),
    (re.compile(r"\binvasion\b", flags=re.IGNORECASE), "project-specific token `invasion` in shared runtime"),
    (re.compile(r"\bwargame\b", flags=re.IGNORECASE), "artifact-family token `wargame` in shared runtime"),
    (re.compile(r"\btabletop\b", flags=re.IGNORECASE), "artifact-family token `tabletop` in shared runtime"),
    (re.compile(r"\bfacilitator\b", flags=re.IGNORECASE), "artifact-family token `facilitator` in shared runtime"),
    (re.compile(r"封鎖|登陸|入侵|兵推"), "project-specific Chinese token in shared runtime"),
    (
        re.compile(r'section_id\.startswith\(\s*["\'](?:1\.|2\.)'),
        "section-number semantic branching in shared runtime",
    ),
)


def _normalize_repo_path(path: str | Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError:
            return candidate.as_posix()
    normalized = candidate.as_posix()
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


def _lintable_paths(paths: list[str] | None = None) -> list[Path]:
    normalized = [_normalize_repo_path(path) for path in (paths or list(DEFAULT_SHARED_RUNTIME_FILES))]
    result: list[Path] = []
    for path in normalized:
        candidate = REPO_ROOT / path
        if candidate.exists():
            result.append(candidate)
    return result


def lint_shared_research_contract(paths: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    for path in _lintable_paths(paths):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, reason in PROJECT_SPECIFIC_PATTERNS:
                if pattern.search(line):
                    errors.append(f"{_normalize_repo_path(path)}:{lineno}: {reason}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="optional files to lint; defaults to shared runtime files")
    args = parser.parse_args(argv)
    errors = lint_shared_research_contract(list(args.paths) or None)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
