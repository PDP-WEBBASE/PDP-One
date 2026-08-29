# Persistent GHCR Credential Bootstrap V1

## Objective

PDP One deployments must reuse one locally protected GHCR credential instead of asking the owner for a token during routine development. Owner secret input is required only when the stored credential is missing, cannot be decrypted for the Windows account, is revoked/expired, or no longer has package-read access.

## Runtime contract

1. The credential remains local to the Windows Deployment Agent under its protected `secrets` directory and is stored with Windows DPAPI.
2. `Test-PDPOneGhcrCredential.ps1` is non-interactive and runs before deployment mutation. It verifies that the protected secret exists, can be decrypted, can authenticate to GHCR, and can read an accepted PDP One package when a probe image is available.
3. If the health check fails, deployment fails before production mutation and records `ghcr_credential_refresh_required=true`.
4. `Set-PDPOnePersistentGhcrCredential.ps1` is the only interactive refresh path in this V1. It accepts the secret through `Read-Host -AsSecureString`, validates GHCR and package-read access before replacing the protected secret, keeps a local encrypted backup, and independently re-runs credential health.
5. Routine deployments never prompt for a token. They reuse the DPAPI-protected credential automatically.

## Security boundaries

- No token value is printed, committed, returned through MCP, or written to application source.
- No automatic credential rotation is introduced.
- No Tailscale identity reset/logout is introduced.
- No PostgreSQL/business-data or Docker-volume mutation is introduced.
- No arbitrary shell capability is introduced.

## Relationship to Zero-Downtime Promotion V1

This is a bounded extension of Session #132. Credential failure is moved ahead of runtime activation so an invalid package credential cannot interrupt the zero-downtime promotion sequence after application mutation has begun.
