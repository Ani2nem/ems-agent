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
});
