"""MCP server entry point — exposes the RAG pipeline as MCP tools.

Supports two transports selected via --transport flag:
  stdio  (default): account_id resolved from MCP_AUTH_TOKEN env var
  http:             account_id resolved from Authorization: Bearer header
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextvars
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.services import auth, document_service, embedding, generation, ingestion, retrieval
from app.services.auth import AuthError
from app.services.storage import get_storage_service

# ContextVar for account_id — set by HTTP middleware per-request or by get_account_id() for stdio
_account_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mcp_account_id", default=None
)

mcp: FastMCP[None] = FastMCP("rag-api")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def get_account_id() -> str:
    """Resolve the caller's account_id for the current tool invocation.

    HTTP transport: the _account_id contextvar is set by _BearerAuthMiddleware.
    stdio transport: read MCP_AUTH_TOKEN from the environment.
    """
    account_id = _account_id.get()
    if account_id is not None:
        return account_id

    token = os.getenv("MCP_AUTH_TOKEN", "")
    if not token:
        raise AuthError("MCP_AUTH_TOKEN not set")
    return auth.decode_token(token)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def upload_document(filename: str, content_b64: str) -> dict[str, Any]:
    """Upload a document to your RAG knowledge base.

    The document will be chunked and embedded automatically.
    content_b64 must be the base64-encoded file content.
    Supported extensions: .txt, .md, .pdf
    """
    account_id = get_account_id()
    data = base64.b64decode(content_b64)

    def _run() -> tuple[str, int]:
        from app.db import SessionLocal

        with SessionLocal() as db:
            doc_id, chunk_count = ingestion.ingest_from_bytes(filename, data, account_id, db)
        return str(doc_id), chunk_count

    doc_id_str, chunk_count = await asyncio.to_thread(_run)
    return {"document_id": doc_id_str, "status": "ready", "chunk_count": chunk_count}


@mcp.tool()
async def query_documents(question: str, top_k: int = 5) -> dict[str, Any]:
    """Ask a question and get an answer grounded in your uploaded documents.

    Returns an answer with citations showing source document and page.
    """
    account_id = get_account_id()

    def _run() -> tuple[str, list[retrieval.RetrievedChunk]]:
        from app.db import SessionLocal

        query_emb = embedding.embed_query(question)
        with SessionLocal() as db:
            chunks = retrieval.retrieve(query_emb, account_id, db, top_k)
        answer, cited_chunks = generation.generate_answer(question, chunks)
        return answer, cited_chunks

    answer, cited_chunks = await asyncio.to_thread(_run)
    return {
        "answer": answer,
        "citations": [
            {
                "document_id": str(c.document_id),
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "text": c.text[:200],
                "score": c.score,
            }
            for c in cited_chunks
        ],
    }


@mcp.tool()
async def list_documents() -> dict[str, Any]:
    """List all documents in your knowledge base."""
    account_id = get_account_id()

    def _run() -> list[dict[str, Any]]:
        from app.db import SessionLocal

        with SessionLocal() as db:
            docs = document_service.list_documents(account_id, db)
        return [
            {
                "document_id": d.document_id,
                "filename": d.filename,
                "status": d.status,
                "created_at": d.created_at,
                "chunk_count": d.chunk_count,
            }
            for d in docs
        ]

    documents = await asyncio.to_thread(_run)
    return {"documents": documents}


@mcp.tool()
async def delete_document(document_id: str) -> dict[str, Any]:
    """Delete a document and all its chunks from your knowledge base."""
    account_id = get_account_id()

    def _run() -> None:
        from app.db import SessionLocal

        storage = get_storage_service()
        with SessionLocal() as db:
            document_service.delete_document(document_id, account_id, db, storage)

    await asyncio.to_thread(_run)
    return {"deleted": document_id}


# ---------------------------------------------------------------------------
# HTTP auth middleware
# ---------------------------------------------------------------------------


class _BearerAuthMiddleware:
    """ASGI middleware that validates Bearer tokens for the HTTP transport.

    Sets the _account_id contextvar for each authenticated request so that
    tool handlers can call get_account_id() without any additional plumbing.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        auth_header = next(
            (v.decode() for k, v in scope["headers"] if k.lower() == b"authorization"),
            "",
        )
        if not auth_header.startswith("Bearer "):
            await _send_auth_error(send, "missing_token", "Authorization: Bearer token required")
            return

        token = auth_header.removeprefix("Bearer ").strip()
        try:
            account_id = auth.decode_token(token)
        except AuthError as exc:
            await _send_auth_error(send, "invalid_token", str(exc))
            return

        token_ctx = _account_id.set(account_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _account_id.reset(token_ctx)


async def _send_auth_error(send: Any, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="HTTP port (default: 8001)")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        import uvicorn

        starlette_app = mcp.streamable_http_app()
        wrapped_app = _BearerAuthMiddleware(starlette_app)
        uvicorn.run(wrapped_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
