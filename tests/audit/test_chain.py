import json
from pathlib import Path

import jsonschema
import psycopg
import pytest

from orquesta.audit.chain import AuditRecord, append, verify
from orquesta.audit.key import load_key
from orquesta.cli import main
from orquesta.errors import AuditChainBroken, AuditKeyInsecure

CONTRACT = json.loads((Path(__file__).parents[2] / "contracts" / "audit-event.schema.json").read_text())
CANARY = "sk-canario-a1b2c3d4e5f6g7h8"
SHA = "a" * 40


def record(index: int, **changes) -> AuditRecord:
    base = {
        "actor": "someone",
        "tenant": "acme",
        "kind": "policy_decision",
        "policy_sha": SHA,
        "asset_set_sha": SHA,
        "tools": ["Bash"],
        "decision": f"deny:readonly-repo #{index}",
        "latency_ms": index,
        "refs": {"rule_id": "readonly-repo"},
    }
    return AuditRecord.model_validate({**base, **changes})


def fill(writer_dsn: str, key: bytes, count: int = 5) -> None:
    with psycopg.connect(writer_dsn) as conn:
        for index in range(1, count + 1):
            append(conn, key, record(index))


def test_an_untouched_chain_verifies(dsns, key_file) -> None:
    _, writer = dsns
    key = load_key(key_file)
    fill(writer, key)
    with psycopg.connect(writer) as conn:
        assert verify(conn, key) == 5


@pytest.mark.parametrize(
    "tamper",
    [
        "UPDATE audit_events SET decision = 'allow:none' WHERE seq = 3",
        'UPDATE audit_events SET refs = \'{"rule_id": "otro"}\' WHERE seq = 3',
        "DELETE FROM audit_events WHERE seq = 3",
        "UPDATE audit_events SET latency_ms = 0 WHERE seq = 3",
    ],
)
def test_altering_or_deleting_a_middle_event_breaks_the_chain(dsns, key_file, tamper: str) -> None:
    owner, writer = dsns
    key = load_key(key_file)
    fill(writer, key)
    with psycopg.connect(owner, autocommit=True) as conn:
        conn.execute(tamper)
    with psycopg.connect(writer) as conn, pytest.raises(AuditChainBroken) as error:
        verify(conn, key)
    assert error.value.seq in (3, 4)
    assert error.value.exit_code == 7


def test_a_different_key_does_not_verify(dsns, key_file, tmp_path) -> None:
    _, writer = dsns
    fill(writer, load_key(key_file))
    other = tmp_path / "other.key"
    other.write_text("b" * 64)
    other.chmod(0o600)
    with psycopg.connect(writer) as conn, pytest.raises(AuditChainBroken):
        verify(conn, load_key(other))


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_events SET decision = 'x'", "DELETE FROM audit_events", "TRUNCATE audit_events"],
)
def test_writer_can_only_insert_and_select(dsns, key_file, statement: str) -> None:
    _, writer = dsns
    fill(writer, load_key(key_file), 1)
    with psycopg.connect(writer) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)


def test_a_canary_in_refs_or_decision_never_reaches_the_table(dsns, key_file) -> None:
    owner, writer = dsns
    key = load_key(key_file)
    with psycopg.connect(writer) as conn:
        append(conn, key, record(1, decision=f"error con {CANARY}", refs={"note": f"token={CANARY}", "x": CANARY}))
        assert verify(conn, key) == 1
    with psycopg.connect(owner) as conn:
        dump = json.dumps(conn.execute("SELECT row_to_json(e) FROM audit_events e").fetchall(), default=str)
    assert CANARY not in dump and "[REDACTADO]" in dump


def test_stored_rows_match_the_contract(dsns, key_file) -> None:
    _, writer = dsns
    key = load_key(key_file)
    with psycopg.connect(writer) as conn:
        append(conn, key, record(1, kind="model_call", provider="fake", model="fake-routing", cost_usd=0.0))
        row = conn.execute("SELECT row_to_json(e) FROM audit_events e").fetchone()[0]
    row["at"] = row["at"].replace(" ", "T")
    row["prev_mac"] = row["prev_mac"].removeprefix("\\x")
    row["mac"] = row["mac"].removeprefix("\\x")
    jsonschema.validate(row, CONTRACT)


def test_model_call_needs_provider_and_model(dsns, key_file) -> None:
    _, writer = dsns
    with psycopg.connect(writer) as conn, pytest.raises(psycopg.errors.CheckViolation):
        append(conn, load_key(key_file), record(1, kind="model_call"))


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604])
def test_key_with_open_permissions_exits_with_9(tmp_path, mode: int) -> None:
    path = tmp_path / "audit.key"
    path.write_text("c" * 64)
    path.chmod(mode)
    with pytest.raises(AuditKeyInsecure) as error:
        load_key(path)
    assert error.value.exit_code == 9


def test_missing_or_short_key_exits_with_9(tmp_path) -> None:
    with pytest.raises(AuditKeyInsecure):
        load_key(tmp_path / "no-existe.key")
    short = tmp_path / "short.key"
    short.write_text("corta")
    short.chmod(0o600)
    with pytest.raises(AuditKeyInsecure):
        load_key(short)


def test_cli_audit_verify(dsns, key_file, monkeypatch, capsys) -> None:
    owner, writer = dsns
    fill(writer, load_key(key_file), 3)
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    monkeypatch.setenv("ORQUESTA_AUDIT_DSN", writer)
    monkeypatch.setenv("ORQUESTA_AUDIT_KEY", str(key_file))
    assert main(["audit", "verify"]) == 0
    assert "3 eventos" in capsys.readouterr().out
    with psycopg.connect(owner, autocommit=True) as conn:
        conn.execute("UPDATE audit_events SET actor = 'otro' WHERE seq = 2")
    assert main(["audit", "verify", "--json"]) == 7
    assert json.loads(capsys.readouterr().err)["seq"] == 2


def test_cli_audit_verify_with_open_key_exits_with_9(key_file, monkeypatch) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    monkeypatch.setenv("ORQUESTA_AUDIT_DSN", "postgresql://nadie@127.0.0.1:1/x")
    key_file.chmod(0o644)
    monkeypatch.setenv("ORQUESTA_AUDIT_KEY", str(key_file))
    assert main(["audit", "verify"]) == 9
