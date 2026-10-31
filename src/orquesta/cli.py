import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from orquesta.errors import OrquestaError
from orquesta.identity import resolve_actor
from orquesta.registry.lock import lock, verify
from orquesta.registry.resolve import resolve
from orquesta.workspace import Workspace


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="errores y salida en JSON")

    parser = argparse.ArgumentParser(prog="orquesta", parents=[common])
    commands = parser.add_subparsers(dest="command", required=True)

    registry = commands.add_parser("registry", help="agentes y skills por SHA").add_subparsers(
        dest="action", required=True
    )
    for name in ("list", "lock"):
        sub = registry.add_parser(name, parents=[common])
        sub.add_argument("--workspace", required=True)
        sub.add_argument("--sha", required=True)
    verify = registry.add_parser("verify", parents=[common])
    verify.add_argument("--workspace", required=True)
    verify.add_argument("--lock", required=True)

    policy = commands.add_parser("policy", help="decisiones de política").add_subparsers(dest="action", required=True)
    evaluate = policy.add_parser("eval", parents=[common])
    evaluate.add_argument("--workspace", required=True)
    evaluate.add_argument("--sha", required=True)

    audit = commands.add_parser("audit", help="cadena de auditoría").add_subparsers(dest="action", required=True)
    audit.add_parser("verify", parents=[common])

    evals = commands.add_parser("eval", help="suites de evaluación").add_subparsers(dest="action", required=True)
    run = evals.add_parser("run", parents=[common])
    run.add_argument("--suite", required=True)
    run.add_argument("--sha", required=True)
    run.add_argument("--provider", choices=["fake", "anthropic"], required=True)

    return parser


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _registry_list(args: argparse.Namespace) -> int:
    manifests = resolve(Workspace(args.workspace), args.sha)
    if args.json:
        _emit([m.to_json() for m in manifests])
    else:
        for m in manifests:
            print(f"{m.id}\t{m.digest}")
    return 0


def _registry_lock(args: argparse.Namespace) -> int:
    _emit(lock(Workspace(args.workspace), args.sha).to_json())
    return 0


def _registry_verify(args: argparse.Namespace) -> int:
    approved = verify(Workspace(args.workspace), Path(args.lock))
    print(f"lock de {approved.sha[:7]} coincide: {len(approved.lock)} activos")
    return 0


HANDLERS: dict[tuple[str, str], Callable[[argparse.Namespace], int]] = {
    ("registry", "list"): _registry_list,
    ("registry", "lock"): _registry_lock,
    ("registry", "verify"): _registry_verify,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handler = HANDLERS.get((args.command, args.action))
    try:
        resolve_actor()
        if handler is None:
            print(f"orquesta {args.command} {args.action}: todavía no implementado", file=sys.stderr)
            return 1
        return handler(args)
    except OrquestaError as error:
        error.report(args.json)
        return error.exit_code


if __name__ == "__main__":
    sys.exit(main())
