/**
 * SimulatorClient â€” the interface that all simulator implementations must satisfy.
 *
 * Phase B: httpSimulatorClient calls POST /api/simulate on the FastAPI backend (PhaseASimulatorAdapter).
 * Phase A (future): phaseASimulatorClient drops in here without any UI changes.
 *
 * Components import `simulatorClient` from this file only â€” never from a specific adapter.
 */

import type { SimulationRequest, SimulationResponse, TemplateSummary } from '../types/simulator'
import type { SpacecraftScenario } from '../types/scenario'
import type { AdvisorStatus, AnalyzeRequest, DecisionPackage } from '../types/advisor'

export interface SimulatorClient {
  simulate(request: SimulationRequest): Promise<SimulationResponse>
}

// â”€â”€â”€ HTTP helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // ignore
    }
    throw new Error(`API error ${response.status}: ${detail}`)
  }
  return response.json() as Promise<T>
}

// â”€â”€â”€ Mock simulator client (Phase B) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const httpSimulatorClient: SimulatorClient = {
  simulate(request: SimulationRequest): Promise<SimulationResponse> {
    return apiFetch<SimulationResponse>('/api/simulate', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  },
}

// â”€â”€â”€ Template API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export async function fetchTemplates(): Promise<TemplateSummary[]> {
  return apiFetch<TemplateSummary[]>('/api/templates')
}

export async function fetchTemplate(id: string): Promise<SpacecraftScenario> {
  const data = await apiFetch<Record<string, unknown>>(`/api/templates/${id}`)
  // The template fixture has emergency embedded â€” extract scenario fields only
  const scenario = { ...data }
  // emergency is kept in the fixture but the frontend stores it separately
  return scenario as unknown as SpacecraftScenario
}

// â”€â”€â”€ Active client (swap this to phaseASimulatorClient when Phase A ships) â”€

export const simulatorClient: SimulatorClient = httpSimulatorClient

// --- Phase C advisor -------------------------------------------------------

export async function fetchAdvisorStatus(): Promise<AdvisorStatus> {
  return apiFetch<AdvisorStatus>('/api/advisor/status')
}

export async function analyzeEmergency(
  request: AnalyzeRequest,
): Promise<DecisionPackage> {
  return apiFetch<DecisionPackage>('/api/analyze', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}
