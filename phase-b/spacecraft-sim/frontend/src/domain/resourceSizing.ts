import type {
  Equipment,
  ScenarioConnection,
  ScenarioModule,
  SpacecraftScenario,
} from '../types/scenario'

export const BASE_MODULE_POWER_W = 10
export const AIR_OUTPUT_POWER_W = 25
export const WATER_OUTPUT_POWER_W = 20
export const CREW_WATER_KG_PER_MIN = 0.00264
export const WATER_LOSS_KG_PER_MIN_HOP = 0.00001

export const DEFAULT_EQUIPMENT_POWER_W: Record<string, number> = {
  life_support: 25,
  power: 8,
  propulsion: 50,
  gnc: 15,
  comms: 20,
  fuel: 1,
  fire_suppression: 12,
  medical: 15,
  science: 20,
  other: 5,
}

export function defaultEquipmentPowerW(type: string): number {
  return DEFAULT_EQUIPMENT_POWER_W[type] ?? DEFAULT_EQUIPMENT_POWER_W.other
}

export function defaultEquipmentPortable(type: string): boolean {
  return ['gnc', 'comms', 'fire_suppression', 'medical', 'science', 'other'].includes(type)
}

export function cleanEquipment(equipment: Equipment): Equipment {
  return {
    ...equipment,
    powerConsumptionW:
      equipment.powerConsumptionW ?? defaultEquipmentPowerW(equipment.type),
    portable: equipment.portable ?? defaultEquipmentPortable(equipment.type),
    passageUnits: equipment.passageUnits ?? 1,
    providesCapabilities: equipment.providesCapabilities.filter(
      (capability) => !['oxygen_supply', 'electrical_power'].includes(capability)
    ),
  }
}

export function calculatedModulePowerDemandW(module: ScenarioModule): number {
  const equipmentW = module.equipment
    .filter((equipment) =>
      ['operational', 'exposed_at_risk'].includes(equipment.state)
    )
    .reduce((total, equipment) => total + equipment.powerConsumptionW, 0)
  const outputW =
    (module.type === 'life_support' && module.suppliesAir ? AIR_OUTPUT_POWER_W : 0) +
    (module.type === 'life_support' && module.suppliesWater ? WATER_OUTPUT_POWER_W : 0)
  return module.powerConsumptionW + equipmentW + outputW
}

type Utility = 'power' | 'air' | 'water'

function distances(
  scenario: SpacecraftScenario,
  sourceId: string,
  utility: Utility
): Record<string, number> {
  const result: Record<string, number> = { [sourceId]: 0 }
  const queue = [sourceId]
  while (queue.length) {
    const current = queue.shift()!
    for (const connection of Object.values(scenario.connections)) {
      if (connection.type !== 'hatch') continue
      const lineOn = {
        power: connection.powerLineOn,
        air: connection.airLineOn && connection.state === 'open',
        water: connection.waterLineOn,
      }[utility]
      if (!lineOn) continue
      let neighbor: string | null = null
      if (connection.source === current) neighbor = connection.target
      if (connection.target === current) neighbor = connection.source
      if (neighbor && result[neighbor] == null) {
        result[neighbor] = result[current] + 1
        queue.push(neighbor)
      }
    }
  }
  return result
}

function assignNearest(
  moduleIds: string[],
  sourceIds: string[],
  bySource: Record<string, Record<string, number>>
): Record<string, string> {
  return Object.fromEntries(
    moduleIds.flatMap((moduleId) => {
      const candidates = sourceIds
        .filter((sourceId) => bySource[sourceId][moduleId] != null)
        .sort((a, b) => bySource[a][moduleId] - bySource[b][moduleId] || a.localeCompare(b))
      return candidates.length ? [[moduleId, candidates[0]]] : []
    })
  )
}

/**
 * Populate safe initial source capacities for the currently selected topology.
 * Values remain editable afterward; this is a scenario-builder default, not a
 * hidden correction inside the simulation engine.
 */
