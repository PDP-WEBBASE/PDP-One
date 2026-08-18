# PDP ONE — APPLICATION REPOSITORY START

> This repository is the PDP One **application source repository**. It is being prepared for Public visibility. Do not store canonical private Project Memory, secrets, private runtime evidence or internal Session coordination here.

## Authorized PDP One conversations

A new ChatGPT Conversation still requires `PDPONE START` once before PDP One mutations. After successful activation, the Conversation remains active until `PDPONE END`.

For authorized project work, canonical private control/memory is maintained in the connected private repository:

`PDP-WEBBASE/PDP-One-Control`

The authorized agent must read that private control entry point first, then inspect this repository for current application source, branches, PRs, CI/build state and exact commit identities.

## Repository role

This repository is authoritative for:
- application source code;
- tests;
- public-safe infrastructure/deployment source;
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

## Public/private boundary

Public GitHub Actions in this repository must never receive credentials granting read/write access to `PDP-One-Control`.

Application PRs/Issues/workflow output must be public-safe. Internal governance, concurrency locks, exact acceptance evidence and private operational rationale are recorded in the private control plane.

## Runtime boundary

Repository topology does not itself move or recreate PostgreSQL/business data, Docker volumes/private files, Windows runtime data, Tailscale identity/state or MCP secrets.

## Exact-version rule

Keep application `main`, PR head, merge commit, immutable image/build identity, deployed exact commit and deployment ID distinct. The private control plane records the accepted cross-system lineage.

## Current migration rule

Until the private migration Session records PRE-PUBLIC PASS, repository visibility must not be changed merely because this forwarding file exists. No Git-history rewrite is authorized by default.

## Public contributor safety

Do not submit secrets, `.env` contents, credentials, private keys, private MCP URLs, private control-memory exports, private company data or sensitive runtime diagnostics in Issues, PRs, commits or workflow output.
