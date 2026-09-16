"""Domain components: pure state belonging to entities.

Components hold no simulation logic. Systems transform them by
replacement (frozen dataclasses) where practical.
"""

from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Identity:
    name: str


class PressureState(enum.Enum):
    """Semantic classification of room pressure.

    Communication deduplicates on TRANSITIONS of this enum, not on raw
    kPa values: people radio "Maintenance is venting", not one message
    per 0.4 kPa change.
    """

    NORMAL = enum.auto()
    LOW = enum.auto()
    CRITICAL = enum.auto()
    VACUUM = enum.auto()


def classify_pressure(pressure_kpa: float) -> PressureState:
    if pressure_kpa >= 80.0:
        return PressureState.NORMAL
    if pressure_kpa >= 50.0:
        return PressureState.LOW
    if pressure_kpa >= 15.0:
        return PressureState.CRITICAL
    return PressureState.VACUUM


# Deterministic belief precedence for conflicting facts held by one
# actor about the same (subject, predicate):
#   1. newest observation wins
#   2. if ticks equal, higher source priority wins
#   3. if source equal, highest confidence wins
#   4. final tie-break by fact sequence ID
SOURCE_PRIORITY = {
    "direct_observation": 3,
    "system_alarm": 2,
    "radio_report": 1,
}


@dataclass(slots=True)
class ReportMemory:
    """What this actor has already reported, per (subject, predicate).

    Key: (subject_name, predicate). Value: last reported PressureState
    name. A new report happens only on a state transition.
    """

    reported: dict[tuple[str, str], str] = field(default_factory=dict)


@dataclass(slots=True)
class SimState:
    """World-owned simulation state: clock, RNG, metrics.

    Mutable by design; owned by a single global entity. The RNG lives
    here so runs are deterministic given the same seed.
    """

    tick: int = 0
    seed: int = 0
    rng: random.Random = field(default_factory=random.Random)
    radio_messages: int = 0
    next_sequence: int = 0
    breach_leak_rate: float = 8.0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)


@dataclass(slots=True)
class EventLog:
    """Omniscient event log. Debugging/analysis only — never knowledge."""

    entries: list[str] = field(default_factory=list)

    def record(self, tick: int, message: str) -> None:
        self.entries.append(f"[{tick}] {message}")


@dataclass(frozen=True, slots=True)
class Atmosphere:
    pressure_kpa: float = 101.3
    oxygen_fraction: float = 0.21
    temperature_c: float = 21.0


@dataclass(frozen=True, slots=True)
class Breach:
    leak_rate_kpa_per_tick: float


@dataclass(frozen=True, slots=True)
class DoorState:
    open: bool = False
    locked: bool = False
    powered: bool = True
    integrity: float = 1.0


@dataclass(frozen=True, slots=True)
class Health:
    hp: float = 100.0
    oxygenation: float = 1.0
    conscious: bool = True


@dataclass(frozen=True, slots=True)
class Personality:
    bravery: float
    duty: float
    empathy: float
    curiosity: float
    self_preservation: float


@dataclass(frozen=True, slots=True)
class Competence:
    engineering: float = 0.0
    medical: float = 0.0
    security: float = 0.0


@dataclass(frozen=True, slots=True)
class RadioState:
    powered: bool = True
    channel: str = "common"
    integrity: float = 1.0


@dataclass(frozen=True, slots=True)
class FactState:
    predicate: str
    value: Any
    confidence: float
    source_kind: str
    observed_tick: int


@dataclass(frozen=True, slots=True)
class ActionState:
    kind: str
    utility: float
    selected_tick: int
    status: str  # pending | completed | failed
