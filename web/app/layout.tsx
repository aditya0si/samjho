import type { Metadata } from "next";
import type { ReactNode } from "react";

import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

import "../styles/globals.css";

export const metadata: Metadata = {
  title: {
    default: "samjho — study companion for CBSE Class 10",
    template: "%s · samjho",
  },
  description:
    "Pick a subject, chapter and section; ask questions answered only from your own ingested copy of the book with chapter, section and page citations; work through concept animations; take a quiz and see which sections you missed.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <SiteHeader />
        <main id="main">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
