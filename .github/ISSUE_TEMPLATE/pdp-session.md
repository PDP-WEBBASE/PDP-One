---
name: PDP One Operational Session
about: Track an activated PDPONE START change session and its live scope/heartbeat.
title: "[PDP SESSION] YYYY-MM-DD — "
labels: ""
assignees: ""
---

## Session identity

- Session ID: `PDP-SESSION-...`
- Activation: `PDPONE START`
- Started at:
- Starting `main` SHA:

## User request

<!-- Preserve the operational intent and important constraints. -->

## Context Sync

- Canonical memory: PASS / INCOMPLETE
- Runtime: VERIFIED / NOT REQUIRED / UNVERIFIED
- Automations: VERIFIED / NOT REQUIRED / UNVERIFIED
- Active PDP sessions checked: yes/no
- Open PRs checked: yes/no
- Concurrency: CLEAR / OVERLAP
- Relevant decisions:

## Soft lock

```yaml
lock_scope:
  modules: []
  files: []
  database: []
  runtime: []
  automations: []
```

## Branch / PR

- Branch:
- PR:
- Current exact head:

## Runtime / deployment impact

- Runtime change expected: yes/no
- Database change expected: yes/no
- Migration expected: yes/no
- Automation change expected: yes/no
- Deployment expected: yes/no

## Current phase

- [ ] START sync
- [ ] PRE-WRITE sync
- [ ] implementation
- [ ] CI / verification
- [ ] PRE-DEPLOY sync, if applicable
- [ ] exact deploy / health, if applicable
- [ ] PRE-MERGE sync
- [ ] memory sync
- [ ] session log finalized

## Heartbeat / event log

<!-- Append decisions, scope changes, commits, CI, failures, root causes, deploy request IDs, health, automation changes, merge and blockers as they occur. -->

## Conflicts / dependencies

None / describe overlap and resolution mode.

## Next action

