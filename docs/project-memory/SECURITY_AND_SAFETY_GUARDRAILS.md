# PDP One — Security and Safety Guardrails

These are hard constraints for every operational session unless the user explicitly and knowingly authorizes a separately guarded action that is allowed by the platform.

## Activation

- Project mutation requires `PDPONE START` at the beginning of the operational request.
- Mentioning PDP One is not activation.
- `PDPONE STATUS` is read-only.
- Activation does not bypass the special confirmation required for destructive recovery or credential operations.

## Secrets and access

Never commit or expose:

- passwords
- API keys
- GitHub PATs
- MCP tokens
- private MCP URLs containing secrets
- Authorization headers
- cookies/session secrets
- CSRF secrets
- `.env` contents
- private keys
- backup passphrases
- sensitive connection strings

Use `[REDACTED — secret intentionally not stored]` in historical/sanitized evidence.

MCP token rotation requires an explicit user instruction. Do not rotate a working token as a troubleshooting reflex.

## Runtime and storage safety

Do not perform or recommend as an automatic fix:

- Rancher Factory Reset
- WSL unregister
- VHDX deletion
- Docker volume prune
- PostgreSQL volume deletion
- private-files volume deletion
- destructive Redis/Tailscale state deletion

Preserve business data and history. Historical recovery procedures that were once useful must not be re-run blindly after newer accepted startup/recovery architecture exists.

## Deployment safety

- Application images must not be built locally as the normal deployment path.
- Use immutable exact images produced by CI.
- Development-fast flow: Branch → CI → immutable exact images → exact-commit deploy → health → merge.
- Never equate merge commit with deployed exact commit.
- Once a deployment write returns a Request ID, do not issue a duplicate deployment; poll that exact request.
- Development-fast has no automatic rollback. Do not claim automatic rollback occurred.
- Arbitrary shell through the PDP One deployment path remains disabled.
- Docker volume operations are outside normal deployment maintenance.

Historical transfer v10 documented a heavier standard gate including Preview, final backup and isolated restore verification. Preserve that historical/standard rule; do not incorrectly apply it as the active development-fast rule when current policy says otherwise.

## Procurement / AI safety

- AI analysis is a draft recommendation, not the company's final decision.
- `Recommended` is AI output; `Selected` is a human/company decision.
- Human rejection of an AI recommendation must not delete the underlying Notice or analysis history.
- Do not silently publish/approve recommendations.
- Contract, receivable, payment and financial records produced through AI workflows are drafts unless an explicitly approved workflow makes them final.
- Do not use deterministic keyword scoring as a replacement for semantic analysis; keywords are context/search guidance under the active policy.
- Do not cancel/restart the active long-running procurement analysis simply to solve unrelated UI issues.

## Source integrity

- Historical snapshots remain historical.
- Missing raw chat history must be marked unavailable; never reconstruct omitted statements as fact.
- Live facts must be refreshed from the authoritative system of record.
- Keep source/decision/deployment provenance wherever feasible.

## Multi-chat safety

- Before write, inspect active session records and open PRs.
- Soft-lock the scope of an operational session.
- Do not knowingly perform overlapping deploy/migration/automation changes without conflict resolution.
- Refresh context before deploy and merge; do not deploy from a stale branch after `main` changes.

## Transfer Package v10 bootstrap scan

On 2026-08-17 the 68 non-PDF textual files covered by the transfer checksum inventory were revalidated and no common private-key, GitHub PAT, OpenAI-key, JWT, Bearer token or simple credential-assignment pattern was detected. This is evidence for bootstrap, not a guarantee that every future source is safe; new sources still require review.
