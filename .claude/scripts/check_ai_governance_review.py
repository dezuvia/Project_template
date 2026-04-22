#!/usr/bin/env python3
"""Run a token-friendly AI governance review for governance-sensitive changes."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from batch_llm_runner import build_runner_command, select_runner_profile


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROVIDER = "codex"
DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_REAL_CODEX = os.environ.get("CODEX_REAL_BINARY", "")
RULES_PATH = REPO_ROOT / "docs" / "governance-review-contract.md"

GOVERNANCE_SENSITIVE_EXACT_PATHS = {
    "AGENTS.md",
    "CLAUDE.md",
    "docs/architecture.md",
    "docs/governance-review-contract.md",
    ".githooks/pre-commit",
    ".githooks/pre-push",
    ".claude/scripts/check_ai_governance_review.py",
    ".claude/scripts/check_architecture_sync.py",
    ".claude/scripts/check_governance_layering.py",
}

GOVERNANCE_SENSITIVE_GLOBS = [
    ".claude/commands/*.md",
    ".claude/agents/*.md",
    ".claude/scripts/check_*.py",
    "codex/skills/*/SKILL.md",
]

BLOCKING_EXACT_PATHS = {
    "AGENTS.md",
    "CLAUDE.md",
    "docs/architecture.md",
    "docs/governance-review-contract.md",
    ".githooks/pre-commit",
    ".githooks/pre-push",
    ".claude/scripts/check_ai_governance_review.py",
    ".claude/scripts/check_architecture_sync.py",
    ".claude/scripts/check_governance_layering.py",
}

BLOCKING_GLOBS = [
    ".claude/scripts/check_*.py",
]

FINDING_BLOCKING_TYPES = {
    "policy_layer_violation",
    "governance_layering_drift",
    "command_contract_drift",
    "architecture_invariant_risk",
}


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
    return [line.rstrip("\n") for line in proc.stdout.splitlines()]


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
        return [line for line in run_git(["diff", "--name-only", f"{base_ref}...HEAD"]) if line]
    if staged:
        return [line for line in run_git(["diff", "--cached", "--name-only"]) if line]
    changed = [line for line in run_git(["diff", "--name-only"]) if line]
    untracked = [line for line in run_git(["ls-files", "--others", "--exclude-standard"]) if line]
    return sorted(set(changed) | set(untracked))


def is_governance_sensitive_file(path: str) -> bool:
    if path in GOVERNANCE_SENSITIVE_EXACT_PATHS:
        return True
    return any(fnmatch.fnmatch(path, pattern) for pattern in GOVERNANCE_SENSITIVE_GLOBS)


def requires_blocking_gate(paths: list[str]) -> bool:
    for path in paths:
        if path in BLOCKING_EXACT_PATHS:
            return True
        if any(fnmatch.fnmatch(path, pattern) for pattern in BLOCKING_GLOBS):
            return True
    return False


def collect_diff_text(path: str, base_ref: str | None, staged: bool) -> str:
    if base_ref:
        return run_git_text(["diff", "--unified=3", f"{base_ref}...HEAD", "--", path])
    if staged:
        return run_git_text(["diff", "--cached", "--unified=3", "--", path])
    return run_git_text(["diff", "--unified=3", "--", path])


def trim_diff_text(diff_text: str, max_lines: int = 160) -> str:
    lines = diff_text.splitlines()
    if len(lines) <= max_lines:
        return diff_text.strip()
    head = lines[: max_lines // 2]
    tail = lines[-(max_lines // 2) :]
    return "\n".join(head + ["... diff truncated for token discipline ..."] + tail).strip()


def extract_json_object(raw_output: str) -> dict[str, Any]:
    raw_output = raw_output.strip()
    if not raw_output:
        raise RuntimeError("AI governance review returned no output")
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_output, flags=re.DOTALL)
        if not match:
            raise RuntimeError("AI governance review did not return JSON")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise RuntimeError("AI governance review returned a non-object JSON payload")
    return parsed


def validate_ai_payload(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    cleaned_findings: list[dict[str, str]] = []
    for item in findings[:6]:
        if not isinstance(item, dict):
            continue
        cleaned_findings.append(
            {
                "type": str(item.get("type", "")).strip(),
                "severity": str(item.get("severity", "")).strip().lower(),
                "summary": str(item.get("summary", "")).strip(),
                "path": str(item.get("path", "")).strip(),
            }
        )
    return {
        "status": str(payload.get("status", "pass")).strip().lower(),
        "severity": str(payload.get("severity", "none")).strip().lower(),
        "confidence": str(payload.get("confidence", "medium")).strip().lower(),
        "summary": str(payload.get("summary", "")).strip(),
        "findings": cleaned_findings,
    }


def prompt_for_review(
    changed_files: list[str],
    scoped_files: list[str],
    rule_text: str,
    diff_bundle: str,
    review_mode: str,
) -> str:
    return (
        "You are reviewing a project-template governance-sensitive change.\n"
        "Judge only architecture/governance layering and command-contract disruption.\n"
        "Be concise and diff-first. Do not ask for more files unless essential.\n"
        "If the change is ordinary implementation work outside the governance-sensitive scope, mark advisory/pass.\n\n"
        "Return JSON only with this schema:\n"
        "{\n"
        '  "status": "pass|advisory|block",\n'
        '  "severity": "none|advisory|blocking",\n'
        '  "confidence": "low|medium|high",\n'
        '  "summary": "one sentence",\n'
        '  "findings": [\n'
        '    {"type": "policy_layer_violation|governance_layering_drift|command_contract_drift|architecture_invariant_risk|note", '
        '"severity": "advisory|blocking", "path": "repo/path", "summary": "short finding"}\n'
        "  ]\n"
        "}\n\n"
        "Blocking guidance:\n"
        "- Block when policy docs drift into command/runtime procedure.\n"
        "- Block when layer ownership is violated.\n"
        "- Block when touched governance/command surfaces appear to disrupt the documented command contract.\n"
        "- Otherwise prefer advisory or pass.\n\n"
        f"Review mode: {review_mode}\n"
        f"All changed files:\n{json.dumps(changed_files, ensure_ascii=False, indent=2)}\n\n"
        f"Governance-sensitive files:\n{json.dumps(scoped_files, ensure_ascii=False, indent=2)}\n\n"
        f"Compact governance rules:\n{rule_text}\n\n"
        f"Scoped diffs:\n{diff_bundle}\n"
    )


def run_ai_review(
    prompt: str,
    *,
    provider: str,
    model: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    runner_profile = select_runner_profile(provider, model, session_class="analytical")
    cmd = build_runner_command(
        provider=provider,
        root=REPO_ROOT,
        prompt=prompt,
        model=runner_profile.model,
        max_budget=None,
        config_overrides=runner_profile.config_overrides,
    )
    child_env = os.environ.copy()
    output_file: str | None = None
    run_kwargs: dict[str, Any] = {
        "cwd": REPO_ROOT,
        "env": child_env,
        "timeout": timeout_seconds,
        "check": False,
    }
    if provider == "codex":
        if DEFAULT_REAL_CODEX and Path(DEFAULT_REAL_CODEX).exists():
            cmd[0] = DEFAULT_REAL_CODEX
        child_env["CODEX_NOTIFY_DISABLE"] = "1"
        child_env.setdefault("CODEX_NOTIFY_LOG", "/tmp/codex-notify.log")
        child_env.setdefault("CODEX_NOTIFY_STATE_DIR", "/tmp/codex-telegram-notify")
        fd, output_file = tempfile.mkstemp(prefix="governance-review-", suffix=".txt", dir="/tmp")
        os.close(fd)
        exec_index = cmd.index("exec")
        cmd = cmd[: exec_index + 1] + ["--output-last-message", output_file] + cmd[exec_index + 1 :]
        run_kwargs.update(
            {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.PIPE,
                "text": True,
            }
        )
    else:
        run_kwargs.update(
            {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
            }
        )
    result = subprocess.run(cmd, **run_kwargs)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        raise RuntimeError(f"AI governance review failed: {detail}")
    raw_output = result.stdout or ""
    if output_file:
        try:
            raw_output = Path(output_file).read_text(encoding="utf-8")
        finally:
            Path(output_file).unlink(missing_ok=True)
    return validate_ai_payload(extract_json_object(raw_output))


def evaluate_override(payload: dict[str, Any], *, review_mode: str) -> tuple[bool, str]:
    blocking_finding = any(
        finding.get("severity") == "blocking" and finding.get("type") in FINDING_BLOCKING_TYPES
        for finding in payload.get("findings", [])
    )
    blocking_status = payload.get("status") == "block" or payload.get("severity") == "blocking" or blocking_finding
    if review_mode != "blocking" or not blocking_status:
        return True, "AI governance review passed."
    return False, "AI governance review found a blocking governance concern."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", help="Compare changes against this ref.")
    parser.add_argument("--staged", action="store_true", help="Review staged changes only.")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="AI review provider.")
    parser.add_argument("--model", help="Optional AI review model override.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
    args = parser.parse_args()

    if args.base_ref and args.staged:
        print("ERROR: --base-ref and --staged are mutually exclusive.")
        return 2

    try:
        changed_files = [path for path in collect_changed_files(args.base_ref, args.staged) if path]
    except RuntimeError as exc:
        print(f"ERROR: failed to collect git diff: {exc}")
        return 2

    scoped_files = [path for path in changed_files if is_governance_sensitive_file(path)]
    if not scoped_files:
        payload = {
            "status": "pass",
            "severity": "none",
            "confidence": "high",
            "summary": "No governance-sensitive files changed; AI governance review not required.",
            "findings": [],
            "review_mode": "advisory",
            "scoped_files": [],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("AI governance review passed: no governance-sensitive files changed.")
        return 0

    review_mode = "blocking" if requires_blocking_gate(scoped_files) else "advisory"
    rule_text = RULES_PATH.read_text(encoding="utf-8").strip()
    diff_parts: list[str] = []
    for rel_path in scoped_files[:10]:
        diff_text = collect_diff_text(rel_path, args.base_ref, args.staged)
        if diff_text.strip():
            diff_parts.append(trim_diff_text(diff_text))
    diff_bundle = "\n\n".join(diff_parts)
    prompt = prompt_for_review(
        changed_files=changed_files,
        scoped_files=scoped_files,
        rule_text=rule_text,
        diff_bundle=diff_bundle,
        review_mode=review_mode,
    )
    try:
        payload = run_ai_review(
            prompt,
            provider=args.provider.strip().lower(),
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:  # pragma: no cover - exercised indirectly
        print(f"ERROR: {exc}")
        return 2

    payload["review_mode"] = review_mode
    payload["scoped_files"] = scoped_files
    payload["provider"] = args.provider.strip().lower()
    payload["model"] = args.model or ""
    ok, message = evaluate_override(payload, review_mode=review_mode)

    if args.json:
        payload["result_message"] = message
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(message)
        print(f"Summary: {payload.get('summary', '')}")
        for finding in payload.get("findings", []):
            print(
                f"- {finding.get('severity','advisory').upper()} "
                f"{finding.get('type','note')} "
                f"{finding.get('path','')}: {finding.get('summary','')}"
            )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
