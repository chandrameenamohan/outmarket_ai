/**
 * The only thing a route in the shell is allowed to render.
 *
 * B1 owns no SPEC feature — it makes the browser layer real, it does not build the
 * product. So every route below says which feature owns it and that the feature is
 * not built. Rendering plausible-looking rules, tables or run records here would
 * make `make check-ui` green against a lie, which is the one failure mode this
 * whole harness exists to prevent (VERIFICATION.md §10).
 */
export function Unbuilt({ heading, owner }: { heading: string; owner: string }) {
  return (
    <>
      <h1>{heading}</h1>
      <p>{owner} is not built yet. This route exists so the browser layer can reach it.</p>
    </>
  );
}
