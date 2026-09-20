import Link from "next/link";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <>
      <h1>There is no page at that address</h1>
      <p className="lede">
        Nothing was found for this URL. Chapter pages are addressed as{" "}
        <code>/&lt;subject&gt;/&lt;chapter&gt;</code>, the study page as{" "}
        <code>/subject/&lt;subject&gt;/chapter/&lt;chapter&gt;</code>, and a quiz as{" "}
        <code>/subject/&lt;subject&gt;/chapter/&lt;chapter&gt;/quiz</code>. A chapter number that is
        not in the Class 10 syllabus lands here too.
      </p>
      <p>
        <Link className="button" href="/">
          Back to the subject list
        </Link>
      </p>
    </>
  );
}
