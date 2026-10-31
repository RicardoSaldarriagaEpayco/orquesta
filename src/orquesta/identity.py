import os
import re
import subprocess
from collections.abc import Mapping

from orquesta.errors import IdentityMissing

GH_ACCOUNT = re.compile(r"account (\S+)")


def gh_account() -> str | None:
    try:
        result = subprocess.run(["gh", "auth", "status", "--active"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = GH_ACCOUNT.search(result.stdout + result.stderr)
    return match.group(1) if match else None


def resolve_actor(env: Mapping[str, str] = os.environ) -> str:
    actor = env.get("ORQUESTA_ACTOR", "").strip() or gh_account()
    if not actor:
        raise IdentityMissing()
    return actor
