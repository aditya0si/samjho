/** Small helpers with no dependencies of their own. */

/** Run `worker` over `items` with at most `limit` in flight. Order of results is preserved. */
export async function mapLimit<T, R>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let cursor = 0;
  const runners = new Array(Math.min(limit, items.length)).fill(null).map(async () => {
    for (;;) {
      const index = cursor++;
      if (index >= items.length) return;
      const item = items[index];
      if (item === undefined) return;
      results[index] = await worker(item, index);
    }
  });
  await Promise.all(runners);
  return results;
}

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** The fragment id a section is anchored with; citation chips link to the same string. */
export function sectionAnchor(sectionNo: string): string {
  return `section-${sectionNo.trim()}`;
}

export function formatRelativeTime(iso: string | null): string | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const seconds = Math.round((Date.now() - then.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return then.toISOString().slice(0, 10);
}
