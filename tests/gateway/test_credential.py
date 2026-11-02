import os

import pytest

from orquesta.errors import CredentialInvalid, KeyInsecure
from orquesta.gateway.credential import MAX_TTL_S, EpisodeAllowlist, issue, load_key, verify
from orquesta.gateway.gateway import Allowlist

KEY = b"k" * 32
NOW = 1_800_000_000.0


def clock(at: float = NOW):
    return lambda: at


def token(**overrides) -> str:
    args = {"run_id": "run-1", "models": ["anthropic/claude-*"], "budget_usd": 0.5, "now": clock()}
    return issue(KEY, **{**args, **overrides})


def test_round_trip():
    claims = verify(KEY, token(), "run-1", clock(NOW + 60))
    assert claims.run_id == "run-1"
    assert claims.models == ("anthropic/claude-*",)
    assert claims.budget_usd == 0.5
    assert claims.exp == NOW + MAX_TTL_S


@pytest.mark.parametrize(
    ("make", "run_id", "at", "reason"),
    [
        (lambda: token(), "run-1", NOW + MAX_TTL_S, "vencida"),
        (lambda: token(), "run-2", NOW, "de otra corrida"),
        (lambda: token()[:-2] + "AA", "run-1", NOW, "firma"),
        (lambda: issue(b"z" * 32, "run-1", ["a/b"], 1, now=clock()), "run-1", NOW, "firma"),
        (lambda: "oqe1.sin-firma", "run-1", NOW, "formato"),
        (lambda: "otro." + token().split(".", 1)[1], "run-1", NOW, "formato"),
    ],
)
def test_rejections(make, run_id, at, reason):
    with pytest.raises(CredentialInvalid) as error:
        verify(KEY, make(), run_id, clock(at))
    assert error.value.reason == reason
    assert error.value.exit_code == 14


def test_ttl_is_capped_at_issue():
    with pytest.raises(ValueError):
        token(ttl_s=MAX_TTL_S + 1)
    with pytest.raises(ValueError):
        token(models=[])


def test_clock_skew_beyond_ttl_is_rejected():
    future = token(now=clock(NOW + 3600))
    with pytest.raises(CredentialInvalid) as error:
        verify(KEY, future, "run-1", clock(NOW))
    assert error.value.reason == "vigencia mayor a la permitida"


def test_episode_allowlist_is_intersection_with_tenant():
    claims = verify(KEY, token(models=["anthropic/*", "openai/gpt-x"]), "run-1", clock())
    scoped = EpisodeAllowlist(Allowlist(["anthropic/claude-a"]), claims)
    assert scoped.allows("anthropic", "claude-a")
    assert not scoped.allows("anthropic", "claude-b")
    assert not scoped.allows_provider("openai")


def test_key_must_be_private(tmp_path):
    path = tmp_path / "gateway.key"
    path.write_bytes(os.urandom(16).hex().encode() * 2)
    path.chmod(0o644)
    with pytest.raises(KeyInsecure):
        load_key(path)
    path.chmod(0o600)
    assert len(load_key(path)) >= 32
