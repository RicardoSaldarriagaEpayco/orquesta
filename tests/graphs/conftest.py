import psycopg
import pytest


@pytest.fixture
def graph_dsn(postgres: dict[str, str]) -> str:
    with psycopg.connect(postgres["owner"], autocommit=True) as conn:
        conn.execute("DROP SCHEMA graph CASCADE")
        conn.execute("CREATE SCHEMA graph AUTHORIZATION graph_writer")
    return postgres["graph"]
