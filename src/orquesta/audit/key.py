import os
import stat
from pathlib import Path

from orquesta.errors import AuditKeyInsecure

DEFAULT_KEY = Path.home() / ".config" / "orquesta" / "audit.key"


def key_path() -> Path:
    return Path(os.environ.get("ORQUESTA_AUDIT_KEY", str(DEFAULT_KEY)))


def load_key(path: Path | None = None) -> bytes:
    path = path or key_path()
    try:
        info = path.stat()
    except OSError as error:
        raise AuditKeyInsecure(str(path), "no existe o no se puede leer") from error
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise AuditKeyInsecure(str(path), f"permisos {oct(info.st_mode & 0o777)}; debe ser 0600")
    key = path.read_bytes().strip()
    if len(key) < 32:
        raise AuditKeyInsecure(str(path), "tiene menos de 32 bytes")
    return key
