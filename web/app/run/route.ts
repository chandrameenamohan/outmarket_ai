import { stream } from "../api";

/**
 * F13 · the one address in `web/` the BROWSER calls, and the only reason it exists.
 *
 * Everything else here is a Server Component: the page is rendered where the data is,
 * and the browser receives markup. A run cannot work that way — its whole point is that
 * verdicts arrive one at a time while somebody watches (SPEC O-3/O-4), so the reader has
 * to be the browser, and the browser is not allowed to know where the Python process is.
 * This handler is the seam: same origin, no CORS, no API base URL in the bundle, and the
 * response body is passed through byte for byte rather than parsed and re-emitted.
 *
 * IT IS NOT A POLLING ENDPOINT AND CANNOT BECOME ONE. It answers POST only, it starts a
 * run, and it holds one socket open until that run is over. There is no address here — or
 * anywhere — that answers "how is the run getting on"; the only account of a run in
 * flight is the response the caller is already reading. `app/api/server.py` says the same
 * thing one layer down, and `tests/test_run_endpoint.py` fails the gate on a GET that
 * reaches the run route.
 *
 * ponytail: this handler still rewrites nothing. It reads a query parameter, calls
 * `stream()` and hands back whatever body came out of it; `Response` accepts that body
 * as it stands and Next writes it out. The rewriting that DOES happen is one layer down
 * and belongs there — `api.ts::stream` pipes the domain expert's body through
 * `framework.ts::framelessLines`, a `TransformStream` that takes the framework out of
 * every event for the reader F12 Rev 0.4 hides it from (and whose own ceiling, a
 * non-JSON line throwing there rather than reaching the browser, is stated where it
 * lives). Ceiling here: a caller that closes the tab leaves this handler to notice a
 * broken pipe on its own — which is exactly what the Python side is built to expect,
 * and what makes an abandoned run leave no record (SPEC F9).
 */
export async function POST(request: Request): Promise<Response> {
  const table = new URL(request.url).searchParams.get("table");
  if (!table) {
    // The same shape the Python side refuses with, because the client reading this
    // response is the same line reader either way.
    return new Response(JSON.stringify({ event: "refused", message: "?table= is required" }), {
      status: 422,
      headers: { "Content-Type": "application/x-ndjson" },
    });
  }
  const answer = await stream(`/runs/${encodeURIComponent(table)}`);
  return new Response(answer.body, {
    status: answer.status,
    headers: {
      "Content-Type": answer.headers.get("Content-Type") ?? "application/x-ndjson",
      "Cache-Control": "no-store",
    },
  });
}
