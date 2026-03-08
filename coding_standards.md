# Coding Standards

Standards for all code in projects built with this framework. AI coding agents must follow these without exception.

---

## Python

### Tooling

| Tool | Purpose | Config |
|---|---|---|
| `ruff` | Linting + formatting | `pyproject.toml` |
| `mypy` | Static type checking | `pyproject.toml` |
| `uv` | Package management | `pyproject.toml` |
| `pytest` | Testing | `pyproject.toml` |

### Rules

- All functions and methods must have type annotations — parameters and return types
- Use `msgspec.Struct` for all API request/response types — not Pydantic
- Business logic lives in `services/` — not in routers, not in models
- Database queries go through the service layer — no raw queries in routers or endpoints
- Use FastAPI's dependency injection for database sessions, auth, and shared resources
- No `# type: ignore` without an inline comment explaining why it's necessary
- No bare `except:` — catch specific exception types

### Naming

| Element | Convention | Example |
|---|---|---|
| Files | `snake_case` | `user_service.py` |
| Classes | `PascalCase` | `UserService` |
| Functions / methods | `snake_case` | `get_user_by_id` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |
| Private methods | `_snake_case` | `_validate_input` |
| msgspec structs | `PascalCase` | `CreateTaskRequest` |

### Router file structure

```python
# 1. Imports
# 2. Router definition
# 3. Dependencies (if specific to this router)
# 4. Route handlers — thin, delegate to service layer
```

### pyproject.toml baseline config

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## TypeScript / Next.js

### Tooling

| Tool | Purpose |
|---|---|
| TypeScript strict mode | Type checking |
| ESLint | Linting |
| Prettier | Formatting |
| pnpm | Package management |
| Playwright | End-to-end testing |

### Rules

- Strict TypeScript — no `any` without an inline comment justifying it
- No raw `fetch()` calls in components — use the typed API client in `lib/api_client.ts`
- No `process.env.X` scattered in components — access env vars through `lib/config.ts`
- Server components by default; add `"use client"` only when required (event handlers, hooks, browser APIs)
- No inline styles — use Tailwind classes

### Naming

| Element | Convention | Example |
|---|---|---|
| Component files | `PascalCase.tsx` | `TaskCard.tsx` |
| Hook files | `use[Name].ts` | `useTaskList.ts` |
| Utility / lib files | `camelCase.ts` | `formatDate.ts` |
| API client functions | `camelCase` | `createTask()`, `listTasks()` |
| Types / interfaces | `PascalCase` | `Task`, `CreateTaskRequest` |

### tsconfig.json baseline

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  }
}
```

---

## General (all languages)

- Prefer editing existing files over creating new ones
- Don't build abstractions for one-off operations — three similar lines is better than a premature abstraction
- Keep functions small and single-purpose
- No commented-out code in commits
- No TODO comments in committed code — create a task instead
