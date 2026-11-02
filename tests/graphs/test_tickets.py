import json
from pathlib import Path

import jsonschema
import pytest

from orquesta.errors import TicketError
from orquesta.graphs.tickets import FileTicketSource, Ticket

CONTRACT = json.loads((Path(__file__).parents[2] / "contracts" / "ticket.schema.json").read_text())

FILE = """tickets:
  - key: APP-12
    project: app
    summary: El botón de pago no responde en móvil.
    labels: [frontend]
    repo: web-app
  - key: OPS-3
    project: ops
    summary: Renovar certificado.
"""


def source(tmp_path: Path, content: str) -> FileTicketSource:
    path = tmp_path / "tickets.yaml"
    path.write_text(content)
    return FileTicketSource(path)


def test_reads_tickets_by_key(tmp_path):
    tickets = source(tmp_path, FILE)
    ticket = tickets.get("APP-12")
    assert ticket.repo == "web-app"
    assert ticket.labels == ("frontend",)
    assert tickets.get("OPS-3").description == ""


def test_missing_key_is_typed_error(tmp_path):
    with pytest.raises(TicketError) as error:
        source(tmp_path, FILE).get("APP-99")
    assert error.value.exit_code == 13
    assert error.value.fields() == {"ticket": "APP-99", "reason": "no existe en la fuente"}


@pytest.mark.parametrize(
    "content",
    [
        "tickets: [{key: app-1, project: a, summary: s}]",
        "tickets: [{key: A-1, project: a, summary: s, extra: 1}]",
        "otra: []",
        "tickets: [",
        "tickets: [{key: A-1, project: a, summary: s}, {key: A-1, project: b, summary: t}]",
    ],
)
def test_invalid_file_fails_closed(tmp_path, content):
    with pytest.raises(TicketError):
        source(tmp_path, content)


def test_error_does_not_echo_ticket_text(tmp_path):
    with pytest.raises(TicketError) as error:
        source(tmp_path, "tickets: [{key: A-1, project: a, summary: texto-canario, extra: 1}]")
    assert "texto-canario" not in str(error.value)


@pytest.mark.parametrize(
    "item",
    [
        {"key": "APP-12", "project": "app", "summary": "s", "labels": ["x"], "repo": "web-app"},
        {"key": "app-12", "project": "app", "summary": "s"},
        {"key": "APP-12", "project": "app"},
        {"key": "APP-12", "project": "app", "summary": "s", "repo": "Web App"},
    ],
)
def test_contract_matches_model(item):
    model_ok = True
    try:
        Ticket.model_validate(item)
    except ValueError:
        model_ok = False
    contract_ok = jsonschema.Draft202012Validator(CONTRACT).is_valid(item)
    assert model_ok == contract_ok
