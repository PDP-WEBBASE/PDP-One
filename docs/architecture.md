# PDP One architecture

PDP One is a modular monolith with five clear planes:

1. The responsive web/PWA presents Persian RTL workflows.
2. Django owns domain rules, permissions, auditing, PostgreSQL, and private files.
3. Celery/Redis runs imports, reports, synchronization, and backups outside web requests.
4. The MCP service exposes a narrow ChatGPT tool surface and calls Django REST APIs only.
5. A Windows Scheduled Task processes only signed, expiring and allowlisted local deployment requests; it has no generic shell endpoint.

## Data boundaries

- GitHub contains source and migrations, never operational data.
- PostgreSQL is authoritative for business records.
- Uploaded files live in a private volume and are downloaded only through authorized API endpoints.
- MCP tools use a dedicated service identity and every write creates an audit event.
- AI-created contracts and reports are drafts until a human reviews them.
- Deployment requests cross a bind-mounted local queue. HMAC verification, exact-commit locking, replay protection and an OS mutex are enforced again on Windows.

## Deployment progression

- Trial: WSL2 + Docker Compose on the user's Windows laptop.
- Controlled trial internet access: a persistent Tailscale Funnel identity to Nginx, with a stable private MCP capability path.
- Company deployment: the same Compose stack inside an isolated Ubuntu VM on the Windows Server host.

