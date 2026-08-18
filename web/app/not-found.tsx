import Link from "next/link";

import { chosenRole } from "./role";

export const metadata = { title: "Not here" };

/**
 * What a reader sees when the address they arrived on names nothing (bead dq-abs).
 *
 * IT IS REACHED BY A MISTYPED ID, not only by a mistyped path, and from BOTH of the two
 * addresses that carry one. `/rules/<id>` and `/runs/<recordId>` each call `notFound()`
 * on a 404 from the API, and an id that is not a uuid is one of those —
 * `app/rules/store.py::latest` and `app/dq/runs.py::find` refuse the shape before it
 * reaches PostgreSQL, so "no record under that id" and "that is not an id at all" are
 * the same answer to the reader, which is the truth. It used to be a 502 and a sentence
 * naming the private host of the internal service.
 *
 * SO THE PAGE SAYS THE THREE THINGS SOMEBODY CAN ACT ON: the link is what is wrong,
 * nothing on this side broke, and here is the door back in. Nothing about hosts, ports,
 * processes or frameworks appears here — the reader who mistyped a URL is not an
 * operator, and a stranger who guessed one is not owed the topology (SPEC §3.1).
 *
 * WHICH DOOR DEPENDS ON WHO IS READING, and that is F11 rather than tidiness. `/tables`
 * is the engineer's front door and refuses a domain expert by name when they reach it;
 * offering the link anyway would make this the one page in the product that points them
 * at it. `chosenRole()` costs one await on a component that is already async.
 *
 * ponytail: one page for every miss rather than a message per route. Ceiling: a bad rule
 * link and a bad run link read the same. That is what a reader needs from a page whose
 * only job is to be somewhere to leave.
 */
export default async function NotFound() {
  const engineer = (await chosenRole()) === "engineer";
  return (
    <div className="screen-head">
      <h1>There is nothing at this address</h1>
      <p className="who">
        The link you followed points at something this workbench has no record of — most
        likely it was mistyped, or the id in it was edited. Nothing here has gone wrong and
        nothing has been changed. If somebody sent you the link, ask them to send it again.
      </p>
      <p className="who">
        {engineer ? (
          <>
            <Link href="/tables">Browse the tables</Link>
            {" · "}
          </>
        ) : null}
        <Link href="/review">Open the review queue</Link>
      </p>
    </div>
  );
}
