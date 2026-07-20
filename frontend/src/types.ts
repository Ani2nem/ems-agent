// Mirror of docs/api-contract.md (FROZEN). Keep field shapes in lockstep with that doc.

export type Payer = 'AETNA' | 'MEDICARE';
export type LevelOfService = 'BLS' | 'ALS';

export interface Vitals {
  gcs: number | null;
  bp: string | null;
  hr: number | null;
  spo2: number | null;
  rr: number | null;
}

export interface ePCRChart {
  incidentId: string;
  patient: { age: number | null; sex: string };
  payer: Payer;
  chiefComplaint: string;
  mechanismOfInjury: string;
  vitals: Vitals;
  interventions: string[];
  comorbidities: string[];
  levelOfService: LevelOfService;
  transportPriority: string;
  narrative: string;
  billedAmount: number;
}

export type NegotiationActor = 'payer' | 'defense';
export type NegotiationType = 'denial' | 'appeal' | 'ruling';
export type ReasonCode = 'CO-50' | 'CO-16' | 'CO-11' | 'DOWNGRADE' | null;

export interface NegotiationRound {
  round: number;
  actor: NegotiationActor;
  type: NegotiationType;
  reasonCode: ReasonCode;
  content: string;
  timestamp: string;
}

export interface AuditEntry {
  ts: string;
  event: string;
}

export type JobStatus =
  | 'PENDING'
  | 'DENIED'
  | 'APPEALING'
  | 'NEGOTIATING'
  | 'RESOLVED'
  | 'ESCALATED'
  | 'ERROR';

export type Outcome = 'OVERTURNED' | 'ESCALATED' | null;

export const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>([
  'RESOLVED',
  'ESCALATED',
  'ERROR',
]);

export interface ParseAudioResponse {
  chartId: string;
  chart: ePCRChart;
}

export interface SubmitClaimResponse {
  jobId: string;
  status: JobStatus;
}

export interface JobState {
  jobId: string;
  status: JobStatus;
  rounds: NegotiationRound[];
  outcome: Outcome;
  recoveredAmount: number | null;
  auditTrail: AuditEntry[];
}
