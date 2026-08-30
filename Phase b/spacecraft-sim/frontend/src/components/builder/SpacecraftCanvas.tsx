/**
 * SpacecraftCanvas — React Flow wrapper.
 *
 * Nodes and edges are DERIVED from the canonical scenario store.
 * When nodes are moved, only the `position` field in the store is updated.
 * No duplicate spacecraft state inside React Flow.
 */

import { useCallback, useEffect, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type Node,
  type Edge,
  Panel,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import ModuleNode, { type ModuleNodeData } from './ModuleNode'
import ConnectionEdge, { type ConnectionEdgeData } from './ConnectionEdge'
import { useScenarioStore } from '../../store/useScenarioStore'

const nodeTypes = { moduleNode: ModuleNode }
const edgeTypes = { connectionEdge: ConnectionEdge }

interface SpacecraftCanvasProps {
  onModuleSelect: (id: string | null) => void
  onConnectionSelect: (id: string | null) => void
  selectedModuleId: string | null
  selectedConnectionId: string | null
}

export default function SpacecraftCanvas({
  onModuleSelect,
  onConnectionSelect,
  selectedModuleId,
  selectedConnectionId,
}: SpacecraftCanvasProps) {
  const { scenario, updateModulePosition, addConnection, removeModule, removeConnection, advanceEmergencyVisual } =
    useScenarioStore()

  useEffect(() => {
    if (!scenario.emergency) return
    const timer = window.setInterval(advanceEmergencyVisual, 1000)
    return () => window.clearInterval(timer)
  }, [scenario.emergency, advanceEmergencyVisual])

  // ── Derive React Flow nodes from scenario store ──────────────────────────
  const rfNodes: Node[] = useMemo(
    () =>
      Object.values(scenario.modules).map((mod) => ({
        id: mod.id,
        type: 'moduleNode',
        position: mod.position,
        selected: mod.id === selectedModuleId,
        data: {
          module: mod,
          emergency: scenario.emergency,
        } as ModuleNodeData,
      })),
    [scenario.modules, scenario.emergency, selectedModuleId]
  )

  // ── Derive React Flow edges from scenario store ──────────────────────────
  const rfEdges: Edge[] = useMemo(
    () =>
      Object.values(scenario.connections).map((conn) => ({
        id: conn.id,
        source: conn.source,
        target: conn.target,
        type: 'connectionEdge',
        selected: conn.id === selectedConnectionId,
        data: {
          connection: conn,
          // A pathway that touches the burning module is how the hazard
          // travels, so it is drawn hot. The rest of the chart stays cool.
          touchesFire:
            !!scenario.emergency &&
            (conn.source === scenario.emergency.affectedModuleId ||
              conn.target === scenario.emergency.affectedModuleId),
          escapeTarget:
            scenario.emergency?.escapeTarget?.connectionId === conn.id
              ? scenario.emergency.escapeTarget
              : undefined,
        } as ConnectionEdgeData,
      })),
    [scenario.connections, scenario.emergency, selectedConnectionId]
  )

  // ── React Flow state (local, position sync only) ─────────────────────────
  const [, , onNodesChange] = useNodesState(rfNodes)
  const [, , onEdgesChange] = useEdgesState(rfEdges)

  // Sync position changes back to the canonical store
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChange(changes)
      for (const change of changes) {
        if (change.type === 'position' && change.position) {
          updateModulePosition(change.id, change.position)
        }
      }
    },
    [onNodesChange, updateModulePosition]
  )

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChange(changes)
      for (const change of changes) {
        if (change.type === 'remove') {
          removeConnection(change.id)
        }
      }
    },
    [onEdgesChange, removeConnection]
  )

  // ── Connection creation ──────────────────────────────────────────────────
  const onConnect = useCallback(
    (connection: Connection) => {
      if (connection.source && connection.target) {
        addConnection(connection.source, connection.target)
      }
    },
    [addConnection]
  )

  // ── Selection ────────────────────────────────────────────────────────────
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onModuleSelect(node.id)
      onConnectionSelect(null)
    },
    [onModuleSelect, onConnectionSelect]
  )

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      onConnectionSelect(edge.id)
      onModuleSelect(null)
    },
    [onConnectionSelect, onModuleSelect]
  )

  const onPaneClick = useCallback(() => {
    onModuleSelect(null)
    onConnectionSelect(null)
  }, [onModuleSelect, onConnectionSelect])

  // ── Delete via keyboard ──────────────────────────────────────────────────
  const onNodesDelete = useCallback(
    (deleted: Node[]) => {
      for (const node of deleted) {
        removeModule(node.id)
      }
    },
    [removeModule]
  )

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      for (const edge of deleted) {
        removeConnection(edge.id)
      }
    },
    [removeConnection]
  )

  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--void)' }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        onNodesDelete={onNodesDelete}
        onEdgesDelete={onEdgesDelete}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        deleteKeyCode="Delete"
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'connectionEdge' }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          color="var(--surface-3)"
          gap={20}
          size={1}
        />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const data = node.data as ModuleNodeData
            if (data?.emergency?.affectedModuleId === node.id) return 'var(--ember)'
            return 'var(--gold)'
          }}
          maskColor="rgba(10, 12, 16, 0.7)"
          style={{ bottom: 20, right: 20 }}
        />
        {Object.keys(scenario.modules).length === 0 && (
          <Panel position="top-center">
            <div
              style={{
                background: 'var(--surface-3)',
                border: '1px solid var(--line)',
                borderRadius: 8,
                padding: '12px 20px',
                color: 'var(--ink-3)',
                fontSize: 13,
                textAlign: 'center',
              }}
            >
              Click <strong style={{ color: 'var(--ink-2)' }}>+ Module</strong> to start building your spacecraft
            </div>
          </Panel>
        )}
      </ReactFlow>
    </div>
  )
}
