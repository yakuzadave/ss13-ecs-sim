"""Perception: turns directly observable world state into knowledge.

Cognitive system — perception is room-local and is the ONLY way
objective state enters a crew member's knowledge without communication.
"""

from __future__ import annotations

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import Atmosphere, FactState
from station_sim.ecs.helpers import belief_value, find_belief, give_belief, location_of
from station_sim.ecs.queries import conscious_crew
from station_sim.ecs.world import new_transient_entity, sim_state

DANGEROUS_PRESSURE_KPA = 70.0
DIRECT_OBSERVATION_CONFIDENCE = 0.99


def _observe_pressure(
    world: tcod.ecs.World, actor: tcod.ecs.Entity, room: tcod.ecs.Entity, pressure: float
) -> None:
    tick = sim_state(world).tick
    existing = find_belief(actor, room, "room_pressure_kpa")
    if existing is not None:
        actor.relation_tags_many[relations.BELIEVES].discard(existing)
        existing.clear()
    fact = new_transient_entity(world, "fact")
    fact.tags.add(tags.FACT)
    fact.components[FactState] = FactState(
        predicate="room_pressure_kpa",
        value=pressure,
        confidence=DIRECT_OBSERVATION_CONFIDENCE,
        source_kind="direct_observation",
        observed_tick=tick,
    )
    fact.relation_tag[relations.SUBJECT] = room
    give_belief(actor, fact)


def perception_system(world: tcod.ecs.World) -> None:
    from station_sim.ecs.queries import name_of

    for crew in sorted(conscious_crew(world), key=name_of):
        room = location_of(crew)
        if room is None:
            continue
        atmo = room.components.get(Atmosphere)
        if atmo is None:
            continue
        # Obvious atmospheric state in the occupied room is directly
        # observable. Crew only update their belief when the observed
        # value differs from what they currently believe.
        believed = belief_value(crew, room, "room_pressure_kpa")
        if believed != atmo.pressure_kpa:
            _observe_pressure(world, crew, room, atmo.pressure_kpa)
