import os
import re
import shlex
from dataclasses import dataclass, field

UNC = re.compile(r"^[\\/]{2}wsl(?:\.localhost|\$)[\\/][^\\/]+(.*)$", re.IGNORECASE)
SEGMENTS = re.compile(r"\|\||&&|;|\n|\|")
REDIRECT = re.compile(r">{1,2}(?!&)\s*([^\s;&|<>]+)")
PREFIXES = {"sudo", "env", "command", "time", "nohup", "builtin"}
CHANGE_DIR = {"cd", "set-location", "pushd", "sl"}


def linux(path: str) -> str:
    match = UNC.match(path)
    if not match:
        return path
    return match.group(1).replace("\\", "/") or "/"


def resolve(path: str, base: str) -> str:
    path = os.path.expanduser(linux(path.strip("'\"")))
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(base, path))


def inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


@dataclass
class Command:
    words: list[str]
    cwd: str
    segment: str
    redirects: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.words[0].lower() if self.words else ""

    def after(self, program: str) -> list[str] | None:
        return self.words[self.words.index(program) + 1 :] if program in self.words else None


def commands(text: str, cwd: str, posix: bool) -> list[Command]:
    parsed = []
    for segment in SEGMENTS.split(text):
        redirects = [resolve(target, cwd) for target in REDIRECT.findall(segment)]
        try:
            words = shlex.split(segment, posix=posix)
        except ValueError:
            words = segment.split()
        words = [w.strip("'\"") for w in words if not re.match(r"^\d*>{1,2}|^<", w)]
        while words and (words[0] in PREFIXES or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])):
            words = words[1:]
        if words and words[0].lower() in CHANGE_DIR and len(words) > 1:
            cwd = resolve(words[1], cwd)
            continue
        parsed.append(Command(words, cwd, segment, redirects))
    return parsed


def git_target(words: list[str], cwd: str) -> tuple[list[str], str]:
    rest, target = list(words), cwd
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag == "-C" and rest:
            target = resolve(rest.pop(0), target)
        elif flag in ("-c", "--git-dir", "--work-tree", "--namespace") and rest:
            rest.pop(0)
    return rest, target


def option(words: list[str], *names: str) -> str:
    for index, word in enumerate(words):
        for name in names:
            if word == name and index + 1 < len(words):
                return words[index + 1]
            if word.startswith(name + "="):
                return word.split("=", 1)[1]
    return ""
