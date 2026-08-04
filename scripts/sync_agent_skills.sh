#!/usr/bin/env bash
# Re-sync curated skills from addyosmani/agent-skills into .cursor/skills/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="${TMPDIR:-/tmp}/agent-skills-sync-$$"
SKILLS=(
  using-agent-skills
  test-driven-development
  code-review-and-quality
  shipping-and-launch
  debugging-and-error-recovery
  git-workflow-and-versioning
  incremental-implementation
  planning-and-task-breakdown
  security-and-hardening
  api-and-interface-design
  frontend-ui-engineering
  ci-cd-and-automation
  observability-and-instrumentation
  deprecation-and-migration
  code-simplification
)

cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

git clone --depth 1 https://github.com/addyosmani/agent-skills.git "$TMP"
mkdir -p "$ROOT/.cursor/skills" "$ROOT/.cursor/references"
for s in "${SKILLS[@]}"; do
  rm -rf "$ROOT/.cursor/skills/$s"
  cp -a "$TMP/skills/$s" "$ROOT/.cursor/skills/$s"
done
cp -a "$TMP/references/." "$ROOT/.cursor/references/"
for s in "${SKILLS[@]}"; do
  mkdir -p "$ROOT/.cursor/skills/$s/references"
  cp -a "$ROOT/.cursor/references/." "$ROOT/.cursor/skills/$s/references/"
done
git -C "$TMP" rev-parse HEAD > "$ROOT/.cursor/skills/.upstream-sha"
printf '%s\n' \
  "source: https://github.com/addyosmani/agent-skills" \
  "mode: curated subset" \
  "synced: $(date -u +%Y-%m-%d)" \
  > "$ROOT/.cursor/skills/README.md"
echo "Synced $(git -C "$TMP" rev-parse --short HEAD) → .cursor/skills/ (${#SKILLS[@]} skills)"
