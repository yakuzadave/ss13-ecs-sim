"""Communication: radios as real entities, belief propagation by report.

Cognitive system. There is no everyone_knows() shortcut: a report
creates a derived belief for each eligible receiver, with lower
confidence and provenance links back to the sender and original fact.
"""

from __future__ import annotations

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import FactState, Health, RadioState
from station_sim.ecs.helpers import give_belief, radio_owned_by
from station_sim.ecs.queries import crew_members, name_of
from station_sim.ecs.world import log_event, new_transient_entity, sim_state

RADIO_CONFIDENCE_RETENTION = 0.85


def reportable_pressure_transitions(
    actor: tcod.ecs.Entity,
) -> list[tuple[tcod.ecs.Entity, "PressureState", tcod.ecs.Entity]]:
    """Pressure beliefs whose semantic state differs from what the actor
    last reported. Returns (subject, new_state, belief_fact) tuples,
    sorted by most-severe-first for determinism.

    A reportable transition is:
      - a non-NORMAL state never reported for that subject, or
      - any state change (escalation OR return to NORMAL/"clearing")
        after a previous report.
    """
    from station_sim.domain.components import (
        FactState,
        PressureState,
        ReportMemory,
        classify_pressure,
    )
    from station_sim.ecs.helpers import beliefs_of, subject_of

    memory = actor.components.get(ReportMemory)
    reported = memory.reported if memory else {}

    # Operative belief per subject: newest/priority via find_belief.
    from station_sim.ecs.helpers import find_belief

    subjects: dict[tcod.ecs.Entity, None] = {}
    for fact in beliefs_of(actor):
        state = fact.components.get(FactState)
        if state is None or state.predicate != "room_pressure_kpa":
            continue
        subject = subject_of(fact)
        if subject is not None:
            subjects[subject] = None

    transitions = []
    for subject in subjects:
        fact = find_belief(actor, subject, "room_pressure_kpa")
        if fact is None:
            continue
        value = fact.components[FactState].value
        if not isinstance(value, (int, float)):
            continue
        # Reports originate from direct observation only. Relaying
        # second-hand radio states would spam the channel with duplicate
        # information everyone already received from the observer.
        if fact.components[FactState].source_kind != "direct_observation":
            continue
        new_state = classify_pressure(value)
        key = (name_of(subject), "room_pressure_kpa")
        last = reported.get(key)
        if last == new_state.name:
            continue
        if last is None and new_state is PressureState.NORMAL:
            continue  # nobody radios "all is normal" unprompted
        transitions.append((subject, new_state, fact))
    # Deterministic order: most severe state first, then subject name.
    severity = {
        PressureState.VACUUM: 0,
        PressureState.CRITICAL: 1,
        PressureState.LOW: 2,
        PressureState.NORMAL: 3,
    }
    transitions.sort(key=lambda t: (severity[t[1]], name_of(t[0])))
    return transitions


def record_report(actor: tcod.ecs.Entity, subject: tcod.ecs.Entity, state: "PressureState") -> None:
    from station_sim.domain.components import ReportMemory

    memory = actor.components.get(ReportMemory)
    if memory is not None:
        memory.reported[(name_of(subject), "room_pressure_kpa")] = state.name



def _radio_usable(radio: tcod.ecs.Entity | None) -> RadioState | None:
    if radio is None:
        return None
    state = radio.components.get(RadioState)
    if state is None or not state.powered:
        return None
    return state


def can_transmit(sender: tcod.ecs.Entity) -> RadioState | None:
    if not sender.components[Health].conscious:
        return None
    return _radio_usable(radio_owned_by(sender))


def eligible_receivers(world: tcod.ecs.World, sender: tcod.ecs.Entity) -> list[tcod.ecs.Entity]:
    sender_radio = can_transmit(sender)
    if sender_radio is None:
        return []
    receivers = []
    for crew in sorted(crew_members(world), key=name_of):
        if crew is sender:
            continue
        state = _radio_usable(radio_owned_by(crew))
        if state is not None and state.channel == sender_radio.channel:
            receivers.append(crew)
    return receivers


def transmit_report(world: tcod.ecs.World, sender: tcod.ecs.Entity, fact: tcod.ecs.Entity) -> int:
    """Send a fact over the radio. Returns the number of recipients.

    Each recipient gets a NEW derived fact entity with lower confidence
    and provenance links (SOURCE -> sender, DERIVED_FROM -> fact).
    """
    sender_state = fact.components[FactState]
    tick = sim_state(world).tick
    delivered = 0
    for receiver in eligible_receivers(world, sender):
        derived = new_transient_entity(world, "fact")
        derived.tags.add(tags.FACT)
        derived.components[FactState] = FactState(
            predicate=sender_state.predicate,
            value=sender_state.value,
            confidence=sender_state.confidence * RADIO_CONFIDENCE_RETENTION,
            source_kind="radio_report",
            observed_tick=tick,
        )
        subject = fact.relation_tag.get(relations.SUBJECT)
        if subject is not None:
            derived.relation_tag[relations.SUBJECT] = subject
        derived.relation_tag[relations.SOURCE] = sender
        derived.relation_tag[relations.DERIVED_FROM] = fact
        give_belief(receiver, derived)
        delivered += 1
    if delivered:
        sim_state(world).radio_messages += 1
        log_event(
            world,
            f"{name_of(sender)} radios: {sender_state.predicate} = "
            f"{sender_state.value} ({delivered} recipient(s)).",
        )
    return delivered
