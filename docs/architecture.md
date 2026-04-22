# Project Template Architecture (SSOT)

Last updated: 2026-04-22 (template-contamination-cleanup)

## Traceability Read Window
- New per-change traceability lives in `.claude/ai_change_runs/` review artifacts and branch commits.
- Pre-implementation planning traceability lives in `.claude/ai_plan_runs/`
  artifacts and feeds scoped acceptance into `/ai-change`.
- Update this file when architecture, layer ownership, or governance workflow rules change.

### Traceability record — 2026-04-21 (template-ai-change-governance)
- Intent: Replace the previous template governance skeleton with `/ai-change`, a git/local-review governance template for AI-assisted state-changing work.
- Commands affected: `/ai-change`
- Layers touched: policy (`AGENTS.md`, `CLAUDE.md`), command docs (`.claude/commands/ai-change.md`), scripts/hooks (`.claude/scripts/ai_change_governance.py`, `.claude/hooks/ai_change_guard.py`, `.githooks/pre-push`), docs (`docs/ai_change_governance.md`, `docs/architecture.md`, `docs/coder_guide.md`, `CommandGuide.md`), command spec (`spec/commands.yaml`), and systemdesign (`docs/systemdesign/architect_ai_change/*`).
- Human checkpoints impacted: medium/high-risk approval requires a fresh independent AI review artifact before approval persistence; merge remains a human decision.
- Verification: template scaffold and static governance checks; runtime checks require the template to be initialized as a real git repository.

### Traceability record — 2026-04-22 (template-ai-plan-governance)
- Intent: Add `/ai-plan` as the default planning router before non-trivial AI-assisted implementation, with durable plan trace, decision-surface classification, scoped acceptance, and `/ai-change` handoff.
- Commands affected: `/ai-plan`, `/ai-change` handoff integration.
- Layers touched: policy (`AGENTS.md`, `CLAUDE.md`), command docs (`.claude/commands/ai-plan.md`), scripts (`.claude/scripts/ai_plan_governance.py`), docs (`docs/ai_plan_governance.md`, `docs/architecture.md`, `docs/coder_guide.md`, `CommandGuide.md`), command spec (`spec/commands.yaml`), and systemdesign (`docs/systemdesign/architect_ai_plan/*`).
- Human checkpoints impacted: deep planning requires architecture, harness, and LLM-delegation review artifacts before final handoff; implementation approval still belongs to `/ai-change`.
- Verification: command index rendering, command SSOT checks, JSON validation, and template static checks when the template is initialized as a real git repository.

### Traceability record — 2026-04-22 (template-contamination-cleanup)
- Intent: Remove project-specific leftovers from the reusable template and keep only template-generic governance behavior.
- Commands affected: `/ai-change` governance classification and review prompts; `/ai-plan` planning artifacts remain ignored per project.
- Layers touched: policy (`AGENTS.md`, `CLAUDE.md`), scripts (`.claude/scripts/ai_change_governance.py`, `.claude/scripts/check_ai_governance_review.py`, `.claude/scripts/check_architecture_sync.py`), docs (`docs/ai_change_governance.md`, `docs/architecture.md`, `docs/coder_guide.md`, `docs/coder_guide_detail.md`, `docs/local-mcp-backend-design.md`), git ignore rules, and systemdesign (`docs/systemdesign/architect_ai_change/*`).
- Human checkpoints impacted: derived-project high-risk review fields remain possible, but this blank template no longer ships project-specific command overlays.
- Verification: project-specific token scan, command SSOT checks, architecture sync checks, governance layering checks, JSON validation, and Python bytecode compilation for changed scripts.

## Source of Truth Hierarchy
- `AGENTS.md`
- `.claude/agents/*.md`
- `CLAUDE.md`
- `.claude/commands/*.md`
- `.claude/scripts/*.py`

