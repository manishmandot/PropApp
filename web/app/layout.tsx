import type { Metadata } from "next";
import Link from "next/link";
import { Disclaimer } from "@/components/Disclaimer";
import { StaleBanner } from "@/components/StaleBanner";
import { siteUrl } from "@/lib/site";
import "./globals.css";

const SITE_URL = siteUrl();

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "PropApp — suburb scores for Australian property investors", template: "%s" },
  description:
    "Every Australian suburb scored on population, supply, income, jobs and — where data exists — prices, rents and sales.",
};

const NAV = [
  { href: "/suburbs", label: "Suburb finder" },
  { href: "/map", label: "Map" },
  { href: "/compare", label: "Compare" },
  { href: "/#methodology", label: "How it works" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-AU">
      <body className="min-h-screen font-sans antialiased">
        <header className="border-b border-line">
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="font-semibold text-ink no-underline">
              PropApp
            </Link>
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="text-sm text-ink-2 hover:text-ink">
                {item.label}
              </Link>
            ))}
          </nav>
        </header>
        <StaleBanner />
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl border-t border-line px-4 py-6">
          <Disclaimer />
        </footer>
      </body>
    </html>
  );
}
