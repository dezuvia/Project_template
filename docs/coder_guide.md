# Coder Guide — Quick Reference

All coding agents MUST apply these rules. Full rationale: `docs/coder_guide_detail.md`.

---

## Pre-Work (do before every task)

- Read `docs/architecture.md` for global context.
- For non-trivial state-changing work, use `/ai-plan autopilot` first when the
  request needs durable planning intent, decision-surface classification,
  architecture traceability, scoped acceptance, or review-lane planning before
  implementation.
- For AI-assisted code/workflow changes, start with `.claude/scripts/ai_change_governance.py` so the change is risk-classified and the minimum required checks/review lanes are selected up front.
- Read `docs/local-mcp-backend-design.md` before designing, debugging, or changing command orchestration or backend routing.
- If modifying a command's pipeline: read `docs/systemdesign/architect_<commandname>/index.json` first. Verify your change does not duplicate an upstream step, break a downstream input contract, or add a deterministic gate where the `type` field says `generative`. Full convention in `docs/architecture_guide.md`.
- If fixing or updating a larger command or workflow, update the matching `/systemdesign` spec in the same change: `docs/systemdesign/architect_<commandname>/`. Do not leave command or workflow behavior changed in code while the architecture SSOT stays stale.
- Confirm your solution does not conflict with or duplicate an existing component.
- State whether the triggering case is a **general use case** or a **test/edge case** before writing any fix.

---

## Governance

- Hierarchy: `AGENTS.md` > `.claude/agents/` > `CLAUDE.md` > `.claude/commands/` > `.claude/scripts/`
- Never add executable detail to top-level files (`AGENTS.md`, `CLAUDE.md`). Push it down.
- Keep AI governance lightweight: concrete hard failures may block submission; reviewer/auditor prompts and broader maintainability notes stay advisory unless they identify a real contract, workflow, provenance, or regression defect.

---

## Scripting & Automation

- Repetitive task → build a script; don't reimplement existing `.claude/scripts/` logic inline.
- Repetitive + ambiguous task → local MCP backend plus an explicit generative stage, not deterministic guesswork.
- Ambiguous planning decisions → `/ai-plan` generative review lane backed by
  the workflow's explicit stage or local MCP backend contract, with
  deterministic code limited to artifact management and validation.
- **Codex**: do not solve orchestration by spawning child sessions. Route deterministic work through the local MCP adapter/server pair and keep AI judgment in the declared workflow stage.

---

## Problem Diagnosis

- Check the **input layer first** (schema, format, upstream assumptions) before touching process logic.
- Tunneling effect: resist the urge to add features/checkers/variables to fix a bug. Ask if removing something is a better fix.

---

## Overfitting

- Never write a fix that only handles a test case. Fix the general contract; verify it covers the test.
- For multi-session debugging: fork the state first and write a fix-specific context note.

---

## System Efficiency

- Proportion solution weight to the feature's global importance. Edge cases don't justify heavyweight gates.
- Local MCP tools and explicit AI stages: pass **minimum required granularity** (metadata, not raw dumps; IDs, not full records).
- Before writing a step, check what the previous step already produced — reuse, don't rebuild.

---

## Ambiguity

- Never fake determinism (keyword lists, regex heuristics) for inherently ambiguous decisions.
- Use existing metadata to infer; route judgment through the workflow's explicit AI/generative stage or backend-owned planner; expose to user only if a policy call is needed.
- Tuning AI behavior = prompt engineering. No magic numeric weights.

---

## Creative Latitude

- Explicitly state what is **fixed** (contract, schema) vs. **open** (implementation, style) in every task prompt.
- Agents should act within their authority without excessive hedging or asking permission for open decisions.

---

## Hygiene

- Scripts: one concern per script; functions ≤ ~50 lines; no config/logic mixed.
- Before adding a feature to an existing script, ask: should this be a separate script? Scripts must not grow unboundedly — a long script is harder to load, debug, and maintain than two focused ones.
- Context windows: no "just in case" data dumps — every token must be used.

---

## Self-Test (before submitting)

1. Root cause or symptom?
2. Simplest solution for the general case?
3. Duplicates upstream work?
4. Only the data this step needs?
5. General case, not overfitted to test?
6. Conflicts with `docs/architecture.md` or `docs/systemdesign/architect_<commandname>/index.json`?
7. Deterministic logic where an explicit AI/generative stage belongs?
8. Updated the relevant `/systemdesign` spec if the task changed a larger command or workflow?
