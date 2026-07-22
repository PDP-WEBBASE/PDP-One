# PDP One v1.0.4-trial

## Windows connectivity self-healing

- verifies the real public HTTPS health endpoint instead of trusting only `Funnel on`
- retries Tailscale Funnel with bounded restart and preserves the existing node identity
- resolves public IPv4 addresses per request without changing Windows DNS
- keeps the application usable through `http://localhost:8080` on the same laptop
- adds automatic logon startup and a ten-minute connectivity watchdog

## Safe diagnostics and emergency operation

- adds `PDP-ONE-EMERGENCY-START.bat`
- adds `PDP-ONE-CREATE-DIAGNOSTICS.bat`
- writes stable safe-to-share TXT and JSON diagnostics to the installation root and Desktop
- redacts MCP path tokens, API tokens, passwords, authorization values and secret URLs

## Real Windows updater failure-path repair

- parses the exact `contracts,receivables` line when Django shell emits extra informational output
- forwards the rollback database switch as a standalone argument for Windows PowerShell 5.1
- supplies non-empty identifiers when manual-update diagnostics are generated
- adds native Windows PowerShell 5.1 regression coverage for these failure paths

## Preservation guarantees

- does not rotate the MCP path token
- does not change Windows DNS
- does not remove or recreate PostgreSQL, private-file, Redis or Tailscale volumes
- does not change the Tailscale node identity
- does not introduce a database migration

## Portable recovery inherited from v1.0.3-trial

- uses Windows PowerShell 5.1-compatible DPAPI support
- writes `PDP-ONE-PORTABLE-BACKUP-REPORT.json` on success or safe failure
- creates SHA-256-verified portable copies in both requested backup destinations
- supports one-file Windows recovery with `RESTORE-PDP-ONE.bat`
