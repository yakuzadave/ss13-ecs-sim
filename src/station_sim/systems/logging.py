"""Omniscient event log access. Never feeds crew knowledge."""

from __future__ import annotations

import tcod.ecs

from station_sim.ecs.world import event_log


def event_log_entries(world: tcod.ecs.World) -> list[str]:
    return list(event_log(world).entries)
