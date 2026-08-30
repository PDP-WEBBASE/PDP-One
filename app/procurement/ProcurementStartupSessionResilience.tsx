"use client";

/**
 * Compatibility boundary retained in the V23 composition.
 *
 * Session resilience is now owned by scoped session/data clients. This
 * component intentionally performs no global browser mutation and MUST NOT
 * replace window.fetch. Keeping the boundary mounted avoids a visual/layout
 * change while removing the cross-cutting request interceptor.
 */
export default function ProcurementStartupSessionResilience() {
  return null;
}
