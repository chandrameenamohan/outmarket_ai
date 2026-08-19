"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

/**
 * The mockup's tab bar (design/ux-variant-workbench.html, `.tabs`), by the author's
 * own call (bead dq-448): from a UX perspective nobody should be typing routes, and
 * the four screens should be reachable from every screen the way the mockup reaches
 * them. Same labels, same F-keys, both roles — the mockup's role split changes what a
 * screen CONTAINS, never which screens exist.
 *
 * IT IS A CLIENT COMPONENT BECAUSE THE LAYOUT CANNOT KNOW THE ROUTE. The shell
 * renders once per document and is preserved across every soft navigation, and both
 * server-side arrangements for route-aware chrome were built, measured and rejected —
 * layout.tsx tells that story. This is the third arrangement it names: the smallest
 * possible client island, the four tabs and nothing else, hydrated with the route the
 * hooks already track.
 *
 * F12 AND F13 ARE PER-TABLE SCREENS, WHICH THE MOCKUP'S STATIC DATA LET IT IGNORE —
 * its Rules tab simply was `orders`. Here the two tabs follow the table in context,
 * read from the path (`/tables/<t>/rules`) or the query (`?table=` on /runs and
 * /review), and render as muted text when there is none: a link has to point
 * somewhere, and inventing a default table would be this component deciding which
 * table matters, which is the coverage dashboard's whole job.
 *
 * WHAT KEEPS THIS LEGAL ON /review (SPEC F11, frozen): the clause forbids a TABLE
 * LIST, and no tab names a table — the visible text is four screen names, fixed. The
 * e2e assertions that read wider than the clause (no navigation at all) were narrowed
 * to the clause itself in the same commit, by the same author decision; they still
 * forbid nav outside this bar, selects anywhere, and a table name as link text.
 *
 * `prefetch={false}` for the tables/page.tsx reasons: four tabs in the viewport on
 * every screen would be four background renders per load, and the cancelled ones read
 * as failures in the console-clean check.
 */

const TABS = [
  { key: "f10", label: "Table Explorer" },
  { key: "f11", label: "Review Queue" },
  { key: "f12", label: "Rules" },
  { key: "f13", label: "Results" },
] as const;

export function Tabs() {
  const pathname = usePathname();
  const query = useSearchParams();

  const fromPath = /^\/tables\/([^/]+)\/rules$/.exec(pathname)?.[1];
  const table = fromPath ? decodeURIComponent(fromPath) : query.get("table");

  const current = fromPath
    ? "f12"
    : pathname === "/tables"
      ? "f10"
      : pathname === "/review"
        ? "f11"
        : pathname.startsWith("/runs")
          ? "f13"
          : null;

  const href = (key: string): string | null => {
    if (key === "f10") return "/tables";
    if (key === "f11") return "/review";
    if (!table) return null;
    const t = encodeURIComponent(table);
    return key === "f12" ? `/tables/${t}/rules` : `/runs?table=${t}`;
  };

  return (
    <nav className="tabs" aria-label="Screens">
      {TABS.map((tab) => {
        const target = href(tab.key);
        return target ? (
          <Link
            key={tab.key}
            href={target}
            prefetch={false}
            aria-current={current === tab.key ? "page" : undefined}
          >
            <span className="fkey">{tab.key.toUpperCase()}</span>
            {tab.label}
          </Link>
        ) : (
          <span
            key={tab.key}
            className="needs-table"
            title="Open a table first — rules and results are per-table screens."
          >
            <span className="fkey">{tab.key.toUpperCase()}</span>
            {tab.label}
          </span>
        );
      })}
    </nav>
  );
}
