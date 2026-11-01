import asyncio

import pytest

from orquesta.sandbox.egress import EgressProxy, decide, parse_allowlist

ALLOW = parse_allowlist(["api.example.com", "git.example.com:22"])


@pytest.mark.parametrize(
    ("line", "verdict", "host"),
    [
        ("CONNECT api.example.com:443 HTTP/1.1", "allow", "api.example.com"),
        ("CONNECT API.Example.com.:443 HTTP/1.1", "allow", "api.example.com"),
        ("CONNECT git.example.com:22 HTTP/1.1", "allow", "git.example.com"),
        ("CONNECT api.example.com:80 HTTP/1.1", "deny", "api.example.com"),
        ("CONNECT evil.example.com:443 HTTP/1.1", "deny", "evil.example.com"),
        ("CONNECT api.example.com.evil.net:443 HTTP/1.1", "deny", "api.example.com.evil.net"),
        ("GET http://api.example.com/ HTTP/1.1", "deny", ""),
        ("CONNECT api.example.com HTTP/1.1", "deny", ""),
        ("basura", "deny", ""),
    ],
)
def test_decide(line, verdict, host):
    decision = decide(ALLOW, line)
    assert (decision.verdict, decision.host) == (verdict, host)


@pytest.mark.parametrize("entry", ["", ":443", "host:abc", "host:0", "host:70000"])
def test_invalid_allowlist(entry):
    with pytest.raises(ValueError):
        parse_allowlist([entry])


async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.write(await reader.read(100))
    await writer.drain()
    writer.close()


async def _connect(proxy_port: int, target: str) -> tuple[bytes, bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
    writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    await writer.drain()
    status = await reader.readuntil(b"\r\n\r\n")
    body = b""
    if b" 200 " in status:
        writer.write(b"ping")
        await writer.drain()
        body = await reader.read(100)
    writer.close()
    return status, body


def test_tunnels_allowed_and_records_denied():
    async def scenario():
        echo = await asyncio.start_server(_echo, "127.0.0.1", 0)
        echo_port = echo.sockets[0].getsockname()[1]
        decisions = []
        proxy = EgressProxy(parse_allowlist([f"127.0.0.1:{echo_port}"]), decisions.append)
        server = await proxy.serve("127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        allowed = await _connect(port, f"127.0.0.1:{echo_port}")
        denied = await _connect(port, "other.example.com:443")
        server.close()
        echo.close()
        return allowed, denied, decisions

    allowed, denied, decisions = asyncio.run(scenario())
    assert b" 200 " in allowed[0] and allowed[1] == b"ping"
    assert b" 403 " in denied[0] and denied[1] == b""
    assert [(d.verdict, d.host) for d in decisions] == [("allow", "127.0.0.1"), ("deny", "other.example.com")]


def test_unreachable_allowed_host_is_denied():
    async def scenario():
        decisions = []
        proxy = EgressProxy(parse_allowlist(["127.0.0.1:1"]), decisions.append)
        server = await proxy.serve("127.0.0.1", 0)
        status, _ = await _connect(server.sockets[0].getsockname()[1], "127.0.0.1:1")
        server.close()
        return status, decisions

    status, decisions = asyncio.run(scenario())
    assert b" 403 " in status
    assert decisions[0].reason == "destino inalcanzable"


def test_oversized_head_is_dropped_without_decision():
    async def scenario():
        decisions = []
        server = await EgressProxy(ALLOW, decisions.append).serve("127.0.0.1", 0)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
        writer.write(b"CONNECT " + b"a" * 9000)
        await writer.drain()
        data = await reader.read(100)
        writer.close()
        server.close()
        return data, decisions

    data, decisions = asyncio.run(scenario())
    assert data == b""
    assert decisions == []
