# Whatodo AGENTS (Codex Translation Layer)

This file is the Codex-facing top-level contract for the workspace.
It translates the `CLAUDE.md` + `.claude/` system into a compact policy and command index.
Executable procedure belongs in `.claude/commands/*.md`.
Workflow detail belongs in `.claude/agents/*.md`.

## Scope and Source of Truth
- System architecture source: `docs/architecture.md` (cross-component design, control points, invariants, change protocol).
- Coding standards source: `docs/coder_guide.md` — **MUST read before any system design, debug, coding, or code review task**.
- Primary Claude-facing command contract: `CLAUDE.md`.
- Detailed workflow source: `.claude/agents/*.md`.
- Detailed command execution source: `.claude/commands/*.md`.
- Script truth for flags and side effects: `.claude/scripts/*.py`.

**Conflict-resolution hierarchy**:
1. `AGENTS.md`
2. `.claude/agents/*.md`
3. `CLAUDE.md`
4. `.claude/commands/*.md`
5. `.claude/scripts/*.py`

## Role
- You are a task-management assistant for Whatodo.
- Help users manage tasks and workflows through conversation and maintain project state with committed changes.

## Command Compatibility Layer
Treat user messages that start with `/` as commands.
The command sections below are intentionally compact; full procedure lives in `.claude/commands/*.md` and `.claude/agents/*.md`.

### `/ai-change`
- `/ai-change <subcommand>` is the git/local-review governance entrypoint for AI-assisted state-changing work.
- Use it when a task needs branch-bound checkpoints, local branch-diff review bundles, acceptance-source tracking, or independent AI review.
- Detailed execution behavior lives in `.claude/commands/ai-change.md`.

### `/ai-plan`
- Detailed execution behavior lives in `.claude/commands/ai-plan.md`.

## Hard Rules
- `AGENTS.md` and `CLAUDE.md` command sections must stay compact and point to `.claude/commands/*.md` for executable detail.
- Workflow detail must stay in `.claude/agents/*.md`; never duplicate it here.
- Always commit state-changing operations with clear messages.

## Codex-Specific Execution Notes
- Prefer running project scripts for command behavior instead of re-implementing logic ad hoc.
- Prefer `.claude/scripts/ai_change_governance.py` as the default AI-assisted change governance entrypoint; policy lives in `docs/ai_change_governance.md`.
- Use concrete dates (`YYYY-MM-DD`) in any index or state updates.
- Codex skills live under `codex/skills/` and are orchestration-only; behavior changes there must stay mirrored with Claude-facing behavior sources.
