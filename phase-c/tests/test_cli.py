"""The `phase-c` console entry point must exist and report configuration
honestly, without ever printing a credential."""

import phase_c.cli as cli


def test_doctor_reports_missing_credentials(monkeypatch, capsys):
    monkeypatch.delenv("WATSONX_API_KEY", raising=False)
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)

    exit_code = cli.doctor(live=False)
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "WATSONX_API_KEY" in out
    assert "not set" in out
    assert "cannot run" in out


def test_doctor_passes_when_configured(monkeypatch, capsys):
    monkeypatch.setenv("WATSONX_API_KEY", "x" * 44)
    monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-123")

    exit_code = cli.doctor(live=False)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Configuration looks complete" in out


def test_doctor_never_prints_the_key(monkeypatch, capsys):
    secret = "SUPER-SECRET-KEY-VALUE-0123456789"
    monkeypatch.setenv("WATSONX_API_KEY", secret)
    monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-123")

    cli.doctor(live=False)
    out = capsys.readouterr().out

    assert secret not in out
    assert f"({len(secret)} characters)" in out


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


def test_doctor_output_is_ascii_safe(monkeypatch, capsys):
    monkeypatch.setenv("WATSONX_API_KEY", "k" * 10)
    monkeypatch.setenv("WATSONX_PROJECT_ID", "p")

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
