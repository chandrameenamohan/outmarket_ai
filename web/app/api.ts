/**
 * The only place `web/` talks to the product. Every screen goes through these two
 * functions and composes nothing.
 *
 * WHY THE FRONTEND HAS NO OPINIONS. The English statement, the evidence line, the
 * status atom, the words on the buttons — all of them are written once, server-side,
 * by the modules that own them (`app/rules/catalog.py`, `app/rules/suggest.py`,
 * `app/dq/status.py`). `tests/test_inv5_sampling_disclosure.py` fails the gate on a
 * second copy of any of them anywhere under `web/`, so this is enforced rather
 * than agreed. What arrives here is display text; what leaves is a rendered page.
 *
 * WHY IT RUNS ON THE SERVER. These are called from Server Components, so the browser
 * never talks to the Python process: no CORS, no second origin to configure, and no
 * API base URL shipped to the client. It is also what makes SPEC F12's amendment real
 * — the decision about whether the Great Expectations configuration appears is taken
 * where the markup is written, so the domain expert's document does not contain it at
 * all. A stylesheet hiding a pane that shipped is a different, weaker promise.
 *
 * AND THAT DECISION IS TAKEN AT THIS DOOR, ONCE, FOR EVERY SCREEN. `./framework.ts`
 * holds the question and the redaction — see it for why they stopped being taken four
 * times, and for why they are a file of their own rather than the second half of this
 * one. Both functions here call them; nothing else in `web/` imports either.
 *
 * ponytail: `fetch`, no client, no generated types, no schema validation at the
 * boundary. The producer and the consumer ship together and the gate runs both, so a
 * validator here would be a third copy of a shape two languages already agree on.
 * Ceiling: a payload that changes shape is a TypeScript error at the use site or a
 * blank field, not a caught one. `refused` covers the case that actually happens —
 * the process is not running, or the thing asked for is not there.
 */

import { framelessLines, frameworkVisible, withoutFramework } from "./framework";

/** Where the Python process answers. Server-side only; never sent to the browser. */
const BASE = process.env.DQ_API_URL ?? "http://localhost:8000";

/** The framing the Python side refuses in, so one line reader parses both (app/api/refuse.py). */
const NDJSON = "application/x-ndjson";

/**
 * What a reader is told when the process behind this page cannot be reached at all.
 *
 * IT USED TO BE `${BASE} did not answer: ${error}`, and that is bead dq-abs. `BASE` is
 * a PRIVATE address — `http://api.railway.internal:8000` in the deployment — and the
 * refusal put it, its port and the JavaScript error class on a page any stranger could
 * reach by mistyping a URL. None of it is usable by the person reading; the host, the
 * port and the runtime are each usable by someone probing (SPEC §3.1).
 *
 * So the reader gets the two facts that are theirs — the item did not load, and it is
 * not something they did — and the operator gets the rest through `console.error`,
 * which on a Server Component lands in the service log and never in the markup.
 */
const UNREACHABLE =
  "This could not be loaded just now — the service behind this page did not answer. " +
  "Nothing you did caused it and nothing was changed. Try again in a moment; if it " +
  "keeps happening, tell whoever runs this.";

/** The engineer's half of the wire contract: `?configuration=1`, on whatever path. */
function configured(path: string): string {
  return `${path}${path.includes("?") ? "&" : "?"}configuration=1`;
}

/** The `{type, kwargs}` pair, ours, and the shape the compiler consumes. */
export type Spec = { type: string; kwargs: Record<string, unknown> };

/**
 * One rule, as `app/rules/view.py` composes it.
 *
 * `configuration` IS OPTIONAL, AND THAT IS SPEC F12'S REV 0.4 AMENDMENT IN THE TYPE.
 * It is present for the engineer and absent for everyone else — `frameworkVisible()`
 * above decides which, for every screen at once — and absent means absent: not null,
 * not empty, the key is not in the payload at all, so there is no framework in the document
 * a domain expert receives. A required field here would have made that unrepresentable
 * and pushed the hiding into a component, where a stylesheet is the only thing standing
 * between a reader and the abstraction this product exists to hide.
 */
