import type { Scenario } from "../types";

// Fixed hand-positioned layout — fine for exactly 5 nodes.
const POSITIONS: Record<string, { x: number; y: number }> = {
  M1: { x: 110, y: 70 },
  M2: { x: 300, y: 70 },
  M3: { x: 490, y: 70 },
  M4: { x: 200, y: 210 },
  M5: { x: 420, y: 210 },
};

const BOX_W = 120;
const BOX_H = 62;

export function SpacecraftGraph({ scenario }: { scenario: Scenario }) {
  return (
    <svg viewBox="0 0 620 290" className="graph" role="img" aria-label="Spacecraft module graph">
      {scenario.connections.map((conn) => {
        const a = POSITIONS[conn.source];
        const b = POSITIONS[conn.target];
        const midX = (a.x + b.x) / 2;
        const midY = (a.y + b.y) / 2;
        return (
          <g key={`${conn.source}-${conn.target}`}>
            <line
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={conn.active ? "#888" : "#c33"}
              strokeWidth={2}
              strokeDasharray={conn.active ? undefined : "6 4"}
            />
            <text x={midX} y={midY - 6} textAnchor="middle" className="edge-label">
              p={conn.hazard_spread_probability}
            </text>
          </g>
        );
      })}
      {Object.values(scenario.modules).map((mod) => {
        const pos = POSITIONS[mod.id];
        const onFire = mod.fire_severity > 0;
        const hasCritical = mod.systems.some((s) => scenario.critical_systems.includes(s));
        return (
          <g key={mod.id}>
            <rect
              x={pos.x - BOX_W / 2}
              y={pos.y - BOX_H / 2}
              width={BOX_W}
              height={BOX_H}
              rx={8}
              fill={onFire ? "#ffe0d6" : "#f2f5f9"}
              stroke={onFire ? "#d9480f" : mod.isolated ? "#1c7ed6" : "#adb5bd"}
              strokeWidth={onFire || mod.isolated ? 3 : 1.5}
              strokeDasharray={mod.isolated ? "5 3" : undefined}
            />
            <text x={pos.x} y={pos.y - 12} textAnchor="middle" className="module-title">
              {mod.id}: {mod.name}
              {hasCritical ? " ★" : ""}
            </text>
            <text x={pos.x} y={pos.y + 6} textAnchor="middle" className="module-sub">
              {onFire ? `🔥 severity ${mod.fire_severity.toFixed(2)}` : "no fire"}
            </text>
            <text x={pos.x} y={pos.y + 22} textAnchor="middle" className="module-sub">
              {mod.crew.length > 0
                ? `👤 ${mod.crew.map((c) => c.id).join(", ")}`
                : "no crew"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
