import type { Metadata } from "next";
import { themeBootScript } from "@/features/preferences/theme-script";
import "./globals.css";
import "./research-design.css";

export const metadata: Metadata = {
  title: "ResearchAssistant",
  description:
    "Check a claim against sources, with exact quotes and an evidence-backed brief you can inspect.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
