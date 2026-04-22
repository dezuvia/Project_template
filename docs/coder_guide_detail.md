# Coder Guide — Whatodo Coding Agent Standards

**Scope**: All coding agents (Claude, Codex, and others) MUST read this file before any system design, debugging, coding, or code review task.

---

## 0. Mandatory Pre-Work Checklist

Before proposing any solution, confirm:

- [ ] Have I read `docs/architecture.md` for global context?
- [ ] For non-trivial state-changing work, have I used `/ai-plan autopilot` or
      recorded why durable planning is unnecessary?
- [ ] If this task designs, debugs, or changes command orchestration or backend routing, have I read `docs/local-mcp-backend-design.md`?
- [ ] If this task fixes or updates a larger command or workflow (for example `/research`), have I planned the matching `/systemdesign` update in `docs/systemdesign/architect_<commandname>/` in the same change?
- [ ] Does my solution conflict with or duplicate an existing component?
- [ ] Am I solving the **actual problem** or a symptom of it?
- [ ] Is this fix general, or am I overfitting to a single test case?
- [ ] Is my solution's complexity proportional to the problem's real weight in the system?

---

## 1. Governance Hierarchy

The conflict-resolution order is:

1. `AGENTS.md`
2. `.claude/agents/*.md`
3. `CLAUDE.md`
4. `.claude/commands/*.md`
5. `.claude/scripts/*.py`

**Self-check rule**: If you are about to add behavior to a top-level file (`AGENTS.md`, `CLAUDE.md`), stop. Push the detail down to the appropriate `.claude/` layer instead. Top-level files must remain compact indexes, not executable specs.

**Bloat prevention**: When a lower-level governance layer is stable and well-tested, actively migrate its settled patterns up one level and remove redundancy below. Never let top-level files silently absorb detail that belongs lower.

---

## 2. Scripting and Automation Strategy

### Repetitive work → script first
If a task will recur, build a script rather than repeating ad hoc steps. Do not reimplement logic inline that already exists in `.claude/scripts/`.

### Repetitive + ambiguous work → local MCP backend plus explicit AI stage
If the task involves judgment, classification, or any non-zero ambiguity, do **not** use deterministic logic (keyword matching, rule lists, hard-coded mappings). Instead, route deterministic orchestration through a local stdio MCP backend and keep the ambiguous decision in an explicit AI/generative stage.

Design command workflows with these responsibilities:
- **Orchestration layer**: accept user input, manage human checkpoints, and call the command-side adapter.
- **Command-side adapter**: translate the command flow into local backend tool calls with stable arguments/results.
- **Local MCP backend**: expose deterministic tools and call shared Python helpers directly.
- **Generative stage**: perform planning, classification, or review with a scoped prompt contract and structured output.

**Codex-specific reminder**: Do not default to nested AI child sessions for command execution. When ambiguity exists, define the generative stage explicitly in the workflow or backend contract, or Codex will tend to hard-code a brittle workaround.

### Non-trivial implementation → planning router first
Use `/ai-plan autopilot` before larger state-changing work when intent,
architecture surfaces, validation strategy, or acceptance scope are not already
durable. `/ai-plan` records the planning contract and emits scoped handoff
artifacts for `/ai-change`; it does not replace `/ai-change` branch
management, checkpoint commits, local branch review, or merge readiness.

Template-derived command orchestration should keep deterministic `/ai-plan`
artifact management in shared helpers or a local MCP adapter/server pair, while
semantic planning judgment remains an explicit generative stage. Do not hide
architecture, harness, or LLM-delegation review behind ad hoc nested Codex
child sessions.

Planning runs should make these boundaries explicit:

- fixed: requirements, architecture surfaces, implementation slices,
  acceptance ids, required checks, and stop conditions
- open: implementation style and local refactoring choices inside the owned
  surfaces
- generative: semantic judgment, plan review, harness adequacy, and LLM
  delegation decisions
- deterministic: file existence, schema validation, trace references, and
  handoff path integrity

If a plan depends on a semantic decision, record the decision as `generative`
or `hybrid` and route it through a declared workflow stage. Do not turn
semantic plan quality into keyword matching or a regex gate.

---

## 3. Problem Diagnosis Before Solution

### Check the input layer first
Bugs and unexpected behavior often originate at the **input boundary** (malformed data, wrong assumptions about upstream format, schema drift). Agents tend to over-focus on the process layer. Always verify:
- What does the actual input look like?
- Does the input match the assumed contract?
- Is there a fundamental assumption that is wrong?

### Resist the tunneling effect
When a problem is raised, the instinct is to add: a new feature, a new variable, a new checker, a new gate. Ask instead:
- Is this addition actually solving the stated problem?
- Does adding this make the system simpler or more complex?
- Would removing something fix this better than adding something?


---

## 4. Overfitting and Generalization

### Distinguish test cases from general cases
Before implementing a fix, explicitly classify the triggering case:
- **General use case**: the fix must work across all realistic inputs.
- **Test/edge case**: the fix addresses a narrow scenario — do not let it distort general behavior.

