# Local MCP Backend Design

This note defines the default command-backend pattern for the Whatodo template.
It replaces the older idea that nested Codex child sessions are the normal way
to orchestrate ambiguous or multi-step command work.

## Core pattern

1. Keep the public `/command` contract in `AGENTS.md`, `CLAUDE.md`,
   `.claude/commands/*.md`, and `.claude/agents/*.md`.
2. Use `*_mcp_client.py` as the command-side adapter.
3. Use `*_mcp_server.py` as the local stdio MCP backend entrypoint.
4. Keep reusable business logic in importable helpers so the MCP server and any
   CLI entrypoint call the same Python functions directly.
5. Keep AI judgment explicit. If a workflow needs planning, classification,
   review, or synthesis, define that work as a named generative stage with a
   prompt contract instead of hiding it behind ad hoc nested session spawning.

## Design rules

- Prefer local stdio MCP backends for command orchestration.
- Do not reimplement backend logic in command docs, agent docs, or skills.
- Do not shell one helper script through another when both can import the same
  shared backend logic directly.
- Keep command syntax, human checkpoints, and output contracts stable unless the
  change intentionally edits the public command contract.
- Return structured, machine-readable failures from backend tools.
- Fail closed when the workflow contract says an AI-owned stage must not degrade
  into deterministic fallback behavior.

## Deterministic vs generative boundaries

- `*_mcp_client.py` and `*_mcp_server.py` may both remain deterministic even
  when the overall command includes AI reasoning.
- Mark the actual AI-owned stage as `generative` in command docs and
  `docs/systemdesign/architect_<commandname>/`.
- AI judgment may stay in-session or sit behind an explicit backend-owned
  planner/reviewer tool, but it should never be the implicit default transport
  layer for command execution.

## Data granularity

- Pass only the fields a tool or prompt actually needs.
- Prefer IDs, metadata, and file paths over raw content dumps.
- Reuse upstream artifacts instead of recomputing them downstream.

## Verification expectations

- Unit-test the shared backend/helper behavior.
- Verify adapter/server JSON contracts.
- Audit docs so command, agent, skill, and architecture layers all describe the
  same adapter/server flow.
