"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { refused, write, type Answer, type Spec } from "../../../api";

/**
 * F12's six writes, in the one file that is allowed to do them.
 *
 * WHY A SEPARATE MODULE AND NOT `"use server"` BLOCKS INSIDE THE PAGE. Two of these are
 * needed by a client component (`desk.tsx`) and four by the page, and an action defined
 * inside a Server Component has to be threaded down as a prop to reach the first group.
 * A `"use server"` file is the shape Next already has for that, so the alternative was
 * six props. It also puts every mutation on this screen in one place a reader can check
 * against SPEC F12's "accepting is the first moment anything is persisted".
 *
 * NOTHING HERE DECIDES ANYTHING. Each function reads a form, calls one endpoint and
 * either revalidates or hands the answer back. The cap, the four states, the reason a
 * rejection needs and the validator every spec walks are all `app/rules/store.py`'s —
 * enforced there because a limit applied next to the screen is a limit anybody can post
 * past, and this file has no path to the store to shortcut with.
 *
 * ponytail: refusals come back on the query string, as they do on the other two
 * judgment screens. That costs no client state, no hook and no third rendering mode,
 * and it makes a failed attempt reloadable and quotable like everything else here.
 * Ceiling: a long refusal makes a long URL. The one exception is `translate`, whose
 * whole answer — a compiled draft or a refusal naming a capability boundary — is far
 * too big for a URL and is returned to a `useActionState` instead.
 */

/**
 * The URL a judgment on `table` returns to: an optional complaint, and whether the
 * proposals the person was looking at are still to be there when they land.
 *
 * `showing` IS B31'S FIX AND IT IS ONE QUERY PARAMETER. A refusal used to return to the
 * bare URL, so the CORRECT refusal for a reasonless rejection also took the ten unsaved
 * proposals off the screen with it — a billed model call and half a minute charged to
 * somebody for reading the guard's own sentence, which is exactly the tax that teaches
 * people to route around a guard. Proposals are deliberately UNSAVED (F3: nothing is
 * stored until a person accepts, because a stored proposal implies coverage that does
 * not exist), so there is no store to recover them from and none is added: `?propose=1`
 * is the same URL the screen was already on, and `app/rules/suggest.py`'s five-minute
 * memo is what makes re-rendering it cost no second call.
 */
function here(table: string, complaint?: string, showing = false): string {
  const base = `/tables/${encodeURIComponent(table)}/rules`;
  const query = [
    showing ? "propose=1" : "",
    complaint ? `refused=${encodeURIComponent(complaint)}` : "",
  ].filter(Boolean);
  return query.length > 0 ? `${base}?${query.join("&")}` : base;
}

/**
 * A selection, as the checkboxes and the row buttons encode it.
 *
 * Two populations arrive through one control, so each carries its own prefix: an unsaved
 * proposal travels as its whole `{type, kwargs}` (there is nothing else to identify it
 * by — it has no row), and a stored rule travels as its id. The server re-validates
 * every spec through `propose()` regardless, so a spec edited in the browser on its way
 * back is refused by INV-2's own door rather than by anything here.
 */
function selection(tokens: string[]): { specs: Spec[]; rule_ids: string[] } {
  const specs: Spec[] = [];
  const rule_ids: string[] = [];
  for (const token of tokens) {
    if (token.startsWith("spec:")) {
      specs.push(JSON.parse(token.slice(5)) as Spec);
    } else if (token.startsWith("rule:")) {
      rule_ids.push(token.slice(5));
    }
  }
  return { specs, rule_ids };
}

/**
 * One judgment on one row — a stored rule or an unsaved proposal, the same either way.
 *
 * The form's `propose` field is how this action learns that proposals were on the screen
 * when the button was pressed, and the screen is the only thing that could tell it: an
 * unsaved proposal has no row to look the answer up in, which is F3's whole point.
 */
export async function judge(form: FormData): Promise<void> {
  const table = String(form.get("table"));
  await post(
    table,
    [String(form.get("pick"))],
    String(form.get("status")),
    form.get("reason"),
    Boolean(form.get("propose")),
  );
}

/**
 * F12's bulk accept. The checkboxes are `name="pick"` on this form, so the selection is
 * whatever the browser sent — and `store.judge_batch` refuses an empty one and anything
 * past the cap before it writes a single revision.
 */
export async function acceptSelected(form: FormData): Promise<void> {
  const table = String(form.get("table"));
  await post(
    table,
    form.getAll("pick").map(String),
    String(form.get("status")),
    null,
    Boolean(form.get("propose")),
  );
}

