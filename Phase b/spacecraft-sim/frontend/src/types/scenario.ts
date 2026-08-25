/**
 * Canonical scenario domain types for Phase B.
 *
 * These types are the single source of truth for spacecraft topology.
 * React Flow nodes/edges are DERIVED from these — not a parallel model.
 *
 * NO hazard_spread_probability — physical interpretation belongs to Phase A.
 * NO crew value weights.
 * NO simulation equations or threshold constants.
 */

export interface SpacecraftScenario {
  id?: string
  name: string
  missionPhase?: string
  modules: Record<string, ScenarioModule>
  connections: Record<string, ScenarioConnection>
  emergency: EmergencyConfig | null
}

export interface ScenarioModule {
  id: string
  name: string
  type: ModuleType
  pressure?: number | null
  oxygenFraction?: number | null
  crew: CrewMember[]
  equipment: Equipment[]
  position: { x: number; y: number }
}

export type ModuleType =
  | 'habitat'
  | 'storage'
  | 'life_support'
  | 'power'
  | 'propulsion'
  | 'other'

export interface CrewMember {
  id: string
  name: string
  role: string
  providesFunctions: string[]
}

export interface Equipment {
  id: string
  name: string
  type: string
  state: EquipmentState
  providesCapabilities: string[]
}

export type EquipmentState =
  | 'operational'
  | 'exposed_at_risk'
  | 'unavailable'
  | 'explicitly_failed'

export interface ScenarioConnection {
  id: string
  source: string // module id
  target: string // module id
  type: ConnectionType
  state: ConnectionState
  ventilationOn: boolean
  flowDirection: FlowDirection
  transferClass: TransferClass
}

export type ConnectionType = 'hatch' | 'imv' | 'leak' | 'other'
export type ConnectionState = 'open' | 'closed' | 'unknown'
export type FlowDirection =
  | 'source_to_target'
  | 'target_to_source'
  | 'bidirectional'
  | 'none'
  | 'unknown'
export type TransferClass = 'none' | 'low' | 'medium' | 'high' | 'unknown'

export interface EmergencyConfig {
  type: 'fire'
  affectedModuleId: string
  detected: boolean
  sourceProfileId?: string | null
}
