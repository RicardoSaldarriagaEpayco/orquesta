import json
import stat
from pathlib import Path

import pytest

from orquesta.cli import main

ARGS = ["audit", "verify"]


@pytest.fixture
def no_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("ORQUESTA_ACTOR", raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    return bin_dir


def fake_gh(bin_dir: Path, output: str, code: int) -> None:
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\necho '{output}'\nexit {code}\n")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)


def test_without_identity_does_not_start(no_identity: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(ARGS) == 1
    assert "IdentityMissing" in capsys.readouterr().err


def test_without_identity_reports_json(no_identity: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*ARGS, "--json"]) == 1
    assert json.loads(capsys.readouterr().err)["error"] == "IdentityMissing"


def test_gh_without_session_is_not_identity(no_identity: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_gh(no_identity, "You are not logged into any GitHub hosts.", 1)
    assert main(ARGS) == 1
    assert "IdentityMissing" in capsys.readouterr().err


def test_gh_session_is_identity(no_identity: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_gh(no_identity, "Logged in to github.com account someone (keyring)", 0)
    assert main(ARGS) == 1
    assert "todavía no implementado" in capsys.readouterr().err


def test_actor_variable_is_identity(
    no_identity: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    assert main(ARGS) == 1
    assert "IdentityMissing" not in capsys.readouterr().err


def test_unknown_command_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["deploy"])
    assert exit_info.value.code == 2
