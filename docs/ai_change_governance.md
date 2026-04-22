# AI Change Governance

Last updated: 2026-04-21

This repo's default AI-assisted change workflow is git/local-review-first.
The review transport for real state-changing work is a real git branch plus a
local branch-diff review bundle under `.claude/ai_change_runs/`.

The repo supports two operating styles on top of that same transport:

- `manual_checkpointed`
  - the user or agent explicitly calls `start-run`, `checkpoint`,
    `ready-for-review`, and `review-feedback`
- `autopilot`
  - the chat agent owns that loop end-to-end inside one session, using the same
    deterministic subcommands under the hood

The default entrypoint remains:

```bash
python3 .claude/scripts/ai_change_governance.py
```

The chat command alias is `/ai-change`. Its command contract lives in
`.claude/commands/ai-change.md`.

## Operating Model

1. Start one `/ai-change` run for the task; the run creates or reuses a
   dedicated working branch. If the task explicitly points to live plan docs,
   pass them as `--acceptance-source` so the review bundle imports their
   acceptance obligations.
2. Work inside a real git repository on that run branch.
3. Use `/ai-change checkpoint` for each meaningful milestone. By default it
   commits only the already staged changes and refreshes the local review bundle
   from the branch diff.
4. Run the targeted checks selected by `ai_change_governance.py`.
5. Use `/ai-change ready-for-review` at each phase-complete checkpoint, not
   only near final task completion. If a milestone is meaningful enough to
   checkpoint as its own change slice, it is meaningful enough to review before
   the next implementation phase begins.
6. Use `/ai-change review-feedback` to refresh the local review artifacts from
   the current branch diff when the next coding step depends on reviewer
   output. The same command also persists the current local review verdict
   (`pending_local_review`, `approved`, `approved_with_advisories`, or
   `changes_requested`) plus machine-readable finding counts, `next_action`,
   and any required acceptance-evidence records for that reviewed branch state.
7. For medium/high-risk approval, run `/ai-change independent-review` before
   persisting approval. That command launches a separate AI code-review session
   and stores a durable review artifact tied to the reviewed head commit.
8. Conduct review from the branch diff, the review brief, the targeted
   validation results, and the independent AI review artifact before starting
   the next implementation phase. Missing a required independent review is
   itself a governance defect, not a reason to continue coding.
9. Review the automation output as a human before merge.
10. Keep `git config core.hooksPath .githooks` enabled in local clones so
   `.githooks/pre-push` blocks direct pushes to `main` when server-side branch
   protection is unavailable on a private repo.

## Why This Shape

The old packet-only workflow created a second local state machine that could
drift away from the actual diff being reviewed. The earlier git/PR-first model
then made `/ai-change` depend on external review transport and repo app setup.
The current repo-default shape keeps the durable git branch boundary, but moves
the review surface fully local so the command family can complete its own loop
without GitHub app dependencies.

The current shape still avoids the "one final commit at the end" failure mode:

- `start-run` binds the session to one branch
- `checkpoint` creates small committed milestones on that branch
- `prepare-pr` remains the compatibility command name, but now writes the local
  review manifest and review bundle
- `ready-for-review` is the explicit checkpoint that marks the branch ready for
  local review
- `independent-review` launches a separate AI reviewer and writes the durable
  independent review artifact for medium/high-risk approval
- `review-feedback` refreshes the local review packet used by manual and
  autopilot loops and persists the current verdict surface for the reviewed
  branch state

`autopilot` uses that same loop, but keeps ownership inside the chat agent:

- start one autopilot run
- edit code
- checkpoint automatically at meaningful milestones
- treat every phase-complete milestone as reviewable unless the change slice is
  obviously unfinished
- mark the branch ready for review at each phase-complete checkpoint instead of
  delaying review until the whole task feels "nearly done"
- refresh local review artifacts
- run independent AI review for medium/high-risk approval
- ingest the independent review artifact through `review-feedback`
- decide whether to stop, fix findings, or ask the human for a policy call
- only then begin the next implementation phase

## Independent AI Review

Medium/high-risk approval requires a separate AI code-review artifact. The
deterministic script does not replace the reviewer; it launches the reviewer
session, requires the git worktree to be clean before review, fails closed if
the child reviewer changes tracked paths, unapproved untracked paths, or
ignored run-state files other than the two review artifacts, validates the
artifact envelope, and blocks stale or self-authored approval persistence.

`/ai-change independent-review` writes:

- `.claude/ai_change_runs/<run_id>/independent_review.json`
- `.claude/ai_change_runs/<run_id>/independent_review.md`

