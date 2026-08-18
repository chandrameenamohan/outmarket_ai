import type { Metadata } from "next";
import "./globals.css";
import { chosenRole, bodyClass, selectRole } from "./role";

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
 * IT IS NOT OFFERED ON THE DOOR, which is the one screen that already asks the same
 * question in full. That subtraction is made in `globals.css` under `body:has(.doorway)`
 * and NOT here, and the reason is worth writing down because the obvious way round is
 * broken: this layout renders once per document and is then PRESERVED across every
 * navigation, so anything it decides from the route is decided once, on the route the
 * reader happened to land on. Both server-side arrangements were built and measured
 * against that. A parallel-route slot (`@toggle/default.tsx` + a `page.tsx` matching `/`)
 * left `/tables` with no switch at all after a reader walked through the door, because
 * a soft navigation keeps an unmatched slot's current state rather than falling back to
 * its default — six hygiene checks went red on it. A `usePathname()` wrapper re-renders
 * correctly but makes the shell of every route a client component to subtract one
 * control from one of them. See the `body:has(.doorway)` rule for what shipped.
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
  return (
    <html lang="en">
      <body className={view}>
        <header className="topbar">
          <div className="brand">
            <span className="wordmark">Diglot</span>
            <span className="glyph">¶ ⇄ {"{ }"}</span>
            <span className="sub">data-quality workbench</span>
          </div>
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
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
