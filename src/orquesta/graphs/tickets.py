from pathlib import Path
from typing import Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from orquesta.errors import TicketError

KEY = r"^[A-Z][A-Z0-9]+-[0-9]+$"


class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=KEY)
    project: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=400)
    description: str = Field(default="", max_length=20000)
    labels: tuple[str, ...] = ()
    repo: str | None = Field(default=None, pattern=r"^[a-z0-9._-]+$")


class TicketSource(Protocol):
    def get(self, key: str) -> Ticket: ...


class FileTicketSource:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            raw = yaml.safe_load(path.read_text())
            tickets = [Ticket.model_validate(item) for item in raw["tickets"]]
        except (OSError, yaml.YAMLError, KeyError, TypeError, ValidationError) as error:
            raise TicketError(path.name, f"archivo de tickets inválido: {type(error).__name__}") from error
        self._tickets: dict[str, Ticket] = {}
        for ticket in tickets:
            if ticket.key in self._tickets:
                raise TicketError(ticket.key, "repetido en el archivo de tickets")
            self._tickets[ticket.key] = ticket

    def get(self, key: str) -> Ticket:
        try:
            return self._tickets[key]
        except KeyError:
            raise TicketError(key, "no existe en la fuente") from None
