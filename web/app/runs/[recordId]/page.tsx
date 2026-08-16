import { Unbuilt } from "../../unbuilt";

export const metadata = { title: "Run record" };

export default async function Page({ params }: PageProps<"/runs/[recordId]">) {
  const { recordId } = await params;
  return <Unbuilt heading={`Run ${recordId}`} owner="F13 · Results dashboard" />;
}
