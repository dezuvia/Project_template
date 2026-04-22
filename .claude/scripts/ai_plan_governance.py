#!/usr/bin/env python3
"""Planning artifact manager for `/ai-plan` governance."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / ".claude" / "ai_plan_runs"
VALID_DEPTHS = {"auto", "minimal", "standard", "deep"}
RESOLVED_DEPTHS = {"minimal", "standard", "deep"}
REQUIRED_ARTIFACTS = [
    "run_manifest.json",
    "input_summary.md",
    "plan_trace.json",
    "decision_surface_inventory.json",
    "implementation_slices.md",
    "acceptance_scope.json",
    "required_checks.md",
    "open_policy_questions.md",
    "ai_change_handoff.json",
    "ai_change_handoff.md",
]
DEEP_REVIEW_LANES = {
    "architecture": ("architecture_review.json", "architecture_review.md"),
    "harness": ("harness_review.json", "harness_review.md"),
    "llm_delegation": ("llm_delegation_review.json", "llm_delegation_review.md"),
}
TRACE_COLLECTIONS = ("requirements", "decisions", "risks", "implementation_slices", "acceptance_requirements")


@dataclass
class ValidationResult:
    run_id: str
    status: str
    errors: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "plan"


def _repo_path(path: str | Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        except ValueError:
            return candidate.as_posix()
    text = candidate.as_posix()
    return text[2:] if text.startswith("./") else text


def _run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def _json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _new_run_id(title: str) -> str:
    base = f"ai-plan-{_timestamp()}-{_slugify(title)}"
    run_id = base
    suffix = 2
    while _run_dir(run_id).exists():
        run_id = f"{base}-{suffix}"
        suffix += 1
    return run_id


def _load_summary(source_summary_file: str | None) -> str | None:
    if not source_summary_file:
        return None
    path = Path(source_summary_file)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.read_text(encoding="utf-8").strip()


def _source_excerpt(path: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if not candidate.exists():
        return f"- `{path}` (missing at planning time)"
    lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    headings = [line.strip() for line in lines if line.lstrip().startswith("#")]
    if headings:
        return f"- `{path}`: " + "; ".join(headings[:5])
    nonempty = [line.strip() for line in lines if line.strip()]
    return f"- `{path}`: " + " ".join(nonempty[:3])[:300]


def _source_mode(planning_request: str | None, plan_sources: list[str], from_conversation: bool) -> str:
    if from_conversation and plan_sources:
        return "mixed"
    if from_conversation:
        return "conversation"
    if plan_sources and planning_request:
        return "mixed"
    if plan_sources:
        return "plan_source"
    return "request"


def _resolve_depth(requested_depth: str, planning_request: str, plan_sources: list[str]) -> tuple[str, str, str]:
    if requested_depth != "auto":
        return (
            requested_depth,
            "explicit",
            f"Depth was explicitly requested as `{requested_depth}`.",
        )

    combined = " ".join([planning_request.lower(), " ".join(plan_sources).lower()])
    deep_terms = (
        "command",
        "governance",
        "systemdesign",
        "architecture",
        "prompt",
        "harness",
        "review",
        "evaluation",
        "multi-agent",
        "llm",
        "semantic",
        "workflow",
        "template",
        "acceptance scope",
    )
    minimal_terms = ("typo", "spelling", "copyedit", "one-line", "one line", "narrow docs")
    if any(term in combined for term in deep_terms):
        return (
            "deep",
            "deterministic_scaffold_from_explicit_surfaces",
            "Explicit request/source surfaces touch command, governance, review, prompt, architecture, or template planning concerns; deep mode is the conservative scaffold.",
        )
    if any(term in combined for term in minimal_terms):
        return (
            "minimal",
            "deterministic_scaffold_from_obvious_mechanical_request",
            "The request shape is an obvious narrow mechanical edit; minimal mode is sufficient unless chat planning finds hidden scope.",
        )
    return (
        "standard",
        "deterministic_scaffold_default",
        "No deep trigger or obvious mechanical-only request was present; standard mode is the default scaffold for normal programming work.",
    )


def _input_summary(title: str, planning_request: str, plan_sources: list[str], source_summary: str | None) -> str:
    lines = [f"# {title}", ""]
    if planning_request:
        lines.extend(["## Planning Request", "", planning_request.strip(), ""])
    if source_summary:
        lines.extend(["## Source Summary", "", source_summary.strip(), ""])
    if plan_sources:
        lines.extend(["## Plan Sources", ""])
        lines.extend(_source_excerpt(path) for path in plan_sources)
        lines.append("")
    return "\n".join(lines)


def _acceptance_source_paths(run_id: str, plan_sources: list[str]) -> list[str]:
    if plan_sources:
        return plan_sources
    return [f".claude/ai_plan_runs/{run_id}/input_summary.md"]


def _core_requirements(depth: str, title: str, source_label: str) -> list[dict[str, Any]]:
    requirements = [
        {
            "id": "PLAN-REQ-001",
            "kind": "requirement",
            "source": source_label,
            "claim": f"Create a durable planning trace and `/ai-change` handoff for {title}.",
            "root_cause": "Implementation governance needs a reviewed intent record before branch-diff review can enforce acceptance.",
            "architecture_surfaces": ["docs/systemdesign/architect_ai_plan/index.json"],
            "decision_surface": "hybrid",
            "implementation_slice_ids": ["SLICE-001"],
            "acceptance_requirement_ids": ["ACCEPT-001"],
            "harness_evidence": ["python3 .claude/scripts/ai_plan_governance.py validate --run-id <run_id>"],
            "status": "planned",
        }
    ]
    if depth in {"standard", "deep"}:
        requirements.append(
            {
                "id": "PLAN-REQ-002",
                "kind": "requirement",
                "source": source_label,
                "claim": "Classify meaningful behavior decisions as deterministic, generative, or hybrid.",
                "root_cause": "Ambiguous planning decisions need explicit generative ownership instead of brittle deterministic substitutes.",
                "architecture_surfaces": ["docs/systemdesign/architect_ai_plan/index.json"],
                "decision_surface": "generative",
                "implementation_slice_ids": ["SLICE-001"],
                "acceptance_requirement_ids": ["ACCEPT-002"],
                "harness_evidence": ["decision_surface_inventory.json"],
                "status": "planned",
            }
        )
    if depth == "deep":
        requirements.append(
            {
                "id": "PLAN-REQ-003",
                "kind": "requirement",
                "source": source_label,
                "claim": "Run architecture, harness-engineering, and LLM-delegation review lanes before final implementation handoff.",
                "root_cause": "Workflow, prompt, review, and semantic planning changes need independent planning review before coding starts.",
                "architecture_surfaces": ["docs/systemdesign/architect_ai_plan/index.json"],
                "decision_surface": "generative",
                "implementation_slice_ids": ["SLICE-002"],
                "acceptance_requirement_ids": ["ACCEPT-003"],
                "harness_evidence": [
                    "architecture_review.json",
                    "harness_review.json",
                    "llm_delegation_review.json",
                ],
                "status": "planned",
            }
        )
    return requirements


def _decisions(depth: str) -> list[dict[str, Any]]:
    decisions = [
        {
            "id": "PLAN-DEC-001",
            "description": "Planning artifacts and `/ai-change` handoff paths are validated deterministically.",
            "decision_surface": "deterministic",
            "implementation_owner": "script",
            "implementation_mode": "deterministic",
            "safety_justification": "File existence, JSON shape, id uniqueness, and path references are mechanically knowable.",
        }
    ]
    if depth in {"standard", "deep"}:
        decisions.append(
            {
                "id": "PLAN-DEC-002",
                "description": "Semantic planning judgments are classified and assigned to planner or AI review ownership.",
                "decision_surface": "generative",
                "implementation_owner": "planner",
                "implementation_mode": "generative",
                "safety_justification": None,
            }
        )
    if depth == "deep":
        decisions.append(
            {
                "id": "PLAN-DEC-003",
                "description": "Deep-mode architecture, harness, and LLM-delegation review lanes must complete before validation passes.",
                "decision_surface": "generative",
                "implementation_owner": "ai_reviewer",
                "implementation_mode": "generative",
                "safety_justification": None,
            }
        )
    return decisions


def _acceptance_requirements(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements, start=1):
        req_id = f"ACCEPT-{index:03d}"
        items.append(
            {
                "id": req_id,
                "requirement_id": req_id,
                "trace_requirement_ids": [requirement["id"]],
                "requirement_text": requirement["claim"],
                "evidence_type": "artifact" if index == 1 else "review",
                "required_artifact_paths": requirement.get("harness_evidence", []),
                "command_text": None,
                "approval_blocking": True,
            }
        )
    return items


def _slices(depth: str, title: str, source_paths: list[str], acceptance_ids: list[str]) -> list[dict[str, Any]]:
    owned_surfaces = source_paths or ["Generated implementation surfaces selected by `/ai-change`"]
    if depth == "deep":
        return [
            {
                "id": "SLICE-001",
                "title": "Plan contracts and traceability",
                "owned_surfaces": owned_surfaces,
                "depends_on": [],
                "ai_change_task_summary": f"Implement planning contract and traceability surfaces for {title}.",
                "acceptance_requirement_ids": acceptance_ids[:2],
                "required_checks": ["python3 .claude/scripts/ai_plan_governance.py validate --run-id <run_id>"],
                "review_risk": "medium",
                "stop_conditions": ["Checkpoint and review before implementation-manager behavior changes."],
            },
            {
                "id": "SLICE-002",
                "title": "Deep review lanes and handoff",
                "owned_surfaces": owned_surfaces,
                "depends_on": ["SLICE-001"],
                "ai_change_task_summary": f"Implement deep planning review-lane validation and `/ai-change` handoff for {title}.",
                "acceptance_requirement_ids": acceptance_ids,
                "required_checks": ["python3 .claude/scripts/ai_plan_governance.py validate --run-id <run_id>"],
                "review_risk": "medium",
                "stop_conditions": ["Do not begin `/ai-change` implementation until deep review artifacts validate."],
            },
        ]
    return [
        {
            "id": "SLICE-001",
            "title": title,
            "owned_surfaces": owned_surfaces,
            "depends_on": [],
            "ai_change_task_summary": f"Implement {title}.",
            "acceptance_requirement_ids": acceptance_ids,
            "required_checks": ["python3 .claude/scripts/ai_plan_governance.py validate --run-id <run_id>"],
            "review_risk": "low" if depth == "minimal" else "medium",
            "stop_conditions": ["Stop for policy decision if scoped acceptance cannot be evidenced."],
        }
    ]


def _build_trace(run_id: str, depth: str, title: str, source_label: str, source_paths: list[str]) -> dict[str, Any]:
    requirements = _core_requirements(depth, title, source_label)
    acceptance = _acceptance_requirements(requirements)
    slices = _slices(depth, title, source_paths, [item["id"] for item in acceptance])
    return {
        "run_id": run_id,
        "requirements": requirements,
        "decisions": _decisions(depth),
        "risks": [
            {
                "id": "PLAN-RISK-001",
                "description": "Implementation may begin before scoped planning acceptance is validated.",
                "mitigation": "Use the emitted acceptance scope file in `/ai-change autopilot`.",
                "status": "planned",
            }
        ],
        "implementation_slices": slices,
        "acceptance_requirements": acceptance,
    }


def _decision_inventory(run_id: str, trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "generated_at": _utc_now(),
        "decisions": trace.get("decisions", []),
    }


def _acceptance_scope(run_id: str, trace: dict[str, Any]) -> dict[str, Any]:
    requirements = []
    for item in trace.get("acceptance_requirements", []):
        requirements.append(
            {
                "requirement_id": item["id"],
                "requirement_text": item["requirement_text"],
                "trace_requirement_ids": item.get("trace_requirement_ids", []),
                "evidence_type": item.get("evidence_type", "assertion"),
                "required_artifact_paths": item.get("required_artifact_paths", []),
                "command_text": item.get("command_text"),
                "approval_blocking": True,
            }
        )
    return {
        "run_id": run_id,
        "requirements": requirements,
    }


def _required_checks_markdown(trace: dict[str, Any]) -> str:
    checks: list[str] = []
    for item in trace.get("implementation_slices", []):
        checks.extend(str(check) for check in item.get("required_checks", []))
    unique = []
    for check in checks:
        if check not in unique:
            unique.append(check)
    lines = ["# Required Checks", ""]
    lines.extend(f"- `{check}`" for check in unique)
    return "\n".join(lines)


def _slices_markdown(trace: dict[str, Any]) -> str:
    lines = ["# Implementation Slices", ""]
    for item in trace.get("implementation_slices", []):
        lines.extend(
            [
                f"## {item['id']}: {item['title']}",
                "",
                f"- Task: {item['ai_change_task_summary']}",
                f"- Owned surfaces: {', '.join(item.get('owned_surfaces', []))}",
                f"- Acceptance ids: {', '.join(item.get('acceptance_requirement_ids', []))}",
                f"- Review risk: {item.get('review_risk', 'medium')}",
                "",
            ]
        )
    return "\n".join(lines)


def _open_questions_markdown(depth: str) -> str:
    if depth == "minimal":
        return "# Open Policy Questions\n\n- None recorded for this minimal planning run."
    if depth == "standard":
        return "# Open Policy Questions\n\n- None blocking. Escalate if implementation uncovers a semantic policy choice."
    return (
        "# Open Policy Questions\n\n"
        "- Blocking until deep review artifacts are present if architecture, harness, or LLM-delegation review finds changes requested."
    )


def _handoff(run_id: str, trace: dict[str, Any], acceptance_sources: list[str]) -> dict[str, Any]:
    scope_file = f".claude/ai_plan_runs/{run_id}/acceptance_scope.json"
    slices = trace.get("implementation_slices", [])
    commands = []
    sources = acceptance_sources or [f".claude/ai_plan_runs/{run_id}/input_summary.md"]
    source_args = " ".join(f"--acceptance-source {source}" for source in sources)
    for item in slices:
        command = (
            f"/ai-change autopilot \"{item['ai_change_task_summary']}\" "
            f"{source_args} --acceptance-scope-file {scope_file}"
        )
        commands.append(command)
    return {
        "run_id": run_id,
        "acceptance_sources": sources,
        "acceptance_scope_file": scope_file,
        "slices": slices,
        "commands": commands,
    }


def _handoff_markdown(payload: dict[str, Any]) -> str:
    lines = ["# `/ai-change` Handoff", ""]
    for command in payload.get("commands", []):
        lines.extend(["```text", command, "```", ""])
    return "\n".join(lines)


def _manifest_artifacts(run_id: str) -> list[str]:
    return [f".claude/ai_plan_runs/{run_id}/{name}" for name in REQUIRED_ARTIFACTS]


def autopilot_run(
    *,
    planning_request: str | None,
    plan_sources: list[str],
    source_summary_file: str | None,
    depth: str,
    title: str | None,
    from_conversation: bool = False,
) -> dict[str, Any]:
    if depth not in VALID_DEPTHS:
        raise ValueError(f"unknown depth `{depth}`")
    normalized_sources = [_repo_path(path) for path in plan_sources]
    for source in normalized_sources:
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = REPO_ROOT / source_path
        if not source_path.exists():
            raise ValueError(f"plan source `{source}` does not exist")
    request_text = (planning_request or "").strip()
    source_summary = _load_summary(source_summary_file)
    resolved_title = (title or request_text or "AI planning run").strip()
    resolved_depth, classification_method, depth_rationale = _resolve_depth(depth, request_text, normalized_sources)
    run_id = _new_run_id(resolved_title)
    run_dir = _run_dir(run_id)
    source_mode = _source_mode(request_text or None, normalized_sources, from_conversation)
    source_label = ", ".join(normalized_sources) if normalized_sources else f"{source_mode}:{run_id}"
    trace = _build_trace(run_id, resolved_depth, resolved_title, source_label, normalized_sources)
    acceptance_sources = _acceptance_source_paths(run_id, normalized_sources)
    handoff = _handoff(run_id, trace, acceptance_sources)
    manifest = {
        "run_id": run_id,
        "title": resolved_title,
        "status": "active",
        "source_mode": source_mode,
        "requested_depth": depth,
        "depth": resolved_depth,
        "depth_rationale": depth_rationale,
        "depth_classification_method": classification_method,
        "source_paths": normalized_sources,
        "reviewed_repo_root": str(REPO_ROOT),
        "generated_artifact_paths": _manifest_artifacts(run_id),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }

    _json_write(run_dir / "run_manifest.json", manifest)
    _text_write(run_dir / "input_summary.md", _input_summary(resolved_title, request_text, normalized_sources, source_summary))
    _json_write(run_dir / "plan_trace.json", trace)
    _json_write(run_dir / "decision_surface_inventory.json", _decision_inventory(run_id, trace))
    _text_write(run_dir / "implementation_slices.md", _slices_markdown(trace))
    _json_write(run_dir / "acceptance_scope.json", _acceptance_scope(run_id, trace))
    _text_write(run_dir / "required_checks.md", _required_checks_markdown(trace))
    _text_write(run_dir / "open_policy_questions.md", _open_questions_markdown(resolved_depth))
    _json_write(run_dir / "ai_change_handoff.json", handoff)
    _text_write(run_dir / "ai_change_handoff.md", _handoff_markdown(handoff))
    return manifest


def _load_manifest(run_id: str) -> dict[str, Any]:
    path = _run_dir(run_id) / "run_manifest.json"
    if not path.exists():
        raise ValueError(f"unknown ai-plan run `{run_id}`")
    payload = _json_load(path)
    if not isinstance(payload, dict):
        raise ValueError(f"run manifest for `{run_id}` is not a JSON object")
    return payload


def _latest_run_id() -> str | None:
    manifests = sorted(RUNS_DIR.glob("*/run_manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not manifests:
        return None
    return manifests[0].parent.name


def _collect_ids(trace: dict[str, Any], errors: list[str]) -> tuple[set[str], set[str], set[str]]:
    all_ids: list[str] = []
    requirement_ids: set[str] = set()
    slice_ids: set[str] = set()
    acceptance_ids: set[str] = set()
    for collection in TRACE_COLLECTIONS:
        value = trace.get(collection, [])
        if not isinstance(value, list):
            errors.append(f"`plan_trace.json` field `{collection}` must be a list")
            continue
        for item in value:
            if not isinstance(item, dict):
                errors.append(f"`plan_trace.json` field `{collection}` contains a non-object item")
                continue
            item_id = str(item.get("id") or item.get("requirement_id") or "").strip()
            if not item_id:
                errors.append(f"`plan_trace.json` field `{collection}` contains an item without id")
                continue
            all_ids.append(item_id)
            if collection == "requirements":
                requirement_ids.add(item_id)
            elif collection == "implementation_slices":
                slice_ids.add(item_id)
            elif collection == "acceptance_requirements":
                acceptance_ids.add(item_id)
    duplicates = sorted({item_id for item_id in all_ids if all_ids.count(item_id) > 1})
    for item_id in duplicates:
        errors.append(f"duplicate trace id `{item_id}`")
    return requirement_ids, slice_ids, acceptance_ids


def _validate_trace_references(
    trace: dict[str, Any],
    requirement_ids: set[str],
    slice_ids: set[str],
    acceptance_ids: set[str],
    errors: list[str],
) -> None:
    for requirement in trace.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        for slice_id in requirement.get("implementation_slice_ids", []):
            if slice_id not in slice_ids:
                errors.append(f"requirement `{requirement.get('id')}` references unknown slice `{slice_id}`")
        for acceptance_id in requirement.get("acceptance_requirement_ids", []):
            if acceptance_id not in acceptance_ids:
                errors.append(f"requirement `{requirement.get('id')}` references unknown acceptance `{acceptance_id}`")
    for item in trace.get("implementation_slices", []):
        if not isinstance(item, dict):
            continue
        for acceptance_id in item.get("acceptance_requirement_ids", []):
            if acceptance_id not in acceptance_ids:
                errors.append(f"slice `{item.get('id')}` references unknown acceptance `{acceptance_id}`")
        for dependency in item.get("depends_on", []):
            if dependency not in slice_ids:
                errors.append(f"slice `{item.get('id')}` references unknown dependency `{dependency}`")


def _validate_acceptance_scope(
    run_dir: Path,
    requirement_ids: set[str],
    acceptance_ids: set[str],
    errors: list[str],
) -> None:
    payload = _json_load(run_dir / "acceptance_scope.json")
    if not isinstance(payload, dict):
        errors.append("`acceptance_scope.json` must contain a JSON object")
        return
    requirements = payload.get("requirements", [])
    if not isinstance(requirements, list):
        errors.append("`acceptance_scope.json` field `requirements` must be a list")
        return
    for item in requirements:
        if not isinstance(item, dict):
            errors.append("`acceptance_scope.json` contains a non-object requirement")
            continue
        requirement_id = str(item.get("requirement_id") or "").strip()
        if requirement_id not in acceptance_ids:
            errors.append(f"acceptance scope references unknown acceptance requirement `{requirement_id}`")
        for trace_id in item.get("trace_requirement_ids", []):
            if trace_id not in requirement_ids:
                errors.append(f"acceptance scope requirement `{requirement_id}` references unknown trace requirement `{trace_id}`")


def _validate_decisions(run_dir: Path, errors: list[str]) -> None:
    payload = _json_load(run_dir / "decision_surface_inventory.json")
    decisions = payload.get("decisions", []) if isinstance(payload, dict) else []
    if not isinstance(decisions, list):
        errors.append("`decision_surface_inventory.json` field `decisions` must be a list")
        return
    for item in decisions:
        if not isinstance(item, dict):
            errors.append("`decision_surface_inventory.json` contains a non-object decision")
            continue
        surface = str(item.get("decision_surface") or "").strip()
        mode = str(item.get("implementation_mode") or "").strip()
        justification = str(item.get("safety_justification") or "").strip()
        if surface not in {"deterministic", "generative", "hybrid"}:
            errors.append(f"decision `{item.get('id')}` has invalid decision_surface `{surface}`")
        if mode not in {"deterministic", "generative", "hybrid"}:
            errors.append(f"decision `{item.get('id')}` has invalid implementation_mode `{mode}`")
        if surface == "generative" and mode == "deterministic" and not justification:
            errors.append(
                f"decision `{item.get('id')}` assigns a generative decision to deterministic implementation without safety justification"
            )


def _validate_handoff(run_dir: Path, run_id: str, errors: list[str]) -> None:
    payload = _json_load(run_dir / "ai_change_handoff.json")
    if not isinstance(payload, dict):
        errors.append("`ai_change_handoff.json` must contain a JSON object")
        return
    expected_scope = f".claude/ai_plan_runs/{run_id}/acceptance_scope.json"
    if payload.get("acceptance_scope_file") != expected_scope:
        errors.append("`ai_change_handoff.json` does not reference this run's acceptance_scope.json")
    commands = payload.get("commands", [])
    if not isinstance(commands, list) or not commands:
        errors.append("`ai_change_handoff.json` must include at least one handoff command")
    elif not all(expected_scope in str(command) for command in commands):
        errors.append("every handoff command must include the acceptance scope file")


def _validate_deep_reviews(run_dir: Path, run_id: str, errors: list[str]) -> None:
    for lane, (json_name, md_name) in DEEP_REVIEW_LANES.items():
        json_path = run_dir / json_name
        md_path = run_dir / md_name
        if not json_path.exists():
            errors.append(f"deep planning review artifact `{json_name}` is missing")
            continue
        if not md_path.exists():
            errors.append(f"deep planning review artifact `{md_name}` is missing")
        payload = _json_load(json_path)
        if not isinstance(payload, dict):
            errors.append(f"`{json_name}` must contain a JSON object")
            continue
        if payload.get("run_id") != run_id:
            errors.append(f"`{json_name}` run_id does not match `{run_id}`")
        if payload.get("review_lane") not in {lane, lane.replace("_", "-")}:
            errors.append(f"`{json_name}` review_lane does not match `{lane}`")
        result = payload.get("review_result")
        if result not in {"pass", "pass_with_advisories", "changes_requested"}:
            errors.append(f"`{json_name}` has invalid review_result `{result}`")
        if result == "changes_requested" or int(payload.get("blocking_findings_count") or 0) > 0:
            errors.append(f"`{json_name}` records blocking planning findings")


def validate_run(run_id: str) -> ValidationResult:
    manifest = _load_manifest(run_id)
    run_dir = _run_dir(run_id)
    errors: list[str] = []
    warnings: list[str] = []
    for name in REQUIRED_ARTIFACTS:
        if not (run_dir / name).exists():
            errors.append(f"required artifact `{name}` is missing")
    if errors:
        result = ValidationResult(run_id, "fail", errors, warnings)
        _write_feedback(run_dir, manifest, result)
        return result

    trace = _json_load(run_dir / "plan_trace.json")
    if not isinstance(trace, dict):
        errors.append("`plan_trace.json` must contain a JSON object")
        requirement_ids: set[str] = set()
        slice_ids: set[str] = set()
        acceptance_ids: set[str] = set()
    else:
        requirement_ids, slice_ids, acceptance_ids = _collect_ids(trace, errors)
        _validate_trace_references(trace, requirement_ids, slice_ids, acceptance_ids, errors)
    _validate_acceptance_scope(run_dir, requirement_ids, acceptance_ids, errors)
    _validate_decisions(run_dir, errors)
    _validate_handoff(run_dir, run_id, errors)
    if manifest.get("depth") == "deep":
        _validate_deep_reviews(run_dir, run_id, errors)

    result = ValidationResult(run_id, "fail" if errors else "pass", errors, warnings)
    _write_feedback(run_dir, manifest, result)
    manifest["status"] = "validated" if result.status == "pass" else "validation_failed"
    manifest["updated_at"] = _utc_now()
    _json_write(run_dir / "run_manifest.json", manifest)
    return result


def _write_feedback(run_dir: Path, manifest: dict[str, Any], result: ValidationResult) -> None:
    payload = {
        "run_id": result.run_id,
        "review_result": result.status,
        "blocking_findings_count": len(result.errors),
        "errors": result.errors,
        "warnings": result.warnings,
        "depth": manifest.get("depth"),
        "generated_at": _utc_now(),
    }
    _json_write(run_dir / "plan_review_feedback.json", payload)
    lines = ["# Plan Review Feedback", "", f"- Result: {result.status}"]
    if result.errors:
        lines.append("- Errors:")
        lines.extend(f"  - {error}" for error in result.errors)
    if result.warnings:
        lines.append("- Warnings:")
        lines.extend(f"  - {warning}" for warning in result.warnings)
    _text_write(run_dir / "plan_review_feedback.md", "\n".join(lines))


def handoff_run(run_id: str) -> dict[str, Any]:
    _load_manifest(run_id)
    path = _run_dir(run_id) / "ai_change_handoff.json"
    if not path.exists():
        raise ValueError(f"handoff artifact for `{run_id}` is missing")
    payload = _json_load(path)
    if not isinstance(payload, dict):
        raise ValueError(f"handoff artifact for `{run_id}` is not a JSON object")
    return payload


def status_run(run_id: str | None = None) -> dict[str, Any]:
    target = run_id or _latest_run_id()
    if not target:
        return {"active_run": None, "runs": []}
    return _load_manifest(target)


def _print_payload(payload: Any, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if isinstance(payload, ValidationResult):
        print(f"run_id: {payload.run_id}")
        print(f"status: {payload.status}")
        for error in payload.errors:
            print(f"error: {error}")
        for warning in payload.warnings:
            print(f"warning: {warning}")
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list):
                print(f"{key}:")
                for item in value:
                    print(f"- {item}")
            else:
                print(f"{key}: {value}")
        return
    print(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    autopilot = subparsers.add_parser("autopilot")
    autopilot.add_argument("request", nargs="?", help="planning request")
    autopilot.add_argument("--planning-request")
    autopilot.add_argument("--source-summary-file")
    autopilot.add_argument("--plan-source", nargs="*", default=[])
    autopilot.add_argument("--from-conversation", action="store_true")
    autopilot.add_argument("--title")
    autopilot.add_argument("--depth", choices=sorted(VALID_DEPTHS), default="auto")
    autopilot.add_argument("--format", choices=("text", "json"), default="text")

    status = subparsers.add_parser("status")
    status.add_argument("--run-id")
    status.add_argument("--format", choices=("text", "json"), default="text")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--format", choices=("text", "json"), default="text")

    handoff = subparsers.add_parser("handoff")
    handoff.add_argument("--run-id", required=True)
    handoff.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "autopilot":
            request = args.planning_request or args.request
            payload = autopilot_run(
                planning_request=request,
                plan_sources=args.plan_source,
                source_summary_file=args.source_summary_file,
                depth=args.depth,
                title=args.title,
                from_conversation=args.from_conversation,
            )
            _print_payload(payload, args.format)
            return 0
        if args.command == "status":
            _print_payload(status_run(args.run_id), args.format)
            return 0
        if args.command == "validate":
            result = validate_run(args.run_id)
            _print_payload(result.as_dict() if args.format == "json" else result, args.format)
            return 0 if result.status == "pass" else 1
        if args.command == "handoff":
            payload = handoff_run(args.run_id)
            if args.format == "text":
                print(_handoff_markdown(payload))
            else:
                _print_payload(payload, args.format)
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
