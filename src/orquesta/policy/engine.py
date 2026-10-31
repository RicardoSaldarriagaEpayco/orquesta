import os
import re
from collections.abc import Callable

from orquesta.policy.model import Environment, PolicyDecision, PolicyRequest, Rules
from orquesta.policy.shell import Command, commands, git_target, inside, linux, option, resolve

SHELLS = {"Bash", "PowerShell"}
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "NotebookEdit": "notebook_path"}
REQUIRED = {"Bash": "command", "PowerShell": "command", "Skill": "skill", **FILE_TOOLS}
KNOWN_TOOLS = {*REQUIRED, "EnterWorktree", "Agent"}
SHELL_SPEC = re.compile(r"(^|[\s/])\.specify[\\/]|\bspecify\s+init\b")
READ_COMMANDS = {
    "cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "ls", "tree", "wc", "diff", "stat",
    "file", "pwd", "echo", "printf", "awk", "jq", "sort", "uniq", "cut", "realpath", "basename", "dirname",
    "test", "[", "true", "column", "md5sum", "sha256sum", "find", "sed", "yq",
    "get-content", "select-string", "get-childitem", "get-item", "get-location", "write-output", "write-host",
}  # fmt: skip
READ_GIT = {
    "log", "show", "diff", "status", "blame", "grep", "ls-files", "ls-tree", "rev-parse", "describe",
    "shortlog", "cat-file", "rev-list", "reflog", "branch", "remote", "config", "help", "version",
}  # fmt: skip
FIND_EFFECTS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}
BRANCH_EFFECTS = {"-d", "-D", "-m", "-M", "-c", "-C", "-f", "--delete", "--move", "--force"}

Rule = Callable[["Context"], str | None]


class Context:
    def __init__(self, request: PolicyRequest, rules: Rules, env: Environment) -> None:
        self.request, self.rules, self.env = request, rules, env
        self.tool = request.tool
        self.input = request.input
        self.cwd = linux(request.cwd)
        text = str(self.input.get("command", "")) if self.tool in SHELLS else ""
        self.text = text
        self.commands = commands(text, self.cwd, posix=self.tool == "Bash") if text else []

    def gh(self) -> list[tuple[Command, list[str]]]:
        return [(c, rest) for c in self.commands if (rest := c.after("gh")) is not None]

    def git(self) -> list[tuple[Command, list[str], str]]:
        found = []
        for c in self.commands:
            rest = c.after("git")
            if rest is not None:
                found.append((c, *git_target(rest, c.cwd)))
        return found

    def product_repo(self, path: str) -> str | None:
        if not inside(path, self.rules.root):
            return None
        probe = path
        repo = self.env.repo(probe)
        if repo is None or repo.is_workspace:
            return None
        return repo.top


def unknown_input(ctx: Context) -> str | None:
    if ctx.tool not in KNOWN_TOOLS:
        return f"{ctx.tool} no es una herramienta que el motor sepa evaluar"
    field = REQUIRED.get(ctx.tool)
    if field and not isinstance(ctx.input.get(field), str):
        return f"{ctx.tool} sin {field} legible"
    if not os.path.isabs(ctx.cwd):
        return "cwd no es una ruta absoluta"
    return None


def self_merge(ctx: Context) -> str | None:
    for _, rest in ctx.gh():
        if rest[:2] == ["pr", "merge"] or (
            rest[:1] == ["api"] and any(re.search(r"/pulls/\d+/merge$", w) for w in rest)
        ):
            return "Merge de PR bloqueado: nadie integra su propio PR; lo integra quien lo aprueba."
    return None


