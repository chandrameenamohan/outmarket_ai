"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Reading } from "../api";

/**
 * F13 · the list of readings, and the control that fills it.
 *
 * WHY THIS IS THE ONE CLIENT COMPONENT IN THE APPLICATION. A run is progressive (SPEC
 * O-3): the response is a line of JSON per verdict, arriving over about fifteen seconds,
 * and the list has to be correct at every moment in between. That is a reader in the
 * browser, and there is no way to have one from a Server Component. Everything else here
 * — the record, its readings, the never-run token — is server-rendered and arrives as
 * markup, so this component's FIRST paint is the cached record and not a spinner.
 *
 * THE SAME LIST RENDERS BOTH STATES, WHICH IS THE WHOLE MECHANISM. A row is a `Reading`
 * whether it has settled or not, so a rule that has not reported cannot be missing from
 * the list — the run's opening event describes every accepted rule before the first one
 * executes, and each verdict REPLACES a row rather than appending one. A screen built
 * the other way round (append as they land) shows a short list that grows, which reads
 * as a small finished run for the first fourteen seconds of a big unfinished one.
 *
 * NOTHING HERE COMPOSES A VERDICT. `reading.status` is the atom `app/dq/status.py` wrote,
 * sampling clause welded in (INV-5); `reading.magnitude` is INV-4's sentence from the same
 * writer; the pending text is that module's too, and it arrives twice — in the page's own
 * payload, so a row can go pending on the click, and again in the stream's opening event.
 * This component decides WHERE they go and nothing about what they say.
 *
 * ponytail: `useState` and a `for await`, no reducer, no state library, no abort
 * controller. Four values change and one function changes them. Ceiling: leaving the page
 * mid-run abandons the fetch rather than cancelling it, which is the same thing on the
 * wire — the Python generator stops at the next broken write and stores nothing (F9).
 */
export function RunPanel({
  table,
  recordId,
  finishedAt,
  readings,
  atom,
  pendingAtom,
}: {
  table: string;
  recordId: string | null;
  finishedAt: string | null;
  readings: Reading[];
  atom: string | null;
  pendingAtom: string;
}) {
  const router = useRouter();
  const [rows, setRows] = useState<Reading[]>(readings);
  const [reported, setReported] = useState(readings.length);
  const [total, setTotal] = useState(readings.length);
  const [live, setLive] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

  async function run() {
    setLive(true);
    setRefusal(null);
    // THE VERDICTS ON SCREEN STOP BEING TRUE THE MOMENT THIS IS PRESSED, and the stream's
    // opening event is a second or two away — so the rows go pending here rather than
    // there. Waiting for the server would leave the previous run's verdicts on screen,
    // labelled as nothing in particular, while a new run was already under way: the exact
    // state SPEC F13 forbids, and the one that looks most plausible while being wrong.
    setRows((before) => before.map((row) => ({ statement: row.statement, status: pendingAtom })));
    setReported(0);
    const answer = await fetch(`/run?table=${encodeURIComponent(table)}`, { method: "POST" });
    if (!answer.body) {
      setRefusal(`the run could not be started (${answer.status})`);
      setLive(false);
      return;
    }
    for await (const event of events(answer.body)) {
      if (event.event === "started" && event.rules) {
        setRows(event.rules);
        setTotal(event.total ?? event.rules.length);
        setReported(0);
      } else if (event.event === "verdict" && event.result) {
        const settled = event.result;
        const at = event.index ?? 0;
        setRows((before) => before.map((row, index) => (index === at ? settled : row)));
        setReported(event.reported ?? 0);
      } else if (event.event === "completed") {
        setLive(false);
        // The record id is the run's whole afterlife: the address it can be re-read at,
        // and the proof it was written down. A run that finished and was NOT stored says
        // so instead (`detail`), because the alternative is a screen full of verdicts
        // that will not survive a reload without admitting it.
        if (event.record_id) {
          router.push(`/runs/${event.record_id}`);
        } else {
          setRefusal(event.detail ?? null);
        }
      } else if (event.event === "refused") {
        setRefusal(event.message ?? null);
        setLive(false);
      }
    }
  }

  return (
    <article className="card record">
      <div className="rec-head">
        {recordId && !live ? (
          <span className="rec-id" data-record-id={recordId}>
            {recordId}
          </span>
        ) : null}
        <span className="ctx-chip">{table}</span>
        <span className="rec-meta" data-reported={reported} data-total={total} aria-live="polite">
          {reported} of {total} rules reported
        </span>
        {/* The mockup's rec-meta reads "persisted <time>" — the word is the claim (F9:
            this row is a stored record, not a live report), so it travels with the
            timestamp it qualifies. The record-level verdict chip and the pulsing
            RUNNING dot stay out; both were removed deliberately (globals.css §F13). */}
        {finishedAt && !live ? <span className="rec-meta">persisted {finishedAt}</span> : null}
        <span className="spacer" />
        <button className="btn primary" data-run onClick={run} disabled={live} aria-busy={live}>
          {recordId ? "Re-run → new record" : "Run → new record"}
        </button>
      </div>

      {refusal ? <p className="refused">{refusal}</p> : null}

      {atom && rows.length === 0 ? (
        <p className="result-row">
          <span className="atom" data-coverage-atom>
            {atom}
          </span>
        </p>
      ) : null}

      <ul className="results">
        {rows.map((reading, index) => (
          <Row key={index} reading={reading} />
        ))}
      </ul>

      <p className="rec-note">
        A run record is a record of what happened, and nothing on this screen edits one.
        Re-running writes a new record under a new address; this one stays where it is.
      </p>
    </article>
  );
}

