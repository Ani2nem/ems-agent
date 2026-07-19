import type { NegotiationRound } from '../types';

interface Props {
  rounds: NegotiationRound[];
}

function actorLabel(round: NegotiationRound): string {
  return round.actor === 'payer' ? 'Payer' : 'Defense agent';
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/**
 * The adversarial transcript: payer denials vs. defense appeals/rulings,
 * appended in order as the workflow advances.
 */
export function NegotiationRounds({ rounds }: Props) {
  if (rounds.length === 0) return null;
  return (
    <ol className="rounds">
      {rounds.map((round, i) => (
        <li key={`${round.round}-${round.actor}-${i}`} className={`round round--${round.actor}`}>
          <div className="round__head">
            <span className="round__actor">{actorLabel(round)}</span>
            <span className={`round__type round__type--${round.type}`}>{round.type}</span>
            {round.reasonCode && <span className="round__code">{round.reasonCode}</span>}
            <span className="round__meta">Round {round.round}</span>
            <span className="round__time">{formatTime(round.timestamp)}</span>
          </div>
          <p className="round__content">{round.content}</p>
        </li>
      ))}
    </ol>
  );
}