def push_protected(ctx: Context) -> str | None:
    for _, rest, target in ctx.git():
        if rest[:1] != ["push"] or "--delete" in rest or "-d" in rest:
            continue
        args = rest[1:]
        positional = [w for w in args if not w.startswith("-")]
        repo = ctx.env.repo(target)
        current = ctx.env.branch(repo.top) if repo else ""
        if any(w in ("--all", "--mirror") for w in args):
            targets = set(ctx.rules.protected_branches)
        elif len(positional) < 2:
            targets = {current}
        else:
            names = {spec.lstrip("+").split(":")[-1].removeprefix("refs/heads/") for spec in positional[1:]}
            targets = {current if name == "HEAD" else name for name in names}
        hit = sorted(name for name in targets if name and ctx.rules.protected(name))
        if hit:
            return f"Push directo a {', '.join(hit)} bloqueado: sube una rama propia y abre un PR con revisor."
    return None


def _pr_writes(ctx: Context) -> list[tuple[Command, list[str]]]:
    return [
        (c, rest)
        for c, rest in ctx.gh()
        if rest[:2] in (["pr", "create"], ["pr", "edit"]) or (rest[:1] == ["api"] and "pulls" in c.segment)
    ]


def ai_attribution(ctx: Context) -> str | None:
    for c, rest in _pr_writes(ctx):
        texts = [ctx.text]
        body_file = option(rest, "--body-file", "-F")
        if body_file and body_file != "-":
            texts.append(ctx.env.read_text(resolve(body_file, c.cwd)) or "")
        if any(p.search(t) for p in ctx.rules.attribution for t in texts):
            return "PR bloqueado: la descripción trae atribución de IA. Quítala y vuelve a intentarlo."
    return None


def _pr_target(ctx: Context, c: Command, rest: list[str]) -> tuple[str, str] | None:
    if rest[:2] == ["pr", "create"]:
        slug, head = option(rest, "--repo", "-R"), option(rest, "--head", "-H")
    elif rest[:1] == ["api"] and any(w in ("POST", "-f", "-F", "--field", "--raw-field") for w in rest):
        paths = [w for w in rest if re.fullmatch(r"/?repos/[^/]+/[^/]+/pulls", w)]
        if not paths:
            return None
        slug = "/".join(paths[0].strip("/").split("/")[1:3])
        head = next((w.split("=", 1)[1] for w in rest if w.startswith("head=")), "")
    else:
        return None
    directory = c.cwd
    if slug:
        name = slug.split("/")[-1]
        sibling = os.path.join(ctx.rules.root, name)
        if name == ctx.env.workspace_name:
            directory = ctx.rules.root
        elif ctx.env.repo(sibling):
            directory = sibling
    return directory, head.split(":")[-1]


def pr_without_receipt(ctx: Context) -> str | None:
    if not ctx.rules.pr_requires_receipt:
        return None
    for c, rest in ctx.gh():
        target = _pr_target(ctx, c, rest)
        if target is None:
            continue
        repo = ctx.env.repo(target[0])
        if repo is None or not inside(repo.top, ctx.rules.root):
            continue
        branch = target[1] or ctx.env.branch(repo.top)
        sha = ctx.env.head(repo.top, branch)
        if sha and not ctx.env.has_receipt(repo.top, sha):
            return f"PR bloqueado: el commit {sha[:7]} de {branch} no pasó la puerta de calidad (epw ready)."
    return None


def worktree_outside_root(ctx: Context) -> str | None:
    targets = []
    if ctx.tool == "EnterWorktree" or (ctx.tool == "Agent" and ctx.input.get("isolation") == "worktree"):
        targets.append(ctx.cwd)
    for _, rest, target in ctx.git():
        if rest[:2] == ["worktree", "add"]:
            targets.append(target)
    for target in targets:
        top = ctx.product_repo(target)
        if top:
            return f"Worktrees solo del repo del workspace. {top} es un repo de producto: usa git checkout -b ahí."
    return None


