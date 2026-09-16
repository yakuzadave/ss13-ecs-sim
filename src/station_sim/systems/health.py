"""Health: physical effects of objective atmosphere on crew.

Physical system — breathing depends on the real atmosphere, so this
system reads objective state directly. Cognitive systems may not.
"""

from __future__ import annotations

import tcod.ecs

from station_sim.domain import tags
from station_sim.domain.components import Atmosphere, Health
from station_sim.ecs.helpers import location_of, occupants_of
from station_sim.ecs.queries import name_of, rooms
from station_sim.ecs.world import log_event

HYPOXIA_PRESSURE_KPA = 60.0
OXYGENATION_LOSS_PER_TICK = 0.05
OXYGENATION_RECOVERY_PER_TICK = 0.02
UNCONSCIOUS_OXYGENATION = 0.4
HP_LOSS_PER_TICK_WHEN_HYPOXIC = 2.0


def health_system(world: tcod.ecs.World) -> None:
    for room in rooms(world):
        pressure = room.components[Atmosphere].pressure_kpa
        hypoxic = pressure < HYPOXIA_PRESSURE_KPA
        for crew in list(occupants_of(room)):
            health = crew.components[Health]
            oxygenation = health.oxygenation
            hp = health.hp
            if hypoxic:
                oxygenation = max(0.0, oxygenation - OXYGENATION_LOSS_PER_TICK)
                hp = max(0.0, hp - HP_LOSS_PER_TICK_WHEN_HYPOXIC)
            else:
                oxygenation = min(1.0, oxygenation + OXYGENATION_RECOVERY_PER_TICK)

            conscious = oxygenation >= UNCONSCIOUS_OXYGENATION and hp > 0
            if conscious != health.conscious:
                crew.tags.discard(tags.CONSCIOUS if health.conscious else tags.UNCONSCIOUS)
                crew.tags.add(tags.CONSCIOUS if conscious else tags.UNCONSCIOUS)
                if not conscious:
                    log_event(world, f"{name_of(crew)} falls unconscious in {name_of(room)}.")
            crew.components[Health] = Health(
                hp=hp, oxygenation=oxygenation, conscious=conscious
            )
