# Agent Operating Manual

**Audience**: AI coding agents working inside a generated project repository.

This is your operating guide. Read `docs/AGENTS.md` in the project for project-specific commands, conventions, and standards. This document covers general operating behaviour that applies across all projects built with this framework.

---

## Before Starting Any Task

Read these if you haven't already this session:
- `docs/AGENTS.md` — commands, coding standards, definition of done for this project
- `docs/ARCHITECTURE.md` — component boundaries and data flow

If either file is missing or incomplete, flag it — don't guess at conventions.

---

## Workflow

For every task, in order:

1. **Plan before coding** — identify the files you'll change, the dependencies involved, and any risks. State the plan explicitly before writing code. For anything non-trivial, confirm the plan is correct before proceeding.
2. **Implement** — follow the conventions in `docs/AGENTS.md`. Small, focused changes.
3. **Test** — write tests for new behaviour. Fix tests broken by the change.
4. **Validate** — run `make lint && make typecheck && make test` and confirm they pass.
5. **Summarise** — produce a response in the Output Format below.

---

## Hard Boundaries — Stop and Raise Rather Than Proceed

- Do not redesign architecture or change component boundaries
- Do not modify CDK / infrastructure code unless the task explicitly requires it
- Do not introduce new packages or external dependencies without justification
- Do not change database schema without a migration
- Do not push directly to `main`

When a task feels like it requires crossing one of these, stop, describe what you found, and ask how to proceed. Don't work around it.

---

## Task Sizing

Break work into small, independently reviewable units. One PR, one concern.

Good: add endpoint, fix bug, add test, refactor single module, update dependency
Bad: implement entire feature area, redesign data model, rewrite service from scratch

If a task spec seems too large, split it and say so.

---

## Output Format

Structure every response as:

**PLAN** — what you intend to do and why, before you do it

**CHANGES** — files modified and the key change in each

**TESTS** — tests added or updated

**VALIDATION** — commands run and their output (pass/fail)

**RISKS** — anything incomplete, uncertain, or potentially impactful that the reviewer should know about

---

## Definition of Done

A task is complete when:
- [ ] All acceptance criteria from the task spec are met
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes with no new errors introduced
- [ ] If architecture, commands, or APIs changed — relevant docs updated
- [ ] PR summary written in the Output Format above