The JSON artifact records the reviewed head commit, changed paths, provider,
model, prompt version, implementer identity/session, reviewer identity/session,
review result, finding counts, contract-sufficiency assessment, overfitting
assessment, and policy-substitution assessment. High-risk `/research` changes
also require shared-branching and architecture-sync audit answers.
For medium/high-risk approval, the run manifest and review artifact must carry
known, distinct implementer and reviewer identity/session values; unknown
identity is treated as insufficient separation. Existing run manifests must not
be repaired from review-time environment values; implementer identity/session
may be initialized at run creation, but missing durable manifest fields remain
missing for review validation.
Identity, reviewed head commit, and reviewed path set must be present in the
durable artifact itself; CLI arguments or environment variables may only
cross-check those fields, not replace them.
When the parent environment sets `CODEX_SANDBOX_NETWORK_DISABLED=1`, Codex
child review fails closed unless the operator explicitly sets
`CODEX_CHILD_NETWORK_ALLOWED=1` for that launch.
The AI reviewer prompt must use `docs/coder_guide.md`, check high-level
architecture alignment against `docs/architecture.md` and touched systemdesign
contracts, and critically examine whether the code translates design intention
into function. For example, a function intended to compress data for decision
making should not emit artifacts about the same size as its input.

`review-feedback` must downgrade requested `approved` /
`approved_with_advisories` to `pending_local_review` when the required
independent AI review artifact is missing, stale, unparsable, self-authored, or
missing required assessment fields. If the independent reviewer requests
changes or records blocking findings, `review-feedback` persists
`changes_requested`.

## Acceptance Sources And Evidence

When a run or task explicitly names live plan docs, treat those files as
explicit acceptance sources by passing them as `--acceptance-source`.

Acceptance-source metadata changes the local review contract in four ways:

- the review manifest and review bundle import the acceptance-source docs into
  the bounded review surface
- acceptance / exit / validation / evaluation bullets from those docs remain
  machine-readable acceptance inventory in the local review artifacts
- explicitly scoped bullets or checklist entries become machine-readable
  approval-blocking acceptance requirements
- any named artifact or comparator path from scoped requirements becomes
  required review evidence even if it lives under a normally excluded surface
  such as `research/**`; unscoped imported paths remain audit context
- the approval blocking point is the `review-feedback` writeback: it must not
  persist `approved` or `approved_with_advisories` for the reviewed head commit
  while scoped required acceptance evidence is still `missing` or `fail`

The default local review mode is `acceptance_mode=scoped`. In scoped mode,
unscoped bullets imported from broad planning or governance docs are retained as
context/audit inventory and are not counted as blocking missing evidence.
Scoped mode no longer generates a procedural default checklist for workflow
facts such as checkpoint, ready-for-review, or review-feedback bookkeeping.
Only an explicit `--acceptance-scope-file` or `strict` mode creates
approval-blocking acceptance evidence obligations.

Use `acceptance_mode=strict` for high-risk or compliance workflows where every
imported acceptance-source bullet must pass. Strict mode preserves the older
fail-closed behavior: every imported acceptance requirement is blocking and
every missing/failing imported evidence entry downgrades approval persistence.

Required acceptance evidence should stay machine-readable where feasible.
`review-feedback.json` records one evidence entry per scoped requirement with:

- `status`: `pass`, `fail`, or `missing`
- `reviewed_artifact_paths`
- `comparator_basis` when the requirement uses a fixed comparator
- optional reviewer notes

For backward compatibility, `review_feedback.json` keeps
`acceptance_requirements`, `acceptance_evidence`, `acceptance_gate_status`,
`acceptance_missing_count`, `acceptance_fail_count`, and
`acceptance_blocking_requirement_ids` as aliases for the current
approval-blocking scoped/strict gate. Downstream tools that need the full
audit input should read `acceptance_inventory_requirements`,
`acceptance_inventory_count`, `acceptance_inventory_unscoped_count`, and
`acceptance_context_only_requirement_ids`. Evidence entries supplied for
unscoped inventory ids are retained in `acceptance_inventory_evidence` as
context-only audit records and do not affect the scoped gate.

## Required Assets

- `.claude/settings.json`
  - registers the project hook configuration
- `.claude/hooks/ai_change_guard.py`
  - blocks direct file edits outside a real git repository so `/ai-change`
    cannot silently bypass the branch-local review transport
- `.githooks/pre-push`
  - blocks local direct pushes to `main`; set `git config core.hooksPath
    .githooks` in each clone that should enforce the local-review merge path
- `.claude/ai_change_runs/<run_id>/review_manifest.json`
  - stores the local governance summary and review brief for the current branch
    diff, including explicit acceptance sources, imported acceptance
    inventory, scoped/strict acceptance requirements, and any named scoped
    required evidence artifacts
- `.claude/ai_change_runs/<run_id>/review_bundle.md`
  - stores the reviewer-facing markdown bundle for the current branch diff
- `.claude/ai_change_runs/<run_id>/independent_review.json`
  - stores the AI-generated independent review artifact for medium/high-risk
    approval, including reviewer identity/session, reviewed head commit,
    finding counts, and required assessment fields
- `.claude/ai_change_runs/<run_id>/independent_review.md`
  - stores the human-readable independent review summary
- `.claude/ai_change_runs/<run_id>/review_feedback.json`
  - stores the latest refreshed local review packet used by autopilot and
    manual review loops to judge the next step, including `review_result`,
    `findings_count`, `blocking_findings_count`, `next_action`, the imported
    acceptance inventory, scoped/strict acceptance requirements, and
    machine-readable scoped acceptance evidence with `status: pass|fail|missing`
    when explicit scoped/strict requirements exist

## Hard Vs Advisory

