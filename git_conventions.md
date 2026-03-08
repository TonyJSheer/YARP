# Git Conventions

---

## Branch Naming

```
feat/<short-description>      # New feature
fix/<short-description>       # Bug fix
chore/<short-description>     # Tooling, deps, config, CI
refactor/<short-description>  # Code restructure with no behaviour change
docs/<short-description>      # Documentation only
```

Examples:
- `feat/task-assignment-notifications`
- `fix/auth-token-expiry-calculation`
- `chore/upgrade-fastapi-0.115`
- `refactor/extract-user-service`

---

## Commit Messages

Format: `<type>: <short description>`

Types: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`

Rules:
- Imperative mood — "add endpoint" not "added endpoint"
- Lowercase, no trailing period
- Max 72 characters on the subject line
- If more context is needed, leave a blank line then add a body paragraph

Examples:
```
feat: add task assignment endpoint
fix: correct auth token expiry calculation
chore: upgrade FastAPI to 0.115
test: add coverage for task status transitions
refactor: extract notification logic into service
```

---

## Pull Requests

- One concern per PR — don't mix a feature with a refactor or unrelated fixes
- PR title follows the same format as commit messages
- PR body must include: Summary, Changes, Testing, Risks (see `agent_operating_manual.md`)
- PRs must pass CI before merge
- Keep PRs reviewable — aim for under 400 lines changed where possible; if larger, explain why in the description

---

## Branch Workflow

- `main` — always deployable, branch-protected
- Cut feature branches from `main`
- Merge via PR only — no direct pushes to `main`
- Delete branches after merge
- Rebase on `main` before merging if the branch is behind (prefer rebase over merge commits for a clean history)

---

## What Not to Do

- Don't force-push to `main`
- Don't `--no-verify` to skip CI hooks without an explicit reason documented in the commit
- Don't commit `.env` files, credentials, or generated build artefacts
- Don't amend commits that have been pushed and shared
