import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tenant_leak.py"


def run(root: Path, terms: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--terms-file", str(terms), "--root", str(root)], capture_output=True, text=True
    )


def test_flags_a_term_without_printing_it(repo, tmp_path: Path) -> None:
    repo.commit({"docs/a.md": "integración con AcmeCorp\n"})
    terms = tmp_path / "terms.txt"
    terms.write_text("# comentario\nacmecorp\n")
    result = run(repo.path, terms)
    assert result.returncode == 1
    assert "docs/a.md:1" in result.stdout
    assert "acme" not in (result.stdout + result.stderr).lower()


def test_term_inside_a_longer_word_does_not_count(repo, tmp_path: Path) -> None:
    repo.commit({"a.md": "acmecorporation\n"})
    terms = tmp_path / "terms.txt"
    terms.write_text("acmecorp\n")
    assert run(repo.path, terms).returncode == 0


def test_untracked_files_are_ignored(repo, tmp_path: Path) -> None:
    repo.commit({"a.md": "limpio\n"})
    (repo.path / "local.md").write_text("acmecorp\n")
    terms = tmp_path / "terms.txt"
    terms.write_text("acmecorp\n")
    assert run(repo.path, terms).returncode == 0


def test_missing_or_empty_terms_fail_closed(repo, tmp_path: Path) -> None:
    repo.commit({"a.md": "limpio\n"})
    empty = tmp_path / "empty.txt"
    empty.write_text("\n# solo comentarios\n")
    assert run(repo.path, empty).returncode == 2
    assert run(repo.path, tmp_path / "no-existe.txt").returncode == 2
