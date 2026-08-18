/**
 * SPEC F12, Rev 0.4 · MAY THIS READER SEE THE FRAMEWORK, and what it takes to make the
 * answer stick. The whole of the question, in one place, and the reason it is here.
 *
 * IT USED TO BE ON THE PAGES, and that is the bug this replaced (bead dq-220). Each
 * screen read the role for itself, appended the wire flag when the reader was the
 * engineer, and got a clean payload back for everyone else. Three screens remembered;
 * `/runs` and `/runs/<recordId>` did not, and served every reader the same document with
 * nine expectation configurations in it, folded into a `<details>` — the disclosure
 * control Rev 0.4 exists to have deleted. An invariant carried by four copies of a
 * convention is one new page away from being broken, and the fifth page had not been
 * written yet.
 *
 * So it moved down to the only door `web/` has. Every screen's data arrives through
 * `./api.ts`'s `call()` or `stream()`, and both ask these functions themselves: a page
 * cannot forget to ask because it is never asked to, and a page written tomorrow
 * inherits the omission by using the same two functions as everything else.
 *
 * WHY IT IS A FILE OF ITS OWN AND NOT PART OF `api.ts`. Two jobs, one 451-line file, and
 * the repo caps a source file at 400 lines — the same seam `app/api/refuse.py` was carved
 * on. `api.ts` is the transport: it knows the address, the verbs and the refusal. This is
 * the redaction: it knows the role and the framework's key names, and it knows nothing
 * about where the product answers. `tests/test_f12_framework_boundary.py` still pins the
 * environment variable naming the product's address to `api.ts` alone — the split leaves
 * that intact, which is what stops a component importing this module and fetching for
 * itself. Neither the address nor the wire flag is spelled out anywhere in this file,
 * including in these comments: that check is a text scan and cannot tell code from prose.
 */

import { chosenRole } from "./role";

export async function frameworkVisible(): Promise<boolean> {
  return (await chosenRole()) === "engineer";
}

/**
 * The keys a Great Expectations payload travels under, wherever they sit in a document.
 *
 * TWO HALVES, BECAUSE ASKING IS NOT ENOUGH. The wire flag `api.ts::configured` appends
 * is asked for on the engineer's behalf only, so the domain expert's answer is smaller
 * on the wire; and whatever does come back for anyone else is stripped of these keys
 * before a component can see it. The second half is the one that makes this a mechanism
 * rather than a politer convention — `/records` sends the framework's own output
 * UNASKED, which is exactly how the run screens came to serve it, and no query parameter
 * would have stopped that.
 *
 * THREE NAMES, AND THE THIRD IS THE ARGUMENT FOR THE CHECK. `configuration` and `raw`
 * were the two anybody would have listed; `spec` — the compiled `{type, kwargs}` that
 * `app/dq/normalise.py::Result.record()` stores beside every reading — was found by
 * reading the finished bytes, not the types, because `Reading` does not even declare it.
 *
 * ponytail: a key-name filter over the parsed payload, not a schema and not a
 * whitelist. Ceiling, and it is a real one: it strips by NAME, so a framework payload
 * arriving under a fourth name travels until somebody notices. What notices is
 * `tests/e2e/test_framework_absence.py`, which reads the finished document for the
 * framework's own vocabulary rather than trusting this list — that is the check, and
 * this is the fix it guards.
 *
 * ONE PAYLOAD IT CANNOT STRIP, AND IT HAS ITS OWN BEAD (dq-8zj). A machine proposal IS a
 * spec — it has no id, because it has no row, so the checkbox that accepts one carries
 * the spec itself as its value (`./tables/[table]/rules/token.ts`). Taking `type` and
 * `kwargs` out of it here would leave the domain expert a checkbox that accepts nothing.
 * That one needs a handle instead of a spec, which is a change to the accept path rather
 * than to this filter.
 */
const FRAMEWORK_KEYS = new Set(["configuration", "raw", "spec"]);

export function withoutFramework(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(withoutFramework);
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([key]) => !FRAMEWORK_KEYS.has(key))
        .map(([key, inner]) => [key, withoutFramework(inner)]),
    );
  }
  return value;
}

/**
 * The run stream with the framework taken out of every event, one line at a time.
 *
 * Line at a time is the whole requirement: a run is progressive (SPEC O-3), so a filter
 * that buffered the body to parse it would turn fifteen seconds of arriving verdicts
 * into fifteen seconds of nothing followed by a finished list — which is the screen
 * F13 exists to not be.
 *
 * ponytail: the same `\n`-buffered read as `web/app/runs/panel.tsx::events`, written
 * twice rather than shared, because the two halves decode opposite ends of the same
 * pipe and lifting them into a module would be a shared abstraction over eleven lines.
 * Ceiling: a line that is not JSON throws here rather than reaching the browser as
 * itself — which for an NDJSON body from our own process is the honest failure.
 */
export function framelessLines(): TransformStream<Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";
  const emit = (line: string, out: TransformStreamDefaultController<Uint8Array>) => {
    if (line.trim()) {
      out.enqueue(encoder.encode(JSON.stringify(withoutFramework(JSON.parse(line))) + "\n"));
    }
  };
  return new TransformStream({
    transform(chunk, out) {
      buffer += decoder.decode(chunk, { stream: true });
      for (let cut = buffer.indexOf("\n"); cut >= 0; cut = buffer.indexOf("\n")) {
        emit(buffer.slice(0, cut), out);
        buffer = buffer.slice(cut + 1);
      }
    },
    flush(out) {
      emit(buffer, out);
    },
  });
}
