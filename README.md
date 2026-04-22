# Project Template / 專案模板

## 一般使用方式 / Normal Usage

一般使用者主要只需要 `autopilot`。其他子命令是進階操作，通常只在恢復中斷流程、除錯治理狀態、或手動控制每個 checkpoint 時才需要。

Most users should start with `autopilot`. The other subcommands are advanced controls for resuming interrupted runs, debugging governance state, or manually controlling each checkpoint.

建議流程 / Recommended flow:

```text
/ai-plan autopilot "<describe the change you want>"
```

`/ai-plan autopilot` 會規劃工作，並在結果裡列出下一步要執行的 `/ai-change autopilot ...` 指令。把它輸出的那行 `/ai-change autopilot ...` 指令貼上執行即可。

`/ai-plan autopilot` plans the work and prints the next `/ai-change autopilot ...` command to run. Paste and run that printed `/ai-change autopilot ...` command.

```text
/ai-change autopilot "<task summary printed by ai-plan>" --acceptance-source <plan-source printed by ai-plan> --acceptance-scope-file .claude/ai_plan_runs/<run_id>/acceptance_scope.json
```

如果是很小、很明確、沒有 durable planning 需求的修改，可以直接使用 `/ai-change autopilot`。

For very small, obvious changes that do not need durable planning, use `/ai-change autopilot` directly.

```text
/ai-change autopilot "<change summary>"
```

## 中文

這是一個空白專案模板，內建 `/ai-plan` 與 `/ai-change` 治理流程，適合用來建立需要 spec-driven planning、AI 協作、分支檢查、在地 review bundle、以及獨立 AI review 的新專案。

### 這個模板包含什麼

- `AGENTS.md`：Codex 讀取的頂層協作與治理規則。
- `CLAUDE.md`：Claude-facing 的頂層命令索引與專案規則。
- `CommandGuide.md`：可用 slash command 的快速索引。
- `.claude/commands/ai-plan.md`：`/ai-plan` 的命令契約與操作入口。
- `.claude/commands/ai-change.md`：`/ai-change` 的命令契約與操作入口。
- `.claude/scripts/ai_plan_governance.py`：pre-implementation planning artifact manager。
- `.claude/scripts/ai_change_governance.py`：治理流程的主要腳本。
- `.claude/hooks/ai_change_guard.py`：防止在非 git 專案中直接做狀態變更的 hook。
- `.githooks/pre-push`：阻擋直接 push 到 `main` 的本地 git hook。
- `docs/ai_plan_governance.md`：spec-driven planning 與 `/ai-plan` 治理政策。
- `docs/ai_change_governance.md`：AI-assisted change governance 政策文件。
- `docs/systemdesign/architect_ai_plan/`：`/ai-plan` 的架構契約、schema、常數。
- `docs/systemdesign/architect_ai_change/`：`/ai-change` 的架構契約、schema、常數。
- `docs/architecture.md`：專案架構 SSOT。
- `docs/architecture_guide.md`：新增或修改 command backend workflow 時的 `docs/systemdesign/architect_<commandname>/` 建立與同步規則。
- `docs/coder_guide.md`：coding agent 的工作規範。

### Spec-driven development 與架構規則

- 非瑣碎的 state-changing work 應先使用 `/ai-plan` 建立 durable planning intent、decision-surface classification、scoped acceptance、以及 `/ai-change` handoff。
- AI-assisted implementation、branch checkpoint、local branch-diff review、以及 independent AI review 由 `/ai-change` 負責。
- `docs/architecture.md` 是跨元件架構 SSOT；改變架構、layer ownership、或治理流程時必須同步更新。
- 每個有 backend workflow 的 command 都必須有對應的 `docs/systemdesign/architect_<commandname>/` 目錄，作為 data flow、script inventory、function contract、prompt spec 的 SSOT。
- 新增 command 時，從 `docs/systemdesign/architect_example/` 複製出 `architect_<commandname>/`，並在 `AGENTS.md`、`CLAUDE.md`、`.claude/commands/<commandname>.md` 建立 compact pointer。

### 建立新專案後

1. 將這個模板複製成新的專案目錄。
2. 在新專案中初始化 git：

