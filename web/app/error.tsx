"use client";

import { useEffect } from "react";

/**
 * Next.js error boundary for the whole app. It shows what happened and offers a retry — it never
 * claims the page is fine, and it never hides the fact that something broke.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Keep the error in the browser console for whoever is debugging; nothing is sent anywhere.
    console.error("samjho: unhandled error in a page", error);
  }, [error]);

  return (
    <>
      <h1>This page stopped working</h1>
      <p className="lede">
        An error was thrown while rendering. The message is below, as given — samjho does not
        decorate errors.
      </p>
      <section className="notice notice--error" role="alert">
        <p className="notice__title">{error.message || "No message was provided by the error."}</p>
        {error.digest ? (
          <p className="mono subtle">digest: {error.digest}</p>
        ) : null}
        <p>
          <button type="button" className="button" onClick={() => reset()}>
            Try this page again
          </button>
        </p>
      </section>
      <p className="subtle">
        If the API is down, the syllabus pages still work from the local copy; the chat and quiz
        pages need the API.
      </p>
    </>
  );
}
