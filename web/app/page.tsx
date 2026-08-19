import { redirect } from "next/navigation";
import { HOME, chosenRole } from "./role";

/**
 * `/` is a pure redirect to the current role's home: `/tables` for the engineer —
 * which, since bead dq-1rp, is every device that has not said otherwise — and
 * `/review` for a device that chose the domain expert in the header.
 *
 * THE WHO-IS-LOOKING DOOR THAT USED TO RENDER HERE WAS REMOVED by that same call:
 * for the demo, nobody should meet a questionnaire before the product. The choice
 * the door offered did not go away — it is the header's role switch, on every
 * screen, remembered exactly as the door's answer was (web/app/role.ts). The door's
 * screen, its CSS and its visual baseline went together; git history has all three.
 */
export default async function Page() {
  redirect(HOME[await chosenRole()]);
}
