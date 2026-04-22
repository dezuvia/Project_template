# Architecture Guide — System Design Documentation

## Purpose

Every command with a backend workflow MUST have a corresponding `docs/systemdesign/architect_<commandname>/` folder.
This folder is the single source of truth for that command's data flow, script inventory, function contracts, and prompt specs.

**Read the relevant `architect_<commandname>/` before modifying any command's scripts, prompts, or pipeline logic.**

---

## Folder Convention

```
docs/systemdesign/
  architect_<commandname>/
    index.json      — stages, scripts (with functions), prompts
    schemas.json    — structured data type definitions
    constants.json  — enum values and system constants
```

For a new command, copy `docs/systemdesign/architect_example/` and rename it.

---

## File Specs

### `index.json`

Three top-level arrays: `stages`, `scripts`, `prompts`.

**Stage entry**
```json
{
  "id": "stage_name",
  "owner": "chat | terminal",
  "purpose": "one-line description",
  "scripts": ["script_id"],
  "prompts": ["PROMPT_ID"],
  "outputs": ["artifact.json"],
  "type": "generative | deterministic"
}
```

**Script entry**
```json
{
  "id": "script_id",
  "file": ".claude/scripts/script_name.py",
  "purpose": "one-line description",
  "stage_ids": ["stage_name"],
  "type": "generative | deterministic",
  "delegates_to": ["other_script_id"],
  "functions": [
    {
      "id": "function_name",
      "purpose": "one-line description",
      "type": "generative | deterministic",
      "inputs":  [{"name": "param", "schema": "str"}],
      "outputs": [{"name": "result", "schema": "str"}]
    }
  ]
}
```

**Prompt entry**
```json
{
  "id": "PROMPT_ID",
  "script": "script_id",
  "purpose": "one-line description",
  "stage_ids": ["stage_name"],
  "agent_type": "agent_role | null",
  "type": "generative",
  "inputs": ["param1", "param2"],
  "context_loaded": [
    {"artifact": "path/file.json", "how": "param_inject | path_ref | file_read", "role": "why loaded"}
  ],
  "outputs": ["output_file.md"]
}
```

### `schemas.json`

Named objects describing structured data types used in the pipeline (inputs, outputs, intermediate files).
Each entry has `required` and `optional` field maps with type strings.

### `constants.json`

Named objects for enum sets and system constants. Each entry has a `valid` array and optionally `default` and `note`.

---

## `type` Field: `generative` vs `deterministic`

| Value | Meaning |
|---|---|
| `deterministic` | Output is fully determined by inputs; no AI judgment involved |
| `generative` | Output involves an AI session, prompt, or ambiguous inference |

Mark every stage, script, and function with one of these. When a command routes through a local MCP backend, the adapter/server pair may remain `deterministic`; the explicit prompt-owned AI stage is what should be marked `generative`.

---

## When to Update

Update the relevant `architect_<commandname>/` whenever you:
- Add, rename, or remove a script or function
- Change a function's inputs or outputs
- Add or modify a prompt
- Change whether a step is generative or deterministic
- Add a new pipeline stage

Keeping this out of sync with the code is a documentation debt that causes agents to duplicate work, break data contracts, or add redundant processing steps.

---

## Registration

When a new command is added:
1. Create `docs/systemdesign/architect_<commandname>/` from the example template.
2. Register the command in `AGENTS.md` and `CLAUDE.md` as a single-line pointer.
3. Link to the architect folder from the command's `.claude/commands/<commandname>.md`.
