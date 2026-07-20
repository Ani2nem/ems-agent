import { statusMeta } from '../statusMeta';
import type { JobStatus, Outcome } from '../types';

interface Props {
  status: JobStatus;
  outcome: Outcome;
  recoveredAmount?: number | null;
  billedAmount?: number;
}

/**
 * The status banner. Reads the current JobStatus and animates between tones as
 * the negotiation progresses (progress -> danger -> success, etc). The `key` on
 * the root drives the enter transition on every status change.
 */
export function NegotiationBanner({ status, outcome, recoveredAmount, billedAmount }: Props) {
  const meta = statusMeta(status, outcome, recoveredAmount, billedAmount);
  return (
    <div
      key={status}
      className={`banner banner--${meta.tone}${meta.active ? ' banner--active' : ''}`}
      role="status"
      aria-live="polite"
    >
      <span className="banner__pulse" aria-hidden="true" />
      <div className="banner__text">
        <strong className="banner__label">{meta.label}</strong>
        <span className="banner__detail">{meta.detail}</span>
      </div>
      <span className="banner__status-code">{status}</span>
    </div>
  );
}
