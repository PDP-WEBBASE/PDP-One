# PDP One Deployment Agent Bootstrap

## Purpose

Install only the corrected local deployment script before retrying the procurement startup-fetch hotfix.

## Scope

The bootstrap replaces only:

`C:\ProgramData\PDP-One\deployment-agent\bin\Invoke-PDPOneDeployment.ps1`

It does not change:

- PDP One web/backend/MCP application code
- PostgreSQL or migrations
- Docker images, containers, networks, or volumes
- business backups
- `.env` or any secret/token
- Tailscale identity, state, or public URL
- the deployed application commit

## Safety controls

- refuses to run while a signed request is in `queue\processing`
- validates Windows PowerShell syntax before installation
- verifies required retry/reporting markers
- backs up the currently installed script
- stops only the `PDP One Local Deployment Agent` Scheduled Task
- stages the replacement to a temporary file
- verifies SHA-256 before and after installation
- restores the previous script if installation fails
- restarts the Scheduled Task
- writes `PDP-ONE-AGENT-BOOTSTRAP-REPORT.json` on the Desktop

## Required sequence

1. CI and Preview this bootstrap branch.
2. Download the approved bootstrap package.
3. Run `BOOTSTRAP-PDP-ONE-DEPLOYMENT-AGENT.bat` once on Windows.
4. Verify the generated report and live Agent status.
5. Create a fresh Preview/Approval/Backup for procurement hotfix commit `8b15854ac2015bfd10326d97bac2d70e739207b1`.
6. Deploy that exact hotfix commit.

No application Deploy is performed by the bootstrap itself.
