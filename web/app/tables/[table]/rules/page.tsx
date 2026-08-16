import { Unbuilt } from "../../../unbuilt";

export const metadata = { title: "Rules" };

export default async function Page({ params }: PageProps<"/tables/[table]/rules">) {
  const { table } = await params;
  return <Unbuilt heading={`Rules for ${table}`} owner="F12 · Rule management" />;
}
