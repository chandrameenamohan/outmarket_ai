import { Suspense } from "react";
import Link from "next/link";
import { read, refused, type Coverage } from "./api";
import { chosenRole } from "./role";

/**
 * The mockup's persistent left rail (design/ux-variant-workbench.html), built for the
 * one reader it may exist for: the ENGINEER. The mockup rendered it for the domain
 * expert too, de-fanged with `pointer-events: none` — and a stylesheet is a promise the
 * DOM can break. F11 says the expert never ENCOUNTERS a table list, and the shipped
 * reading is stronger than the mockup's: for anyone but the engineer this component
 * returns null and never calls the coverage endpoint, so there is no rail in the
 * markup, the payload or the wire — the same subtraction /tables makes.
 *
 * IT IS NOT IN THE LAYOUT, deliberately, twice over. The layout renders once per
 * document and is preserved across navigations, so anything it decides is decided on
 * whatever route the reader landed on (see layout.tsx). And /review may not carry
 * navigation at all — `test_review_queue_contains_no_table_list_anywhere` counts
 * `a[href]` and `nav` over that page's WHOLE DOM, in any role. So each screen that
 * wants the rail includes it, and the review queue simply does not.
 *
 * THE DOTS ARE THE BUCKET, NOT A SECOND OPINION. An entry's dot class comes from the
 * bucket id the coverage payload filed it under, and the list renders in payload
 * order — worst evidence first, the same argument the explorer makes. Composing a
 * colour from the verdict here would be a second copy of `app/dq/coverage.py`'s
 * decision, which is the mockup defect (a hardcoded NEVER RUN beside a live run) this
 * codebase exists to make impossible.
 *
 * ponytail: no connection block and no catalog count, both of which the mockup's rail
 * carries. The connection facts (database, schema, role) have no API route to arrive
 * by — add one with a bead if the rail proves to need them — and the catalog is
 * already a card on the rules screen, where it is live rather than a static count.
 *
 * `prefetch={false}` for the two reasons tables/page.tsx documents on its own links:
 * a viewport of rail links would fire a background render per table, and the cancelled
 * prefetches read as failed requests in the console-clean check.
 */

const DOT: Record<string, string> = {
  "never-run": "never",
  unverifiable: "unver",
  verified: "verif",
};

/**
 * The rail, off the critical path (bead dq-9do). Every screen that rendered <Rail/>
 * used to wait on its coverage read before the page could answer at all — ~1.6 s warm,
 * against page payloads of 0.2–0.9 s, so the slowest thing on every engineer tab click
 * was the CHROME. This wrapper streams it instead: the page flushes immediately with a
 * same-width skeleton in the rail's column, and the real list replaces it when
 * coverage answers. (/tables passes its own coverage in, so there the child resolves
 * with the page and the skeleton never shows — one read, two renderings, unchanged.)
 *
 * THE ROLE CHECK LIVES OUTSIDE THE BOUNDARY, and that is the reason this wrapper is
 * async rather than a bare <Suspense>. A static fallback would flash a rail at the
 * domain expert, whose document must never CONTAIN one (F11 — the e2e asserts DOM
 * absence, not invisibility). The check is a cookie read, effectively free, so it is
 * settled before deciding whether a boundary exists at all: for anyone but the
 * engineer there is no skeleton, no Suspense and no coverage call — the same
 * subtraction Rail itself makes.
 *
 * THE SKELETON WEARS THE `.rail` CLASS, deliberately. `main:has(> .rail)` is what
 * flips the page into its two-column layout, and it must hold from FIRST paint: a
 * fallback without the class would render single-column and shove the content left
 * when the rail arrived — the exact jump the 0.1 CLS budget
 * (tests/e2e/test_ui_hygiene.py::test_no_layout_shift_on_first_paint) exists to catch.
 */
export async function StreamedRail({ coverage }: { coverage?: Coverage }) {
  if ((await chosenRole()) !== "engineer") {
    return null;
  }
  return (
    <Suspense fallback={<RailSkeleton />}>
      <Rail coverage={coverage} />
    </Suspense>
  );
}

/**
 * Same column, same surface, nothing to read: holds the rail's 248px while the
 * coverage read is in flight. `aria-hidden` because a placeholder has no content a
 * screen reader should stop on — the labelled aside arrives with the data.
 */
function RailSkeleton() {
  return (
    <aside className="rail" aria-hidden="true">
      <div className="rail-block">
        <span className="skel-line" />
        <span className="skel-line" />
        <span className="skel-line" />
        <span className="skel-line" />
      </div>
    </aside>
  );
}

export async function Rail({ coverage }: { coverage?: Coverage }) {
  if ((await chosenRole()) !== "engineer") {
    return null;
  }
  const buckets = coverage ?? (await read<Coverage>("/tables"));
  if (refused(buckets)) {
    // The rail is chrome. A coverage refusal belongs to the screen that is ABOUT
    // coverage; a second banner in the margin would say the same thing twice.
    return null;
  }
  return (
    <aside className="rail" aria-label="Tables, by verification bucket">
      <div className="rail-block">
        <span className="eyebrow">Tables</span>
        <span className="rail-cap">Click to open a table&rsquo;s rules.</span>
        <div className="rail-tables">
          {buckets.buckets.flatMap((bucket) =>
            bucket.tables.map((row) => (
              <Link
                key={row.table}
                href={`/tables/${encodeURIComponent(row.table)}/rules`}
                prefetch={false}
              >
                <span className={`dot ${DOT[bucket.id] ?? ""}`} />
                {row.table}
                <span className="rows">{row.rows}</span>
              </Link>
            )),
          )}
        </div>
      </div>
      <div className="rail-block">
        <span className="eyebrow">Verification buckets</span>
        <div className="legend">
          <div>
            <span className="dot never" />
            never run
          </div>
          <div>
            <span className="dot unver" />
            ran, unverifiable
          </div>
          <div>
            <span className="dot verif" />
            verified
          </div>
        </div>
      </div>
    </aside>
  );
}
