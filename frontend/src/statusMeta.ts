import type { JobStatus, Outcome } from './types';

export type Tone = 'neutral' | 'progress' | 'danger' | 'success' | 'warning';

export interface StatusMeta {
  label: string;
  detail: string;
  tone: Tone;
  /** Whether the workflow is still advancing (drives the pulsing indicator). */
  active: boolean;
}

/**
 * Maps a raw JobStatus (+ terminal outcome) to the banner's label, supporting
 * copy, and visual tone. Single source of truth for the status → UI mapping
 * described in docs/api-contract.md § "Status progression".
 */
export function statusMeta(status: JobStatus, outcome: Outcome): StatusMeta {
  switch (status) {
    case 'PENDING':
      return {
        label: 'Submitting to clearinghouse',
        detail: 'Claim in flight - awaiting payer adjudication.',
        tone: 'progress',
        active: true,
      };
    case 'DENIED':
      return {
        label: 'Claim denied',
        detail: 'Payer returned a denial. Defense agent engaging.',
        tone: 'danger',
        active: true,
      };
    case 'APPEALING':
      return {
        label: 'Appeal filed',
        detail: 'Defense agent submitted a policy-backed appeal.',
        tone: 'success',
        active: true,
      };
    case 'NEGOTIATING':
      return {
        label: 'Under re-review',
        detail: 'Round 2 negotiation in progress.',
        tone: 'progress',
        active: true,
      };
    case 'RESOLVED':
      return {
        label: 'Revenue recovered',
        detail: outcome === 'OVERTURNED' ? 'Denial overturned - claim approved.' : 'Claim resolved.',
        tone: 'success',
        active: false,
      };
    case 'ESCALATED':
      return {
        label: 'Escalated - human review',
        detail: 'Negotiation capped without resolution. Routed to a human biller.',
        tone: 'warning',
        active: false,
      };
    case 'ERROR':
      return {
        label: 'Workflow error',
        detail: 'Something went wrong. Safe to retry the submission.',
        tone: 'danger',
        active: false,
      };
  }
}
