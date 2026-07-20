import { describe, expect, it } from 'vitest';
import { statusMeta } from './statusMeta';
import type { JobStatus } from './types';

describe('statusMeta', () => {
  it('maps every JobStatus to a defined banner tone', () => {
    const statuses: JobStatus[] = [
      'PENDING',
      'DENIED',
      'APPEALING',
      'NEGOTIATING',
      'RESOLVED',
      'ESCALATED',
      'ERROR',
    ];
    for (const s of statuses) {
      const meta = statusMeta(s, null);
      expect(meta.label).toBeTruthy();
      expect(meta.detail).toBeTruthy();
      expect(['neutral', 'progress', 'danger', 'success', 'warning']).toContain(meta.tone);
    }
  });

  it('flags in-flight statuses as active and terminal ones as inactive', () => {
    expect(statusMeta('PENDING', null).active).toBe(true);
    expect(statusMeta('NEGOTIATING', null).active).toBe(true);
    expect(statusMeta('RESOLVED', 'OVERTURNED').active).toBe(false);
    expect(statusMeta('ESCALATED', 'ESCALATED').active).toBe(false);
    expect(statusMeta('ERROR', null).active).toBe(false);
  });

  it('reflects an overturned outcome in the resolved copy', () => {
    expect(statusMeta('RESOLVED', 'OVERTURNED').detail).toMatch(/overturned/i);
    expect(statusMeta('RESOLVED', 'OVERTURNED').tone).toBe('success');
  });

  it('shows the recovered dollar amount when resolved', () => {
    expect(statusMeta('RESOLVED', 'OVERTURNED', 900).detail).toMatch(/\$900 recovered/);
  });

  it('falls back to the plain resolved copy when no amount is given', () => {
    // Backward-compatible: callers that don't pass recoveredAmount (e.g. the
    // existing tests above) still get sensible copy, not "undefined".
    expect(statusMeta('RESOLVED', 'OVERTURNED').detail).not.toMatch(/\$/);
  });

  it('shows a partial-recovery message when escalated with a nonzero amount', () => {
    const detail = statusMeta('ESCALATED', 'ESCALATED', 500, 900).detail;
    expect(detail).toMatch(/\$500/);
    expect(detail).toMatch(/\$900/);
    expect(detail).toMatch(/human review/i);
  });

  it('keeps the original capped-negotiation copy when escalated with nothing recovered', () => {
    const detail = statusMeta('ESCALATED', 'ESCALATED', 0, 900).detail;
    expect(detail).not.toMatch(/\$/);
    expect(detail).toMatch(/capped without resolution/i);
  });
});
