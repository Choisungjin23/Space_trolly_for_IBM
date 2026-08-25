// TypeScript mirrors of the backend API schemas (app/api/schemas.py).

export interface CrewMember {
  id: string;
  name: string;
  alive: boolean;
}

export interface Module {
  id: string;
  name: string;
  fire_severity: number;
  isolated: boolean;
  crew: CrewMember[];
  systems: string[];
}

export interface Connection {
  source: string;
  target: string;
  hazard_spread_probability: number;
  active: boolean;
}

export interface Action {
  id: string;
  label: string;
  description: string;
}

export interface Scenario {
  modules: Record<string, Module>;
  connections: Connection[];
  critical_systems: string[];
  // Available actions depend on where the fire is, so they ship with the scenario.
  actions: Action[];
}

/** Control metadata for one GUI-editable numeric parameter. */
export interface FieldSpec {
  key: string;
  label: string;
  group: string;
  min: number;
  max: number;
  step: number;
  integer: boolean;
  help: string;
}

export interface NamedEntity {
  id: string;
  name: string;
}

export interface ConfigMeta {
  defaults: Record<string, unknown>;
  fields: FieldSpec[];
  modules: NamedEntity[];
  crew: NamedEntity[];
}

/** The editable parameter set the GUI sends back with every request. */
export interface Settings {
  initial_fire_module: string;
  crew_placement: Record<string, string>;
  [key: string]: string | number | Record<string, string>;
}

export interface ActionResult {
  action_id: string;
  label: string;
  runs: number;
  total_crew: number;
  expected_surviving_crew: number;
  crew_survival_pct: number;
  fire_contained_pct: number;
  critical_systems_pct: number;
  mission_survival_pct: number;
  mean_final_fire_severity: number;
}

export interface SimulateResponse {
  runs: number;
  seed: number | null;
  steps: number;
  results: ActionResult[];
}
