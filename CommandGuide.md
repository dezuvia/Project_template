# Command Guide

<!-- BEGIN:COMMAND_INDEX -->

| Command | Purpose | Category |
|---|---|---|
| `/ai-change` | Run git/local-review governance for AI-assisted state-changing work | governance |
| `/ai-plan` | Plan non-trivial AI-assisted changes before implementation handoff | governance |

<!-- END:COMMAND_INDEX -->

## AI Change Governance

Use `/ai-change` when AI-assisted state-changing work needs branch-bound checkpoints, local branch-diff review, acceptance-source tracking, or independent AI review.

```text
/ai-change start-run --task-summary "<summary>"
/ai-change checkpoint --run-id <id> --message "<message>" --paths <path ...>
/ai-change ready-for-review --run-id <id>
/ai-change independent-review --run-id <id>
/ai-change review-feedback --run-id <id> --review-result <state>
```

Detailed behavior lives in `.claude/commands/ai-change.md`; policy lives in `docs/ai_change_governance.md`.

## AI Plan Governance

Use `/ai-plan` before non-trivial AI-assisted implementation when the work
needs durable planning intent, deterministic/generative decision-surface
classification, scoped acceptance, or review-lane planning.

```text
/ai-plan autopilot "<planning request>"
/ai-plan autopilot --plan-source <path ...> --title "<title>"
/ai-plan validate --run-id <id>
/ai-plan handoff --run-id <id>
```

Detailed behavior lives in `.claude/commands/ai-plan.md`; policy lives in `docs/ai_plan_governance.md`.
