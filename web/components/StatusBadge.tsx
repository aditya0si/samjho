/**
 * Ingest status of one chapter. `null` means "we could not find out" — which is a different thing
 * from "not ingested", and the label says so.
 */
export default function StatusBadge({ ingested }: { ingested: boolean | null }) {
  if (ingested === true) {
    return <span className="badge badge--ok">Text ingested</span>;
  }
  if (ingested === false) {
    return <span className="badge badge--warn">Text not ingested</span>;
  }
  return <span className="badge badge--plain">Ingest status unknown</span>;
}
