# DocMind Architecture

DocMind is a document-intelligence app: users upload documents, an async
worker ingests them into a hybrid (vector + full-text) index, and a chat
interface answers questions with streamed, citation-grounded responses.

Five services run under docker-compose (names and ports are pinned in
[docs/api-contract.md](api-contract.md)): the Next.js `web` frontend, the
FastAPI `api`, the ARQ `worker` (same image as `api`), `postgres`
(pgvector/pgvector:pg16), and `redis`.

## System components

```mermaid
flowchart LR
    subgraph client["Browser"]
        UI["Next.js app<br/>(chat, documents, auth)"]
    end

    subgraph web["web :3000"]
        NX["Next.js server<br/>rewrites /api/* → api:8000"]
    end

    subgraph api["api :8000 (FastAPI)"]
        AUTH["Auth<br/>JWT httpOnly cookie"]
        DOCS["Documents API<br/>upload / list / delete"]
        CHAT["Chat API<br/>SSE streaming"]
        RAG["RAG pipeline<br/>retrieve + generate"]
        RL["Rate limiter<br/>Redis sliding window"]
    end

    subgraph worker["worker (ARQ, same image)"]
        ING["ingest_document<br/>extract → chunk → embed"]
    end

    subgraph providers["Pluggable providers (384-dim)"]
        EMB["Embeddings<br/>local fastembed | openai | hash"]
        LLM["LLM<br/>local extractive | openai | anthropic"]
    end

    PG[("Postgres + pgvector<br/>HNSW + GIN tsvector")]
    RD[("Redis<br/>job queue + rate limits")]
    FS[("Local disk<br/>/data/uploads")]

    UI --> NX --> AUTH & DOCS & CHAT
    DOCS -->|store file, enqueue job| FS & RD
    RD -->|dequeue| ING
    ING --> FS
    ING -->|chunks + embeddings| PG
    ING --> EMB
    CHAT --> RL --> RAG
    RAG --> EMB & LLM
    RAG -->|hybrid search| PG
```

### Component notes

- **web** — Next.js serves the UI and proxies `/api/*` to the API container,
  so the browser talks to a single origin and the auth cookie stays
  first-party. No API URL configuration leaks into client code.
- **api** — FastAPI app. Owns auth (JWT in an httpOnly cookie), document
  CRUD, conversations, and the SSE chat endpoint. It never does heavy work
  inline: uploads are written to disk and a job is enqueued.
- **worker** — an ARQ worker running from the *same image* as the API (one
  Dockerfile, two commands), so ingestion code shares the models, config, and
  providers without a second build. It processes `ingest_document` jobs:
  extract text (pypdf / plain text / markdown), chunk, embed, and bulk-insert
  chunks.
- **postgres (pgvector)** — the only datastore. Chunks carry both a 384-dim
  vector (HNSW index, cosine) and a generated `tsvector` column (GIN index),
  which is what makes hybrid retrieval a two-query, one-database problem
  instead of a two-system synchronization problem.
- **redis** — ARQ job queue plus the sliding-window rate limiter for chat and
  uploads.
- **providers** — embedding and LLM providers are selected independently via
  env (`EMBEDDING_PROVIDER`, `LLM_PROVIDER`). All embedding providers emit
  384-dim vectors so switching providers never requires a schema migration.
  The `local` pair (fastembed + extractive answerer) makes the whole stack
  run with zero API keys.

## Ingestion pipeline

