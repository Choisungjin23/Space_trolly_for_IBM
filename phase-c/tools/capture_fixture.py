"""Capture a Phase C fixture from REAL Phase A output.

Run once; commit the result. Every agent test then replays real shapes offline.

    python tools/capture_fixture.py \
        ../spacecraft-sim/examples/demo_spacecraft.json \
        tests/fixtures/demo_case.json --samples 20 --seed 42
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phase_c.providers.phase_a import (  # noqa: E402
    PhaseASimulationAdapter,
    load_scenario,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario")
    parser.add_argument("out")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--horizon", type=float, default=None)
    parser.add_argument("--dt", type=float, default=None)
    args = parser.parse_args()

    scenario = load_scenario(args.scenario)
    adapter = PhaseASimulationAdapter(
        horizon_seconds=args.horizon, dt_seconds=args.dt
    )
    case = adapter.analyze_case(scenario, samples=args.samples, seed=args.seed)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(case.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {out} — {len(case.actions)} actions, digest {case.scenario_digest}")


if __name__ == "__main__":
    main()
