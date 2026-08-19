import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import { read, refused, type Coverage } from "./api";
import { chosenRole, bodyClass, selectRole } from "./role";
import { Tabs } from "./tabs";
import { Report } from "./report";

export const metadata: Metadata = {
  title: { default: "Data quality assistant", template: "%s · Data quality assistant" },
  description: "AI-powered data quality assistant",
};

/**
 * The shell every route renders inside: the brand, the role switch, and `<main>`.
 *
 * THE ROLE SWITCH IS IN THE HEADER AND NOT ON A PAGE, which is the mockup's
 * arrangement (design/ux-variant-workbench.html) and is load-bearing rather than
 * decorative. It is the only control that changes what a permalink shows, so it has
 * to be on the permalink — a reader who arrived cold from someone else's link is
 * exactly the person who may be in the wrong view, and F14 promises them a page they
 * can act on with no prior navigation.
 *
 * IT RENDERS ONCE PER DOCUMENT AND IS THEN PRESERVED across every navigation, so
 * anything it decides from the route is decided once, on the route the reader happened
 * to land on. Both server-side arrangements for route-aware chrome were built and
 * measured against that, back when the role door needed the switch subtracted from one
 * screen: a parallel-route slot left `/tables` with no switch after a soft navigation
 * (six hygiene checks went red), and a `usePathname()` wrapper makes the shell of every
 * route a client component. The door is gone (bead dq-1rp) but the constraint is not —
 * it is why the tab bar below is its own client island rather than logic here.
 *
 * `body.expert` is the mockup's own mechanism, carried over verbatim: one class on
 * one element, and the configuration pane is not rendered (SPEC F12, Rev 0.4). It is
 * decided on the SERVER, so the first paint is already right — see web/app/role.ts.
 *
 * ponytail: no header component, no nav component, no `<RoleSwitch />`. Each would
 * have exactly one caller — this file — and a wrapper with one caller is a file to
 * open on the way to reading the markup it hides.
 */
export default async function RootLayout({ children }: LayoutProps<"/">) {
  const role = await chosenRole();
  // Hoisted rather than inlined as `className={await bodyClass()}`: jsx-ast-utils
  // cannot resolve an await inside a prop and prints a "please file an issue" line on
  // every lint run, which is noise in a gate whose whole value is that green means green.
  const view = await bodyClass();
  // The tab bar's fallback table, so F12 and F13 are live before any table has been
  // opened (bead dq-1rp: every tab clickable from the first paint). The first entry of
  // the first bucket is the coverage order's own top pick — the payload decided, not
  // this file. Server-to-server; the document carries one href, never the list.
  const coverage = await read<Coverage>("/tables");
  const fallbackTable = refused(coverage)
    ? null
    : (coverage.buckets.flatMap((bucket) => bucket.tables)[0]?.table ?? null);
  return (
    <html lang="en">
      <body className={view}>
        <header className="topbar">
          <div className="brand">
            <span className="wordmark">Diglot</span>
            <span className="glyph">¶ ⇄ {"{ }"}</span>
            <span className="sub">data-quality workbench</span>
          </div>
          {/* The mockup's screen tabs, restored by the author's call (bead dq-448; the
              component says what that decision cost and where). Suspense because
              useSearchParams demands a boundary at build time; the fallback is nothing
              for the frame of a hard load. */}
          <Suspense fallback={null}>
            <Tabs fallbackTable={fallbackTable} />
          </Suspense>
          <form className="role-switch" action={selectRole}>
            <span className="cap" id="role-caption">
              Viewing as · a view, not an account
            </span>
            <span className="role-seg" role="group" aria-labelledby="role-caption">
              <button name="role" value="engineer" aria-pressed={role === "engineer"}>
                Engineer
              </button>
              <button name="role" value="expert" aria-pressed={role === "expert"}>
                Domain expert
              </button>
            </span>
          </form>
          {/* The bug door (bead dq-bba). Last in the header so it is reachable and
              never in the way; inside the topbar because that is the only place a
              persistent link is legal (tests/e2e/test_f11_review_queue.py). Its own
              island for the same reason Tabs is one, and the same Suspense, because
              it too reads useSearchParams. */}
          <Suspense fallback={null}>
            <Report role={role} />
          </Suspense>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
