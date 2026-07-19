import type {
  ePCRChart,
  JobState,
  ParseAudioResponse,
  SubmitClaimResponse,
} from './types';

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch (cause) {
    throw new ApiError(0, `Network error contacting ${path}`, { cause });
  }

  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const message =
      (body && typeof body.error === 'string' && body.error) ||
      `Request to ${path} failed (${res.status})`;
    throw new ApiError(res.status, message);
  }
  return body as T;
}

export function parseAudio(transcript: string): Promise<ParseAudioResponse> {
  return request<ParseAudioResponse>('/api/parse-audio', {
    method: 'POST',
    body: JSON.stringify({ transcript }),
  });
}

export function submitClaim(
  chart: ePCRChart,
  idempotencyKey: string,
): Promise<SubmitClaimResponse> {
  return request<SubmitClaimResponse>('/api/submit-claim', {
    method: 'POST',
    body: JSON.stringify({ chart, idempotencyKey }),
  });
}

export function getJob(jobId: string): Promise<JobState> {
  return request<JobState>(`/api/submit-claim/${encodeURIComponent(jobId)}`);
}
