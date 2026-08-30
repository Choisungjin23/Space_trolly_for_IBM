/**
 * Phase C advisor types — mirror phase_c/contracts/findings.py.
 *
 * The frontend depends only on these shapes, never on agent internals.
 */

export type Basis = 'SIMULATION_FACT' | 'EVIDENCE' | 'INFERENCE' | 'ASSUMPTION'
export type Confidence = 'HIGH' | 'MEDIUM' | 'LOW'
export type Severity = 'BLOCKER' | 'MAJOR' | 'MINOR'

export interface Claim {
  statement: string
  basis: Basis
  refs: string[]
  confidence: Confidence
}

export interface AgentFinding {
  agent: string
  action_id: string | null
  claims: Claim[]
  concerns: string[]
  open_questions: string[]
}

export interface EvidenceCitation {
  source_id: string
  title: string
  locator: string
  retrieved_on: string
  url: string
}

export interface EvidenceAnswer {
  query: string
  claim: string
  citation: EvidenceCitation
  applicability: string
  limits: string
}

export interface GroundingViolation {
  agent: string
  action_id: string | null
  rule: string
  detail: string
  claim_statement: string | null
  severity: Severity
}

export interface CriticIssue {
  severity: Severity
  target_agent: string
  target_claim_ref: string | null
  issue: string
  suggested_correction: string | null
}

export interface CriticReview {
  issues: CriticIssue[]
  grounding_violations: GroundingViolation[]
  unexamined_actions: string[]
}

export interface Tradeoff {
  versus_action_id: string
  gives_up: string
  gains: string
}

export interface Recommendation {
  recommended_action_id: string
  rationale: Claim[]
  tradeoffs: Tradeoff[]
  dissent: string[]
  uncertainty: string[]
  human_decision_required: boolean
}

export interface DecisionPackage {
  scenario_digest: string
  findings: AgentFinding[]
  evidence: EvidenceAnswer[]
  critic: CriticReview
  recommendation: Recommendation | null
  provenance: Record<string, unknown>
}

export interface AdvisorStatus {
  available: boolean
  detail: string
}

export interface AnalyzeRequest {
  scenario: unknown
  emergency: unknown
  focusActionId?: string | null
  samples?: number
  seed?: number | null
}
