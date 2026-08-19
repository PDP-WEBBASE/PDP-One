# PDP ONE — APPLICATION REPOSITORY START

> This repository is the PDP One **canonical application source repository**. Its GitHub visibility may operationally alternate between **Public** and **Private** without changing its source-of-truth role. Treat all content here as safe for future Public exposure at all times. Do not store canonical private Project Memory, secrets, private runtime evidence or internal Session coordination here.

## Authorized PDP One conversations

A new ChatGPT Conversation requires `PDPONE START` once before PDP One mutations. After successful activation, the Conversation remains active until `PDPONE END`.

For authorized project work, canonical private control/memory is maintained in the connected private repository:

`PDP-WEBBASE/PDP-One-Control`

The authorized agent must read that private control entry point first, then inspect this repository for current application source, branches, PRs, CI/build state, exact commit identities and current repository visibility.

## Repository role

This repository is authoritative for:
- application source code;
- tests;
- visibility-safe infrastructure/deployment source;
- GitHub Actions CI/build definitions;
- application `main`, PR head and merge commit identities.

This repository is **not** the authoritative home for:
- internal PDP Session details;
- canonical Project Memory/Current State;
- company-private knowledge;
- private incident evidence;
- private backup/control metadata;
- runtime secrets/tokens/private MCP URLs;
- accepted private deployment/runtime evidence.

## Application/control boundary

GitHub Actions in this repository must never receive credentials granting read/write access to `PDP-One-Control`, regardless of whether this application repository is currently Public or Private.

Application PRs, Issues and workflow output must remain safe for future Public exposure even while this repository is Private. Internal governance, concurrency locks, exact acceptance evidence and private operational rationale are recorded in the private control plane.

Canonical `docs/project-memory/**` content must not be added or modified by application PRs.

## Runtime boundary

Repository visibility or topology changes do not themselves move or recreate PostgreSQL/business data, Docker volumes/private files, Windows runtime data, Tailscale identity/state or MCP secrets.

## Exact-version rule

Keep application `main`, PR head, merge commit, immutable image/build identity, deployed exact commit and deployment ID distinct. The private control plane records the accepted cross-system lineage.

## Repository topology and visibility policy

The two-repository migration is **COMPLETED**.

- `PDP-WEBBASE/PDP-One` is the canonical application repository.
- `PDP-WEBBASE/PDP-One-Control` is the **always-Private** canonical control/memory repository.
- `PDP-One` visibility is an operational GitHub setting, not an architectural role. It may be switched between Public and Private without redesigning the two-repository model or changing application source-of-truth responsibilities.
- A visibility switch does not by itself require application-code, database, Docker-volume, Tailscale, MCP-token or GHCR redesign.
- After each visibility switch, perform a short verification of repository visibility, GitHub Actions availability/quota, `main` ruleset/protection state, connector access and GHCR/deployment access before the next material write/deployment/merge.
- Content in this repository must always obey the stricter future-Public safety boundary, even when the repository is currently Private.
- No Git-history rewrite was performed as part of the migration; do not rewrite history without separate explicit authorization.

## Visibility safety

Do not submit secrets, `.env` contents, credentials, private keys, private MCP URLs, private control-memory exports, private company data or sensitive runtime diagnostics in Issues, PRs, commits or workflow output. This rule applies in both Public and Private visibility modes because the application repository may later become Public again.
