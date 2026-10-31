import argparse
import re
import subprocess
import sys
from pathlib import Path


def load_terms(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True, timeout=60)
    return [root / name for name in result.stdout.decode().split("\0") if name]


def scan(root: Path, terms: list[str]) -> list[tuple[str, int, int]]:
    patterns = [re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.IGNORECASE) for term in terms]
    hits = []
    for file in tracked_files(root):
        try:
            text = file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            hits.extend(
                (str(file.relative_to(root)), number, index) for index, p in enumerate(patterns, 1) if p.search(line)
            )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Falla si un archivo trackeado contiene un término del tenant.")
    parser.add_argument("--terms-file", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        terms = load_terms(args.terms_file)
    except OSError as error:
        print(f"no se pudo leer la lista de términos: {error.strerror}", file=sys.stderr)
        return 2
    if not terms:
        print("la lista de términos está vacía", file=sys.stderr)
        return 2
    hits = scan(args.root, terms)
    for file, line, index in hits:
        print(f"{file}:{line}: término #{index} de la lista")
    print(f"{len(hits)} coincidencias con {len(terms)} términos", file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
