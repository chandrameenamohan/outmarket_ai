import { read, refused, type RunView } from "../../api";
import { RunPanel } from "../panel";

export const metadata = { title: "Run record" };

/**
 * F13/F14 · one run, at its own address, for ever.
 *
 * A record is immutable (F9), so this page is the one screen in the product that can
 * never go stale: what it renders is what happened, and re-running writes a different
 * record at a different address rather than editing this one. That is what makes the URL
 * worth pasting into a conversation — the receiver sees the same run the sender did.
 *
 * A RECORD THAT DOES NOT EXIST IS NOT A 404 HERE, and the difference from the rule
 * permalink is deliberate. A rule id that was never written is a broken link and says so
 * with the status code. A record id, though, is the thing other screens compose links out
 * of and the thing a run hands back at the end — so the useful answer names the id that
 * was asked for and offers the table's current state, rather than replacing the address
 * with a not-found page that has lost the id it was about.
 */
export default async function Page({ params }: PageProps<"/runs/[recordId]">) {
  const { recordId } = await params;
  const answer = await read<RunView>(`/records/${encodeURIComponent(recordId)}`);

  if (refused(answer) || !answer.record) {
    return (
      <div className="screen-head">
        <h1>Run {recordId}</h1>
        <p className="refused">
          {refused(answer) ? answer.refused : `no run record ${recordId} is readable here`}
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="screen-head">
        <h1>What this run found in {answer.record.table}</h1>
        <p className="who">
          One row per rule the run submitted. This record is what happened and does not
          change; re-running writes a new one and leaves this address where it is.
        </p>
      </div>
      <RunPanel
        key={answer.record.record_id}
        table={answer.record.table}
        recordId={answer.record.record_id}
        finishedAt={answer.record.finished_at}
        readings={answer.record.results}
        atom={answer.atom}
        pendingAtom={answer.pending}
      />
    </>
  );
}
