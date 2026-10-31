import re

MARK = "[REDACTADO]"
DETECTORS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"\b[0-9a-f]{32}\b"),
    re.compile(r"(?=[A-Za-z0-9+=]*[A-Z])(?=[A-Za-z0-9+=]*[a-z])(?=[A-Za-z0-9+=]*[0-9])[A-Za-z0-9+=]{32,}"),
]
SHA = re.compile(r"^[0-9a-f]{40}$")


def redact(text: str) -> str:
    for detector in DETECTORS:
        text = detector.sub(MARK, text)
    return text


def redact_refs(refs: dict[str, str]) -> dict[str, str]:
    return {redact(key): value if SHA.match(value) else redact(value) for key, value in refs.items()}
