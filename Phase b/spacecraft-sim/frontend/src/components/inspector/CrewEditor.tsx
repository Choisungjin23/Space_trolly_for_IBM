/**
 * CrewEditor — add/edit/remove crew members within a module.
 */

import { useState } from 'react'
import type { CrewMember } from '../../types/scenario'
import { useScenarioStore } from '../../store/useScenarioStore'

interface Props {
  moduleId: string
  crew: CrewMember[]
}

const ROLE_OPTIONS = [
  'Commander', 'Pilot', 'Engineer', 'Mission Specialist', 'Flight Surgeon', 'Payload Specialist', 'Other',
]

const FUNCTION_SUGGESTIONS = [
  'command', 'navigation', 'propulsion_ops', 'life_support_ops', 'power_ops',
  'repair', 'gnc_ops', 'eva_ops', 'medical', 'docking', 'payload_ops',
]

export default function CrewEditor({ moduleId, crew }: Props) {
  const { addCrewMember, updateCrewMember, removeCrewMember } = useScenarioStore()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  function handleAdd() {
    const id = `crew-${crypto.randomUUID().slice(0, 8)}`
    addCrewMember(moduleId, {
      id,
      name: 'New Crew Member',
      role: 'Other',
      providesFunctions: [],
    })
    setExpandedId(id)
  }

  function toggleFunction(crewId: string, fn: string, current: string[]) {
    const updated = current.includes(fn)
      ? current.filter((f) => f !== fn)
      : [...current, fn]
    updateCrewMember(moduleId, crewId, { providesFunctions: updated })
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ color: 'var(--ink-2)', fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>
          CREW ({crew.length})
        </span>
        <button
          onClick={handleAdd}
          style={{
            background: 'var(--gold-dim)',
            color: 'var(--gold-bright)',
            border: 'none',
            borderRadius: 4,
            padding: '3px 10px',
            fontSize: 11,
            cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          + Add
        </button>
      </div>

      {crew.length === 0 && (
        <div style={{ color: 'var(--ink-4)', fontSize: 12, fontStyle: 'italic', padding: '4px 0' }}>
          No crew assigned
        </div>
      )}

      {crew.map((c) => (
        <div
          key={c.id}
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 6,
            marginBottom: 6,
            overflow: 'hidden',
          }}
        >
          {/* Header row */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 10px',
              cursor: 'pointer',
            }}
            onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
          >
            <span style={{ color: 'var(--gold)', fontSize: 13 }}>👤</span>
            <span style={{ flex: 1, color: 'var(--ink)', fontSize: 12, fontWeight: 500 }}>{c.name}</span>
            <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>{c.role}</span>
            <button
              onClick={(e) => {
                e.stopPropagation()
                removeCrewMember(moduleId, c.id)
              }}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--ember)',
                cursor: 'pointer',
                fontSize: 14,
                padding: '0 2px',
                lineHeight: 1,
              }}
              title="Remove crew member"
            >
              ×
            </button>
          </div>

          {/* Expanded editor */}
          {expandedId === c.id && (
            <div style={{ padding: '0 10px 10px', borderTop: '1px solid var(--surface-3)' }}>
              <label style={labelStyle}>Name</label>
              <input
                style={inputStyle}
                value={c.name}
                onChange={(e) => updateCrewMember(moduleId, c.id, { name: e.target.value })}
              />

              <label style={labelStyle}>Role</label>
              <select
                style={inputStyle}
                value={c.role}
                onChange={(e) => updateCrewMember(moduleId, c.id, { role: e.target.value })}
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>

              <label style={labelStyle}>Functions Provided</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {FUNCTION_SUGGESTIONS.map((fn) => {
                  const active = c.providesFunctions.includes(fn)
                  return (
                    <button
                      key={fn}
                      onClick={() => toggleFunction(c.id, fn, c.providesFunctions)}
                      style={{
                        background: active ? 'var(--gold-dim)' : 'var(--surface-3)',
                        color: active ? 'var(--gold-bright)' : 'var(--ink-3)',
                        border: `1px solid ${active ? 'var(--gold)' : 'var(--line)'}`,
                        borderRadius: 4,
                        padding: '2px 8px',
                        fontSize: 11,
                        cursor: 'pointer',
                      }}
                    >
                      {fn}
                    </button>
                  )
                })}
              </div>
              {c.providesFunctions.filter((f) => !FUNCTION_SUGGESTIONS.includes(f)).map((fn) => (
                <span key={fn} style={{
                  background: 'var(--gold-dim)',
                  color: 'var(--gold-bright)',
                  borderRadius: 4,
                  padding: '2px 8px',
                  fontSize: 11,
                  marginRight: 4,
                }}>{fn}</span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  color: 'var(--ink-3)',
  fontSize: 11,
  marginTop: 8,
  marginBottom: 3,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--void)',
  border: '1px solid var(--line)',
  borderRadius: 4,
  color: 'var(--ink)',
  fontSize: 12,
  padding: '4px 8px',
  outline: 'none',
}
