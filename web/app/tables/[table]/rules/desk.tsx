"use client";

import { createContext, useActionState, useContext, useState } from "react";
import type { Answer, Workbench } from "../../../api";
import { acceptSelected, translate } from "./actions";
import { specToken } from "./token";

/**
 * The two controls on F12 that cannot be a form post, and nothing else.
 *
 * WHY THESE TWO AND NO MORE. Everything else on this screen — the spread, the evidence
 * lines, the catalog rail, every judgment, both edit doors — is server-rendered markup
 * and plain `<form>`s, so the first paint is the real screen and the role decision is
 * taken before any of it exists. That is not tidiness: SPEC F12's Rev 0.4 amendment says
 * the domain expert's document must not CONTAIN the configuration, and a list rendered
 * in a client component is a list whose data shipped to the browser.
 *
 * Two things genuinely need it:
 *
 *   the selection    the bulk label counts what is ticked and the control is disabled at
 *                    zero — a number that changes on every click. A round trip per
 *                    checkbox is not a thing to build.
 *   the translation  F4 answers with a compiled draft or a refusal naming a capability
 *                    boundary, and neither fits in a query string, which is how every
 *                    other refusal on this screen travels.
 *
 * NOTHING HERE COMPOSES A SENTENCE. `copy` is `app/dq/status.py`'s, arriving in the
 * payload. The only string this file builds is the bulk label, and it builds it by
 * substituting a number into a template that same module wrote — see
 * `BULK_ACTION_TEMPLATE` for why that is one writer rather than two.
 */

type Selected = { picked: string[]; toggle: (token: string, on: boolean) => void };

/**
 * The selection, reachable from the rows without threading it through every caller.
 *
 * ponytail: React's own context, four lines, no store and no state library. The
 * alternative — lifting the rows into the client component — would put the whole
 * rendered list in a browser bundle, and the rows are exactly the part that has to stay
 * server markup. Ceiling: one selection per page, which is all there is.
 */
const Context = createContext<Selected>({ picked: [], toggle: () => {} });

export function Selection({
  table,
  cap,
  copy,
  proposing,
  children,
}: {
  table: string;
  cap: number;
  copy: Workbench["copy"];
  proposing: boolean;
  children: React.ReactNode;
}) {
  const [picked, setPicked] = useState<string[]>([]);

  function toggle(token: string, on: boolean) {
    // THE CAP REFUSES THE EXTRA TICK RATHER THAN DROPPING AN EARLIER ONE. Evicting the
    // first selection to make room would accept a rule the reader had stopped looking
    // at, which is precisely what the cap exists to prevent.
    setPicked((before) =>
      on ? (before.length >= cap ? before : [...before, token]) : before.filter((t) => t !== token),
    );
  }

  return (
    <>
      {/* The rows live OUTSIDE this form and reach it by `form="bulk"` on each checkbox,
          because each row also carries its own form — three judgment buttons and a
          reason field — and forms cannot nest. The platform has had this attribute for
          fifteen years; the React answer would have been to lift the rows. */}
      <form id="bulk" action={acceptSelected}>
        <input type="hidden" name="table" value={table} />
        {/* The same field every row's own form carries, for the same reason (B31): this
            control can be refused too — by the validator, on a spec that was edited on
            its way back — and a refusal must not cost the reader the other proposals. */}
        {proposing ? <input type="hidden" name="propose" value="1" /> : null}
      </form>
      <Context.Provider value={{ picked, toggle }}>{children}</Context.Provider>
      <div className="bulk-foot">
        <button
          className="btn primary"
          form="bulk"
          name="status"
          value="accepted"
          disabled={picked.length === 0}
          data-bulk-accept
        >
          {copy.bulk_action.replace("{n}", String(picked.length))}
        </button>
        <span className="count num" data-selected={picked.length} data-cap={cap}>
          {picked.length} / {cap}
        </span>
      </div>
    </>
  );
}