def spec_outside_root(ctx: Context) -> str | None:
    if ctx.tool == "Skill" and str(ctx.input["skill"]).split(":")[-1].startswith("speckit-"):
        top = ctx.product_repo(ctx.cwd)
        if top:
            return f"spec-kit corre solo en el workspace, no dentro de {top}."
    if ctx.tool in FILE_TOOLS:
        path = resolve(str(ctx.input[FILE_TOOLS[ctx.tool]]), ctx.cwd)
        top = ctx.product_repo(path)
        if top and os.path.relpath(path, top).split(os.sep)[0] in ("specs", ".specify"):
            return f"{path} está en un repo de producto; las specs viven solo en el workspace."
    for c in ctx.commands:
        if SHELL_SPEC.search(c.segment):
            top = ctx.product_repo(c.cwd)
            if top:
                return f"spec-kit corre solo en el workspace, no dentro de {top}."
    return None


def _git_is_read(words: list[str]) -> bool:
    rest, _ = git_target(words[1:], "")
    sub, args = (rest[0], rest[1:]) if rest else ("", [])
    if sub == "branch" and any(w in BRANCH_EFFECTS for w in args):
        return False
    if sub == "remote" and args and args[0] not in ("-v", "show", "get-url"):
        return False
    if sub == "config" and not any(w in ("--get", "--list", "-l", "--get-all") for w in args):
        return False
    return sub in READ_GIT


def _is_read(c: Command) -> bool:
    name = c.name
    if name == "git":
        return _git_is_read(c.words)
    if name not in READ_COMMANDS:
        return False
    if name in ("sed", "yq"):
        return not any(re.match(r"^-[a-zA-Z]*i", w) or w.startswith("--in-place") for w in c.words[1:])
    if name == "awk":
        return "inplace" not in " ".join(c.words)
    if name == "find":
        return not any(w in FIND_EFFECTS for w in c.words)
    return True


def readonly_repo(ctx: Context) -> str | None:
    roots = [(os.path.normpath(os.path.join(ctx.rules.root, n)), n) for n in ctx.rules.readonly_repos]

    def hit(path: str) -> str | None:
        return next((name for root, name in roots if inside(path, root)), None)

    def deny(name: str) -> str:
        return f"{name} es un repo de solo lectura: los agentes solo pueden leerlo."

    if ctx.tool in FILE_TOOLS:
        name = hit(resolve(str(ctx.input[FILE_TOOLS[ctx.tool]]), ctx.cwd))
        return deny(name) if name else None
    for c in ctx.commands:
        for target in c.redirects:
            if name := hit(target):
                return deny(name)
        if not c.words or _is_read(c):
            continue
        base = git_target(c.words[1:], c.cwd)[1] if c.name == "git" else c.cwd
        touched = [hit(base), *(hit(resolve(w, c.cwd)) for w in c.words[1:] if not w.startswith("-"))]
        touched += [
            name for _, name in roots if re.search(r"(^|[\s/'\"=])" + re.escape(name) + r"($|[/\s'\"])", c.segment)
        ]
        if name := next((t for t in touched if t), None):
            return deny(name)
    return None


RULES: list[tuple[str, Rule]] = [
    ("self-merge", self_merge),
    ("push-protected", push_protected),
    ("ai-attribution", ai_attribution),
    ("pr-without-receipt", pr_without_receipt),
    ("worktree-outside-root", worktree_outside_root),
    ("spec-outside-root", spec_outside_root),
    ("readonly-repo", readonly_repo),
]


def evaluate(request: PolicyRequest, rules: Rules, env: Environment, policy_sha: str) -> PolicyDecision:
    ctx = Context(request, rules, env)
    if reason := unknown_input(ctx):
        return PolicyDecision(verdict="deny", rule_id="unknown-input", reason=reason, policy_sha=policy_sha)
    for rule_id, rule in RULES:
        if reason := rule(ctx):
            return PolicyDecision(verdict="deny", rule_id=rule_id, reason=reason, policy_sha=policy_sha)
    return PolicyDecision(verdict="allow", rule_id="none", reason="ninguna regla lo niega", policy_sha=policy_sha)