export type Rule = Judgeable & {
  rule_id: string;
  revision: number;
  table: string;
  reason: string | null;
  reason_label: string;
};

/**
 * F12 · one machine proposal, and it is NOT a `Rule` — it has no id, because it has no
 * row. `app/rules/suggest.py` cannot reach the store or the executor, so this is a line
 * on a screen with buttons under it; pressing one is what persists it (SPEC F12).
 */
export type Proposal = Judgeable & Spec;

/**
 * What F12's list renders, whichever of the two a row happens to be.
 *
 * The type exists because the SCREEN does not distinguish them and should not: what a
 * person judges is a sentence and the numbers behind it, and whether the thing already
 * has a row in the store is our problem rather than theirs.
 *
 * `bulk` and `held` TRAVEL AS BOOLEANS rather than being derived from `status` in a
 * component, which is the same argument `judgments[].primary` makes: a state name typed
 * into a `.tsx` is the store's closed set living in a second language, in the one place
 * where getting it wrong puts a checkbox on a rule nobody has settled.
 */
type Judgeable = {
  column: string | null;
  // The store's raw state, and the same fact in the reader's language. Both travel and
  // they do different jobs: `status` is the styling hook and the `data-row` attribute
  // the browser checks read, `state_label` is the only one of the two that is ever
  // PRINTED — `needs_review` in a monospace chip is the schema arriving on the screen
  // F11 promises needs no schema knowledge (app/dq/status.py::STATE_LABELS).
  status: string;
  state_label: string;
  statement: string;
  evidence: string;
  bulk: boolean;
  held: boolean;
  configuration?: Spec;
  judgments: { status: string; label: string; primary: boolean }[];
};

/**
 * F12's whole screen, as `app/rules/desk.py::workbench` composes it.
 *
 * `copy` is every load-bearing sentence the screen renders, from the one writer
 * (`app/dq/status.py`). It travels as payload rather than being typed here because
 * `tests/test_inv5_sampling_disclosure.py` fails the gate on a second copy of any of
 * them under `web/` — and `bulk_action` is a TEMPLATE with an `{n}` slot for the one
 * label whose number changes on every click of a checkbox.
 */
export type Workbench = {
  table: string;
  rules: Rule[];
  // `type` is the framework's identifier and arrives for the engineer only — the same
  // Rev 0.4 rule the panes follow. The domain expert gets the same fifteen entries as
  // the sentence each one turns into, which is a better answer to their version of
  // "what can this express?" than a function name would be.
  catalog: { type?: string; english: string; in_use: boolean }[];
  cap: number;
  copy: {
    compiled_token: string;
    compiled_caveat: string;
    unsaved: string;
    bulk_note: string;
    bulk_action: string;
    bulk_excluded: string;
    restate: string;
    reconfigure: string;
    amended: string;
    reason_label: string;
    refused_token: string;
  };
};

/**
 * F4 · what one English sentence comes back as: a draft to confirm, or a refusal.
 *
 * Exactly one of the two is non-null and the other is always present as `null`, so a
 * screen renders `answer.refusal ? … : …` and cannot fall through a shape it did not
 * expect. Both are a 200 — see `app/rules/desk.py::draft` for why a refusal is this
 * endpoint working rather than failing.
 */
export type Answer = {
  table: string;
  request: string;
  draft: (Spec & { statement: string; configuration?: Spec }) | null;
  refusal: { reason: string; message: string; detail: string | null } | null;
};

/**
 * One decision waiting on the domain expert, as `app/rules/view.py::awaiting` composes it.
 *
 * It is a `Rule` minus the Great Expectations configuration — which is not omitted for
 * tidiness, it is F12 Rev 0.4: the queue is the domain expert's screen, so the payload
 * behind it never carries the framework at all and there is nothing to hide.
 *
 * `failing` is the status atom of the last run's verdict, with the sampling clause
 * welded inside the same string (INV-5). `null` when the rule is queued because a
 * person asked for it rather than because it failed. It is rendered as ONE text node
 * and never taken apart here.
 */
