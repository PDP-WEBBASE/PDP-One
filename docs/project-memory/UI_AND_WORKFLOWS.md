# PDP One — UI, UX and Workflow Memory

## Historical Master Design principles

The historical Master Design source required a Persian/RTL, responsive management application with a consistent Design System, usable density, accessibility considerations, fast rendering and management dashboards/KPIs.

These are design-intent principles; the exact current component library/layout must be read from current source code.

## Accepted Procurement UI behavior at Transfer v10 / V25

`33-PDPOne-Procurement-Current-State.md` recorded the following accepted state on 2026-07-31:

- primary areas included management dashboard, tenders, inquiries, direct referrals and subsystem management;
- tabs used explicit Persian labels such as `کل مناقصات`, `کل استعلامات` and direct-referral wording rather than a generic “همه”;
- opportunity cards remained compact/dense and unnecessary generic “next action” prose had been removed;
- importance had color coding;
- filters included urgency, province, source and importance;
- source was displayed as a compact label/link to the original website;
- already-loaded data remained visible while background refresh occurred;
- V25 initial UI waited for session, dashboard summary, first Notice page and first Direct-referral page, with remaining records loading in the background;
- source/extraction-history/automation settings were deferred until subsystem-management UI was opened.

These statements are a **historical accepted V25 snapshot**, not a guarantee that every current UI detail remains unchanged after PR54–58.

## Installed-version proof lesson

V23 showed that a healthy endpoint did not prove the intended frontend bundle was installed. V24/V25 acceptance therefore used Build-ID/browser-behavior evidence in addition to health.

Historical V25 evidence:

- exact runtime commit: `ee5c83aeeced74f7a00ed1aaf39305e3413dfbac`
- Build ID: `procurement-fast-initial-v25-20260725`
- public procurement route historically recorded as `https://pdp-one-trial.tail84ea7e.ts.net/procurement`

The URL is a historical public locator and must be live-verified before current use.

## PR54 — list semantics

- General Tender/Inquiry lists became recent operational views.
- Recommended view remains complete effective AI-recommendation history.
- Latest effective AI draft determines recommendation state.

## PR55 — management toolbar / selected actions

- Multiple floating controls were consolidated into a responsive management toolbar.
- Selected Tender/Inquiry rows gained visible remove and documents/send actions.
- UI actions follow safe Case/business-history semantics rather than deleting source Notices.

## PR56 — management tabs and Timeout

- management tools became a top-level area;
- extraction/analysis management naming was clarified;
- analysis engine/settings tools moved into the management area;
- selected-action resolution stopped scanning the full Tender/Inquiry archive;
- bounded Case/detail reads prevented the archive-page Timeout pattern;
- Direct Opportunity selection/actions were integrated.

## PR57 — result and recommendation workflow

- Submitted records expose `ثبت نتیجه` and later appear under Results.
- submission modal allows zero files;
- Direct Opportunity `پیشنهادی` tab was removed;
- Tender/Inquiry Recommended rows gained human `حذف از پیشنهادی` without deleting history.

## UI change rule

A future UI change must preserve:

- visible business state/history;
- stable loading behavior;
- no full-archive scans merely to render row actions;
- explicit distinction between AI recommendation and human selection;
- accessibility/readability of Persian RTL management workflows;
- version/build verification when deployment affects frontend behavior.
