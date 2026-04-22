Run the repo-default AI-assisted change governance flow.

Arguments received: $ARGUMENTS

## Required behavior source
1. `AGENTS.md` (conflict precedence + command contract)
2. `docs/ai_change_governance.md`
3. `docs/coder_guide.md`
4. `docs/architecture.md`
5. `CLAUDE.md` (Commands + Rules)
6. `.claude/scripts/ai_change_governance.py`

Always follow those files exactly; this command doc is a dispatcher.
Do not duplicate the full governance policy here.

## Execution mode
- Git branch + local branch-diff review by default
- Local `/ai-change` artifacts are the review transport and targeted-check support
- Uses `.claude/scripts/ai_change_governance.py` as the implementation authority
- `/ai-change autopilot` is a chat-owned loop layered on top of the deterministic script subcommands

## Variants
- `/ai-change` — show the active git/local-review run status when one exists; otherwise fall back to legacy analyze-only behavior
- `/ai-change autopilot "<task summary>" [--acceptance-source <doc ...>] [--acceptance-mode scoped|strict] [--acceptance-scope-file <path>] [--implementer-id <id>] [--implementer-session-id <id>]` — start an autopilot run, then keep cycling through implement -> checkpoint -> ready for review -> independent review -> review feedback -> next step selection at every phase-complete milestone until the task is done or human intervention is needed
- `/ai-change start-run --task-summary "<summary>" [--base-branch main] [--head-branch <branch>] [--title "<title>"] [--acceptance-source <doc ...>] [--acceptance-mode scoped|strict] [--acceptance-scope-file <path>] [--implementer-id <id>] [--implementer-session-id <id>]` — open a new local governance run and create or reuse the working branch for that run
- `/ai-change checkpoint --run-id <id> --message "<commit message>" [--paths <path ...> | --all] [--title "<title>"]` — commit the current checkpoint and refresh the branch-local review bundle
- `/ai-change prepare-pr --run-id <id> [--title "<title>"] [--base-branch main] [--head-branch <branch>] [--staged | --branch-diff] [--paths <path ...>] [--acceptance-source <doc ...>] [--acceptance-mode scoped|strict] [--acceptance-scope-file <path>]` — generate the local review governance summary, acceptance inventory, scoped/strict acceptance gates, and machine-readable review manifest
- `/ai-change independent-review --run-id <id> [--provider claude|codex] [--model <model>] [--reviewer-id <id>] [--reviewer-session-id <id>]` — launch a separate AI code-review session and store `independent_review.json` / `independent_review.md` for the current reviewed branch state
- `/ai-change review-feedback --run-id <id> [--review-result <state>] [--findings-count <n>] [--blocking-findings-count <n>] [--next-action <state>] [--review-notes "<notes>"] [--acceptance-evidence-file <json>] [--acceptance-mode scoped|strict] [--acceptance-scope-file <path>] [--reviewer-id <id>] [--reviewer-session-id <id>] [--independent-review-artifact <json>]` — refresh the local review artifacts from the current branch diff and optionally persist the local review verdict for that reviewed branch state
- `/ai-change ready-for-review --run-id <id> [--title "<title>"]` — require a clean worktree, refresh the review bundle, and mark the branch ready for local review
- `/ai-change status [--run-id <id>]` — print the active run state
- `/ai-change <path ...> --format json` — analyze-only report for explicit paths

## Default Flow

1. Read `docs/ai_change_governance.md`.
2. Read `docs/coder_guide.md` and `docs/architecture.md`.
3. Start a run with one task summary; `/ai-change` will create or reuse the run branch.
4. Work on that run branch inside the real repo root.
5. Keep `git config core.hooksPath .githooks` enabled in this clone so
   `.githooks/pre-push` blocks direct pushes to `main`.
6. Use `checkpoint` for each meaningful milestone. The safe default is staged-only; use `--paths` or `--all` only when you really mean it.
7. Let `checkpoint` refresh the local review bundle from the current branch diff.
8. Run the targeted local checks selected by `.claude/scripts/ai_change_governance.py`.
9. Use `ready-for-review` when the branch is ready for the local review pass.
10. Merge only after human review of the local branch diff and the automation output.

## Autopilot Loop

1. `/ai-change autopilot "<task>"` starts an autopilot run and binds the session to one branch.
2. The agent edits code normally inside the session.
3. After each meaningful batch, the agent runs `checkpoint` so the branch and local review bundle stay current.
4. Every phase-complete checkpoint is a mandatory review checkpoint; the agent must not keep stacking the next implementation phase onto an unreviewed meaningful milestone.
5. The agent runs `ready-for-review` at that checkpoint.
6. The agent runs `independent-review` to launch a separate AI code-review session for medium/high-risk approval, then runs `review-feedback` with the resulting artifact.
   Acceptance mode defaults to `scoped`: imported unscoped acceptance-source
   bullets stay context/audit inventory. Only explicit scope files or strict
   mode create acceptance evidence blockers; the old default procedural
   checklist is not generated.
7. If the feedback contains actionable defects, the agent fixes them and returns to `checkpoint`.
8. If the feedback is clean or only advisory, the agent may either stop or begin the next implementation phase; review is not reserved for the final branch state.

## Restrictions
- Do not perform state-changing `/ai-change` edits outside a real git repository.
- Do not bypass `.githooks/pre-push` for routine work; use `AI_CHANGE_ALLOW_DIRECT_MAIN_PUSH=1` only for an explicit emergency/admin push.
- Do not let `autopilot` silently auto-merge after review; merge remains a human decision unless the user explicitly changes that policy later.
- Do not drop explicit acceptance-source inventory from the local review bundle when the run declared it.
- Do not persist medium/high-risk `approved` / `approved_with_advisories` without a fresh AI-generated independent review artifact tied to the reviewed head commit.
- Do not persist medium/high-risk approval when implementer or reviewer identity/session is unknown, or when implementer/reviewer identity or session matches.
- Do not invent a second state machine outside `.claude/scripts/ai_change_governance.py`.
- Do not expand top-level command docs with execution detail; keep the stable command index in `AGENTS.md` and `CLAUDE.md` compact.
