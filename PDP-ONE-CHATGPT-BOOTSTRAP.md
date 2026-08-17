# PDP One — ChatGPT Bootstrap

This is the **minimal external bootstrap** for a new ChatGPT conversation. It is intentionally tiny; GitHub remains the canonical memory.

## Canonical bootstrap text

Use the following as the PDP One ChatGPT Project Instruction (or equivalent persistent instruction available to every new PDP One chat):

> When the user starts a new conversation with `PDPONE START`, activate PDP One operational mode for the lifetime of that conversation. Open GitHub repository `PDP-WEBBASE/PDP-One`, read `PDP-ONE-START-HERE.md`, and follow its Context Sync, concurrency, safety and change-governance rules. Do not require `PDPONE START` again in the same conversation unless the user explicitly used `PDPONE END`. GitHub is canonical memory; refresh live Server and ChatGPT Automation state only from their authoritative sources when relevant.

## Scope

The bootstrap only teaches a fresh chat:

- what `PDPONE START` means;
- which repository is canonical;
- which file is the mandatory entry point;
- that activation persists within the same conversation;
- that GitHub, Server and ChatGPT Automations have separate source-of-truth roles.

It must **not** duplicate project history, architecture, decisions or runtime state. Those stay in GitHub and are loaded through `PDP-ONE-START-HERE.md`.

## Installation target

Preferred target: the persistent **ChatGPT Project Instructions** for the PDP One project so every new chat inside that project recognizes `PDPONE START` before it has read GitHub.

Repository status: **DEFINED**.

External ChatGPT Project-Instruction installation status from Session #72: **NOT PROGRAMMATICALLY VERIFIED** because the available connector/tool set in this session exposes GitHub/PDP One resources but no write action for ChatGPT Project Instructions. Do not claim external installation until it is actually verified in the product.

This limitation does not affect the GitHub-side protocol; it only means a fresh chat outside any already-configured PDP One project context may need this one bootstrap instruction installed at the product level.