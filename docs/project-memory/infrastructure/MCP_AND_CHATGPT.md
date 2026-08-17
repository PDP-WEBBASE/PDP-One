# PDP One — MCP and ChatGPT Integration

## Purpose

The PDP One connector/MCP surface gives ChatGPT controlled access to domain reads, draft writes and deployment-agent operations without exposing arbitrary shell.

## Secret rule

Never store or display:

- private MCP token
- private tokenized MCP URL
- authorization material
- session secrets

The project-memory registry records the logical connector/access method only.

## Token policy evolution

An early historical restart guide described creating a new MCP token/URL during each manual startup and updating the ChatGPT connection.

That model is **superseded**.

Current hard rule:

> Do not rotate a working MCP token unless the user explicitly instructs token rotation.

Startup/recovery should repair services/connectivity without gratuitous credential changes.

## Runtime disconnect behavior

The connector may temporarily disconnect while MCP/application services restart during deployment. If a deployment Request ID has already been accepted, do not send a duplicate deploy; wait for reconnection and read the same request report.

## Capability boundaries

The connector exposes governed domain/deployment actions. Current Deployment Agent state explicitly reports arbitrary shell disabled.

Use read tools before writes where required. Contract/financial artifacts created by AI remain Draft according to project policy.

## Project-memory protocol

A new chat must not mutate PDP One merely because the connector is available.

Mutation additionally requires:

1. user message begins `PDPONE START`;
2. GitHub Project Memory Context Sync;
3. concurrent-work check;
4. Session Issue and scope declaration;
5. applicable domain safety checks.

## Historical transfer limitation

Transfer packages can preserve connector configuration/evidence but cannot carry a live authenticated ChatGPT/MCP session to another chat/machine. New sessions must use the currently connected tool and verify runtime state live.
