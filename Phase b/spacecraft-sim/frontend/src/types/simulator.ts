/**
 * Simulator API request/response types for Phase B.
 *
 * These mirror the Pydantic schemas in backend/app/api/schemas.py.
 * The frontend depends only on these shapes — not on simulator internals.
 *
 * sourceLabel in SimulationResponse identifies whether results came from
 * MockSimulatorAdapter (Phase B) or PhaseASimulatorAdapter (future).
 */

import type { SpacecraftScenario, EmergencyConfig } from './scenario'

// ─── Request ──────────────────────────────────────────────────────────────

export interface SimulationRequest {
  scenario: SpacecraftScenario
  emergency: EmergencyConfig
  actions: string[] | null
  runs: number
  seed: number | null
}

// ─── Action spec ──────────────────────────────────────────────────────────

export interface ActionOperation {
  type:
    | 'close_connection'
    | 'isolate_module'
    | 'shutdown_ventilation'
    | 'evacuate_crew'
    | 'power_down_equipment'
    | 'do_nothing'
  targetId: string
}

export interface ActionSpec {
  id: string
  label: string
  description: string
  operations: ActionOperation[]
}

// ─── Simulation result ────────────────────────────────────────────────────

export interface HazardOutcome {
  modulesReached: number
  modulesReachedIds: string[]
  containedInNScenarios: number
  totalScenarios: number
}

export interface CrewMemberOutcome {
  status: string
  exposureExampleSeconds: number
}

export interface CrewOutcomeSummary {
  allEvacuatedCount: number
  anyTrappedCount: number
  totalScenarios: number
  byCrewMember?: Record<string, CrewMemberOutcome>
}

export interface EquipmentItemOutcome {
  name: string
  state: string
}

export interface EquipmentOutcomeSummary {
  byEquipmentId: Record<string, EquipmentItemOutcome>
}

export type CapabilityStatus = 'available' | 'degraded' | 'unavailable'

export interface CapabilityOutcomeSummary {
  byCapability: Record<string, CapabilityStatus>
}

export interface CriticalFunctionEntry {
  providersAvailable: number
  totalProviders: number
  status: 'nominal' | 'single_provider' | 'no_provider'
}

export interface CriticalFunctionSummary {
  byFunction: Record<string, CriticalFunctionEntry>
}

export interface UncertaintySummary {
  note: string
}

export interface TrajectoryStep {
  stepIndex: number
  timeSeconds: number
  moduleStates: Record<string, { hazardSeverity: number; crewPresent: number }>
  events: string[]
}

export interface ExampleTrajectory {
  seed: number
  steps: TrajectoryStep[]
}

export interface ActionSimulationResult {
  actionId: string
  hazard: HazardOutcome
  crew: CrewOutcomeSummary
  equipment: EquipmentOutcomeSummary
  capabilities: CapabilityOutcomeSummary
  criticalFunctions: CriticalFunctionSummary
  uncertaintySummary?: UncertaintySummary
  exampleTrajectory?: ExampleTrajectory
}

export interface SimulationResponse {
  generatedActions: ActionSpec[]
  results: ActionSimulationResult[]
  simulatedHorizonSeconds: number
  runsRequested: number
  seed: number | null
  sourceLabel: string
}

// ─── Template ─────────────────────────────────────────────────────────────

export interface TemplateSummary {
  id: string
  name: string
  description: string
}
