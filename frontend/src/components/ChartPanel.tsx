import type { ReactNode } from 'react';
import type { ePCRChart } from '../types';

interface Props {
  chart: ePCRChart | null;
  parsing: boolean;
  error: string | null;
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="field">
      <dt className="field__label">{label}</dt>
      <dd className="field__value">{value ?? <span className="field__empty">-</span>}</dd>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  if (items.length === 0) return <span className="field__empty">None recorded</span>;
  return (
    <ul className="chip-list">
      {items.map((item, i) => (
        <li key={i} className="chip">{item}</li>
      ))}
    </ul>
  );
}

/**
 * Right half of the split screen: the structured ePCR chart the parser
 * extracted from the transcript. NEMSIS-inspired sections rendered as a clean
 * clinical readout.
 */
export function ChartPanel({ chart, parsing, error }: Props) {
  return (
    <section className="panel panel--chart" aria-label="Structured ePCR chart">
      <header className="panel__head">
        <div className="panel__title">
          <span className="panel__eyebrow">Channel B</span>
          <h2>Structured ePCR</h2>
        </div>
        {chart && <span className="tag tag--id">{chart.incidentId}</span>}
      </header>

      {error && <p className="panel__alert" role="alert">{error}</p>}

      {!chart && !error && (
        <div className="chart-empty">
          {parsing ? (
            <p className="chart-empty__loading">
              <span className="spinner" aria-hidden="true" /> Extracting structured fields...
            </p>
          ) : (
            <p>The parsed chart will appear here once the dictation is structured.</p>
          )}
        </div>
      )}

      {chart && (
        <div className="chart">
          <div className="chart__group">
            <h3 className="chart__heading">Encounter</h3>
            <dl className="field-grid">
              <Field label="Patient" value={`${chart.patient.age ?? 'Unknown'} yo ${chart.patient.sex}`} />
              <Field label="Payer" value={<span className="tag tag--payer">{chart.payer}</span>} />
              <Field label="Level of service" value={<span className="tag tag--los">{chart.levelOfService}</span>} />
              <Field label="Transport priority" value={chart.transportPriority} />
            </dl>
          </div>

          <div className="chart__group">
            <h3 className="chart__heading">Presentation</h3>
            <dl className="field-grid field-grid--wide">
              <Field label="Chief complaint" value={chart.chiefComplaint} />
              <Field label="Mechanism of injury" value={chart.mechanismOfInjury} />
            </dl>
          </div>

          <div className="chart__group">
            <h3 className="chart__heading">Vitals</h3>
            <dl className="field-grid field-grid--vitals">
              <Field label="GCS" value={chart.vitals.gcs} />
              <Field label="BP" value={chart.vitals.bp} />
              <Field label="HR" value={chart.vitals.hr} />
              <Field label="SpO2" value={chart.vitals.spo2 != null ? `${chart.vitals.spo2}%` : null} />
              <Field label="RR" value={chart.vitals.rr} />
            </dl>
          </div>

          <div className="chart__group">
            <h3 className="chart__heading">Interventions</h3>
            <List items={chart.interventions} />
          </div>

          <div className="chart__group">
            <h3 className="chart__heading">Comorbidities</h3>
            <List items={chart.comorbidities} />
          </div>

          <div className="chart__group">
            <h3 className="chart__heading">Narrative</h3>
            <p className="chart__narrative">{chart.narrative}</p>
          </div>
        </div>
      )}
    </section>
  );
}