/**
 * One rule's reading. Four things can be on it and three of them are often absent.
 *
 * The verdict class is `reading.verdict` and the fallback is `pending` — never a
 * default that happens to be the pass class. A rule that has not reported is styled as
 * itself: neutral, dashed, and carrying no number, because it has not counted anything.
 */
function Row({ reading }: { reading: Reading }) {
  const state = reading.verdict ?? "pending";
  const evidence = reading.evidence ?? [];
  const raw = reading.raw && Object.keys(reading.raw).length ? reading.raw : null;
  return (
    <li className="result-row" data-verdict={state}>
      <div className="rr-top">
        <span className={`atom ${state}`} data-status-atom>
          {reading.status}
        </span>
        <span className="stmt">{reading.statement}</span>
      </div>

      {reading.magnitude ? (
        <p className="viol">
          <span data-magnitude>{reading.magnitude}</span>
          {evidence.length ? (
            <span className="vals" data-evidence>
              {evidence.join("   ")}
            </span>
          ) : null}
        </p>
      ) : null}

      {/* The aggregate and table-level shapes: no count exists, so what is reported is a
          value against the range the statement already names. */}
      {!reading.magnitude && reading.observed !== null && reading.observed !== undefined ? (
        <p className="viol">
          <span data-observed>observed {String(reading.observed)}</span>
        </p>
      ) : null}

      {/* Why a rule produced no verdict. It is a fact about the RULE, so it never appears
          as a count of bad rows — see the `magnitude` note in web/app/api.ts. */}
      {reading.detail ? (
        <p className="viol why" data-detail>
          {reading.detail}
        </p>
      ) : null}

      {raw ? (
        <details className="raw">
          <summary>raw framework output</summary>
          <pre>{JSON.stringify(raw, null, 2)}</pre>
        </details>
      ) : null}
    </li>
  );
}

/** One event of the run stream, as `app/dq/run.py` yields it. */
type RunEvent = {
  event: string;
  rules?: Reading[];
  index?: number;
  total?: number;
  reported?: number;
  result?: Reading;
  record_id?: string | null;
  detail?: string | null;
  message?: string;
};

/**
 * The response body, read as the sequence of JSON documents it is.
 *
 * Newline-framed, so the reader is a buffer and an `indexOf` — that is the entire
 * argument for NDJSON over server-sent events (`app/api/server.py` makes the rest of it).
 * A chunk boundary can land anywhere, including mid-character, which is what
 * `{ stream: true }` on the decoder is for.
 */
async function* events(body: ReadableStream<Uint8Array>): AsyncGenerator<RunEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    for (let cut = buffer.indexOf("\n"); cut >= 0; cut = buffer.indexOf("\n")) {
      const line = buffer.slice(0, cut).trim();
      buffer = buffer.slice(cut + 1);
      if (line) {
        yield JSON.parse(line) as RunEvent;
      }
    }
    if (done) {
      return;
    }
  }
}
