/**
 * THE ADVICE OF CIRCE — entry.
 *
 * Asymmetric by design: identity and the two ways in on the left, the chart on
 * the right. The chart earns the space because the graph is the product's whole
 * visual language — what you see here is what you are about to draw.
 *
 * Both routes end in the same place. The reference vessel is a starting
 * architecture, not a special mode: it runs the identical Scenario → Simulator
 * path a hand-drawn one does.
 */

import { useState } from 'react'
import { fetchTemplate } from '../../api/simulatorClient'
import { useScenarioStore } from '../../store/useScenarioStore'
import type { EmergencyConfig, SpacecraftScenario } from '../../types/scenario'
import { ProvenanceDisclosure } from '../shared/Provenance'
import { IconArrowRight, IconConstellation, IconVessel } from '../shared/Icons'
import ConstellationChart from './ConstellationChart'

interface Props {
  onStart: () => void
}

/** The four movements of the product, used verbatim across the application. */
const PASSAGE = [
  { n: '01', name: 'ARCHITECTURE', line: 'Chart the vessel.' },
  { n: '02', name: 'CRISIS', line: 'Introduce the hazard.' },
  { n: '03', name: 'FUTURES', line: 'Explore the consequences.' },
  { n: '04', name: 'ADVISORY', line: 'Consult the decision-support system.' },
]

export default function LandingPage({ onStart }: Props) {
  const { loadScenario, addModule } = useScenarioStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleReferenceVessel() {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchTemplate('five-module-demo')
      // The reference fixture carries a reproducible emergency roll. Manual
      // hazard injection still performs a fresh 1–50 roll in the store.
      loadScenario(data as SpacecraftScenario & { emergency?: EmergencyConfig })
      onStart()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'The reference architecture could not be loaded.',
      )
    } finally {
      setLoading(false)
    }
  }

  function handleNewVessel() {
    addModule({ x: 300, y: 250 })
    onStart()
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--void)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* ── Rule line: product mark, transparency ─────────────────────────── */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 20,
          padding: '20px 40px',
          borderBottom: '1px solid var(--line-soft)',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
          <span style={{ color: 'var(--gold)' }}>
            <IconConstellation size={17} />
          </span>
          <span
            className="circe-label"
            style={{ color: 'var(--ink-2)', letterSpacing: '.22em' }}
          >
            CIRCE
          </span>
        </div>
        <ProvenanceDisclosure align="right" />
      </header>

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <main
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: 'minmax(340px, 1fr) minmax(320px, .92fr)',
          alignItems: 'center',
          gap: 72,
          padding: '56px 40px 40px',
          maxWidth: 1320,
          width: '100%',
          margin: '0 auto',
        }}
      >
        {/* Left: identity and the ways in */}
        <div style={{ animation: 'circe-fade-up .5s ease-out' }}>
          <h1
            className="circe-display"
            style={{
              margin: 0,
              fontSize: 'clamp(48px, 6.4vw, 82px)',
              color: 'var(--ink)',
            }}
          >
            THE ADVICE
            <br />
            <span style={{ color: 'var(--gold)' }}>OF CIRCE</span>
          </h1>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 14,
              margin: '26px 0 22px',
            }}
          >
            <span style={{ width: 34, height: 1, background: 'var(--gold-dim)' }} />
            <span
              className="circe-label"
              style={{ color: 'var(--ink-2)', letterSpacing: '.2em' }}
            >
              A Mission-Control Advisor for Uncertain Futures
            </span>
          </div>

          <p
            style={{
              margin: '0 0 34px',
              color: 'var(--ink-2)',
              fontSize: 16,
              lineHeight: 1.75,
              maxWidth: '38ch',
              fontWeight: 300,
            }}
          >
            Chart your spacecraft. Introduce a crisis.
            <br />
            Explore where each decision leads.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 430 }}>
            <PrimaryAction
              icon={<IconVessel size={15} />}
              title="CREATE A VESSEL"
              body="Begin with an empty architecture and define your own modules, crew, systems, and connections."
              onClick={handleNewVessel}
            />
            <SecondaryAction
              title="EXPLORE A REFERENCE SPACECRAFT"
              body="Start from a prepared spacecraft architecture with crew, systems, pathways, and an active emergency."
              loading={loading}
              onClick={handleReferenceVessel}
            />
          </div>

          {error && (
            <div
              role="alert"
              style={{
                marginTop: 16,
                borderLeft: '2px solid var(--ember)',
                paddingLeft: 12,
                color: 'var(--ember)',
                fontSize: 12.5,
                maxWidth: 430,
              }}
            >
              {error}
            </div>
          )}

          <div
            className="circe-label"
            style={{
              marginTop: 30,
              color: 'var(--ink-4)',
              letterSpacing: '.14em',
              lineHeight: 1.9,
            }}
          >
            Evidence-informed simulation · Source-traced parameters
            <br />
            Human decision retained
          </div>
        </div>

        {/* Right: the chart */}
        <div
          style={{
            position: 'relative',
            animation: 'circe-fade-up .6s .12s ease-out backwards',
          }}
        >
          <ConstellationChart />
        </div>
      </main>

      {/* ── The passage ───────────────────────────────────────────────────── */}
      <section
        style={{
          borderTop: '1px solid var(--line-soft)',
          padding: '26px 40px',
          maxWidth: 1320,
          width: '100%',
          margin: '0 auto',
        }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
            gap: 26,
          }}
        >
          {PASSAGE.map((step) => (
            <div key={step.n} style={{ display: 'flex', gap: 12 }}>
              <span
                className="mono"
                style={{ color: 'var(--gold-dim)', fontSize: 11, paddingTop: 2 }}
              >
                {step.n}
              </span>
              <div>
                <div
                  className="circe-label"
                  style={{ color: 'var(--ink-2)', letterSpacing: '.16em' }}
                >
                  {step.name}
                </div>
                <div style={{ color: 'var(--ink-3)', fontSize: 12.5, marginTop: 3 }}>
                  {step.line}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer
        style={{
          padding: '16px 40px 22px',
          color: 'var(--ink-4)',
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          letterSpacing: '.06em',
          textAlign: 'center',
        }}
      >
        Built with IBM Bob and IBM Granite for the IBM AI Builders Challenge
      </footer>

      <style>{`
        @media (max-width: 900px) {
          main { grid-template-columns: 1fr !important; gap: 40px !important; }
        }
      `}</style>
    </div>
  )
}

/* ── Actions ──────────────────────────────────────────────────────────────── */

function PrimaryAction({
  icon,
  title,
  body,
  onClick,
}: {
  icon: React.ReactNode
  title: string
  body: string
  onClick: () => void
}) {
  const [hover, setHover] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '18px 1fr',
        gap: 14,
        textAlign: 'left',
        background: hover ? 'var(--gold-wash)' : 'transparent',
        border: `1px solid ${hover ? 'var(--gold)' : 'var(--gold-dim)'}`,
        borderRadius: 3,
        padding: '18px 20px',
        cursor: 'pointer',
        transition: 'background .18s, border-color .18s',
        width: '100%',
      }}
    >
      <span style={{ color: 'var(--gold)', paddingTop: 2 }}>{icon}</span>
      <span>
        <span
          style={{
            display: 'block',
            color: 'var(--gold)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            fontWeight: 500,
            letterSpacing: '.16em',
          }}
        >
          {title}
        </span>
        <span
          style={{
            display: 'block',
            color: 'var(--ink-2)',
            fontSize: 12.5,
            lineHeight: 1.6,
            marginTop: 6,
          }}
        >
          {body}
        </span>
      </span>
    </button>
  )
}

