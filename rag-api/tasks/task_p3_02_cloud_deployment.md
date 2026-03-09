# Task P3-02 — Cloud Deployment (Fly.io + Neon)

**Type**: `infrastructure`
**Priority**: P1

**Summary**: Deploy the API and MCP server to Fly.io with Neon as the managed PostgreSQL backend (pgvector built in) and Fly Tigris for S3-compatible file storage. After this task, users connect to the MCP server via `https://rag-api.fly.dev/mcp` — no local infrastructure required.

**Depends on**: P3-01 (MCP-native query — no `ANTHROPIC_API_KEY` needed for MCP)

---

## Context

**The problem**: Running the MCP server locally requires Docker + PostgreSQL. For most users this is too much friction. A cloud deployment turns the MCP server into a simple URL that any MCP client can connect to.

**Chosen stack**:
- **Fly.io** — simple `fly.toml`, `fly deploy`, scales to zero, ~$5/mo for a small app
- **Neon** — serverless PostgreSQL with pgvector built in, generous free tier, connection pooling via PgBouncer
- **Fly Tigris** — S3-compatible object storage co-located with the Fly.io app (lower latency, simpler billing). Drop-in S3 replacement — just change endpoint URL.

---

## Requirements

**Functional**:
- `fly deploy` from the repo deploys both the API (`:8000`) and MCP server (`:8001`) as separate process groups in a single Fly.io app
- Neon database is used as `DATABASE_URL` — pgvector extension is pre-installed on Neon, no manual `CREATE EXTENSION` needed
- File uploads go to Fly Tigris (S3-compatible) with `STORAGE_BACKEND=s3`
- Secrets (`JWT_SECRET`, `ANTHROPIC_API_KEY`, AWS/Tigris credentials) are stored in Fly secrets, not in `fly.toml`
- `fly deploy` is triggered automatically on push to `main` via GitHub Actions

**Non-functional**:
- The app must start within 60 seconds (sentence-transformers model must be pre-downloaded into the Docker image at build time, not downloaded at runtime)
- Neon free tier is sufficient for Phase 3 — no need to size up yet
- The local Docker Compose setup continues to work unchanged for development

---

## Implementation Guidelines

### 1. Pre-download the embedding model at Docker build time

Currently the sentence-transformers model downloads on first use (~420MB). In a cloud container this is unacceptable.

Add to `Dockerfile`:
```dockerfile
# Pre-download the embedding model so startup is fast
ARG EMBED_MODEL=all-mpnet-base-v2
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')"
```

This bakes the model into the Docker image. Image size increases by ~420MB but startup is fast.

### 2. fly.toml

```toml
app = "rag-api"
primary_region = "syd"  # or closest region to you

[build]

[[services]]
  internal_port = 8000
  protocol = "tcp"

  [[services.ports]]
    handlers = ["http"]
    port = 80
    force_https = true

  [[services.ports]]
    handlers = ["tls", "http"]
    port = 443

[processes]
  api = "uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"
  mcp = "uv run rag-mcp --transport http --host 0.0.0.0 --port 8001"

[[services]]
  internal_port = 8001
  protocol = "tcp"
  processes = ["mcp"]

  [[services.ports]]
    handlers = ["tls", "http"]
    port = 8001

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

[vm]
  memory = "1gb"
  cpu_kind = "shared"
  cpus = 1
```

### 3. Fly Tigris setup

Tigris is provisioned as a Fly.io storage extension:
```bash
fly storage create
```
This creates a bucket and sets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, and `BUCKET_NAME` as Fly secrets automatically.

Update `app/services/storage.py` `S3StorageService` to accept an optional `endpoint_url` for Tigris compatibility:
```python
self.client = boto3.client(
    "s3",
    region_name=region,
    endpoint_url=endpoint_url or None,  # Tigris uses custom endpoint
)
```
Add `s3_endpoint_url: str = ""` to `app/config.py`.

### 4. GitHub Actions CI/CD

Add a deploy step to `.github/workflows/ci.yml` (after tests pass):
```yaml
deploy:
  needs: test
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  steps:
    - uses: actions/checkout@v4
    - uses: superfly/flyctl-actions/setup-flyctl@master
    - run: fly deploy --remote-only
      env:
        FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

### 5. Secrets to set via `fly secrets set`

```bash
fly secrets set \
  DATABASE_URL="<neon-connection-string>" \
  JWT_SECRET="<strong-random-secret>" \
  ANTHROPIC_API_KEY="<key>"  \
  STORAGE_BACKEND="s3" \
  S3_BUCKET="<tigris-bucket-name>"
  # AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY set automatically by Tigris
```

### 6. Neon database setup

1. Create a Neon project at [neon.tech](https://neon.tech)
2. Copy the connection string (pooled, port 5432) to `DATABASE_URL`
3. Run migrations against Neon: `DATABASE_URL=<neon-url> make migrate`
4. The `CREATE EXTENSION IF NOT EXISTS vector` migration step works on Neon without any manual steps — pgvector is pre-installed

---

## Files to Create/Modify

**Create**:
- `fly.toml` — Fly.io app config
- `.github/workflows/deploy.yml` — or add deploy job to existing `ci.yml`

**Modify**:
- `Dockerfile` — pre-download embedding model at build time
- `app/config.py` — add `s3_endpoint_url: str = ""`
- `app/services/storage.py` — pass `endpoint_url` to boto3 client
- `README.md` — add cloud deployment section with Fly.io setup steps
- `.env.example` — add `S3_ENDPOINT_URL=`

---

## Acceptance Criteria

- [ ] `fly deploy` succeeds from a clean checkout
- [ ] `https://rag-api.fly.dev/health` returns `{"status": "ok"}`
- [ ] MCP HTTP server responds at `https://rag-api.fly.dev:8001/mcp` (or separate subdomain)
- [ ] Uploads go to Tigris bucket — verify via `fly storage ls`
- [ ] Migrations run successfully against Neon
- [ ] Sentence-transformers model is baked into the image (startup < 30s)
- [ ] Push to `main` triggers automatic deploy via GitHub Actions
- [ ] Local Docker Compose still works unchanged

---

## Validation Steps

```bash
# Initial setup (one-time)
fly auth login
fly apps create rag-api
fly storage create          # creates Tigris bucket + sets secrets
fly secrets set DATABASE_URL="..." JWT_SECRET="..." ANTHROPIC_API_KEY="..."
DATABASE_URL=<neon-url> make migrate

# Deploy
fly deploy

# Smoke test
curl https://rag-api.fly.dev/health
TOKEN=$(JWT_SECRET=<secret> uv run python scripts/generate_token.py myaccount)
curl https://rag-api.fly.dev/documents -H "Authorization: Bearer $TOKEN"

# MCP HTTP test
curl https://rag-api.fly.dev:8001/mcp  # should return MCP capability handshake
```

---

## Risks

- Fly.io free tier has limited memory (256MB). The sentence-transformers model needs ~500MB RAM at inference time. Use a paid shared-1x-1gb machine ($2–3/mo).
- Neon free tier has a 0.5GB storage limit. For Phase 3 this is fine; monitor as documents accumulate.
- Tigris S3 compatibility: not all boto3 operations work identically. Test `put_object`, `delete_object`, `generate_presigned_url` against Tigris specifically.
- The MCP HTTP server on port 8001 — Fly.io routes by hostname, not port, for HTTPS. Consider serving the MCP server on a path (`/mcp`) on the same port as the API instead of a separate port. This simplifies the Fly.io config significantly. Discuss with team before implementing.
