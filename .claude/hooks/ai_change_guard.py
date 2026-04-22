#!/usr/bin/env python3
"""Block direct file edits outside a real git repository for ai-change flows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ALLOWED_NON_GIT_PREFIX = ".claude/ai_change_runs/"
DENY_REASON = (
    "State-changing edits require a real git repository because `/ai-change` now uses "
    "git branches and local branch-diff review bundles as the primary review boundary. Move this "
    "work to the actual repo root or clone before editing files."
)


def _git_repo_present(project_dir: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _collect_candidate_paths(tool_input: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    paths_value = tool_input.get("paths")
    if isinstance(paths_value, list):
        for item in paths_value:
            if isinstance(item, str) and item.strip():
                candidates.append(item.strip())
    return candidates


def _normalize_to_repo(project_dir: Path, candidate: str) -> str | None:
    path = Path(candidate)
    if not path.is_absolute():
        path = project_dir / path
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return None


def _allow_non_git_artifacts(project_dir: Path, tool_input: dict[str, Any]) -> bool:
    candidates = _collect_candidate_paths(tool_input)
    if not candidates:
        return False
    normalized = [_normalize_to_repo(project_dir, candidate) for candidate in candidates]
    if any(item is None for item in normalized):
        return False
    return all(str(item).startswith(ALLOWED_NON_GIT_PREFIX) for item in normalized)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"invalid hook input: {exc}", file=sys.stderr)
        return 1

    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    if payload.get("tool_name") not in {"Write", "Edit", "MultiEdit"}:
        return 0

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        tool_input = {}

    if _git_repo_present(project_dir) or _allow_non_git_artifacts(project_dir, tool_input):
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": DENY_REASON,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