Hard gates stay narrow and deterministic where possible.
In this repo they should usually reduce to:

- real git repository required for state-changing code/workflow edits
- repo-managed local push guard required for direct `main` push blocking in
  private-repo clones
- checkpoint commits should default to staged-only unless the caller explicitly
  widens the staging scope
- autopilot may decide the next coding step from `review-feedback`
  `next_action`, but it may not auto-merge without an explicit future policy
  change
- autopilot must run local review at each phase-complete checkpoint; it may not
  stack a new meaningful implementation phase on top of an unreviewed branch
  state just because the overall task is still open
- medium/high-risk `approved` / `approved_with_advisories` persistence requires
  a fresh AI-generated independent review artifact for the reviewed head commit
- implementer and reviewer identity/session must be known and distinct when
  persisting medium/high-risk approval
- targeted regression checks when the touched surface warrants them and the derived project defines those checks
- `/research` overlays only when touched paths actually hit shared `/research`
  runtime, contract, workflow, or architecture surfaces
- the default review read surface stays bounded: `docs/legacy/**` and bulk
  generated `research/**` artifacts are summarized in review guidance rather
  than loaded by default unless a live doc, active contract failure, concrete
  finding, or explicit acceptance-source requirement points there
- `review-feedback` must block approval persistence when scoped acceptance
  requirements still have evidence status `missing` or `fail`; in strict mode,
  every imported acceptance-source requirement is scoped for blocking

Reviewer findings remain findings-first and concrete.
The reviewer should block only on concrete correctness, regression, contract,
provenance, security, or meaningful missing-test defects. Style preference and
future cleanup stay advisory.

## Risk Policy

`low`
- docs-only or tests-only edits
- lightweight local governance may be enough before merge

`medium`
- general code, governance docs, command contracts, ai-change tooling
- local branch review is required before merge

`high`
- shared `/research` runtime, workflow, command-contract, or architecture edits
- local branch review plus independent audit expectations still apply

## Usage

Start a run:

```bash
python3 .claude/scripts/ai_change_governance.py \
  start-run --task-summary "tighten /ai-change governance" \
  --acceptance-source docs/live_plan.md \
  --acceptance-mode scoped \
  --base-branch main
```

Start an autopilot run:

```bash
python3 .claude/scripts/ai_change_governance.py \
  autopilot --task-summary "tighten /ai-change governance" \
  --acceptance-source docs/live_plan.md docs/eval_plan.md \
  --acceptance-mode scoped \
  --base-branch main
```

Use strict acceptance blocking for workflows that intentionally require every
imported source bullet to pass:

```bash
python3 .claude/scripts/ai_change_governance.py \
  review-feedback --run-id ai-change-20260415093000 \
  --review-result approved \
  --acceptance-mode strict \
  --acceptance-evidence-file acceptance_evidence.json
```

Provide a scoped checklist or selected imported requirement ids with:

```bash
python3 .claude/scripts/ai_change_governance.py \
  review-feedback --run-id ai-change-20260415093000 \
  --acceptance-scope-file acceptance_scope.json
```

Create a checkpoint from the currently staged changes:

```bash
python3 .claude/scripts/ai_change_governance.py \
  checkpoint --run-id ai-change-20260415093000 \
  --message "Checkpoint governance automation"
```

Mark the branch ready for local review:

```bash
python3 .claude/scripts/ai_change_governance.py \
  ready-for-review --run-id ai-change-20260415093000
```

Launch the required independent AI review for medium/high-risk approval:

```bash
python3 .claude/scripts/ai_change_governance.py \
  independent-review --run-id ai-change-20260415093000 \
  --provider codex \
  --reviewer-id codex-independent-reviewer
```

Refresh the local review feedback bundle:

```bash
python3 .claude/scripts/ai_change_governance.py \
  review-feedback --run-id ai-change-20260415093000
```

Record acceptance evidence and a completed local review verdict for the current
reviewed branch state:

```bash
python3 .claude/scripts/ai_change_governance.py \
  review-feedback --run-id ai-change-20260415093000 \
  --review-result approved \
  --independent-review-artifact .claude/ai_change_runs/ai-change-20260415093000/independent_review.json \
  --acceptance-evidence-file acceptance_evidence.json
```

Example acceptance evidence file:

```json
{
  "entries": [
    {
      "requirement_id": "docs-live-plan-md-01",
      "status": "pass",
      "reviewed_artifact_paths": ["research/demo/output.md"]
    },
    {
      "requirement_id": "docs-live-plan-md-02",
      "status": "pass",
      "reviewed_artifact_paths": ["docs/example.md"],
      "comparator_basis": "research/gold/output_claude.md"
    }
  ]
}
```

Generate local review artifacts explicitly:

```bash
python3 .claude/scripts/ai_change_governance.py \
  prepare-pr --run-id ai-change-20260415093000 \
  --title "Tighten ai-change governance" \
  --base-branch main \
  --branch-diff
```

Analyze changes without starting a run:

```bash
python3 .claude/scripts/ai_change_governance.py --staged
```

or

```bash
python3 .claude/scripts/ai_change_governance.py docs/ai_change_governance.md
```
