import { useCallback, useMemo, useRef, useState } from 'react';
import { ApiError, parseAudio, submitClaim } from './api';
import { DictationPanel } from './components/DictationPanel';
import { ChartPanel } from './components/ChartPanel';
import { NegotiationBanner } from './components/NegotiationBanner';
import { NegotiationRounds } from './components/NegotiationRounds';
import { AuditTrail } from './components/AuditTrail';
import { useSpeechDictation } from './hooks/useSpeechDictation';
import { useNegotiationPoll } from './hooks/useNegotiationPoll';
import type { ePCRChart } from './types';

export default function App() {
  const dictation = useSpeechDictation();
  const [chart, setChart] = useState<ePCRChart | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Stable per-chart idempotency key so retries dedupe to one workflow.
  const idempotencyKeyRef = useRef<string | null>(null);

  const { job, error: pollError } = useNegotiationPoll(jobId);

  const transcriptReady = dictation.transcript.trim().length > 0;
  const submitted = jobId !== null;
  const locked = parsing || chart !== null;

  const handleParse = useCallback(async () => {
    if (!transcriptReady || parsing) return;
    if (dictation.listening) dictation.stop();
    setParsing(true);
    setParseError(null);
    try {
      const { chart: parsed } = await parseAudio(dictation.transcript.trim());
      setChart(parsed);
    } catch (err) {
      setParseError(err instanceof ApiError ? err.message : 'Failed to parse dictation.');
    } finally {
      setParsing(false);
    }
  }, [dictation, parsing, transcriptReady]);

  const handleSubmit = useCallback(async () => {
    if (!chart || submitting || submitted) return;
    setSubmitting(true);
    setSubmitError(null);
    if (!idempotencyKeyRef.current) idempotencyKeyRef.current = crypto.randomUUID();
    try {
      const res = await submitClaim(chart, idempotencyKeyRef.current);
      setJobId(res.jobId);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Failed to submit claim.');
    } finally {
      setSubmitting(false);
    }
  }, [chart, submitting, submitted]);

  const handleReset = useCallback(() => {
    dictation.stop();
    dictation.reset();
    setChart(null);
    setParseError(null);
    setJobId(null);
    setSubmitError(null);
    idempotencyKeyRef.current = null;
  }, [dictation]);

  const primaryAction = useMemo(() => {
    if (!chart) {
      return (
        <button
          type="button"
          className="btn btn--primary"
          onClick={handleParse}
          disabled={!transcriptReady || parsing}
        >
          {parsing ? 'Structuring...' : 'Structure chart'}
        </button>
      );
    }
    if (!submitted) {
      return (
        <button
          type="button"
          className="btn btn--primary"
          onClick={handleSubmit}
          disabled={submitting}
        >
          {submitting ? 'Submitting...' : 'Submit claim'}
        </button>
      );
    }
    return null;
  }, [chart, handleParse, handleSubmit, parsing, submitted, submitting, transcriptReady]);

  return (
    <div className="app">
      <header className="app__header">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">◈</span>
          <div>
            <h1 className="brand__name">EMS Agent</h1>
            <p className="brand__tag">Ambient documentation - autonomous revenue recovery</p>
          </div>
        </div>
        <div className="app__actions">
          {primaryAction}
          {(chart || submitted) && (
            <button type="button" className="btn btn--ghost" onClick={handleReset}>
              New run
            </button>
          )}
        </div>
      </header>

      {submitError && <p className="app__alert" role="alert">{submitError}</p>}

      <main className="split">
        <DictationPanel dictation={dictation} locked={locked} />
        <ChartPanel chart={chart} parsing={parsing} error={parseError} />
      </main>

      {submitted && job && (
        <section className="negotiation" aria-label="Negotiation progress">
          <NegotiationBanner status={job.status} outcome={job.outcome} />
          {pollError && <p className="app__alert" role="alert">{pollError}</p>}
          <div className="negotiation__body">
            <NegotiationRounds rounds={job.rounds} />
            <AuditTrail entries={job.auditTrail} />
          </div>
        </section>
      )}
    </div>
  );
}
