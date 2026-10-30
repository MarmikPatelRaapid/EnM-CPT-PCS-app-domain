from dataclasses import dataclass, field
from typing import Literal

from src.agents.agent1 import Procedure


@dataclass
class PCSNode:
    procedure: Procedure
    current_code: str
    accumulated_evidences: dict = field(default_factory=dict)


@dataclass
class PCSCode:
    code: str
    procedure_name: str
    status: Literal["billable", "non_billable"]
    evidences: dict
