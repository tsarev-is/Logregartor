import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Logregator — Incident Intelligence",
  description: "Evidence-first AI observability workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
