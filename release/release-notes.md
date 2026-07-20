# PDP One v1.0.1-trial

## Portable backup repair

- preserves and displays the redacted root cause when base backup or isolated restore verification fails
- writes `PDP-ONE-PORTABLE-BACKUP-REPORT.json` on both success and safe failure
- automatically writes a second SHA-256-verified `.pdpone` copy to `D:\BackUp PDP-0NE-14050429-01`
- finalizes destination files atomically so incomplete `.partial` files are never treated as valid backups

This fixed trial release includes BACKLOG-001 stable automated deployment, the Health Gate and Approval Gate compatibility fixes, portable encrypted disaster-recovery backups, and one-file Windows restore orchestration.

Important:

- Operational data and secrets are never stored in GitHub.
- Create the portable backup with `CREATE-PDP-ONE-PORTABLE-BACKUP.bat` and store it off the Windows system drive.
- Restore a clean Windows installation with `RESTORE-PDP-ONE.bat` and the `.pdpone` backup file.
- A Windows restart may be required when WSL/Rancher prerequisites are installed; rerun the same restore BAT afterward.
