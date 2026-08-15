import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ResearchAssistant — Evidence, in context",
  description:
    "Research a public claim from both sides and release a source-grounded brief.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
