import { read, refused, write, type Proposal, type Rule, type Workbench } from "../../../api";
import { chosenRole } from "../../../role";
import { judge, propose, revise } from "./actions";
import { AuthorField, Pick, Selection } from "./desk";
import { ruleToken, specToken } from "./token";

export const metadata = { title: "Rules" };

/**
 * F12 · the translation desk. The screen the whole UI direction was chosen for.
 *
 * ITS IDEA IS A BILINGUAL SPREAD: the plain-English statement and the Great Expectations
 * configuration as facing pages, warm paper against cool
 * (`design/ux-variant-workbench.html`). SPEC F12 was amended to Rev 0.4 for it, and the
 * amendment is the single most important line in this file:
 *
 *     const engineer = (await chosenRole()) === "engineer";
 *
 * That one boolean decides whether `?configuration=1` is asked for, which decides
 * whether the framework is IN THE PAYLOAD at all. For the domain expert the GE pane is
 * not collapsed, not hidden and not styled away — the data it would render never leaves
 * the Python process, so there is nothing in this document to reveal by scrolling, by
 * viewing source, or by a stylesheet failing to load. The mockup did it with
 * `body.expert .ge-pane { display: none }`; a pane hidden with CSS is a pane that
 * shipped.
 *
 * WHAT THE OTHER DIRECTION COSTS, AND WHAT IS GRAFTED IN. Three judges scored this
 * direction 6.5/10 on expert usability — second lowest of four — because its heart is
 * the bilingual pane and the expert never sees the second half of it (design/README.md).
 * The prescribed mitigation is the Reviewer variant's copy, and it is already load-
 * bearing here: every Accept button on this screen reads
 * `app/dq/status.py::ACCEPT_ACTION`, which is Reviewer's "I vouch for this" rather than
 * a bare "Accept", and the bulk control reads its plural. The time-budget indicator is
 * the other half of that graft and lives where INV-1 actually applies — the review queue
 * (`/review`), which is the screen a domain expert spends five minutes on.
 *
 * NOTHING ON THIS SCREEN CAN PERSIST A RULE THAT SKIPPED THE VALIDATOR. Every write goes
 * through `./actions.ts` to `POST /rules`, `app/api/request.py::batched` and
 * `app/rules/store.py::judge_batch`, which reaches the table only through `propose()` and
 * `set_status()` — both of which call `validate()`. A spec that travelled to the browser
 * as a checkbox value and came back edited is refused by INV-2's own door.
 *
 * ponytail: no component library, no tabs, no accordion, no drag-to-reorder. One page,
 * three cards and a rail, all server-rendered; the two things that genuinely need the
 * browser are in `./desk.tsx` and say why. Ceiling: every rule this table has renders in
 * one document, and a table with two hundred rules is a long page.
 */
