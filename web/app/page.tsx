import { redirect } from "next/navigation";
import { HOME, chosenRole, selectRole } from "./role";

/**
 * F11 · the role door. One click, remembered, and then this page is never seen again.
 *
 * A device that has already chosen never gets here: it is redirected to that role's
 * own door, which is `/tables` for the engineer and `/review` for the domain expert.
 * That redirect is the "remembered" half of F11's acceptance, and it is why `/` is
 * not a dashboard — a shared front page would be a third screen to design and the one
 * place both users would meet the other's job.
 *
 * The two doors are `<form>`s rather than links because choosing writes something
 * (the cookie). A link that changed state on GET would be re-chosen by every
 * prefetch, every crawler and every back button.
 *
 * THE CHOICE IS OFFERED ONCE ON THIS SCREEN. The header's role switch is on every
 * other route and not on this one; `globals.css` under `body:has(.doorway)` is where
 * that is implemented and where the reasoning lives, including the two server-side
 * arrangements that were tried first and what each cost.
 *
 * `.doorway` is the composition: three bands — the question, the two doors, and the
 * line that says what choosing does and does not mean — sized to the fold and
 * centred in it, rather than a stack that stops a third of the way down a screen it
 * was given all of. Not one word of the copy moved except that last line, which now
 * sits under the choice it reassures the reader about instead of above it.
 */
export default async function Page() {
  const role = await chosenRole();
  if (role) {
    redirect(HOME[role]);
  }
  return (
    <section className="doorway">
      <div className="screen-head">
        <h1>Who is looking?</h1>
      </div>
      <div className="door">
        <form action={selectRole}>
          <input type="hidden" name="then" value="home" />
          <button name="role" value="engineer">
            <span className="title">Engineer</span>
            <span className="why">
              Start at coverage: which tables nobody has vouched for yet, which have no rules
              at all, and what the last run actually proved.
            </span>
          </button>
        </form>
        <form action={selectRole}>
          <input type="hidden" name="then" value="home" />
          <button name="role" value="expert">
            <span className="title">Domain expert</span>
            <span className="why">
              Start at judgment: rules waiting for your decision, each stated in business
              language with the numbers it was inferred from. No schema, and no table list.
            </span>
          </button>
        </form>
      </div>
      <p className="who">
        This is a view, not an account. There is nothing to log into, the two views share every
        address, and you can change your mind from any screen.
      </p>
    </section>
  );
}
