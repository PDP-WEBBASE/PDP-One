# PDP One — Operational Topology

## Change/control plane

```text
User / ChatGPT operational session
        |
        | PDPONE START + Context Sync
        v
GitHub Project Memory + Session Issue + Branch/PR
        |
        | CI / immutable images / exact commit
        v
PDP One Deployment Agent (signed controlled queue)
        |
        v
Windows / Rancher-Docker runtime
```

## Runtime service lineage

```text
Browser / external access
        |
     Tailscale/Funnel (when enabled)
        |
      Nginx / Web
        |
      Backend API
        |
  PostgreSQL / Redis
        |
 Celery worker/beat where configured
```

ChatGPT accesses the application through the governed PDP One connector/MCP surface, not arbitrary remote shell.

## Analysis execution topology

```text
External procurement sources
        |
 modular extraction connectors
        |
 raw/source occurrence evidence
        |
 normalized canonical notices
        |
 active persistent analysis run
        |
 atomic claim + lease
        |
 ChatGPT Hyper Turbo lanes
        |
 validated AI Draft import
        |
 human review / recommendation UI
        |
 human selection → submission → result
```

`newest_first` and adaptive admission prevent fresh opportunities from being trapped behind the historical backlog.

## Automation/control interaction

GitHub stores desired Automation policy/specification.

ChatGPT Automations hold actual scheduled tasks.

PDP One Runtime holds the analysis run and business data.

A scheduled lane therefore depends on all three planes:

1. GitHub policy/context;
2. ChatGPT live task state;
3. PDP One live run/Context/API.

## Backup/recovery topology

Backup payloads remain on approved local/external backup storage. GitHub keeps metadata, history, safe locators and verification evidence, never backup secrets/passphrases.

## Historical caveat

Transfer v10 captures a July snapshot of this topology and cannot transfer a live connector/session/runtime. Future sessions must refresh all dynamic edges and service identities before operational action.
