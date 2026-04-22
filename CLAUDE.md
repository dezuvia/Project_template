# Project Template — Claude Top-Level Contract

## Role
You are a project collaboration assistant for this workspace.
Help users manage project work through conversation, and maintain project state without changing command semantics.

## Architecture SSOT
**System architecture source**: `docs/architecture.md` — cross-component design, control points, invariants, and change protocol.
**Coding standards source**: `docs/coder_guide.md` — mandatory pre-work checklist, governance, scripting strategy, problem diagnosis, and efficiency rules for all coding agents.

**Conflict-resolution hierarchy**:
1. `AGENTS.md` — Codex policy and top-level contract
2. `.claude/agents/*.md` — Detailed workflow logic
3. `CLAUDE.md` — Claude-facing command contract
4. `.claude/commands/*.md` — Command execution steps
5. `.claude/scripts/*.py` — Script flags and side effects

`AGENTS.md` and `CLAUDE.md` are intentionally compact top-level index files.
Executable detail belongs in `.claude/commands/*.md`.
Workflow detail belongs in `.claude/agents/*.md`.

## Folder Layout
- `.claude/agents/` — Per-agent workflow definitions.
- `.claude/commands/` — Per-command execution procedures.
- `.claude/scripts/` — Helper scripts for commands and agents.
- `docs/` — Architecture, governance, and reference documentation.

## Commands
The sections below keep the stable public contract only.
Full procedure lives in `.claude/commands/*.md`.
Workflow detail lives in `.claude/agents/*.md`.

### `/ai-change`
- `/ai-change <subcommand>` is the git/local-review governance entrypoint for AI-assisted state-changing work.
- `/ai-change` creates or reuses a run branch, records checkpoints, prepares local review bundles, and can require independent AI review for medium/high-risk approval.
- Detailed execution behavior lives in `.claude/commands/ai-change.md`.

### `/ai-plan`
- Detailed execution behavior lives in `.claude/commands/ai-plan.md`.

## Rules
See `AGENTS.md` `## Hard Rules` for the authoritative set.

- `AGENTS.md` and `CLAUDE.md` command sections must stay compact and point to `.claude/commands/*.md` for executable detail.
- Workflow detail must stay in `.claude/agents/*.md`; never duplicate it here.
