/**
 * The licensing boundary, written for a student rather than for a lawyer.
 * Rendered on the home page; the reasoning and the deployment consequences are in
 * docs/adr/ADR-001-licensing-boundary.md (owned by the docs builder).
 */
export default function LicensingBoundary() {
  return (
    <section className="card" id="licensing" aria-labelledby="licensing-heading">
      <h2 id="licensing-heading">About the book text: what samjho does and does not include</h2>
      <p>
        <strong>samjho does not contain your textbook, and never serves it to anyone.</strong>{" "}
        NCERT&apos;s terms of use for its online textbooks say that republication of NCERT textbooks
        by any other individual or agency is strictly prohibited, and that no website or online
        service is permitted to host those online textbooks.
      </p>
      <p>So the project is split in two:</p>
      <ul>
        <li>
          <strong>What ships with samjho:</strong> the chapter and section list with page anchors
          (factual structure taken from public syllabus documents), the concept animations, and the
          quiz and answer machinery. None of that is book text.
        </li>
        <li>
          <strong>What stays with you:</strong> the text of the book. You ingest it from your own
          copy, on your own machine, into a folder that is never committed and never uploaded. If
          you run samjho for yourself, the answers are built from <em>your</em> copy.
        </li>
      </ul>
      <p>
        Answers are generated from the passages that were retrieved from your copy, and every
        sentence that leans on the book carries a citation — chapter, section and page — so you can
        check it against the page in front of you. They are <em>not</em> quotations from the book,
        and samjho will not pretend otherwise: when your material does not cover a question, it
        refuses and says so instead of writing something plausible.
      </p>
      <p className="subtle">
        Maths-heavy pages are a known weak spot: the PDF text layer for radicals and fractions
        degrades (for example <code>3√2</code> extracts as <code>3 2</code>), so samjho answers
        maths questions at the section and reasoning level and points you at the page rather than
        reproducing a formula as if the extraction were faithful.
      </p>
    </section>
  );
}
