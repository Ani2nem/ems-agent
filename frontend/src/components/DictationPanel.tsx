import type { SpeechDictation } from '../hooks/useSpeechDictation';

interface Props {
  dictation: SpeechDictation;
  /** Disable editing once the chart has been parsed / submitted. */
  locked: boolean;
}

/**
 * Left half of the split screen: the raw audio channel. Renders the live Web
 * Speech transcript with word-by-word interim results, or a plain textarea
 * fallback when the browser lacks the Speech API.
 */
export function DictationPanel({ dictation, locked }: Props) {
  const { supported, listening, transcript, interim, error, start, stop, setTranscript } = dictation;

  const wordCount = transcript.trim() ? transcript.trim().split(/\s+/).length : 0;

  return (
    <section className="panel panel--transcript" aria-label="Audio transcript">
      <header className="panel__head">
        <div className="panel__title">
          <span className="panel__eyebrow">Channel A</span>
          <h2>Ambient dictation</h2>
        </div>
        {supported ? (
          <button
            type="button"
            className={`mic-btn${listening ? ' mic-btn--live' : ''}`}
            onClick={listening ? stop : start}
            disabled={locked}
          >
            <span className="mic-btn__dot" aria-hidden="true" />
            {listening ? 'Stop dictation' : 'Start dictation'}
          </button>
        ) : (
          <span className="tag tag--muted">Manual entry</span>
        )}
      </header>

      {error && <p className="panel__alert" role="alert">{error}</p>}

      {supported ? (
        <div className={`transcript${locked ? ' transcript--locked' : ''}`} aria-live="polite">
          {transcript || interim ? (
            <p className="transcript__body">
              {transcript}
              {interim && <span className="transcript__interim"> {interim}</span>}
              {listening && <span className="transcript__caret" aria-hidden="true" />}
            </p>
          ) : (
            <p className="transcript__placeholder">
              Press <strong>Start dictation</strong> and describe the run. Words stream in live as
              you speak.
            </p>
          )}
        </div>
      ) : (
        <textarea
          className="transcript-input"
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder="Speech recognition is unavailable in this browser. Type or paste the run dictation here."
          disabled={locked}
          spellCheck={false}
        />
      )}

      <footer className="panel__foot">
        <span>{wordCount} words</span>
        {supported && listening && <span className="live-dot">Listening</span>}
      </footer>
    </section>
  );
}
