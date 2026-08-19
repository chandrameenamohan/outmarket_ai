"use client";

/**
 * The bug door (bead dq-bba): "Report a problem", far right of the topbar.
 *
 * One click, straight to GitHub's new-issue form in a new tab — GitHub is the
 * collector, so there is no in-app form to lose text in and nothing to store.
 * The title is left EMPTY on purpose: a prefilled title is what nobody edits,
 * and forty identical subjects are worse than forty first sentences in the
 * reporter's own words. The body prefills identifiers and addresses ONLY —
 * the page's absolute URL and, where the route carries one, the run record,
 * rule or table id. Never page content: payloads and error text live in the
 * immutable record, which the URL already reaches. That rule is also what
 * keeps the href two orders of magnitude under GitHub's ~8k URL truncation.
 *
 * A client island like `Tabs`, and for the same reason (web/app/layout.tsx):
 * the shell renders once per document, so anything route-aware in the header
 * must read the route itself. The origin comes from `window.location` after
 * mount — the server does not know the address it is deployed at, and the
 * pre-mount href is the same link minus the page line, which still works.
 *
 * A plain <a>, not a button with window.open: middle-click, copy-link-address
 * and screen-reader link semantics come free, and `next/link` buys nothing
 * for an off-site URL. This is the app's first external link; new tab because
 * the reporter is standing on the evidence they are reporting.
 */

import { usePathname, useSearchParams } from "next/navigation";
import { useSyncExternalStore } from "react";

const NEW_ISSUE = "https://github.com/chandrameenamohan/outmarket_ai/issues/new";

export function Report({ role }: { role: string }) {
  const pathname = usePathname();
  const query = useSearchParams();
  // Hydration-safe origin: "" on the server, the real address after mount. An
  // external-store read rather than a set-state-in-effect, which the lint gate
  // rejects for the cascading render it causes.
  const origin = useSyncExternalStore(
    () => () => {},
    () => window.location.origin,
    () => "",
  );

  const recordId = /^\/runs\/([^/]+)$/.exec(pathname)?.[1];
  const ruleId = /^\/rules\/([^/]+)$/.exec(pathname)?.[1];
  const fromPath = /^\/tables\/([^/]+)\/rules$/.exec(pathname)?.[1];
  const table = fromPath ? decodeURIComponent(fromPath) : query.get("table");

  const search = query.toString();
  const lines = [
    "<!-- Say what you expected and what happened instead. Plain English is perfect. -->",
    "",
    "---",
    "*Sent from the workbench*",
  ];
  if (origin) lines.push(`- Page: ${origin}${pathname}${search ? `?${search}` : ""}`);
  if (recordId) lines.push(`- Run record: \`${decodeURIComponent(recordId)}\``);
  if (ruleId) lines.push(`- Rule: \`${decodeURIComponent(ruleId)}\``);
  if (table) lines.push(`- Table: ${table}`);
  lines.push(`- Viewing as: ${role === "expert" ? "Domain expert" : "Engineer"}`);

  const href = `${NEW_ISSUE}?labels=from-the-app&body=${encodeURIComponent(lines.join("\n"))}`;

  return (
    <a
      className="report"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Report a problem (opens GitHub in a new tab)"
      title="Opens GitHub in a new tab, with this page's address already filled in. You write what went wrong; we read every one."
    >
      Report a problem
    </a>
  );
}
