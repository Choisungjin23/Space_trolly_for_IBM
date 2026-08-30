/**
 * Provenance: source traceability as a design system, not a warning system.
 *
 * The model's limitations used to occupy a warning box in the hero, which made
 * the product read as a debug tool and — worse — made the caveat something to
 * scroll past. Here the same information is always one click away and styled as
 * scientific metadata: a badge pair (verified / assumed) held apart from the
 * hazard palette, so "this figure has a source" never reads as "something is
 * wrong".
 */

import { useEffect, useRef, useState } from 'react'
import { IconClose, IconEvidence } from './Icons'

type Basis = 'verified' | 'assumed'

/** A badge stating where a single figure came from. */
export function ProvenanceBadge({
  basis,
  children,
  title,
}: {
  basis: Basis
  children?: React.ReactNode
  title?: string
}) {
  const verified = basis === 'verified'
  return (
    <span
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        fontFamily: 'var(--font-mono)',
        fontSize: 9.5,
        fontWeight: 500,
        letterSpacing: '.1em',
        color: verified ? 'var(--verified)' : 'var(--assumed)',
        background: verified ? 'var(--verified-wash)' : 'var(--assumed-wash)',
        border: `1px solid ${verified ? 'var(--verified)' : 'var(--assumed)'}33`,
        borderRadius: 2,
        padding: '1.5px 6px',
        whiteSpace: 'nowrap',
      }}
    >
      <span
        aria-hidden
        style={{
          width: 4,
          height: 4,
          borderRadius: verified ? '50%' : 0,
          background: 'currentColor',
          transform: verified ? 'none' : 'rotate(45deg)',
        }}
      />
      {children ?? (verified ? 'VERIFIED' : 'ASSUMED')}
    </span>
  )
}

const ENTRIES: { basis: Basis; label: string; body: string }[] = [
  {
    basis: 'verified',
    label: 'Source-traced parameters',
    body:
      'Exposure limits, ventilation flow, detector thresholds and combustion ' +
      'chemistry are read from primary documents — NASA JSC 20584 Rev C, the ' +
      'Saffire microgravity experiments, NIST fire dynamics, MIL-STD-1629A.',
  },
  {
    basis: 'assumed',
    label: 'Declared assumptions',
    body:
      'Values with no obtainable public figure — passive hatch exchange, ' +
      'equipment damage thresholds, crew translation speed, repair duration — ' +
      'are named as assumptions in the engine itself and are not validated.',
  },
  {
    basis: 'assumed',
    label: 'What the outputs are',
    body:
      'Sampled counts are results of a scenario model, not validated ' +
      'real-world probabilities. The engine tracks hazard transport, exposure, ' +
      'evacuation, resources and capability state. Its survival/return values ' +
      'come from an explicit ASSUMED exposure model, not a clinical forecast; ' +
      'it invents no spread probability.',
  },
  {
    basis: 'verified',
    label: 'Human decision retained',
    body:
      'Every recommendation is advisory and machine-checked against the ' +
      'simulation. Assertions the simulation does not support are shown, not ' +
      'silently corrected. The operator decides.',
  },
]

/** The control and its panel. Opens on click, closes on Escape or outside click. */
export function ProvenanceDisclosure({ align = 'left' }: { align?: 'left' | 'right' }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    function onDown(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  return (
    <div ref={wrapRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 7,
          background: 'transparent',
          border: `1px solid ${open ? 'var(--gold-dim)' : 'var(--line)'}`,
          borderRadius: 3,
          padding: '5px 11px',
          color: open ? 'var(--gold)' : 'var(--ink-2)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          letterSpacing: '.12em',
          textTransform: 'uppercase',
          cursor: 'pointer',
          transition: 'color .15s, border-color .15s',
        }}
      >
        <IconEvidence size={12} />
        Evidence &amp; assumptions
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Evidence and assumptions"
          style={{
            position: 'absolute',
            top: 'calc(100% + 10px)',
            left: align === 'left' ? 0 : undefined,
            right: align === 'right' ? 0 : undefined,
            width: 460,
            maxWidth: '86vw',
            maxHeight: '62vh',
            overflowY: 'auto',
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 4,
            padding: '20px 22px',
            zIndex: 900,
            boxShadow: '0 24px 60px rgba(0,0,0,.6)',
            animation: 'circe-fade-up .18s ease-out',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              marginBottom: 16,
            }}
          >
            <div>
              <div className="circe-label" style={{ color: 'var(--gold)' }}>
                Model transparency
              </div>
              <div style={{ color: 'var(--ink-2)', fontSize: 12, marginTop: 5 }}>
                Where each figure in this system comes from.
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--ink-3)',
                cursor: 'pointer',
                padding: 2,
              }}
            >
              <IconClose size={13} />
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {ENTRIES.map((entry) => (
              <div key={entry.label}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 9,
                    marginBottom: 5,
                  }}
                >
                  <ProvenanceBadge basis={entry.basis} />
                  <span style={{ color: 'var(--ink)', fontSize: 12.5, fontWeight: 500 }}>
                    {entry.label}
                  </span>
                </div>
                <p
                  style={{
                    margin: 0,
                    color: 'var(--ink-2)',
                    fontSize: 12,
                    lineHeight: 1.65,
                  }}
                >
                  {entry.body}
                </p>
              </div>
            ))}
          </div>

          <div
            style={{
              marginTop: 18,
              paddingTop: 14,
              borderTop: '1px solid var(--line-soft)',
              color: 'var(--ink-3)',
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
              lineHeight: 1.7,
            }}
          >
            Engine: spacecraft_sim — real-unit proof-of-concept.
            <br />
            Not a validated NASA flight model.
          </div>
        </div>
      )}
    </div>
  )
}
