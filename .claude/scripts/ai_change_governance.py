#!/usr/bin/env python3
"""Git/local-review AI-assisted change governance for this workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_architecture_sync
from batch_llm_runner import (
    CODEX_CHILD_NETWORK_ALLOWED_ENV,
    build_runner_command,
    build_runner_env,
    codex_child_network_allowed,
    codex_child_network_blocked,
    codex_child_network_failure_reason,
    select_runner_profile,
    verify_provider_cli,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = Path(".claude/ai_change_runs")
BASE_READ_SURFACE = (
    "docs/coder_guide.md",
    "docs/ai_change_governance.md",
    "docs/architecture.md",
)
ARCHITECTURE_SYNC_DOCS = {
    "docs/architecture.md",
}
GOVERNANCE_SURFACES = {
    "AGENTS.md",
    "CLAUDE.md",
    "docs/coder_guide.md",
    "docs/architecture.md",
    "docs/ai_change_governance.md",
}
WORKFLOW_SURFACES = {
    ".claude/commands/",
    ".claude/scripts/",
    "docs/systemdesign/architect_ai_change/",
}
TEST_COMMANDS = {
    "ai_change_governance": ["python3", "-m", "unittest", "tests.test_ai_change_governance"],
    "ai_change_flow": ["python3", "-m", "unittest", "tests.test_ai_change_pr_flow"],
    "ai_change_hook_guard": ["python3", "-m", "unittest", "tests.test_ai_change_hook_guard"],
    "review_cycle": ["python3", "-m", "unittest", "tests.test_review_cycle_repairs"],
}
DEFAULT_WORKFLOW_MODE = "git_local_review"
DEFAULT_REVIEW_TRANSPORT = "local_branch_diff"
DEFAULT_LOCAL_GOVERNANCE_ROLE = "primary_review_and_checks"
HOOK_SETTINGS_PATH = ".claude/settings.json"
HOOK_GUARD_PATH = ".claude/hooks/ai_change_guard.py"
GIT_PUSH_GUARD_PATH = ".githooks/pre-push"
EXPECTED_GIT_HOOKS_PATH = ".githooks"
PROTECTED_BRANCH = "main"
DEFAULT_BRANCH_PREFIX = "ai-change/"
DEFAULT_REVIEW_STATE = "deferred_until_ready"
DEFAULT_CHECKPOINT_MODE = "staged_only"
DEFAULT_EXECUTION_MODE = "manual"
DEFAULT_AUTOPILOT_MAX_REVIEW_CYCLES = 3
DEFAULT_AUTOPILOT_NEXT_ACTION = "implement_then_checkpoint"
DEFAULT_INDEPENDENT_REVIEW_PROVIDER = "codex"
INDEPENDENT_REVIEW_PROMPT_VERSION = "ai-change-independent-review-v1"
UNKNOWN_REVIEW_IDENTITY = "unknown"
AI_CHANGE_IMPLEMENTER_ID_ENV = "AI_CHANGE_IMPLEMENTER_ID"
AI_CHANGE_IMPLEMENTER_SESSION_ID_ENV = "AI_CHANGE_IMPLEMENTER_SESSION_ID"
AI_CHANGE_REVIEWER_ID_ENV = "AI_CHANGE_REVIEWER_ID"
AI_CHANGE_REVIEWER_SESSION_ID_ENV = "AI_CHANGE_REVIEWER_SESSION_ID"
INDEPENDENT_REVIEW_BASE_ASSESSMENT_FIELDS = (
    "contract_sufficiency_assessment",
    "overfitting_assessment",
    "policy_substitution_assessment",
)
INDEPENDENT_REVIEW_HIGH_RISK_ASSESSMENT_FIELDS = (
    "high_risk_assessment",
    "architecture_sync_assessment",
)
LEGACY_WORKFLOW_MODE = "git_pr_assisted"
LEGACY_REVIEW_TRANSPORT = "github_pull_request"
LEGACY_LOCAL_GOVERNANCE_ROLE = "pre_pr_policy_and_checks"
VALID_REVIEW_RESULTS = {
    "pending_ready_transition",
    "pending_local_review",
    "approved",
    "approved_with_advisories",
    "changes_requested",
}
VALID_REVIEW_NEXT_ACTIONS = {
    "mark_ready_for_review",
    "conduct_local_review",
    "human_merge_judgment",
    "fix_blocking_findings",
}
VALID_ACCEPTANCE_EVIDENCE_STATUSES = {
    "pass",
    "fail",
    "missing",
}
VALID_ACCEPTANCE_MODES = {
    "scoped",
    "strict",
}
DEFAULT_ACCEPTANCE_MODE = "scoped"
DEFAULT_SCOPED_ACCEPTANCE_NOTES = (
    "Changed docs should be synchronized when command/runtime behavior changed.",
    "No stale approval may be carried across a different head commit.",
)
ACCEPTANCE_SECTION_KEYWORDS = (
    "acceptance criteria",
    "exit criteria",
    "validation",
    "evaluation",
    "comparison",
    "comparator",
)
ACCEPTANCE_COMMAND_PREFIXES = (
    "python",
    "python3",
    "pytest",
    "bash",
    "sh",
    "node",
    "npm",
    "pnpm",
    "yarn",
    "uv",
    "cargo",
    "go",
    "git",
    "make",
    "./",
)
REPO_PATH_SUFFIXES = (
    ".md",
    ".json",
    ".txt",
    ".py",
    ".yaml",
    ".yml",
    ".sh",
)
DEFAULT_READ_SURFACE_FOCUS_LIMIT = 8
REVIEW_RULE_SOURCES = {
    "docs/coder_guide.md",
    "docs/ai_change_governance.md",
    "docs/architecture.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/commands/ai-change.md",
}
GENERAL_REVIEW_SCOPE = "general_code_review"
RELATED_CONTEXT_POLICY = "bounded_related_context"
SUBCOMMANDS = {
    "autopilot",
    "independent-review",
    "start-run",
    "checkpoint",
    "prepare-pr",
    "review-feedback",
    "ready-for-review",
    "status",
}


@dataclass
class CheckResult:
    name: str
    status: str
    details: list[str]
    command: str | None = None


@dataclass
class GitContext:
    available: bool
    repo_root: str | None
    current_branch: str | None
    detached_head: bool
    remotes: list[str]
    has_origin_remote: bool
    hooks_path: str | None
    local_push_guard_present: bool
    local_push_guard_installed: bool
    reason: str | None = None


@dataclass
class GovernanceReport:
    paths: list[str]
    tags: list[str]
    risk_tier: str
    review_policy: str
    review_transport: str
    local_governance_role: str
    review_scope: str
    context_policy: str
    domain_overlays: list[str]
    read_surface: list[str]
    hard_requirements: list[str]
    advisory_notes: list[str]
    validation_commands: list[str]
    verification_expectations: list[str]
    acceptance_sources: list[str]
    acceptance_mode: str
    acceptance_scope_file: str | None
    acceptance_requirements: list[dict[str, Any]]
    scoped_acceptance_requirements: list[dict[str, Any]]
    scoped_acceptance_notes: list[str]
    acceptance_inventory_requirements: list[dict[str, Any]]
    acceptance_inventory_count: int
    acceptance_inventory_unscoped_count: int
    acceptance_context_only_requirement_ids: list[str]
    required_acceptance_artifacts: list[str]
    acceptance_inventory_artifacts: list[str]
    approval_blocking_policy: str | None
    review_brief: str
    audit_brief: str | None
    checks: list[CheckResult]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _has_prefix(path: str, prefixes: set[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def _runs_root() -> Path:
    return REPO_ROOT / RUNS_ROOT


def _run_dir(run_id: str) -> Path:
    return _runs_root() / run_id


def _run_manifest_path(run_id: str) -> Path:
    return _run_dir(run_id) / "run_manifest.json"


def _review_manifest_path(run_id: str) -> Path:
    return _run_dir(run_id) / "review_manifest.json"


def _review_bundle_path(run_id: str) -> Path:
    return _run_dir(run_id) / "review_bundle.md"


def _legacy_pr_manifest_path(run_id: str) -> Path:
    return _run_dir(run_id) / "pull_request_manifest.json"


def _legacy_pr_body_path(run_id: str) -> Path:
    return _run_dir(run_id) / "pull_request.md"


def _review_feedback_path(run_id: str) -> Path:
    return _run_dir(run_id) / "review_feedback.json"


def _review_feedback_body_path(run_id: str) -> Path:
    return _run_dir(run_id) / "review_feedback.md"


def _independent_review_path(run_id: str) -> Path:
    return _run_dir(run_id) / "independent_review.json"


def _independent_review_body_path(run_id: str) -> Path:
    return _run_dir(run_id) / "independent_review.md"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    _ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _existing_path(*candidates: Path) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _normalize_paths(paths: list[str]) -> list[str]:
    normalized = [_normalize_repo_path(path) for path in paths if str(path).strip()]
    return sorted(dict.fromkeys(normalized))


def _normalized_review_state(raw_state: object) -> str:
    state = str(raw_state or "").strip()
    if state == "ready_for_review":
        return "ready_for_review"
    return DEFAULT_REVIEW_STATE


def _normalize_review_result(raw_result: object) -> str:
    candidate = str(raw_result or "").strip()
    return candidate if candidate in VALID_REVIEW_RESULTS else ""


def _normalize_review_next_action(raw_action: object) -> str:
    candidate = str(raw_action or "").strip()
    return candidate if candidate in VALID_REVIEW_NEXT_ACTIONS else ""


def _normalize_identity(raw_value: object, *, env_name: str | None = None) -> str:
    candidate = str(raw_value or "").strip()
    if not candidate and env_name:
        candidate = os.getenv(env_name, "").strip()
    return candidate or UNKNOWN_REVIEW_IDENTITY


def _identity_known(value: object) -> bool:
    return str(value or "").strip() not in {"", UNKNOWN_REVIEW_IDENTITY}


def _same_known_identity(left: object, right: object) -> bool:
    return _identity_known(left) and str(left).strip() == str(right or "").strip()


def _same_known_session(left: object, right: object) -> bool:
    return _same_known_identity(left, right)


def _review_feedback_next_action(review_result: str) -> str:
    if review_result == "pending_ready_transition":
        return "mark_ready_for_review"
    if review_result == "changes_requested":
        return "fix_blocking_findings"
    if review_result in {"approved", "approved_with_advisories"}:
        return "human_merge_judgment"
    return "conduct_local_review"


def _coerce_optional_non_negative_int(value: object, *, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{field_name}` must be a non-negative integer") from exc
    if normalized < 0:
        raise ValueError(f"`{field_name}` must be a non-negative integer")
    return normalized


def _resolve_acceptance_sources(raw_sources: list[str] | None) -> list[str]:
    normalized = _normalize_paths(list(raw_sources or []))
    for path in normalized:
        candidate = REPO_ROOT / path
        if not candidate.exists():
            raise ValueError(f"acceptance source `{path}` does not exist")
        if not candidate.is_file():
            raise ValueError(f"acceptance source `{path}` must be a file")
    return normalized


def _normalize_acceptance_mode(raw_mode: object) -> str:
    mode = str(raw_mode or DEFAULT_ACCEPTANCE_MODE).strip().lower()
    if mode not in VALID_ACCEPTANCE_MODES:
        raise ValueError("`acceptance_mode` must be one of: " + ", ".join(sorted(VALID_ACCEPTANCE_MODES)))
    return mode


def _resolve_acceptance_scope_file(raw_path: str | None) -> str | None:
    if not raw_path:
        return None
    normalized = _normalize_repo_path(raw_path)
    candidate = REPO_ROOT / normalized
    if not candidate.exists():
        raise ValueError(f"acceptance scope file `{normalized}` does not exist")
    if not candidate.is_file():
        raise ValueError(f"acceptance scope file `{normalized}` must be a file")
    return normalized


def _acceptance_heading_title(raw_title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^[0-9.]+\s*", "", raw_title.strip())).strip()


def _acceptance_section_match(title: str) -> bool:
    normalized = _acceptance_heading_title(title).lower()
    return any(keyword in normalized for keyword in ACCEPTANCE_SECTION_KEYWORDS)


def _looks_like_repo_path(token: str) -> bool:
    stripped = token.strip()
    if not stripped or "\n" in stripped or stripped.startswith(("http://", "https://")):
        return False
    if " " in stripped:
        return False
    if stripped.startswith(("/", "../")):
        return False
    return "/" in stripped or stripped.endswith(REPO_PATH_SUFFIXES)


def _looks_like_command(token: str) -> bool:
    stripped = token.strip()
    if not stripped or "\n" in stripped:
        return False
    first = stripped.split()[0]
    return first.startswith("./") or first in ACCEPTANCE_COMMAND_PREFIXES


def _requirement_kind(source_section: str) -> str:
    normalized = _acceptance_heading_title(source_section).lower()
    if "acceptance criteria" in normalized:
        return "acceptance_criteria"
    if "exit criteria" in normalized:
        return "exit_criteria"
    if "validation" in normalized:
        return "validation"
    if "comparison" in normalized or "comparator" in normalized:
        return "comparison"
    if "evaluation" in normalized:
        return "evaluation"
    return "acceptance_evidence"


def _classify_acceptance_evidence_type(
    requirement_text: str,
    source_section: str,
    command_text: str | None,
    required_artifact_paths: list[str],
) -> str:
    normalized = f"{source_section} {requirement_text}".lower()
    if command_text:
        return "command"
    if "comparator" in normalized or "compare" in normalized:
        return "comparator"
    if "review" in normalized or "audit" in normalized or "sufficiency" in normalized:
        return "review"
    if "smoke" in normalized or "sample run" in normalized or "real run" in normalized:
        return "run"
    if required_artifact_paths:
        return "artifact"
    return "assertion"


def _extract_acceptance_requirements(source_path: str) -> list[dict[str, Any]]:
    source_file = REPO_ROOT / source_path
    text = source_file.read_text(encoding="utf-8")
    heading_stack: list[tuple[int, str]] = []
    current_section: str | None = None
    current_item: list[str] = []
    collected: list[tuple[str, str]] = []

    def flush_current() -> None:
        nonlocal current_section, current_item
        if current_section and current_item:
            item_text = " ".join(part.strip() for part in current_item if part.strip()).strip()
            if item_text:
                collected.append((current_section, item_text))
        current_section = None
        current_item = []

    for raw_line in text.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.*\S)\s*$", raw_line)
        if heading_match:
            flush_current()
            level = len(heading_match.group(1))
            title = _acceptance_heading_title(heading_match.group(2))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue

        active_headings = [title for _, title in heading_stack if _acceptance_section_match(title)]
        if not active_headings:
            flush_current()
            continue

        bullet_match = re.match(r"^\s*[-*]\s+(.*\S)\s*$", raw_line)
        if bullet_match:
            flush_current()
            current_section = heading_stack[-1][1]
            current_item = [bullet_match.group(1).strip()]
            continue

        if current_item:
            stripped = raw_line.strip()
            if stripped:
                current_item.append(stripped)
            else:
                flush_current()

    flush_current()

    seen: set[tuple[str, str]] = set()
    requirements: list[dict[str, Any]] = []
    source_slug = _slugify(source_path.replace("/", "-"))
    for index, (source_section, item_text) in enumerate(collected, start=1):
        dedupe_key = (source_section, item_text)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        backtick_tokens = [match.strip() for match in re.findall(r"`([^`]+)`", item_text) if match.strip()]
        command_text = next((token for token in backtick_tokens if _looks_like_command(token)), None)
        required_artifact_paths = _normalize_paths(
            [token for token in backtick_tokens if _looks_like_repo_path(token)]
        )
        normalized_text = f"{source_section} {item_text}".lower()
        comparator_basis = None
        if "comparator" in normalized_text or "compare" in normalized_text or "gold" in normalized_text:
            comparator_basis = next(iter(required_artifact_paths), None)

        requirements.append(
            {
                "requirement_id": f"{source_slug}-{index:02d}",
                "acceptance_source": source_path,
                "source_section": source_section,
                "requirement_kind": _requirement_kind(source_section),
                "evidence_type": _classify_acceptance_evidence_type(
                    item_text,
                    source_section,
                    command_text,
                    required_artifact_paths,
                ),
                "requirement_text": item_text,
                "command_text": command_text,
                "required_artifact_paths": required_artifact_paths,
                "comparator_basis": comparator_basis,
                "approval_blocking": True,
            }
        )
    return requirements


def _collect_acceptance_requirements(acceptance_sources: list[str]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for source_path in acceptance_sources:
        requirements.extend(_extract_acceptance_requirements(source_path))
    return requirements


def _requirement_with_blocking(
    requirement: dict[str, Any],
    approval_blocking: bool,
    *,
    scope_source: str | None = None,
) -> dict[str, Any]:
    normalized = dict(requirement)
    normalized["approval_blocking"] = approval_blocking
    normalized["context_only"] = not approval_blocking
    if scope_source:
        normalized["scope_source"] = scope_source
    return normalized


def _scoped_requirement_from_item(scope_file: str, item: dict[str, Any], index: int) -> dict[str, Any]:
    requirement_text = str(item.get("requirement_text") or item.get("text") or "").strip()
    if not requirement_text:
        raise ValueError(f"scoped acceptance requirement #{index} in `{scope_file}` is missing `requirement_text`")
    requirement_id = str(item.get("requirement_id") or "").strip()
    if not requirement_id:
        requirement_id = f"{_slugify(scope_file.replace('/', '-'))}-scoped-{index:02d}"
    required_artifact_paths = _normalize_paths(list(item.get("required_artifact_paths") or []))
    command_text = str(item.get("command_text") or "").strip() or None
    comparator_basis = str(item.get("comparator_basis") or "").strip() or None
    return {
        "requirement_id": requirement_id,
        "acceptance_source": scope_file,
        "source_section": str(item.get("source_section") or "Acceptance Scope").strip(),
        "requirement_kind": str(item.get("requirement_kind") or "acceptance_evidence").strip(),
        "evidence_type": str(item.get("evidence_type") or "assertion").strip(),
        "requirement_text": requirement_text,
        "command_text": command_text,
        "required_artifact_paths": required_artifact_paths,
        "comparator_basis": comparator_basis,
        "approval_blocking": True,
        "context_only": False,
        "scope_source": scope_file,
    }


def _load_acceptance_scope_payload(scope_file: str) -> tuple[list[str], list[dict[str, Any]]]:
    text = (REPO_ROOT / scope_file).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        requirement_items = [
            {"requirement_text": match.group(1).strip()}
            for line in text.splitlines()
            if (match := re.match(r"^\s*[-*]\s+(.*\S)\s*$", line))
        ]
        return ([], requirement_items)

    requirement_ids: list[str] = []
    requirement_items: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        raw_ids = (
            payload.get("requirement_ids")
            or payload.get("scoped_requirement_ids")
            or payload.get("approval_blocking_requirement_ids")
            or []
        )
        if not isinstance(raw_ids, list):
            raise ValueError("acceptance scope file `requirement_ids` must be a list")
        requirement_ids = [str(item).strip() for item in raw_ids if str(item).strip()]
        raw_requirements = payload.get("requirements") or payload.get("checklist") or []
        if not isinstance(raw_requirements, list):
            raise ValueError("acceptance scope file `requirements` must be a list")
        requirement_items = [item for item in raw_requirements if isinstance(item, dict)]
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                requirement_ids.append(item.strip())
            elif isinstance(item, dict):
                requirement_items.append(item)
            else:
                raise ValueError("acceptance scope file list entries must be strings or objects")
    else:
        raise ValueError("acceptance scope file must contain a JSON object/list or markdown bullets")
    return (requirement_ids, requirement_items)


def _scoped_requirements_from_scope_file(
    inventory_requirements: list[dict[str, Any]],
    scope_file: str,
) -> list[dict[str, Any]]:
    requirement_ids, requirement_items = _load_acceptance_scope_payload(scope_file)
    inventory_by_id = {
        str(requirement.get("requirement_id") or ""): requirement
        for requirement in inventory_requirements
    }
    scoped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for requirement_id in requirement_ids:
        if requirement_id not in inventory_by_id:
            raise ValueError(f"acceptance scope file `{scope_file}` references unknown requirement `{requirement_id}`")
        scoped_item = _requirement_with_blocking(inventory_by_id[requirement_id], True, scope_source=scope_file)
        scoped.append(scoped_item)
        seen.add(requirement_id)
    for index, item in enumerate(requirement_items, start=1):
        scoped_item = _scoped_requirement_from_item(scope_file, item, index)
        requirement_id = str(scoped_item["requirement_id"])
        if requirement_id in seen:
            raise ValueError(f"duplicate scoped acceptance requirement `{requirement_id}` in `{scope_file}`")
        scoped.append(scoped_item)
        seen.add(requirement_id)
    return scoped


def _resolve_acceptance_model(
    acceptance_sources: list[str],
    acceptance_mode: str,
    acceptance_scope_file: str | None,
) -> dict[str, Any]:
    inventory_raw = _collect_acceptance_requirements(acceptance_sources)
    if acceptance_mode == "strict":
        blocking_requirements = [_requirement_with_blocking(item, True) for item in inventory_raw]
        inventory_requirements = [_requirement_with_blocking(item, True) for item in inventory_raw]
        context_only_ids: list[str] = []
    else:
        inventory_requirements = [_requirement_with_blocking(item, False) for item in inventory_raw]
        if acceptance_scope_file:
            blocking_requirements = _scoped_requirements_from_scope_file(inventory_requirements, acceptance_scope_file)
        else:
            blocking_requirements = []
        scoped_imported_ids = {
            str(item.get("requirement_id") or "")
            for item in blocking_requirements
            if item.get("acceptance_source") in acceptance_sources
        }
        context_only_ids = [
            str(item.get("requirement_id") or "")
            for item in inventory_requirements
            if str(item.get("requirement_id") or "") not in scoped_imported_ids
        ]

    return {
        "acceptance_requirements": blocking_requirements,
        "scoped_acceptance_requirements": blocking_requirements,
        "scoped_acceptance_notes": (
            list(DEFAULT_SCOPED_ACCEPTANCE_NOTES)
            if acceptance_mode == "scoped" and blocking_requirements
            else []
        ),
        "acceptance_inventory_requirements": inventory_requirements,
        "acceptance_inventory_count": len(inventory_requirements),
        "acceptance_inventory_unscoped_count": len(context_only_ids),
        "acceptance_context_only_requirement_ids": context_only_ids,
    }


def _required_acceptance_artifacts(requirements: list[dict[str, Any]]) -> list[str]:
    artifacts: list[str] = []
    for item in requirements:
        artifacts.extend(list(item.get("required_artifact_paths") or []))
    return _normalize_paths(artifacts)


def _acceptance_blocking_policy(
    acceptance_sources: list[str],
    acceptance_mode: str,
    scoped_requirement_count: int,
    inventory_count: int,
) -> str | None:
    if not acceptance_sources and not scoped_requirement_count:
        return None
    if acceptance_mode == "strict":
        return (
            "Strict acceptance mode: during `review-feedback`, do not persist `approved` "
            "or `approved_with_advisories` for the reviewed head commit until every imported "
            "acceptance-evidence record is present with status `pass`."
        )
    return (
        "Scoped acceptance mode: during `review-feedback`, approval persistence is blocked only "
        "by scoped acceptance requirements with evidence status `missing` or `fail`; imported "
        f"unscoped acceptance-source bullets remain context/audit inventory ({inventory_count} item(s))."
    )


def _load_acceptance_evidence_entries(path: str | None) -> list[dict[str, Any]] | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if not candidate.exists():
        raise ValueError(f"acceptance evidence file `{path}` does not exist")
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("entries")
    if not isinstance(payload, list):
        raise ValueError("acceptance evidence file must contain a JSON list or an object with `entries`")
    return payload


def _normalize_context_acceptance_evidence(
    inventory_requirements: list[dict[str, Any]],
    raw_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    inventory_by_id = {
        str(requirement.get("requirement_id") or ""): requirement
        for requirement in inventory_requirements
    }
    normalized: list[dict[str, Any]] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            raise ValueError("each acceptance evidence entry must be an object")
        requirement_id = str(item.get("requirement_id") or "").strip()
        if requirement_id not in inventory_by_id:
            raise ValueError(f"unknown acceptance evidence requirement `{requirement_id}`")
        status = str(item.get("status") or "").strip()
        if status not in VALID_ACCEPTANCE_EVIDENCE_STATUSES:
            raise ValueError(
                "`status` must be one of: " + ", ".join(sorted(VALID_ACCEPTANCE_EVIDENCE_STATUSES))
            )
        requirement = inventory_by_id[requirement_id]
        normalized.append(
            {
                "requirement_id": requirement_id,
                "status": status,
                "reviewed_artifact_paths": _normalize_paths(
                    list(item.get("reviewed_artifact_paths") or requirement.get("required_artifact_paths") or [])
                ),
                "comparator_basis": (
                    str(item.get("comparator_basis")).strip()
                    if item.get("comparator_basis") is not None
                    else requirement.get("comparator_basis")
                ),
                "notes": str(item.get("notes") or "").strip(),
                "context_only": True,
            }
        )
    return normalized


def _split_scoped_and_context_evidence(
    raw_entries: list[dict[str, Any]] | None,
    scoped_requirements: list[dict[str, Any]],
    inventory_requirements: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    if raw_entries is None:
        return (None, [])
    scoped_ids = {str(item.get("requirement_id") or "") for item in scoped_requirements}
    inventory_ids = {str(item.get("requirement_id") or "") for item in inventory_requirements}
    scoped_entries: list[dict[str, Any]] = []
    context_entries: list[dict[str, Any]] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            raise ValueError("each acceptance evidence entry must be an object")
        requirement_id = str(item.get("requirement_id") or "").strip()
        if requirement_id in scoped_ids:
            scoped_entries.append(item)
        elif requirement_id in inventory_ids:
            context_entries.append(item)
        else:
            raise ValueError(f"unknown acceptance evidence requirement `{requirement_id}`")
    return (scoped_entries, _normalize_context_acceptance_evidence(inventory_requirements, context_entries))


def _normalize_acceptance_evidence(
    requirements: list[dict[str, Any]],
    raw_entries: list[dict[str, Any]] | None,
    default_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not requirements:
        return []
    defaults: dict[str, dict[str, Any]] = {}
    for requirement in requirements:
        defaults[str(requirement["requirement_id"])] = {
            "requirement_id": str(requirement["requirement_id"]),
            "status": "missing",
            "reviewed_artifact_paths": list(requirement.get("required_artifact_paths") or []),
            "comparator_basis": requirement.get("comparator_basis"),
            "notes": "",
        }
    for item in default_entries or []:
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("requirement_id") or "").strip()
        if requirement_id not in defaults:
            continue
        status = str(item.get("status") or "").strip()
        if status not in VALID_ACCEPTANCE_EVIDENCE_STATUSES:
            continue
        defaults[requirement_id] = {
            "requirement_id": requirement_id,
            "status": status,
            "reviewed_artifact_paths": _normalize_paths(
                list(item.get("reviewed_artifact_paths") or defaults[requirement_id]["reviewed_artifact_paths"])
            ),
            "comparator_basis": (
                str(item.get("comparator_basis")).strip()
                if item.get("comparator_basis") is not None
                else defaults[requirement_id]["comparator_basis"]
            ),
            "notes": str(item.get("notes") or "").strip(),
        }
    if not raw_entries:
        return list(defaults.values())

    for item in raw_entries:
        if not isinstance(item, dict):
            raise ValueError("each acceptance evidence entry must be an object")
        requirement_id = str(item.get("requirement_id") or "").strip()
        if not requirement_id:
            raise ValueError("each acceptance evidence entry must include `requirement_id`")
        if requirement_id not in defaults:
            raise ValueError(f"unknown acceptance evidence requirement `{requirement_id}`")
        status = str(item.get("status") or "").strip()
        if status not in VALID_ACCEPTANCE_EVIDENCE_STATUSES:
            raise ValueError(
                "`status` must be one of: " + ", ".join(sorted(VALID_ACCEPTANCE_EVIDENCE_STATUSES))
            )
        reviewed_artifact_paths = _normalize_paths(
            list(item.get("reviewed_artifact_paths") or defaults[requirement_id]["reviewed_artifact_paths"])
        )
        defaults[requirement_id] = {
            "requirement_id": requirement_id,
            "status": status,
            "reviewed_artifact_paths": reviewed_artifact_paths,
            "comparator_basis": (
                str(item.get("comparator_basis")).strip()
                if item.get("comparator_basis") is not None
                else defaults[requirement_id]["comparator_basis"]
            ),
            "notes": str(item.get("notes") or "").strip(),
        }
    return list(defaults.values())


def _acceptance_gate_status(
    requirements: list[dict[str, Any]],
    acceptance_evidence: list[dict[str, Any]],
) -> tuple[str, int, int, list[str]]:
    if not requirements:
        return ("not_required", 0, 0, [])
    fail_count = sum(1 for item in acceptance_evidence if item.get("status") == "fail")
    missing_count = sum(1 for item in acceptance_evidence if item.get("status") == "missing")
    blocker_ids = [
        str(item.get("requirement_id") or "")
        for item in acceptance_evidence
        if item.get("status") in {"fail", "missing"}
    ]
    if fail_count:
        return ("fail", missing_count, fail_count, blocker_ids)
    if missing_count:
        return ("missing", missing_count, fail_count, blocker_ids)
    return ("pass", 0, 0, [])


def _independent_review_required(risk_tier: str) -> bool:
    return risk_tier in {"medium", "high"}


def _resolve_independent_review_artifact_path(run_id: str, raw_path: str | None) -> Path | None:
    if raw_path:
        candidate = Path(raw_path)
        return candidate if candidate.is_absolute() else REPO_ROOT / candidate
    default_path = _independent_review_path(run_id)
    return default_path if default_path.exists() else None


def _artifact_review_result(payload: dict[str, Any]) -> str:
    return _normalize_review_result(payload.get("review_result") or payload.get("result"))


def _string_field(payload: dict[str, Any], field_name: str) -> str:
    return str(payload.get(field_name) or "").strip()


def _validate_independent_review_artifact(
    *,
    run_id: str,
    run_manifest: dict[str, Any],
    review_manifest_payload: dict[str, Any],
    review_basis_head_commit: str,
    changed_paths: list[str],
    artifact_path: str | None,
    reviewer_id: str | None,
    reviewer_session_id: str | None,
) -> dict[str, Any]:
    risk_tier = str(review_manifest_payload.get("risk_tier") or "medium")
    required = _independent_review_required(risk_tier)
    resolved_path = _resolve_independent_review_artifact_path(run_id, artifact_path)
    result: dict[str, Any] = {
        "required": required,
        "status": "not_required",
        "artifact_path": str(resolved_path) if resolved_path else None,
        "errors": [],
        "review_result": None,
        "findings_count": 0,
        "blocking_findings_count": 0,
        "reviewer_id": _normalize_identity(reviewer_id, env_name=AI_CHANGE_REVIEWER_ID_ENV),
        "reviewer_session_id": _normalize_identity(
            reviewer_session_id,
            env_name=AI_CHANGE_REVIEWER_SESSION_ID_ENV,
        ),
    }
    if not required and resolved_path is None:
        implementer_id = _normalize_identity(run_manifest.get("implementer_id"))
        implementer_session_id = _normalize_identity(run_manifest.get("implementer_session_id"))
        errors = []
        if _same_known_identity(result["reviewer_id"], implementer_id):
            errors.append("reviewer id matches implementer id")
        if _same_known_session(result["reviewer_session_id"], implementer_session_id):
            errors.append("reviewer session id matches implementer session id")
        if errors:
            result["status"] = "fail"
            result["errors"] = errors
        return result
    if resolved_path is None or not resolved_path.exists():
        result["status"] = "missing"
        result["errors"] = ["required independent AI review artifact is missing"]
        return result

    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result["status"] = "fail"
        result["errors"] = [f"independent AI review artifact is unreadable: {exc}"]
        return result
    if not isinstance(payload, dict):
        result["status"] = "fail"
        result["errors"] = ["independent AI review artifact must contain a JSON object"]
        return result

    errors: list[str] = []
    payload_reviewer_id = _normalize_identity(payload.get("reviewer_id"))
    payload_reviewer_session_id = _normalize_identity(payload.get("reviewer_session_id"))
    reviewer_identity_hint = str(reviewer_id or os.getenv(AI_CHANGE_REVIEWER_ID_ENV) or "").strip()
    reviewer_session_hint = str(
        reviewer_session_id or os.getenv(AI_CHANGE_REVIEWER_SESSION_ID_ENV) or ""
    ).strip()
    if reviewer_identity_hint and reviewer_identity_hint != payload_reviewer_id:
        errors.append("reviewer id argument does not match independent review artifact")
    if reviewer_session_hint and reviewer_session_hint != payload_reviewer_session_id:
        errors.append("reviewer session argument does not match independent review artifact")
    if not _identity_known(payload_reviewer_id):
        errors.append("independent AI review artifact must record a reviewer id")
    if not _identity_known(payload_reviewer_session_id):
        errors.append("independent AI review artifact must record a reviewer session id")

    implementer_id = _normalize_identity(run_manifest.get("implementer_id"))
    implementer_session_id = _normalize_identity(run_manifest.get("implementer_session_id"))
    payload_implementer_id = _normalize_identity(payload.get("implementer_id"))
    payload_implementer_session_id = _normalize_identity(payload.get("implementer_session_id"))
    if required and not _identity_known(implementer_id):
        errors.append("run manifest must record an implementer id for independent review")
    if required and not _identity_known(implementer_session_id):
        errors.append("run manifest must record an implementer session id for independent review")
    if not _identity_known(payload_implementer_id):
        errors.append("independent AI review artifact must record an implementer id")
    elif payload_implementer_id != implementer_id:
        errors.append("independent AI review artifact implementer id does not match run manifest")
    if not _identity_known(payload_implementer_session_id):
        errors.append("independent AI review artifact must record an implementer session id")
    elif payload_implementer_session_id != implementer_session_id:
        errors.append("independent AI review artifact implementer session id does not match run manifest")
    if _same_known_identity(payload_reviewer_id, implementer_id):
        errors.append("reviewer id matches implementer id")
    if _same_known_session(payload_reviewer_session_id, implementer_session_id):
        errors.append("reviewer session id matches implementer session id")

    if str(payload.get("review_basis_head_commit") or "") != review_basis_head_commit:
        errors.append("independent AI review artifact is stale for the reviewed head commit")
    payload_paths = _normalize_paths(list(payload.get("paths") or []))
    if not payload_paths:
        errors.append("independent AI review artifact must record reviewed paths")
    elif payload_paths != _normalize_paths(changed_paths):
        errors.append("independent AI review artifact path set does not match the review manifest")
    if _string_field(payload, "reviewer_type") != "ai":
        errors.append("independent review artifact must record reviewer_type=ai")
    if not _string_field(payload, "provider"):
        errors.append("independent AI review artifact must record provider")
    if _string_field(payload, "prompt_version") != INDEPENDENT_REVIEW_PROMPT_VERSION:
        errors.append("independent AI review artifact prompt version is missing or unsupported")

    review_result = _artifact_review_result(payload)
    if review_result not in {"pending_local_review", "approved", "approved_with_advisories", "changes_requested"}:
        errors.append("independent AI review artifact must include a valid review_result")
    try:
        artifact_findings_count = _coerce_optional_non_negative_int(
            payload.get("findings_count"),
            field_name="independent_review.findings_count",
        ) or 0
        artifact_blocking_count = _coerce_optional_non_negative_int(
            payload.get("blocking_findings_count"),
            field_name="independent_review.blocking_findings_count",
        ) or 0
    except ValueError as exc:
        artifact_findings_count = 0
        artifact_blocking_count = 0
        errors.append(str(exc))
    if artifact_blocking_count > artifact_findings_count:
        errors.append("independent AI review blocking findings exceed total findings")

    required_fields = list(INDEPENDENT_REVIEW_BASE_ASSESSMENT_FIELDS)
    if risk_tier == "high":
        required_fields.extend(INDEPENDENT_REVIEW_HIGH_RISK_ASSESSMENT_FIELDS)
    for field_name in required_fields:
        if not _string_field(payload, field_name):
            errors.append(f"independent AI review artifact is missing `{field_name}`")

    result.update(
        {
            "status": "fail" if errors else "pass",
            "errors": errors,
            "review_result": review_result or None,
            "findings_count": artifact_findings_count,
            "blocking_findings_count": artifact_blocking_count,
            "reviewer_id": payload_reviewer_id,
            "reviewer_session_id": payload_reviewer_session_id,
            "provider": _string_field(payload, "provider"),
            "model": _string_field(payload, "model"),
        }
    )
    return result


def _resolve_review_feedback_contract(
    *,
    review_state: str,
    requested_review_result: object = "",
    requested_findings_count: object = None,
    requested_blocking_findings_count: object = None,
    requested_next_action: object = "",
    carried_review_result: object = "",
    carried_findings_count: object = None,
    carried_blocking_findings_count: object = None,
    carried_next_action: object = "",
) -> tuple[str, int, int, str]:
    if review_state != "ready_for_review":
        return ("pending_ready_transition", 0, 0, "mark_ready_for_review")

    normalized_requested_result = _normalize_review_result(requested_review_result)
    if str(requested_review_result or "").strip() and not normalized_requested_result:
        raise ValueError(
            "`review_result` must be one of: "
            + ", ".join(sorted(VALID_REVIEW_RESULTS))
        )
    normalized_requested_action = _normalize_review_next_action(requested_next_action)
    if str(requested_next_action or "").strip() and not normalized_requested_action:
        raise ValueError(
            "`next_action` must be one of: "
            + ", ".join(sorted(VALID_REVIEW_NEXT_ACTIONS))
        )

    review_result = normalized_requested_result or _normalize_review_result(carried_review_result) or "pending_local_review"
    findings_count = _coerce_optional_non_negative_int(
        requested_findings_count if requested_findings_count is not None else carried_findings_count,
        field_name="findings_count",
    )
    blocking_findings_count = _coerce_optional_non_negative_int(
        (
            requested_blocking_findings_count
            if requested_blocking_findings_count is not None
            else carried_blocking_findings_count
        ),
        field_name="blocking_findings_count",
    )
    findings_count = findings_count or 0
    blocking_findings_count = blocking_findings_count or 0

    if blocking_findings_count > findings_count:
        findings_count = blocking_findings_count

    if review_result == "pending_local_review":
        findings_count = 0
        blocking_findings_count = 0
    elif review_result == "changes_requested":
        blocking_findings_count = max(blocking_findings_count, 1)
        findings_count = max(findings_count, blocking_findings_count)
    elif review_result == "approved":
        if blocking_findings_count > 0:
            review_result = "changes_requested"
            findings_count = max(findings_count, blocking_findings_count)
        elif findings_count > 0:
            review_result = "approved_with_advisories"
    elif review_result == "approved_with_advisories":
        blocking_findings_count = 0
        findings_count = max(findings_count, 1)

    if normalized_requested_action:
        next_action = normalized_requested_action
    elif normalized_requested_result:
        next_action = _review_feedback_next_action(review_result)
    else:
        next_action = _normalize_review_next_action(carried_next_action)
        if not next_action:
            next_action = _review_feedback_next_action(review_result)
    return review_result, findings_count, blocking_findings_count, next_action


def _normalize_run_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(manifest)
    workflow_mode = str(normalized.get("workflow_mode") or "")
    if not workflow_mode or workflow_mode == LEGACY_WORKFLOW_MODE:
        normalized["workflow_mode"] = DEFAULT_WORKFLOW_MODE

    review_transport = str(normalized.get("review_transport") or "")
    if not review_transport or review_transport == LEGACY_REVIEW_TRANSPORT:
        normalized["review_transport"] = DEFAULT_REVIEW_TRANSPORT

    local_role = str(normalized.get("local_governance_role") or "")
    if not local_role or local_role == LEGACY_LOCAL_GOVERNANCE_ROLE:
        normalized["local_governance_role"] = DEFAULT_LOCAL_GOVERNANCE_ROLE

    review_title = str(
        normalized.get("review_title")
        or normalized.get("pr_title")
        or normalized.get("task_summary")
        or ""
    )
    normalized["review_title"] = review_title
    normalized["pr_title"] = review_title

    review_state = _normalized_review_state(normalized.get("review_state") or normalized.get("pr_review_state"))
    normalized["review_state"] = review_state
    normalized["pr_review_state"] = review_state
    if normalized.get("execution_mode") == "autopilot":
        normalized["autopilot_next_action"] = str(
            normalized.get("autopilot_next_action") or DEFAULT_AUTOPILOT_NEXT_ACTION
        )
    else:
        normalized["autopilot_next_action"] = normalized.get("autopilot_next_action")
    latest_review_result = _normalize_review_result(normalized.get("latest_review_result"))
    latest_review_next_action = _normalize_review_next_action(normalized.get("latest_review_next_action"))
    normalized["latest_review_result"] = latest_review_result or None
    normalized["latest_review_next_action"] = latest_review_next_action or None
    normalized["acceptance_sources"] = _normalize_paths(list(normalized.get("acceptance_sources") or []))
    normalized["acceptance_mode"] = _normalize_acceptance_mode(normalized.get("acceptance_mode"))
    normalized["acceptance_scope_file"] = (
        _normalize_repo_path(str(normalized.get("acceptance_scope_file")))
        if normalized.get("acceptance_scope_file")
        else None
    )
    normalized["implementer_id"] = _normalize_identity(normalized.get("implementer_id"))
    normalized["implementer_session_id"] = _normalize_identity(normalized.get("implementer_session_id"))
    return normalized


def _load_run_manifest(run_id: str) -> dict[str, Any]:
    path = _run_manifest_path(run_id)
    if not path.exists():
        raise ValueError(f"unknown run `{run_id}`")
    return _normalize_run_manifest(_read_json(path))


def _save_run_manifest(manifest: dict[str, Any]) -> None:
    manifest = _normalize_run_manifest(manifest)
    manifest["updated_at"] = _utc_now()
    _write_json(_run_manifest_path(str(manifest["run_id"])), manifest)


def _list_run_ids() -> list[str]:
    root = _runs_root()
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def _active_run_manifest() -> dict[str, Any] | None:
    active_manifests: list[dict[str, Any]] = []
    for run_id in _list_run_ids():
        manifest = _load_run_manifest(run_id)
        if manifest.get("status") == "active":
            active_manifests.append(manifest)
    if not active_manifests:
        return None
    active_manifests.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return active_manifests[0]


def _next_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    base = f"ai-change-{stamp}"
    candidate = base
    suffix = 1
    while _run_manifest_path(candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix:02d}"
    return candidate


def _git_result(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _resolve_hooks_path(repo_root: str | None, hooks_path: str | None) -> Path | None:
    if not repo_root or not hooks_path:
        return None
    candidate = Path(hooks_path)
    if not candidate.is_absolute():
        candidate = Path(repo_root) / candidate
    return candidate.resolve()


def detect_git_context() -> GitContext:
    root_result = _git_result(["rev-parse", "--show-toplevel"])
    if root_result.returncode != 0:
        detail = (root_result.stderr or root_result.stdout).strip() or f"exit {root_result.returncode}"
        return GitContext(
            available=False,
            repo_root=None,
            current_branch=None,
            detached_head=False,
            remotes=[],
            has_origin_remote=False,
            hooks_path=None,
            local_push_guard_present=False,
            local_push_guard_installed=False,
            reason=f"not a git repository: {detail}",
        )

    repo_root = root_result.stdout.strip() or None
    branch_result = _git_result(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode == 0:
        branch_name = (branch_result.stdout or "").strip()
        detached_head = branch_name == "HEAD"
    else:
        symbolic_branch = _git_result(["symbolic-ref", "--quiet", "--short", "HEAD"])
        branch_name = (symbolic_branch.stdout or "").strip() if symbolic_branch.returncode == 0 else ""
        detached_head = False if branch_name else True
    remote_result = _git_result(["remote"])
    remotes = [line.strip() for line in remote_result.stdout.splitlines() if line.strip()] if remote_result.returncode == 0 else []
    hooks_result = _git_result(["config", "--get", "core.hooksPath"])
    hooks_path = (hooks_result.stdout or "").strip() if hooks_result.returncode == 0 else ""
    configured_hooks_path = hooks_path or None
    push_guard_present = bool(repo_root) and (Path(repo_root) / GIT_PUSH_GUARD_PATH).exists()
    resolved_hooks_path = _resolve_hooks_path(repo_root, configured_hooks_path)
    expected_hooks_path = _resolve_hooks_path(repo_root, EXPECTED_GIT_HOOKS_PATH)
    return GitContext(
        available=True,
        repo_root=repo_root,
        current_branch=None if detached_head or not branch_name else branch_name,
        detached_head=detached_head,
        remotes=remotes,
        has_origin_remote="origin" in remotes,
        hooks_path=configured_hooks_path,
        local_push_guard_present=push_guard_present,
        local_push_guard_installed=bool(push_guard_present and resolved_hooks_path and expected_hooks_path and resolved_hooks_path == expected_hooks_path),
    )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "task"


def _default_branch_name(run_id: str, task_summary: str) -> str:
    suffix = run_id.removeprefix("ai-change-")
    return f"{DEFAULT_BRANCH_PREFIX}{suffix}-{_slugify(task_summary)[:40]}"


def _git_error(result: subprocess.CompletedProcess[str], context: str) -> ValueError:
    detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
    return ValueError(f"{context}: {detail}")


def _git_require(args: list[str], context: str) -> subprocess.CompletedProcess[str]:
    result = _git_result(args)
    if result.returncode != 0:
        raise _git_error(result, context)
    return result


def _git_ref_exists(ref: str) -> bool:
    return _git_result(["rev-parse", "--verify", "--quiet", ref]).returncode == 0


def _git_local_branch_exists(branch: str) -> bool:
    return _git_ref_exists(f"refs/heads/{branch}")


def _git_remote_tracking_branch_exists(branch: str) -> bool:
    return _git_ref_exists(f"refs/remotes/origin/{branch}")


def _git_checkout(branch: str) -> None:
    _git_require(["checkout", branch], f"unable to checkout branch `{branch}`")


def _git_checkout_new_branch(branch: str, start_point: str | None = None) -> None:
    args = ["checkout", "-b", branch]
    if start_point:
        args.append(start_point)
    _git_require(args, f"unable to create branch `{branch}`")


def _ensure_run_branch(
    run_id: str,
    task_summary: str,
    base_branch: str,
    requested_branch: str | None,
) -> tuple[str, str]:
    git_context = detect_git_context()
    if not git_context.available:
        raise ValueError("start-run requires a real git repository because the branch diff is now part of the default workflow")

    current_branch = git_context.current_branch
    target_branch = requested_branch or _default_branch_name(run_id, task_summary)

    if not requested_branch and current_branch and current_branch not in {base_branch, PROTECTED_BRANCH}:
        return current_branch, "reused_current"
    if current_branch == target_branch:
        return target_branch, "reused_current"
    if _git_local_branch_exists(target_branch):
        _git_checkout(target_branch)
        return target_branch, "checked_out_existing"
    if _git_remote_tracking_branch_exists(target_branch):
        _git_require(
            ["checkout", "-b", target_branch, f"origin/{target_branch}"],
            f"unable to checkout tracking branch `{target_branch}`",
        )
        return target_branch, "checked_out_tracking"

    start_point = current_branch or "HEAD"
    _git_checkout_new_branch(target_branch, start_point)
    return target_branch, "created"


def _render_review_feedback_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Review Feedback",
        "",
        f"- Review state: `{payload['review_state']}`",
        f"- Review result: `{payload['review_result']}`",
        f"- Code review findings: {payload['findings_count']}",
        f"- Blocking code findings: {payload['blocking_findings_count']}",
        f"- Next action: `{payload['next_action']}`",
        f"- Review transport: `{payload['review_transport']}`",
        f"- Base branch: `{payload['base_branch']}`",
        f"- Head branch: `{payload['head_branch']}`",
        f"- Review basis head commit: `{payload['review_basis_head_commit']}`",
        f"- Changed paths: {len(payload.get('paths', []))}",
        "",
    ]
    if payload.get("summary"):
        lines.extend(["## Summary", payload["summary"], ""])
    if payload.get("review_notes"):
        lines.extend(["## Review Notes", str(payload["review_notes"]).strip(), ""])
    if payload.get("review_brief"):
        lines.extend(["## Reviewer Brief", payload["review_brief"], ""])
    if payload.get("independent_review_required") or payload.get("independent_review_artifact"):
        lines.extend(
            [
                "## Independent AI Review",
                f"- Required: `{payload.get('independent_review_required')}`",
                f"- Status: `{payload.get('independent_review_status')}`",
                f"- Artifact: `{payload.get('independent_review_artifact')}`",
                f"- Reviewer id: `{payload.get('reviewer_id')}`",
                f"- Reviewer session id: `{payload.get('reviewer_session_id')}`",
                f"- Result: `{payload.get('independent_review_result')}`",
                f"- Findings: {payload.get('independent_review_findings_count', 0)}",
                f"- Blocking findings: {payload.get('independent_review_blocking_findings_count', 0)}",
            ]
        )
        for error in payload.get("independent_review_errors") or []:
            lines.append(f"- Gate error: {error}")
        lines.append("")
    if payload.get("validation_commands"):
        lines.append("## Validation Commands")
        lines.extend(f"- `{command}`" for command in payload["validation_commands"])
        lines.append("")
    if payload.get("acceptance_requirements") or payload.get("acceptance_inventory_count"):
        acceptance_mode = str(payload.get("acceptance_mode") or DEFAULT_ACCEPTANCE_MODE)
        lines.extend(
            [
                "## Acceptance Gate",
                f"- Acceptance mode: `{acceptance_mode}`",
                f"- Scoped acceptance gate status: `{payload.get('scoped_acceptance_gate_status')}`",
                f"- Scoped missing evidence count: {payload.get('scoped_acceptance_missing_count', 0)}",
                f"- Scoped failing evidence count: {payload.get('scoped_acceptance_fail_count', 0)}",
                f"- Scoped blocking requirements: {len(payload.get('scoped_acceptance_requirements') or [])}",
                f"- Context/audit inventory items: {payload.get('acceptance_inventory_count', 0)}",
                f"- Unscoped inventory items: {payload.get('acceptance_inventory_unscoped_count', 0)}",
            ]
        )
        if acceptance_mode == "strict":
            lines.append(
                f"- Imported acceptance requirements: {payload.get('acceptance_inventory_count', 0)} blocking item(s)."
            )
        else:
            lines.append(
                "- Imported acceptance inventory: "
                f"{payload.get('acceptance_inventory_count', 0)} context item(s); "
                f"scoped blocking requirements: {len(payload.get('scoped_acceptance_requirements') or [])}."
            )
        if payload.get("acceptance_sources"):
            lines.append("- Acceptance sources: " + ", ".join(f"`{path}`" for path in payload["acceptance_sources"]))
        if payload.get("approval_blocking_requirement_ids"):
            lines.append(
                "- Blocking requirement ids: "
                + ", ".join(f"`{item}`" for item in payload["approval_blocking_requirement_ids"])
            )
        if payload.get("scoped_acceptance_notes"):
            lines.append("- Scoped notes: " + " ".join(str(item) for item in payload["scoped_acceptance_notes"]))
        lines.append("")
        lines.append("## Scoped Acceptance Evidence")
        for item in payload.get("scoped_acceptance_evidence", payload.get("acceptance_evidence", [])):
            lines.append(f"- `{item['requirement_id']}` status=`{item['status']}`")
            if item.get("reviewed_artifact_paths"):
                lines.append(
                    "  - Reviewed artifact paths: "
                    + ", ".join(f"`{path}`" for path in item["reviewed_artifact_paths"])
                )
            if item.get("comparator_basis"):
                lines.append(f"  - Comparator basis: `{item['comparator_basis']}`")
            if item.get("notes"):
                lines.append(f"  - Notes: {item['notes']}")
        lines.append("")
        if payload.get("acceptance_context_only_requirement_ids"):
            context_ids = list(payload["acceptance_context_only_requirement_ids"])
            lines.append("## Acceptance Inventory")
            lines.append(
                f"- Context-only requirement ids: {len(context_ids)} item(s) recorded in `review_feedback.json`."
            )
            if payload.get("acceptance_inventory_evidence"):
                lines.append(
                    f"- Context-only evidence entries: {len(payload['acceptance_inventory_evidence'])} item(s)."
                )
            if len(context_ids) <= 20:
                lines.append("- IDs: " + ", ".join(f"`{item}`" for item in context_ids))
            else:
                lines.append("- First 20 IDs: " + ", ".join(f"`{item}`" for item in context_ids[:20]))
            lines.append("")
    if payload.get("paths"):
        lines.append("## Changed Paths")
        lines.extend(f"- `{path}`" for path in payload["paths"])
        lines.append("")
    lines.extend(
        [
            "## Review Process",
            f"- Review bundle: `{payload['review_bundle']}`",
            f"- Review manifest: `{payload['review_manifest']}`",
            "- Conduct the code review locally from the current branch diff and report findings in-session.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _git_stage_paths(paths: list[str]) -> None:
    if not paths:
        return
    _git_require(["add", "--", *paths], "unable to stage requested paths")


def _git_stage_all() -> None:
    _git_require(["add", "-A"], "unable to stage all changes")


def _git_branch_diff_paths(base_branch: str, head_ref: str = "HEAD") -> list[str]:
    # The run branch is created from the local clean base branch; prefer that
    # same local ref so clones with local main ahead of origin do not widen the
    # review diff to unrelated historical commits.
    base_candidates = [base_branch, f"origin/{base_branch}"]
    base_ref = next((candidate for candidate in base_candidates if _git_ref_exists(candidate)), None)
    if base_ref is None:
        raise ValueError(f"unable to resolve base branch `{base_branch}` locally; fetch or create it first")
    result = _git_result(["diff", "--name-only", f"{base_ref}...{head_ref}"])
    if result.returncode != 0:
        raise _git_error(result, f"unable to diff `{head_ref}` against `{base_ref}`")
    return _normalize_paths([line.strip() for line in result.stdout.splitlines() if line.strip()])


def _git_head_commit(ref: str = "HEAD") -> str:
    return _git_require(["rev-parse", ref], f"unable to resolve git commit for `{ref}`").stdout.strip()


def _git_commit(message: str) -> str:
    commit_result = _git_result(["commit", "-m", message])
    if commit_result.returncode != 0:
        raise _git_error(commit_result, "unable to create checkpoint commit")
    head_result = _git_require(["rev-parse", "HEAD"], "unable to read checkpoint commit id")
    return head_result.stdout.strip()


def _git_push_branch(branch: str) -> None:
    _git_require(["push", "-u", "origin", branch], f"unable to push branch `{branch}` to `origin`")


def _git_worktree_dirty() -> bool:
    result = _git_require(["status", "--porcelain"], "unable to read git worktree status")
    return bool(result.stdout.strip())


def _git_status_paths() -> list[str]:
    result = _git_require(["status", "--porcelain"], "unable to read git worktree status")
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        candidate = line[3:] if len(line) >= 4 else line
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1]
        candidate = candidate.strip().strip('"')
        if candidate:
            paths.append(candidate)
    return _normalize_paths(paths)


def _repo_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_dir_file_snapshot(run_id: str) -> dict[str, str]:
    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        snapshot[_normalize_paths([_repo_relative_path(path)])[0]] = _file_sha256(path)
    return snapshot


def _changed_snapshot_paths(
    before: dict[str, str],
    after: dict[str, str],
    allowed_paths: set[str],
) -> list[str]:
    changed: list[str] = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path) and path not in allowed_paths:
            changed.append(path)
    return changed


def _require_run_branch(run_manifest: dict[str, Any]) -> GitContext:
    git_context = detect_git_context()
    if not git_context.available:
        raise ValueError("this `/ai-change` run requires a real git repository")
    expected_branch = str(run_manifest.get("head_branch") or "")
    if not expected_branch:
        raise ValueError("run manifest is missing `head_branch`; start a new git-backed run")
    if git_context.current_branch != expected_branch:
        current = git_context.current_branch or "detached HEAD"
        raise ValueError(f"run `{run_manifest['run_id']}` is bound to branch `{expected_branch}`, but the current branch is `{current}`")
    return git_context


def classify_path_tags(path: str) -> set[str]:
    tags: set[str] = set()
    if path.startswith("tests/"):
        tags.add("tests")
    if path.startswith("docs/legacy/"):
        tags.add("legacy_docs")
    if path.startswith("docs/") or path.endswith(".md") or path.endswith(".json"):
        tags.add("docs")
    if path in GOVERNANCE_SURFACES:
        tags.add("governance")
    if _has_prefix(path, WORKFLOW_SURFACES):
        tags.add("workflow")
    if path.startswith(".claude/scripts/check_") or path == ".claude/scripts/ai_change_governance.py":
        tags.add("governance_tooling")
    if path == ".claude/commands/ai-change.md":
        tags.add("governance_tooling")
    if path.startswith(".claude/commands/"):
        tags.add("command_contract")
    if path.startswith(".claude/agents/"):
        tags.add("workflow")
    if path in ARCHITECTURE_SYNC_DOCS:
        tags.add("architecture_sync_doc")
    return tags


def _is_code_or_workflow_surface(path: str) -> bool:
    if _has_prefix(path, WORKFLOW_SURFACES):
        return True
    return path in {
        "AGENTS.md",
        "CLAUDE.md",
        "docs/coder_guide.md",
        "docs/architecture.md",
        "docs/ai_change_governance.md",
    }


def _domain_overlays(tags: set[str]) -> list[str]:
    del tags
    return []


def _risk_tier(tags: set[str], paths: list[str]) -> str:
    if any(tag in tags for tag in ("governance", "governance_tooling", "workflow", "command_contract")):
        return "medium"
    if paths and all("tests" in classify_path_tags(path) or "docs" in classify_path_tags(path) for path in paths):
        return "low"
    return "medium"


def _review_policy(risk_tier: str) -> str:
    if risk_tier == "high":
        return "independent_review_and_audit"
    if risk_tier == "medium":
        return "independent_review"
    return "self_review_plus_optional_independent_review"


def _read_surface(tags: set[str], acceptance_sources: list[str]) -> list[str]:
    del tags
    surface = list(BASE_READ_SURFACE)
    surface.extend(acceptance_sources)
    deduped: list[str] = []
    for path in surface:
        normalized = _normalize_repo_path(path)
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _default_read_surface_exclusion_label(path: str) -> str:
    if path.startswith("docs/legacy/"):
        return "docs/legacy/**"
    return ""


def _default_read_surface_guidance(paths: list[str], read_surface: list[str]) -> list[str]:
    lines = ["- Read surface: " + ", ".join(read_surface)]
    focus_paths: list[str] = []
    omitted_focus_count = 0
    excluded_counts: dict[str, int] = {}
    for path in paths:
        exclusion_label = _default_read_surface_exclusion_label(path)
        if exclusion_label:
            excluded_counts[exclusion_label] = excluded_counts.get(exclusion_label, 0) + 1
            continue
        if len(focus_paths) < DEFAULT_READ_SURFACE_FOCUS_LIMIT:
            focus_paths.append(path)
        else:
            omitted_focus_count += 1
    if focus_paths:
        suffix = f", +{omitted_focus_count} more directly touched path(s)" if omitted_focus_count else ""
        lines.append("- Changed-path focus: " + ", ".join(focus_paths) + suffix + ".")
    elif paths:
        lines.append(
            "- Changed-path focus: none in the default read surface summary; start from the branch diff and open only the touched files needed for a concrete finding."
        )
    if excluded_counts:
        exclusions = ", ".join(
            f"{label} ({count})" for label, count in sorted(excluded_counts.items())
        )
        lines.append(
            "- Default read-surface exclusions: "
            + exclusions
            + "; open only when a live doc, active contract failure, or concrete finding points there."
        )
    return lines


def _hard_requirements(
    paths: list[str],
    tags: set[str],
    acceptance_sources: list[str],
    acceptance_mode: str = DEFAULT_ACCEPTANCE_MODE,
) -> list[str]:
    requirements: list[str] = []
    if any(_is_code_or_workflow_surface(path) for path in paths):
        requirements.append(
            "Use a real git branch plus the local ai-change review bundle as the primary review boundary for state-changing work."
        )
        requirements.append(
            "Install the repo-managed git push guard with `git config core.hooksPath .githooks` so direct pushes to `main` are blocked locally when GitHub branch protection is unavailable."
        )
    if "governance_tooling" in tags:
        requirements.append("Keep governance automation lightweight: only concrete hard failures should block submission.")
    if acceptance_sources:
        requirements.append(
            "Import acceptance-source bullets into machine-readable local review artifacts so reviewers can trace the audit inventory."
        )
        if acceptance_mode == "strict":
            requirements.append(
                "Strict mode: the `review-feedback` writeback must not persist `approved` or `approved_with_advisories` when any imported acceptance evidence is `missing` or `fail` for the reviewed head commit."
            )
        else:
            requirements.append(
                "Scoped mode: the `review-feedback` writeback must not persist `approved` or `approved_with_advisories` when any scoped acceptance requirement is `missing` or `fail`; unscoped imported bullets are context-only inventory."
            )
    return requirements


def _advisory_notes(tags: set[str], risk_tier: str) -> list[str]:
    notes = [
        "Start from the branch diff or local `git diff` and changed files before opening related context.",
        "Keep related context expansion bounded to nearby interfaces, callers/callees, tests, or architecture docs needed to judge correctness.",
        "Keep style-only cleanup and speculative refactors advisory; reserve blockers for concrete defects.",
        "Treat the local `/ai-change` review bundle as the review transport for the current branch diff.",
    ]
    if risk_tier != "low":
        notes.append("Complete the local branch-diff review before merge.")
    if risk_tier == "high":
        notes.append("Run an independent audit lane that looks for contract drift, overfitting, and missing architecture sync.")
    return notes


def _test_command_available(command_key: str) -> bool:
    command = TEST_COMMANDS[command_key]
    if len(command) < 4 or command[:3] != ["python3", "-m", "unittest"]:
        return True
    module_path = command[3].replace(".", "/") + ".py"
    return (REPO_ROOT / module_path).exists()


def _validation_commands(tags: set[str]) -> list[str]:
    command_keys: list[str] = []
    if any(tag in tags for tag in ("governance", "governance_tooling", "command_contract")):
        command_keys.extend(["ai_change_governance", "ai_change_flow", "ai_change_hook_guard"])
    deduped: list[str] = []
    for key in command_keys:
        if not _test_command_available(key):
            continue
        command = " ".join(TEST_COMMANDS[key])
        if command not in deduped:
            deduped.append(command)
    return deduped


def _verification_expectations(
    tags: set[str],
    paths: list[str],
    validation_commands: list[str],
    acceptance_requirements: list[dict[str, Any]],
    acceptance_inventory_count: int = 0,
    acceptance_mode: str = DEFAULT_ACCEPTANCE_MODE,
) -> list[str]:
    expectations = [
        "Start from the branch diff or local `git diff` before opening related context.",
        "Use the local governance report, review bundle, and targeted checks to judge the actual branch diff in-session.",
    ]
    if validation_commands:
        expectations.append("Prefer the change's targeted validation commands before broad suite reruns when extra verification is needed.")
    behavior_paths = [path for path in paths if "docs" not in classify_path_tags(path) and "tests" not in classify_path_tags(path)]
    if behavior_paths:
        expectations.append("If behavior changed without proportional targeted verification or another concrete artifact, raise a finding.")
    else:
        expectations.append("Docs/tests-only changes may use lightweight verification when no behavior changed.")
    if acceptance_requirements:
        expectations.append(
            "Review scoped acceptance requirements and record machine-readable evidence with `status=pass|fail|missing`, reviewed artifact paths, and comparator basis where applicable."
        )
    if acceptance_mode == "scoped" and acceptance_inventory_count:
        expectations.append(
            "Use unscoped imported acceptance-source bullets as context/audit inventory, not as approval-blocking findings."
        )
    return expectations


def _review_brief(
    paths: list[str],
    risk_tier: str,
    read_surface: list[str],
    domain_overlays: list[str],
    verification_expectations: list[str],
    acceptance_sources: list[str],
    acceptance_mode: str,
    acceptance_scope_file: str | None,
    acceptance_requirements: list[dict[str, Any]],
    acceptance_inventory_count: int,
    acceptance_inventory_unscoped_count: int,
    required_acceptance_artifacts: list[str],
    approval_blocking_policy: str | None,
) -> str:
    lines = [
        "Reviewer brief",
        f"- Risk tier: {risk_tier}",
        f"- Review scope: {GENERAL_REVIEW_SCOPE}",
        f"- Context policy: {RELATED_CONTEXT_POLICY}",
        f"- Review transport: {DEFAULT_REVIEW_TRANSPORT}",
        f"- Local governance role: {DEFAULT_LOCAL_GOVERNANCE_ROLE}",
    ]
    lines.extend(_default_read_surface_guidance(paths, read_surface))
    lines.extend(
        [
        "- Start from the branch diff or local `git diff` and changed files first.",
        "- Open only directly related interfaces, callers/callees, nearby tests, or architecture docs needed to judge correctness.",
        "- Focus on bugs, regressions, contract or invariant drift, risky assumptions, security defects, and missing proportional verification.",
        "- Apply `docs/coder_guide.md` when judging whether the implementation follows repo engineering policy.",
        "- Check high-level architecture alignment against `docs/architecture.md` and any touched systemdesign contract.",
        "- Challenge contract sufficiency for the intended behavior, not just whether touched files look coherent.",
        "- Critically examine whether the code translates design intention into function; for example, a function intended to compress data for decision making must not emit artifacts about the same size as its input.",
        "- Look for overfitting to a narrow test case, fixture, project name, artifact family, or incidental wording.",
        "- Flag policy substitutions where process language or bookkeeping is used instead of enforcing the real workflow boundary.",
        "- Findings first, ordered by severity, with file references.",
        "- Keep style-only cleanup and speculative refactors advisory.",
        ]
    )
    if domain_overlays:
        lines.append("- Domain overlays: " + ", ".join(domain_overlays))
    if acceptance_sources:
        lines.append("- Acceptance sources: " + ", ".join(acceptance_sources))
        lines.append(f"- Acceptance mode: {acceptance_mode}")
    if acceptance_scope_file:
        lines.append(f"- Acceptance scope file: {acceptance_scope_file}")
    if required_acceptance_artifacts:
        lines.append("- Required acceptance artifacts: " + ", ".join(required_acceptance_artifacts))
    if acceptance_mode == "strict" and acceptance_inventory_count:
        lines.append(
            f"- Imported acceptance requirements: {acceptance_inventory_count} blocking item(s) from explicit acceptance sources."
        )
    elif acceptance_sources:
        lines.append(
            f"- Imported acceptance inventory: {acceptance_inventory_count} context item(s); "
            f"scoped blocking requirements: {len(acceptance_requirements)}."
        )
        lines.append(f"- Unscoped inventory count: {acceptance_inventory_unscoped_count}")
    if approval_blocking_policy:
        lines.append(f"- Approval blocking: {approval_blocking_policy}")
    for item in verification_expectations:
        lines.append(f"- Verification: {item}")
    return "\n".join(lines)


def _audit_brief(paths: list[str], read_surface: list[str]) -> str:
    lines = [
        "Audit brief",
    ]
    lines.extend(_default_read_surface_guidance(paths, read_surface))
    lines.extend(
        [
        "- This audit is an additive high-risk review layered on top of the default local review path.",
        "- Check contract/doc sync, architecture alignment, and test proportionality.",
        "- Apply `docs/coder_guide.md` and check high-level architecture alignment before reviewing implementation style.",
        "- Challenge contract sufficiency, overfitting, policy substitutions, and design-intent/function mismatch.",
        "- Distinguish hard failures from advisory concerns; do not turn heuristics into blockers.",
        "- Flag overfitting, hidden case-specific branching, or missing architecture sync before discussing implementation style.",
        ]
    )
    return "\n".join(lines)


def analyze_change(
    paths: list[str],
    acceptance_sources: list[str] | None = None,
    acceptance_mode: str = DEFAULT_ACCEPTANCE_MODE,
    acceptance_scope_file: str | None = None,
) -> GovernanceReport:
    normalized = _normalize_paths(paths)
    resolved_acceptance_sources = _resolve_acceptance_sources(acceptance_sources or [])
    resolved_acceptance_mode = _normalize_acceptance_mode(acceptance_mode)
    resolved_acceptance_scope_file = _resolve_acceptance_scope_file(acceptance_scope_file)
    tags: set[str] = set()
    for path in normalized:
        tags.update(classify_path_tags(path))
    risk_tier = _risk_tier(tags, normalized)
    acceptance_model = _resolve_acceptance_model(
        resolved_acceptance_sources,
        resolved_acceptance_mode,
        resolved_acceptance_scope_file,
    )
    acceptance_requirements = list(acceptance_model["acceptance_requirements"])
    acceptance_inventory_requirements = list(acceptance_model["acceptance_inventory_requirements"])
    required_acceptance_artifacts = _required_acceptance_artifacts(acceptance_requirements)
    acceptance_inventory_artifacts = _required_acceptance_artifacts(acceptance_inventory_requirements)
    approval_blocking_policy = _acceptance_blocking_policy(
        resolved_acceptance_sources,
        resolved_acceptance_mode,
        len(acceptance_requirements),
        int(acceptance_model["acceptance_inventory_count"]),
    )
    read_surface = _read_surface(tags, resolved_acceptance_sources)
    domain_overlays = _domain_overlays(tags)
    validation_commands = _validation_commands(tags)
    verification_expectations = _verification_expectations(
        tags,
        normalized,
        validation_commands,
        acceptance_requirements,
        int(acceptance_model["acceptance_inventory_count"]),
        resolved_acceptance_mode,
    )
    checks = evaluate_hard_checks(normalized, tags)
    return GovernanceReport(
        paths=normalized,
        tags=sorted(tags),
        risk_tier=risk_tier,
        review_policy=_review_policy(risk_tier),
        review_transport=DEFAULT_REVIEW_TRANSPORT,
        local_governance_role=DEFAULT_LOCAL_GOVERNANCE_ROLE,
        review_scope=GENERAL_REVIEW_SCOPE,
        context_policy=RELATED_CONTEXT_POLICY,
        domain_overlays=domain_overlays,
        read_surface=read_surface,
        hard_requirements=_hard_requirements(normalized, tags, resolved_acceptance_sources, resolved_acceptance_mode),
        advisory_notes=_advisory_notes(tags, risk_tier),
        validation_commands=validation_commands,
        verification_expectations=verification_expectations,
        acceptance_sources=resolved_acceptance_sources,
        acceptance_mode=resolved_acceptance_mode,
        acceptance_scope_file=resolved_acceptance_scope_file,
        acceptance_requirements=acceptance_requirements,
        scoped_acceptance_requirements=list(acceptance_model["scoped_acceptance_requirements"]),
        scoped_acceptance_notes=list(acceptance_model["scoped_acceptance_notes"]),
        acceptance_inventory_requirements=acceptance_inventory_requirements,
        acceptance_inventory_count=int(acceptance_model["acceptance_inventory_count"]),
        acceptance_inventory_unscoped_count=int(acceptance_model["acceptance_inventory_unscoped_count"]),
        acceptance_context_only_requirement_ids=list(acceptance_model["acceptance_context_only_requirement_ids"]),
        required_acceptance_artifacts=required_acceptance_artifacts,
        acceptance_inventory_artifacts=acceptance_inventory_artifacts,
        approval_blocking_policy=approval_blocking_policy,
        review_brief=_review_brief(
            normalized,
            risk_tier,
            read_surface,
            domain_overlays,
            verification_expectations,
            resolved_acceptance_sources,
            resolved_acceptance_mode,
            resolved_acceptance_scope_file,
            acceptance_requirements,
            int(acceptance_model["acceptance_inventory_count"]),
            int(acceptance_model["acceptance_inventory_unscoped_count"]),
            required_acceptance_artifacts,
            approval_blocking_policy,
        ),
        audit_brief=_audit_brief(normalized, read_surface) if risk_tier == "high" else None,
        checks=checks,
    )


def evaluate_hard_checks(paths: list[str], tags: set[str]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    if any(_is_code_or_workflow_surface(path) for path in paths):
        git_context = detect_git_context()
        if git_context.available:
            checks.append(CheckResult(name="git_repo_required", status="pass", details=[]))
        else:
            checks.append(
                CheckResult(
                    name="git_repo_required",
                    status="fail",
                    details=[
                        "real code/workflow changes must run from a real git repository because the branch diff is the primary review boundary",
                        git_context.reason or "git repository not detected",
                    ],
                )
            )
        if git_context.available and git_context.local_push_guard_installed:
            checks.append(CheckResult(name="main_push_guard", status="pass", details=[]))
        elif git_context.available:
            details = [
                f"install the repo-managed push guard with `git config core.hooksPath {EXPECTED_GIT_HOOKS_PATH}` so direct pushes to `{PROTECTED_BRANCH}` are blocked locally",
            ]
            if not git_context.local_push_guard_present:
                details.append(f"missing repo-managed hook file `{GIT_PUSH_GUARD_PATH}`")
            if git_context.hooks_path != EXPECTED_GIT_HOOKS_PATH:
                details.append(
                    "git `core.hooksPath` is not set to `.githooks` in this clone"
                    if not git_context.hooks_path
                    else f"git `core.hooksPath` currently points to `{git_context.hooks_path}`"
                )
            checks.append(CheckResult(name="main_push_guard", status="fail", details=details))
    return checks


def _run_command(command: list[str]) -> CheckResult:
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stderr or result.stdout).strip()
    details = [line for line in output.splitlines() if line.strip()]
    return CheckResult(
        name=f"test:{command[-1]}",
        status="pass" if result.returncode == 0 else "fail",
        details=details[:20],
        command=" ".join(command),
    )


def run_validation_commands(report: GovernanceReport) -> list[CheckResult]:
    results = list(report.checks)
    for command_text in report.validation_commands:
        results.append(_run_command(command_text.split()))
    return results


def _git_changed_paths(staged: bool) -> list[str]:
    args = ["diff", "--name-only"]
    if staged:
        args.append("--cached")
    result = _git_result(args)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        raise RuntimeError(f"unable to read changed paths from git: {detail}")
    return _normalize_paths([line.strip() for line in result.stdout.splitlines() if line.strip()])


def _git_worktree_changed_paths() -> list[str]:
    result = _git_result(["status", "--porcelain"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        raise RuntimeError(f"unable to read worktree status from git: {detail}")
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        candidate = line[3:] if len(line) >= 4 else line
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1]
        candidate = candidate.strip().strip('"')
        if candidate:
            paths.append(candidate)
    return _normalize_paths(paths)


def _report_to_dict(report: GovernanceReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["checks"] = [asdict(check) for check in report.checks]
    return payload


def _render_review_bundle_markdown(
    run_manifest: dict[str, Any],
    report: GovernanceReport,
    base_branch: str,
    head_branch: str,
) -> str:
    lines = [
        f"# Local Review Bundle: {run_manifest['task_summary']}",
        "",
        "## Summary",
        f"- Task summary: {run_manifest['task_summary']}",
        f"- Review transport: `{report.review_transport}`",
        f"- Local governance role: `{report.local_governance_role}`",
        f"- Base branch: `{base_branch}`",
        f"- Head branch: `{head_branch}`",
        "",
        "## Changed Paths",
    ]
    lines.extend(f"- `{path}`" for path in report.paths)
    lines.extend(
        [
            "",
            "## Governance",
            f"- Risk tier: `{report.risk_tier}`",
            f"- Review policy: `{report.review_policy}`",
            f"- Review scope: `{report.review_scope}`",
            f"- Context policy: `{report.context_policy}`",
            "- Primary review should happen on the local branch diff for this run.",
            "- Local `/ai-change` artifacts are the review transport and reviewer setup surface.",
            "- Medium/high-risk approval requires an AI-generated independent review artifact tied to this head commit.",
            "- Independent review must challenge contract sufficiency, overfitting, and policy substitutions.",
        ]
    )
    if report.hard_requirements:
        lines.extend(["", "## Hard Requirements"])
        lines.extend(f"- {item}" for item in report.hard_requirements)
    if report.validation_commands:
        lines.extend(["", "## Validation"])
        lines.extend(f"- `{command}`" for command in report.validation_commands)
    if report.acceptance_sources:
        lines.extend(["", "## Acceptance Sources"])
        lines.extend(f"- `{path}`" for path in report.acceptance_sources)
        lines.append(f"- Acceptance mode: `{report.acceptance_mode}`")
        if report.acceptance_scope_file:
            lines.append(f"- Acceptance scope file: `{report.acceptance_scope_file}`")
    if report.acceptance_inventory_requirements:
        lines.extend(["", "## Acceptance Inventory"])
        if report.acceptance_mode == "strict":
            lines.append(
                f"- Imported acceptance requirements: {report.acceptance_inventory_count} blocking item(s)."
            )
        else:
            lines.append(
                f"- Imported acceptance inventory: {report.acceptance_inventory_count} context item(s); "
                f"scoped blocking requirements: {len(report.scoped_acceptance_requirements)}."
            )
            lines.append(f"- Unscoped inventory count: {report.acceptance_inventory_unscoped_count}")
        if report.acceptance_inventory_artifacts:
            lines.append(
                "- Inventory artifact paths: "
                + ", ".join(f"`{path}`" for path in report.acceptance_inventory_artifacts)
            )
    if report.acceptance_requirements:
        heading = "## Strict Acceptance Requirements" if report.acceptance_mode == "strict" else "## Scoped Acceptance Requirements"
        lines.extend(["", heading])
        for item in report.acceptance_requirements:
            lines.append(
                "- "
                + f"`{item['requirement_id']}` [{item['source_section']}] "
                + item["requirement_text"]
            )
            if item.get("command_text"):
                lines.append(f"  - Command evidence: `{item['command_text']}`")
            if item.get("required_artifact_paths"):
                lines.append(
                    "  - Required artifact paths: "
                    + ", ".join(f"`{path}`" for path in item["required_artifact_paths"])
                )
            if item.get("comparator_basis"):
                lines.append(f"  - Comparator basis: `{item['comparator_basis']}`")
    if report.scoped_acceptance_notes:
        lines.extend(["", "## Scoped Acceptance Notes"])
        lines.extend(f"- {item}" for item in report.scoped_acceptance_notes)
    if report.approval_blocking_policy:
        lines.extend(["", "## Approval Blocking", f"- {report.approval_blocking_policy}"])
    if report.verification_expectations:
        lines.extend(["", "## Reviewer Guidance"])
        lines.extend(f"- {item}" for item in report.verification_expectations)
    if report.advisory_notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {item}" for item in report.advisory_notes)
    lines.extend(
        [
            "",
            "## Automation",
            f"- Claude hook guard: `{HOOK_GUARD_PATH}`",
            f"- Git push guard: `{GIT_PUSH_GUARD_PATH}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _print_payload(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for key, value in payload.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for item_key, item_value in value.items():
                print(f"- {item_key}: {item_value}")
            continue
        if isinstance(value, list):
            print(f"{key}:")
            for item in value:
                print(f"- {item}")
            continue
        print(f"{key}: {value}")


def _print_text_report(report: GovernanceReport, show_review_brief: bool, show_audit_brief: bool) -> None:
    print("AI Change Governance")
    print(f"risk_tier: {report.risk_tier}")
    print(f"review_policy: {report.review_policy}")
    print(f"review_transport: {report.review_transport}")
    print(f"local_governance_role: {report.local_governance_role}")
    print(f"review_scope: {report.review_scope}")
    print(f"context_policy: {report.context_policy}")
    print("paths:")
    for path in report.paths:
        print(f"- {path}")
    if report.tags:
        print("tags:")
        for tag in report.tags:
            print(f"- {tag}")
    if report.domain_overlays:
        print("domain_overlays:")
        for item in report.domain_overlays:
            print(f"- {item}")
    if report.hard_requirements:
        print("hard_requirements:")
        for item in report.hard_requirements:
            print(f"- {item}")
    if report.advisory_notes:
        print("advisory_notes:")
        for item in report.advisory_notes:
            print(f"- {item}")
    if report.verification_expectations:
        print("verification_expectations:")
        for item in report.verification_expectations:
            print(f"- {item}")
    if report.acceptance_sources:
        print("acceptance_sources:")
        for item in report.acceptance_sources:
            print(f"- {item}")
        print(f"acceptance_mode: {report.acceptance_mode}")
        if report.acceptance_scope_file:
            print(f"acceptance_scope_file: {report.acceptance_scope_file}")
    if report.acceptance_requirements:
        print("scoped_acceptance_requirements:")
        for item in report.acceptance_requirements:
            print(f"- {item['requirement_id']}: {item['requirement_text']}")
    if report.acceptance_inventory_requirements:
        print(f"acceptance_inventory_count: {report.acceptance_inventory_count}")
        print(f"acceptance_inventory_unscoped_count: {report.acceptance_inventory_unscoped_count}")
    if report.required_acceptance_artifacts:
        print("required_acceptance_artifacts:")
        for item in report.required_acceptance_artifacts:
            print(f"- {item}")
    if report.approval_blocking_policy:
        print(f"approval_blocking_policy: {report.approval_blocking_policy}")
    if report.checks:
        print("hard_checks:")
        for check in report.checks:
            print(f"- {check.name}: {check.status}")
            for detail in check.details:
                print(f"  {detail}")
    if report.validation_commands:
        print("validation_commands:")
        for command in report.validation_commands:
            print(f"- {command}")
    if show_review_brief:
        print()
        print(report.review_brief)
    if show_audit_brief and report.audit_brief:
        print()
        print(report.audit_brief)


def start_run(
    task_summary: str,
    base_branch: str = PROTECTED_BRANCH,
    branch_name: str | None = None,
    title: str | None = None,
    execution_mode: str = DEFAULT_EXECUTION_MODE,
    autopilot_max_review_cycles: int = DEFAULT_AUTOPILOT_MAX_REVIEW_CYCLES,
    acceptance_sources: list[str] | None = None,
    acceptance_mode: str = DEFAULT_ACCEPTANCE_MODE,
    acceptance_scope_file: str | None = None,
    implementer_id: str | None = None,
    implementer_session_id: str | None = None,
) -> dict[str, Any]:
    run_id = _next_run_id()
    head_branch, branch_action = _ensure_run_branch(run_id, task_summary, base_branch, branch_name)
    git_context = detect_git_context()
    resolved_acceptance_sources = _resolve_acceptance_sources(acceptance_sources or [])
    resolved_acceptance_mode = _normalize_acceptance_mode(acceptance_mode)
    resolved_acceptance_scope_file = _resolve_acceptance_scope_file(acceptance_scope_file)
    manifest = {
        "run_id": run_id,
        "task_summary": task_summary,
        "status": "active",
        "workflow_mode": DEFAULT_WORKFLOW_MODE,
        "execution_mode": execution_mode,
        "review_transport": DEFAULT_REVIEW_TRANSPORT,
        "local_governance_role": DEFAULT_LOCAL_GOVERNANCE_ROLE,
        "git_repo_present": git_context.available,
        "base_branch": base_branch,
        "head_branch": head_branch,
        "review_title": title or task_summary,
        "acceptance_sources": resolved_acceptance_sources,
        "acceptance_mode": resolved_acceptance_mode,
        "acceptance_scope_file": resolved_acceptance_scope_file,
        "implementer_id": _normalize_identity(implementer_id, env_name=AI_CHANGE_IMPLEMENTER_ID_ENV),
        "implementer_session_id": _normalize_identity(
            implementer_session_id,
            env_name=AI_CHANGE_IMPLEMENTER_SESSION_ID_ENV,
        ),
        "review_state": DEFAULT_REVIEW_STATE,
        "pr_title": title or task_summary,
        "pr_review_state": DEFAULT_REVIEW_STATE,
        "last_checkpoint_commit": None,
        "last_checkpoint_at": None,
        "autopilot_max_review_cycles": autopilot_max_review_cycles if execution_mode == "autopilot" else None,
        "autopilot_review_cycle_count": 0 if execution_mode == "autopilot" else None,
        "autopilot_next_action": DEFAULT_AUTOPILOT_NEXT_ACTION if execution_mode == "autopilot" else None,
        "latest_review_feedback_at": None,
        "latest_review_feedback_summary": None,
        "latest_review_result": None,
        "latest_review_next_action": None,
        "latest_review_findings_count": None,
        "latest_review_blocking_findings_count": None,
        "latest_review_basis_head_commit": None,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    _save_run_manifest(manifest)
    return {
        **manifest,
        "branch_action": branch_action,
    }


def autopilot_start(
    task_summary: str,
    base_branch: str = PROTECTED_BRANCH,
    branch_name: str | None = None,
    title: str | None = None,
    max_review_cycles: int = DEFAULT_AUTOPILOT_MAX_REVIEW_CYCLES,
    acceptance_sources: list[str] | None = None,
    acceptance_mode: str = DEFAULT_ACCEPTANCE_MODE,
    acceptance_scope_file: str | None = None,
    implementer_id: str | None = None,
    implementer_session_id: str | None = None,
) -> dict[str, Any]:
    payload = start_run(
        task_summary,
        base_branch,
        branch_name,
        title,
        execution_mode="autopilot",
        autopilot_max_review_cycles=max_review_cycles,
        acceptance_sources=acceptance_sources,
        acceptance_mode=acceptance_mode,
        acceptance_scope_file=acceptance_scope_file,
        implementer_id=implementer_id,
        implementer_session_id=implementer_session_id,
    )
    payload["autopilot_next_action"] = DEFAULT_AUTOPILOT_NEXT_ACTION
    return payload


def prepare_pr(
    run_id: str,
    title: str | None,
    base_branch: str | None,
    head_branch: str | None,
    staged: bool,
    paths: list[str] | None,
    acceptance_sources: list[str] | None,
    acceptance_mode: str | None = None,
    acceptance_scope_file: str | None = None,
    branch_diff: bool = False,
) -> dict[str, Any]:
    run_manifest = _load_run_manifest(run_id)
    git_context = detect_git_context()
    if not git_context.available:
        raise ValueError("prepare-pr requires a real git repository because the local branch diff is the primary review boundary")

    resolved_base_branch = base_branch or str(run_manifest.get("base_branch") or PROTECTED_BRANCH)
    resolved_head_branch = head_branch or str(run_manifest.get("head_branch") or git_context.current_branch or "")
    if not resolved_head_branch:
        raise ValueError("prepare-pr requires `--head-branch` when git is in detached HEAD state")

    changed_paths = _normalize_paths(list(paths or []))
    if not changed_paths:
        if branch_diff:
            changed_paths = _git_branch_diff_paths(resolved_base_branch, resolved_head_branch if resolved_head_branch != git_context.current_branch else "HEAD")
        else:
            changed_paths = _git_changed_paths(staged=True) if staged else _git_worktree_changed_paths()
    if not changed_paths:
        raise ValueError("prepare-pr found no changed paths; pass `--paths` or stage/create changes first")

    resolved_acceptance_sources = _resolve_acceptance_sources(
        acceptance_sources
        if acceptance_sources is not None
        else list(run_manifest.get("acceptance_sources") or [])
    )
    resolved_acceptance_mode = _normalize_acceptance_mode(
        acceptance_mode if acceptance_mode is not None else run_manifest.get("acceptance_mode")
    )
    resolved_acceptance_scope_file = _resolve_acceptance_scope_file(
        acceptance_scope_file
        if acceptance_scope_file is not None
        else run_manifest.get("acceptance_scope_file")
    )
    report = analyze_change(
        changed_paths,
        acceptance_sources=resolved_acceptance_sources,
        acceptance_mode=resolved_acceptance_mode,
        acceptance_scope_file=resolved_acceptance_scope_file,
    )
    report_payload = _report_to_dict(report)
    review_basis_head_commit = _git_head_commit(
        resolved_head_branch if resolved_head_branch and resolved_head_branch != git_context.current_branch else "HEAD"
    )
    report_payload.update(
        {
            "run_id": run_id,
            "title": title or run_manifest.get("review_title") or run_manifest["task_summary"],
            "base_branch": resolved_base_branch,
            "head_branch": resolved_head_branch,
            "review_basis_head_commit": review_basis_head_commit,
            "generated_at": _utc_now(),
            "source_mode": "branch_diff" if branch_diff else ("staged" if staged else "worktree"),
            "workflow_mode": run_manifest.get("workflow_mode", DEFAULT_WORKFLOW_MODE),
            "hook_guard": HOOK_GUARD_PATH,
            "hook_settings": HOOK_SETTINGS_PATH,
            "git_push_guard": GIT_PUSH_GUARD_PATH,
            "git_context": asdict(git_context),
        }
    )
    _write_json(_review_manifest_path(run_id), report_payload)
    _write_text(_review_bundle_path(run_id), _render_review_bundle_markdown(run_manifest, report, resolved_base_branch, resolved_head_branch))
    run_manifest["base_branch"] = resolved_base_branch
    run_manifest["head_branch"] = resolved_head_branch
    run_manifest["review_title"] = title or run_manifest.get("review_title") or run_manifest["task_summary"]
    run_manifest["acceptance_sources"] = resolved_acceptance_sources
    run_manifest["acceptance_mode"] = resolved_acceptance_mode
    run_manifest["acceptance_scope_file"] = resolved_acceptance_scope_file
    run_manifest["pr_title"] = run_manifest["review_title"]
    _save_run_manifest(run_manifest)
    return {
        "run_id": run_id,
        "title": title or run_manifest["task_summary"],
        "workflow_mode": run_manifest.get("workflow_mode", DEFAULT_WORKFLOW_MODE),
        "review_transport": run_manifest.get("review_transport", DEFAULT_REVIEW_TRANSPORT),
        "base_branch": resolved_base_branch,
        "head_branch": resolved_head_branch,
        "review_basis_head_commit": review_basis_head_commit,
        "paths": changed_paths,
        "acceptance_sources": resolved_acceptance_sources,
        "acceptance_mode": resolved_acceptance_mode,
        "acceptance_scope_file": resolved_acceptance_scope_file,
        "acceptance_requirement_count": len(report.acceptance_requirements),
        "acceptance_inventory_count": report.acceptance_inventory_count,
        "acceptance_inventory_unscoped_count": report.acceptance_inventory_unscoped_count,
        "source_mode": "branch_diff" if branch_diff else ("staged" if staged else "worktree"),
        "review_manifest": str(_review_manifest_path(run_id)),
        "review_bundle": str(_review_bundle_path(run_id)),
        "pull_request_manifest": str(_review_manifest_path(run_id)),
        "pull_request_body": str(_review_bundle_path(run_id)),
        "hook_guard": HOOK_GUARD_PATH,
        "git_push_guard": GIT_PUSH_GUARD_PATH,
    }


def checkpoint_run(
    run_id: str,
    message: str,
    stage_all: bool,
    paths: list[str] | None,
    title: str | None,
) -> dict[str, Any]:
    run_manifest = _load_run_manifest(run_id)
    _require_run_branch(run_manifest)
    if stage_all:
        _git_stage_all()
    elif paths:
        _git_stage_paths(_normalize_paths(paths))

    staged_paths = _git_changed_paths(staged=True)
    if not staged_paths:
        raise ValueError("checkpoint requires staged changes or explicit `--paths`; it will not auto-commit the whole dirty worktree by default")

    checkpoint_commit = _git_commit(message)
    run_manifest["last_checkpoint_commit"] = checkpoint_commit
    run_manifest["last_checkpoint_at"] = _utc_now()
    _save_run_manifest(run_manifest)

    pr_payload = prepare_pr(
        run_id,
        title or str(run_manifest.get("review_title") or run_manifest.get("pr_title") or run_manifest["task_summary"]),
        str(run_manifest.get("base_branch") or PROTECTED_BRANCH),
        str(run_manifest.get("head_branch") or ""),
        staged=False,
        paths=None,
        acceptance_sources=None,
        branch_diff=True,
    )

    run_manifest = _load_run_manifest(run_id)
    review_state = str(run_manifest.get("review_state") or run_manifest.get("pr_review_state") or DEFAULT_REVIEW_STATE)
    run_manifest["review_state"] = review_state
    run_manifest["pr_review_state"] = review_state
    _save_run_manifest(run_manifest)
    return {
        "run_id": run_id,
        "checkpoint_message": message,
        "checkpoint_commit": checkpoint_commit,
        "checkpoint_mode": "all_changes" if stage_all else ("explicit_paths" if paths else DEFAULT_CHECKPOINT_MODE),
        "staged_paths": staged_paths,
        "head_branch": run_manifest.get("head_branch"),
        "base_branch": run_manifest.get("base_branch"),
        "review_state": review_state,
        "review_manifest": pr_payload["review_manifest"],
        "review_bundle": pr_payload["review_bundle"],
        "pull_request_manifest": pr_payload["pull_request_manifest"],
        "pull_request_body": pr_payload["pull_request_body"],
    }


def ready_for_review(
    run_id: str,
    title: str | None,
) -> dict[str, Any]:
    run_manifest = _load_run_manifest(run_id)
    _require_run_branch(run_manifest)
    if _git_worktree_dirty():
        raise ValueError("ready-for-review requires a clean worktree; commit or stash remaining changes before requesting review")

    pr_payload = prepare_pr(
        run_id,
        title or str(run_manifest.get("review_title") or run_manifest.get("pr_title") or run_manifest["task_summary"]),
        str(run_manifest.get("base_branch") or PROTECTED_BRANCH),
        str(run_manifest.get("head_branch") or ""),
        staged=False,
        paths=None,
        acceptance_sources=None,
        branch_diff=True,
    )

    run_manifest = _load_run_manifest(run_id)
    run_manifest["review_state"] = "ready_for_review"
    run_manifest["pr_review_state"] = "ready_for_review"
    _save_run_manifest(run_manifest)
    return {
        "run_id": run_id,
        "head_branch": run_manifest.get("head_branch"),
        "base_branch": run_manifest.get("base_branch"),
        "review_state": "ready_for_review",
        "review_manifest": pr_payload["review_manifest"],
        "review_bundle": pr_payload["review_bundle"],
        "pull_request_manifest": pr_payload["pull_request_manifest"],
        "pull_request_body": pr_payload["pull_request_body"],
    }


def _render_independent_review_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Independent AI Review",
        "",
        f"- Run id: `{payload.get('run_id')}`",
        f"- Review result: `{payload.get('review_result')}`",
        f"- Provider: `{payload.get('provider')}`",
        f"- Model: `{payload.get('model') or 'configured default'}`",
        f"- Reviewer id: `{payload.get('reviewer_id')}`",
        f"- Reviewer session id: `{payload.get('reviewer_session_id')}`",
        f"- Implementer id: `{payload.get('implementer_id')}`",
        f"- Implementer session id: `{payload.get('implementer_session_id')}`",
        f"- Review basis head commit: `{payload.get('review_basis_head_commit')}`",
        f"- Findings: {payload.get('findings_count', 0)}",
        f"- Blocking findings: {payload.get('blocking_findings_count', 0)}",
        "",
        "## Assessments",
        f"- Contract sufficiency: {payload.get('contract_sufficiency_assessment', '')}",
        f"- Overfitting: {payload.get('overfitting_assessment', '')}",
        f"- Policy substitution: {payload.get('policy_substitution_assessment', '')}",
    ]
    if payload.get("high_risk_assessment") or payload.get("architecture_sync_assessment"):
        lines.extend(
            [
                f"- High-risk assessment: {payload.get('high_risk_assessment', '')}",
                f"- Architecture sync: {payload.get('architecture_sync_assessment', '')}",
            ]
        )
    if payload.get("summary"):
        lines.extend(["", "## Summary", str(payload["summary"]).strip()])
    findings = payload.get("findings") or []
    if findings:
        lines.extend(["", "## Findings"])
        for item in findings:
            if isinstance(item, dict):
                severity = str(item.get("severity") or "finding").strip()
                text = str(
                    item.get("text")
                    or item.get("summary")
                    or item.get("title")
                    or item.get("evidence")
                    or item.get("recommendation")
                    or ""
                ).strip()
                path = str(item.get("path") or "").strip()
                location = f" `{path}`" if path else ""
                lines.append(f"- {severity}:{location} {text}".rstrip())
                if not item.get("text") and not item.get("summary"):
                    evidence = str(item.get("evidence") or "").strip()
                    recommendation = str(item.get("recommendation") or "").strip()
                    if evidence and evidence != text:
                        lines.append(f"  Evidence: {evidence}")
                    if recommendation and recommendation != text:
                        lines.append(f"  Recommendation: {recommendation}")
            else:
                lines.append(f"- {item}")
    if payload.get("paths"):
        lines.extend(["", "## Reviewed Paths"])
        lines.extend(f"- `{path}`" for path in payload["paths"])
    return "\n".join(lines).rstrip() + "\n"


def _render_independent_review_prompt(
    *,
    run_manifest: dict[str, Any],
    review_manifest_payload: dict[str, Any],
    reviewer_id: str,
    reviewer_session_id: str,
    provider: str,
    model: str | None,
) -> str:
    run_id = str(run_manifest["run_id"])
    review_json = _independent_review_path(run_id)
    review_md = _independent_review_body_path(run_id)
    base_branch = str(run_manifest.get("base_branch") or PROTECTED_BRANCH)
    head_branch = str(run_manifest.get("head_branch") or "")
    risk_tier = str(review_manifest_payload.get("risk_tier") or "medium")
    paths = list(review_manifest_payload.get("paths") or [])
    required_fields = list(INDEPENDENT_REVIEW_BASE_ASSESSMENT_FIELDS)
    if risk_tier == "high":
        required_fields.extend(INDEPENDENT_REVIEW_HIGH_RISK_ASSESSMENT_FIELDS)
    schema_hint = {
        "run_id": run_id,
        "reviewer_type": "ai",
        "provider": provider,
        "model": model or "",
        "prompt_version": INDEPENDENT_REVIEW_PROMPT_VERSION,
        "review_basis_head_commit": str(review_manifest_payload.get("review_basis_head_commit") or ""),
        "paths": paths,
        "implementer_id": str(run_manifest.get("implementer_id") or ""),
        "implementer_session_id": str(run_manifest.get("implementer_session_id") or ""),
        "reviewer_id": reviewer_id,
        "reviewer_session_id": reviewer_session_id,
        "review_result": "approved|approved_with_advisories|changes_requested|pending_local_review",
        "findings_count": 0,
        "blocking_findings_count": 0,
        "summary": "short review summary",
        "findings": [],
    }
    for field_name in required_fields:
        schema_hint[field_name] = "required substantive assessment"
    return (
        "You are an independent AI code reviewer for an `/ai-change` branch.\n"
        "Review the local branch diff and write only the requested review artifacts.\n\n"
        "<review_context>\n"
        f"Run id: {run_id}\n"
        f"Base branch: {base_branch}\n"
        f"Head branch: {head_branch}\n"
        f"Risk tier: {risk_tier}\n"
        f"Implementer id: {run_manifest.get('implementer_id')}\n"
        f"Implementer session id: {run_manifest.get('implementer_session_id')}\n"
        f"Review manifest: {_review_manifest_path(run_id)}\n"
        f"Review bundle: {_review_bundle_path(run_id)}\n"
        f"Write JSON artifact: {review_json}\n"
        f"Write markdown artifact: {review_md}\n"
        "</review_context>\n\n"
        "<instructions>\n"
        "Start from `git diff --stat` and the branch diff for the base/head pair, then open only related files needed for concrete findings.\n"
        "Apply the closest `AGENTS.md` instructions, `docs/coder_guide.md`, and the command contract before judging the diff.\n"
        "Check high-level architecture alignment against `docs/architecture.md` and any touched systemdesign contract.\n"
        "Stay focused as a reviewer: read/search/run only the commands needed to assess the diff, and do not edit tracked files or create artifacts other than the two review files above.\n"
        "Findings must prioritize correctness, regressions, risky behavior changes, contract drift, missing tests, documentation issues, provenance/security issues, and missing proportional verification.\n"
        "Pay special attention to secrets, auth, dependency changes, and other high-risk surfaces when present.\n"
        "Explicitly challenge contract sufficiency, overfitting to tests or artifact-family wording, and policy substitutions where bookkeeping replaces the real workflow boundary.\n"
        "Critically examine whether the code translates design intention into function; for example, if a function is meant to compress data for decision making, its output must not remain about the same size as the input.\n"
        "Do not report hidden chain-of-thought; provide concise evidence, file references, and the required structured fields.\n"
        "For high-risk changes, also assess domain-specific contract risk and architecture sync.\n\n"
        "</instructions>\n\n"
        "<output_schema>\n"
        "Write valid JSON matching this shape, then a concise markdown summary with the same result:\n"
        f"{json.dumps(schema_hint, ensure_ascii=False, indent=2)}\n"
        "</output_schema>\n"
    )


def conduct_independent_review(
    run_id: str,
    provider: str = DEFAULT_INDEPENDENT_REVIEW_PROVIDER,
    model: str | None = None,
    reviewer_id: str | None = None,
    reviewer_session_id: str | None = None,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    run_manifest = _load_run_manifest(run_id)
    _require_run_branch(run_manifest)
    pre_review_status_paths = _git_status_paths()
    if pre_review_status_paths:
        details = ", ".join(pre_review_status_paths[:10])
        if len(pre_review_status_paths) > 10:
            details += f", +{len(pre_review_status_paths) - 10} more"
        raise ValueError(f"independent AI review requires a clean git worktree before launch: {details}")
    resolved_reviewer_id = (
        str(reviewer_id or os.getenv(AI_CHANGE_REVIEWER_ID_ENV) or "").strip()
        or f"{provider}_independent_ai_reviewer"
    )
    resolved_reviewer_session_id = (
        str(reviewer_session_id or os.getenv(AI_CHANGE_REVIEWER_SESSION_ID_ENV) or "").strip()
        or f"independent-review-{run_id}-{_utc_now().replace(':', '').replace('-', '')}"
    )
    review_path = _independent_review_path(run_id)
    review_body_path = _independent_review_body_path(run_id)
    review_payload = prepare_pr(
        run_id,
        str(run_manifest.get("review_title") or run_manifest.get("pr_title") or run_manifest["task_summary"]),
        str(run_manifest.get("base_branch") or PROTECTED_BRANCH),
        str(run_manifest.get("head_branch") or ""),
        staged=False,
        paths=None,
        acceptance_sources=None,
        branch_diff=True,
    )
    allowed_artifact_paths = set(
        _normalize_paths(
            [
                _repo_relative_path(review_path),
                _repo_relative_path(review_body_path),
            ]
        )
    )
    pre_review_run_snapshot = _run_dir_file_snapshot(run_id)
    review_manifest_payload = _read_json(_review_manifest_path(run_id))
    profile = select_runner_profile(provider, model, "high_level")
    prompt = _render_independent_review_prompt(
        run_manifest=run_manifest,
        review_manifest_payload=review_manifest_payload,
        reviewer_id=resolved_reviewer_id,
        reviewer_session_id=resolved_reviewer_session_id,
        provider=provider,
        model=profile.model,
    )
    if codex_child_network_blocked(provider) and not codex_child_network_allowed(provider):
        raise ValueError(
            codex_child_network_failure_reason("independent AI review child run")
            + f"; set {CODEX_CHILD_NETWORK_ALLOWED_ENV}=1 only after explicitly approving a network-capable child review"
        )
    verify_provider_cli(provider)
    cmd = build_runner_command(
        provider=provider,
        root=REPO_ROOT,
        prompt=prompt,
        model=profile.model,
        max_budget=1.0,
        config_overrides=profile.config_overrides,
    )
    run_kwargs: dict[str, Any]
    if provider == "codex":
        run_kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
    else:
        run_kwargs = {"capture_output": True, "text": True}
    completed = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=build_runner_env(provider),
        timeout=timeout_seconds,
        check=False,
        **run_kwargs,
    )
    if completed.returncode != 0:
        detail = ""
        if isinstance(getattr(completed, "stderr", None), str):
            detail = completed.stderr.strip()
        if not detail and isinstance(getattr(completed, "stdout", None), str):
            detail = completed.stdout.strip()
        raise ValueError(f"independent AI review provider failed: {detail or f'exit {completed.returncode}'}")

    post_review_status_paths = _git_status_paths()
    disallowed_status_paths = [
        path for path in post_review_status_paths if path not in allowed_artifact_paths
    ]
    if disallowed_status_paths:
        details = ", ".join(disallowed_status_paths[:10])
        if len(disallowed_status_paths) > 10:
            details += f", +{len(disallowed_status_paths) - 10} more"
        raise ValueError(f"independent AI review changed tracked or unapproved worktree paths: {details}")
    disallowed_run_state_paths = _changed_snapshot_paths(
        pre_review_run_snapshot,
        _run_dir_file_snapshot(run_id),
        allowed_artifact_paths,
    )
    if disallowed_run_state_paths:
        details = ", ".join(disallowed_run_state_paths[:10])
        if len(disallowed_run_state_paths) > 10:
            details += f", +{len(disallowed_run_state_paths) - 10} more"
        raise ValueError(f"independent AI review changed ignored or run-state paths: {details}")

    if not review_path.exists():
        raise ValueError(f"independent AI review did not write `{review_path}`")
    gate = _validate_independent_review_artifact(
        run_id=run_id,
        run_manifest=run_manifest,
        review_manifest_payload=review_manifest_payload,
        review_basis_head_commit=str(review_payload.get("review_basis_head_commit") or ""),
        changed_paths=list(review_payload.get("paths") or []),
        artifact_path=str(review_path),
        reviewer_id=resolved_reviewer_id,
        reviewer_session_id=resolved_reviewer_session_id,
    )
    if gate["status"] != "pass":
        raise ValueError("independent AI review artifact failed validation: " + "; ".join(gate["errors"]))
    review_payload_json = _read_json(review_path)
    if not _string_field(review_payload_json, "generated_at"):
        review_payload_json["generated_at"] = _utc_now()
    _write_json(review_path, review_payload_json)
    _write_text(review_body_path, _render_independent_review_markdown(review_payload_json))
    return {
        "run_id": run_id,
        "review_result": gate.get("review_result"),
        "findings_count": gate.get("findings_count"),
        "blocking_findings_count": gate.get("blocking_findings_count"),
        "independent_review_status": gate.get("status"),
        "independent_review_artifact": str(review_path),
        "independent_review_body": str(review_body_path),
        "reviewer_id": resolved_reviewer_id,
        "reviewer_session_id": resolved_reviewer_session_id,
    }


def collect_review_feedback(
    run_id: str,
    review_result: str | None = None,
    findings_count: int | None = None,
    blocking_findings_count: int | None = None,
    next_action: str | None = None,
    review_notes: str | None = None,
    acceptance_evidence_file: str | None = None,
    acceptance_mode: str | None = None,
    acceptance_scope_file: str | None = None,
    reviewer_id: str | None = None,
    reviewer_session_id: str | None = None,
    independent_review_artifact: str | None = None,
) -> dict[str, Any]:
    run_manifest = _load_run_manifest(run_id)
    resolved_acceptance_mode = _normalize_acceptance_mode(
        acceptance_mode if acceptance_mode is not None else run_manifest.get("acceptance_mode")
    )
    resolved_acceptance_scope_file = _resolve_acceptance_scope_file(
        acceptance_scope_file
        if acceptance_scope_file is not None
        else run_manifest.get("acceptance_scope_file")
    )
    review_payload = prepare_pr(
        run_id,
        str(run_manifest.get("review_title") or run_manifest.get("pr_title") or run_manifest["task_summary"]),
        str(run_manifest.get("base_branch") or PROTECTED_BRANCH),
        str(run_manifest.get("head_branch") or ""),
        staged=False,
        paths=None,
        acceptance_sources=None,
        acceptance_mode=resolved_acceptance_mode,
        acceptance_scope_file=resolved_acceptance_scope_file,
        branch_diff=True,
    )
    review_manifest_payload = _read_json(_review_manifest_path(run_id))
    existing_feedback_payload = (
        _read_json(_review_feedback_path(run_id))
        if _review_feedback_path(run_id).exists()
        else {}
    )
    review_state = str(run_manifest.get("review_state") or run_manifest.get("pr_review_state") or DEFAULT_REVIEW_STATE)
    review_basis_head_commit = str(
        review_payload.get("review_basis_head_commit")
        or review_manifest_payload.get("review_basis_head_commit")
        or ""
    )
    can_carry_existing_review = (
        str(existing_feedback_payload.get("review_basis_head_commit") or "") == review_basis_head_commit
        and str(existing_feedback_payload.get("review_state") or "") == review_state
    )
    resolved_review_result, resolved_findings_count, resolved_blocking_findings_count, resolved_next_action = (
        _resolve_review_feedback_contract(
            review_state=review_state,
            requested_review_result=review_result,
            requested_findings_count=findings_count,
            requested_blocking_findings_count=blocking_findings_count,
            requested_next_action=next_action,
            carried_review_result=existing_feedback_payload.get("review_result") if can_carry_existing_review else "",
            carried_findings_count=existing_feedback_payload.get("findings_count") if can_carry_existing_review else None,
            carried_blocking_findings_count=(
                existing_feedback_payload.get("blocking_findings_count") if can_carry_existing_review else None
            ),
            carried_next_action=existing_feedback_payload.get("next_action") if can_carry_existing_review else "",
        )
    )
    acceptance_requirements = list(review_manifest_payload.get("acceptance_requirements") or [])
    scoped_acceptance_requirements = list(
        review_manifest_payload.get("scoped_acceptance_requirements") or acceptance_requirements
    )
    scoped_acceptance_notes = list(review_manifest_payload.get("scoped_acceptance_notes") or [])
    acceptance_inventory_requirements = list(review_manifest_payload.get("acceptance_inventory_requirements") or [])
    acceptance_inventory_count = int(
        review_manifest_payload.get("acceptance_inventory_count")
        or len(acceptance_inventory_requirements)
        or 0
    )
    acceptance_inventory_unscoped_count = int(
        review_manifest_payload.get("acceptance_inventory_unscoped_count") or 0
    )
    acceptance_context_only_requirement_ids = list(
        review_manifest_payload.get("acceptance_context_only_requirement_ids") or []
    )
    raw_acceptance_evidence = _load_acceptance_evidence_entries(acceptance_evidence_file)
    if raw_acceptance_evidence is None and can_carry_existing_review:
        raw_acceptance_evidence = list(existing_feedback_payload.get("acceptance_evidence") or [])
    raw_scoped_acceptance_evidence, acceptance_inventory_evidence = _split_scoped_and_context_evidence(
        raw_acceptance_evidence,
        scoped_acceptance_requirements,
        acceptance_inventory_requirements,
    )
    if raw_acceptance_evidence is None and can_carry_existing_review:
        acceptance_inventory_evidence = list(existing_feedback_payload.get("acceptance_inventory_evidence") or [])
    scoped_acceptance_evidence = _normalize_acceptance_evidence(
        scoped_acceptance_requirements,
        raw_scoped_acceptance_evidence,
    )
    (
        scoped_acceptance_gate_status,
        scoped_acceptance_missing_count,
        scoped_acceptance_fail_count,
        approval_blocking_requirement_ids,
    ) = _acceptance_gate_status(scoped_acceptance_requirements, scoped_acceptance_evidence)
    resolved_review_notes = (
        str(review_notes).strip()
        if review_notes is not None
        else (
            str(existing_feedback_payload.get("review_notes", "")).strip()
            if can_carry_existing_review
            else ""
        )
    )
    if (
        scoped_acceptance_requirements
        and resolved_review_result in {"approved", "approved_with_advisories"}
        and scoped_acceptance_gate_status in {"missing", "fail"}
    ):
        resolved_review_result = "changes_requested"
        resolved_next_action = "fix_blocking_findings"
    independent_review_gate = _validate_independent_review_artifact(
        run_id=run_id,
        run_manifest=run_manifest,
        review_manifest_payload=review_manifest_payload,
        review_basis_head_commit=review_basis_head_commit,
        changed_paths=list(review_payload["paths"]),
        artifact_path=independent_review_artifact,
        reviewer_id=reviewer_id,
        reviewer_session_id=reviewer_session_id,
    )
    artifact_result = ""
    artifact_findings_count = 0
    artifact_blocking_count = 0
    if independent_review_gate["status"] == "pass":
        artifact_result = str(independent_review_gate.get("review_result") or "")
        artifact_findings_count = int(independent_review_gate.get("findings_count") or 0)
        artifact_blocking_count = int(independent_review_gate.get("blocking_findings_count") or 0)
        resolved_findings_count = max(resolved_findings_count, artifact_findings_count)
        resolved_blocking_findings_count = max(resolved_blocking_findings_count, artifact_blocking_count)
        if artifact_result == "changes_requested" or artifact_blocking_count > 0:
            resolved_review_result = "changes_requested"
            resolved_next_action = "fix_blocking_findings"
            resolved_blocking_findings_count = max(resolved_blocking_findings_count, 1)
            resolved_findings_count = max(resolved_findings_count, resolved_blocking_findings_count)
    if resolved_review_result in {"approved", "approved_with_advisories"}:
        if independent_review_gate["status"] in {"missing", "fail"}:
            resolved_review_result = "pending_local_review"
            resolved_next_action = "conduct_local_review"
        elif independent_review_gate["status"] == "pass":
            if artifact_result == "changes_requested" or artifact_blocking_count > 0:
                resolved_review_result = "changes_requested"
                resolved_next_action = "fix_blocking_findings"
            elif artifact_result == "pending_local_review":
                resolved_review_result = "pending_local_review"
                resolved_next_action = "conduct_local_review"
            elif artifact_result == "approved_with_advisories":
                resolved_review_result = "approved_with_advisories"
                resolved_next_action = "human_merge_judgment"
            if resolved_review_result == "changes_requested":
                resolved_blocking_findings_count = max(resolved_blocking_findings_count, 1)
                resolved_findings_count = max(resolved_findings_count, resolved_blocking_findings_count)
            elif resolved_review_result == "approved_with_advisories":
                resolved_blocking_findings_count = 0
                resolved_findings_count = max(resolved_findings_count, 1)
            elif resolved_review_result == "approved" and resolved_findings_count > 0:
                resolved_review_result = "approved_with_advisories"
                resolved_next_action = "human_merge_judgment"
    summary_items = [
        f"review_result={resolved_review_result}",
        f"next_action={resolved_next_action}",
        f"code_findings={resolved_findings_count}",
        f"blocking_code_findings={resolved_blocking_findings_count}",
        f"changed_paths={len(review_payload['paths'])}",
        f"validation_commands={len(review_manifest_payload.get('validation_commands', []))}",
        f"acceptance_mode={resolved_acceptance_mode}",
        f"independent_review={independent_review_gate['status']}",
    ]
    if resolved_acceptance_mode == "strict":
        summary_items.extend(
            [
                f"acceptance_requirements={len(scoped_acceptance_requirements)}",
                f"acceptance_gate={scoped_acceptance_gate_status}",
                f"acceptance_missing={scoped_acceptance_missing_count}",
                f"acceptance_fail={scoped_acceptance_fail_count}",
            ]
        )
    else:
        summary_items.extend(
            [
                f"scoped_acceptance_requirements={len(scoped_acceptance_requirements)}",
                f"scoped_acceptance_gate={scoped_acceptance_gate_status}",
                f"scoped_acceptance_missing={scoped_acceptance_missing_count}",
                f"scoped_acceptance_fail={scoped_acceptance_fail_count}",
                f"acceptance_inventory={acceptance_inventory_count}",
                f"acceptance_inventory_unscoped={acceptance_inventory_unscoped_count}",
            ]
        )
    summary = "; ".join(summary_items)
    feedback_payload = {
        "run_id": run_id,
        "review_transport": str(run_manifest.get("review_transport") or DEFAULT_REVIEW_TRANSPORT),
        "review_state": review_state,
        "review_result": resolved_review_result,
        "findings_count": resolved_findings_count,
        "blocking_findings_count": resolved_blocking_findings_count,
        "next_action": resolved_next_action,
        "review_title": str(run_manifest.get("review_title") or run_manifest.get("pr_title") or run_manifest["task_summary"]),
        "base_branch": str(run_manifest.get("base_branch") or PROTECTED_BRANCH),
        "head_branch": str(run_manifest.get("head_branch") or ""),
        "review_basis_head_commit": review_basis_head_commit,
        "paths": list(review_payload["paths"]),
        "review_manifest": str(_review_manifest_path(run_id)),
        "review_bundle": str(_review_bundle_path(run_id)),
        "review_brief": str(review_manifest_payload.get("review_brief") or ""),
        "validation_commands": list(review_manifest_payload.get("validation_commands") or []),
        "acceptance_sources": list(review_manifest_payload.get("acceptance_sources") or []),
        "acceptance_mode": resolved_acceptance_mode,
        "acceptance_scope_file": resolved_acceptance_scope_file,
        "acceptance_requirements": acceptance_requirements,
        "acceptance_evidence": scoped_acceptance_evidence,
        "acceptance_gate_status": scoped_acceptance_gate_status,
        "acceptance_missing_count": scoped_acceptance_missing_count,
        "acceptance_fail_count": scoped_acceptance_fail_count,
        "acceptance_blocking_requirement_ids": approval_blocking_requirement_ids,
        "scoped_acceptance_requirements": scoped_acceptance_requirements,
        "scoped_acceptance_evidence": scoped_acceptance_evidence,
        "scoped_acceptance_gate_status": scoped_acceptance_gate_status,
        "scoped_acceptance_missing_count": scoped_acceptance_missing_count,
        "scoped_acceptance_fail_count": scoped_acceptance_fail_count,
        "scoped_acceptance_notes": scoped_acceptance_notes,
        "acceptance_inventory_requirements": acceptance_inventory_requirements,
        "acceptance_inventory_evidence": acceptance_inventory_evidence,
        "acceptance_inventory_count": acceptance_inventory_count,
        "acceptance_inventory_unscoped_count": acceptance_inventory_unscoped_count,
        "acceptance_context_only_requirement_ids": acceptance_context_only_requirement_ids,
        "approval_blocking_requirement_ids": approval_blocking_requirement_ids,
        "implementer_id": run_manifest.get("implementer_id"),
        "implementer_session_id": run_manifest.get("implementer_session_id"),
        "reviewer_id": independent_review_gate.get("reviewer_id"),
        "reviewer_session_id": independent_review_gate.get("reviewer_session_id"),
        "independent_review_required": independent_review_gate.get("required"),
        "independent_review_status": independent_review_gate.get("status"),
        "independent_review_artifact": independent_review_gate.get("artifact_path"),
        "independent_review_errors": list(independent_review_gate.get("errors") or []),
        "independent_review_result": independent_review_gate.get("review_result"),
        "independent_review_findings_count": independent_review_gate.get("findings_count"),
        "independent_review_blocking_findings_count": independent_review_gate.get("blocking_findings_count"),
        "review_notes": resolved_review_notes,
        "summary": summary,
        "generated_at": _utc_now(),
    }
    _write_json(_review_feedback_path(run_id), feedback_payload)
    _write_text(_review_feedback_body_path(run_id), _render_review_feedback_markdown(feedback_payload))

    if run_manifest.get("execution_mode") == "autopilot":
        run_manifest["autopilot_review_cycle_count"] = int(run_manifest.get("autopilot_review_cycle_count") or 0) + 1
        run_manifest["autopilot_next_action"] = resolved_next_action
    run_manifest["latest_review_feedback_at"] = feedback_payload["generated_at"]
    run_manifest["latest_review_feedback_summary"] = feedback_payload["summary"]
    run_manifest["latest_review_result"] = resolved_review_result
    run_manifest["latest_review_next_action"] = resolved_next_action
    run_manifest["latest_review_findings_count"] = resolved_findings_count
    run_manifest["latest_review_blocking_findings_count"] = resolved_blocking_findings_count
    run_manifest["latest_review_basis_head_commit"] = review_basis_head_commit
    _save_run_manifest(run_manifest)

    return {
        "run_id": run_id,
        "review_state": review_state,
        "review_result": resolved_review_result,
        "findings_count": resolved_findings_count,
        "blocking_findings_count": resolved_blocking_findings_count,
        "next_action": resolved_next_action,
        "summary": feedback_payload["summary"],
        "review_feedback_manifest": str(_review_feedback_path(run_id)),
        "review_feedback_body": str(_review_feedback_body_path(run_id)),
        "review_manifest": str(_review_manifest_path(run_id)),
        "review_bundle": str(_review_bundle_path(run_id)),
        "independent_review_status": independent_review_gate.get("status"),
        "independent_review_artifact": independent_review_gate.get("artifact_path"),
        "independent_review_errors": list(independent_review_gate.get("errors") or []),
    }


def status_payload(run_id: str | None) -> dict[str, Any]:
    if run_id:
        run_manifest = _load_run_manifest(run_id)
    else:
        run_manifest = _active_run_manifest()
        if run_manifest is None:
            return {"active_run": None, "runs": _list_run_ids()}

    git_context = detect_git_context()
    review_manifest = _existing_path(
        _review_manifest_path(str(run_manifest["run_id"])),
        _legacy_pr_manifest_path(str(run_manifest["run_id"])),
    )
    review_bundle = _existing_path(
        _review_bundle_path(str(run_manifest["run_id"])),
        _legacy_pr_body_path(str(run_manifest["run_id"])),
    )
    review_feedback_manifest = _review_feedback_path(str(run_manifest["run_id"]))
    review_feedback_body = _review_feedback_body_path(str(run_manifest["run_id"]))
    independent_review_manifest = _independent_review_path(str(run_manifest["run_id"]))
    independent_review_body = _independent_review_body_path(str(run_manifest["run_id"]))
    review_title = run_manifest.get("review_title") or run_manifest.get("pr_title")
    review_state = run_manifest.get("review_state") or run_manifest.get("pr_review_state", DEFAULT_REVIEW_STATE)
    return {
        "run_id": run_manifest["run_id"],
        "task_summary": run_manifest["task_summary"],
        "status": run_manifest["status"],
        "workflow_mode": run_manifest.get("workflow_mode", DEFAULT_WORKFLOW_MODE),
        "execution_mode": run_manifest.get("execution_mode", DEFAULT_EXECUTION_MODE),
        "review_transport": run_manifest.get("review_transport", DEFAULT_REVIEW_TRANSPORT),
        "local_governance_role": run_manifest.get("local_governance_role", DEFAULT_LOCAL_GOVERNANCE_ROLE),
        "base_branch": run_manifest.get("base_branch"),
        "head_branch": run_manifest.get("head_branch"),
        "review_title": review_title,
        "acceptance_sources": list(run_manifest.get("acceptance_sources") or []),
        "acceptance_mode": str(run_manifest.get("acceptance_mode") or DEFAULT_ACCEPTANCE_MODE),
        "acceptance_scope_file": run_manifest.get("acceptance_scope_file"),
        "implementer_id": run_manifest.get("implementer_id"),
        "implementer_session_id": run_manifest.get("implementer_session_id"),
        "review_state": review_state,
        "pr_title": review_title,
        "pr_review_state": review_state,
        "last_checkpoint_commit": run_manifest.get("last_checkpoint_commit"),
        "last_checkpoint_at": run_manifest.get("last_checkpoint_at"),
        "autopilot_max_review_cycles": run_manifest.get("autopilot_max_review_cycles"),
        "autopilot_review_cycle_count": run_manifest.get("autopilot_review_cycle_count"),
        "autopilot_next_action": run_manifest.get("autopilot_next_action"),
        "latest_review_feedback_at": run_manifest.get("latest_review_feedback_at"),
        "latest_review_feedback_summary": run_manifest.get("latest_review_feedback_summary"),
        "latest_review_result": run_manifest.get("latest_review_result"),
        "latest_review_next_action": run_manifest.get("latest_review_next_action"),
        "latest_review_findings_count": run_manifest.get("latest_review_findings_count"),
        "latest_review_blocking_findings_count": run_manifest.get("latest_review_blocking_findings_count"),
        "latest_review_basis_head_commit": run_manifest.get("latest_review_basis_head_commit"),
        "git_context": asdict(git_context),
        "review_manifest": str(review_manifest) if review_manifest else None,
        "review_bundle": str(review_bundle) if review_bundle else None,
        "pull_request_manifest": str(review_manifest) if review_manifest else None,
        "pull_request_body": str(review_bundle) if review_bundle else None,
        "review_feedback_manifest": str(review_feedback_manifest) if review_feedback_manifest.exists() else None,
        "review_feedback_body": str(review_feedback_body) if review_feedback_body.exists() else None,
        "independent_review_manifest": str(independent_review_manifest) if independent_review_manifest.exists() else None,
        "independent_review_body": str(independent_review_body) if independent_review_body.exists() else None,
        "hook_guard": HOOK_GUARD_PATH if (REPO_ROOT / HOOK_GUARD_PATH).exists() else None,
        "git_push_guard": GIT_PUSH_GUARD_PATH if (REPO_ROOT / GIT_PUSH_GUARD_PATH).exists() else None,
    }


def _legacy_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="repo-relative or absolute changed paths")
    parser.add_argument("--staged", action="store_true", help="read changed paths from staged git files")
    parser.add_argument("--run-checks", action="store_true", help="run the selected test commands")
    parser.add_argument("--show-review-brief", action="store_true", help="print the generated review brief")
    parser.add_argument("--show-audit-brief", action="store_true", help="print the generated audit brief when required")
    parser.add_argument("--acceptance-mode", choices=sorted(VALID_ACCEPTANCE_MODES), default=DEFAULT_ACCEPTANCE_MODE)
    parser.add_argument("--acceptance-scope-file")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    parser.add_argument("--write-report", help="optional output path for the generated report")
    args = parser.parse_args(argv)

    try:
        paths = list(args.paths) or (_git_changed_paths(staged=args.staged) if args.staged else [])
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not paths:
        print("no changed paths supplied; pass explicit paths or use --staged", file=sys.stderr)
        return 2

    report = analyze_change(
        paths,
        acceptance_mode=args.acceptance_mode,
        acceptance_scope_file=args.acceptance_scope_file,
    )
    if args.run_checks:
        report.checks = run_validation_commands(report)

    if args.write_report:
        _write_json(Path(args.write_report), _report_to_dict(report))

    if args.format == "json":
        print(json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2))
    else:
        _print_text_report(report, args.show_review_brief, args.show_audit_brief)

    return 0 if all(check.status == "pass" for check in report.checks) else 1


def _subcommand_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    autopilot = subparsers.add_parser("autopilot")
    autopilot.add_argument("--task-summary", required=True)
    autopilot.add_argument("--base-branch", default="main")
    autopilot.add_argument("--head-branch")
    autopilot.add_argument("--title")
    autopilot.add_argument("--acceptance-source", nargs="*")
    autopilot.add_argument("--acceptance-mode", choices=sorted(VALID_ACCEPTANCE_MODES), default=DEFAULT_ACCEPTANCE_MODE)
    autopilot.add_argument("--acceptance-scope-file")
    autopilot.add_argument("--implementer-id")
    autopilot.add_argument("--implementer-session-id")
    autopilot.add_argument("--max-review-cycles", type=int, default=DEFAULT_AUTOPILOT_MAX_REVIEW_CYCLES)
    autopilot.add_argument("--format", choices=("text", "json"), default="text")

    start = subparsers.add_parser("start-run")
    start.add_argument("--task-summary", required=True)
    start.add_argument("--base-branch", default="main")
    start.add_argument("--head-branch")
    start.add_argument("--title")
    start.add_argument("--acceptance-source", nargs="*")
    start.add_argument("--acceptance-mode", choices=sorted(VALID_ACCEPTANCE_MODES), default=DEFAULT_ACCEPTANCE_MODE)
    start.add_argument("--acceptance-scope-file")
    start.add_argument("--implementer-id")
    start.add_argument("--implementer-session-id")
    start.add_argument("--format", choices=("text", "json"), default="text")

    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.add_argument("--run-id", required=True)
    checkpoint.add_argument("--message", required=True)
    checkpoint.add_argument("--all", action="store_true")
    checkpoint.add_argument("--paths", nargs="*")
    checkpoint.add_argument("--title")
    checkpoint.add_argument("--format", choices=("text", "json"), default="text")

    prepare = subparsers.add_parser("prepare-pr")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--title")
    prepare.add_argument("--base-branch", default="main")
    prepare.add_argument("--head-branch")
    prepare.add_argument("--staged", action="store_true")
    prepare.add_argument("--branch-diff", action="store_true")
    prepare.add_argument("--paths", nargs="*")
    prepare.add_argument("--acceptance-source", nargs="*")
    prepare.add_argument("--acceptance-mode", choices=sorted(VALID_ACCEPTANCE_MODES))
    prepare.add_argument("--acceptance-scope-file")
    prepare.add_argument("--format", choices=("text", "json"), default="text")

    ready = subparsers.add_parser("ready-for-review")
    ready.add_argument("--run-id", required=True)
    ready.add_argument("--title")
    ready.add_argument("--format", choices=("text", "json"), default="text")

    independent_review = subparsers.add_parser("independent-review")
    independent_review.add_argument("--run-id", required=True)
    independent_review.add_argument("--provider", default=DEFAULT_INDEPENDENT_REVIEW_PROVIDER, choices=("claude", "codex"))
    independent_review.add_argument("--model")
    independent_review.add_argument("--reviewer-id")
    independent_review.add_argument("--reviewer-session-id")
    independent_review.add_argument("--timeout-seconds", type=int, default=900)
    independent_review.add_argument("--format", choices=("text", "json"), default="text")

    review_feedback = subparsers.add_parser("review-feedback")
    review_feedback.add_argument("--run-id", required=True)
    review_feedback.add_argument("--review-result", choices=sorted(VALID_REVIEW_RESULTS))
    review_feedback.add_argument("--findings-count", type=int)
    review_feedback.add_argument("--blocking-findings-count", type=int)
    review_feedback.add_argument("--next-action", choices=sorted(VALID_REVIEW_NEXT_ACTIONS))
    review_feedback.add_argument("--review-notes")
    review_feedback.add_argument("--acceptance-evidence-file")
    review_feedback.add_argument("--acceptance-mode", choices=sorted(VALID_ACCEPTANCE_MODES))
    review_feedback.add_argument("--acceptance-scope-file")
    review_feedback.add_argument("--reviewer-id")
    review_feedback.add_argument("--reviewer-session-id")
    review_feedback.add_argument("--independent-review-artifact")
    review_feedback.add_argument("--format", choices=("text", "json"), default="text")

    status = subparsers.add_parser("status")
    status.add_argument("--run-id")
    status.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)
    try:
        if args.command == "autopilot":
            payload = autopilot_start(
                args.task_summary,
                args.base_branch,
                args.head_branch,
                args.title,
                args.max_review_cycles,
                list(args.acceptance_source or []),
                args.acceptance_mode,
                args.acceptance_scope_file,
                args.implementer_id,
                args.implementer_session_id,
            )
        elif args.command == "start-run":
            payload = start_run(
                args.task_summary,
                args.base_branch,
                args.head_branch,
                args.title,
                acceptance_sources=list(args.acceptance_source or []),
                acceptance_mode=args.acceptance_mode,
                acceptance_scope_file=args.acceptance_scope_file,
                implementer_id=args.implementer_id,
                implementer_session_id=args.implementer_session_id,
            )
        elif args.command == "checkpoint":
            payload = checkpoint_run(
                args.run_id,
                args.message,
                args.all,
                list(args.paths or []),
                args.title,
            )
        elif args.command == "prepare-pr":
            payload = prepare_pr(
                args.run_id,
                args.title,
                args.base_branch,
                args.head_branch,
                args.staged,
                list(args.paths or []),
                list(args.acceptance_source or []),
                args.acceptance_mode,
                args.acceptance_scope_file,
                args.branch_diff,
            )
        elif args.command == "ready-for-review":
            payload = ready_for_review(args.run_id, args.title)
        elif args.command == "independent-review":
            payload = conduct_independent_review(
                args.run_id,
                args.provider,
                args.model,
                args.reviewer_id,
                args.reviewer_session_id,
                args.timeout_seconds,
            )
        elif args.command == "review-feedback":
            payload = collect_review_feedback(
                args.run_id,
                args.review_result,
                args.findings_count,
                args.blocking_findings_count,
                args.next_action,
                args.review_notes,
                args.acceptance_evidence_file,
                args.acceptance_mode,
                args.acceptance_scope_file,
                args.reviewer_id,
                args.reviewer_session_id,
                args.independent_review_artifact,
            )
        else:
            payload = status_payload(args.run_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    _print_payload(payload, args.format)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        active = _active_run_manifest()
        if active is not None:
            _print_payload(status_payload(str(active["run_id"])), "text")
            return 0
        return _legacy_main(argv)
    if argv[0] in SUBCOMMANDS:
        return _subcommand_main(argv)
    return _legacy_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
