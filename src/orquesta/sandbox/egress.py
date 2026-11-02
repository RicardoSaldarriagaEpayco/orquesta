import argparse
import asyncio
import contextlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass

MAX_HEAD = 8192
HEAD_TIMEOUT_S = 10.0
DEFAULT_PORT = 443


@dataclass(frozen=True)
class EgressDecision:
    verdict: str
    host: str
    port: int
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"verdict": self.verdict, "host": self.host, "port": self.port, "reason": self.reason}


def parse_allowlist(entries: list[str]) -> frozenset[tuple[str, int]]:
    allowed = set()
    for entry in entries:
        value = entry.strip().lower()
        host, separator, port = value.rpartition(":")
        if not separator:
            host, port = value, str(DEFAULT_PORT)
        host = host.rstrip(".")
        if not host or not port.isdigit() or not 0 < int(port) < 65536:
            raise ValueError(f"entrada de allowlist inválida: {entry!r}")
        allowed.add((host, int(port)))
    return frozenset(allowed)


def decide(allowlist: frozenset[tuple[str, int]], request_line: str) -> EgressDecision:
    parts = request_line.split()
    if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
        return EgressDecision("deny", "", 0, "petición ilegible")
    method, target, _ = parts
    host, _, port = target.rpartition(":")
    if method != "CONNECT":
        return EgressDecision("deny", "", 0, "solo se permite CONNECT")
    if not host or not port.isdigit():
        return EgressDecision("deny", "", 0, "destino ilegible")
    host = host.strip("[]").lower().rstrip(".")
    if (host, int(port)) not in allowlist:
        return EgressDecision("deny", host, int(port), "fuera de la allowlist")
    return EgressDecision("allow", host, int(port), "en la allowlist")


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        with contextlib.suppress(Exception):
            writer.close()


class EgressProxy:
    def __init__(self, allowlist: frozenset[tuple[str, int]], record: Callable[[EgressDecision], None]) -> None:
        self.allowlist = allowlist
        self.record = record

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEAD_TIMEOUT_S)
        except (TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            writer.close()
            return
        decision = decide(self.allowlist, head.split(b"\r\n", 1)[0].decode("latin-1"))
        if decision.verdict == "allow":
            try:
                upstream_reader, upstream_writer = await asyncio.wait_for(
                    asyncio.open_connection(decision.host, decision.port), HEAD_TIMEOUT_S
                )
            except (TimeoutError, OSError):
                decision = EgressDecision("deny", decision.host, decision.port, "destino inalcanzable")
        self.record(decision)
        if decision.verdict == "deny":
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            with contextlib.suppress(ConnectionError):
                await writer.drain()
            writer.close()
            return
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await asyncio.gather(_pipe(reader, upstream_writer), _pipe(upstream_reader, writer))

    async def serve(self, host: str, port: int) -> asyncio.Server:
        return await asyncio.start_server(self.handle, host, port, limit=MAX_HEAD)


def _print_decision(decision: EgressDecision) -> None:
    print(json.dumps(decision.to_dict(), ensure_ascii=False), file=sys.stderr, flush=True)


async def _run(args: argparse.Namespace) -> None:
    proxy = EgressProxy(parse_allowlist(args.allow), _print_decision)
    server = await proxy.serve(args.host, args.port)
    async with server:
        await server.serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="orquesta-egress")
    parser.add_argument("--allow", action="append", default=[], help="host o host:puerto (443 por defecto)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3128)
    asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
