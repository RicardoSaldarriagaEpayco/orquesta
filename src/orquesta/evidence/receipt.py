import base64
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from orquesta.errors import KeyInsecure, ReceiptInvalid

DEFAULT_KEY = Path.home() / ".config" / "orquesta" / "receipt.key"
RECEIPTS_DIR = "orquesta-receipts"


@dataclass(frozen=True)
class EvidenceReceipt:
    version: int
    repo: str
    sha: str
    tree: str
    check: str
    command: str
    tool_version: str
    result: str
    at: str
    key_id: str
    signature: str = ""

    def payload(self) -> bytes:
        data = {k: v for k, v in asdict(self).items() if k != "signature"}
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def _git(repo: str, *args: str) -> str:
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=15)
    return result.stdout.strip() if result.returncode == 0 else ""


def resolve_sha(repo: str, ref: str) -> str:
    return _git(repo, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") or ref


def public_raw(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id(public: bytes) -> str:
    return hashlib.sha256(public).hexdigest()[:16]


def encode_public(key: Ed25519PublicKey) -> str:
    return base64.b64encode(public_raw(key)).decode()


def decode_public(text: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(text))


def keygen(path: Path) -> str:
    if path.exists():
        raise KeyInsecure(str(path), "ya existe; no se sobrescribe")
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(pem)
    return encode_public(key.public_key())


def load_private(path: Path) -> Ed25519PrivateKey:
    try:
        info = path.stat()
    except OSError as error:
        raise KeyInsecure(str(path), "no existe o no se puede leer") from error
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise KeyInsecure(str(path), f"permisos {oct(info.st_mode & 0o777)}; debe ser 0600")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise KeyInsecure(str(path), "no es una llave Ed25519")
    return key


def sign(
    repo: str, check: str, command: str, tool_version: str, result: str, key: Ed25519PrivateKey
) -> EvidenceReceipt:
    sha, tree = _git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", "HEAD^{tree}")
    if not sha or not tree:
        raise ReceiptInvalid(sha or "HEAD", f"{repo} no es un repo git con commits")
    if result not in ("pass", "fail"):
        raise ReceiptInvalid(sha, "result debe ser pass o fail")
    top = _git(repo, "rev-parse", "--show-toplevel")
    unsigned = EvidenceReceipt(
        version=1,
        repo=os.path.basename(top),
        sha=sha,
        tree=tree,
        check=check,
        command=command,
        tool_version=tool_version,
        result=result,
        at=datetime.now(UTC).isoformat(timespec="seconds"),
        key_id=key_id(public_raw(key.public_key())),
    )
    signature = base64.b64encode(key.sign(unsigned.payload())).decode()
    return EvidenceReceipt(**{**asdict(unsigned), "signature": signature})


def receipt_path(repo: str, sha: str) -> Path:
    common = _git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common) / RECEIPTS_DIR / f"{sha}.json"


def store(repo: str, receipt: EvidenceReceipt) -> Path:
    path = receipt_path(repo, receipt.sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt.to_json(), indent=2) + "\n", encoding="utf-8")
    return path


def load(repo: str, sha: str) -> EvidenceReceipt:
    path = receipt_path(repo, sha)
    try:
        return EvidenceReceipt(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise ReceiptInvalid(sha, "no hay recibo legible para el commit") from error


def verify(repo: str, receipt: EvidenceReceipt, trusted: list[str]) -> EvidenceReceipt:
    keys = {key_id(base64.b64decode(k)): decode_public(k) for k in trusted}
    if receipt.key_id not in keys:
        raise ReceiptInvalid(receipt.sha, "firmado con una llave que el tenant no reconoce")
    try:
        keys[receipt.key_id].verify(base64.b64decode(receipt.signature), receipt.payload())
    except (InvalidSignature, ValueError) as error:
        raise ReceiptInvalid(receipt.sha, "la firma no corresponde al contenido") from error
    if _git(repo, "rev-parse", f"{receipt.sha}^{{tree}}") != receipt.tree:
        raise ReceiptInvalid(receipt.sha, "el commit o su árbol cambiaron")
    if receipt.result != "pass":
        raise ReceiptInvalid(receipt.sha, "la puerta no pasó")
    return receipt
