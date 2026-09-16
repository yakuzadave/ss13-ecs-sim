"""Explicit tick ordering. The runner owns execution; systems never
call each other.
"""

from __future__ import annotations

import tcod.ecs

from station_sim.ecs.world import sim_state
from station_sim.systems.actions import action_system
from station_sim.systems.atmosphere import atmosphere_system
from station_sim.systems.health import health_system
from station_sim.systems.knowledge import knowledge_system
from station_sim.systems.perception import perception_system
from station_sim.systems.utility_ai import utility_ai_system


def simulation_tick(world: tcod.ecs.World) -> None:
    # Physical systems (may read objective state)
    atmosphere_system(world)
    health_system(world)

    # Cognitive systems (respect information boundaries)
    perception_system(world)
    knowledge_system(world)

    utility_ai_system(world)
    action_system(world)

    sim_state(world).tick += 1


def run(world: tcod.ecs.World, ticks: int) -> None:
    for _ in range(ticks):
        simulation_tick(world)
