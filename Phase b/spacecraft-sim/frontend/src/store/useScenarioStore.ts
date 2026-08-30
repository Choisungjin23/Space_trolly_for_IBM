/**
 * Scenario store — canonical source of truth for spacecraft topology.
 *
 * React Flow nodes/edges are DERIVED from this store.
 * When module positions change (via React Flow drag), only `position` is updated here.
 * No simulation logic belongs here.
 */

import { create } from 'zustand'
import type {
  SpacecraftScenario,
  ScenarioModule,
  ScenarioConnection,
  EmergencyConfig,
  CrewMember,
  Equipment,
} from '../types/scenario'
import {
  autoSizeResourceSources,
  cleanEquipment,
  normalizeConnectionUtilities,
} from '../domain/resourceSizing'
import { recommendedEscapeRoute } from '../domain/escapeRouting'

interface ScenarioState {
  scenario: SpacecraftScenario
  // ── Mutations ──────────────────────────────────────────────────────────────
  setScenarioName: (name: string) => void
  setMissionPhase: (phase: string) => void
  addModule: (position: { x: number; y: number }) => string
  removeModule: (id: string) => void
  updateModule: (id: string, patch: Partial<Omit<ScenarioModule, 'id'>>) => void
  updateModulePosition: (id: string, position: { x: number; y: number }) => void
  addConnection: (source: string, target: string) => string
  removeConnection: (id: string) => void
  updateConnection: (id: string, patch: Partial<Omit<ScenarioConnection, 'id' | 'source' | 'target'>>) => void
  setEmergency: (config: EmergencyConfig | null) => void
  advanceEmergencyVisual: () => void
  addCrewMember: (moduleId: string, crew: CrewMember) => void
  updateCrewMember: (moduleId: string, crewId: string, patch: Partial<CrewMember>) => void
  removeCrewMember: (moduleId: string, crewId: string) => void
  addEquipment: (moduleId: string, equipment: Equipment) => void
  updateEquipment: (moduleId: string, equipmentId: string, patch: Partial<Equipment>) => void
  removeEquipment: (moduleId: string, equipmentId: string) => void
  loadScenario: (scenario: SpacecraftScenario) => void
  resetScenario: () => void
}

let moduleCounter = 0

function newModuleId(): string {
  return `mod-${crypto.randomUUID().slice(0, 8)}`
}

function newConnectionId(): string {
  return `conn-${crypto.randomUUID().slice(0, 8)}`
}

function newCrewId(): string {
  return `crew-${crypto.randomUUID().slice(0, 8)}`
}

function newEquipmentId(): string {
  return `eq-${crypto.randomUUID().slice(0, 8)}`
}

const emptyScenario = (): SpacecraftScenario => ({
  name: 'New Spacecraft',
  modules: {},
  connections: {},
  emergency: null,
})

function withResourceDefaults(scenario: SpacecraftScenario): SpacecraftScenario {
  return {
    ...scenario,
    modules: Object.fromEntries(
      Object.entries(scenario.modules).map(([id, module]) => [
        id,
        {
          ...module,
          oxygenFraction: module.oxygenFraction ?? 0.25,
          powerLevelW: module.powerLevelW ?? 10,
          powerConsumptionW: module.powerConsumptionW ?? 10,
          maxPowerOutputW: module.maxPowerOutputW ?? 0,
          waterStoredKg: module.waterStoredKg ?? 0,
          waterCapacityKg: module.waterCapacityKg ?? 0,
          suppliesAir: module.suppliesAir ?? false,
          suppliesWater: module.suppliesWater ?? false,
          maxAirOutputPercentPerMin: module.maxAirOutputPercentPerMin ?? 0,
          maxWaterOutputKgPerMin: module.maxWaterOutputKgPerMin ?? 0,
          waterRecoveryEfficiency: module.waterRecoveryEfficiency ?? 0.98,
          disruptionLevel: module.disruptionLevel ?? 0,
          equipment: (module.equipment ?? []).map(cleanEquipment),
        },
      ])
    ),
    connections: Object.fromEntries(
      Object.entries(scenario.connections).map(([id, connection]) => [
        id,
        normalizeConnectionUtilities(connection),
      ])
    ),
  }
}