export default async function Page({ params, searchParams }: PageProps<"/tables/[table]/rules">) {
  const { table } = await params;
  const { propose: asked, refused: complaint } = await searchParams;

  // SPEC F12, Rev 0.4 — see the note above. This is the whole of the role's effect: one
  // boolean, turned into one query parameter, deciding what the payload contains.
  const engineer = (await chosenRole()) === "engineer";
  const asConfigured = (path: string) =>
    engineer ? `${path}${path.includes("?") ? "&" : "?"}configuration=1` : path;

  const desk = await read<Workbench>(asConfigured(`/rules?table=${encodeURIComponent(table)}`));
  if (refused(desk)) {
    return <p className="refused">{desk.refused}</p>;
  }

  // ONE BILLED CALL, AND ONLY WHEN SOMEBODY ASKED FOR IT. `?propose=1` is reached by a
  // POST that redirects (`actions.ts::propose`), never by a link, because the fetch
  // behind it costs ~$0.04 and ~6.6 s (LT-2b) and a link is what a prefetch, a crawler
  // and a back button all issue on their own. `app/rules/suggest.py` memoises the batch
  // for five minutes, so reloading this URL is free.
  const suggested = asked
    ? await write<{ proposals: Proposal[] }>(
        asConfigured(`/proposals/${encodeURIComponent(table)}`),
        {},
      )
    : null;
  const proposals = suggested && !refused(suggested) ? suggested.proposals : [];

  // TWO LISTS, AND THE SPLIT IS THE TWO BOOLEANS THE SERVER SENT. `bulk` means the row may
  // be selected and `held` means somebody asked for it to be looked at; a rule that is
  // neither has been judged, and filing it under "waiting on a decision" would be asking
  // for a decision nobody owes. Neither state name appears here — see
  // `app/rules/desk.py::workbench` for why the screen is told rather than deducing.
  const waiting = desk.rules.filter((rule) => rule.bulk || rule.held);
  const settled = desk.rules.filter((rule) => !rule.bulk && !rule.held);

  return (
    <>
      <div className="screen-head">
        <h1>
          Rules · <code>{table}</code>
        </h1>
        <p className="who">
          The translation desk — both users work here.{" "}
          {engineer
            ? "English on the left, the configuration it compiles to on the right, always the same rule."
            : "Everything is stated in business language. Nothing here asks you to read a schema."}
        </p>
      </div>

      {typeof complaint === "string" ? <p className="refused">{complaint}</p> : null}

      <div className="f12-grid">
        <div>
          <AuthorField
            table={table}
            copy={desk.copy}
            configuration={engineer}
            judge={judge}
          />

          <section className="card bulk">
            <div className="bulk-head">
              <span className="eyebrow">Waiting on a decision</span>
              <span className="cap-note">{desk.copy.bulk_note}</span>
              {/* Said once, above every row that carries the token. Great Expectations
                  accepted 10 of 25 deliberately nonsense rules while reporting success
                  (LT-2a), so "Compiled" beside a rule is a statement about shape and a
                  reader has to be told that in words — a neutral grey chip is a weaker
                  claim than a sentence, and this is the sentence. */}
              <span className="compiled-hint">{desk.copy.compiled_caveat}</span>
            </div>

            <Selection table={table} cap={desk.cap} copy={desk.copy}>
              <ul className="bulk-list">
                {proposals.map((proposal) => (
                  <Row
                    key={specToken(proposal)}
                    table={table}
                    token={specToken(proposal)}
                    item={proposal}
                    copy={desk.copy}
                  />
                ))}
                {waiting.map((rule) => (
                  <Row
                    key={rule.rule_id}
                    table={table}
                    token={ruleToken(rule.rule_id)}
                    item={rule}
                    copy={desk.copy}
                  />
                ))}
              </ul>
            </Selection>

            {proposals.length === 0 ? (
              <form className="actions" action={propose}>
                <input type="hidden" name="table" value={table} />
                <button className="btn" data-suggest>
                  Suggest rules from this table&rsquo;s statistics
                </button>
                <span className="unsaved-note">{desk.copy.unsaved}</span>
              </form>
            ) : null}
          </section>

          <p className="mutability-note">{desk.copy.amended}</p>

          {/* THE SECOND LIST IS THE SETTLED ONE, and it is a separate section rather than
              more of the first because the heading above is a claim: a screen that filed
              an accepted rule under "waiting on a decision" would be asking for a decision
              nobody owes. Same rows, same actions — a rule that has been accepted can
              still be rejected, and one that was rejected can be revisited — but no
              checkbox on any of them, because `bulk` is false for both states and the
              server is what decided that. */}
          <section className="card bulk">
            <div className="bulk-head">
              <span className="eyebrow">
                Settled — {settled.length} {settled.length === 1 ? "rule" : "rules"} on this table
              </span>
              <span className="cap-note">
                Judged already. Changing one is a new revision, not an edit, and the previous
                one stays readable.
              </span>
            </div>
            <ul className="bulk-list">
              {settled.map((rule) => (
                <Row
                  key={rule.rule_id}
                  table={table}
                  token={ruleToken(rule.rule_id)}
                  item={rule}
                  copy={desk.copy}
                />
              ))}
            </ul>
          </section>
        </div>

        {/* B6 · the whole menu, from the one file. Nothing here declares how long it is. */}
        <aside className="card catalog">
          <div className="catalog-head">
            <span className="eyebrow">Expectation catalog</span>
            <span className="note">
              The whole menu — {desk.catalog.length} curated types. Neither the translator nor
              the proposer may leave it, and a rule outside it is refused rather than
              approximated.
            </span>
          </div>
          {/* The menu is bilingual too: the engineer reads the framework's identifiers,
              the domain expert reads the sentence each one turns into. Same fifteen
              entries either way, and neither reader meets a name from the other's
              language — see app/rules/desk.py::catalog_rail. */}
          <ul className="catalog-list" data-catalog>
            {desk.catalog.map((entry) => (
              <li
                key={entry.english}
                className={entry.in_use ? "on" : undefined}
                title={entry.english}
              >
                {entry.type ?? entry.english}
              </li>
            ))}
          </ul>
          <div className="catalog-foot">● in use on this table</div>
        </aside>
      </div>
    </>
  );
}

