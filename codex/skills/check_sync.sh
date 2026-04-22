#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-origin/main}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: must run inside a git repository."
  exit 2
fi

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "ERROR: base ref '$BASE_REF' not found."
  echo "Usage: bash codex/skills/check_sync.sh [base_ref]"
  exit 2
fi

skill_changed="$(git diff --name-only "$BASE_REF"...HEAD -- codex/skills | rg -v '^codex/skills/(README|MAPPING)\\.md$' || true)"
claude_changed="$(git diff --name-only "$BASE_REF"...HEAD -- AGENTS.md CLAUDE.md .claude/agents .claude/commands || true)"

errors=0

while IFS= read -r skill_file; do
  [[ -z "$skill_file" ]] && continue
  if ! rg -q "References" "$skill_file"; then
    echo "ERROR: $skill_file missing 'References' section."
    errors=1
  fi
  if ! rg -q "\\.claude/(agents|commands)/" "$skill_file"; then
    echo "ERROR: $skill_file must reference .claude/agents or .claude/commands."
    errors=1
  fi
done < <(rg --files codex/skills -g '*/SKILL.md')

if [[ -n "$claude_changed" && -z "$skill_changed" ]]; then
  echo "ERROR: Claude behavior sources changed but no Codex skill update detected."
  echo "$claude_changed" | sed 's/^/  - /'
  errors=1
fi

if [[ -n "$skill_changed" && -z "$claude_changed" ]]; then
  echo "ERROR: Codex skill behavior changed but no matching Claude source update detected."
  echo "$skill_changed" | sed 's/^/  - /'
  errors=1
fi

if [[ "$errors" -ne 0 ]]; then
  echo
  echo "Sync check failed."
  echo "Requirement: behavior changes must be mirrored across codex skills and Claude sources."
  exit 1
fi

echo "Sync check passed."
