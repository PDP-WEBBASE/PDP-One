# PDP One repository guidance

## Product rules

- The interface is Persian, RTL, mobile responsive, and uses the Solar Hijri calendar at the presentation layer.
- Git stores source code and migrations only. Never commit operational data, uploaded files, credentials, database dumps, or private company documents.
- PostgreSQL is the source of truth for business records. Files are stored outside the public web root and referenced by opaque identifiers.
- ChatGPT integrations must call the REST API through narrowly scoped MCP tools. They must never connect directly to PostgreSQL.
- AI-created records start as drafts. Financial finalization, deletion, permission changes, and contractual approval require explicit human confirmation.
- Every write from ChatGPT must be attributable in the audit log.

## Verification

- Frontend: `npm run lint && npm test`
- Python syntax: `python -m compileall backend services/pdp_mcp`
- Containers: `docker compose config`
- Add or update tests for business rules before considering a change complete.

## Architecture boundaries

- `app/`: responsive web/PWA presentation.
- `backend/`: Django domain logic and REST API.
- `services/pdp_mcp/`: ChatGPT-facing MCP tools only.
- `infra/`: deployment, reverse proxy, and backup configuration.
- `docs/`: architecture and operating guides.

