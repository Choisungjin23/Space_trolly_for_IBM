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
      return { scenario: { ...s.scenario, modules, connections, emergency } }
    }),

  updateModule: (id, patch) =>
    set((s) => {
      const existing = s.scenario.modules[id]
      if (!existing) return s
      return {
        scenario: {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [id]: { ...existing, ...patch },
          },
        },
      }
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
    }
    set((s) => ({
      scenario: {
        ...s.scenario,
        connections: { ...s.scenario.connections, [id]: connection },
      },
    }))
    return id
  },

  removeConnection: (id) =>
    set((s) => {
      const connections = { ...s.scenario.connections }
      delete connections[id]
      return { scenario: { ...s.scenario, connections } }
    }),

  updateConnection: (id, patch) =>
    set((s) => {
      const existing = s.scenario.connections[id]
      if (!existing) return s
      return {
        scenario: {
          ...s.scenario,
          connections: {
            ...s.scenario.connections,
            [id]: { ...existing, ...patch },
          },
        },
      }
    }),

  setEmergency: (config) =>
    set((s) => ({ scenario: { ...s.scenario, emergency: config } })),

  addCrewMember: (moduleId, crew) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      const newCrew = { ...crew, id: crew.id || newCrewId() }
      return {
        scenario: {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: { ...mod, crew: [...mod.crew, newCrew] },
          },
        },
      }
    }),

  updateCrewMember: (moduleId, crewId, patch) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      return {
        scenario: {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: {
              ...mod,
              crew: mod.crew.map((c) => (c.id === crewId ? { ...c, ...patch } : c)),
            },
          },
        },
      }
    }),

  removeCrewMember: (moduleId, crewId) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      return {
        scenario: {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: {
              ...mod,
              crew: mod.crew.filter((c) => c.id !== crewId),
            },
          },
        },
      }
    }),

  addEquipment: (moduleId, equipment) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      const newEq = { ...equipment, id: equipment.id || newEquipmentId() }
      return {
        scenario: {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: { ...mod, equipment: [...mod.equipment, newEq] },
          },
        },
      }
    }),

  updateEquipment: (moduleId, equipmentId, patch) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      return {
        scenario: {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: {
              ...mod,
              equipment: mod.equipment.map((e) =>
                e.id === equipmentId ? { ...e, ...patch } : e
              ),
            },
          },
        },
      }
    }),

  removeEquipment: (moduleId, equipmentId) =>
    set((s) => {
      const mod = s.scenario.modules[moduleId]
      if (!mod) return s
      return {
        scenario: {
          ...s.scenario,
          modules: {
            ...s.scenario.modules,
            [moduleId]: {
              ...mod,
              equipment: mod.equipment.filter((e) => e.id !== equipmentId),
            },
          },
        },
      }
    }),

  loadScenario: (scenario) => set({ scenario }),

  resetScenario: () => set({ scenario: emptyScenario() }),
}))