type Decision = Omit<Rule, "configuration"> & {
  failing: string | null;
  magnitude: string | null;
  budget: string;
};

/** The whole queue: F11's caveat, what it is scoped to, and the decisions. */
export type Queue = { table: string | null; caveat: string; items: Decision[] };

/**
 * F10 · one line of the coverage dashboard, as `app/dq/coverage.py::row` composes it.
 *
 * `status` is the whole verdict slot and is never taken apart here: the sampling clause
 * is welded INSIDE that string by the single writer (INV-5), so splitting it or
 * recomposing it in the component is precisely the bug the invariant exists to prevent.
 * `rows` arrives pre-formatted for the same reason — the thousands separators have to
 * match the ones inside the atom sitting two columns away.
 */
type CoverageRow = {
  table: string;
  rows: string;
  accepted_rules: number;
  status: string;
  verdict: string | null;
  record_id: string | null;
};

/** The dashboard: three buckets in the order they render, and why that order. */
export type Coverage = {
  buckets: { id: string; heading: string; why: string; tables: CoverageRow[] }[];
  sort_note: string;
};

/**
 * One rule's reading of one run, as `app/dq/normalise.py::Result.record()` writes it.
 *
 * EVERY FIELD BUT THE FIRST TWO IS OPTIONAL, and that is the shape of the thing rather
 * than defensive typing. A row arrives here in two states: settled, with a verdict and
 * everything a verdict carries; or still out, in which case the run's opening event has
 * given it a `statement` and the pending atom and nothing else, because there is nothing
 * else true about it yet. One type for both is what lets the list render the same way
 * whether a rule has answered or not — see web/app/runs/panel.tsx.
 *
 * `status` is the rendered atom and is never taken apart: the sampling clause is welded
 * into it server-side (INV-5), so a component that recomposed it from `verdict` would be
 * the second writer the gate fails on.
 *
 * `magnitude` is null for the four aggregate and table-level shapes, which have no
 * violating count to report, and for every errored rule — a rule that could not run
 * counted nothing, and "0 violating rows" beside it is exactly the confusion
 * `catch_exceptions` creates (LT-1a).
 *
 * `raw` IS THE ENGINEER'S, and optional for the same reason `configuration` is: the
 * record on the wire carries it unasked, and the door takes it out for anyone else
 * (`FRAMEWORK_KEYS`). The payload also carries a `spec` this type does not declare —
 * declaring it would be declaring a field no screen may render.
 */
export type Reading = {
  statement: string;
  status: string;
  verdict?: string;
  magnitude?: string | null;
  evidence?: string[];
  observed?: unknown;
  detail?: string | null;
  raw?: Record<string, unknown> | null;
};

/** One completed run, as `app/dq/runs.py::Record.payload()` stores and returns it. */
type RunRecord = {
  record_id: string;
  table: string;
  status: string;
  scanned_rows: number;
  total_rows: number;
  coverage: number;
  results: Reading[];
  finished_at: string | null;
};

/**
 * What both of F13's addresses answer with. `record` is null when the table has never
 * been run, and `atom` carries the never-run token in that case and only then — the
 * same slot a verdict would occupy, from the same writer (`app/dq/status.py`).
 */
export type RunView = {
  table: string;
  record: RunRecord | null;
  atom: string | null;
  pending: string;
};

/**
 * A refusal carries the sentence the server wrote and the code it wrote it with.
 * Both are needed: 404 means the link is wrong and 422 means the system is, and a
 * permalink has to be able to tell a reader which.
 */
type Refused = { refused: string; status: number };

export function refused(answer: unknown): answer is Refused {
  return typeof answer === "object" && answer !== null && "refused" in answer;
}

export async function read<T>(path: string): Promise<T | Refused> {
  return call<T>(path, { method: "GET" });
}

