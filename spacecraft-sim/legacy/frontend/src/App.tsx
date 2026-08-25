import { useEffect, useState } from "react";
import { fetchConfig, previewScenario, runSimulation, settingsFromConfig } from "./api";
import type { ConfigMeta, Scenario, Settings, SimulateResponse } from "./types";
import { SpacecraftGraph } from "./components/SpacecraftGraph";
import { ModuleCard } from "./components/ModuleCard";
import { SettingsPanel } from "./components/SettingsPanel";
import { ActionPanel } from "./components/ActionPanel";
import { ResultsComparison } from "./components/ResultsComparison";

export default function App() {
  const [config, setConfig] = useState<ConfigMeta | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [runs, setRuns] = useState(1000);
  const [seed, setSeed] = useState("42");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<SimulateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load the parameter metadata + defaults once.
  useEffect(() => {
    fetchConfig()
      .then((c) => {
        setConfig(c);
        setSettings(settingsFromConfig(c));
      })
      .catch((e) => setError(String(e)));
  }, []);

  // Re-preview the scenario whenever settings change (debounced so dragging a
  // slider does not fire a request per pixel).
  useEffect(() => {
    if (!settings) return;
    const timer = setTimeout(() => {
      previewScenario(settings)
        .then(setScenario)
        .catch((e) => setError(String(e)));
    }, 150);
    return () => clearTimeout(timer);
  }, [settings]);

  async function simulate() {
    if (!settings) return;
    setBusy(true);
    setError(null);
    try {
      const parsedSeed = seed.trim() === "" ? null : Number(seed);
      setResults(await runSimulation(settings, runs, parsedSeed));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    if (config) {
      setSettings(settingsFromConfig(config));
      setResults(null);
    }
  }

  if (error && !scenario) {
    return (
      <main>
        <h1>Spacecraft Emergency Simulator</h1>
        <p className="error">
          Could not reach the backend: {error}. Is FastAPI running on port 8000?
        </p>
      </main>
    );
  }
  if (!config || !settings || !scenario) {
    return (
      <main>
        <h1>Spacecraft Emergency Simulator</h1>
        <p>Loading scenario…</p>
      </main>
    );
  }

  return (
    <main>
      <h1>Spacecraft Emergency Simulator</h1>
      <p className="subtitle">
        Phase A proof of concept. Stochastic propagation model with configurable PoC
        parameters (not validated fire physics). ★ = critical system.
      </p>

      <SpacecraftGraph scenario={scenario} />

      <div className="module-cards">
        {Object.values(scenario.modules).map((mod) => (
          <ModuleCard
            key={mod.id}
            module={mod}
            criticalSystems={scenario.critical_systems}
          />
        ))}
      </div>

      <SettingsPanel
        config={config}
        settings={settings}
        onChange={setSettings}
        onReset={reset}
      />

      <ActionPanel
        actions={scenario.actions}
        runs={runs}
        seed={seed}
        busy={busy}
        onRunsChange={setRuns}
        onSeedChange={setSeed}
        onSimulate={simulate}
      />

      {error && <p className="error">{error}</p>}
      {results && <ResultsComparison response={results} />}
    </main>
  );
}