```bash
git init
```

3. 啟用本地 push guard：

```bash
git config core.hooksPath .githooks
```

4. 建立初始 commit：

```bash
git add .
git commit -m "Initialize project from template"
```

### 使用 `/ai-plan`

`/ai-plan` 是非瑣碎 AI-assisted implementation 前的 planning router。它會建立 durable plan trace、decision-surface inventory、scoped acceptance、required checks、open policy questions，並輸出 `/ai-change` handoff artifacts。

主要 user-facing 指令：

```text
/ai-plan autopilot "<planning request>"
```

進階指令：

```text
/ai-plan autopilot --plan-source <path ...> --title "<title>"
/ai-plan validate --run-id <id>
/ai-plan handoff --run-id <id>
```

`validate` 和 `handoff` 主要給 agents、恢復流程、或手動檢查 planning artifacts 使用；一般使用者通常只需要 `autopilot`。

詳細政策請看 `docs/ai_plan_governance.md`，命令細節請看 `.claude/commands/ai-plan.md`，architecture contract 請看 `docs/systemdesign/architect_ai_plan/`。

### 使用 `/ai-change`

`/ai-change` 是 AI-assisted state-changing work 的治理入口。它會把變更綁定到真實 git branch，建立 checkpoint commit，產生 local branch-diff review bundle，並在 medium/high-risk approval 前要求獨立 AI review。

主要 user-facing 指令：

```text
/ai-change autopilot "<task summary>"
```

`autopilot` 會在同一個治理 run 中循環處理 implementation、checkpoint、ready-for-review、independent review、review-feedback、以及下一步判斷。一般使用者不需要手動串下面這些子命令。

進階指令：

```text
/ai-change start-run --task-summary "<change summary>"
/ai-change checkpoint --run-id <id> --message "<checkpoint message>" --paths <path ...>
/ai-change ready-for-review --run-id <id>
/ai-change independent-review --run-id <id>
/ai-change review-feedback --run-id <id> --review-result <state>
```

進階指令適合用在手動控制 checkpoint、修復中斷 run、重跑 review、或除錯 governance artifact。

詳細政策請看 `docs/ai_change_governance.md`，命令細節請看 `.claude/commands/ai-change.md`。

### 注意事項

- 請先把衍生專案初始化成真正的 git repository，再使用會修改狀態的 `/ai-change` run。
- `/ai-plan` 不取代 `/ai-change` 的 branch management、checkpoint commit、merge readiness、或 review-feedback state。
- `/ai-change` 不會自動 merge；merge 仍然是 human decision。
- `.claude/ai_plan_runs/` 是每個專案執行後產生的 planning 狀態，不是模板本身需要預先填入的內容。
- `.claude/ai_change_runs/` 是每個專案執行後產生的治理狀態，不是模板本身需要預先填入的內容。
- 如果衍生專案有自己的測試，請把測試命令接到專案自己的文件或治理腳本中。

---

## English

This is a blank project template with `/ai-plan` and `/ai-change` governance workflows built in. It is intended for new projects that use spec-driven planning, AI-assisted development, branch-bound checkpoints, local review bundles, and independent AI review for higher-risk changes.

### What This Template Includes

- `AGENTS.md`: Top-level collaboration and governance rules for Codex.
- `CLAUDE.md`: Claude-facing top-level command index and project rules.
- `CommandGuide.md`: Quick index of available slash commands.
- `.claude/commands/ai-plan.md`: Command contract and entrypoint for `/ai-plan`.
- `.claude/commands/ai-change.md`: Command contract and entrypoint for `/ai-change`.
- `.claude/scripts/ai_plan_governance.py`: Pre-implementation planning artifact manager.
- `.claude/scripts/ai_change_governance.py`: Main governance workflow script.
- `.claude/hooks/ai_change_guard.py`: Hook that blocks direct state-changing edits outside a real git repository.
- `.githooks/pre-push`: Local git hook that blocks direct pushes to `main`.
- `docs/ai_plan_governance.md`: Policy document for spec-driven planning and `/ai-plan` governance.
- `docs/ai_change_governance.md`: Policy document for AI-assisted change governance.
- `docs/systemdesign/architect_ai_plan/`: Architecture contract, schemas, and constants for `/ai-plan`.
- `docs/systemdesign/architect_ai_change/`: Architecture contract, schemas, and constants for `/ai-change`.
- `docs/architecture.md`: Architecture source of truth.
- `docs/architecture_guide.md`: Rules for creating and syncing `docs/systemdesign/architect_<commandname>/` when adding or changing command backend workflows.
- `docs/coder_guide.md`: Working rules for coding agents.