/**
 * One row of the list: a machine proposal or a stored rule, rendered the same way.
 *
 * THEY ARE ONE COMPONENT BECAUSE THEY ARE ONE DECISION. What a person judges is a
 * sentence and the numbers behind it, and whether it happens to have a row in the store
 * yet is our problem rather than theirs. The two differences are both carried by the
 * payload rather than derived here: `bulk` says whether the row may be selected, `held`
 * says whether it is waiting on somebody, and a stored rule additionally carries the
 * `judgments` still open to it.
 *
 * THE EVIDENCE LINE IS NOT OPTIONAL. LT-2b's proposal — `order_total BETWEEN 0 AND
 * 89,400` — was true of every row the model saw and wrong about the business, and it is
 * indistinguishable from a good rule until you can see that 89,400 is simply the largest
 * value in the table. `Proposal.__post_init__` refuses a proposal with a blank evidence
 * line, so a row with nothing to show here cannot exist.
 */
function Row({
  table,
  token,
  item,
  copy,
}: {
  table: string;
  token: string;
  item: Proposal | Rule;
  copy: Workbench["copy"];
}) {
  const stored = "rule_id" in item ? item : null;
  return (
    <li className={item.held ? "excluded" : undefined} data-row={item.status}>
      {item.bulk ? <Pick token={token} label={item.statement} /> : <span />}

      <div className="b-body">
        <div className="rr-top">
          {/* The state in English, styled by its raw name — the same pair everywhere
              (app/dq/status.py::STATE_LABELS). Both users get the English one: the
              engineer's own vocabulary is the facing pane, not the state machine. */}
          <span className={`atom ${item.status}`}>{item.state_label}</span>
          <span className="atom compiled" data-compiled>
            {copy.compiled_token}
          </span>
          {item.column ? <code>{item.column}</code> : null}
        </div>
        {/* THE FACING PAGES, and they are facing rather than folded. SPEC F12 Rev 0.4
            replaced "collapsed by default" with a pane, so there is no `<details>` on
            this screen and no disclosure control to open: the engineer reads both
            languages at once, which is the entire variant. For anyone else `.ge-pane`
            is not rendered, `body.expert .spread` makes the grid one column, and the
            row is a sentence with numbers under it. */}
        <div className="spread">
          <div className="pane en-pane">
            <span className="eyebrow">In English</span>
            <p className="b-stmt">{item.statement}</p>
          </div>
          {item.configuration ? (
            <div className="pane ge-pane">
              <span className="eyebrow">The configuration it compiles to</span>
              <pre tabIndex={0}>{JSON.stringify(item.configuration, null, 2)}</pre>
            </div>
          ) : null}
        </div>

        <p className="evidence">{item.evidence}</p>
        {stored?.reason ? <p className="evidence">{stored.reason}</p> : null}
        {item.held ? <p className="excl-why">{copy.bulk_excluded}</p> : null}

        <form className="actions" action={judge}>
          <input type="hidden" name="table" value={table} />
          <input type="hidden" name="pick" value={token} />
          <label>
            {copy.reason_label}
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

        {stored ? <Amend table={table} rule={stored} copy={copy} /> : null}
      </div>
    </li>
  );
}

/**
 * The two edit doors, one per user, on the rule they change.
 *
 * THE ENGINEER EDITS THE CONFIGURATION; THE DOMAIN EXPERT EDITS THE SENTENCE AND THE
 * SYSTEM RECOMPILES. That is SPEC F12's fourth clause, and it is the thing that makes
 * the bilingual split honest rather than decorative: the spread is not two views of one
 * rule, it is two ways INTO it. Both end at `app/rules/desk.py::revise`, both are
 * revalidated on the way in, and both land the rule in `needs_review` — which is what
 * `copy.amended` says under the list, because it is the half nobody expects.
 *
 * Which door renders is decided by whether the configuration arrived at all, so it is
 * the same Rev 0.4 mechanism as the pane itself rather than a second role check.
 */
function Amend({ table, rule, copy }: { table: string; rule: Rule; copy: Workbench["copy"] }) {
  return (
    <form className="amend" action={revise}>
      <input type="hidden" name="table" value={table} />
      <input type="hidden" name="ruleId" value={rule.rule_id} />
      {rule.configuration ? (
        <label>
          {copy.reconfigure}
          <textarea
            name="configuration"
            rows={6}
            spellCheck={false}
            defaultValue={JSON.stringify(rule.configuration, null, 2)}
            data-configuration
          />
        </label>
      ) : (
        <label>
          {copy.restate}
          <input type="text" name="statement" defaultValue={rule.statement} data-restate />
        </label>
      )}
      <button className="btn">Propose revision &rarr;</button>
    </form>
  );
}
