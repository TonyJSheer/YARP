# API Conventions

Standards for all HTTP API endpoints. Applies when `api_style = rest` or `api_style = hybrid`.

For `redis_event_layer` specifics, see the Event Layer section at the bottom.

---

## URL Structure

- Lowercase with hyphens: `/user-tasks` not `/userTasks` or `/user_tasks`
- Resource nouns, not verbs: `/tasks` not `/getTasks` or `/createTask`
- Nested resources for clear ownership: `/users/{id}/tasks`
- API versioning prefix: `/api/v1/...`

## HTTP Methods

| Method | Use |
|---|---|
| `GET` | Retrieve resource(s) — no side effects |
| `POST` | Create a new resource or trigger an action |
| `PUT` | Replace a resource entirely |
| `PATCH` | Partial update |
| `DELETE` | Remove a resource |

---

## Standard Error Response

All errors return this shape:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Task with id '123' not found.",
    "field": null
  }
}
```

- `code` — machine-readable, UPPER_SNAKE_CASE string
- `message` — human-readable description suitable for logging (not necessarily for end-user display)
- `field` — the field name for validation errors, `null` otherwise

### Standard error codes

| HTTP Status | Code | When to use |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Request body or query params fail validation |
| 401 | `UNAUTHORIZED` | Not authenticated |
| 403 | `FORBIDDEN` | Authenticated but not permitted |
| 404 | `RESOURCE_NOT_FOUND` | Resource doesn't exist |
| 409 | `CONFLICT` | State conflict (e.g., duplicate, wrong state for action) |
| 422 | `UNPROCESSABLE` | Passes validation but violates a business rule |
| 500 | `INTERNAL_ERROR` | Unexpected server error — do not leak internal details |

---

## Response Envelope

Successful single-resource response:
```json
{
  "data": { ... }
}
```

Successful list response:
```json
{
  "data": [ ... ],
  "next_cursor": "eyJpZCI6MTIzfQ==",
  "has_more": false
}
```

---

## Pagination

List endpoints use cursor-based pagination (not page numbers).

**Request**: `GET /tasks?cursor=<cursor>&limit=50`

**Defaults**: limit = 50, max limit = 200

Never return unbounded lists.

---

## Authentication

All protected endpoints require:
```
Authorization: Bearer <token>
```

Unauthenticated requests return `401 UNAUTHORIZED`.

---

## Field Naming in Schemas

- `snake_case` for all field names
- Timestamps as ISO 8601 with timezone: `"2024-01-15T10:30:00Z"`
- IDs as strings (UUIDs): `"id": "550e8400-e29b-41d4-a716-446655440000"`
- Boolean fields prefixed with `is_` or `has_`: `is_active`, `has_access`
- Nullable fields must be explicitly typed as `field | None` in msgspec structs

---

## Redis Event Layer

When `api_style = redis_event_layer` or `api_style = hybrid`:

**Channel naming**: `{domain}.{entity}.{event}` — e.g., `tasks.task.created`, `tasks.task.status_changed`

**Event envelope**:
```json
{
  "event": "task.status_changed",
  "timestamp": "2024-01-15T10:30:00Z",
  "data": { ... },
  "correlation_id": "uuid"
}
```

**Client connection**: WebSocket at `/ws` or SSE at `/events` — both require `Authorization: Bearer <token>` in the connection handshake or first message.

**Command endpoints**: HTTP POST endpoints still exist for mutations (`POST /tasks`, `POST /tasks/{id}/assign`, etc.). Only the real-time subscription model changes.
