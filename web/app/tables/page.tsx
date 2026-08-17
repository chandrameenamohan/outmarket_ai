import Link from "next/link";
import { read, refused, type Coverage } from "../api";
import { chosenRole } from "../role";

export const metadata = { title: "Tables" };

/**
 * F10 · the engineer's front door: a coverage dashboard, not a database browser.
 *
 * THE ORDER IS THE ARGUMENT. Three buckets, worst evidence first — never run, then ran
 * but unverifiable, then verified — and inside each, the tables nobody has written a
 * rule for come first. None of that is decided here: `app/dq/coverage.py` returns the
 * buckets already ordered and already filled, so this file renders a list in the order
 * it arrived. That is deliberate. A component that sorted or grouped would be a second
 * opinion about which table is least trustworthy, and the mockup's own defect is what
 * that looks like — `design/ux-variant-workbench.html` files `customers` under "never
 * run" while its results screen holds a run for it, because the bucket was typed rather
 * than derived.
 *
 * WHAT THE DOMAIN EXPERT GETS INSTEAD (F11). Not a restyled table, not a hidden column:
 * this page does not even CALL the coverage endpoint unless the view is the engineer's,
 * so there is no table list in the markup, in the payload or on the wire. F11 says a
 * domain expert never encounters one, and a stylesheet is a promise the DOM can break.
 * The URL is the same either way — see web/app/role.ts for why role is never a segment.
 *
 * ponytail: a `<table>`, plain server-rendered, no sort controls and no filter box. SPEC
 * F10 lists both as out of scope and the default order is the entire feature; a column
 * header that reordered the screen would let the reader dismantle the argument it is
 * making. Ceiling: every table in the schema renders, in one document, every load.
 *
 * `prefetch={false}` on every row link, and it is not a micro-optimisation. Next prefetches
 * links in the viewport, so the default turns one page load into two background requests
 * per ROW — each of which renders a rules page or reads a run record server-side — for an
 * engineer who is going to click exactly one of them. It also made `make check-ui` red:
 * the prefetches are cancelled when the reader navigates, and a cancelled request is a
 * failed request in the console-clean check. Two reasons, same one word.
 */
export default async function Page() {
  if ((await chosenRole()) !== "engineer") {
    return <Signpost />;
  }
  const coverage = await read<Coverage>("/tables");
  if (refused(coverage)) {
    return <p className="refused">{coverage.refused}</p>;
  }
  return (
    <>
      <div className="screen-head">
        <h1>Table Explorer</h1>
        <p className="who">
          Where coverage is missing, and which coverage can actually be trusted.
        </p>
      </div>
      <p className="sort-note">{coverage.sort_note}</p>

      {coverage.buckets.map((bucket) => (
        <section className="bucket" key={bucket.id} data-bucket={bucket.id}>
          <div className="bucket-head">
            <h2>{bucket.heading}</h2>
            <span className="why">{bucket.why}</span>
          </div>
          {bucket.tables.length === 0 ? (
            <p className="note">Nothing is in this bucket.</p>
          ) : (
            <div className="card tbl-wrap">
              <table className="explorer">
                <thead>
                  <tr>
                    <th scope="col">Table</th>
                    <th scope="col" className="r">
                      Rows
                    </th>
                    <th scope="col" className="r">
                      Accepted rules
                    </th>
                    <th scope="col">Last run</th>
                    <th scope="col">Run record</th>
                  </tr>
                </thead>
                <tbody>
                  {bucket.tables.map((row) => (
                    <tr key={row.table} data-table={row.table}>
                      <th scope="row" className="tname">
                        {/* Selecting a table opens its rules — SPEC F10's one
                            interaction. Never the run record, even for a table that has
                            one: the engineer's next move on a row is to change what is
                            checked, and the record has its own column and its own URL. */}
                        <Link
                          href={`/tables/${encodeURIComponent(row.table)}/rules`}
                          prefetch={false}
                        >
                          {row.table}
                        </Link>
                      </th>
                      <td className="r num">{row.rows}</td>
                      <td className="r num" data-accepted-rules={row.accepted_rules}>
                        {row.accepted_rules}
                      </td>
                      <td>
                        {/* INV-5: one element, and the sampling clause is inside the
                            string the server composed. Nothing is appended to it here
                            and nothing sits beside it in this cell. */}
                        <span className={`atom ${row.verdict ?? ""}`} data-status-atom>
                          {row.status}
                        </span>
                      </td>
                      <td className="rec">
                        {row.record_id ? (
                          <Link
                            href={`/runs/${encodeURIComponent(row.record_id)}`}
                            prefetch={false}
                          >
                            {row.record_id}
                          </Link>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ))}
    </>
  );
}

/**
 * What this address renders for anyone who is not looking as the engineer.
 *
 * It is a signpost and not a redirect on purpose. A redirect would mean this URL
 * answered differently depending on who opened it, which is the fork F14 forbids — one
 * address, one page, and what differs is what is on it. So the address stays honest and
 * says whose door it is.
 */
function Signpost() {
  return (
    <>
      <div className="screen-head">
        <h1>This is the engineer&rsquo;s door</h1>
        <p className="who">
          Coverage is a question about tables: how many rows, how many rules, what the
          last run proved. You do not need any of it to do your part.
        </p>
      </div>
      <p className="note">
        Your work is the review queue — the rules waiting on your judgment, each stated in
        business language with the numbers behind it. Switch to the engineer view in the
        header if you came here to look at coverage.
      </p>
      <p className="door-link">
        <Link href="/review">Go to the review queue</Link>
      </p>
    </>
  );
}
