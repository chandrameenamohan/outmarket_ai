import { notFound } from "next/navigation";
import { read, refused, type RunView } from "../../api";
import { StreamedRail } from "../../rail";
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
 * A RECORD ID THAT NAMES NOTHING IS A 404, THE SAME AS A RULE ID — and it used to not
 * be. `/rules/not-a-uuid` answered 404 and the not-found page; `/runs/not-a-uuid`
 * answered **200** with a heading reading "Run not-a-uuid" and the API's sentence as a
 * banner. The API was right both times; this page simply did not branch. Two addresses
 * carry an id somebody can mistype, and they may not disagree about what a mistyped one
 * means — a 200 for a thing that does not exist is also what a crawler and a link
 * checker each record as fine.
 *
 * ANYTHING ELSE IS STILL A BANNER, and that is the distinction worth keeping: a database
 * that is not answering is a 503, and telling that reader "there is nothing at this
 * address" would send them to fix a link that is perfectly good.
 */
export default async function Page({ params }: PageProps<"/runs/[recordId]">) {
  const { recordId } = await params;
  const answer = await read<RunView>(`/records/${encodeURIComponent(recordId)}`);

  if (refused(answer) && answer.status === 404) {
    notFound();
  }
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
      {/* Streams (bead dq-9do): the record payload answers in well under a second and
          the coverage read takes ~1.6 s — the page no longer waits for its margin. */}
      <StreamedRail />
      <div className="railed">
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
      </div>
    </>
  );
}
