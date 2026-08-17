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

/** The URL a judgment on `table` returns to, with an optional complaint attached. */
function here(table: string, complaint?: string): string {
  const base = `/tables/${encodeURIComponent(table)}/rules`;
  return complaint ? `${base}?refused=${encodeURIComponent(complaint)}` : base;
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

/** One judgment on one row — a stored rule or an unsaved proposal, the same either way. */
export async function judge(form: FormData): Promise<void> {
  const table = String(form.get("table"));
  await post(table, [String(form.get("pick"))], String(form.get("status")), form.get("reason"));
}

/**
 * F12's bulk accept. The checkboxes are `name="pick"` on this form, so the selection is
 * whatever the browser sent — and `store.judge_batch` refuses an empty one and anything
 * past the cap before it writes a single revision.
 */
export async function acceptSelected(form: FormData): Promise<void> {
  const table = String(form.get("table"));
  await post(table, form.getAll("pick").map(String), String(form.get("status")), null);
}

async function post(
  table: string,
  picks: string[],
  status: string,
  reason: FormDataEntryValue | null,
): Promise<never> {
  const answer = await write("/rules", {
    table,
    ...selection(picks),
    status,
    reason: reason === null ? null : String(reason),
  });
  if (refused(answer)) {
    redirect(here(table, answer.refused));
  }
  revalidatePath(here(table));
  redirect(here(table));
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
  redirect(`${here(table)}?propose=1`);
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
  const answer = await write<Answer>(
    `/drafts/${encodeURIComponent(table)}${form.get("configuration") ? "?configuration=1" : ""}`,
    { request },
  );
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
  const configuration = form.get("configuration");
  let body: Record<string, unknown>;
  if (typeof configuration === "string" && configuration.trim()) {
    try {
      body = JSON.parse(configuration) as Record<string, unknown>;
    } catch (error) {
      redirect(here(table, `that is not valid JSON, so nothing was saved: ${error}`));
    }
  } else {
    body = { statement: String(form.get("statement") ?? "") };
  }
  const answer = await write(`/rules/${encodeURIComponent(ruleId)}/revision`, body);
  if (refused(answer)) {
    redirect(here(table, answer.refused));
  }
  // A refusal from the authoring path is a 200 carrying `refusal`, not an HTTP error —
  // it is the product working, and it has to reach the person who pressed the button.
  const refusal = (answer as Answer).refusal;
  if (refusal) {
    redirect(here(table, refusal.message));
  }
  revalidatePath(here(table));
  redirect(here(table));
}
