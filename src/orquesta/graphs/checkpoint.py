import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from orquesta.errors import GraphStoreUnavailable

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres import PostgresSaver

DSN_ENV = "ORQUESTA_GRAPH_DSN"
SCHEMA = "graph"


@contextmanager
def open_checkpointer(dsn: str | None = None) -> Iterator["PostgresSaver"]:
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver

    dsn = dsn or os.environ.get(DSN_ENV, "")
    if not dsn:
        raise GraphStoreUnavailable(f"define {DSN_ENV} con la credencial de graph_writer")
    try:
        with PostgresSaver.from_conn_string(dsn) as saver:
            row = saver.conn.execute(
                "SELECT current_schema() AS schema, EXISTS (SELECT 1 FROM information_schema.table_privileges"
                " WHERE table_name = 'audit_events') AS audit"
            ).fetchone()
            if row["schema"] != SCHEMA or row["audit"]:
                raise GraphStoreUnavailable(f"el rol debe usar solo el esquema {SCHEMA}")
            saver.setup()
            yield saver
    except psycopg.OperationalError as error:
        raise GraphStoreUnavailable(type(error).__name__) from error
