import { useCallback, useEffect, useRef, useState } from 'react';

function getRecognitionCtor(): SpeechRecognitionConstructor | undefined {
  return window.SpeechRecognition ?? window.webkitSpeechRecognition;
}

export interface SpeechDictation {
  /** Whether the browser exposes the Web Speech API at all. */
  supported: boolean;
  /** True while the microphone is actively listening. */
  listening: boolean;
  /** Committed transcript text (final results only). */
  transcript: string;
  /** In-flight words not yet finalized by the recognizer. */
  interim: string;
  /** Last recognition error, surfaced to the UI. */
  error: string | null;
  start: () => void;
  stop: () => void;
  /** Replace the transcript (used by the textarea fallback). */
  setTranscript: (value: string) => void;
  reset: () => void;
}

/**
 * Live word-by-word dictation via the Web Speech API.
 *
 * Streams interim results as the user speaks and appends final results to the
 * committed transcript. When the API is unavailable, `supported` is false and
 * the caller renders a plain textarea fallback that writes through `setTranscript`.
 */
export function useSpeechDictation(): SpeechDictation {
  const [supported] = useState(() => getRecognitionCtor() !== undefined);
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  // Guards the auto-restart: browsers stop recognition on silence, but we want
  // continuous capture until the user explicitly stops.
  const wantListeningRef = useRef(false);

  useEffect(() => {
    const Ctor = getRecognitionCtor();
    if (!Ctor) return;

    const recognition = new Ctor();
    recognition.lang = 'en-US';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      let finalChunk = '';
      let interimChunk = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0].transcript;
        if (result.isFinal) finalChunk += text;
        else interimChunk += text;
      }
      if (finalChunk) {
        setTranscript((prev) => (prev ? `${prev.trimEnd()} ${finalChunk.trim()}` : finalChunk.trim()));
      }
      setInterim(interimChunk);
    };

    recognition.onerror = (event) => {
      // "no-speech"/"aborted" are benign; surface everything else.
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setError(event.error === 'not-allowed' ? 'Microphone permission denied.' : event.error);
        wantListeningRef.current = false;
      }
    };

    recognition.onend = () => {
      setInterim('');
      if (wantListeningRef.current) {
        try {
          recognition.start();
        } catch {
          // start() throws if called before the previous session fully ended; ignore.
        }
      } else {
        setListening(false);
      }
    };

    recognitionRef.current = recognition;
    return () => {
      wantListeningRef.current = false;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      recognition.abort();
      recognitionRef.current = null;
    };
  }, []);

  const start = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition || wantListeningRef.current) return;
    setError(null);
    wantListeningRef.current = true;
    setListening(true);
    try {
      recognition.start();
    } catch {
      // Already started; onresult will keep flowing.
    }
  }, []);

  const stop = useCallback(() => {
    wantListeningRef.current = false;
    setListening(false);
    recognitionRef.current?.stop();
    setInterim('');
  }, []);

  const reset = useCallback(() => {
    setTranscript('');
    setInterim('');
    setError(null);
  }, []);

  return {
    supported,
    listening,
    transcript,
    interim,
    error,
    start,
    stop,
    setTranscript,
    reset,
  };
}
