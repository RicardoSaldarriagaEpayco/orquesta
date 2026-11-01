from typing import TypedDict

import psycopg
import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from orquesta.errors import GraphStoreUnavailable
from orquesta.graphs.checkpoint import open_checkpointer


class State(TypedDict, total=False):
    proposal: str
    decision: str


def build(calls: list[str]):
    def propose(state: State) -> State:
        calls.append("propose")
        return {"proposal": "agent/reviewer"}

    def approve(state: State) -> State:
        calls.append("approve")
        return {"decision": interrupt({"proposal": state["proposal"]})["decision"]}

    graph = StateGraph(State)
    graph.add_node("propose", propose)
    graph.add_node("approve", approve)
    graph.add_edge(START, "propose")
    graph.add_edge("propose", "approve")
    graph.add_edge("approve", END)
    return graph


def test_resume_after_restart_does_not_repeat_nodes(graph_dsn):
    calls: list[str] = []
    config = {"configurable": {"thread_id": "run-1"}}
    with open_checkpointer(graph_dsn) as saver:
        first = build(calls).compile(checkpointer=saver).invoke({}, config)
    assert first["__interrupt__"][0].value == {"proposal": "agent/reviewer"}

    with open_checkpointer(graph_dsn) as saver:
        app = build(calls).compile(checkpointer=saver)
        assert app.get_state(config).next == ("approve",)
        final = app.invoke(Command(resume={"decision": "approve"}), config)

    assert final == {"proposal": "agent/reviewer", "decision": "approve"}
    assert calls == ["propose", "approve", "approve"]


def test_checkpoint_tables_live_in_graph_schema(graph_dsn, postgres):
    with open_checkpointer(graph_dsn):
        pass
    with psycopg.connect(postgres["owner"]) as conn:
        rows = conn.execute("SELECT schemaname FROM pg_tables WHERE tablename LIKE 'checkpoint%'").fetchall()
    schemas = {row[0] for row in rows}
    assert schemas == {"graph"}


def test_graph_writer_cannot_touch_audit(graph_dsn):
    with psycopg.connect(graph_dsn) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT count(*) FROM public.audit_events")


def test_audit_writer_cannot_touch_graph(graph_dsn, postgres):
    with open_checkpointer(graph_dsn):
        pass
    with psycopg.connect(postgres["writer"]) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT count(*) FROM graph.checkpoints")


def test_rejects_role_outside_graph_schema(postgres):
    with pytest.raises(GraphStoreUnavailable), open_checkpointer(postgres["writer"]):
        pass


def test_requires_dsn(monkeypatch):
    monkeypatch.delenv("ORQUESTA_GRAPH_DSN", raising=False)
    with pytest.raises(GraphStoreUnavailable) as error, open_checkpointer():
        pass
    assert error.value.exit_code == 12


def test_unreachable_store_fails_closed():
    with pytest.raises(GraphStoreUnavailable), open_checkpointer("postgresql://graph_writer:x@127.0.0.1:1/audit"):
        pass
