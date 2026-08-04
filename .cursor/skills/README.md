# Cursor agent-skills (curated)

Upstream: https://github.com/addyosmani/agent-skills

**Mode:** curated subset for Mission Dashboard (not all 24 skills).

Included:
- `using-agent-skills` (router)
- `planning-and-task-breakdown`
- `incremental-implementation`
- `test-driven-development`
- `debugging-and-error-recovery`
- `code-review-and-quality`
- `code-simplification`
- `security-and-hardening`
- `shipping-and-launch`
- `git-workflow-and-versioning`
- `ci-cd-and-automation`
- `observability-and-instrumentation`
- `api-and-interface-design`
- `frontend-ui-engineering`
- `deprecation-and-migration`

Shared checklists: `.cursor/references/` (also copied into each skill’s
`references/` for relative paths).

Routing rule: `.cursor/rules/agent-skills.mdc`  
Stack rule: `.cursor/rules/mission-dashboard.mdc`

Re-sync from upstream:

```bash
./scripts/sync_agent_skills.sh
```
