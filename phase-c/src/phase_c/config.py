"""watsonx.ai configuration.

Every IBM value comes from the environment, which in normal local development
is populated from ``phase-b/spacecraft-sim/backend/.env``.

Nothing is captured at import time. ``WatsonxConfig.from_env()`` reads the
environment when a client or a diagnostic actually asks for it, so a ``.env``
loaded during application startup is always visible - and there are no baked-in
model or region defaults to silently mask a missing value.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE_VAR = "WATSONX_ENV_FILE"

# The repository ships one .env, next to the backend that owns startup.
_REPO_BACKEND_ENV = (
    Path(__file__).resolve().parents[3]
    / "phase-b"
    / "spacecraft-sim"
    / "backend"
    / ".env"
)

REQUIRED_VARS = (
    "WATSONX_API_KEY",
    "WATSONX_PROJECT_ID",
    "WATSONX_URL",
    "WATSONX_MODEL_ID",
)

_PLACEHOLDER_PREFIXES = ("YOUR_", "PUT_YOUR_", "REPLACE_", "CHANGE_ME", "<")
_PLACEHOLDER_FRAGMENTS = ("YOUR_REGION", "YOUR_IBM", "YOUR_WATSONX", "YOUR_PROJECT")


class ConfigError(RuntimeError):
    """Configuration is missing, or still holds an unedited example value."""


def is_placeholder(value: str | None) -> bool:
    """True when a value is absent or is still the text from .env.example."""
    normalized = (value or "").strip().upper()
    if not normalized:
        return True
    if normalized.startswith(_PLACEHOLDER_PREFIXES):
        return True
    return any(fragment in normalized for fragment in _PLACEHOLDER_FRAGMENTS)


def _env_file_candidates(path: str | Path | None) -> list[Path]:
    if path is not None:
        return [Path(path)]
    explicit = os.environ.get(ENV_FILE_VAR)
    if explicit:
        return [Path(explicit)]
    return [Path.cwd() / ".env", _REPO_BACKEND_ENV]


def load_env(path: str | Path | None = None) -> Path | None:
    """Populate os.environ from a .env file. Returns the file used, if any.

    Real operating-system variables win, so deployment configuration keeps
    working and a shell override is still possible.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a declared dep
        return None

    for candidate in _env_file_candidates(path):
        if candidate.is_file():
            load_dotenv(dotenv_path=candidate, override=False)
            return candidate
    return None


def fingerprint(secret: str | None) -> str:
    """A short, one-way tag for a credential.

    Enough to tell two keys apart — "the app is using a different key from the
    one in my .env" is otherwise invisible — while revealing nothing about the
    key itself.
    """
    if not secret:
        return "none"
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


def value_sources(path: str | Path | None = None) -> dict[str, str]:
    """Where each watsonx value actually came from.

    A real operating-system variable silently outranks the .env file. That is
    deliberate — it is how deployments override configuration — but it also
    means someone can edit .env, restart, and still run on a stale key with no
    hint as to why. Naming the source turns that into a visible fact.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - python-dotenv is a declared dep
        return {}

    file_values: dict[str, str | None] = {}
    for candidate in _env_file_candidates(path):
        if candidate.is_file():
            file_values = dict(dotenv_values(candidate))
            break

    sources: dict[str, str] = {}
    for name in REQUIRED_VARS + ("IBM_BUDGET_USD",):
        live = os.environ.get(name)
        in_file = file_values.get(name)
        if live is None:
            sources[name] = "unset"
        elif in_file is None:
            sources[name] = "OS environment"
        elif live == in_file:
            sources[name] = "backend/.env"
        else:
            # The dangerous case: both exist and disagree.
            sources[name] = "OS environment (overriding backend/.env)"
    return sources


def _read_api_key() -> str | None:
    """Prefer an explicit env var; otherwise read the key out of the JSON file
    IBM hands you. The value is returned, never logged or persisted."""
    key = os.environ.get("WATSONX_API_KEY")
    if key:
        return key

    key_file = os.environ.get("WATSONX_APIKEY_FILE")
    if not key_file:
        return None

    path = Path(key_file)
    if not path.is_file():
        raise ConfigError(f"WATSONX_APIKEY_FILE points at a missing file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"WATSONX_APIKEY_FILE is not valid JSON: {exc}") from exc

    value = data.get("apikey") or data.get("api_key")
    if not value:
        raise ConfigError(
            f"No 'apikey' field in {path.name}. Expected the JSON IBM Cloud "
            "gives you when you create an API key."
        )
    return value


_HINTS = {
    "WATSONX_API_KEY": (
        "Create one at IBM Cloud > Manage > Access (IAM) > API keys, or point "
        "WATSONX_APIKEY_FILE at the JSON file IBM gave you."
    ),
    "WATSONX_PROJECT_ID": (
        "Open your watsonx.ai project, then Manage > General > Details. It must "
        "be a project in the same region as WATSONX_URL."
    ),
    "WATSONX_URL": (
        "The regional endpoint, for example https://us-south.ml.cloud.ibm.com "
        "for Dallas."
    ),
    "WATSONX_MODEL_ID": (
        "The foundation model to call, for example ibm/granite-4-h-small."
    ),
}


def configuration_problems() -> list[str]:
    """Sanitized, human-readable reasons the advisor cannot run. Never
    includes a credential value."""
    problems: list[str] = []

    try:
        api_key = _read_api_key()
    except ConfigError as exc:
        problems.append(str(exc))
        api_key = None

    values = {
        "WATSONX_API_KEY": api_key,
        "WATSONX_PROJECT_ID": os.environ.get("WATSONX_PROJECT_ID"),
        "WATSONX_URL": os.environ.get("WATSONX_URL"),
        "WATSONX_MODEL_ID": os.environ.get("WATSONX_MODEL_ID"),
    }

    for name in REQUIRED_VARS:
        value = values[name]
        if value is None or not value.strip():
            if name == "WATSONX_API_KEY" and problems:
                continue  # the key-file failure above already explains it
            problems.append(f"{name} is not set. {_HINTS[name]}")
        elif is_placeholder(value):
            problems.append(
                f"{name} still holds the placeholder from .env.example. {_HINTS[name]}"
            )

    url = values["WATSONX_URL"]
    if url and not is_placeholder(url) and not url.strip().startswith("https://"):
        problems.append("WATSONX_URL must be an https:// endpoint.")

    return problems


@dataclass(frozen=True)
class WatsonxConfig:
    api_key: str
    project_id: str
    url: str
    model_id: str

    @classmethod
    def from_env(cls, *, load_dotenv_file: bool = True) -> "WatsonxConfig":
        """Read and validate the configuration. Raises ConfigError listing
        every problem at once, so one run fixes them all."""
        if load_dotenv_file:
            load_env()

        problems = configuration_problems()
        if problems:
            raise ConfigError(
                "watsonx.ai is not configured in backend/.env:\n  - "
                + "\n  - ".join(problems)
            )

        return cls(
            api_key=_read_api_key() or "",
            project_id=os.environ["WATSONX_PROJECT_ID"].strip(),
            url=os.environ["WATSONX_URL"].strip(),
            model_id=os.environ["WATSONX_MODEL_ID"].strip(),
        )

    def describe(self) -> dict:
        """Safe-to-publish view: identifies the environment, never the key."""
        return {
            "configured": True,
            "model_id": self.model_id,
            "watsonx_url": self.url,
            "region": self.region,
        }

    @property
    def region(self) -> str:
        """The regional prefix of the endpoint, e.g. 'us-south' for Dallas."""
        host = self.url.split("://", 1)[-1]
        return host.split(".", 1)[0]
