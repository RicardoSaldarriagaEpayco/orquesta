import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import ValidationError

from orquesta.errors import AuditUnavailable, OrquestaError, ProviderError
from orquesta.evals import promotion, suite
from orquesta.evals.run import EvalRun
from orquesta.evals.run import run as run_suite
from orquesta.gateway.config import load_models
from orquesta.gateway.gateway import Gateway
from orquesta.gateway.provider import FakeProvider
from orquesta.identity import resolve_actor
from orquesta.policy.engine import evaluate
from orquesta.policy.fixtures import run as run_fixtures
from orquesta.policy.load import GitEnvironment, RequestUnreadable, load_rules
from orquesta.policy.model import PolicyRequest
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
    fixture = policy.add_parser("test", parents=[common], help="corre un fixture de paridad con las reglas del SHA")
    fixture.add_argument("--workspace", required=True)
    fixture.add_argument("--sha", required=True)
    fixture.add_argument("--fixtures", required=True)

    audit = commands.add_parser("audit", help="cadena de auditoría").add_subparsers(dest="action", required=True)
    audit.add_parser("verify", parents=[common])

    evals = commands.add_parser("eval", help="suites de evaluación").add_subparsers(dest="action", required=True)
    run = evals.add_parser("run", parents=[common])
    run.add_argument("--workspace", required=True)
    run.add_argument("--suite", required=True, help="ruta de la suite dentro del workspace")
    run.add_argument("--sha", required=True)
    run.add_argument("--provider", choices=["fake", "anthropic"], required=True)
    run.add_argument("--answers", help="tabla case_id -> respuesta del proveedor fake (YAML)")
    run.add_argument("--model", help="modelo; por defecto models.default, o fake-routing con --provider fake")
    run.add_argument("--baseline", help="EvalRun JSON de la línea base para comparar")
    run.add_argument("--record", help="ruta donde escribir el PromotionRecord")

    return parser


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _record(writer: object, **fields: object) -> None:
    if writer is not None:
        from orquesta.audit.chain import AuditRecord

        writer.write(AuditRecord(actor=resolve_actor(), **fields))


def _registry_event(args: argparse.Namespace, workspace: Workspace, count: int, ms: int) -> None:
    from orquesta.audit.sink import tenant, writer_from_env

    sha = workspace.resolve(args.sha)
    _record(
        writer_from_env(),
        tenant=tenant(workspace, sha),
        kind="registry_resolve",
        policy_sha=sha,
        asset_set_sha=sha,
        decision=f"registry {args.action}: {count} activos",
        latency_ms=ms,
        refs={"command": f"registry {args.action}"},
    )


def _registry_list(args: argparse.Namespace) -> int:
    from orquesta.audit.sink import Stopwatch

    watch = Stopwatch()
    workspace = Workspace(args.workspace)
    manifests = resolve(workspace, args.sha)
    _registry_event(args, workspace, len(manifests), watch.ms)
    if args.json:
        _emit([m.to_json() for m in manifests])
    else:
        for m in manifests:
            print(f"{m.id}\t{m.digest}")
    return 0


def _registry_lock(args: argparse.Namespace) -> int:
    from orquesta.audit.sink import Stopwatch

    watch = Stopwatch()
    workspace = Workspace(args.workspace)
    candidate = lock(workspace, args.sha)
    _registry_event(args, workspace, len(candidate.lock), watch.ms)
    _emit(candidate.to_json())
    return 0


def _registry_verify(args: argparse.Namespace) -> int:
    approved = verify(Workspace(args.workspace), Path(args.lock))
    print(f"lock de {approved.sha[:7]} coincide: {len(approved.lock)} activos")
    return 0


def _policy_eval(args: argparse.Namespace) -> int:
    try:
        request = PolicyRequest.model_validate_json(sys.stdin.read())
    except ValidationError as error:
        raise RequestUnreadable(error.errors()[0]["msg"]) from error
    from orquesta.audit.sink import Stopwatch, tenant, writer_from_env

    watch = Stopwatch()
    workspace = Workspace(args.workspace)
    rules, sha = load_rules(workspace, args.sha)
    decision = evaluate(request, rules, GitEnvironment(str(workspace.path.resolve())), sha)
    _record(
        writer_from_env(),
        tenant=tenant(workspace, sha),
        kind="policy_decision",
        policy_sha=sha,
        asset_set_sha=sha,
        tools=[request.tool],
        decision=f"{decision.verdict}:{decision.rule_id}",
        latency_ms=watch.ms,
        refs={"entrypoint": request.entrypoint, "rule_id": decision.rule_id},
    )
    print(decision.model_dump_json())
    return 0


def _policy_test(args: argparse.Namespace) -> int:
    rules, _ = load_rules(Workspace(args.workspace), args.sha)
    outcomes = run_fixtures(Path(args.fixtures).read_text(encoding="utf-8"), rules)
    failed = [o for o in outcomes if not o.ok]
    for o in failed:
        print(f"FALLA {o.name}: se esperaba {o.expected} y salió {o.actual}")
    print(f"{len(outcomes) - len(failed)} de {len(outcomes)} casos coinciden")
    return 1 if failed else 0


def _eval_run(args: argparse.Namespace) -> int:
    import yaml

    workspace = Workspace(args.workspace)
    sha = workspace.resolve(args.sha)
    loaded = suite.load(workspace, sha, args.suite)
    allowlist, default = load_models(workspace, sha)
    if args.provider == "anthropic":
        raise ProviderError("anthropic", "el proveedor real llega con T064, después de la autorización (T026)")
    answers = yaml.safe_load(Path(args.answers).read_text(encoding="utf-8")) if args.answers else {}
    provider = FakeProvider({str(k): str(v) for k, v in (answers or {}).items()})
    model = args.model or "fake-routing"
    from orquesta.audit.sink import ModelCallSink, tenant, writer_from_env

    sink = ModelCallSink(writer_from_env(), sha, sha)
    gateway = Gateway(allowlist, sink, actor=resolve_actor(), tenant=tenant(workspace, sha))
    result = run_suite(loaded, resolve(workspace, sha), gateway, provider, model, sha)
    if args.record:
        baseline = EvalRun.model_validate_json(Path(args.baseline).read_text()) if args.baseline else None
        entry = promotion.record(result, baseline, loaded.margin, reviewer=resolve_actor())
        Path(args.record).write_text(entry.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(result.model_dump_json(indent=2))
    return 0


def _audit_verify(args: argparse.Namespace) -> int:
    import psycopg

    from orquesta.audit.chain import verify as verify_chain
    from orquesta.audit.key import load_key

    key = load_key()
    dsn = os.environ.get("ORQUESTA_AUDIT_DSN", "")
    if not dsn:
        raise AuditUnavailable("define ORQUESTA_AUDIT_DSN con la credencial de audit_writer")
    with psycopg.connect(dsn) as conn:
        count = verify_chain(conn, key)
    print(f"cadena íntegra: {count} eventos")
    return 0


HANDLERS: dict[tuple[str, str], Callable[[argparse.Namespace], int]] = {
    ("registry", "list"): _registry_list,
    ("registry", "lock"): _registry_lock,
    ("registry", "verify"): _registry_verify,
    ("policy", "eval"): _policy_eval,
    ("policy", "test"): _policy_test,
    ("eval", "run"): _eval_run,
    ("audit", "verify"): _audit_verify,
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
