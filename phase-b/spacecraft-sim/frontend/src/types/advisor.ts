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
  model_proposed_action_id: string | null
  policy_override_applied: boolean
  policy_id: string | null
}

export type EthicsStatus = 'POLICY_CONSISTENT' | 'REVIEW_REQUIRED' | 'BLOCKED'
export type PolicyCheckStatus = 'PASS' | 'REVIEW' | 'BLOCK'

export interface PolicyCheck {
  rule_id: string
  status: PolicyCheckStatus
  summary: string
  refs: string[]
}

export interface ActionEthicsAssessment {
  action_id: string
  eligible: boolean
  expected_returnees: number
  expected_survivors: number
  minimum_crew_survival_probability: number | null
  abandoned_crew_count: number
  trapped_crew_count: number
  maximum_smac_dose_fraction: number | null
  smac_exceeded_module_count: number
  hazard_reached_module_count: number
  affected_crew_ids: string[]
  policy_checks: PolicyCheck[]
  co_recommended: boolean
}

export interface TieBreakStep {
  criterion: string
  direction: 'MAXIMIZE' | 'MINIMIZE'
  best_value: number
  tie_margin: number
  remaining_action_ids: string[]
  explanation: string
}

export interface EthicalAssessment {
  policy_id: string
  policy_version: string
  status: EthicsStatus
  selected_action_id: string | null
  co_recommended_action_ids: string[]
  selection_basis: string
  action_assessments: ActionEthicsAssessment[]
  tie_break_steps: TieBreakStep[]
  sources: EvidenceCitation[]
  limitations: string[]
  human_decision_required: boolean
}

export interface DecisionPackage {
  scenario_digest: string
  findings: AgentFinding[]
  evidence: EvidenceAnswer[]
  critic: CriticReview
  recommendation: Recommendation | null
  ethical_assessment: EthicalAssessment | null
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
