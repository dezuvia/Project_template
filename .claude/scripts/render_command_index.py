#!/usr/bin/env python3
"""Render CommandGuide quick-reference table from spec/commands.yaml."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "spec" / "commands.yaml"
GUIDE_PATH = REPO_ROOT / "CommandGuide.md"
START_MARK = "<!-- BEGIN:COMMAND_INDEX -->"
END_MARK = "<!-- END:COMMAND_INDEX -->"


def parse_spec(text: str) -> list[dict[str, object]]:
    commands: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    in_aliases = False

    for raw in text.splitlines():
        line = raw.rstrip()

        m_name = re.match(r"^\s*-\s*name:\s*(/[\w-]+)\s*$", line)
        if m_name:
            current = {
                "name": m_name.group(1),
                "category": "",
                "purpose": "",
                "aliases": [],
            }
            commands.append(current)
            in_aliases = False
            continue

        if current is None:
            continue

        m_category = re.match(r"^\s*category:\s*([a-z-]+)\s*$", line)
        if m_category:
            current["category"] = m_category.group(1)
            in_aliases = False
            continue

        m_purpose = re.match(r"^\s*purpose:\s*(.+)\s*$", line)
        if m_purpose:
            current["purpose"] = m_purpose.group(1).strip()
            in_aliases = False
            continue

        if re.match(r"^\s*aliases:\s*\[\]\s*$", line):
            current["aliases"] = []
            in_aliases = False
            continue

        if re.match(r"^\s*aliases:\s*$", line):
            current["aliases"] = []
            in_aliases = True
            continue

        m_alias = re.match(r"^\s*-\s*(/[\w-]+)\s*$", line)
        if in_aliases and m_alias:
            aliases = current["aliases"]
            assert isinstance(aliases, list)
            aliases.append(m_alias.group(1))
            continue

        if re.match(r"^\s*[a-z_]+:\s*", line):
            in_aliases = False

    return commands


def render_block(commands: list[dict[str, object]]) -> str:
    lines = [
        START_MARK,
        "",
        "| Command | Purpose | Category |",
        "|---|---|---|",
    ]
    for cmd in commands:
        name = str(cmd["name"])
        purpose = str(cmd["purpose"])
        category = str(cmd["category"])
        aliases = cmd["aliases"]
        alias_suffix = ""
        if isinstance(aliases, list) and aliases:
            alias_suffix = " (aliases: " + ", ".join(f"`{a}`" for a in aliases) + ")"
        lines.append(f"| `{name}`{alias_suffix} | {purpose} | {category} |")

    lines.append("")
    lines.append(END_MARK)
    return "\n".join(lines)


def replace_block(guide_text: str, block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(START_MARK)}.*?{re.escape(END_MARK)}",
        re.DOTALL,
    )
    if not pattern.search(guide_text):
        raise ValueError("CommandGuide.md missing command index markers.")
    return pattern.sub(block, guide_text, count=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check only; do not write.")
    args = parser.parse_args()

    if not SPEC_PATH.exists():
        print(f"ERROR: missing spec file: {SPEC_PATH}")
        return 2
    if not GUIDE_PATH.exists():
        print(f"ERROR: missing CommandGuide: {GUIDE_PATH}")
        return 2

    commands = parse_spec(SPEC_PATH.read_text(encoding="utf-8"))
    if not commands:
        print("ERROR: failed to parse commands from spec/commands.yaml")
        return 2

    block = render_block(commands)
    current = GUIDE_PATH.read_text(encoding="utf-8")
    updated = replace_block(current, block)

    if args.check:
        if current != updated:
            print("ERROR: CommandGuide quick reference is out of sync.")
            print("Run: python3 .claude/scripts/render_command_index.py")
            return 1
        print("CommandGuide command index is in sync.")
        return 0

    GUIDE_PATH.write_text(updated, encoding="utf-8")
    print("Rendered CommandGuide command index from spec/commands.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
