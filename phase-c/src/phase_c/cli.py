"""Phase C command line.

    phase-c doctor            check the install and the LLM configuration
    phase-c doctor --live     also make one real Granite call
    phase-c analyze <file>    run the full pipeline over a Phase A scenario JSON

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

OK = "  ok   "
BAD = " FAIL  "
WARN = " warn  "

REQUIRED_VARS = ("WATSONX_PROJECT_ID",)
# Either of these supplies the key; the file form keeps the secret out of
# environment listings and shell history.
KEY_VARS = ("WATSONX_API_KEY", "WATSONX_APIKEY_FILE")
OPTIONAL_VARS = ("WATSONX_URL", "WATSONX_MODEL_ID")


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" - {detail}" if detail else ""))


def doctor(live: bool) -> int:
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
        _line(BAD, "ibm-watsonx-ai SDK", 'not installed - pip install -e ".[granite]"')
        failures += 1

    print()
    key_source = None
    for name in KEY_VARS:
        value = os.environ.get(name)
        if not value:
            continue
        key_source = name
        if name.endswith("API_KEY"):
            # Never print the secret; length is enough to catch a bad paste.
            _line(OK, name, f"set ({len(value)} characters)")
        else:
            exists = Path(value).is_file()
            _line(OK if exists else BAD, name, value if exists else f"{value} (missing)")
            if not exists:
                failures += 1
        break
    if key_source is None:
        _line(BAD, "API key", "set WATSONX_API_KEY or WATSONX_APIKEY_FILE")
        failures += 1

    for name in REQUIRED_VARS:
        value = os.environ.get(name)
        if not value:
            _line(BAD, name, "not set")
            failures += 1
        else:
            _line(OK, name, value)

    for name in OPTIONAL_VARS:
        value = os.environ.get(name)
        _line(OK if value else WARN, name, value or "not set, using the default")

    if failures:
        print(f"\n{failures} problem(s). The advisor cannot run until these are fixed.")
        return 1

    print("\nConfiguration looks complete.")

    if not live:
        print("Run with --live to make one real Granite call.")
        return 0

    print("\nCalling Granite...")
    try:
        from pydantic import BaseModel

        from phase_c.llm.granite import GraniteClient

        class _Ping(BaseModel):
            status: str

        client = GraniteClient()
        reply = client.complete(
            system="AGENT: doctor\nYou reply with JSON only.",
            user='Reply exactly: {"status": "ok"}',
            schema=_Ping,
        )
        _line(OK, "Granite call", f"model {client.model_id} replied status={reply.status!r}")
        return 0
    except Exception as exc:
        _line(BAD, "Granite call", str(exc))
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
    parser = argparse.ArgumentParser(prog="phase-c", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_cmd = sub.add_parser("doctor", help="check install and LLM configuration")
    doctor_cmd.add_argument(
        "--live", action="store_true", help="also make one real Granite call"
    )

    analyze_cmd = sub.add_parser("analyze", help="run the pipeline over a scenario")
    analyze_cmd.add_argument("scenario", help="Phase A scenario JSON")
    analyze_cmd.add_argument("--focus", default=None, help="action id to analyze in depth")
    analyze_cmd.add_argument("--samples", type=int, default=20)
    analyze_cmd.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    if args.command == "doctor":
        raise SystemExit(doctor(args.live))
    raise SystemExit(analyze(args.scenario, args.focus, args.samples, args.seed))


if __name__ == "__main__":
    main()
