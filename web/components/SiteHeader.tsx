import Link from "next/link";

/** Static header: no data fetch, so it renders identically on every page. */
export default function SiteHeader() {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <Link href="/" className="brand">
          samjho
          <span>study companion · CBSE Class 10</span>
        </Link>
        <nav className="site-nav" aria-label="Main">
          <ul>
            <li>
              <Link href="/">Subjects</Link>
            </li>
            <li>
              <Link href="/#what-this-is">What this is</Link>
            </li>
            <li>
              <Link href="/#licensing">Licensing boundary</Link>
            </li>
          </ul>
        </nav>
      </div>
    </header>
  );
}
