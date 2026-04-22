# AI Plan Governance

Last updated: 2026-04-22

`/ai-plan` is the default planning router before non-trivial state-changing
work. It creates a durable record of implementation intent before `/ai-change`
owns branch management, checkpoint commits, local branch review, and merge
readiness.

Template projects should expose command orchestration through the local MCP
adapter/server pattern described in `docs/local-mcp-backend-design.md`.
`/ai-plan` follows that rule: deterministic artifact management may live in a
script, client, server, or shared helper, while architecture, harness, and
LLM-delegation judgment remain explicit generative stages. Do not implement
those review lanes as hidden nested Codex child-session orchestration.

The default script entrypoint is:

```bash
python3 .claude/scripts/ai_plan_governance.py
```

The chat command alias is `/ai-plan`. Its dispatcher contract lives in
`.claude/commands/ai-plan.md`.

## Operating Model

1. The chat agent gathers the planning request, explicit source paths, or a
   concise conversation summary. Conversation history is source material, not a
   deterministic script input.
2. The planner chooses the smallest sufficient depth:
   - `minimal`: typo fixes, narrow docs edits, simple tests, and obviously
     mechanical one-file work.
   - `standard`: normal behavior-changing programming tasks.
   - `deep`: command contracts, shared workflow changes, harnesses, prompts,
     review or evaluation logic, multi-agent behavior, and ambiguous semantic
     decisions.
3. The deterministic artifact manager writes run artifacts under
   `.claude/ai_plan_runs/<run_id>/`.
4. Standard and deep plans record trace ids for requirements, decisions,
   implementation slices, acceptance requirements, and evidence expectations.
5. Standard and deep plans classify meaningful behavior decisions as
   `deterministic`, `generative`, or `hybrid`.
6. Deep plans require architecture, harness-engineering, and LLM-delegation
   review artifacts before `validate` can pass.
7. The planner emits `acceptance_scope.json` and `ai_change_handoff.*` so
   `/ai-change autopilot` can enforce scoped acceptance requirements.

## Depth Policy

`--depth auto` is a planning-router request. The chat planner owns ambiguous
depth judgment. The deterministic script may compute a conservative scaffold
depth from explicit source paths and obvious request shape, but it must record
the method and may not treat that scaffold as a substitute for required deep
review lanes.

Use `minimal` when the expected implementation surface is small and mechanical.
Minimal runs still create durable artifacts because the handoff and status
surfaces should be resumable.

Use `standard` when the work changes behavior, tests, scripts, or local
contracts but does not alter shared workflow governance, prompt behavior,
review/evaluation semantics, or multi-agent routing.

Use `deep` when the work touches any of these surfaces:

- command contracts or command dispatchers
- governance docs or systemdesign specs
- harness, smoke, benchmark, review, or evaluation logic
- prompt contracts or LLM delegation behavior
- ambiguous semantic decision surfaces
- cross-repo template propagation

## Required Artifacts

Every run writes:

- `run_manifest.json`
- `input_summary.md`
- `plan_trace.json`
- `decision_surface_inventory.json`
- `implementation_slices.md`
- `acceptance_scope.json`
- `required_checks.md`
- `open_policy_questions.md`
- `ai_change_handoff.json`
- `ai_change_handoff.md`

Deep runs also require:

- `architecture_review.json` and `architecture_review.md`
- `harness_review.json` and `harness_review.md`
- `llm_delegation_review.json` and `llm_delegation_review.md`
- `plan_review_feedback.json` and `plan_review_feedback.md`

## Decision-Surface Policy

Each meaningful behavior decision must use one of these classifications:

- `deterministic`: exact schema, file, diff, state, command, or format logic
  where the correct answer is mechanically knowable.
- `generative`: semantic judgment, synthesis, quality assessment, ambiguity
  resolution, plan review, or prose-to-contract interpretation.
- `hybrid`: deterministic shell around an explicit generative stage.

If a planned implementation proposes deterministic logic for a generative
decision, the plan must include an explicit safety justification. Without that
justification, `validate` fails.

## Review Lanes

Deep mode requires three planning review lanes.

Architecture review checks that the plan changes the right command and
systemdesign surfaces, avoids duplicate state machines, and keeps top-level
files compact.

Harness-engineering review checks that the validation plan proves the intended
behavior rather than a fixture-specific example, and that scoped acceptance
requirements have evidence paths.

LLM-delegation review checks that semantic judgment is assigned to explicit
generative stages with bounded context instead of hidden deterministic keyword,
regex, or template branches.

Review artifacts are planning evidence only. They do not approve code changes;
that remains `/ai-change` work. In template-derived projects, these lanes may
be backed by local MCP tools or explicit in-session AI stages, but the
generative boundary must be declared in the workflow and systemdesign contract.

## Handoff To `/ai-change`

The handoff must include at least one command shaped like:

```text
/ai-change autopilot "<slice task summary>" \
  --acceptance-source <plan-source> \
  --acceptance-scope-file .claude/ai_plan_runs/<run_id>/acceptance_scope.json
```

When the plan has multiple slices, each slice should include:

- task summary
- owned file/surface boundaries
- acceptance requirement ids
- required checks
- review risk level
- dependency ordering
- stop conditions

`/ai-change` remains the implementation authority for branch creation,
checkpoint commits, branch-diff review bundles, independent code review, review
feedback, and merge readiness.

## Hard Vs Advisory

Hard planning gates:

- required run artifacts must exist and be parseable
- trace ids must be unique
- acceptance requirements must reference known plan trace or requirement ids
- handoff files must name the scoped acceptance file
- deep runs must include all three review-lane artifacts
- generative decisions must not be assigned to deterministic implementation
  without explicit justification

Advisory planning findings:

- slice ordering improvements
- extra validation suggestions beyond scoped acceptance
- maintainability notes that do not identify a contract, traceability,
  provenance, or regression defect