### Spec-Driven Development And Architecture Rules

- Use `/ai-plan` before non-trivial state-changing work when the task needs durable planning intent, decision-surface classification, scoped acceptance, or `/ai-change` handoff.
- `/ai-change` owns AI-assisted implementation, branch checkpoints, local branch-diff review, and independent AI review.
- `docs/architecture.md` is the cross-component architecture SSOT. Update it when architecture, layer ownership, or governance workflow rules change.
- Every command with a backend workflow must have a corresponding `docs/systemdesign/architect_<commandname>/` directory as the SSOT for data flow, script inventory, function contracts, and prompt specs.
- When adding a command, copy `docs/systemdesign/architect_example/` to `architect_<commandname>/`, then add compact pointers in `AGENTS.md`, `CLAUDE.md`, and `.claude/commands/<commandname>.md`.

### After Creating a New Project

1. Copy this template into a new project directory.
2. Initialize git in the new project:

```bash
git init
```

3. Enable the local push guard:

```bash
git config core.hooksPath .githooks
```

4. Create the initial commit:

```bash
git add .
git commit -m "Initialize project from template"
```

### Using `/ai-plan`

`/ai-plan` is the planning router before non-trivial AI-assisted implementation. It creates durable plan trace, decision-surface inventory, scoped acceptance, required checks, open policy questions, and `/ai-change` handoff artifacts.

Primary user-facing command:

```text
/ai-plan autopilot "<planning request>"
```

Advanced commands:

```text
/ai-plan autopilot --plan-source <path ...> --title "<title>"
/ai-plan validate --run-id <id>
/ai-plan handoff --run-id <id>
```

`validate` and `handoff` are mainly for agents, resumed workflows, or manual artifact checks. Most users only need `autopilot`.

For policy details, read `docs/ai_plan_governance.md`. For command details, read `.claude/commands/ai-plan.md`. For the architecture contract, read `docs/systemdesign/architect_ai_plan/`.

### Using `/ai-change`

`/ai-change` is the governance entrypoint for AI-assisted state-changing work. It binds the work to a real git branch, records checkpoint commits, creates local branch-diff review bundles, and requires independent AI review before medium/high-risk approval is persisted.

Primary user-facing command:

```text
/ai-change autopilot "<task summary>"
```

`autopilot` keeps implementation, checkpoint, ready-for-review, independent review, review-feedback, and next-step selection inside one governance run. Most users do not need to manually chain the subcommands below.

Advanced commands:

```text
/ai-change start-run --task-summary "<change summary>"
/ai-change checkpoint --run-id <id> --message "<checkpoint message>" --paths <path ...>
/ai-change ready-for-review --run-id <id>
/ai-change independent-review --run-id <id>
/ai-change review-feedback --run-id <id> --review-result <state>
```

Use advanced commands when manually controlling checkpoints, repairing an interrupted run, rerunning review, or debugging governance artifacts.

For policy details, read `docs/ai_change_governance.md`. For command details, read `.claude/commands/ai-change.md`.

### Notes

- Initialize derived projects as real git repositories before using state-changing `/ai-change` runs.
- `/ai-plan` does not replace `/ai-change` branch management, checkpoint commits, merge readiness, or review-feedback state.
- `/ai-change` does not auto-merge; merge remains a human decision.
- `.claude/ai_plan_runs/` is generated per project during actual planning runs. It does not need to be pre-populated in the template.
- `.claude/ai_change_runs/` is generated per project during actual runs. It does not need to be pre-populated in the template.
- If the derived project has its own test suite, wire those checks into the project-specific docs or governance script.
