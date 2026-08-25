/**
 * InspectorPanel — slide-in right panel showing module or connection editor.
 */

import { useScenarioStore } from '../../store/useScenarioStore'
import ModuleInspector from '../inspector/ModuleInspector'
import ConnectionInspector from '../inspector/ConnectionInspector'

interface Props {
  selectedModuleId: string | null
  selectedConnectionId: string | null
  onClose: () => void
}

export default function InspectorPanel({ selectedModuleId, selectedConnectionId, onClose }: Props) {
  const { scenario } = useScenarioStore()

  const module = selectedModuleId ? scenario.modules[selectedModuleId] : null
  const connection = selectedConnectionId ? scenario.connections[selectedConnectionId] : null
  const isOpen = !!module || !!connection

  const title = module
    ? module.name
    : connection
    ? `Connection: ${scenario.modules[connection.source]?.name ?? connection.source} ↔ ${scenario.modules[connection.target]?.name ?? connection.target}`
    : ''

  const subtitle = module
    ? module.type.replace('_', ' ').toUpperCase()
    : connection
    ? connection.type.toUpperCase()
    : ''

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        width: isOpen ? 320 : 0,
        height: '100vh',
        background: '#111318',
        borderLeft: isOpen ? '1px solid #2a2d36' : 'none',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
        zIndex: 100,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {isOpen && (
        <>
          {/* Header */}
          <div
            style={{
              padding: '14px 16px',
              borderBottom: '1px solid #2a2d36',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              flexShrink: 0,
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  color: '#e2e8f0',
                  fontWeight: 600,
                  fontSize: 14,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {title}
              </div>
              <div style={{ color: '#64748b', fontSize: 11, marginTop: 2, letterSpacing: '0.06em' }}>
                {subtitle}
              </div>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: '#64748b',
                cursor: 'pointer',
                fontSize: 18,
                padding: '0 4px',
                lineHeight: 1,
                flexShrink: 0,
              }}
              title="Close inspector"
            >
              ×
            </button>
          </div>

          {/* Content */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '16px',
            }}
          >
            {module && (
              <ModuleInspector module={module} emergency={scenario.emergency} />
            )}
            {connection && (
              <ConnectionInspector
                connection={connection}
                sourceModuleName={scenario.modules[connection.source]?.name ?? connection.source}
                targetModuleName={scenario.modules[connection.target]?.name ?? connection.target}
              />
            )}
          </div>
        </>
      )}
    </div>
  )
}
