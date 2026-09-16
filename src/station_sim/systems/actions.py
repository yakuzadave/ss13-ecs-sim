"""Actions: execute pending action entities against the world."""

from __future__ import annotations

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import ActionState, DoorState
from station_sim.ecs.helpers import (
    doors_connecting,
    find_belief,
    move_entity,
    other_side,
)
from station_sim.ecs.queries import name_of
from station_sim.ecs.world import log_event
from station_sim.systems.communication import transmit_report


def _fail(world: tcod.ecs.World, action: tcod.ecs.Entity, state: ActionState, why: str) -> None:
    actor = action.relation_tag[relations.PERFORMED_BY]
    action.components[ActionState] = ActionState(
        state.kind, state.utility, state.selected_tick, "failed"
    )
    log_event(world, f"{name_of(actor)} fails to {state.kind}: {why}.")


def _complete(world: tcod.ecs.World, action: tcod.ecs.Entity, state: ActionState, what: str) -> None:
    action.components[ActionState] = ActionState(
        state.kind, state.utility, state.selected_tick, "completed"
    )
    log_event(world, what)


def action_system(world: tcod.ecs.World) -> None:
    # Deterministic execution order: performer name, then action kind.
    pending = [
        a
        for a in world.Q.all_of(tags=[tags.ACTION])
        if a.components[ActionState].status == "pending"
    ]
    pending.sort(
        key=lambda a: (
            name_of(a.relation_tag[relations.PERFORMED_BY]),
            a.components[ActionState].kind,
        )
    )
    for action in pending:
        state = action.components[ActionState]
        actor = action.relation_tag[relations.PERFORMED_BY]
        targets = set(action.relation_tags_many[relations.TARGETS])

        if state.kind == "idle":
            _complete(world, action, state, f"{name_of(actor)} idles.")

        elif state.kind == "evacuate":
            moved = False
            for door in doors_connecting(actor.relation_tag[relations.LOCATED_IN]):
                door_state = door.components[DoorState]
                if door_state.open and not door_state.locked:
                    destination = other_side(door, actor.relation_tag[relations.LOCATED_IN])
                    move_entity(actor, destination)
                    _complete(
                        world, action, state,
                        f"{name_of(actor)} evacuates to {name_of(destination)}.",
                    )
                    moved = True
                    break
            if not moved:
                _fail(world, action, state, "no open door")

        elif state.kind == "close_door":
            (door,) = targets
            door_state = door.components[DoorState]
            if door_state.locked:
                _fail(world, action, state, "door is locked")
            else:
                door.components[DoorState] = DoorState(
                    open=False,
                    locked=door_state.locked,
                    powered=door_state.powered,
                    integrity=door_state.integrity,
                )
                _complete(
                    world, action, state,
                    f"{name_of(actor)} closes {name_of(door)}.",
                )

        elif state.kind == "report_hazard":
            # Report the selected subject's operative pressure belief and
            # record the transition so it is not re-reported next tick.
            from station_sim.domain.components import classify_pressure
            from station_sim.systems.communication import (
                record_report,
                reportable_pressure_transitions,
            )

            transitions = reportable_pressure_transitions(actor)
            chosen = None
            if targets:
                (subject,) = targets
                for t_subject, t_state, t_fact in transitions:
                    if t_subject is subject:
                        chosen = (t_subject, t_state, t_fact)
                        break
            elif transitions:
                chosen = transitions[0]
            if chosen is None:
                _fail(world, action, state, "no state transition to report")
            else:
                t_subject, t_state, t_fact = chosen
                delivered = transmit_report(world, actor, t_fact)
                if delivered:
                    record_report(actor, t_subject, t_state)
                    _complete(
                        world, action, state,
                        f"{name_of(actor)} reports {name_of(t_subject)} "
                        f"pressure is {t_state.name} ({delivered} recipient(s)).",
                    )
                else:
                    _fail(world, action, state, "no eligible receivers")

        elif state.kind == "investigate":
            (destination,) = targets
            door_ok = False
            for door in doors_connecting(actor.relation_tag[relations.LOCATED_IN]):
                if (
                    door.components[DoorState].open
                    and other_side(door, actor.relation_tag[relations.LOCATED_IN]) is destination
                ):
                    door_ok = True
                    break
            if door_ok:
                move_entity(actor, destination)
                _complete(
                    world, action, state,
                    f"{name_of(actor)} investigates {name_of(destination)}.",
                )
            else:
                _fail(world, action, state, "no open path")

        else:
            _fail(world, action, state, f"unknown action kind {state.kind!r}")
