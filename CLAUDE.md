# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This is the **AI Blueprint Framework** — a collection of template and reference documents used to generate and operate AI-assisted software projects. There is no application code here.

The framework covers two phases:

1. **Planning phase** — human + architect agent produce a `PROJECT_BLUEPRINT.md` and scaffold a new repository
2. **Development phase** — coding agents work from the scaffolded repo using the generated `docs/AGENTS.md`

---

## Document Map

### Planning Phase (architect agent reads these)

| File | Purpose |
|---|---|
| `project_spec_template.md` | Fill this in to describe WHAT to build |
| `ai_blueprint_meta.md` | Architecture defaults, the full decision slot table, and rules — the engineering rulebook |
| `project_start_prompt.md` | Master prompt to hand the architect agent to kick off project generation |
| `repo_template_spec.md` | File-level detail for what the scaffold must contain |

### Development Phase (coding agents in generated projects read these)

| File | Purpose |
|---|---|
| `AGENTS.md.template` | Template for `docs/AGENTS.md` in generated projects — fill in during scaffolding |
| `ARCHITECTURE.md.template` | Template for `docs/ARCHITECTURE.md` in generated projects |
| `agent_operating_manual.md` | General operating behaviour for coding agents |
| `task_spec_template.md` | Format for scoping individual development tasks |

### Reference Standards (apply to all generated projects)

| File | Purpose |
|---|---|
| `coding_standards.md` | Python and TypeScript conventions |
| `git_conventions.md` | Branch naming, commit format, PR rules |
| `api_conventions.md` | URL structure, error format, pagination, Redis event layer conventions |
| `database_conventions.md` | Alembic migrations, table/column naming, SQLAlchemy patterns |
| `.env.example.template` | Environment variable template for generated projects |

---

## How to Use

### Start a new project

1. Copy `project_spec_template.md` and fill in all sections
2. Hand the architect agent `project_start_prompt.md` along with your filled-in spec
3. Architect agent reads `ai_blueprint_meta.md`, resolves all decision slots with you, and produces `PROJECT_BLUEPRINT.md`
4. Architect agent scaffolds the repo using `repo_template_spec.md` and fills in the `*.template` files

### Create a task for a coding agent

Fill in `task_spec_template.md` (lightweight or full version). Every task must define: what changes, which files are affected, and how success is verified.

---

## Key Design Decisions Baked In

- **Decision slots** — architecture choices (`api_style`, `auth_method`, `realtime`, etc.) are resolved by human + architect agent during planning. Coding agents receive them as resolved requirements, not decisions to make.
- **`api_style: redis_event_layer`** — supported option for event-driven apps where the primary data flow is server-to-client push via Redis pub/sub, bypassing a traditional REST layer for real-time data.
- **Stack defaults**: Python + FastAPI + msgspec backend, Next.js + TypeScript frontend, AWS ECS Fargate, PostgreSQL + Redis + S3, `uv` for Python, `pnpm` for JS.
- **Monorepo**: `apps/`, `services/`, `packages/`, `infrastructure/cdk/`.
