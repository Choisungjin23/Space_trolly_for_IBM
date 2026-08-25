import type { Action } from "../types";

export function ActionPanel({
  actions,
  runs,
  seed,
  busy,
  onRunsChange,
  onSeedChange,
  onSimulate,
}: {
  actions: Action[];
  runs: number;
  seed: string;
  busy: boolean;
  onRunsChange: (runs: number) => void;
  onSeedChange: (seed: string) => void;
  onSimulate: () => void;
}) {
  return (
    <div className="action-panel">
      <h2>Emergency actions</h2>
      <p className="hint">
        Options are derived from where the fire currently is: do nothing, seal the burning
        module, or close any one hatch leading out of it. Running the simulation compares{" "}
        <strong>all {actions.length}</strong> of them on the same initial state, {runs}{" "}
        Monte Carlo runs each.
      </p>
      <ul>
        {actions.map((action) => (
          <li key={action.id}>
            <strong>{action.label}</strong> — {action.description}
          </li>
        ))}
      </ul>
      <div className="controls">
        <label>
          Runs per action{" "}
          <input
            type="number"
            min={1}
            max={10000}
            value={runs}
            onChange={(e) => onRunsChange(Number(e.target.value))}
          />
        </label>
        <label>
          Seed (optional){" "}
          <input
            type="number"
            placeholder="random"
            value={seed}
            onChange={(e) => onSeedChange(e.target.value)}
          />
        </label>
        <button onClick={onSimulate} disabled={busy}>
          {busy ? "Simulating…" : "Run Simulation"}
        </button>
      </div>
    </div>
  );
}
