/**
 * The student id used for the progress endpoints. It is generated in the browser and kept in
 * localStorage — there is no account system in v1, and this is stated in the UI rather than
 * implying a login that does not exist.
 */

const KEY = "samjho.student_id";

export function getStudentId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function ensureStudentId(): string | null {
  if (typeof window === "undefined") return null;
  const existing = getStudentId();
  if (existing) return existing;
  const generated =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? `local-${crypto.randomUUID()}`
      : `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  try {
    window.localStorage.setItem(KEY, generated);
    return generated;
  } catch {
    return null;
  }
}
