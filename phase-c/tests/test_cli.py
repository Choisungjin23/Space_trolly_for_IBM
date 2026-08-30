"""The `phase-c` console entry point must exist and report configuration
honestly, without ever printing a credential."""

import pytest

import phase_c.cli as cli
from phase_c import config


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("WATSONX_API_KEY", "x" * 44)
    monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-123")
    monkeypatch.setenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    monkeypatch.setenv("WATSONX_MODEL_ID", "ibm/granite-4-h-small")
    monkeypatch.delenv("WATSONX_APIKEY_FILE", raising=False)
    return monkeypatch


def test_doctor_reports_missing_credentials(monkeypatch, capsys):
    for name in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL", "WATSONX_MODEL_ID"):
        monkeypatch.delenv(name, raising=False)

    exit_code = cli.doctor(live=False)
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "WATSONX_API_KEY" in out
    assert "not set" in out
    assert "cannot run" in out


def test_doctor_requires_a_url_and_a_model(configured, capsys):
    """Neither has a built-in default any more, so an unset one must fail
    rather than quietly pointing the advisor somewhere else."""
    configured.delenv("WATSONX_MODEL_ID", raising=False)

    exit_code = cli.doctor(live=False)
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "WATSONX_MODEL_ID" in out


def test_doctor_passes_when_configured(configured, capsys):
    exit_code = cli.doctor(live=False)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Configuration looks complete" in out


def test_doctor_shows_the_region_and_model_it_will_use(configured, capsys):
    cli.doctor(live=False)
    out = capsys.readouterr().out

    assert "https://us-south.ml.cloud.ibm.com" in out
    assert "ibm/granite-4-h-small" in out


def test_doctor_never_prints_the_key(configured, capsys):
    secret = "SUPER-SECRET-KEY-VALUE-0123456789"
    configured.setenv("WATSONX_API_KEY", secret)

    cli.doctor(live=False)
    out = capsys.readouterr().out

    assert secret not in out
    assert f"{len(secret)} characters" in out
    # The fingerprint identifies the key without disclosing any of it.
    assert config.fingerprint(secret) in out


def test_doctor_never_prints_the_project_id(configured, capsys):
    """The project ID is an account-scoped identifier, so doctor confirms it is
    present without publishing it."""
    project = "PROJECT-ID-THAT-MUST-NOT-APPEAR"
    configured.setenv("WATSONX_PROJECT_ID", project)

    cli.doctor(live=False)

    assert project not in capsys.readouterr().out


def test_cli_source_is_ascii_only():
    """Windows consoles use a legacy codepage, so any non-ASCII the CLI can
    print turns into mojibake. Checking the source catches every branch, not
    just the one a test happens to exercise."""
    from pathlib import Path

    source = Path(cli.__file__).read_text(encoding="utf-8")
    offenders = [
        (n, line) for n, line in enumerate(source.splitlines(), 1) if not line.isascii()
    ]
    assert offenders == [], offenders


def test_doctor_output_is_ascii_safe(configured, capsys):
    cli.doctor(live=False)
    capsys.readouterr().out.encode("ascii")  # raises if anything non-ASCII slipped in


def test_console_entry_point_is_wired():
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text("utf-8")
    )
    target = pyproject["project"]["scripts"]["phase-c"]
    module, function = target.split(":")
    assert module == "phase_c.cli"
    assert hasattr(cli, function)


def test_plain_doctor_makes_no_network_call(configured, capsys, monkeypatch):
    """Without a flag, doctor stays offline so it is safe and instant."""
    def explode(*a, **k):
        raise AssertionError("doctor must not reach IBM without --access/--live")

    monkeypatch.setattr(cli, "_check_access", explode)

    assert cli.doctor(live=False) == 0
    assert "no model tokens" not in capsys.readouterr().out


def test_access_mode_runs_the_token_free_check(configured, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_check_access", lambda: calls.append(1) or 0)

    exit_code = cli.doctor(live=False, access=True)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [1]
    assert "no model tokens are spent" in out


def test_a_failed_access_check_stops_before_spending_tokens(configured, monkeypatch):
    """If the credentials are refused there is no point billing an inference."""
    monkeypatch.setattr(cli, "_check_access", lambda: 1)
    monkeypatch.setattr(
        cli, "_report_configuration", lambda: 0
    )

    def explode(*a, **k):
        raise AssertionError("no inference should be attempted")

    monkeypatch.setattr("phase_c.llm.granite.GraniteClient", explode)

    assert cli.doctor(live=True) == 1
