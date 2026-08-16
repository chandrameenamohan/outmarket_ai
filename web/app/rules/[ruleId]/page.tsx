import { Unbuilt } from "../../unbuilt";

export const metadata = { title: "Rule" };

export default async function Page({ params }: PageProps<"/rules/[ruleId]">) {
  const { ruleId } = await params;
  return <Unbuilt heading={`Rule ${ruleId}`} owner="F12 · Rule management, F14 · permalinks" />;
}
