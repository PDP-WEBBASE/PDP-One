# PDP One — Active Work Discovery

## Canonical discovery method

Every activated session must discover **all open PDP Session Issues** before writing.

Preferred future labels:

- `pdp-session`
- `pdp-active-work`
- `pdp-conflict`
- `pdp-blocked`
- `pdp-memory`

## Bootstrap limitation

At the 2026-08-17 bootstrap, the repository did not contain the dedicated `pdp-*` labels and the connected GitHub tool did not expose label-creation capability.

Therefore the immediately active, tool-compatible fallback is:

1. search all open Issues whose title begins `[PDP SESSION]`;
2. read every matching Issue body/heartbeat;
3. compare soft-lock scope;
4. inspect all open PRs as a second independent concurrency source.

Issue #59 is the first canonical session record under this fallback.

**Do not skip concurrency checks merely because labels are absent.**

If dedicated labels are later created through GitHub UI or another approved capability, apply them to Session Issues and retain `[PDP SESSION]` title discovery as a backwards-compatible fallback.
