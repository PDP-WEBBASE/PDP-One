# PDP One v1.0.0-trial

This fixed trial release includes BACKLOG-001 stable automated deployment, the Health Gate and Approval Gate compatibility fixes, portable encrypted disaster-recovery backups, and one-file Windows restore orchestration.

Important:

- Operational data and secrets are never stored in GitHub.
- Create the portable backup with `CREATE-PDP-ONE-PORTABLE-BACKUP.bat` and store it off the Windows system drive.
- Restore a clean Windows installation with `RESTORE-PDP-ONE.bat` and the `.pdpone` backup file.
- A Windows restart may be required when WSL/Rancher prerequisites are installed; rerun the same restore BAT afterward.