export const useScenarioStore = create<ScenarioState>()((set, get) => ({
  scenario: emptyScenario(),

  setScenarioName: (name) =>
    set((s) => ({ scenario: { ...s.scenario, name } })),

  setMissionPhase: (phase) =>
    set((s) => ({ scenario: { ...s.scenario, missionPhase: phase } })),

  addModule: (position) => {
    const id = newModuleId()
    moduleCounter++
    const module: ScenarioModule = {
      id,
      name: `Module ${moduleCounter}`,
      type: 'other',
      oxygenFraction: 0.25,
      powerLevelW: 10,
      powerConsumptionW: 10,
      maxPowerOutputW: 0,
      waterStoredKg: 0,
      waterCapacityKg: 0,
      suppliesAir: false,
      suppliesWater: false,
      maxAirOutputPercentPerMin: 0,
      maxWaterOutputKgPerMin: 0,
      waterRecoveryEfficiency: 0.98,
      disruptionLevel: 0,
      crew: [],
      equipment: [],
      position,
    }
    set((s) => ({
      scenario: {
        ...s.scenario,
        modules: { ...s.scenario.modules, [id]: module },
      },
    }))
    return id
  },

  removeModule: (id) =>
    set((s) => {
      const modules = { ...s.scenario.modules }
      delete modules[id]
      const connections = Object.fromEntries(
        Object.entries(s.scenario.connections).filter(
          ([, c]) => c.source !== id && c.target !== id
        )
      )
      const emergency =
        s.scenario.emergency?.affectedModuleId === id ? null : s.scenario.emergency
      return {
        scenario: autoSizeResourceSources({
          ...s.scenario, modules, connections, emergency,
        }),
      }
    }),

  updateModule: (id, patch) =>
    set((s) => {
      const existing = s.scenario.modules[id]
      if (!existing) return s
      const scenario = {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [id]: { ...existing, ...patch },
          },
      }
      const isManualSourceValue = [
        'powerLevelW', 'maxPowerOutputW', 'maxAirOutputPercentPerMin',
        'maxWaterOutputKgPerMin',
      ].some((key) => key in patch)
      return { scenario: isManualSourceValue ? scenario : autoSizeResourceSources(scenario) }
    }),

  updateModulePosition: (id, position) => {
    const existing = get().scenario.modules[id]
    if (!existing) return
    set((s) => ({
      scenario: {
        ...s.scenario,
        modules: {
          ...s.scenario.modules,
          [id]: { ...existing, position },
        },
      },
    }))
  },

  addConnection: (source, target) => {
    const id = newConnectionId()
    const connection: ScenarioConnection = {
      id,
      source,
      target,
      type: 'hatch',
      state: 'open',
      ventilationOn: false,
      flowDirection: 'bidirectional',
      transferClass: 'medium',
      powerLineOn: true,
      airLineOn: true,
      waterLineOn: true,
      baseConnectivity: 100,
      connectivity: 100,
      powerTransferFactor: 1,
    }
    set((s) => ({
      scenario: autoSizeResourceSources({
        ...s.scenario,
        connections: { ...s.scenario.connections, [id]: connection },
      }),
    }))
    return id
  },

  removeConnection: (id) =>
    set((s) => {
      const connections = { ...s.scenario.connections }
      delete connections[id]
      return { scenario: autoSizeResourceSources({ ...s.scenario, connections }) }
    }),

  updateConnection: (id, patch) =>
    set((s) => {
      const existing = s.scenario.connections[id]
      if (!existing) return s
      const scenario = {
          ...s.scenario,
          connections: {
            ...s.scenario.connections,
            [id]: normalizeConnectionUtilities({ ...existing, ...patch }),
          },
      }
      return { scenario: autoSizeResourceSources(scenario) }
    }),

  setEmergency: (config) =>
    set((s) => {
      const resetConnections = Object.fromEntries(
        Object.entries(s.scenario.connections).map(([id, connection]) => [id, {
          ...connection,
          connectivity: connection.baseConnectivity,
          powerTransferFactor: 1,
        }])
      )
      if (!config) {
        return { scenario: { ...s.scenario, connections: resetConnections, emergency: null } }
      }
      const connections = Object.fromEntries(
        Object.entries(resetConnections).map(([id, connection]) => {
          const adjacent =
            connection.type === 'hatch' &&
            (connection.source === config.affectedModuleId || connection.target === config.affectedModuleId)
          if (!adjacent) return [id, connection]
          return [id, {
            ...connection,
            connectivity: Math.floor(Math.random() * 50) + 1,
            powerTransferFactor: config.type === 'electronic_short'
              ? (Math.floor(Math.random() * 16) + 5) / 100
              : 1,
          }]
        })
      )
      const scenarioWithDamage = { ...s.scenario, connections, emergency: config }
      const recommended = recommendedEscapeRoute(
        scenarioWithDamage,
        config.affectedModuleId,
      )
      const emergency = config.escapeTarget || !recommended
        ? config
        : {
            ...config,
            escapeTarget: {
              connectionId: recommended.connectionId,
              fromModuleId: recommended.fromModuleId,
              toModuleId: recommended.toModuleId,
              selection: 'recommended' as const,
            },
          }
      return { scenario: { ...scenarioWithDamage, emergency } }
    }),

  advanceEmergencyVisual: () =>
    set((s) => {
      const emergency = s.scenario.emergency
      if (!emergency) return s
      const affected = s.scenario.modules[emergency.affectedModuleId]
      if (!affected) return s
      const oxygenLoss = emergency.type === 'fire' ? 0.00025 : 0.00005
      const nextOxygen = Math.max(0, (affected.oxygenFraction ?? 0.25) - oxygenLoss)
      const airRatio = Math.max(0.01, Math.min(1, nextOxygen / 0.25))
      const modules = {
        ...s.scenario.modules,
        [affected.id]: { ...affected, oxygenFraction: nextOxygen },
      }
      const connections = Object.fromEntries(
        Object.entries(s.scenario.connections).map(([id, connection]) => {
          const adjacent = connection.type === 'hatch' &&
            (connection.source === affected.id || connection.target === affected.id)
          if (!adjacent) return [id, connection]
          const feedbackLoss = (emergency.type === 'fire' ? 0.1 : 0.04) + (1 - airRatio) * 0.3
          return [id, {
            ...connection,
            connectivity: Math.max(1, Math.min(
              connection.connectivity - feedbackLoss,
              connection.baseConnectivity * airRatio,
            )),
          }]
        })
      )
      return { scenario: { ...s.scenario, modules, connections } }
    }),

  addCrewMember: (moduleId, crew) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      const newCrew = { ...crew, id: crew.id || newCrewId() }
      const scenario = {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: { ...mod, crew: [...mod.crew, newCrew] },
          },
      }
      return { scenario: autoSizeResourceSources(scenario) }
    }),

  updateCrewMember: (moduleId, crewId, patch) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      const scenario = {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: {
              ...mod,
              crew: mod.crew.map((c) => (c.id === crewId ? { ...c, ...patch } : c)),
            },
          },
      }
      return { scenario: autoSizeResourceSources(scenario) }
    }),

  removeCrewMember: (moduleId, crewId) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      const scenario = {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: {
              ...mod,
              crew: mod.crew.filter((c) => c.id !== crewId),
            },
          },
      }
      return { scenario: autoSizeResourceSources(scenario) }
    }),

  addEquipment: (moduleId, equipment) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      const newEq = cleanEquipment({ ...equipment, id: equipment.id || newEquipmentId() })
      const scenario = {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: { ...mod, equipment: [...mod.equipment, newEq] },
          },
      }
      return { scenario: autoSizeResourceSources(scenario) }
    }),

  updateEquipment: (moduleId, equipmentId, patch) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      const scenario = {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: {
              ...mod,
              equipment: mod.equipment.map((e) =>
                e.id === equipmentId ? cleanEquipment({ ...e, ...patch }) : e
              ),
            },
          },
      }
      return { scenario: autoSizeResourceSources(scenario) }
    }),

  removeEquipment: (moduleId, equipmentId) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      const scenario = {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: {
              ...mod,
              equipment: mod.equipment.filter((e) => e.id !== equipmentId),
            },
          },
      }
      return { scenario: autoSizeResourceSources(scenario) }
    }),

  loadScenario: (scenario) =>
    set({ scenario: autoSizeResourceSources(withResourceDefaults(scenario)) }),

  resetScenario: () => set({ scenario: emptyScenario() }),
}))
