# Task Spec Template

Use the lightweight format for simple tasks. Use the full format for anything touching multiple components, requiring database changes, or with meaningful complexity.

---

## Lightweight Task Spec

For bug fixes, small features, and simple refactors.

```
Title:
Type: bugfix | feature | refactor | docs | infrastructure

Summary:
[One or two sentences — what changes and why]

Files likely affected:
- path/to/file.py — what changes
- path/to/other.ts — what changes

Acceptance criteria:
- [ ] specific, verifiable condition
- [ ] specific, verifiable condition

Tests required:
- [what to test]
```

---

## Full Task Spec

### 1. Overview

**Title**:
**Type**: `feature` | `bugfix` | `refactor` | `docs` | `infrastructure`
**Summary**: One paragraph describing what changes and why.

---

### 2. Context

**Background**: Why does this task exist? What problem does it solve?

**Affected components**:
- [ ] Backend API
- [ ] Worker service
- [ ] Frontend web
- [ ] Mobile app
- [ ] Infrastructure / CDK
- [ ] Database schema

---

### 3. Requirements

**Functional requirements**:
- [What the system must do after this change]

**Non-functional requirements**:
- [Performance, compatibility, security constraints if relevant]

---

### 4. Implementation Guidelines

**Files likely affected**:
- `services/api/app/routers/example.py` — [what changes]

**New files required**:
- `services/api/app/services/new_service.py` — [purpose]

**Architecture constraints**:
- [e.g., must use FastAPI router system]
- [e.g., must use msgspec models, not Pydantic]
- [e.g., must not bypass service layer — no raw DB queries in routers]

---

### 5. Database Changes

**Schema changes**: [new tables, new columns, changed columns]

**Migration required**: yes | no

If yes: `uv run alembic revision --autogenerate -m "description_of_change"`

---

### 6. API Changes

**Endpoint**: `METHOD /path`

**Request**:
```json
{
  "field": "value"
}
```

**Response**:
```json
{
  "data": { ... }
}
```

---

### 7. Frontend Changes

[New pages, modified components, state changes, new API client methods needed]

---

### 8. Background Jobs

[If this task requires async work: job type, trigger, payload, expected behaviour]

---

### 9. Test Requirements

**Backend**:
- `test_[happy path]` — [what it verifies]
- `test_[error case]` — [what it verifies]

**Frontend**:
- [Playwright scenario if applicable]

---

### 10. Acceptance Criteria

- [ ] [Specific, verifiable condition]
- [ ] [Specific, verifiable condition]

---

### 11. Validation Steps

Commands to run before submitting:
```bash
make lint
make typecheck
make test
```

For API changes, also verify manually:
```bash
make dev
curl -X POST http://localhost:8000/path -d '{"field": "value"}'
```

---

### 12. Risks

[Potential impacts, edge cases, anything the reviewer should pay attention to]

---

## Agent Output Format

Regardless of which spec format was used, structure your response as:

**PLAN** — implementation plan, stated before writing code

**CHANGES** — files modified and the key change in each

**TESTS** — tests added or updated

**VALIDATION** — commands run and results

**RISKS** — remaining concerns or incomplete areas
