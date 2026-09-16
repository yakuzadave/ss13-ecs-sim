"""Atmosphere: room-granularity pressure simulation.

Physical system — may read objective state. Simple deterministic model:
active breaches vent pressure to space; open doors partially equalize
pressure between the two rooms they connect.
"""

from __future__ import annotations

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import Atmosphere, Breach, DoorState
from station_sim.ecs.queries import doors, name_of, rooms
from station_sim.ecs.world import log_event

MIN_PRESSURE_KPA = 0.0
DOOR_EQUALIZATION_FRACTION = 0.1  # fraction of pressure delta transferred per tick


def atmosphere_system(world: tcod.ecs.World) -> None:
    # 1. Breaches vent pressure to space.
    for room in rooms(world):
        breach = room.components.get(Breach)
        if breach is None or tags.ACTIVE_BREACH not in room.tags:
            continue
        atmo = room.components[Atmosphere]
        new_pressure = max(
            MIN_PRESSURE_KPA, atmo.pressure_kpa - breach.leak_rate_kpa_per_tick
        )
        room.components[Atmosphere] = Atmosphere(
            pressure_kpa=new_pressure,
            oxygen_fraction=atmo.oxygen_fraction,
            temperature_c=atmo.temperature_c,
        )

    # 2. Open doors equalize pressure between connected rooms.
    transfers: dict[tcod.ecs.Entity, float] = {}
    for door in doors(world):
        state = door.components[DoorState]
        if not state.open:
            continue
        room_a = door.relation_tag[relations.SIDE_A]
        room_b = door.relation_tag[relations.SIDE_B]
        pressure_a = room_a.components[Atmosphere].pressure_kpa
        pressure_b = room_b.components[Atmosphere].pressure_kpa
        transfer = (pressure_a - pressure_b) * DOOR_EQUALIZATION_FRACTION / 2
        transfers[room_a] = transfers.get(room_a, 0.0) - transfer
        transfers[room_b] = transfers.get(room_b, 0.0) + transfer

    for room in sorted(transfers, key=name_of):
        delta = transfers[room]
        atmo = room.components[Atmosphere]
        room.components[Atmosphere] = Atmosphere(
            pressure_kpa=max(MIN_PRESSURE_KPA, atmo.pressure_kpa + delta),
            oxygen_fraction=atmo.oxygen_fraction,
            temperature_c=atmo.temperature_c,
        )


def trigger_breach(
    world: tcod.ecs.World, room: tcod.ecs.Entity, leak_rate: float
) -> None:
    room.components[Breach] = Breach(leak_rate_kpa_per_tick=leak_rate)
    room.tags.add(tags.ACTIVE_BREACH)
    room.tags.add(tags.INCIDENT)
    log_event(world, f"Hull breach detected in {name_of(room)}.")