/**
 * `showing` SURVIVES THE SUCCESS PATH TOO, not only the refusal. Accepting one proposal
 * used to take the other seven off the screen — the same loss B31 is about, one press
 * later, and the one a reviewer who reads the note above will hit next. Re-listing them
 * is safe and free: the batch is `app/rules/suggest.py`'s five-minute memo, so there is
 * no second billed call, and `app/rules/desk.py::proposals` drops any proposal the table
 * now holds by COMPILED spec — so the one just accepted is gone from the list because it
 * is in the store, which is the honest reason for it to disappear.
 *
 * ponytail: the draft's Save button still returns to the bare URL. Ceiling: a refused
 * draft on a screen that also had proposals on it still costs them — but that control
 * writes through `translate`, which returns its refusal to a `useActionState` and never
 * navigates at all, so the loss is a redirect it does not make.
 */
async function post(
  table: string,
  picks: string[],
  status: string,
  reason: FormDataEntryValue | null,
  showing = false,
): Promise<never> {
  const answer = await write("/rules", {
    table,
    ...selection(picks),
    status,
    reason: reason === null ? null : String(reason),
  });
  if (refused(answer)) {
    redirect(here(table, answer.refused, showing));
  }
  revalidatePath(here(table, undefined, showing));
  redirect(here(table, undefined, showing));
}

/**
 * Ask the model for proposals — a POST that redirects, never a link.
 *
 * `?propose=1` is what the page reads to decide whether to fetch them, and it is reached
 * this way rather than by an anchor because the fetch behind it costs a real model call
 * (~$0.04, ~6.6 s — LT-2b). A link is a GET, and a GET is what a prefetch, a crawler and
 * a back button all issue on their own. The redirect makes the resulting URL shareable
 * and reloadable anyway, and `app/rules/suggest.py` memoises the batch for five minutes
 * so a reload of it is free.
 */
export async function propose(form: FormData): Promise<void> {
  const table = String(form.get("table"));
  redirect(here(table, undefined, true));
}

/**
 * F4 · one English sentence in; a draft to confirm, or a refusal that wrote nothing.
 *
 * The only action here that RETURNS rather than redirects, and the only one a
 * `useActionState` drives. Both outcomes are a normal answer — see
 * `app/rules/desk.py::draft` for why a refusal is this endpoint working — so the failure
 * shape is a third one: the process not answering at all, which arrives as `refused` and
 * is rendered as itself.
 */
export async function translate(
  _previous: Answer | { refused: string } | null,
  form: FormData,
): Promise<Answer | { refused: string } | null> {
  const table = String(form.get("table"));
  const request = String(form.get("request") ?? "").trim();
  if (!request) {
    return null;
  }
  // No configuration flag on this path, and no hidden field asking for one. A form field
  // is a thing the BROWSER sends, so the reader who may see the framework would have been
  // decided by the client — the door decides instead (`web/app/api.ts`, bead dq-220).
  const answer = await write<Answer>(`/drafts/${encodeURIComponent(table)}`, { request });
  return refused(answer) ? { refused: answer.refused } : answer;
}

/**
 * A new revision, from whichever side of the spread the person was standing on.
 *
 * One action for both doors because it is one outcome (`app/rules/desk.py::revise`): the
 * engineer's configuration is revalidated, the domain expert's sentence is compiled
 * again, and both land in `needs_review`. The engineer's half parses the textarea here
 * so that a typo in the JSON is a sentence about JSON rather than a 422 about a missing
 * `type` — the only judgement this file makes, and it is about syntax rather than rules.
 */
export async function revise(form: FormData): Promise<void> {
  const table = String(form.get("table"));
  const ruleId = String(form.get("ruleId"));
  // The same field `judge` reads, for the same reason: all three of this action's
  // refusals are correct and all three used to land on a screen with the proposals
  // gone, which is B31 one control sideways. An amendment is the likeliest of the four
  // to be refused, because it is the only one where somebody types the configuration.
  const showing = Boolean(form.get("propose"));
  const configuration = form.get("configuration");
  let body: Record<string, unknown>;
  if (typeof configuration === "string" && configuration.trim()) {
    try {
      body = JSON.parse(configuration) as Record<string, unknown>;
    } catch (error) {
      redirect(here(table, `that is not valid JSON, so nothing was saved: ${error}`, showing));
    }
  } else {
    body = { statement: String(form.get("statement") ?? "") };
  }
  const answer = await write(`/rules/${encodeURIComponent(ruleId)}/revision`, body);
  if (refused(answer)) {
    redirect(here(table, answer.refused, showing));
  }
  // A refusal from the authoring path is a 200 carrying `refusal`, not an HTTP error —
  // it is the product working, and it has to reach the person who pressed the button.
  const refusal = (answer as Answer).refusal;
  if (refusal) {
    redirect(here(table, refusal.message, showing));
  }
  revalidatePath(here(table, undefined, showing));
  redirect(here(table, undefined, showing));
}
