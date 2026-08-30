"""Typer CLI for the Phase A engine."""

from pathlib import Path

import typer

from spacecraft_sim import config
from spacecraft_sim.actions import find_action, generate_actions
from spacecraft_sim.crew import measured_criticality
from spacecraft_sim.engine import counterfactual
from spacecraft_sim.models import Scenario
from spacecraft_sim.montecarlo import run_montecarlo
from spacecraft_sim.report import format_comparison, format_criticality, format_result

app = typer.Typer(help="Generic spacecraft emergency simulation engine (Phase A PoC).")


def _load(scenario_file: Path) -> Scenario:
    return Scenario.model_validate_json(scenario_file.read_text(encoding="utf-8"))


@app.command()
def actions(scenario_file: Path) -> None:
    """List every rule-generated action available for the scenario."""
    scenario = _load(scenario_file)
    for action in generate_actions(scenario):
        typer.echo(f"{action.id:<40} {action.label}")


@app.command("simulate")
def simulate_cmd(
    scenario_file: Path,
    action: str = typer.Option("do_nothing", help="Action id (see 'actions')."),
    horizon: float = typer.Option(config.HORIZON_SECONDS),
    dt: float = typer.Option(config.DT_SECONDS),
    decision_delay: float = typer.Option(
        0.0, help="Seconds between the alarm and the action being taken."
    ),
) -> None:
    """Counterfactual simulation of one action."""
    scenario = _load(scenario_file)
    act = find_action(scenario, action)
    result = counterfactual(
        scenario, act, horizon=horizon, dt=dt, decision_delay=decision_delay
    )
    typer.echo(format_result(result))


@app.command()
def compare(
    scenario_file: Path,
    horizon: float = typer.Option(config.HORIZON_SECONDS),
    dt: float = typer.Option(config.DT_SECONDS),
    decision_delay: float = typer.Option(0.0),
) -> None:
    """Simulate every available action and list the outcomes side by side.

    Facts only: no BEST ACTION is designated (reserved for Phase C + humans).
    """
    scenario = _load(scenario_file)
    results = [
        counterfactual(
            scenario, action, horizon=horizon, dt=dt, decision_delay=decision_delay
        )
        for action in generate_actions(scenario)
    ]
    typer.echo(format_comparison(results))


@app.command()
def montecarlo(
    scenario_file: Path,
    action: str = typer.Option(..., help="Action id (see 'actions')."),
    n: int = typer.Option(config.MONTECARLO_SAMPLES, "-n", "--samples"),
    seed: int = typer.Option(None, help="RNG seed for reproducibility."),
    horizon: float = typer.Option(config.HORIZON_SECONDS),
    dt: float = typer.Option(config.DT_SECONDS),
) -> None:
    """Sample uncertain scenario assumptions n times and report counts."""
    scenario = _load(scenario_file)
    act = find_action(scenario, action)
    deterministic = counterfactual(scenario, act, horizon=horizon, dt=dt)
    dist = run_montecarlo(scenario, act, n=n, seed=seed, horizon=horizon, dt=dt)
    typer.echo(format_result(deterministic, mc=dist))


@app.command()
def criticality(
    scenario_file: Path,
    action: str = typer.Option("do_nothing", help="Action id (see 'actions')."),
    horizon: float = typer.Option(config.HORIZON_SECONDS),
    dt: float = typer.Option(config.DT_SECONDS),
) -> None:
    """Measure crew criticality by leave-one-out, alongside the assumed weight.

    Removes each crew member in turn and re-runs the simulation, so criticality
    is measured by the engine rather than taken from an assumed table.
    """
    scenario = _load(scenario_file)
    act = find_action(scenario, action)
    typer.echo(format_criticality(measured_criticality(scenario, act, horizon, dt)))


@app.command()
def provenance() -> None:
    """Show which constants are NASA-sourced and which are PoC assumptions."""
    typer.echo(config.ETHICS_NOTICE)
    typer.echo("")
    for key, citation in config.SOURCES.items():
        typer.echo(f"[{key}]")
        typer.echo(f"  {citation}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
