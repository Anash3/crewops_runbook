import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "CrewOps | Runbook Control",
  description: "Resolve crew operations cases with traceable tool calls and human approval.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
    >
      <body className="min-h-full"><Providers><AppShell>{children}</AppShell></Providers></body>
    </html>
  );
}
