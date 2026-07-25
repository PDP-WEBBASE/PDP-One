# PDP One Connector Acceptance Agent

## Purpose

This change enables a controlled real acceptance test for the procurement connectors through the signed local deployment agent.

## Test scope

- `hezareh_tenders`: up to three public-list pages
- `hezareh_inquiries`: up to three public-list pages
- `parsnamad_inquiries`: up to three public-list pages
- `parsnamad_tenders`: skipped when disabled, preserving the approved operational decision
- `setad_tenders`: up to two public-list pages
- `setad_inquiries`: up to two public-list pages

## Safety controls

- a PostgreSQL dump is created before the test;
- only public list pages are requested;
- detail-page extraction is disabled;
- ChatGPT analysis is disabled;
- CAPTCHA bypass and stored browser cookies are not used;
- Docker volumes, application images, tokens, and Tailscale identity are not modified by the acceptance action;
- reports contain sanitized errors, totals, and limited sample records.

## Connected-app compatibility

The current ChatGPT conversation can retain an older cached tool schema. A narrowly scoped compatibility bridge allows the existing deployment-health tool to invoke the acceptance action only for the exact identifier `connector-acceptance-run-20260725`. Normal deployment health checks are unchanged.

## Installed-root handling

The deployment agent resolves the active installed PDP One project root and passes that absolute path to the connector acceptance runner. The runner does not assume that the application is installed at `C:\PDP-One`, and fresh agent installations also copy the acceptance runner into the protected agent `bin` directory. This prevents Scheduled Task context and installation-location differences from stopping the test before connector execution.

The cached-client compatibility branch passes the same resolved project root explicitly. This call path is covered independently because it is the path used by an already-open ChatGPT conversation whose Connected App tool schema predates the new dedicated connector-test tool.

## Deployment policy

The feature remains on a draft pull request. It may be deployed only after CI, Preview, a fresh final backup, isolated restore verification, and health checks.
