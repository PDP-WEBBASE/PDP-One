# PDP One v1.1.0-trial — Release Candidate

## Release status

- GitHub source baseline: `b271e40feee3cd2f6f7b46f24bede2543a55de4e`
- Accepted deployed application commit: `ee5c83aeeced74f7a00ed1aaf39305e3413dfbac`
- Deployment ID: `procurement-v25-fast-load-ee5c83ae-20260725`
- Build ID: `procurement-fast-initial-v25-20260725`
- Verified final backup: `PDP-One-final-Backup-20260725-003429`
- Browser acceptance and full Windows restart tests: passed

This candidate prepares the first consolidated release containing the Procurement subsystem and its operational stabilization chain. Publishing the Git tag and GitHub Release remains a separate final gate.

## Procurement and opportunities

- adds the PostgreSQL-backed Procurement workspace for tenders, inquiries and direct opportunities
- preserves the approved compact management interface, importance labels, urgency filtering and independent source controls
- supports full lists, proposed items, selected items, search, filtering and source links
- persists automation settings and connector enablement through protected APIs
- provides dashboard summaries, extraction history and infrastructure-management views

## Connector and extraction controls

- includes independent connectors for Hezareh, Pars Namad Data and Setad Iran
- keeps Pars Namad tenders disabled because its public route returned inquiry content
- supports first-run today plus one previous day, incremental normal runs and explicit manual date ranges
- detects repeated pages, unexpected empty pages, type mismatches and incomplete termination
- records page-level progress and errors without stopping healthy connectors
- does not silently report a partial extraction as complete

## Versioned analysis context and guarded analysis engine

- stores versioned roles, prompts, keywords, company profile, qualifications and experience context
- supports private context attachments and audited activation of a new context version
- creates fixed analysis requests and structured ChatGPT analysis drafts
- prevents duplicate analysis using context version and content hashes
- requires human review before publication; no automatic decision is published
- keeps scheduled automatic analysis disabled in this release candidate

## Browser and API reliability

- applies ten-second request guards and one controlled retry only for safe GET requests
- never retries create or update operations automatically
- keeps successful page data visible during background refreshes
- polls only the active extraction run instead of reloading the entire subsystem every five seconds
- safely recovers a stale browser session without changing business data
- verifies the real Session API instead of relying only on the nginx shell health endpoint

## Fast initial load

- initial entry waits only for the user session, dashboard summary, first notice page and first direct-opportunity page
- loads remaining pages in the background without returning the interface to a full-screen loading state
- loads sources, extraction history and automation settings only when subsystem management is opened
- uses a verifiable Web build marker and cache-safe HTML delivery to prevent an old frontend from being accepted as the new release

## Windows startup and public connectivity

- starts PDP One automatically after Windows logon and waits for Rancher/Moby readiness
- includes a bounded startup watchdog and controlled Tailscale Funnel self-healing
- validates local health, the real API route and public HTTPS separately
- preserves the existing Tailscale identity and MCP path token
- includes safe diagnostics and an emergency local start path

## Deployment, backup and disk safety

- requires an exact approved commit, Preview, verified final backup and isolated restore verification
- writes a deployment report from the beginning of an attempt and records redacted stage failures
- retries temporary GitHub commit and source-download failures in a bounded manner
- reuses the already verified deployment backup instead of creating a duplicate backup during deploy
- removes only temporary staging, unused images and build cache after a healthy deployment
- never runs Docker volume prune or removes PostgreSQL, private-files, Redis or Tailscale volumes
- retains protected rollback backups and archives eligible verified backups to the configured D drive with hash verification

## Verified operational state

- PostgreSQL connected
- contracts preserved: 9
- receivables preserved: 3
- arbitrary shell execution remains disabled
- no MCP token rotation
- no Windows DNS change
- no observed data loss

## Final publication gate

Before publishing `v1.1.0-trial`:

1. verify CI for this release-candidate branch;
2. review this version number and release notes;
3. create the final tag from the approved `main` commit or a dedicated release merge commit;
4. publish the GitHub Release without triggering an unapproved Windows deployment.
