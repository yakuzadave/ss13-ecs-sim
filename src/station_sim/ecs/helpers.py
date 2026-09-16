"""Thin semantic helpers over tcod-ecs.

These exist for readability, invariants, and migration flexibility —
not as a complete wrapper. Raw queries are fine inside query modules.
"""

from __future__ import annotations

from typing import Iterator

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import FactState


def move_entity(entity: tcod.ecs.Entity, destination: tcod.ecs.Entity) -> None:
    entity.relation_tag[relations.LOCATED_IN] = destination


def location_of(entity: tcod.ecs.Entity) -> tcod.ecs.Entity | None:
    return entity.relation_tag.get(relations.LOCATED_IN)


def assign_job(actor: tcod.ecs.Entity, job: tcod.ecs.Entity) -> None:
    actor.relation_tag[relations.HAS_JOB] = job


def job_of(actor: tcod.ecs.Entity) -> tcod.ecs.Entity | None:
    return actor.relation_tag.get(relations.HAS_JOB)


def give_belief(actor: tcod.ecs.Entity, fact: tcod.ecs.Entity) -> None:
    actor.relation_tags_many[relations.BELIEVES].add(fact)


def beliefs_of(actor: tcod.ecs.Entity) -> set[tcod.ecs.Entity]:
    return set(actor.relation_tags_many[relations.BELIEVES])


def radio_owned_by(actor: tcod.ecs.Entity) -> tcod.ecs.Entity | None:
    return actor.relation_tag.get(relations.OWNS_RADIO)


def subject_of(fact: tcod.ecs.Entity) -> tcod.ecs.Entity | None:
    return fact.relation_tag.get(relations.SUBJECT)


def belief_value(
    actor: tcod.ecs.Entity,
    subject: tcod.ecs.Entity,
    predicate: str,
) -> object | None:
    """The actor's believed value for (subject, predicate), or None.

    Cognitive code must use this instead of reading objective state.
    """
    fact = find_belief(actor, subject, predicate)
    if fact is None:
        return None
    return fact.components[FactState].value


def sequence_of(entity: tcod.ecs.Entity) -> int:
    """Deterministic sequence number from a transient Identity name.

    'fact.0042' -> 42. Entities without a sequence name (e.g. manually
    constructed test fixtures) return 0.
    """
    from station_sim.domain.components import Identity

    identity = entity.components.get(Identity)
    if identity is None:
        return 0
    try:
        return int(identity.name.rsplit(".", 1)[1])
    except (IndexError, ValueError):
        return 0


def find_belief(
    actor: tcod.ecs.Entity,
    subject: tcod.ecs.Entity,
    predicate: str,
) -> tcod.ecs.Entity | None:
    """Return the actor's operative belief about (subject, predicate).

    Deterministic precedence when several facts conflict:
      1. newest observation wins
      2. if ticks equal, higher source priority wins
      3. if source equal, highest confidence wins
      4. final tie-break by fact sequence ID (later creation wins)
    """
    from station_sim.domain.components import SOURCE_PRIORITY

    best: tcod.ecs.Entity | None = None
    best_key: tuple | None = None
    for fact in beliefs_of(actor):
        state = fact.components.get(FactState)
        if state is None or state.predicate != predicate:
            continue
        if fact.relation_tag.get(relations.SUBJECT) is not subject:
            continue
        key = (
            state.observed_tick,
            SOURCE_PRIORITY.get(state.source_kind, 0),
            state.confidence,
            sequence_of(fact),
        )
        if best_key is None or key > best_key:
            best, best_key = fact, key
    return best


def doors_connecting(room: tcod.ecs.Entity) -> Iterator[tcod.ecs.Entity]:
    """Doors touching a room, in deterministic (identity name) order."""
    from station_sim.domain.components import Identity

    found = []
    for door in room.registry.Q.all_of(tags=[tags.DOOR]):
        if (
            door.relation_tag.get(relations.SIDE_A) is room
            or door.relation_tag.get(relations.SIDE_B) is room
        ):
            found.append(door)
    found.sort(key=lambda d: d.components.get(Identity, Identity("")).name)
    yield from found


def other_side(door: tcod.ecs.Entity, room: tcod.ecs.Entity) -> tcod.ecs.Entity:
    side_a = door.relation_tag[relations.SIDE_A]
    side_b = door.relation_tag[relations.SIDE_B]
    return side_b if side_a is room else side_a


def adjacent_rooms(room: tcod.ecs.Entity) -> Iterator[tcod.ecs.Entity]:
    for door in doors_connecting(room):
        yield other_side(door, room)


def occupants_of(room: tcod.ecs.Entity) -> Iterator[tcod.ecs.Entity]:
    for crew in room.registry.Q.all_of(tags=[tags.CREW]):
        if location_of(crew) is room:
            yield crew
