import type { ScenarioConnection, SpacecraftScenario } from '../types/scenario'
import { calculatedModulePowerDemandW, CREW_WATER_KG_PER_MIN } from './resourceSizing'

export const ESCAPE_RESERVE_MINUTES = 60

export interface EscapeRouteCandidate {
  connectionId: string
  fromModuleId: string
  toModuleId: string
  zoneModuleIds: string[]
  eligible: boolean
  reasons: string[]
  score: number
}

function componentWithout(
  scenario: SpacecraftScenario,
  startId: string,
  removedConnectionId: string,
): string[] {
  const seen = new Set([startId])
  const queue = [startId]
  while (queue.length) {
    const current = queue.shift()!
    for (const connection of Object.values(scenario.connections)) {
      if (
        connection.id === removedConnectionId ||
        connection.type !== 'hatch' ||
        connection.state !== 'open'
      ) continue
      const next = connection.source === current
        ? connection.target
        : connection.target === current
          ? connection.source
          : null
      if (next && !seen.has(next)) {
        seen.add(next)
        queue.push(next)
      }
    }
  }
  return [...seen]
}

function assessDirection(
  scenario: SpacecraftScenario,
  connection: ScenarioConnection,
  fromModuleId: string,
  toModuleId: string,
  affectedModuleId: string,
): EscapeRouteCandidate {
  const sourceZone = componentWithout(scenario, fromModuleId, connection.id)
  const zoneModuleIds = componentWithout(scenario, toModuleId, connection.id)
  const reasons: string[] = []
  if (!sourceZone.includes(affectedModuleId)) reasons.push('hazard cannot reach the entry side')
  if (zoneModuleIds.includes(affectedModuleId)) reasons.push('target zone is not isolated from the hazard')

  const zone = zoneModuleIds.map((id) => scenario.modules[id]).filter(Boolean)
  const powerSources = zone.filter(
    (module) => module.type === 'power' && module.maxPowerOutputW > 0
  )
  const powerCapacity = powerSources.reduce(
    (total, module) => total + module.maxPowerOutputW,
    0,
  )
  const powerDemand = zone.reduce(
    (total, module) => total + calculatedModulePowerDemandW(module),
    0,
  )
  if (!powerSources.length) reasons.push('no independent power source')
  else if (powerCapacity < powerDemand) reasons.push('power source capacity is below zone demand')

  const airSources = zone.filter(
    (module) =>
      module.type === 'life_support' &&
      module.suppliesAir &&
      module.maxAirOutputPercentPerMin > 0
  )
  const airCapacity = airSources.reduce(
    (total, module) => total + module.maxAirOutputPercentPerMin,
    0,
  )
  const airDemand = zone.length * 0.01
  if (!airSources.length) reasons.push('no independent air source')
  else if (airCapacity < airDemand) reasons.push('air output is below zone demand')

  const waterStoredKg = zone.reduce(
    (total, module) => total + module.waterStoredKg,
    0,
  )
  const crewToShelter = Object.values(scenario.modules).reduce(
    (total, module) => total + module.crew.length,
    0,
  )
  const waterRequiredKg =
    crewToShelter * CREW_WATER_KG_PER_MIN * ESCAPE_RESERVE_MINUTES
  if (waterStoredKg < waterRequiredKg) {
    reasons.push(`water reserve below ${ESCAPE_RESERVE_MINUTES}-minute crew demand`)
  }

  const eligible = reasons.length === 0
  const averageAir = zone.length
    ? zone.reduce((total, module) => total + (module.oxygenFraction ?? 0.25), 0) / zone.length
    : 0
  const score = eligible
    ? connection.connectivity + averageAir * 100 + Math.min(25, waterStoredKg) +
      Math.min(25, Math.max(0, powerCapacity - powerDemand) / 10)
    : -reasons.length * 100
  return {
    connectionId: connection.id,
    fromModuleId,
    toModuleId,
    zoneModuleIds,
    eligible,
    reasons,
    score,
  }
}

export function escapeRouteCandidates(
  scenario: SpacecraftScenario,
  affectedModuleId: string,
): EscapeRouteCandidate[] {
  return Object.values(scenario.connections)
    .filter((connection) => connection.type === 'hatch' && connection.state === 'open')
    .flatMap((connection) => [
      assessDirection(
        scenario,
        connection,
        connection.source,
        connection.target,
        affectedModuleId,
      ),
      assessDirection(
        scenario,
        connection,
        connection.target,
        connection.source,
        affectedModuleId,
      ),
    ])
    .sort((a, b) => Number(b.eligible) - Number(a.eligible) || b.score - a.score)
}

export function recommendedEscapeRoute(
  scenario: SpacecraftScenario,
  affectedModuleId: string,
): EscapeRouteCandidate | null {
  return escapeRouteCandidates(scenario, affectedModuleId).find((candidate) => candidate.eligible) ?? null
}
