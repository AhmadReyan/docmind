# DocMind API Contract

**This document is the single source of truth for the HTTP interface between `frontend/` and `backend/`.**
`frontend/src/lib/api-types.ts` (TypeScript) and `backend/app/schemas/*` (Pydantic) transcribe these shapes.
Any change requires editing this document first.

- Base path: `/api` (the Next.js dev/prod server rewrites `/api/*` to the API service at `http://api:8000/api/*`)
- Auth: JWT in an httpOnly cookie named `docmind_token` (`SameSite=Lax`, `Secure` off in local dev), set by register/login, cleared by logout. All endpoints except `/auth/register`, `/auth/login`, and `/health` require it; unauthenticated requests get `401`.
- Errors (every non-2xx): `{ "detail": string, "code": string }`. Codes used: `unauthorized`, `invalid_credentials`, `email_taken`, `not_found`, `validation_error`, `file_too_large`, `unsupported_file_type`, `rate_limited`, `internal_error`.
- Pagination: query `?limit=<int, default 20, max 100>&offset=<int, default 0>` → response `{ "items": [...], "total": <int> }`.
- Timestamps: ISO 8601 UTC strings with timezone (e.g. `2026-07-07T12:00:00Z`).
- IDs: UUID strings.

## Auth

| Method | Path | Request body | Success response |
|---|---|---|---|
| POST | `/api/auth/register` | `{ "email": string, "password": string (min 8) }` | `201 UserOut` + sets cookie |
| POST | `/api/auth/login` | `{ "email": string, "password": string }` | `200 UserOut` + sets cookie |
| POST | `/api/auth/logout` | — | `204` + clears cookie |
| GET | `/api/auth/me` | — | `200 UserOut` |

```
UserOut = { "id": string, "email": string, "created_at": string }
```

Register with an existing email → `409 { code: "email_taken" }`. Bad login → `401 { code: "invalid_credentials" }`.

## Documents

| Method | Path | Request | Success response |
|---|---|---|---|
| POST | `/api/documents` | multipart form, field `file` (pdf/txt/md, ≤ 20 MB) | `202 DocumentOut` (status `pending`; ingestion job enqueued) |
| GET | `/api/documents` | paginated | `200 { items: DocumentOut[], total }` (newest first) |
| GET | `/api/documents/{id}` | — | `200 DocumentOut` |
| GET | `/api/documents/{id}/chunks` | paginated | `200 { items: ChunkOut[], total }` (by `chunk_index` asc) |
| DELETE | `/api/documents/{id}` | — | `204` (cascades chunks, deletes stored file) |

```
DocumentOut = {
  "id": string,
  "title": string,            // original filename without extension
  "filename": string,
  "mime_type": string,        // "application/pdf" | "text/plain" | "text/markdown"
  "size_bytes": number,
  "status": "pending" | "processing" | "ready" | "failed",
  "error_message": string | null,
  "page_count": number | null,
  "chunk_count": number | null,
  "created_at": string
}

ChunkOut = {
  "id": string,
  "chunk_index": number,
  "content": string,
  "page_number": number | null,
  "token_count": number
}
```

Oversized file → `413 { code: "file_too_large" }`. Wrong type → `415 { code: "unsupported_file_type" }`.
Accessing another user's document → `404 { code: "not_found" }` (no existence leak).

## Conversations & Chat

| Method | Path | Request | Success response |
|---|---|---|---|
| POST | `/api/conversations` | `{}` (empty JSON body) | `201 ConversationOut` |
| GET | `/api/conversations` | paginated | `200 { items: ConversationOut[], total }` (by `updated_at` desc) |
| GET | `/api/conversations/{id}` | — | `200 ConversationDetail` |
| DELETE | `/api/conversations/{id}` | — | `204` |
| POST | `/api/conversations/{id}/messages` | `{ "content": string (1..4000) }` | `200` SSE stream (below) |

```
ConversationOut = { "id": string, "title": string, "created_at": string, "updated_at": string }
ConversationDetail = ConversationOut & { "messages": MessageOut[] }   // by created_at asc

MessageOut = {
  "id": string,
  "role": "user" | "assistant",
  "content": string,               // assistant content contains literal [n] citation markers
  "sources": Source[] | null,      // null for user messages
  "created_at": string
}

Source = {
  "index": number,                 // matches the [n] marker in the assistant text, 1-based
  "chunk_id": string,
  "document_id": string,
  "document_title": string,
  "page_number": number | null,
  "snippet": string,               // first ~200 chars of the chunk
  "score": number                  // RRF fusion score
}
```

### SSE stream protocol

`POST /api/conversations/{id}/messages` responds with `Content-Type: text/event-stream` and headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`. Event sequence:

```
event: sources
data: {"sources": Source[]}          # exactly once, before any tokens

event: token
data: {"delta": string}              # zero or more times

event: done
data: {"message_id": string, "conversation_title": string}   # exactly once, last event on success

event: error
data: {"detail": string, "code": string}    # terminal; may replace any of the above after `sources`
```

The user message is persisted before streaming begins; the assistant message (full content + frozen `sources` jsonb) is persisted before `done` is emitted. If the conversation had the default title, the backend sets it from the first user message (truncated to 60 chars) and returns it in `done`.

Rate limit exceeded → normal (non-SSE) `429 { code: "rate_limited" }` JSON response.

## Health

| Method | Path | Response |
|---|---|---|
| GET | `/api/health` | `200 { "status": "ok", "db": boolean, "redis": boolean, "providers": { "llm": string, "embedding": string } }` |

## Internal contract: retrieval function

The eval harness (`backend/evals/run_eval.py`) and the RAG pipeline both call:

```python
# backend/app/rag/retrieval.py
async def retrieve(
    session: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    *,
    embedding_provider: EmbeddingProvider,
    top_k: int = 6,
) -> list[ScoredChunk]: ...

@dataclass
class ScoredChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    page_number: int | None
    score: float          # RRF fusion score
```

## Service topology (docker-compose service names & ports — also a contract)

| Service | Host port | Container port | Notes |
|---|---|---|---|
| `web` | 3000 | 3000 | Next.js; rewrites `/api/*` → `http://api:8000/api/*` |
| `api` | 8000 | 8000 | FastAPI (uvicorn) |
| `worker` | — | — | ARQ, same image as `api` |
| `postgres` | 5432 | 5432 | `pgvector/pgvector:pg16` |
| `redis` | 6379 | 6379 | `redis:7-alpine` |