/**
 * One row's checkbox — rendered ONLY where the payload says the row is selectable.
 *
 * SPEC F12: a `needs_review` proposal carries no checkbox ELEMENT at all rather than a
 * disabled one, because a disabled control still says "bulk-acceptable, just not right
 * now" and this population is the opposite of that. So the absence is decided by the
 * caller from `rule.bulk`, which the server computed, and the held row renders
 * `copy.bulk_excluded` in its place — a sentence, not a greyed-out box.
 */
export function Pick({ token, label }: { token: string; label: string }) {
  const { picked, toggle } = useContext(Context);
  const on = picked.includes(token);
  return (
    <input
      type="checkbox"
      form="bulk"
      name="pick"
      value={token}
      checked={on}
      aria-label={label}
      onChange={(event) => toggle(token, event.target.checked)}
    />
  );
}

/**
 * F4 · the one text field, and what comes back from it.
 *
 * The draft is shown for CONFIRMATION and is not saved: `copy.unsaved` says so, and it is
 * true because nothing in `app/rules/authoring.py`'s import graph can persist anything.
 * The Save button under it posts to the same door a bulk accept uses, so the first write
 * for a hand-written rule and for a machine proposal is one function with one validator
 * in front of it.
 *
 * The compile token is `atom compiled` and never the pass class. Great Expectations
 * accepted 10 of 25 nonsense rules while reporting success (LT-2a), so
 * `copy.compiled_caveat` sits beside it saying exactly that.
 */
export function AuthorField({
  table,
  copy,
  judge,
}: {
  table: string;
  copy: Workbench["copy"];
  judge: (form: FormData) => void | Promise<void>;
}) {
  const [answer, act, pending] = useActionState<Answer | { refused: string } | null, FormData>(
    translate,
    null,
  );
  const failed = answer && "refused" in answer ? answer.refused : null;
  const outcome = answer && !("refused" in answer) ? answer : null;

  return (
    <article className="card">
      <div className="rule-row-head">
        <span className="eyebrow">Write a rule in plain English</span>
      </div>
      <form className="nl-input-row" action={act}>
        <input type="hidden" name="table" value={table} />
        <input
          type="text"
          name="request"
          autoComplete="off"
          aria-label="A rule for this table, in your own words"
          placeholder="order total can never be negative"
          data-author-field
        />
        <button className="btn primary" disabled={pending} aria-busy={pending}>
          Translate
        </button>
      </form>

      {failed ? <p className="refused">{failed}</p> : null}

      {outcome?.refusal ? (
        <div className="reject-inner" data-refusal>
          {/* A refusal is an OUTCOME and wears a chip like every other one on this
              screen. Without it the card is prose with a coloured border, which reads as
              the system telling you something rather than as a decision it recorded —
              and the decision it recorded is that nothing was. */}
          <span className="atom refused-atom">{copy.refused_token}</span>
          <p className="attempt">{outcome.request}</p>
          <p className="reason">{outcome.refusal.message}</p>
          {outcome.refusal.detail ? <p className="not-stored">{outcome.refusal.detail}</p> : null}
        </div>
      ) : null}

      {outcome?.draft ? (
        <>
          <div className="spread">
            <div className="pane en-pane">
              <span className="eyebrow">In English · as understood</span>
              <p className="stmt">{outcome.draft.statement}</p>
            </div>
            {outcome.draft.configuration ? (
              <div className="pane ge-pane">
                <span className="eyebrow">The configuration it compiles to</span>
                <pre tabIndex={0}>{JSON.stringify(outcome.draft.configuration, null, 2)}</pre>
              </div>
            ) : null}
          </div>
          <form className="actions" action={judge}>
            <input type="hidden" name="table" value={table} />
            <input type="hidden" name="pick" value={specToken(outcome.draft)} />
            <span className="atom compiled" data-compiled>
              {copy.compiled_token}
            </span>
            <span className="compiled-hint">{copy.compiled_caveat}</span>
            <span className="unsaved-note">{copy.unsaved}</span>
            <button className="btn primary" name="status" value="accepted" data-save-draft>
              Save it
            </button>
          </form>
        </>
      ) : null}
    </article>
  );
}