# PDP One — Resource and Environment Registry

This registry preserves both current locators and historical paths. A recorded path or URL does **not** prove current existence/reachability; verify live state before use.

| ID | Resource | Role | Known locator / lineage | Authority / access | Current status |
|---|---|---|---|---|---|
| RES-GH-01 | Main repository | source/change/control plane | `PDP-WEBBASE/PDP-One` | GitHub connector | current |
| RES-GH-02 | `main` | canonical source branch | current SHA from GitHub | GitHub | current; refresh |
| RES-GH-03 | GitHub Actions | CI/tests/immutable image pipeline | repo workflows/runs | GitHub | current; refresh |
| RES-GH-04 | GHCR / immutable images | deployable application images | exact-commit image lineage | GitHub/registry | current; refresh before deploy |
| RES-WIN-01 | Windows host | PDP One trial runtime host | local Windows machine | runtime/agent | current architecture lineage |
| RES-WIN-02 | PDP One working directory | local deployment/config/scripts | `C:\PDP-One` | Windows host | historically/currently referenced; verify before file operation |
| RES-DEP-01 | Deployment Agent | controlled deploy/health/backup operations | local signed file queue | PDP One tools | current, configured |
| RES-DEP-02 | Deployment reports | exact deployment evidence | historically under `C:\ProgramData\PDP-One\deployment-agent\reports\...` | Deployment Agent | live locator pattern; use exact request ID |
| RES-DEP-03 | Signed queue | controlled agent transport | local signed file queue | Deployment Agent | current |
| RES-DKR-01 | Docker/Rancher Desktop | container runtime | Windows/Rancher | runtime evidence | current architecture; live state refresh required |
| RES-WSL-01 | WSL/VHDX | Rancher/Docker backing environment | historical Rancher VHDX under the Windows user profile | Windows/runtime | protected; no unregister/delete |
| RES-DB-01 | PostgreSQL | structured business system of record | container/runtime service | PDP One/PostgreSQL | current; connected at bootstrap |
| RES-REDIS-01 | Redis | runtime queue/cache infrastructure | container service | runtime | architecture lineage; verify when relevant |
| RES-CELERY-01 | Celery worker/beat | background task execution | container services | runtime | architecture lineage; verify when relevant |
| RES-BE-01 | Backend | API/domain runtime | container/service | PDP One | current architecture |
| RES-WEB-01 | Web frontend | browser UI | container/service | PDP One | current architecture |
| RES-NGX-01 | Nginx | proxy/front door | container/service | runtime | current lineage; Nginx-only health is not app version proof |
| RES-MCP-01 | PDP One MCP | ChatGPT operational interface | private connector; secret URL/token intentionally not stored | PDP One connector | current when connected; secrets excluded |
| RES-TAIL-01 | Tailscale/Funnel | remote/public connectivity | Tailscale identity/endpoints | runtime | verify live before recovery |
| RES-PUBLIC-01 | Historical public web URL | older public PDP One route | `https://pdp-one-trial.tail84ea7e.ts.net` | historical restart guide / Tailscale | historical locator only; verify current public route before use |
| RES-CHAT-01 | ChatGPT Automations | scheduled analysis/monitoring tasks | ChatGPT Automation service | Automations | live schedule system of record |
| RES-GHCON-01 | GitHub connector | repository read/write | connected private GitHub app | ChatGPT/GitHub | current connection when available |
| RES-PDPCON-01 | PDP One connector | runtime/agent/domain tools | `PDP One - 04` logical connector | ChatGPT/PDP One | current connection when available |
| RES-FLIB-01 | ChatGPT/File Library | user-provided source packages/evidence | ChatGPT file environment | user/file tools | not a permanent project runtime |
| RES-BKP-00 | Local Deployment Agent backup root | local verified-backup storage lineage | `C:\ProgramData\PDP-One\backups` | Windows/Deployment Agent | historical/current locator pattern; verify before restore |
| RES-BKP-01 | Historical local final backups | rollback/recovery evidence | names in Backup Registry | Windows/backup storage | historical; verify before restore |
| RES-BKP-02 | User D: backup archive | external/local copy destination | `D:\BackUp PDP-0NE-14050429-01` | user Windows storage | historical/current user-chosen path; verify |
| RES-BKP-03 | Historical portable external example | portable copy location | `E:\BACKUP-PDP` | user storage | historical locator only; verify device/path availability |
| RES-SRC-01 | Transfer v10 package | immutable historical source | `PDPOne-Transfer-Package-v10.0-2026-07-31`; SHA in Source Catalog | user-provided transfer asset | verified source package |
| RES-COMP-01 | Company résumé | company knowledge evidence | `attachments/PDP-G-14-company-resume.pdf`; SHA `2a8fe533...` | transfer source | historical source; 66 pages |
| RES-KEY-01 | Keyword policy | AI/context guidance source | `attachments/11_KEYWORD_POLICY_AND_LISTS.md` | transfer source / active context lineage | historical policy, active principles tracked separately |
| RES-MASTER-01 | Master Design Prompt | broad architecture/design intent | `attachments/PDPOne-Master-Design-And-Implementation-Prompt.txt` | transfer source | historical design source, partially superseded |

## Access principles

### GitHub
Read current source and history through GitHub. Writes require an activated session, a branch and conflict-aware change flow.

### Server/runtime
Use controlled PDP One tools for operational reads/writes. Do not substitute arbitrary shell. Dynamic state such as analysis counters, DB counts, deployment queue and connectors must be read live.

### ChatGPT Automations
Read live task state before changing schedules. Desired specs belong in GitHub; actual enabled state belongs to the Automation service.

### Backups
Repository memory stores metadata, verification evidence and locators, not passphrases or secret-bearing backup contents.

## Historical/current marking

A resource may move or be superseded. When this happens:

- retain old locator as Historical;
- add new locator and evidence;
- never silently rewrite old recovery/diagnostic evidence as if it used the new path.