export function autoSizeResourceSources(input: SpacecraftScenario): SpacecraftScenario {
  const scenario: SpacecraftScenario = {
    ...input,
    modules: Object.fromEntries(
      Object.entries(input.modules).map(([id, module]) => [
        id,
        { ...module, equipment: module.equipment.map(cleanEquipment) },
      ])
    ),
  }
  const modules = scenario.modules
  const moduleIds = Object.keys(modules)

  const powerSources = moduleIds.filter((id) => modules[id].type === 'power')
  const powerDistances = Object.fromEntries(
    powerSources.map((id) => [id, distances(scenario, id, 'power')])
  )
  const powerAssignments = assignNearest(moduleIds, powerSources, powerDistances)
  for (const sourceId of powerSources) {
    const targets = moduleIds.filter(
      (id) => id !== sourceId && powerAssignments[id] === sourceId
    )
    const sourceDemand = calculatedModulePowerDemandW(modules[sourceId])
    const requiredAtTarget = targets.map((id) => calculatedModulePowerDemandW(modules[id]))
    const level = Math.ceil(
      Math.max(
        sourceDemand,
        ...targets.map(
          (id) => calculatedModulePowerDemandW(modules[id]) + powerDistances[sourceId][id]
        )
      )
    )
    modules[sourceId] = {
      ...modules[sourceId],
      powerLevelW: modules[sourceId].sourceSizingLocked
        ? modules[sourceId].powerLevelW
        : level,
      maxPowerOutputW: modules[sourceId].sourceSizingLocked
        ? modules[sourceId].maxPowerOutputW
        : targets.length * Math.max(0, ...requiredAtTarget),
    }
    const distributedLevel = modules[sourceId].powerLevelW
    for (const targetId of targets) {
      modules[targetId] = {
        ...modules[targetId],
        powerLevelW: Math.max(0, distributedLevel - powerDistances[sourceId][targetId]),
      }
    }
  }

  const airSources = moduleIds.filter(
    (id) => modules[id].type === 'life_support' && modules[id].suppliesAir
  )
  const airDistances = Object.fromEntries(
    airSources.map((id) => [id, distances(scenario, id, 'air')])
  )
  const airAssignments = assignNearest(moduleIds, airSources, airDistances)
  for (const sourceId of airSources) {
    const targets = moduleIds.filter(
      (id) => id !== sourceId && airAssignments[id] === sourceId
    )
    modules[sourceId] = {
      ...modules[sourceId],
      oxygenFraction: 0.25,
      maxAirOutputPercentPerMin: modules[sourceId].sourceSizingLocked
        ? modules[sourceId].maxAirOutputPercentPerMin
        : Number((targets.length * 0.01).toFixed(4)),
    }
    for (const targetId of targets) {
      modules[targetId] = {
        ...modules[targetId],
        oxygenFraction: Math.max(0, 0.25 - airDistances[sourceId][targetId] * 0.005),
      }
    }
  }

  const waterSources = moduleIds.filter(
    (id) => modules[id].type === 'life_support' && modules[id].suppliesWater
  )
  const waterDistances = Object.fromEntries(
    waterSources.map((id) => [id, distances(scenario, id, 'water')])
  )
  const waterAssignments = assignNearest(moduleIds, waterSources, waterDistances)
  for (const sourceId of waterSources) {
    const occupiedTargets = moduleIds.filter(
      (id) =>
        id !== sourceId &&
        waterAssignments[id] === sourceId &&
        modules[id].crew.length > 0
    )
    const maxGrossDemand = Math.max(
      0,
      ...occupiedTargets.map(
        (id) =>
          modules[id].crew.length * CREW_WATER_KG_PER_MIN +
          waterDistances[sourceId][id] * WATER_LOSS_KG_PER_MIN_HOP
      )
    )
    modules[sourceId] = {
      ...modules[sourceId],
      maxWaterOutputKgPerMin: modules[sourceId].sourceSizingLocked
        ? modules[sourceId].maxWaterOutputKgPerMin
        : Number((occupiedTargets.length * maxGrossDemand).toFixed(6)),
    }
  }
  return scenario
}

export function normalizeConnectionUtilities(connection: ScenarioConnection): ScenarioConnection {
  const isHatch = connection.type === 'hatch'
  return {
    ...connection,
    powerLineOn: isHatch && (connection.powerLineOn ?? true),
    airLineOn: isHatch && (connection.airLineOn ?? true),
    waterLineOn: isHatch && (connection.waterLineOn ?? true),
    baseConnectivity: connection.baseConnectivity ?? 100,
    connectivity: connection.connectivity ?? connection.baseConnectivity ?? 100,
    powerTransferFactor: connection.powerTransferFactor ?? 1,
  }
}
