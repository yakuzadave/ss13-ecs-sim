"""World construction and the single global state entity."""

from __future__ import annotations

import tcod.ecs

from station_sim.domain import tags
from station_sim.domain.components import EventLog, SimState


def new_world(seed: int = 0) -> tcod.ecs.World:
    world = tcod.ecs.World()
    state = world.new_entity()
    state.tags.add(tags.GLOBAL)
    state.components[SimState] = SimState(seed=seed)
    state.components[EventLog] = EventLog()
    return world


def sim_state(world: tcod.ecs.World) -> SimState:
    (entity,) = world.Q.all_of(tags=[tags.GLOBAL])
    return entity.components[SimState]


def event_log(world: tcod.ecs.World) -> EventLog:
    (entity,) = world.Q.all_of(tags=[tags.GLOBAL])
    return entity.components[EventLog]


def log_event(world: tcod.ecs.World, message: str) -> None:
    event_log(world).record(sim_state(world).tick, message)


def new_transient_entity(world: tcod.ecs.World, kind: str) -> tcod.ecs.Entity:
    """Create a transient entity (fact, action, ...) with a deterministic
    sequence identity: 'fact.0007', 'action.0042', ...

    tcod-ecs anonymous entities use object() uids, which are unique but
    not reproducible across runs. Sequence IDs make run A and run B
    directly comparable and replay logs diffable.
    """
    from station_sim.domain.components import Identity

    state = sim_state(world)
    state.next_sequence += 1
    entity = world.new_entity()
    entity.components[Identity] = Identity(f"{kind}.{state.next_sequence:04d}")
    return entity
