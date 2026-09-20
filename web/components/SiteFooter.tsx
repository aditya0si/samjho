import Link from "next/link";

import { API_BASE } from "@/lib/api";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <p>
          <strong>samjho</strong> never ships or serves textbook text. NCERT does not permit
          republication or hosting of its books, so your copy of the book stays on the machine that
          ingested it — the repo ships only the chapter and section structure and our own
          animations.{" "}
          <Link href="/#licensing">Read the licensing boundary</Link>.
        </p>
        <p className="mono">
          API: {API_BASE} · answers are refused rather than invented when your material does not
          cover a question.
        </p>
      </div>
    </footer>
  );
}
