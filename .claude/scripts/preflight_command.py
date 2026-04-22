#!/usr/bin/env python3
"""Read-only preflight checks for command workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def check_paths(repo_root: Path, rel_paths: list[str]) -> list[str]:
    errors: list[str] = []
    for rel in rel_paths:
        if not (repo_root / rel).exists():
            errors.append(f"missing path: {rel}")
    return errors


def run_preflight(repo_root: Path, command: str, source: str, active_doc_id: str) -> dict[str, object]:
    del source, active_doc_id
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    if command == "/scv":
        errors.extend(
            check_paths(
                repo_root,
                [
                    "docs/architecture.md",
                    "docs/governance-review-contract.md",
                    "AGENTS.md",
                    "CLAUDE.md",
                    ".claude/agents/scv.md",
                    ".claude/commands/scv.md",
                    ".claude/scripts/scv_create.py",
                    ".claude/scripts/scv_governance.py",
                    ".claude/scripts/scv_mcp_server.py",
                    ".claude/scripts/scv_mcp_client.py",
                    ".claude/scripts/check_scv_contract.py",
                ],
            )
        )

    return {"ok": not errors, "command": command, "errors": errors, "warnings": warnings, "info": info}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True, choices=["/scv"])
    parser.add_argument("--source", default="")
    parser.add_argument("--active-doc-id", default="")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    result = run_preflight(repo_root, args.command, args.source, args.active_doc_id)
    if result["ok"]:
        print(f"[PASS] preflight {args.command}")
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
