"""Common world queries. Raw tcod-ecs queries belong here."""

from __future__ import annotations

from typing import Iterator

import tcod.ecs

from station_sim.domain import tags
from station_sim.domain.components import Identity


def crew_members(world: tcod.ecs.World) -> Iterator[tcod.ecs.Entity]:
    yield from world.Q.all_of(tags=[tags.CREW])


def rooms(world: tcod.ecs.World) -> Iterator[tcod.ecs.Entity]:
    yield from world.Q.all_of(tags=[tags.ROOM])


def doors(world: tcod.ecs.World) -> Iterator[tcod.ecs.Entity]:
    yield from world.Q.all_of(tags=[tags.DOOR])


def name_of(entity: tcod.ecs.Entity) -> str:
    identity = entity.components.get(Identity)
    return identity.name if identity else repr(entity)


def crew_named(world: tcod.ecs.World, name: str) -> tcod.ecs.Entity:
    for crew in crew_members(world):
        if name_of(crew) == name:
            return crew
    raise KeyError(name)


def room_named(world: tcod.ecs.World, name: str) -> tcod.ecs.Entity:
    for room in rooms(world):
        if name_of(room) == name:
            return room
    raise KeyError(name)


def conscious_crew(world: tcod.ecs.World) -> Iterator[tcod.ecs.Entity]:
    yield from world.Q.all_of(tags=[tags.CREW, tags.CONSCIOUS])
