import type { ConfigMeta, Scenario, Settings, SimulateResponse } from "./types";

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${url} failed (${response.status}): ${await response.text()}`);
  }
  return response.json();
}

export async function fetchConfig(): Promise<ConfigMeta> {
  const response = await fetch("/api/config");
  if (!response.ok) throw new Error(`/api/config failed: ${response.status}`);
  return response.json();
}

/** Preview the scenario that the current settings produce (graph + actions). */
export function previewScenario(settings: Settings): Promise<Scenario> {
  return postJson<Scenario>("/api/scenario", { settings });
}

export function runSimulation(
  settings: Settings,
  runs: number,
  seed: number | null
): Promise<SimulateResponse> {
  // actions omitted = simulate every action available for this scenario
  return postJson<SimulateResponse>("/api/simulate", { settings, runs, seed });
}

/** Build the initial editable settings object from the backend defaults. */
export function settingsFromConfig(config: ConfigMeta): Settings {
  const defaults = config.defaults;
  const settings: Settings = {
    initial_fire_module: String(defaults.initial_fire_module),
    crew_placement: { ...(defaults.crew_placement as Record<string, string>) },
  };
  for (const field of config.fields) {
    settings[field.key] = Number(defaults[field.key]);
  }
  return settings;
}
