#!/usr/bin/env python3
"""Check architecture SSOT presence and scoped sync requirements."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCH_PATH = REPO_ROOT / "docs" / "architecture.md"
README_PATH = REPO_ROOT / "README.md"
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
GOVERNANCE_REVIEW_PATH = REPO_ROOT / "docs" / "governance-review-contract.md"

REQUIRED_HEADINGS = [
    "## Source of Truth Hierarchy",
    "## System Components",
    "## Runtime Flows",
    "## Human-in-the-Loop Control Points",
    "## Change Protocol and Traceability",
]

ARCHITECTURE_SENSITIVE_EXACT_PATHS = {
    "AGENTS.md",
    "CLAUDE.md",
    "CommandGuide.md",
    "docs/architecture.md",
    "docs/governance-review-contract.md",
    ".claude/agents/scv.md",
    ".claude/commands/scv.md",
    ".claude/scripts/check_architecture_sync.py",
    ".claude/scripts/check_ai_governance_review.py",
    ".claude/scripts/check_governance_layering.py",
    ".claude/scripts/check_scv_contract.py",
    ".claude/scripts/scv_create.py",
    ".claude/scripts/scv_governance.py",
    ".claude/scripts/scv_mcp_server.py",
    ".claude/scripts/scv_mcp_client.py",
    "codex/skills/README.md",
    "codex/skills/MAPPING.md",
    "codex/skills/check_sync.sh",
    "codex/skills/whatodo-scv/SKILL.md",
}
ARCHITECTURE_SENSITIVE_GLOBS = [
    ".claude/scripts/check_*.py",
    "codex/skills/*/SKILL.md",
]


def run_git(args: list[str]) -> list[str]:
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or "unknown git error"
        raise RuntimeError(msg)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def collect_changed_files(base_ref: str | None, staged: bool) -> list[str]:
    if base_ref:
        return run_git(["diff", "--name-only", f"{base_ref}...HEAD"])
    if staged:
        return run_git(["diff", "--cached", "--name-only"])
    changed = run_git(["diff", "--name-only"])
    untracked = run_git(["ls-files", "--others", "--exclude-standard"])
    return sorted(set(changed) | set(untracked))


def is_architecture_sensitive_file(path: str) -> bool:
    if path in ARCHITECTURE_SENSITIVE_EXACT_PATHS:
        return True
    return any(fnmatch.fnmatch(path, pattern) for pattern in ARCHITECTURE_SENSITIVE_GLOBS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref")
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()

    if args.base_ref and args.staged:
        print("ERROR: --base-ref and --staged are mutually exclusive.")
        return 2
    if not ARCH_PATH.exists() or not GOVERNANCE_REVIEW_PATH.exists():
        print("ERROR: missing architecture or governance review contract file.")
        return 2

    errors = 0
    arch_text = ARCH_PATH.read_text(encoding="utf-8")
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in arch_text]
    if missing:
        print("ERROR: docs/architecture.md is missing required sections:")
        for heading in missing:
            print(f"  - {heading}")
        errors = 1

    if "docs/architecture.md" not in README_PATH.read_text(encoding="utf-8"):
        print("ERROR: README.md must reference docs/architecture.md")
        errors = 1
    if "docs/architecture.md" not in AGENTS_PATH.read_text(encoding="utf-8"):
        print("ERROR: AGENTS.md must reference docs/architecture.md")
        errors = 1
    if "## Layer Rules" not in GOVERNANCE_REVIEW_PATH.read_text(encoding="utf-8"):
        print("ERROR: docs/governance-review-contract.md must include layer rules")
        errors = 1

    try:
        changed_files = collect_changed_files(args.base_ref, args.staged)
    except RuntimeError as exc:
        print(f"ERROR: failed to collect git diff: {exc}")
        return 2

    architecture_sensitive = [path for path in changed_files if path != "docs/architecture.md" and is_architecture_sensitive_file(path)]
    if architecture_sensitive and "docs/architecture.md" not in changed_files:
        print("ERROR: architecture-sensitive files changed without docs/architecture.md update:")
        for path in architecture_sensitive:
            print(f"  - {path}")
        errors = 1

    if errors:
        print("\nArchitecture sync check failed.")
        return 1

    print("Architecture sync check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
