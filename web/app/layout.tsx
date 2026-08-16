import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Data quality assistant", template: "%s · Data quality assistant" },
  description: "AI-powered data quality assistant",
};

// `<main>` wraps every route so axe's `region` rule is satisfied by the shell rather
// than by each screen remembering a landmark. `lang` is what `html-has-lang` reads.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
