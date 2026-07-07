# Architecture Decision Records

Short records of the decisions that shaped DocMind. Format: context →
decision → consequences. Newest thinking wins; superseded ADRs stay for the
paper trail.

---

## ADR-1: ARQ over Celery for background jobs

**Context.** Document ingestion (extract/chunk/embed) is too slow for a
request handler and must survive API restarts. The backend is fully async
(FastAPI + SQLAlchemy asyncio + asyncpg); Redis is already in the stack for
rate limiting.

**Decision.** Use ARQ: async-native, Redis-backed, a few hundred lines of
worker config instead of Celery's broker/backend/beat topology.

**Consequences.** Ingestion code shares the app's async DB layer and provider
registry directly — no sync/async bridging, one image for api and worker.
We give up Celery's ecosystem (flower, complex routing, rate-limited queues);
acceptable at one queue and one job type. Revisit if job topology grows.

## ADR-2: Fixed 384-dim embeddings across all providers

**Context.** pgvector columns and HNSW indexes are declared with a fixed
dimension. Different embedding APIs default to different sizes (OpenAI 1536+,
fastembed 384), and re-embedding a corpus on provider switch is acceptable —
a column migration plus index rebuild on every switch is not.

**Decision.** Pin `EMBEDDING_DIM = 384` in the schema and require every
provider to emit 384-dim vectors (OpenAI via the `dimensions` request
parameter; fastembed's default model is natively 384).

**Consequences.** Provider switches never touch the schema. 384 dims costs a
little retrieval quality versus 1536 but keeps the HNSW index small and fast
on a laptop. Providers that cannot project to 384 are simply not eligible.

## ADR-3: LLM and embedding providers selected independently

**Context.** Generation and embedding are different concerns with different
vendors: Anthropic has no embeddings API, and a user with an Anthropic key
should not be locked out of good semantic retrieval (or vice versa).

**Decision.** Two independent settings — `EMBEDDING_PROVIDER` and
`LLM_PROVIDER` — each with its own registry function
(`get_embedding_provider`, `get_llm_provider`).

**Consequences.** Any combination works (e.g. local embeddings + Claude
generation, OpenAI embeddings + local answerer). Slightly more configuration
surface, and the health endpoint reports both so misconfiguration is visible
rather than silent.

## ADR-4: Local extractive answerer for a zero-key demo

**Context.** A portfolio project dies at `OPENAI_API_KEY=...`. Reviewers must
get a working end-to-end demo — including chat with citations — from
`docker compose up` alone.

**Decision.** Ship a deterministic local LLM provider that *extracts* answer
sentences from the retrieved chunks (scored by query-term overlap) and emits
them with `[n]` citation markers, streamed like a real model.

**Consequences.** The default demo needs zero keys and produces grounded,
citation-bearing answers; retrieval quality is showcased honestly since the
answerer can only use what retrieval found. Prose is stilted compared to a
real LLM — one env var upgrades it. Evals gate retrieval, not generation, so
they hold for every provider.

## ADR-5: Hybrid retrieval (vector + FTS) fused with RRF, not vector-only

**Context.** Vector search alone misses exact tokens (IDs, error codes,
"$499", "NX-3"); keyword search alone misses paraphrases ("change login
credentials" → password rotation policy). Real document Q&A needs both, and
cosine similarities and `ts_rank` scores live on incompatible scales.

**Decision.** Run both legs in Postgres (HNSW top-20, tsvector top-20) and
fuse with Reciprocal Rank Fusion, `score = Σ 1/(60 + rank)`, keeping top 6.

**Consequences.** Uses only ranks, so no score-normalization tuning; k=60 is
the literature-standard constant. One extra indexed query per message —
negligible. The golden set includes paraphrase-only cases specifically to
catch regressions in the vector leg.

## ADR-6: SSE over WebSockets for chat streaming

**Context.** Chat needs server→client token streaming. Client→server traffic
is a single POST per message; there is no bidirectional chatter.

**Decision.** Stream responses as Server-Sent Events on the message POST
itself (`sources` → `token`* → `done`/`error`).

**Consequences.** Plain HTTP: cookies, proxies, and the Next.js rewrite work
unchanged, and the endpoint is curl-able. No connection lifecycle to manage
or reconnect protocol to design. If bidirectional features arrive (typing
indicators, live collaboration), this decision gets revisited rather than
stretched.

## ADR-7: JWT in an httpOnly cookie, no refresh tokens

**Context.** Tokens in localStorage are readable by any XSS payload. Full
refresh-token rotation (device sessions, revocation lists) is real work that
demonstrates little in a project whose point is RAG.

**Decision.** A single HS256 JWT with 24-hour expiry in an httpOnly,
`SameSite=Lax` cookie. No refresh tokens — a deliberate, documented scope
cut.

**Consequences.** No token is exposed to JavaScript; CSRF exposure is limited
by SameSite plus JSON-only request bodies. Sessions silently expire after
24 h (users just log in again) and individual tokens cannot be revoked before
expiry. Production hardening path: short-lived access + rotating refresh
tokens.

## ADR-8: Local disk storage behind a Storage protocol

**Context.** Uploaded files must persist somewhere. S3-compatible object
storage is the production answer but adds credentials, a bucket, or a MinIO
container to the zero-key demo.

**Decision.** Store files on a local volume (`/data/uploads`) behind a small
`Storage` protocol (save/open/delete) shared by the api and worker via a
compose volume.

**Consequences.** Zero external dependencies for the demo; delete-document
cleanup is a file unlink. Horizontal scaling of the api/worker pair would
require the shared volume or an S3 implementation of the protocol — which is
the point of the protocol: the swap is one class, not a refactor.
