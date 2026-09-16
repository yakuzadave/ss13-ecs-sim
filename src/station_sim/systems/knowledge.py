"""Knowledge: beliefs, provenance, and inspection helpers."""

from __future__ import annotations

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import FactState
from station_sim.ecs.helpers import beliefs_of, subject_of
from station_sim.ecs.queries import crew_members, name_of


def crew_knowledge_report(world: tcod.ecs.World) -> list[dict]:
    """Flat rows describing every crew belief — for analysis, not AI."""
    rows = []
    for crew in crew_members(world):
        for fact in beliefs_of(crew):
            state = fact.components[FactState]
            subject = subject_of(fact)
            source = fact.relation_tag.get(relations.SOURCE)
            rows.append(
                {
                    "holder": name_of(crew),
                    "predicate": state.predicate,
                    "value": state.value,
                    "confidence": state.confidence,
                    "source_kind": state.source_kind,
                    "observed_tick": state.observed_tick,
                    "subject": name_of(subject) if subject else None,
                    "source": name_of(source) if source else None,
                }
            )
    return rows


def aware_of_breach(crew: tcod.ecs.Entity) -> bool:
    """True if the actor believes some room's pressure is abnormally low
    (semantic state LOW or worse)."""
    from station_sim.domain.components import PressureState, classify_pressure

    for fact in beliefs_of(crew):
        state = fact.components.get(FactState)
        if (
            state is not None
            and state.predicate == "room_pressure_kpa"
            and isinstance(state.value, (int, float))
            and classify_pressure(state.value) is not PressureState.NORMAL
        ):
            return True
    return False


def knowledge_system(world: tcod.ecs.World) -> None:
    """Placeholder for fact aging / decay / inference.

    Beliefs currently persist unchanged; the system boundary exists so
    those mechanics can be added without touching other systems.
    """
