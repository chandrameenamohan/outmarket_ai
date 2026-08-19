import { read, refused, type RunView } from "../api";
import { Rail } from "../rail";
import { RunPanel } from "./panel";

export const metadata = { title: "Runs" };

/**
 * F13 · what this table looks like NOW — the last completed run, and the way to make a
 * newer one.
 *
 * TWO ADDRESSES, ON PURPOSE, AND THEY MEAN DIFFERENT THINGS. This one moves: it always
 * shows the most recent record for the table, so it is the address a screen links to when
 * it means "the current state of the data". `/runs/[recordId]` is fixed: it is one run,
 * for ever, and it is the address somebody pastes into a conversation. A product with only
 * the first has no way to quote a result; with only the second, no way to ask a question.
 *
 * THE PAGE LOAD NEVER EXECUTES ANYTHING. It reads the stored record (SPEC F9) — the
 * import graph makes that structural rather than careful, since `app/dq/runs.py` has no
 * path to the executor. A run costs fifteen seconds and real database work; a screen that
 * re-ran on every refresh would answer differently each time for reasons that have nothing
 * to do with the data.
 */
export default async function Page({ searchParams }: PageProps<"/runs">) {
  const { table } = await searchParams;

  if (typeof table !== "string" || !table) {
    // A run is always about one table, so this address is incomplete rather than empty.
    // It says so and stops: no table picker, because F11 is explicit that a domain
    // expert never meets a table list, and this URL is reachable by both readers.
    return (
      <div className="screen-head">
        <h1>Runs</h1>
        <p className="who">
          A run is always about one table, and this address does not name one. Open a run
          from the table it belongs to, or follow a link to a specific record.
        </p>
      </div>
    );
  }

  const answer = await read<RunView>(`/records?table=${encodeURIComponent(table)}`);
  if (refused(answer)) {
    return <p className="refused">{answer.refused}</p>;
  }

  return (
    <>
      <Rail />
      <div className="railed">
      <div className="screen-head">
        <h1>What the last run found in {answer.table}</h1>
        <p className="who">
          One row per rule that was accepted for this table. Each says what it checked, in
          the sentence somebody vouched for, and what it found.
        </p>
      </div>
      <RunPanel
        key={answer.record?.record_id ?? "none"}
        table={answer.table}
        recordId={answer.record?.record_id ?? null}
        finishedAt={answer.record?.finished_at ?? null}
        readings={answer.record?.results ?? []}
        atom={answer.atom}
        pendingAtom={answer.pending}
      />
      </div>
    </>
  );
}
