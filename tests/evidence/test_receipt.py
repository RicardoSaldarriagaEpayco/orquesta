import json
from pathlib import Path

import jsonschema
import pytest

from orquesta.cli import main
from orquesta.errors import KeyInsecure, ReceiptInvalid
from orquesta.evidence.receipt import keygen, load, load_private, sign, store, verify
from orquesta.policy.load import GitEnvironment

CONTRACT = json.loads((Path(__file__).parents[2] / "contracts" / "evidence-receipt.schema.json").read_text())


@pytest.fixture
def signer(tmp_path):
    path = tmp_path / "keys" / "receipt.key"
    public = keygen(path)
    return load_private(path), public, path


def test_signed_receipt_matches_the_contract_and_verifies(repo, signer) -> None:
    key, public, _ = signer
    repo.commit({"a.txt": "a"})
    receipt = sign(str(repo.path), "ready", "make test", "1.0", "pass", key)
    jsonschema.validate(receipt.to_json(), CONTRACT)
    store(str(repo.path), receipt)
    assert verify(str(repo.path), load(str(repo.path), receipt.sha), [public]).sha == receipt.sha


def test_tampered_receipt_fails(repo, signer) -> None:
    key, public, _ = signer
    repo.commit({"a.txt": "a"})
    receipt = sign(str(repo.path), "ready", "make test", "1.0", "pass", key)
    forged = type(receipt)(**{**receipt.to_json(), "command": "true"})
    with pytest.raises(ReceiptInvalid, match="firma"):
        verify(str(repo.path), forged, [public])


def test_unknown_key_and_failed_check_are_rejected(repo, signer, tmp_path) -> None:
    key, public, _ = signer
    other = keygen(tmp_path / "other.key")
    repo.commit({"a.txt": "a"})
    with pytest.raises(ReceiptInvalid, match="no reconoce"):
        verify(str(repo.path), sign(str(repo.path), "ready", "c", "1", "pass", key), [other])
    with pytest.raises(ReceiptInvalid, match="no pasó"):
        verify(str(repo.path), sign(str(repo.path), "ready", "c", "1", "fail", key), [public])


def test_a_new_commit_has_no_receipt(repo, signer) -> None:
    key, public, _ = signer
    repo.commit({"a.txt": "a"})
    store(str(repo.path), sign(str(repo.path), "ready", "c", "1", "pass", key))
    later = repo.commit({"a.txt": "b"})
    with pytest.raises(ReceiptInvalid, match="no hay recibo"):
        load(str(repo.path), later)


def test_private_key_needs_0600_and_is_never_overwritten(signer) -> None:
    _, _, path = signer
    with pytest.raises(KeyInsecure, match="ya existe"):
        keygen(path)
    path.chmod(0o644)
    with pytest.raises(KeyInsecure) as error:
        load_private(path)
    assert error.value.exit_code == 9


def test_git_environment_accepts_a_signed_receipt_as_evidence(repo, signer) -> None:
    key, public, _ = signer
    sha = repo.commit({"a.txt": "a"})
    without_keys = GitEnvironment(str(repo.path))
    trusting = GitEnvironment(str(repo.path), receipt_keys=(public,))
    assert not trusting.has_receipt(str(repo.path), sha)
    store(str(repo.path), sign(str(repo.path), "ready", "c", "1", "pass", key))
    assert trusting.has_receipt(str(repo.path), sha) and not without_keys.has_receipt(str(repo.path), sha)


def test_cli_keygen_sign_and_verify(repo, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORQUESTA_ACTOR", "someone")
    repo.commit({"a.txt": "a"})
    key = tmp_path / "k" / "receipt.key"
    assert main(["receipt", "keygen", "--key", str(key)]) == 0
    public = capsys.readouterr().out.strip()
    sign_args = ["receipt", "sign", "--repo", str(repo.path), "--check", "ready", "--command", "make test"]
    assert main([*sign_args, "--tool-version", "1.0", "--result", "pass", "--key", str(key)]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "pass"
    assert main(["receipt", "verify", "--repo", str(repo.path), "--public-key", public]) == 0
    repo.commit({"a.txt": "b"})
    assert main(["receipt", "verify", "--repo", str(repo.path), "--public-key", public]) == 11
