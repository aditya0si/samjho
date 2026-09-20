"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

/**
 * Re-fetches the current server component tree. Used by the API-unreachable states so a student
 * whose API just came up does not have to guess that they should reload.
 */
export default function RetryButton({ label = "Try again" }: { label?: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [attempted, setAttempted] = useState(false);

  return (
    <button
      type="button"
      className="button button--secondary button--small"
      onClick={() => {
        setAttempted(true);
        startTransition(() => router.refresh());
      }}
      aria-busy={pending}
    >
      {pending ? "Checking…" : attempted ? "Try again" : label}
    </button>
  );
}