If the triggering case is a test, write the fix to the **general contract**, then verify it handles the test. Never write a fix that only handles the test.

### Fork-and-fix for non-trivial debugging
When debugging a complex or multi-session issue:
1. Fork the working state (branch or isolated copy) before making changes.
2. Create a fix-specific context note capturing: what the system does normally, what the current fix targets, and which parts of the test are edge cases vs. general behavior.
3. This prevents the agent from losing the big picture mid-fix and accidentally over-fitting to the test case.

---

## 5. System-Level Efficiency

### Proportion effort to global feature weight
Before adding a checker, audit trail, validator, or new processing stage, ask: **how important is this to the overall system?** A low-frequency edge case does not justify a heavyweight gate that runs on every execution.

### Pass only what the backend or AI stage needs
When constructing a local MCP tool request or explicit AI prompt context:
- Identify the **minimum data granularity** the task requires (metadata vs. full content).
- Do not dump raw data when metadata suffices.
- Do not dump full records when only IDs and a few fields are needed.
- Explain the required granularity explicitly in the prompt or tool contract.

### Reuse upstream work — do not rebuild
Before writing a processing step, check what the **previous step already produced**. If a label, tag, or field was computed upstream, read it — do not recompute it. Duplication of upstream work is a red flag; surface it and eliminate it.

---

## 6. Ambiguity Handling

### Never fake determinism
If a decision involves ambiguity (classifying text, inferring intent, judging relevance), do **not** invent a deterministic proxy (keyword lists, character counts, regex heuristics). These are brittle and wrong by construction.

The correct response to ambiguity is:
1. **Use existing metadata** to infer — check what fields are already available before building new logic.
2. **Route the judgment through the workflow's explicit AI/generative stage** or backend-owned planner with an explicit prompt contract.
3. **Expose the ambiguity** to the user if a policy decision is required.

### Prompt engineering over magic weights
When an AI-driven step needs tuning (e.g., how strictly to follow evidence, how much weight to give a source), this is a prompt engineering problem. Iterate on the prompt explicitly; do not introduce numeric weights or hidden thresholds that turn into undebuggable knobs.

---

## 7. Creative Latitude

Compliance framing (excessive caution, always hedging, always asking permission) suppresses useful output. Agents should apply judgment and act within their authority. Explicitly note in task prompts when the agent has latitude to:
- Choose implementation details freely.
- Propose an alternative approach.
- Simplify or restructure without prior approval.

State what is **fixed** (interface, contract, output schema) versus what is **open** (implementation, style, internal structure). This prevents both over-caution and over-reach.

---

## 8. Script and Context Hygiene

### Keep scripts token-friendly
Scripts must not become bloated. Signs of bloat:
- A script that handles more than one distinct concern.
- Functions longer than ~50 lines without a clear sub-task boundary.
- Config and logic mixed in the same block.

When a script exceeds these thresholds, refactor before extending it further.

**Growth check**: Before adding any new feature to an existing script, explicitly ask: *does this belong here, or should it be a separate script?* Scripts tend to grow by accretion — each addition seems small, but the cumulative result is a long monolith that is slow to load into context, hard to debug, and hard to maintain. Two focused 40-line scripts are always better than one 80-line script that handles two concerns.

### No unnecessary data dumps in context windows
Every token in a session context has a cost. Before including a data structure in a prompt:
- Can the backend or AI stage work from an ID + lookup instead of a full record?
- Can a summary or schema description replace raw content?
- Is this data actually used, or is it "just in case"?

---

## 9. Command/Workflow Architecture Discipline

When fixing or updating a larger command or workflow, update the matching
`/systemdesign` spec in the same change. For command-specific architecture, the
SSOT lives under `docs/systemdesign/architect_<commandname>/`.

Example:
- `/research` changes must update `docs/systemdesign/architect_research/` when
  they alter pipeline behavior, prompts, stages, artifact contracts, schemas, or
  other command-level workflow semantics.

Do not leave command or workflow behavior changed in code, prompts, or command
docs while the corresponding `/systemdesign` spec remains stale.

---

## 10. Quick Self-Test Before Submitting

Run through these before finalizing any design or implementation:

1. **Root cause check**: Am I solving the root cause or a symptom?
2. **Complexity check**: Is this the simplest solution that correctly handles the general case?
3. **Duplication check**: Does this replicate work already done upstream or in another component?
4. **Granularity check**: Am I passing/processing only the data this step actually needs?
5. **Generality check**: Does this solve the general case, or am I overfitting to a test?
6. **Architecture check**: Does this conflict with or duplicate anything in `docs/architecture.md`?
7. **Ambiguity check**: Am I using deterministic logic where an AI judgment is more appropriate?
8. **Systemdesign check**: Did I update the relevant `/systemdesign` spec if this task changed a larger command or workflow?

If any answer is "no" or "unsure", stop and resolve it before proceeding.
