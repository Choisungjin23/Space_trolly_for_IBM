/**
 * The architecture bar.
 *
 * Product identity sits at the left, the vessel's own name beside it, and the
 * one action that moves the work forward sits at the right. Everything between
 * is a tool, styled to recede: the chart is the subject, not this strip.
 *
 * The primary action is EXPLORE FUTURES, and it means exactly what it runs —
 * Phase A counterfactuals over every candidate action. Consulting Circe is a
 * separate step on the results screen, because that is where the agents are.
 */

import { useState } from 'react'
import { useScenarioStore } from '../../store/useScenarioStore'
import { useSimulationStore } from '../../store/useSimulationStore'
import { simulateWithProgress } from '../../api/simulatorClient'
import EmergencyInjector from '../emergency/EmergencyInjector'
import { ProvenanceDisclosure } from '../shared/Provenance'
import {
  IconConstellation,
  IconFutures,
  IconHazard,
  IconModule,
  IconRemove,
} from '../shared/Icons'

interface Props {
  selectedModuleId: string | null
  selectedConnectionId: string | null
  onDeselect: () => void
  onResultsReady: () => void
  blueprintOpen: boolean
  onToggleBlueprint: () => void
}

export default function BuilderToolbar({
  selectedModuleId,
  selectedConnectionId,
  onDeselect,
  onResultsReady,
  blueprintOpen,
  onToggleBlueprint,
}: Props) {
  const { scenario, addModule, removeModule, removeConnection, setScenarioName } =
    useScenarioStore()
  const { startLoading, setProgress, setResult, setError, status } =
    useSimulationStore()
  const [injectorOpen, setInjectorOpen] = useState(false)

  const moduleCount = Object.keys(scenario.modules).length
  const hasEmergency = !!scenario.emergency
  const hasValidEmergency =
    !!scenario.emergency && !!scenario.modules[scenario.emergency.affectedModuleId]
  const canExplore = hasValidEmergency && moduleCount > 0 && status !== 'loading'
  const hasSelection = !!(selectedModuleId || selectedConnectionId)

  function handleAddModule() {
    addModule({ x: 200 + Math.random() * 200, y: 150 + Math.random() * 150 })
  }

  function handleDelete() {
    if (selectedModuleId) removeModule(selectedModuleId)
    else if (selectedConnectionId) removeConnection(selectedConnectionId)
    onDeselect()
  }

  async function handleExploreFutures() {
    if (!scenario.emergency) return
    startLoading()
    try {
      const result = await simulateWithProgress(
        {
          scenario,
          emergency: scenario.emergency,
          actions: null,
          runs: 200,
          seed: 42,
        },
        setProgress,
      )
      setResult(result)
      onResultsReady()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The simulation did not complete.')
    }
  }

  /** The stage the operator is standing in, derived from the scenario itself. */
  const stage = hasValidEmergency ? 'CRISIS' : 'ARCHITECTURE'

  return (
    <>
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 10,
          background: 'var(--surface)',
          borderBottom: '1px solid var(--line)',
          padding: '0 18px',
          height: 52,
          display: 'flex',
          alignItems: 'center',
          gap: 14,
        }}
      >
        {/* Identity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
          <span style={{ color: 'var(--gold)' }}>
            <IconConstellation size={15} />
          </span>
          <span
            className="circe-label"
            style={{ color: 'var(--ink-2)', letterSpacing: '.22em' }}
          >
            CIRCE
          </span>
        </div>

        <Divider />

        {/* Vessel name */}
        <input
          aria-label="Vessel name"
          value={scenario.name}
          onChange={(e) => setScenarioName(e.target.value)}
          style={{
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid transparent',
            color: 'var(--ink)',
            fontFamily: 'var(--font-ui)',
            fontSize: 14,
            fontWeight: 400,
            outline: 'none',
            width: 200,
            padding: '2px 2px 3px',
          }}
          onFocus={(e) => (e.target.style.borderBottomColor = 'var(--gold-dim)')}
          onBlur={(e) => (e.target.style.borderBottomColor = 'transparent')}
        />

        {/* Stage */}
        <span
          className="circe-label"
          style={{
            color: stage === 'CRISIS' ? 'var(--ember)' : 'var(--ink-3)',
            letterSpacing: '.18em',
            flexShrink: 0,
          }}
        >
          {stage}
        </span>

        <Divider />

        <ToolButton onClick={handleAddModule} icon={<IconModule size={13} />}>
          Module
        </ToolButton>

        <ToolButton
          onClick={handleDelete}
          disabled={!hasSelection}
          icon={<IconRemove size={13} />}
          tone={hasSelection ? 'danger' : undefined}
        >
          Remove
        </ToolButton>

        <ToolButton onClick={onToggleBlueprint} active={blueprintOpen}>
          Deck plan
        </ToolButton>

        <Divider />

        <ToolButton
          onClick={() => setInjectorOpen(true)}
          disabled={moduleCount === 0}
          icon={<IconHazard size={13} />}
          tone={hasEmergency ? 'hazard' : undefined}
        >
          {hasEmergency ? 'Emergency active' : 'Introduce hazard'}
        </ToolButton>

        <div style={{ flex: 1 }} />

        <span
          className="mono"
          style={{ color: 'var(--ink-4)', fontSize: 10, letterSpacing: '.1em' }}
        >
          {moduleCount} MODULE{moduleCount !== 1 ? 'S' : ''}
        </span>

        <ProvenanceDisclosure align="right" />

        {/* The one action that advances the work */}
        <button
          onClick={handleExploreFutures}
          disabled={!canExplore}
          title={
            canExplore
              ? 'Run counterfactual simulations across every candidate action'
              : 'Introduce a hazard into a module first'
          }
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            background: canExplore
              ? 'linear-gradient(180deg, var(--gold-bright) 0%, var(--gold) 100%)'
              : 'var(--surface-3)',
            color: canExplore ? '#181205' : 'var(--ink-4)',
            border: 'none',
            borderRadius: 3,
            padding: '9px 20px',
            fontFamily: 'var(--font-mono)',
            fontSize: 11.5,
            fontWeight: 700,
            letterSpacing: '.18em',
            boxShadow: canExplore ? '0 2px 14px rgba(194,161,91,.26)' : 'none',
            cursor: canExplore ? 'pointer' : 'not-allowed',
            transition: 'background .16s, border-color .16s, color .16s',
            flexShrink: 0,
          }}
        >
          <IconFutures size={13} />
          {status === 'loading' ? 'EXPLORING…' : 'EXPLORE FUTURES'}
        </button>
      </div>

      {injectorOpen && (
        <EmergencyInjector isOpen onClose={() => setInjectorOpen(false)} />
      )}
    </>
  )
}

