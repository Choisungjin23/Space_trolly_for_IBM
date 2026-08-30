/**
 * Simulation store — status and results from the simulator client.
 *
 * No simulation logic here. Only state management for the async simulation call.
 */

import { create } from 'zustand'
import type { SimulationResponse } from '../types/simulator'
import type { RunProgress } from '../api/simulatorClient'

type SimulationStatus = 'idle' | 'loading' | 'done' | 'error'

interface SimulationState {
  status: SimulationStatus
  result: SimulationResponse | null
  error: string | null
  progress: RunProgress | null
  // ── Mutations ──────────────────────────────────────────────────────────────
  startLoading: () => void
  setProgress: (progress: RunProgress) => void
  setResult: (result: SimulationResponse) => void
  setError: (error: string) => void
  reset: () => void
}

export const useSimulationStore = create<SimulationState>()((set) => ({
  status: 'idle',
  result: null,
  error: null,
  progress: null,

  startLoading: () =>
    set({ status: 'loading', result: null, error: null, progress: null }),
  setProgress: (progress) => set({ progress }),
  setResult: (result) =>
    set({ status: 'done', result, error: null, progress: null }),
  setError: (error) =>
    set({ status: 'error', error, result: null, progress: null }),
  reset: () => set({ status: 'idle', result: null, error: null, progress: null }),
}))
