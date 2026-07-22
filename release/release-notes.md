# PDP One v1.0.4-trial

## Windows startup and connectivity self-healing hotfix

- adds a stable Windows startup watchdog that runs after logon and rechecks PDP One every ten minutes
- starts Rancher Desktop when needed and waits for the Docker engine instead of failing during early Windows startup
- verifies the local application, PostgreSQL, MCP, Tailscale state and the real public health endpoint separately
- no longer treats the text `Funnel on` by itself as proof that the internet route is usable
- retries the Tailscale container and Funnel automatically without rotating the MCP path token
- tests public IPv4 resolution without changing Windows or corporate-network DNS settings
- opens `http://localhost:8080` for the local user, so the local browser does not depend on public `.ts.net` DNS resolution
- adds a one-click emergency startup and tunnel-repair BAT
- adds a one-click safe diagnostic BAT
- writes redacted TXT and JSON diagnostics to the installation root and Desktop on failure
- preserves PostgreSQL data, Docker volumes, Tailscale identity, `.env`, MCP tokens and the existing ChatGPT connector identity

## Operational files

- `PDP-ONE-EMERGENCY-START.bat`
- `PDP-ONE-CREATE-DIAGNOSTICS.bat`
- `PDP-ONE-LAST-STARTUP-REPORT.json`
- `PDP-ONE-LAST-DIAGNOSTICS.txt`
- `PDP-ONE-LAST-DIAGNOSTICS.json`

## Important

This hotfix does not change business data or database models. It only changes Windows startup, connectivity verification, self-repair, task registration and safe diagnostics.