## System Components
- Policy layer: `AGENTS.md`, `CLAUDE.md`
- Command layer: `.claude/commands/*.md`
- Agent layer: `.claude/agents/*.md`
- Script layer: `.claude/scripts/*.py`
- AI change governance layer: `docs/ai_change_governance.md`, `docs/systemdesign/architect_ai_change/*`, `.claude/ai_change_runs/`
- AI plan governance layer: `docs/ai_plan_governance.md`, `docs/systemdesign/architect_ai_plan/*`, `.claude/ai_plan_runs/`
- Local git guard layer: `.claude/hooks/ai_change_guard.py`, `.githooks/pre-push`

## Runtime Flows
### Command orchestration pattern
- Keep the public `/command` contract stable in policy, command, and agent docs.
- Keep deterministic behavior in scripts and keep AI judgment explicit as a named generative stage.
- Do not duplicate executable command behavior in top-level policy files.

### AI Change Governance (`/ai-change`)
- `/ai-change` is the git/local-review governance entrypoint for AI-assisted state-changing work.
- `/ai-change` creates or reuses a dedicated run branch, records checkpoint commits, writes local branch-diff review bundles, and can launch an independent AI review for medium/high-risk approval.
- Local run artifacts live under `.claude/ai_change_runs/`; template projects should treat generated run artifacts as per-project state, not reusable template content.
- The public command contract lives in `.claude/commands/ai-change.md`; policy lives in `docs/ai_change_governance.md`; architecture contract lives in `docs/systemdesign/architect_ai_change/`.

### AI Plan Governance (`/ai-plan`)
- `/ai-plan` is the pre-implementation planning router for non-trivial state-changing work.
- `/ai-plan` writes durable plan trace, decision-surface inventory, scoped acceptance, required checks, open policy questions, and `/ai-change` handoff artifacts under `.claude/ai_plan_runs/`.
- `/ai-plan` does not create implementation branches, checkpoint commits, merge approvals, or a second `/ai-change` review-feedback state machine.
- Template-derived projects should implement any backend command orchestration through the local MCP adapter/server pattern in `docs/local-mcp-backend-design.md`; architecture, harness, and LLM-delegation judgment remain explicit generative stages.
- The public command contract lives in `.claude/commands/ai-plan.md`; policy lives in `docs/ai_plan_governance.md`; architecture contract lives in `docs/systemdesign/architect_ai_plan/`.

## Human-in-the-Loop Control Points
| Command/Flow | Checkpoint | Required Behavior | Stop Condition |
|---|---|---|---|
| `/ai-change` | Run start | Bind state-changing work to a real git repo and dedicated branch | No real git repository or branch setup fails |
| `/ai-change` | Checkpoint | Commit a meaningful milestone and refresh local review artifacts | Required checkpoint or review artifact generation fails |
| `/ai-change` | Independent review | Require fresh independent AI review before medium/high-risk approval persistence | Missing, stale, self-authored, or incomplete review artifact |
| `/ai-change` | Merge | Human reviews local branch diff and automation output before merge | Human declines or blocking findings remain |
| `/ai-plan` | Depth selection | Choose minimal, standard, or deep planning depth and record rationale | Ambiguous semantic planning is reduced to deterministic guesswork |
| `/ai-plan` | Deep review | Require architecture, harness, and LLM-delegation review artifacts | Required deep review artifact is missing or requests changes |
| `/ai-plan` | Handoff | Emit scoped acceptance and `/ai-change` command suggestions | Handoff omits acceptance scope or slice ownership |

## Change Protocol and Traceability
- AI-assisted behavior-changing work should use `/ai-change` when branch-bound checkpoints, local review bundles, acceptance-source tracking, or independent AI review are required.
- Non-trivial AI-assisted work should use `/ai-plan` first when durable planning intent, decision-surface classification, scoped acceptance, or review-lane planning is required.
- `AGENTS.md` and `CLAUDE.md` stay compact; executable detail belongs in `.claude/commands/*.md`, and workflow detail belongs in `.claude/agents/*.md`.
- `docs/ai_change_governance.md` is the policy bundle for AI-assisted change governance.
- `docs/ai_plan_governance.md` is the policy bundle for pre-implementation planning governance.
- Update all touched governance layers in the same change set.