function Divider() {
  return (
    <span
      style={{ width: 1, height: 20, background: 'var(--line)', flexShrink: 0 }}
    />
  )
}

function ToolButton({
  children,
  onClick,
  icon,
  disabled,
  active,
  tone,
}: {
  children: React.ReactNode
  onClick: () => void
  icon?: React.ReactNode
  disabled?: boolean
  active?: boolean
  tone?: 'danger' | 'hazard'
}) {
  const [hover, setHover] = useState(false)

  const color = disabled
    ? 'var(--ink-4)'
    : tone === 'danger'
      ? 'var(--ember)'
      : tone === 'hazard'
        ? 'var(--amber)'
        : active
          ? 'var(--gold)'
          : hover
            ? 'var(--ink)'
            : 'var(--ink-2)'

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        background: active ? 'var(--gold-wash)' : 'transparent',
        border: `1px solid ${active ? 'var(--gold-dim)' : hover && !disabled ? 'var(--line)' : 'transparent'}`,
        borderRadius: 3,
        padding: '6px 10px',
        color,
        fontFamily: 'var(--font-ui)',
        fontSize: 12,
        cursor: disabled ? 'not-allowed' : 'pointer',
        whiteSpace: 'nowrap',
        transition: 'color .15s, border-color .15s, background .15s',
        flexShrink: 0,
      }}
    >
      {icon}
      {children}
    </button>
  )
}
