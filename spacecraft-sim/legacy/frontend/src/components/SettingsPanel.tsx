import type { ConfigMeta, Settings } from "../types";

export function SettingsPanel({
  config,
  settings,
  onChange,
  onReset,
}: {
  config: ConfigMeta;
  settings: Settings;
  onChange: (next: Settings) => void;
  onReset: () => void;
}) {
  const groups = Array.from(new Set(config.fields.map((f) => f.group)));

  function setNumber(key: string, value: number) {
    onChange({ ...settings, [key]: value });
  }

  function setFireModule(moduleId: string) {
    onChange({ ...settings, initial_fire_module: moduleId });
  }

  function setCrewModule(crewId: string, moduleId: string) {
    onChange({
      ...settings,
      crew_placement: { ...settings.crew_placement, [crewId]: moduleId },
    });
  }

  return (
    <div className="settings">
      <div className="settings-head">
        <h2>Scenario parameters</h2>
        <button className="secondary" onClick={onReset}>
          Reset to defaults
        </button>
      </div>
      <p className="hint">
        Every value here is a configurable PoC assumption, not validated fire physics.
        Changing anything updates the diagram above immediately; press Run Simulation to
        see the effect on outcomes.
      </p>

      <div className="settings-grid">
        <fieldset>
          <legend>Fire &amp; crew placement</legend>

          <label className="row">
            <span>Fire starts in</span>
            <select
              value={settings.initial_fire_module}
              onChange={(e) => setFireModule(e.target.value)}
            >
              {config.modules.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}: {m.name}
                </option>
              ))}
            </select>
          </label>

          {config.crew.map((c) => (
            <label className="row" key={c.id}>
              <span>
                {c.name} <em>({c.id})</em>
              </span>
              <select
                value={settings.crew_placement[c.id]}
                onChange={(e) => setCrewModule(c.id, e.target.value)}
              >
                {config.modules.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id}: {m.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>

        {groups.map((group) => (
          <fieldset key={group}>
            <legend>{group}</legend>
            {config.fields
              .filter((f) => f.group === group)
              .map((field) => {
                const value = Number(settings[field.key]);
                return (
                  <label className="slider" key={field.key} title={field.help}>
                    <span>
                      {field.label}
                      <em>{field.integer ? value : value.toFixed(2)}</em>
                    </span>
                    <input
                      type="range"
                      min={field.min}
                      max={field.max}
                      step={field.step}
                      value={value}
                      onChange={(e) => setNumber(field.key, Number(e.target.value))}
                    />
                  </label>
                );
              })}
          </fieldset>
        ))}
      </div>
    </div>
  );
}
