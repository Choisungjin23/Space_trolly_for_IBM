import type { ActionResult, SimulateResponse } from "../types";

interface MetricRow {
  key: keyof ActionResult;
  label: string;
  format: (v: number) => string;
  // Whether a higher value is better (used to highlight the best cell).
  higherIsBetter: boolean;
}

const METRICS: MetricRow[] = [
  {
    key: "expected_surviving_crew",
    label: "Expected surviving crew",
    format: (v) => v.toFixed(2),
    higherIsBetter: true,
  },
  {
    key: "crew_survival_pct",
    label: "Crew survival %",
    format: (v) => `${v.toFixed(1)}%`,
    higherIsBetter: true,
  },
  {
    key: "fire_contained_pct",
    label: "Fire contained %",
    format: (v) => `${v.toFixed(1)}%`,
    higherIsBetter: true,
  },
  {
    key: "critical_systems_pct",
    label: "Critical systems surviving %",
    format: (v) => `${v.toFixed(1)}%`,
    higherIsBetter: true,
  },
  {
    key: "mission_survival_pct",
    label: "Mission survival %",
    format: (v) => `${v.toFixed(1)}%`,
    higherIsBetter: true,
  },
  {
    key: "mean_final_fire_severity",
    label: "Mean final fire severity (max over modules)",
    format: (v) => v.toFixed(3),
    higherIsBetter: false,
  },
];

export function ResultsComparison({ response }: { response: SimulateResponse }) {
  const results = response.results;
  const bestMission = results.reduce((best, r) =>
    r.mission_survival_pct > best.mission_survival_pct ? r : best
  );
  const totalCrew = results[0]?.total_crew ?? 0;

  return (
    <div className="results">
      <h2>Simulation results</h2>
      <p className="hint">
        {response.runs} runs per action, {response.steps} time steps each
        {response.seed !== null ? `, seed ${response.seed}` : ", random seed"}. Best value
        per metric is highlighted.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              {results.map((r) => (
                <th key={r.action_id}>{r.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {METRICS.map((metric) => {
              const values = results.map((r) => r[metric.key] as number);
              const best = metric.higherIsBetter
                ? Math.max(...values)
                : Math.min(...values);
              const label =
                metric.key === "expected_surviving_crew"
                  ? `${metric.label} (of ${totalCrew})`
                  : metric.label;
              return (
                <tr key={metric.key}>
                  <td>{label}</td>
                  {results.map((r, i) => (
                    <td key={r.action_id} className={values[i] === best ? "best" : ""}>
                      {metric.format(values[i])}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="verdict">
        Highest mission survival: <strong>{bestMission.label}</strong> at{" "}
        {bestMission.mission_survival_pct.toFixed(1)}%.
      </p>
    </div>
  );
}
