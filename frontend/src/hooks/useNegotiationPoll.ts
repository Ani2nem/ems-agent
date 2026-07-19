import { useEffect, useRef, useState } from 'react';
import { ApiError, getJob } from '../api';
import { TERMINAL_STATUSES, type JobState } from '../types';

const POLL_INTERVAL_MS = 1000;

export interface NegotiationPoll {
  job: JobState | null;
  /** Non-null when polling itself failed (network / unknown job). */
  error: string | null;
}

/**
 * Polls GET /api/submit-claim/{jobId} once per second until the job reaches a
 * terminal status (RESOLVED, ESCALATED, ERROR), then stops. Passing a null
 * jobId disables polling (before a claim is submitted).
 */
export function useNegotiationPoll(jobId: string | null): NegotiationPoll {
  const [job, setJob] = useState<JobState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setJob(null);
    setError(null);
    if (!jobId) return;

    let cancelled = false;

    const clear = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const poll = async () => {
      try {
        const next = await getJob(jobId);
        if (cancelled) return;
        setJob(next);
        setError(null);
        if (TERMINAL_STATUSES.has(next.status)) {
          clear();
          return;
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Failed to reach negotiation service.');
      }
      if (!cancelled) {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    };

    void poll();

    return () => {
      cancelled = true;
      clear();
    };
  }, [jobId]);

  return { job, error };
}
