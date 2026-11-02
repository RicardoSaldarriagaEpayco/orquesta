import pytest
import yaml

from orquesta.api.auth import Principal, TokenStore, parse_grants
from orquesta.cli import main
from orquesta.errors import Forbidden, KeyInsecure, Unauthenticated


@pytest.fixture
def store(tmp_path):
    return TokenStore(tmp_path / "tokens.yaml")


def test_created_token_authenticates_and_is_stored_hashed(store):
    token = store.create("ana", parse_grants(["web-app=operator", "*=viewer"]))
    principal = store.authenticate(f"Bearer {token}")
    assert principal.actor == "ana"
    assert token not in store.path.read_text()
    assert oct(store.path.stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("header", [None, "", "Bearer", "Basic abc", "Bearer oqt_desconocido", "Bearer otro"])
def test_unknown_or_malformed_token(store, header):
    store.create("ana", parse_grants(["*=viewer"]))
    with pytest.raises(Unauthenticated):
        store.authenticate(header)


def test_roles_by_repo():
    principal = Principal("ana", parse_grants(["web-app=operator", "infra=approver"]))
    assert principal.has("operator", "web-app")
    assert not principal.has("operator", "infra")
    assert not principal.has("approver", "web-app")
    assert principal.has("viewer", "infra")
    assert not principal.has("viewer", "otro")
    assert not principal.has("operator", None)
    with pytest.raises(Forbidden) as error:
        principal.require("approver", "web-app")
    assert error.value.fields() == {"actor": "ana", "role": "approver", "repo": "web-app"}


def test_wildcard_grant_applies_to_every_repo():
    principal = Principal("ops", parse_grants(["*=approver"]))
    assert principal.has("approver", "cualquiera")
    assert principal.has("approver", None)
    assert not principal.has("operator", "cualquiera")


@pytest.mark.parametrize("value", ["web-app", "=viewer", "web-app=", "web-app=admin"])
def test_invalid_grants(value):
    with pytest.raises(ValueError):
        parse_grants([value])


def test_world_readable_file_is_rejected(store):
    token = store.create("ana", parse_grants(["*=viewer"]))
    store.path.chmod(0o644)
    with pytest.raises(KeyInsecure):
        store.authenticate(f"Bearer {token}")


def test_corrupt_entry_fails_closed(store):
    token = store.create("ana", parse_grants(["*=viewer"]))
    data = yaml.safe_load(store.path.read_text())
    data["tokens"][0]["grants"] = {"*": ["root"]}
    store.path.write_text(yaml.safe_dump(data))
    with pytest.raises(KeyInsecure):
        store.authenticate(f"Bearer {token}")


def test_cli_creates_token(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ORQUESTA_ACTOR", "ops")
    path = tmp_path / "tokens.yaml"
    assert main(["token", "create", "--actor", "ana", "--grant", "web-app=viewer", "--file", str(path)]) == 0
    token = capsys.readouterr().out.strip()
    assert TokenStore(path).authenticate(f"Bearer {token}").has("viewer", "web-app")
    assert main(["token", "create", "--actor", "ana", "--grant", "web-app=root", "--file", str(path)]) == 2
