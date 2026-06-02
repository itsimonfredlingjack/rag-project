# API Endpoint Catalog & Validation Status

**Project**: Svensk Ragg Backend
**Framework**: FastAPI
**Base URL**: `http://localhost:8900`
**API Version**: v2
**Documentation**: `/docs`, `/redoc`, and `/openapi.json` are private/local by default. In `public-riksdag-demo`, they are disabled unless `CONST_API_DOCS_ENABLED=true` is explicitly set for local review.

---

## Quick Summary

| Category | Endpoints | Validation | Auth | Status |
| --- | --- | --- | --- | --- |
| Health & Readiness | 2 | Pydantic | None | Public |
| Metrics & Stats | 3 | Pydantic/text | None | Local/operator only; 404 in public |
| Agent Query | 3 | Pydantic + rate limits | None | Public |
| Document Read | 4 | Pydantic/query validation | None | Facets public; Chroma/parent reads disabled in public |
| Document Write | 4 | Pydantic + write dependency | `X-API-Key`; disabled in public profile | Admin |
| Operator/Legacy | `/mcp`, `/sse`, `/ws/harvest`, docs | Profile-gated | Local/private only | Gated |

---

## Public Route Surface

For `CONST_PROFILE=public-riksdag-demo`:

| Route | Classification | Public behavior |
| --- | --- | --- |
| `GET /` | `public_read` | Basic service links; omits docs/MCP/harvest links unless explicitly enabled. |
| `GET /api/svensk-ragg/health` | `public_read` | Process/service health. HTTP reachability means the process is alive. |
| `GET /api/svensk-ragg/ready` | `public_read` | Truth source for whether the public runtime can answer. |
| `GET /api/svensk-ragg/metrics` | `local_only` | 404 in public profile; metrics can include operator telemetry and recent question text. |
| `GET /api/svensk-ragg/metrics/prometheus` | `local_only` | 404 in public profile; expose only behind local/private monitoring. |
| `GET /api/svensk-ragg/stats/overview` | `local_only` | 404 in public profile; placeholder dashboard stats are not public functionality. |
| `GET /api/svensk-ragg/collections` | `local_only` | 404 in public profile; Chroma collection listing is private/operator surface. |
| `POST /api/svensk-ragg/agent/query` | `public_query` | Public Riksdagen BM25-only query path. |
| `POST /api/svensk-ragg/agent/query/stream` | `public_query` | Streaming public query path. |
| `POST /api/svensk-ragg/agent/query/stream/resume` | `public_query` | Replays buffered stream events when stream resumption is enabled; otherwise returns a 404-style SSE error. |
| `/api/constitutional/*` | `legacy_alias` | Same read/query handlers as `/api/svensk-ragg/*`; prefer the branded paths for public clients. |
| `GET /api/documents` | `disabled_in_public` | 404 in public profile; Chroma document listing is private-lab surface. |
| `GET /api/documents/facets` | `public_read` | Public profile returns only Riksdagen facets. |
| `GET /api/documents/{document_id}` | `disabled_in_public` | 404 in public profile; full document lookup should use public Riksdagen URLs, not private Chroma. |
| `GET /api/documents/parents/{parent_id}` | `disabled_in_public` | 404 in public profile; parent store may contain private-lab/SFS data. |
| `POST /api/documents` | `admin_write` | Always 403 in public profile. |
| `PUT /api/documents/{document_id}` | `admin_write` | Always 403 in public profile. |
| `PATCH /api/documents/{document_id}` | `admin_write` | Always 403 in public profile. |
| `DELETE /api/documents/{document_id}` | `admin_write` | Always 403 in public profile. |
| `/mcp` | `local_only` | Not mounted in public profile. MCP job launch also rejects public profile if invoked manually. |
| `/sse`, `/sse/message` | `local_only` / `legacy_alias` | Not registered in public profile. Kept only for private/local legacy MCP-SSE compatibility. |
| `/ws/harvest` | `local_only` | Not registered in public profile. Existing implementation is heartbeat-only. |
| `/docs`, `/redoc`, `/openapi.json` | `disabled_in_public` | Disabled in public profile unless `CONST_API_DOCS_ENABLED=true`. |

---

## Readiness Semantics

`GET /api/svensk-ragg/health` is process/service health. Use it to know whether the backend is alive.

`GET /api/svensk-ragg/ready` is answer readiness. For `public-riksdag-demo`, `can_answer=true` requires:

- profile `public-riksdag-demo`,
- corpus scope `riksdagen_open_data_only`,
- valid public `manifest.json`,
- valid public `docs.checkpoint.json`,
- clean public BM25/FTS5 index with matching document and FTS counts,
- configured LLM service reachable and configured model available.

`degraded_but_usable` is expected when public BM25 and the LLM are ready while Chroma is intentionally disabled.

---

## Query Endpoints

### POST `/api/svensk-ragg/agent/query`

Main non-streaming RAG query endpoint.

- Request validation: `question` is 1-2000 chars; `mode` is `auto`, `chat`, `assist`, or `evidence`.
- Rate limit: 30/minute per client.
- Public profile behavior: uses public BM25-only retrieval and validates source provenance.

### POST `/api/svensk-ragg/agent/query/stream`

Server-Sent Events variant of the query endpoint.

- Rate limit: 20/minute per client.
- Public profile behavior: emits metadata, token, and done events derived from the public BM25-only path.

### POST `/api/svensk-ragg/agent/query/stream/resume`

Replay endpoint for stream resumption.

- Rate limit: 30/minute per client.
- Returns a 404-style SSE error when `CONST_STREAM_RESUMPTION_ENABLED=false`.

---

## Document Routes

Read routes are unauthenticated helpers. Write routes are admin-only and use `require_write_access`:

- private/local profile: requires `CONST_API_KEY`, except explicit local development bypass with `CONST_ALLOW_UNAUTHENTICATED_WRITES=true`;
- public profile: writes always return 403, even when an API key is supplied.

---

## Operator Routes

`/mcp`, `/sse`, `/sse/message`, and `/ws/harvest` are local/private operator or legacy routes. They are not part of the public route surface. The public profile does not register them by default.

---

## Validation Coverage Notes

Validated:

- JSON request bodies via Pydantic models.
- Query parameters for type, range, and length where modeled.
- Query rate limits on public query endpoints.
- Document write auth through a centralized dependency.
- Public source provenance on public query responses.

Still environment-dependent:

- Full answer quality and citation faithfulness depend on local BM25 data and the configured local LLM.
- Browser/security headers may be supplied by a reverse proxy or deployment layer, not only by the FastAPI app.
