import type { Module } from "../types";

export function ModuleCard({
  module,
  criticalSystems,
}: {
  module: Module;
  criticalSystems: string[];
}) {
  const onFire = module.fire_severity > 0;
  return (
    <div className={`module-card${onFire ? " on-fire" : ""}`}>
      <h3>
        {module.id}: {module.name}
      </h3>
      <p>
        {onFire ? `🔥 Fire severity ${module.fire_severity.toFixed(2)}` : "No fire"}
        {module.isolated ? " · isolated" : ""}
      </p>
      <p>
        <strong>Systems:</strong>{" "}
        {module.systems.length > 0
          ? module.systems
              .map((s) => (criticalSystems.includes(s) ? `${s} ★` : s))
              .join(", ")
          : "none"}
      </p>
      <p>
        <strong>Crew:</strong>{" "}
        {module.crew.length > 0 ? module.crew.map((c) => c.name).join(", ") : "none"}
      </p>
    </div>
  );
}
