# Governance Review Contract

This template keeps high-level policy files compact and moves executable
behavior into command docs, systemdesign contracts, and scripts.

## Layer Rules

- `AGENTS.md` and `CLAUDE.md` register command families and source-of-truth
  pointers only.
- `.claude/commands/*.md` owns command dispatch procedure.
- `docs/*_governance.md` owns policy and operating model.
- `docs/systemdesign/architect_<command>/` owns stage, schema, and artifact
  contracts.
- `.claude/scripts/*.py` owns concrete flags, file writes, and validation side
  effects.
- Codex skills may orchestrate existing contracts, but must not become a hidden
  source of command behavior.
