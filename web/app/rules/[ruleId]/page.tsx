import { notFound, redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { read, refused, write, type Rule } from "../../api";
import { chosenRole } from "../../role";

export const metadata = { title: "Rule" };

/**
 * F14 · a rule's address. This page is the whole feature.
 *
 * SPEC §7 step 4 is the scenario it exists for: an engineer copies this URL into a
 * chat client and a domain expert follows it — cold, no prior navigation, no login,
 * possibly on a phone. So everything needed to judge the rule is here and nothing is
 * one click away: the sentence, the numbers it was inferred from, what state it is
 * in, and the three buttons that change that state.
 *
 * WHAT THE TWO READERS SEE DIFFERS, AND THE URL DOES NOT. The Great Expectations
 * configuration is a facing pane for the engineer and is **not rendered at all** for
 * anyone else (SPEC F12, Rev 0.4) — not `display: none`, not a disclosure control:
 * absent from the markup, so a domain expert reading this on a phone cannot meet the
 * framework by scrolling or by viewing source. A reader who has chosen no role at all
 * gets that same view, which is the conservative half of web/app/role.ts's default.
 * See that file for why a `/engineer/...` prefix would break exactly this.
 *
 * AND THE PAYLOAD DOES NOT CARRY IT EITHER, as of bead dq-rbf.4: `?configuration=1` is
 * asked for only in the engineer's render, so for anyone else the word is absent from
 * the JSON as well as from the markup. That closed the last gap in the sentence above —
 * a component deciding not to print a field it was handed is one refactor away from
 * printing it.
 *
 * ponytail: the configuration pane is read-only here. The editable one is on the rules
 * screen (`/tables/[table]/rules`), which is where both edit doors live because both of
 * them need the catalog rail beside them to say what the product can express at all.
 * Ceiling: engineers read the configuration on a permalink and amend it on the desk.
 *
 * ponytail: a static `metadata` title rather than `generateMetadata`. A per-rule
 * title would mean fetching the rule twice — once for the tab and once for the page —
 * to improve the wording of a browser tab.
 */
export default async function Page({ params, searchParams }: PageProps<"/rules/[ruleId]">) {
  const { ruleId } = await params;
  const { refused: complaint } = await searchParams;
  const engineer = (await chosenRole()) === "engineer";
  const rule = await read<Rule>(
    `/rules/${encodeURIComponent(ruleId)}${engineer ? "?configuration=1" : ""}`,
  );

  if (refused(rule)) {
    // A pasted link to a rule nobody ever wrote is a 404 and should say so with the
    // status code, not with a 200 carrying an apology. Everything else — the process
    // is down, the database is not answering — is the operator's problem and is
    // reported as itself, because a reader who cannot tell those apart will retry the
    // wrong one.
    if (rule.status === 404) {
      notFound();
    }
    return <p className="refused">{rule.refused}</p>;
  }

  return (
    <>
      <div className="screen-head">
        <h1>A rule about {rule.table}</h1>
        <p className="who">
          You opened this rule directly. Everything needed to judge it is on this page, and
          your decision is recorded as a new revision — nothing here is edited in place.
        </p>
      </div>

      {typeof complaint === "string" ? <p className="refused">{complaint}</p> : null}

      <article className="card">
        <div className="card-head">
          {/* In English, styled by the raw state. A permalink is the one screen a
              stranger reaches cold, so it is the last place to print a schema word. */}
          <span className={`atom ${rule.status}`}>{rule.state_label}</span>
          <span>
            about the table <code>{rule.table}</code>
            {rule.column ? (
              <>
                {" · column "}
                <code>{rule.column}</code>
              </>
            ) : null}
            {" · revision "}
            {rule.revision}
          </span>
        </div>

        <div className="spread">
          <div className="pane en-pane">
            <span className="eyebrow">In English</span>
            <p className="stmt">{rule.statement}</p>
          </div>
          {rule.configuration ? (
            <div className="pane ge-pane">
              <span className="eyebrow">The configuration it compiles to</span>
              <pre tabIndex={0}>{JSON.stringify(rule.configuration, null, 2)}</pre>
            </div>
          ) : null}
        </div>

        <p className="evidence">{rule.evidence}</p>
        {rule.reason ? <p className="evidence">{rule.reason}</p> : null}

        <form className="actions" action={judge}>
          <input type="hidden" name="ruleId" value={rule.rule_id} />
          <label>
            {rule.reason_label}
            <input type="text" name="reason" autoComplete="off" />
          </label>
          {rule.judgments.map((judgment) => (
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
    </>
  );
}

/**
 * One judgment, appended as a revision by the store (F6).
 *
 * A refusal comes back on the URL rather than in component state — the store rejects
 * a rejection with no reason, and that sentence has to reach the person who pressed
 * the button. Putting it in the query string means no client component, no hook and
 * no third rendering mode, and the failed attempt is reloadable and quotable like
 * everything else here.
 */
async function judge(form: FormData): Promise<void> {
  "use server";

  const ruleId = String(form.get("ruleId"));
  const answer = await write(`/rules/${encodeURIComponent(ruleId)}`, {
    status: form.get("status"),
    reason: form.get("reason"),
  });
  const here = `/rules/${encodeURIComponent(ruleId)}`;
  if (refused(answer)) {
    redirect(`${here}?refused=${encodeURIComponent(answer.refused)}`);
  }
  revalidatePath(here);
  redirect(here);
}