function SecondaryAction({
  title,
  body,
  loading,
  onClick,
}: {
  title: string
  body: string
  loading: boolean
  onClick: () => void
}) {
  const [hover, setHover] = useState(false)
  return (
    <button
      onClick={onClick}
      disabled={loading}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 18px',
        gap: 14,
        alignItems: 'center',
        textAlign: 'left',
        background: 'transparent',
        border: `1px solid ${hover && !loading ? 'var(--ink-4)' : 'var(--line)'}`,
        borderRadius: 3,
        padding: '18px 20px',
        cursor: loading ? 'wait' : 'pointer',
        transition: 'border-color .18s',
        width: '100%',
        opacity: loading ? 0.6 : 1,
      }}
    >
      <span>
        <span
          style={{
            display: 'block',
            color: 'var(--ink)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            fontWeight: 500,
            letterSpacing: '.16em',
          }}
        >
          {loading ? 'LOADING ARCHITECTURE…' : title}
        </span>
        <span
          style={{
            display: 'block',
            color: 'var(--ink-3)',
            fontSize: 12.5,
            lineHeight: 1.6,
            marginTop: 6,
          }}
        >
          {body}
        </span>
      </span>
      <span
        style={{
          color: hover && !loading ? 'var(--gold)' : 'var(--ink-4)',
          transform: hover && !loading ? 'translateX(2px)' : 'none',
          transition: 'color .18s, transform .18s',
        }}
      >
        <IconArrowRight size={15} />
      </span>
    </button>
  )
}
