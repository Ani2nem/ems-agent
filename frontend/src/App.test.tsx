import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import type { ePCRChart, JobState } from './types';

const CHART: ePCRChart = {
  incidentId: 'INC-2026-04837',
  patient: { age: 45, sex: 'M' },
  payer: 'AETNA',
  chiefComplaint: 'Chest pain',
  mechanismOfInjury: 'high-speed MVC with significant vehicular intrusion',
  vitals: { gcs: 15, bp: '120/80', hr: 98, spo2: 96, rr: 18 },
  interventions: ['18-gauge IV access', 'cardiac monitoring'],
  comorbidities: ['hypertension'],
  levelOfService: 'ALS',
  transportPriority: 'Priority 1 (emergent)',
  narrative: 'Patient transported emergent following an MVC.',
};

function jobState(over: Partial<JobState>): JobState {
  return { jobId: 'job-1', status: 'PENDING', rounds: [], outcome: null, auditTrail: [], ...over };
}

const okJson = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response;

describe('App negotiation flow', () => {
  beforeEach(() => {
    // Force the textarea fallback path (no Web Speech API in jsdom).
    vi.stubGlobal('crypto', { ...crypto, randomUUID: () => 'idem-key-1' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('parses a transcript, submits a claim, and renders banner transitions as it polls', async () => {
    const pollBodies = [
      jobState({ status: 'PENDING' }),
      jobState({
        status: 'DENIED',
        rounds: [
          {
            round: 1,
            actor: 'payer',
            type: 'denial',
            reasonCode: 'CO-50',
            content: 'Not medically necessary.',
            timestamp: '2026-07-18T10:00:00Z',
          },
        ],
        auditTrail: [{ ts: '2026-07-18T10:00:00Z', event: 'Denial intercepted' }],
      }),
      jobState({
        status: 'RESOLVED',
        outcome: 'OVERTURNED',
        rounds: [
          {
            round: 1,
            actor: 'payer',
            type: 'denial',
            reasonCode: 'CO-50',
            content: 'Not medically necessary.',
            timestamp: '2026-07-18T10:00:00Z',
          },
          {
            round: 2,
            actor: 'defense',
            type: 'appeal',
            reasonCode: null,
            content: 'Meets ALS criteria per policy.',
            timestamp: '2026-07-18T10:00:05Z',
          },
        ],
        auditTrail: [
          { ts: '2026-07-18T10:00:00Z', event: 'Denial intercepted' },
          { ts: '2026-07-18T10:00:05Z', event: 'Appeal filed' },
        ],
      }),
    ];
    let pollIdx = 0;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url === '/api/parse-audio') {
        return okJson({ chartId: 'c1', chart: CHART });
      }
      if (url === '/api/submit-claim' && init?.method === 'POST') {
        return okJson({ jobId: 'job-1', status: 'PENDING' }, 202);
      }
      if (url.startsWith('/api/submit-claim/')) {
        const body = pollBodies[Math.min(pollIdx, pollBodies.length - 1)];
        pollIdx += 1;
        return okJson(body);
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<App />);

    await user.type(
      screen.getByPlaceholderText(/type or paste the run dictation/i),
      'Forty five year old male, chest pain, MVC.',
    );
    await user.click(screen.getByRole('button', { name: /structure chart/i }));

    // Chart panel renders the structured fields.
    expect(await screen.findByText('INC-2026-04837')).toBeInTheDocument();
    expect(screen.getByText('45 yo M')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /submit claim/i }));

    // Banner walks PENDING -> DENIED -> RESOLVED as polling advances.
    expect(await screen.findByText(/submitting to clearinghouse/i)).toBeInTheDocument();
    expect(await screen.findByText(/claim denied/i)).toBeInTheDocument();

    expect(await screen.findByText(/revenue recovered/i)).toBeInTheDocument();

    // Both negotiation rounds and the audit trail are rendered.
    expect(screen.getByText(/meets als criteria per policy/i)).toBeInTheDocument();
    expect(screen.getByText('Appeal filed')).toBeInTheDocument();
  });

  it('surfaces a parse error without crashing', async () => {
    const fetchMock = vi.fn(async () => okJson({ error: 'Model unavailable' }, 502));
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByPlaceholderText(/type or paste the run dictation/i), 'test dictation');
    await user.click(screen.getByRole('button', { name: /structure chart/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/model unavailable/i));
  });
});
