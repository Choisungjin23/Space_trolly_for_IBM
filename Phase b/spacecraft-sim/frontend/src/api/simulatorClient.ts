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

// --- Progress streaming ----------------------------------------------------

/**
 * One stage the backend actually reached. `percent` moves when work completes,
 * never on a timer, so a run that stalls looks stalled instead of creeping
 * toward a finish it has not reached.
 */
export interface RunProgress {
  stage: string
  label: string
  done: number
  total: number
  percent: number
}

/**
 * POST a request and read Server-Sent Events off the response body.
 *
 * `EventSource` is GET-only and these payloads are whole scenarios, so the
 * stream is parsed by hand. Frames arrive as `event:`/`data:` pairs separated
 * by a blank line; a partial frame is held in the buffer until it completes.
 */
async function streamRun<T>(
  path: string,
  body: unknown,
  onProgress: (progress: RunProgress) => void,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      // The body may not be JSON; the status line still identifies it.
    }
    throw new Error(`API error ${response.status}: ${detail}`)
  }
  if (!response.body) throw new Error('This browser cannot read a streamed response.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: T | undefined
  let failure: string | null = null

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let split: number
    while ((split = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, split)
      buffer = buffer.slice(split + 2)

      let name = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) name = line.slice(7).trim()
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!data) continue

      const payload = JSON.parse(data)
      if (name === 'progress') onProgress(payload as RunProgress)
      else if (name === 'result') result = payload.result as T
      else if (name === 'error') failure = payload.detail
    }
  }

  if (failure !== null) throw new Error(failure)
  if (result === undefined) throw new Error('The run ended without returning a result.')
  return result
}

export function simulateWithProgress(
  request: SimulationRequest,
  onProgress: (progress: RunProgress) => void,
  signal?: AbortSignal,
): Promise<SimulationResponse> {
  return streamRun<SimulationResponse>('/api/simulate/stream', request, onProgress, signal)
}

export function analyzeWithProgress(
  request: AnalyzeRequest,
  onProgress: (progress: RunProgress) => void,
  signal?: AbortSignal,
): Promise<DecisionPackage> {
  return streamRun<DecisionPackage>('/api/analyze/stream', request, onProgress, signal)
}
