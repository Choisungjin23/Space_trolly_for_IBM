/**
 * Simulation store — status and results from the simulator client.
 *
 * No simulation logic here. Only state management for the async simulation call.
 */

import { create } from 'zustand'
import type { SimulationResponse } from '../types/simulator'

type SimulationStatus = 'idle' | 'loading' | 'done' | 'error'

interface SimulationState {
  status: SimulationStatus
  result: SimulationResponse | null
  error: string | null
  // ── Mutations ──────────────────────────────────────────────────────────────
  startLoading: () => void
  setResult: (result: SimulationResponse) => void
  setError: (error: string) => void
  reset: () => void
}

export const useSimulationStore = create<SimulationState>()((set) => ({
  status: 'idle',
  result: null,
  error: null,

  startLoading: () => set({ status: 'loading', result: null, error: null }),
  setResult: (result) => set({ status: 'done', result, error: null }),
  setError: (error) => set({ status: 'error', error, result: null }),
  reset: () => set({ status: 'idle', result: null, error: null }),
}))
