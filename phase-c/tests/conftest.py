from pathlib import Path

import pytest

from phase_c import config
from phase_c.contracts.findings import AgentFinding, Claim, Recommendation, Tradeoff
from phase_c.providers.mock import MockSimulationProvider

FIXTURE = Path(__file__).parent / "fixtures" / "demo_case.json"


@pytest.fixture(autouse=True)
def isolated_watsonx_env(tmp_path, monkeypatch):
    """Keep the developer's real backend/.env out of the test environment.

    phase_c.config discovers a .env when configuration is read, so without
    this a machine with working credentials would silently pass tests that
    are meant to prove the unconfigured behaviour.
    """
    monkeypatch.setenv(config.ENV_FILE_VAR, str(tmp_path / "absent.env"))


@pytest.fixture
def provider() -> MockSimulationProvider:
    return MockSimulationProvider.from_fixture(FIXTURE)


@pytest.fixture
def case(provider):
    return provider.analyze_case()


@pytest.fixture
def focus(case):
    """The do-nothing baseline, which the orchestrator analyses by default."""
    return case.action("do_nothing")


def grounded_finding(agent: str, action_id: str = "do_nothing") -> AgentFinding:
    """A finding whose every number traces to the fixture."""
    return AgentFinding(
        agent=agent,
        action_id=action_id,
        claims=[
            Claim(
                statement="In this simulation, detection occurred at 270 seconds.",
                basis="SIMULATION_FACT",
                refs=["/actions/0/detection/detected_at_seconds"],
                confidence="HIGH",
            )
        ],
        concerns=["Smoke reached more than one module."],
    )


def sound_recommendation(action_id: str = "isolate:M2") -> Recommendation:
    return Recommendation(
        recommended_action_id=action_id,
        rationale=[
            Claim(
                statement="Smoke stayed in the burning module.",
                basis="SIMULATION_FACT",
                refs=["/actions/4/hazard/reached_modules"],
            )
        ],
        tradeoffs=[
            Tradeoff(
                versus_action_id="do_nothing",
                gives_up="Access to the sealed module for the rest of the run.",
                gains="Containment of smoke to the module of origin.",
            )
        ],
        uncertainty=[
            "Sampling covered decision delay and flow uncertainty only.",
        ],
    )


class ScriptedLLM:
    """Returns a per-agent scripted object; records what it was asked."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.seen: list[str] = []

    def complete(self, *, system: str, user: str, schema, temperature: float = 0.0):
        agent = "unknown"
        for line in system.splitlines():
            if line.strip().startswith("AGENT:"):
                agent = line.split("AGENT:", 1)[1].strip()
                break
        self.seen.append(agent)
        if agent not in self.responses:
            raise AssertionError(f"No scripted response for agent {agent!r}")
        value = self.responses[agent]
        return value(user) if callable(value) else value
