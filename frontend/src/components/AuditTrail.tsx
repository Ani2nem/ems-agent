import type { AuditEntry } from '../types';

interface Props {
  entries: AuditEntry[];
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** Compact chronological audit log rendered alongside the negotiation. */
export function AuditTrail({ entries }: Props) {
  if (entries.length === 0) return null;
  return (
    <div className="audit">
      <h3 className="audit__heading">Audit trail</h3>
      <ol className="audit__list">
        {entries.map((entry, i) => (
          <li key={i} className="audit__row">
            <time className="audit__ts">{formatTime(entry.ts)}</time>
            <span className="audit__event">{entry.event}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
