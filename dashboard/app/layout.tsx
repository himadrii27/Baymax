import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Baymax — Personal Healthcare Companion",
  description: "Your personal healthcare companion, powered by Gemini.",
  icons: { icon: "/baymax.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-bh-dark min-h-screen antialiased">{children}</body>
    </html>
  );
}
