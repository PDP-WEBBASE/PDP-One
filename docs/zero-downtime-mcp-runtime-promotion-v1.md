# Zero-Downtime MCP & Runtime Promotion V1

Private Control Session: #132

This document describes the public-safe application-side implementation. Canonical governance, acceptance and project memory remain in the Private Control repository.

## Objective

Prevent ordinary Backend/MCP promotions from creating a stop-before-start availability gap on the ChatGPT-facing MCP path.

## Runtime sequence

1. Resolve exact changed components and immutable images.
2. Keep the currently accepted canonical Backend/MCP containers serving.
3. Start temporary candidate Backend/MCP containers only for the affected continuity unit.
4. Require direct candidate readiness before traffic movement.
5. Gracefully reload the persistent Nginx edge with a non-secret temporary upstream override.
6. Observe local/public API and MCP continuity for the configured 30-second stabilization window.
7. Recreate canonical changed services behind the ready candidate route.
8. Require canonical readiness.
9. Gracefully return Nginx routing to canonical service names.
10. Run exact-candidate scoped health and remove temporary candidates.

Nginx and Tailscale are not stopped or force-recreated during the normal application promotion sequence. The existing capability token is not changed.

## Failure behavior

A candidate that does not become ready is never switched into traffic. A continuity failure after the candidate switch fails the deployment and uses the bounded accepted-release recovery path. No credential rotation, Tailscale identity reset, destructive database operation, Docker-volume reset or arbitrary shell capability is introduced.

## Scope

V1 stays on Docker Compose/Windows Deployment Agent and preserves Promotion V3 serialization. It does not introduce Kubernetes or a new external orchestrator.
