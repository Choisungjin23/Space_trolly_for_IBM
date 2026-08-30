"""An OS variable silently outranks backend/.env. That is intended, but it is
also the failure that looks like a broken key: the file is edited, the app
restarts, and a stale credential is still in play. These tests pin the
diagnostics that make it visible."""

import pytest

from phase_c import config
from phase_c.config import WatsonxConfig
from phase_c.llm.granite import _classify


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "WATSONX_API_KEY=from-the-file\n"
        "WATSONX_PROJECT_ID=proj-file\n"
        "WATSONX_URL=https://us-south.ml.cloud.ibm.com\n"
        "WATSONX_MODEL_ID=ibm/granite-4-h-small\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(config.ENV_FILE_VAR, str(path))
    return path


def test_a_matching_value_is_reported_as_coming_from_the_file(env_file, monkeypatch):
    monkeypatch.setenv("WATSONX_API_KEY", "from-the-file")
    assert config.value_sources()["WATSONX_API_KEY"] == "backend/.env"


def test_a_shell_value_that_disagrees_is_reported_as_overriding(env_file, monkeypatch):
    monkeypatch.setenv("WATSONX_API_KEY", "a-stale-key-from-the-shell")
    source = config.value_sources()["WATSONX_API_KEY"]
    assert "overriding" in source


def test_an_unset_value_is_reported_as_unset(env_file, monkeypatch):
    monkeypatch.delenv("WATSONX_API_KEY", raising=False)
    assert config.value_sources()["WATSONX_API_KEY"] == "unset"


def test_fingerprints_distinguish_keys_without_revealing_them():
    secret = "super-secret-key-value"
    tag = config.fingerprint(secret)

    assert secret not in tag
    assert len(tag) == 8
    assert tag != config.fingerprint("a-different-key")
    assert tag == config.fingerprint(secret)  # stable
    assert config.fingerprint(None) == "none"


# ── IAM rejections ──────────────────────────────────────────────────────────

CONFIG = WatsonxConfig(
    api_key="k" * 44,
    project_id="proj",
    url="https://us-south.ml.cloud.ibm.com",
    model_id="ibm/granite-4-h-small",
)


def _iam(code: str, message: str) -> Exception:
    return Exception(
        "Attempt of authenticating connection to service failed, please validate "
        'your credentials. Error: {"errorCode":"' + code + '","errorMessage":"'
        + message + '","context":{"requestId":"abc"}}'
    )


def test_a_disabled_key_is_named_as_disabled():
    """IAM rejections arrive with no HTTP status, so the status branches never
    see them; without this they degraded to a generic failure."""
    text = _classify(_iam("BXNIM0462E", "Provided API key is disabled."), CONFIG)

    assert "DISABLED" in text
    assert "BXNIM0462E" in text


def test_a_missing_key_is_distinguished_from_a_disabled_one():
    text = _classify(_iam("BXNIM0415E", "Provided API key could not be found."), CONFIG)

    assert "no such API key" in text
    assert "DISABLED" not in text


def test_an_unknown_iam_code_is_still_reported_verbatim():
    text = _classify(_iam("BXNIM9999E", "Something new."), CONFIG)

    assert "BXNIM9999E" in text
    assert "Something new." in text


def test_a_credential_never_appears_in_a_classified_error(monkeypatch):
    monkeypatch.setenv("WATSONX_API_KEY", "SECRET-KEY-MUST-NOT-LEAK")

    text = _classify(_iam("BXNIM0462E", "Provided API key is disabled."), CONFIG)

    assert "SECRET-KEY-MUST-NOT-LEAK" not in text
    assert CONFIG.api_key not in text
    assert CONFIG.project_id not in text


# ── watsonx service codes ───────────────────────────────────────────────────

class _Resp:
    def __init__(self, status):
        self.status_code = status


def _service(status: int, body: str) -> Exception:
    exc = Exception(f"Failure during chat. Status code: {status}, body: {body}")
    exc.response = _Resp(status)  # type: ignore[attr-defined]
    return exc


QUOTA_BODY = (
    '{"errors":[{"code":"token_quota_reached","message":"Request of 1 token(s) '
    'from quota was rejected"}],"trace":"abc","status_code":403}'
)


def test_an_exhausted_quota_is_not_reported_as_a_permission_problem():
    """Both arrive as HTTP 403 but need opposite fixes: one is an account
    limit that resets, the other means the key cannot see the project."""
    text = _classify(_service(403, QUOTA_BODY), CONFIG)

    assert "quota is exhausted" in text
    assert "lacks access" not in text


def test_a_bare_403_is_still_read_as_a_permission_problem():
    text = _classify(_service(403, "forbidden"), CONFIG)

    assert "permission denied" in text


def test_an_unsupported_model_code_names_the_model_variable():
    body = '{"errors":[{"code":"model_not_supported","message":"nope"}]}'
    text = _classify(_service(400, body), CONFIG)

    assert "WATSONX_MODEL_ID" in text


def test_an_unknown_service_code_falls_back_to_the_status():
    body = '{"errors":[{"code":"something_new","message":"hm"}]}'
    text = _classify(_service(500, body), CONFIG)

    assert "500" in text
