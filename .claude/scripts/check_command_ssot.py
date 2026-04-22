#!/usr/bin/env python3
"""Check that core commands in spec/commands.yaml are present in key docs."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "spec" / "commands.yaml"
TARGETS = [
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CommandGuide.md",
]


def parse_commands(spec_text: str) -> list[str]:
    cmds: list[str] = []
    for line in spec_text.splitlines():
        m = re.match(r"\s*-\s*name:\s*(/[\w-]+)\s*$", line)
        if m:
            cmds.append(m.group(1))
    return cmds


def main() -> int:
    if not SPEC_PATH.exists():
        print(f"ERROR: missing spec file: {SPEC_PATH}")
        return 2

    commands = parse_commands(SPEC_PATH.read_text(encoding="utf-8"))
    if not commands:
        print("ERROR: no commands parsed from spec/commands.yaml")
        return 2

    errors = 0
    for target in TARGETS:
        if not target.exists():
            print(f"ERROR: missing target file: {target}")
            errors = 1
            continue
        text = target.read_text(encoding="utf-8")
        missing = [cmd for cmd in commands if cmd not in text]
        if missing:
            print(f"ERROR: {target.relative_to(REPO_ROOT)} missing commands:")
            for cmd in missing:
                print(f"  - {cmd}")
            errors = 1

    if errors:
        print()
        print("SSOT command check failed.")
        print("Update the target docs or spec/commands.yaml to keep command vocabulary aligned.")
        return 1

    print("SSOT command check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
