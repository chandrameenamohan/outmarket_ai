import type { Spec } from "../../../api";

/**
 * How a selectable row identifies itself in a form, and the one shape three files agree on.
 *
 * TWO POPULATIONS ARRIVE THROUGH ONE CONTROL. A stored rule has an id; an unsaved
 * proposal has nothing but itself, because `app/rules/suggest.py` cannot reach the store
 * and a proposal therefore has no row (SPEC F12 — accepting is the first moment anything
 * is persisted). So a proposal travels as its whole `{type, kwargs}` and a rule as its id,
 * each behind a prefix, and `actions.ts::selection` reads them back apart.
 *
 * NOTHING TRUSTS THIS ON THE WAY BACK. A spec that went to the browser as a checkbox value
 * and returned edited is re-validated by `store.propose()` — our sanity table AND the
 * framework's constructor (INV-2) — so the round trip is a convenience, never a
 * permission.
 *
 * WHY ITS OWN FILE. It is called from a Server Component (`page.tsx`, rendering the rows)
 * and from a Client Component (`desk.tsx`, rendering the draft's Save button), and a
 * module carrying `"use client"` cannot be CALLED from the server — only rendered.
 * `actions.ts` is `"use server"`, which has the mirror-image restriction. A plain module
 * is the only place both sides can reach, which is what a shared encoding needs to be.
 */
export function specToken(spec: Spec): string {
  return `spec:${JSON.stringify({ type: spec.type, kwargs: spec.kwargs })}`;
}

/** The other half. A stored rule is addressed by the id it already has. */
export function ruleToken(ruleId: string): string {
  return `rule:${ruleId}`;
}
