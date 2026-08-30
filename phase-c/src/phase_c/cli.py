"""Phase C command line.

    phase-c doctor            check the install and the watsonx configuration
    phase-c doctor --access   verify the credentials against IBM, spending no tokens
    phase-c doctor --live     also make one real Granite call
    phase-c analyze <file>    run the full pipeline over a Phase A scenario JSON

Configuration is read from backend/.env, so no shell variables are needed.
`doctor` never prints a credential. It reports only whether each variable is
set and, for the key, its length - enough to spot a truncated paste without
putting the secret on screen or in a shell history.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from phase_c import config

OK = "  ok   "
BAD = " FAIL  "
WARN = " warn  "


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" - {detail}" if detail else ""))


def _report_configuration() -> int:
    """Print the watsonx configuration. Returns the number of problems."""
    env_file = config.load_env()
    _line(
        OK if env_file else WARN,
        "backend/.env",
        str(env_file) if env_file else "not found, using the process environment",
    )

    sources = config.value_sources()

    key = os.environ.get("WATSONX_API_KEY")
    key_file = os.environ.get("WATSONX_APIKEY_FILE")
    if key:
        # Never print the secret. Length catches a truncated paste; the
        # fingerprint tells two different keys apart; the source says which
        # file or shell won, since an OS variable outranks backend/.env.
        _line(
            OK,
            "API key",
            f"configured ({len(key)} characters, fingerprint "
            f"{config.fingerprint(key)}) from {sources.get('WATSONX_API_KEY')}",
        )
    elif key_file:
        exists = Path(key_file).is_file()
        _line(
            OK if exists else BAD,
            "API key",
            f"from {key_file}" if exists else f"{key_file} (missing)",
        )
    else:
        _line(BAD, "API key", "not set")

    project_id = os.environ.get("WATSONX_PROJECT_ID")
    _line(
        OK if project_id and not config.is_placeholder(project_id) else BAD,
        "Project ID",
        f"configured from {sources.get('WATSONX_PROJECT_ID')}"
        if project_id
        else "not set",
    )

    for label, name in (("watsonx URL", "WATSONX_URL"), ("Model ID", "WATSONX_MODEL_ID")):
        value = os.environ.get(name)
        # Region and model identify the environment, not the account, so
        # printing them is what makes this command useful.
        _line(
            OK if value and not config.is_placeholder(value) else BAD,
            label,
            f"{value} (from {sources.get(name)})" if value else "not set",
        )

    # An OS variable beating the file is the failure that looks like a bad key:
    # the file is edited, the app restarts, and a stale value is still in play.
    overridden = [n for n, s in sources.items() if "overriding" in s]
    if overridden:
        _line(
            WARN,
            "shadowed by the shell",
            ", ".join(overridden)
            + " differ from backend/.env. The shell value wins. Clear it with"
            + ' Remove-Item Env:\\<NAME> and restart, or edit the shell value.',
        )

    problems = config.configuration_problems()
    for problem in problems:
        _line(BAD, "configuration", problem)
    return len(problems)


def _check_access() -> int:
    """Prove the credentials work without spending a single model token.

    Listing an environment's models is a metadata call, so it still answers
    when the plan's token quota is exhausted. That is exactly when you most
    need to know whether a freshly pasted key is good: `--live` cannot tell
    you, because inference is blocked for reasons that have nothing to do with
    the key.
    """
    try:
        from ibm_watsonx_ai import APIClient, Credentials

        from phase_c.config import WatsonxConfig

        cfg = WatsonxConfig.from_env()
        client = APIClient(
            Credentials(url=cfg.url, api_key=cfg.api_key), project_id=cfg.project_id
        )
        specs = client.foundation_models.get_model_specs()
        served = [s["model_id"] for s in (specs or {}).get("resources", [])]
    except Exception as exc:
        from phase_c.llm.granite import _classify

        try:
            from phase_c.config import WatsonxConfig

            _line(BAD, "IBM access", _classify(exc, WatsonxConfig.from_env()))
        except Exception:
            _line(BAD, "IBM access", str(exc))
        return 1

    _line(OK, "Authentication", "the API key is accepted by IBM Cloud")
    _line(OK, "Project access", f"the project is readable in {cfg.region}")

    if cfg.model_id in served:
        _line(OK, "Model availability", f"{cfg.model_id} is served in {cfg.region}")
        return 0
    _line(
        BAD,
        "Model availability",
        f"{cfg.model_id} is NOT served in {cfg.region}. This region offers: "
        + ", ".join(sorted(served)[:8])
        + (" ..." if len(served) > 8 else ""),
    )
    return 1


def doctor(live: bool, access: bool = False) -> int:
    failures = 0

    try:
        import phase_c

        _line(OK, "phase_c", f"version {phase_c.__version__}")
    except ImportError as exc:
        _line(BAD, "phase_c", str(exc))
        return 1

    try:
        from phase_c.providers.phase_a import PHASE_A_VERSION

        _line(OK, "Phase A engine", f"spacecraft_sim {PHASE_A_VERSION}")
    except Exception as exc:
        _line(BAD, "Phase A engine", f"{exc}. Set SPACECRAFT_SIM_SRC or pip install it.")
        failures += 1

    try:
        from phase_c.rag.store import EvidenceStore

        store = EvidenceStore.from_corpus()
        _line(OK, "Evidence corpus", f"{len(store.chunks)} chunks")
    except Exception as exc:
        _line(BAD, "Evidence corpus", str(exc))
        failures += 1

    try:
        import ibm_watsonx_ai  # noqa: F401

        _line(OK, "ibm-watsonx-ai SDK", "installed")
    except ImportError:
        _line(BAD, "ibm-watsonx-ai SDK", "not installed - pip install -e '.[granite]'")
        failures += 1

    print()
    failures += _report_configuration()

    if failures:
        print(f"\n{failures} problem(s). The advisor cannot run until these are fixed.")
        return 1

    print("\nConfiguration looks complete.")

    if access or live:
        print("\nChecking IBM access (no model tokens are spent)...")
        if _check_access() != 0:
            return 1

    if not live:
        if not access:
            print("Run with --access to verify the credentials without spending tokens,")
            print("or --live to also make one real watsonx call.")
        return 0

    print("\nCalling watsonx...")
    try:
        from pydantic import BaseModel

        from phase_c.llm.granite import GraniteClient

        class _Ping(BaseModel):
            status: str

        # A tiny reply cap: this is a reachability check, not a workload.
        client = GraniteClient(max_new_tokens=24, retries=0)
        reply = client.complete(
            system="AGENT: doctor\nYou reply with JSON only.",
            user='Reply exactly: {"status": "ok"}',
            schema=_Ping,
        )
        _line(
            OK,
            "watsonx call",
            f"{client.model_id} at {client.url} replied status={reply.status!r}",
        )
        return 0
    except Exception as exc:
        # The message is already sanitized by the client's error classifier.
        _line(BAD, "watsonx call", str(exc))
        return 1


def analyze(path: str, focus: str | None, samples: int, seed: int | None) -> int:
    from phase_c.llm.granite import GraniteClient
    from phase_c.orchestrator import Orchestrator
    from phase_c.providers.phase_a import PhaseASimulationAdapter, load_scenario

    scenario = load_scenario(path)
    case = PhaseASimulationAdapter().analyze_case(scenario, samples=samples, seed=seed)
    package = Orchestrator(GraniteClient(), focus_action_id=focus).run(case)

    print(json.dumps(package.model_dump(mode="json"), indent=2, ensure_ascii=False))

    violations = package.critic.grounding_violations
    if violations:
        print(
            f"\n{len(violations)} grounding violation(s) - an agent asserted "
            "something the simulation does not support.",
            file=sys.stderr,
        )
    return 0


def main() -> None:
    config.load_env()

    parser = argparse.ArgumentParser(prog="phase-c", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_cmd = sub.add_parser("doctor", help="check install and watsonx configuration")
    doctor_cmd.add_argument(
        "--access",
        action="store_true",
        help="verify the key, project and model against IBM without spending tokens",
    )
    doctor_cmd.add_argument(
        "--live", action="store_true", help="also make one real watsonx call"
    )

    analyze_cmd = sub.add_parser("analyze", help="run the pipeline over a scenario")
    analyze_cmd.add_argument("scenario", help="Phase A scenario JSON")
    analyze_cmd.add_argument("--focus", default=None, help="action id to analyze in depth")
    analyze_cmd.add_argument("--samples", type=int, default=20)
    analyze_cmd.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    if args.command == "doctor":
        raise SystemExit(doctor(args.live, args.access))
    raise SystemExit(analyze(args.scenario, args.focus, args.samples, args.seed))


if __name__ == "__main__":
    main()
