# Project Start Prompt — Architect Agent Instructions

**Audience**: Human + architect agent. Run this at the start of a new project to go from a filled-in spec to a scaffolded repository.

**Goal**: Read the project specification, resolve all architecture decisions collaboratively with the human, produce `PROJECT_BLUEPRINT.md`, and scaffold the repository.

---

## Step 1 — Load Documents

Read in full:
- Your filled-in project specification (copy of `project_spec_template.md`)
- `ai_blueprint_meta.md`
- `repo_template_spec.md`

---

## Step 2 — Summarise the Specification

Extract and present back to the human:
- Product purpose and type
- Core features and user model
- Data characteristics and scale
- Real-time requirements
- Mobile requirements
- Background job requirements
- Security and compliance requirements
- External integrations
- Operational priorities

Ask for corrections before proceeding.

---

## Step 3 — Resolve Decision Slots

Work through every slot in the decision table in `ai_blueprint_meta.md`.

For each slot:
1. Check if the spec or human has stated a preference
2. If not, propose the default with a one-line justification
3. Flag any slot where the default is non-obvious or trade-offs are significant — **discuss with the human before deciding**

Do not proceed to blueprint generation until all slots are resolved and the human has confirmed the decisions.

---

## Step 4 — Generate PROJECT_BLUEPRINT.md

Produce a document containing:

1. Product Architecture Overview
2. Resolved Technology Stack (every slot decision with justification)
3. Cloud Infrastructure Layout (services, networking, data stores)
4. Data Architecture (core schema overview, storage decisions per data type)
5. API Architecture (style, auth model, error format, versioning)
6. Frontend Architecture
7. Mobile Strategy
8. Background Job System (queue design, job types, failure handling)
9. Repository Structure (actual directory tree for this project)
10. Development Workflow (local setup, key commands)
11. CI/CD Pipeline
12. Testing Strategy
13. Security Model
14. Observability Setup (logging format, future instrumentation)
15. Deployment Model (per environment)
16. Delivery Roadmap — Phase 1 scope clearly bounded

---

## Step 5 — Validate the Blueprint

Run through the Blueprint Validation Checklist in `ai_blueprint_meta.md`. Revise if anything is missing or inconsistent.

Present the completed blueprint to the human for review before scaffolding.

---

## Step 6 — Scaffold the Repository

Using `repo_template_spec.md`, create the repository structure including:

- Directory layout
- Baseline service implementations (health endpoint, example router, worker loop, example page)
- Makefile with all required targets
- Docker Compose for local development
- CI/CD workflow files (`.github/workflows/`)
- Fill in `AGENTS.md.template` and `ARCHITECTURE.md.template` with project-specific content and place them at `docs/AGENTS.md` and `docs/ARCHITECTURE.md`
- `.env.example` from `.env.example.template`

---

## Step 7 — Generate Starter Task Specs

Produce initial task specs (using `task_spec_template.md`) for the first development sprint:

- Authentication implementation
- Core feature database schema and migrations
- First domain API endpoints
- Frontend UI scaffold for core feature
- Background job setup (if `background_jobs != none`)
