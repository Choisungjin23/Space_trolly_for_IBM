/**
 * SpacecraftCanvas — React Flow wrapper.
 *
 * Nodes and edges are DERIVED from the canonical scenario store.
 * When nodes are moved, only the `position` field in the store is updated.
 * No duplicate spacecraft state inside React Flow.
 */

import { useCallback, useMemo } from 'react'
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
  const { scenario, updateModulePosition, addConnection, removeModule, removeConnection } =
    useScenarioStore()

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
        data: { connection: conn } as ConnectionEdgeData,
      })),
    [scenario.connections, selectedConnectionId]
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
    <div style={{ width: '100%', height: '100%', background: '#0a0c10' }}>
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
          color="#1e2128"
          gap={20}
          size={1}
        />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const data = node.data as ModuleNodeData
            if (data?.emergency?.affectedModuleId === node.id) return '#ef4444'
            return '#3b82f6'
          }}
          maskColor="rgba(10, 12, 16, 0.7)"
          style={{ bottom: 20, right: 20 }}
        />
        {Object.keys(scenario.modules).length === 0 && (
          <Panel position="top-center">
            <div
              style={{
                background: '#1e2128',
                border: '1px solid #2a2d36',
                borderRadius: 8,
                padding: '12px 20px',
                color: '#64748b',
                fontSize: 13,
                textAlign: 'center',
              }}
            >
              Click <strong style={{ color: '#94a3b8' }}>+ Module</strong> to start building your spacecraft
            </div>
          </Panel>
        )}
      </ReactFlow>
    </div>
  )
}
