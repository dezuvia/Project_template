#!/usr/bin/env python3
"""Enforce layering cleanliness for high-level governance policy docs."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

TARGET_CONFIG = {
    "AGENTS.md": {"max_nonblank_lines": 24},
    "CLAUDE.md": {"max_nonblank_lines": 16},
}

SCRIPT_DETAIL_PATTERNS = (
    re.compile(r"\bpython(?:3)?\b\s"),
    re.compile(r"\bbash\b\s"),
    re.compile(r"\bsh\b\s"),
    re.compile(r"\bcodex\b\s+exec\b"),
)


def run_git(args: list[str]) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or "unknown git error"
        raise RuntimeError(msg)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def run_git_text(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or "unknown git error"
        raise RuntimeError(msg)
    return proc.stdout


def collect_changed_files(base_ref: str | None, staged: bool) -> list[str]:
    if base_ref:
        return run_git(["diff", "--name-only", f"{base_ref}...HEAD"])
    if staged:
        return run_git(["diff", "--cached", "--name-only"])
    changed = run_git(["diff", "--name-only"])
    untracked = run_git(["ls-files", "--others", "--exclude-standard"])
    return sorted(set(changed) | set(untracked))


def collect_diff_text(path: str, base_ref: str | None, staged: bool) -> str:
    if base_ref:
        return run_git_text(["diff", "--unified=0", f"{base_ref}...HEAD", "--", path])
    if staged:
        return run_git_text(["diff", "--cached", "--unified=0", "--", path])
    return run_git_text(["diff", "--unified=0", "--", path])


def parse_touched_new_lines(diff_text: str) -> set[int]:
    touched: set[int] = set()
    for line in diff_text.splitlines():
        if not line.startswith("@@"):
            continue
        match = re.search(r"\+(\d+)(?:,(\d+))?", line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count <= 0:
            continue
        touched.update(range(start, start + count))
    return touched


def iter_sections(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for idx, line in enumerate(lines, start=1):
        if re.match(r"^#{1,3}\s", line):
            if current is not None:
                current["end_line"] = idx - 1
                sections.append(current)
                current = None
            if line.startswith("### "):
                current = {
                    "title": line[4:].strip(),
                    "start_line": idx,
                    "lines": [line],
                }
            continue
        if current is not None:
            current["lines"].append(line)

    if current is not None:
        current["end_line"] = len(lines)
        sections.append(current)

    return sections


def is_command_section(title: str) -> bool:
    return "/" in title


def command_doc_pointer(title: str) -> str | None:
    match = re.search(r"/([a-z][a-z0-9-]*)", title.lower())
    if not match:
        return None
    pointer = f".claude/commands/{match.group(1)}.md"
    return pointer if (REPO_ROOT / pointer).exists() else None


def section_body_lines(section: dict[str, object]) -> list[str]:
    lines = section.get("lines", [])
    return [str(line) for line in lines[1:]]


def has_script_detail(line: str) -> bool:
    if ".claude/scripts/" in line or "codex/skills/check_sync.sh" in line:
        return True
    return any(pattern.search(line) for pattern in SCRIPT_DETAIL_PATTERNS)


def validate_touched_sections(rel_path: str, text: str, touched_lines: set[int]) -> list[str]:
    errors: list[str] = []
    config = TARGET_CONFIG[rel_path]
    max_nonblank_lines = int(config["max_nonblank_lines"])

    for section in iter_sections(text):
        title = str(section["title"])
        start_line = int(section["start_line"])
        end_line = int(section["end_line"])
        if not is_command_section(title):
            continue
        if not any(start_line <= line_no <= end_line for line_no in touched_lines):
            continue

        body = section_body_lines(section)
        nonblank_count = sum(1 for line in body if line.strip())
        if nonblank_count > max_nonblank_lines:
            errors.append(
                f"{rel_path} section '{title}' is too detailed for the policy layer "
                f"({nonblank_count} nonblank lines > {max_nonblank_lines})"
            )

        if any("```" in line for line in body):
            errors.append(
                f"{rel_path} section '{title}' contains a fenced code block; move executable detail to command docs"
            )

        for line in body:
            if has_script_detail(line):
                errors.append(
                    f"{rel_path} section '{title}' contains direct script/runtime invocation detail; "
                    "move it to command or agent docs"
                )
                break

        pointer = command_doc_pointer(title)
        section_text = "\n".join(str(line) for line in section["lines"])
        if pointer and pointer not in section_text:
            errors.append(
                f"{rel_path} section '{title}' must point to {pointer} for detailed execution behavior"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-ref",
        help="Compare policy-layer changes against this ref (uses <ref>...HEAD).",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged policy-layer changes only.",
    )
    args = parser.parse_args()

    if args.base_ref and args.staged:
        print("ERROR: --base-ref and --staged are mutually exclusive.")
        return 2

    try:
        changed_files = collect_changed_files(args.base_ref, args.staged)
    except RuntimeError as exc:
        print(f"ERROR: failed to collect git diff: {exc}")
        return 2

    errors: list[str] = []

    for rel_path in TARGET_CONFIG:
        if rel_path not in changed_files:
            continue
        abs_path = REPO_ROOT / rel_path
        if not abs_path.exists():
            continue

        try:
            diff_text = collect_diff_text(rel_path, args.base_ref, args.staged)
        except RuntimeError as exc:
            print(f"ERROR: failed to collect diff for {rel_path}: {exc}")
            return 2

        touched_lines = parse_touched_new_lines(diff_text)
        if not touched_lines:
            touched_lines = set(range(1, len(abs_path.read_text(encoding="utf-8").splitlines()) + 1))
        text = abs_path.read_text(encoding="utf-8")
        errors.extend(validate_touched_sections(rel_path, text, touched_lines))

    if errors:
        print("Governance layering check failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Governance layering check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
