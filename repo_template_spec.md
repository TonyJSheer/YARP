# Repository Scaffold Specification

Defines the files the architect agent must generate when scaffolding a new project. The overall structure, technology stack, and architecture rules are defined in `ai_blueprint_meta.md` — this document covers the file-level detail within each service.

---

## Backend API Service — `services/api/`

```
services/api/
  app/
    main.py           # FastAPI app init, middleware, router registration
    config.py         # Settings loaded from environment via pydantic-settings
    dependencies.py   # Shared FastAPI dependencies (db session, auth, etc.)
    routers/
      health.py       # GET /health → {"status": "ok"}
      example.py      # Example domain router
    models/
      example_model.py    # SQLAlchemy ORM models
    schemas/
      example_schema.py   # msgspec Struct definitions for request/response
    services/
      example_service.py  # Business logic layer
  tests/
    test_health.py
  pyproject.toml
  Dockerfile
  README.md
```

Requirements:
- Health endpoint at `GET /health` returns `{"status": "ok"}`
- OpenAPI docs enabled at `/docs`
- All request/response types use `msgspec.Struct` — not Pydantic models
- Business logic lives in `services/`, not in routers
- Routers are thin: validate input, call service, return response

---

## Worker Service — `services/workers/`

```
services/workers/
  worker.py         # Main loop: connects to Redis, dispatches jobs by type
  jobs/
    example_job.py  # One module per job type
  pyproject.toml
  Dockerfile
```

Requirements:
- Listens on a Redis list or stream (match the `api_style` and `background_jobs` decisions)
- Each job type is a separate module in `jobs/`
- Worker logs job start, success, and failure with structured JSON logs
- Failed jobs are moved to a dead-letter queue, not silently dropped

---

## Web Application — `apps/web/`

```
apps/web/
  app/
    layout.tsx
    page.tsx
  components/
    ExampleComponent.tsx
  lib/
    api_client.ts     # Typed API client — all API calls go through here
    config.ts         # Typed env var access
  styles/
  package.json        # next, react, typescript, tailwindcss
  README.md
```

Requirements:
- TypeScript strict mode enabled
- All API calls go through `lib/api_client.ts` — no raw `fetch()` in components
- Environment variable for API base URL: `NEXT_PUBLIC_API_URL`
- Server components by default; `"use client"` only where required

---

## Mobile App — `apps/mobile/`

Skip in Phase 1. If `mobile_support = required_at_launch`, generate:

```
apps/mobile/
  app/
  components/
  lib/
    api_client.ts
  package.json    # expo, react-native, typescript
```

---

## Shared Packages

```
packages/shared_types/   # TypeScript types matching API schemas
packages/client_sdk/     # Typed API client shared between web and mobile
```

---

## Infrastructure — `infrastructure/cdk/`

Required CDK stacks:

| Stack | Contents |
|---|---|
| `network_stack.ts` | VPC, subnets, security groups |
| `database_stack.ts` | RDS PostgreSQL, subnet group, parameter group |
| `service_stack.ts` | ECS Fargate services (API + workers), task definitions, IAM roles |
| `storage_stack.ts` | S3 bucket, Redis container on ECS |

Adjust stacks based on resolved deployment decisions (e.g., add Lambda stack if `background_jobs = lambda`).

---

## Development Tooling

### Makefile (root)

```makefile
setup      # Install all dependencies (uv sync + pnpm install)
dev        # Start all services locally via Docker Compose
test       # Run all tests (pytest + playwright)
lint       # Run ruff + ESLint
typecheck  # Run mypy + tsc
build      # Build web app and Docker images
deploy     # Deploy to target environment (requires ENVIRONMENT set)
```

### docker-compose.yml (root)

Services:
- `api` — FastAPI app on port 8000
- `worker` — Background worker
- `web` — Next.js dev server on port 3000
- `postgres` — PostgreSQL on port 5432
- `redis` — Redis on port 6379

---

## Documentation Files

Fill in these templates and place at the specified paths:

| Template | Output Path | Purpose |
|---|---|---|
| `AGENTS.md.template` | `docs/AGENTS.md` | Operating contract for AI coding agents |
| `ARCHITECTURE.md.template` | `docs/ARCHITECTURE.md` | System overview and component map |

Also create:
- `docs/DEVELOPMENT.md` — Local setup walkthrough, seed data instructions, environment variable guide, common tasks
- `README.md` (root) — Project overview, quick start, link to docs

---

## Environment Config

`.env.example` must be generated from `.env.example.template` with project-specific values filled in. Never commit real secrets.

---

## CI/CD — `.github/workflows/`

| File | Trigger | Steps |
|---|---|---|
| `ci.yml` | All PRs | lint, typecheck, backend tests, web build |
| `deploy_dev.yml` | Push to `main` | deploy to dev environment, run smoke tests |
| `deploy_prod.yml` | Manual trigger | approval gate, deploy to production |

---

## Post-Scaffold Validation

After generating the scaffold, verify:

- [ ] `make dev` starts all services without errors
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `make test` passes with no failures
- [ ] `make lint && make typecheck` passes clean
- [ ] `make build` completes without errors
- [ ] CI pipeline passes on a trivial PR
