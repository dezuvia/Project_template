Run the repo-default AI-assisted planning governance flow.

Arguments received: $ARGUMENTS

## Required behavior source
1. `AGENTS.md` (conflict precedence + command contract)
2. `docs/ai_plan_governance.md`
3. `docs/coder_guide.md`
4. `docs/architecture.md`
5. `docs/local-mcp-backend-design.md`
6. `docs/systemdesign/architect_ai_plan/index.json`
7. `.claude/scripts/ai_plan_governance.py`

Always follow those files exactly; this command doc is a dispatcher.
Do not duplicate the full planning policy here.

## Execution mode
- Chat-owned planning router before non-trivial state-changing work
- Template command orchestration should use the local MCP adapter/server
  pattern when a derived project implements backend tooling
- Durable planning artifacts under `.claude/ai_plan_runs/`
- Emits scoped acceptance and handoff artifacts that `/ai-change autopilot` can consume
- Does not create implementation branches, checkpoint commits, merge approvals, or review-feedback state

## Variants
- `/ai-plan` - show the active planning run status when one exists.
- `/ai-plan autopilot "<planning request>" [--depth auto|minimal|standard|deep]` - create a planning run from a request and emit the smallest sufficient planning artifact set.
- `/ai-plan autopilot --from-conversation --title "<title>" [--depth auto|minimal|standard|deep]` - create a planning run from a chat-owned conversation summary supplied to the script.
- `/ai-plan autopilot --plan-source <path ...> --title "<title>" [--depth auto|minimal|standard|deep]` - create a planning run from one or more plan/source files.
- `/ai-plan status [--run-id <id>]` - print planning run state.
- `/ai-plan validate --run-id <id>` - validate required artifacts, trace references, scoped acceptance, and deep-mode review gates.
- `/ai-plan handoff --run-id <id> [--format text|json]` - print `/ai-change` handoff commands and machine-readable scope references.

## Default Flow
1. Read `docs/ai_plan_governance.md`.
2. Read `docs/coder_guide.md` and `docs/architecture.md`.
3. Summarize any conversation-derived source material before invoking the deterministic script.
4. Create a planning run with one request or explicit plan source.
5. Let the planner choose `minimal`, `standard`, or `deep`; use the smallest depth that preserves traceability and review integrity.
6. For standard/deep plans, classify meaningful behavior decisions as deterministic, generative, or hybrid.
7. For deep plans, run the architecture, harness-engineering, and LLM-delegation review lanes before treating the handoff as complete.
8. Run `validate` before passing the scoped acceptance file to `/ai-change`.
9. Start implementation with `/ai-change autopilot` using the emitted acceptance source and scope file.

## Restrictions
- Do not use `/ai-plan` as a replacement for `/ai-change` branch management, checkpoint commits, local branch review, or merge readiness.
- Do not add implementation-review state to `.claude/ai_plan_runs/`.
- Do not let a deterministic fallback approve a semantic planning decision that requires AI judgment.
- Do not add command behavior detail to `AGENTS.md` or `CLAUDE.md`.
- Do not drop scoped acceptance ids from the `/ai-change` handoff.
