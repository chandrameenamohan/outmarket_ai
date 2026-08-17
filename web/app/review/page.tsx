import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { read, refused, write, type Queue } from "../api";

export const metadata = { title: "Review" };

/**
 * F11 · the domain expert's front door. It opens on judgment, and there is no table
 * list on it — not collapsed, not behind a control, not further down. Absent.
 *
 * WHAT IS ON THE SCREEN IS EXACTLY WHAT NEEDS A DECISION: rules somebody flagged as
 * `needs_review`, and accepted rules the last completed run reports as failing. The
 * selection is `app/rules/view.py::queued` and it is checked without a browser; what
 * this file is responsible for is that a person can act on it without learning the
 * schema.
 *
 * THE TABLE NAME IS CONTEXT AND NOT NAVIGATION. It renders as a `<code>` inside the
 * card's own context line and inside the budget sentence — words, in a page with no
 * anchor elements in it at all. That absence is asserted rather than intended:
 * `tests/e2e/test_ui_behaviour.py::test_review_queue_contains_no_table_list_anywhere`
 * counts links and nav landmarks across the whole DOM and fails on any.
 *
 * ponytail: no links, and therefore no navigation, deliberately. Every decision is
 * taken in place with a form that posts and re-renders this same URL, which is both
 * the cheapest thing to build and the thing INV-1 actually needs — five minutes does
 * not survive a round trip to a detail screen and back per rule. Ceiling: a reader who
 * wants the rule's own address has to be on the rules screen or hold the permalink
 * already; F14's page is where a link INTO a rule is meant to come from, not out of.
 *
 * ponytail: `judge` below is a near-copy of the one in `rules/[ruleId]/page.tsx`. Two
 * server actions of six lines each, differing in where they send the reader afterwards
 * and in the query they have to preserve, are cheaper than a shared helper that takes
 * a redirect target — and the shared one would have exactly two callers forever.
 */
export default async function Page({ searchParams }: PageProps<"/review">) {
  const { table, refused: complaint } = await searchParams;

  // `?table=` narrows the same queue; it is never a path segment, so the address a
  // person lands on is the address anybody else would reach (F11, web/app/role.ts).
  const scope = typeof table === "string" ? table : null;
  const queue = await read<Queue>(`/review${scope ? `?table=${encodeURIComponent(scope)}` : ""}`);

  if (refused(queue)) {
    return <p className="refused">{queue.refused}</p>;
  }

  return (
    <>
      <div className="screen-head">
        <h1>Waiting on you</h1>
        <p className="who">
          {queue.items.length} {queue.items.length === 1 ? "decision" : "decisions"}
          {scope ? (
            <>
              {" about "}
              <code>{scope}</code>
            </>
          ) : null}
          . Each one is a rule stated in business language, with the numbers it was
          inferred from. Nothing here runs until a person vouches for it.
        </p>
      </div>

      <p className="caveat">{queue.caveat}</p>

      {typeof complaint === "string" ? <p className="refused">{complaint}</p> : null}

      {queue.items.length === 0 ? (
        <p className="note">
          Nothing is waiting for your judgment{scope ? <> on {scope}</> : null}. That is the
          empty state, not an error — no rule has been flagged and the last run found nothing
          to argue about.
        </p>
      ) : null}

      {/* THE QUEUE IS ORDERED BY TABLE AND THE BUDGET RESTARTS AT EACH ONE, because
          INV-1 is a promise about a TABLE's proposals (app/rules/view.py::awaiting). A
          counter that goes "37 of 37 for orders" and then "1 of 1 for payments" with
          nothing between them reads as a bug rather than as a second queue, so the first
          card of each table carries a marker and the stylesheet draws the seam. It is an
          attribute and a rule, not a heading: a list of table names with counts under
          them is the table list F11 forbids on this screen. */}
      {queue.items.map((item, index) => (
        <article
          className="card decision"
          key={item.rule_id}
          data-table-start={index > 0 && item.table !== queue.items[index - 1].table ? "" : undefined}
        >
          {/* INV-1, made visible to the person it constrains — one sentence, from
              app/dq/status.py::budget, rendered as one text node. There was a
              `<progress>` beside it drawing the same two numbers, fed by two regexes
              that scraped them back out of the sentence the server had just welded them
              into; it was deleted. The words are what a reader is given, and a bar that
              needs a parser to exist is a decoration with a failure mode. */}
          <p className="budget">{item.budget}</p>

          <div className="card-head">
            {/* One text node, from one writer: the verdict and its sampling clause are
                the same string (INV-5) and nothing sits beside it carrying half. */}
            {item.failing ? <span className="atom failing">{item.failing}</span> : null}
            {/* The state in the reader's language, styled by its raw name. F11's
                screen may not print `needs_review` at somebody who has been promised
                they need no schema knowledge. */}
            <span className={`atom ${item.status}`}>{item.state_label}</span>
            <span>
              about <code>{item.table}</code>
              {item.column ? (
                <>
                  {" · "}
                  <code>{item.column}</code>
                </>
              ) : null}
            </span>
          </div>

          <div className="spread">
            <div className="pane en-pane">
              <span className="eyebrow">In English</span>
              <h2 className="stmt">{item.statement}</h2>
              {item.magnitude ? <p className="magnitude">{item.magnitude}</p> : null}
            </div>
          </div>

          <p className="evidence">{item.evidence}</p>
          {item.reason ? <p className="evidence">{item.reason}</p> : null}

          <form className="actions" action={judge}>
            <input type="hidden" name="ruleId" value={item.rule_id} />
            <input type="hidden" name="table" value={scope ?? ""} />
            <label>
              {item.reason_label}
              <input type="text" name="reason" autoComplete="off" />
            </label>
            {item.judgments.map((judgment) => (
              <button
                key={judgment.status}
                className={judgment.primary ? "btn primary" : "btn"}
                name="status"
                value={judgment.status}
              >
                {judgment.label}
              </button>
            ))}
          </form>
        </article>
      ))}
    </>
  );
}

/**
 * One judgment, appended as a revision by the store (F6), then back to this queue.
 *
 * The scope travels through the form so a decision taken on `?table=orders` returns to
 * `?table=orders`. It is a hidden field rather than something read off a header: the
 * action has no request in scope, and a redirect that quietly dropped the scope would
 * put a reader who was working through one table back at the top of everything.
 */
async function judge(form: FormData): Promise<void> {
  "use server";

  const table = String(form.get("table") ?? "");
  const here = `/review${table ? `?table=${encodeURIComponent(table)}` : ""}`;
  const answer = await write(`/rules/${encodeURIComponent(String(form.get("ruleId")))}`, {
    status: form.get("status"),
    reason: form.get("reason"),
  });
  if (refused(answer)) {
    const complaint = `refused=${encodeURIComponent(answer.refused)}`;
    redirect(`${here}${table ? "&" : "?"}${complaint}`);
  }
  revalidatePath("/review");
  redirect(here);
}