Upload returns `202` immediately; everything below the enqueue is
asynchronous, and the document row's `status` field (`pending → processing →
ready | failed`) is the frontend's polling contract.

```mermaid
sequenceDiagram
    autonumber
    participant U as Browser
    participant A as api (FastAPI)
    participant D as Disk (/data/uploads)
    participant R as Redis (ARQ)
    participant W as worker (ARQ)
    participant E as Embedding provider
    participant P as Postgres (pgvector)

    U->>A: POST /api/documents (multipart file)
    A->>A: validate type (pdf/txt/md) and size (≤20 MB)
    A->>D: write file to disk
    A->>P: INSERT document (status=pending)
    A->>R: enqueue ingest_document(document_id)
    A-->>U: 202 DocumentOut (status=pending)

    R->>W: dequeue job
    W->>P: UPDATE status=processing
    W->>D: read file
    W->>W: extract text (pypdf | plain) and chunk
    W->>E: embed(chunk batch) → 384-dim vectors
    W->>P: bulk INSERT chunks (content, embedding, tsvector generated)
    W->>P: UPDATE status=ready, page_count, chunk_count
    Note over W,P: on any failure: status=failed + error_message
    U->>A: GET /api/documents/{id} (poll until ready)
```

## RAG query flow

Chat responses stream over SSE with a fixed event order — `sources` first
(so the UI can render citation targets before any text arrives), then
`token` deltas, then `done`.

```mermaid
sequenceDiagram
    autonumber
    participant U as Browser
    participant A as api (FastAPI)
    participant R as Redis
    participant E as Embedding provider
    participant P as Postgres (pgvector)
    participant L as LLM provider

    U->>A: POST /api/conversations/{id}/messages
    A->>R: sliding-window rate check
    alt limit exceeded
        A-->>U: 429 rate_limited (plain JSON)
    end
    A->>P: persist user message
    A->>E: embed(query)
    par hybrid retrieval
        A->>P: vector top-20 (HNSW, cosine)
    and
        A->>P: FTS top-20 (tsvector GIN, ts_rank)
    end
    A->>A: RRF fusion (k=60), keep top 6 ScoredChunks
    A-->>U: event: sources {Source[]}
    A->>L: generate_stream(system + context + history)
    loop each delta
        A-->>U: event: token {delta}
    end
    A->>P: persist assistant message (content + frozen sources jsonb)
    A-->>U: event: done {message_id, conversation_title}
```

### Retrieval design

Both retrieval legs run against the same `chunks` table, scoped to the
requesting user (`user_id` is denormalized onto chunks so the filter is one
predicate, not a join):

1. **Vector leg** — cosine similarity over the HNSW index against the query
   embedding; catches paraphrases with no lexical overlap.
2. **Lexical leg** — Postgres full-text search over the generated `tsvector`
   column ranked with `ts_rank`; catches exact identifiers, numbers, and
   names that embeddings blur.

Results are fused with **Reciprocal Rank Fusion**: each chunk scores
`Σ 1/(60 + rank_i)` across the lists it appears in, and the top 6 fused
chunks become the LLM context and the `[n]` citation sources. RRF needs no
score normalization between the two legs — only ranks — which is exactly the
property you want when one leg returns cosine distances and the other
`ts_rank` values on incompatible scales. (Rationale: [decisions.md](decisions.md), ADR-5.)

The retrieval function's exact signature is a frozen contract shared with the
eval harness — see "Internal contract" in [api-contract.md](api-contract.md)
and `backend/evals/` for the golden-set gate that CI runs against it.

## Cross-cutting concerns

- **Auth** — JWT (HS256, 24 h expiry) in an httpOnly `SameSite=Lax` cookie.
  No tokens in JavaScript-accessible storage; no refresh-token machinery
  (deliberate scope cut, ADR-7).
- **Rate limiting** — Redis sorted-set sliding window per user: 20 chat
  messages/minute, 10 uploads/hour. Enforced before any model call, returned
  as a plain `429` rather than an SSE error.
- **Tenancy** — every query filters by the authenticated `user_id`; foreign
  documents 404 rather than 403 to avoid existence leaks.
- **Migrations** — Alembic owns the schema, including the HNSW and GIN
  indexes; `alembic upgrade head` runs on API startup and in the eval
  harness, so dev, CI, and demo databases are always built the same way.