export async function write<T>(path: string, body: unknown): Promise<T | Refused> {
  return call<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * The one call whose ANSWER IS NOT A DOCUMENT: a run, streaming a line per verdict.
 *
 * It exists beside `read`/`write` rather than inside them because it is the one thing
 * they may not do — `call()` awaits `response.json()`, which for this response means
 * waiting for the whole run and throwing away the reason it is streamed at all. So the
 * body is handed back untouched, and web/app/run/route.ts pipes it to the browser.
 *
 * The proxy is why this is here at all. The browser cannot call the Python process
 * directly: `BASE` is server-side configuration and shipping it to a client would add a
 * second origin, its CORS headers and a URL in the bundle. One route handler on our own
 * origin costs none of that, and this function keeps the address of the process in the
 * one file that is allowed to know it.
 *
 * IT IS THE SECOND DOOR, SO IT ASKS THE SAME QUESTION. A verdict event carries the
 * framework's own output, and a run is how the domain expert's screen fills up — so
 * redacting the page load and passing the stream through untouched would hide the
 * configuration until somebody pressed the button. The engineer's body is still handed
 * over byte for byte; everyone else's goes through `framelessLines()`.
 *
 * AND IT REFUSES THE SAME WAY, which it did not until now. `call()` caught an
 * unreachable process and `stream()` did not, so with the Python side down `POST
 * /run?table=orders` left the exception to Next and answered **500 with a zero-byte
 * body** — nothing for `panel.tsx`'s line reader to read and nothing for a person to
 * act on, so the screen said "the run could not be started (500)" and showed a domain
 * expert a status code. Both doors go through `ask()` now, so there is one place where
 * the address is used and one place where it can fail.
 */
export async function stream(path: string): Promise<Response> {
  // Asked BEFORE the run is started, not after: a run is a real fifteen seconds of
  // database work, and the reader it is for is decided while nothing is in flight.
  const framework = await frameworkVisible();
  const answer = await ask(path, { method: "POST" });
  if (!answer) {
    // The NDJSON refusal shape `app/api/refuse.py` writes, because the client reading
    // this is the same line reader either way (web/app/runs/panel.tsx::events).
    return new Response(JSON.stringify({ event: "refused", message: UNREACHABLE }) + "\n", {
      status: 503,
      headers: { "Content-Type": NDJSON },
    });
  }
  if (framework || !answer.body) {
    return answer;
  }
  return new Response(answer.body.pipeThrough(framelessLines()), {
    status: answer.status,
    headers: answer.headers,
  });
}

/**
 * THE ONLY PLACE `BASE` IS USED, and therefore the only place the process can be
 * unreachable. Both doors call it, so neither can be the one that forgot the `try` —
 * which is what `tests/test_malformed_requests.py` pins by counting the occurrences.
 * `null` rather than a throw: the two callers answer a failure in two shapes, a
 * `Refused` and an NDJSON `Response`, and neither of them is an exception.
 *
 * `no-store` on every call: a rule's state changes the moment somebody presses one of
 * the buttons on the page that is reading it, and a cached judgment is a screen telling
 * two people different things about what will execute tonight.
 */
async function ask(path: string, init: RequestInit): Promise<Response | null> {
  try {
    return await fetch(BASE + path, { ...init, cache: "no-store" });
  } catch (error) {
    // The address and the cause go to the service log, where the person who can act on
    // them reads them; the page gets `UNREACHABLE` and nothing else.
    console.error(`api call failed: ${init.method} ${path}`, error);
    return null;
  }
}

async function call<T>(path: string, init: RequestInit): Promise<T | Refused> {
  const framework = await frameworkVisible();
  const response = await ask(framework ? configured(path) : path, init);
  if (!response) {
    return { refused: UNREACHABLE, status: 503 };
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.message ?? `${response.status} from ${path}`;
    return { refused: String(message), status: response.status };
  }
  return (framework ? payload : withoutFramework(payload)) as T;
}
