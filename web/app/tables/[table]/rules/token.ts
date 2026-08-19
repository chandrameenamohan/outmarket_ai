import type { Spec } from "../../../api";

/**
 * How a selectable row identifies itself in a form, and the one shape three files agree on.
 *
 * THREE POPULATIONS ARRIVE THROUGH ONE CONTROL, each behind a prefix, and
 * `actions.ts::selection` reads them back apart. A stored rule travels as its id. A
 * machine proposal travels as a HANDLE — it has no row, because `app/rules/suggest.py`
 * cannot reach the store (SPEC F12 — accepting is the first moment anything is
 * persisted), so the server names one row of the batch it is already holding and that
 * name is all the browser is told. F4's authored draft is the one that still travels as
 * its own `{type, kwargs}`: it is composed on demand and memoised nowhere, so there is
 * no batch for it to be an index into.
 *
 * THE HANDLE IS BEAD dq-8zj, AND IT IS NOT AN OPTIMISATION. A proposal used to travel as
 * its spec too, which meant a domain expert who pressed Suggest was handed the compiled
 * expectation's own type name and its kwargs in the value attribute of every
 * checkbox — the framework in the document SPEC F12 Rev 0.4 says has none, arriving by
 * the one carrier `web/app/framework.ts` cannot strip, because stripping it would have
 * left that reader a checkbox that accepts nothing.
 *
 * NOTHING TRUSTS EITHER OF THEM ON THE WAY BACK. A spec that went to the browser and
 * returned edited is re-validated by `store.propose()` — our sanity table AND the
 * framework's constructor (INV-2); a handle that names nothing the server is still
 * holding is refused by `app/rules/suggest.py::resolve` before any write. The round trip
 * is a convenience, never a permission.
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

/** A machine proposal, as the server named it — and never as the rule it stands for. */
export function proposalToken(handle: string): string {
  return `proposal:${handle}`;
}

/** The other half. A stored rule is addressed by the id it already has. */
export function ruleToken(ruleId: string): string {
  return `rule:${ruleId}`;
}
