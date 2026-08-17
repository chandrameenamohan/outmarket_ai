/**
 * F11 / F14 · role is a selected VIEW, remembered on the device — never a route.
 *
 * THE RULE THIS FILE EXISTS TO ENFORCE. There is no `/engineer/rules/7` and no
 * `/expert/rules/7`. If both existed, every permalink would fork in two and the
 * engineer who pastes a link into chat would send the receiver their own role —
 * which is exactly what F11 forbids, since a domain expert must never be handed a
 * table list. One URL space; what differs is what renders on it.
 *
 * WHY A COOKIE AND NOT localStorage. The role decides what the SERVER renders — the
 * configuration pane is not hidden with CSS from a component that fetched it, it is
 * never sent (SPEC F12, Rev 0.4). A value only the browser can read would mean
 * rendering the page twice: once wrong, then again after hydration, which is a
 * layout shift on every route and `make check-ui` budgets 0.1 CLS. A cookie arrives
 * with the request, so the first paint is the right one.
 *
 * IT IS NOT A LOGIN, AND THERE IS NOTHING TO LOG INTO. It gates no data, grants no
 * capability, and every URL answers the same to a request that carries no cookie at
 * all. SPEC's non-goals settled that: one env-configured connection means
 * authentication would add realism rather than capability.
 */

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

/**
 * The two roles, each pointing at the door it opens on. This is the whole of the
 * role -> route relationship, and it points one way only: a role chooses a starting
 * point, and no route implies a role.
 */
export const HOME = { engineer: "/tables", expert: "/review" } as const;

export type Role = keyof typeof HOME;

const COOKIE = "dq-role";

/** A year. The choice is a preference about this device, so it outlives the session. */
const REMEMBERED = 60 * 60 * 24 * 365;

/**
 * The role this device chose, or `null` if it has not chosen one.
 *
 * `null` is a real answer and not a missing one — `/` renders the door on it, which
 * is how "a one-click choice on entry" happens without an account.
 */
export async function chosenRole(): Promise<Role | null> {
  const value = (await cookies()).get(COOKIE)?.value;
  return value === "engineer" || value === "expert" ? value : null;
}

/**
 * What the body class says, for a request that has not chosen — and the reason the
 * default is `expert` rather than `engineer`.
 *
 * A cold permalink is the one arrival with no context at all: no cookie, no prior
 * navigation, someone else's link. Defaulting to the engineer view would show the
 * Great Expectations configuration to a reader who has not said they want it, which
 * is the single thing F12's amendment exists to prevent. Defaulting the other way
 * costs an engineer one click on a control that is already on screen — and then
 * remembers it forever.
 */
export async function bodyClass(): Promise<string> {
  return (await chosenRole()) === "engineer" ? "engineer" : "expert";
}

/**
 * Remember a role, and go where the form asked to go.
 *
 * One action for both callers, because they differ only in that: the door on `/`
 * submits `then=home`, so choosing there also walks through the door; the switch in
 * the header submits none, so switching re-renders the URL you are already on. That
 * asymmetry IS the feature — changing role must never change your address.
 */
export async function selectRole(form: FormData): Promise<void> {
  "use server";

  const role = String(form.get("role"));
  if (!(role in HOME)) {
    throw new Error(`${role} is not a role; the two are ${Object.keys(HOME).join(" and ")}`);
  }
  (await cookies()).set(COOKIE, role, { path: "/", maxAge: REMEMBERED, sameSite: "lax" });

  // The role is read in the layout, so every route's cached render is now stale.
  revalidatePath("/", "layout");

  // Only the two doors, never whatever the form said. A redirect target taken from a
  // submitted field is an open redirect, and this one has exactly two legal values.
  if (form.get("then") === "home") {
    redirect(HOME[role as Role]);
  }
}
