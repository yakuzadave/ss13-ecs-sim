"""Utility AI: subjective beliefs + personality + competence -> actions.

Cognitive system. Scoring reads ONLY the actor's beliefs (via
belief_value / beliefs_of), never objective room atmosphere. Each
score keeps per-term contributions so decisions stay explainable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import (
    ActionState,
    Competence,
    DoorState,
    FactState,
    Personality,
)
from station_sim.ecs.helpers import (
    belief_value,
    beliefs_of,
    doors_connecting,
    find_belief,
    location_of,
    other_side,
)
from station_sim.ecs.queries import conscious_crew, name_of
from station_sim.ecs.world import log_event, new_transient_entity, sim_state
from station_sim.systems.communication import reportable_pressure_transitions

DANGEROUS_PRESSURE_KPA = 70.0


@dataclass(frozen=True)
class UtilityScore:
    action_kind: str
    value: float
    contributions: dict[str, float] = field(default_factory=dict)
    targets: tuple[tcod.ecs.Entity, ...] = ()


@dataclass(frozen=True)
class ActorContext:
    actor: tcod.ecs.Entity
    room: tcod.ecs.Entity
    personality: Personality
    competence: Competence
    believed_current_pressure: float | None
    worst_remote_pressure_belief: tuple[tcod.ecs.Entity, float] | None
    reportable_transitions: tuple = ()


def _build_context(actor: tcod.ecs.Entity) -> ActorContext | None:
    room = location_of(actor)
    if room is None:
        return None
    believed_here = belief_value(actor, room, "room_pressure_kpa")
    worst: tuple[tcod.ecs.Entity, float] | None = None
    for fact in beliefs_of(actor):
        state = fact.components.get(FactState)
        if state is None or state.predicate != "room_pressure_kpa":
            continue
        subject = fact.relation_tag.get(relations.SUBJECT)
        if subject is None or subject is room:
            continue
        if not isinstance(state.value, (int, float)):
            continue
        if worst is None or (state.value, name_of(subject)) < (worst[1], name_of(worst[0])):
            worst = (subject, float(state.value))
    return ActorContext(
        actor=actor,
        room=room,
        personality=actor.components[Personality],
        competence=actor.components[Competence],
        believed_current_pressure=believed_here,
        worst_remote_pressure_belief=worst,
        reportable_transitions=tuple(reportable_pressure_transitions(actor)),
    )


def _danger_of(believed_pressure: float | None) -> float:
    """0..1 danger from a believed pressure. Unknown pressure = no danger."""
    if believed_pressure is None or believed_pressure >= DANGEROUS_PRESSURE_KPA:
        return 0.0
    return min(1.0, (DANGEROUS_PRESSURE_KPA - believed_pressure) / DANGEROUS_PRESSURE_KPA)


def score_evacuate(ctx: ActorContext) -> UtilityScore:
    danger = _danger_of(ctx.believed_current_pressure)
    contributions = {
        "personal_danger": 0.6 * danger,
        "self_preservation": 0.5 * ctx.personality.self_preservation * danger,
        "bravery_resists": -0.3 * ctx.personality.bravery * danger,
        "duty_resists": -0.2 * ctx.personality.duty * danger,
    }
    if danger > 0:
        contributions["base"] = 0.1
    return UtilityScore("evacuate", sum(contributions.values()), contributions)


def _closable_door_to_danger(ctx: ActorContext) -> tcod.ecs.Entity | None:
    """An open door between the actor's room and a believed-dangerous room."""
    for door in doors_connecting(ctx.room):
        state = door.components[DoorState]
        if not state.open or state.locked:
            continue
        neighbor = other_side(door, ctx.room)
        believed = belief_value(ctx.actor, neighbor, "room_pressure_kpa")
        if _danger_of(believed) > 0:
            return door
    return None


def score_close_door(ctx: ActorContext) -> UtilityScore:
    door = _closable_door_to_danger(ctx)
    if door is None:
        return UtilityScore("close_door", 0.0, {})
    danger = _danger_of(
        belief_value(ctx.actor, other_side(door, ctx.room), "room_pressure_kpa")
    )
    contributions = {
        "base_urgency": 0.2 * danger,
        "duty": 0.3 * ctx.personality.duty * danger,
        "engineering_competence": 0.3 * ctx.competence.engineering * danger,
        "bravery": 0.15 * ctx.personality.bravery * danger,
        "personal_danger": -0.1 * _danger_of(ctx.believed_current_pressure),
        "self_preservation": -0.1 * ctx.personality.self_preservation * danger,
    }
    return UtilityScore("close_door", sum(contributions.values()), contributions, (door,))


def score_report_hazard(ctx: ActorContext) -> UtilityScore:
    """Report only on semantic state transitions — never repeat a state
    already reported for that subject.
    """
    if not ctx.reportable_transitions:
        return UtilityScore("report_hazard", 0.0, {})
    from station_sim.domain.components import PressureState

    subject, new_state, _fact = ctx.reportable_transitions[0]
    urgency = 1.0 if new_state is not PressureState.NORMAL else 0.5
    contributions = {
        "base_urgency": 0.25 * urgency,
        "duty": 0.4 * ctx.personality.duty * urgency,
        "empathy": 0.3 * ctx.personality.empathy * urgency,
    }
    return UtilityScore(
        "report_hazard", sum(contributions.values()), contributions, (subject,)
    )


def score_investigate(ctx: ActorContext) -> UtilityScore:
    if ctx.worst_remote_pressure_belief is None:
        return UtilityScore("investigate", 0.0, {})
    subject, pressure = ctx.worst_remote_pressure_belief
    danger = _danger_of(pressure)
    # Only investigate a room reachable through an open door from here.
    reachable = None
    for door in doors_connecting(ctx.room):
        if door.components[DoorState].open and other_side(door, ctx.room) is subject:
            reachable = subject
    if reachable is None:
        return UtilityScore("investigate", 0.0, {})
    contributions = {
        "curiosity": 0.4 * ctx.personality.curiosity * danger,
        "duty": 0.3 * ctx.personality.duty * danger,
        "bravery": 0.2 * ctx.personality.bravery * danger,
        "self_preservation": -0.4 * ctx.personality.self_preservation * danger,
    }
    return UtilityScore("investigate", sum(contributions.values()), contributions, (reachable,))


def score_idle(ctx: ActorContext) -> UtilityScore:
    return UtilityScore("idle", 0.02, {"base": 0.02})


SCORERS = (score_evacuate, score_close_door, score_report_hazard, score_investigate, score_idle)


def select_action(actor: tcod.ecs.Entity) -> UtilityScore | None:
    ctx = _build_context(actor)
    if ctx is None:
        return None
    scores = [scorer(ctx) for scorer in SCORERS]
    # Deterministic tie-break: stable order of SCORERS.
    return max(scores, key=lambda s: s.value)


def utility_ai_system(world: tcod.ecs.World) -> None:
    tick = sim_state(world).tick
    for crew in sorted(conscious_crew(world), key=name_of):
        score = select_action(crew)
        if score is None:
            continue
        action = new_transient_entity(world, "action")
        action.tags.add(tags.ACTION)
        action.components[ActionState] = ActionState(
            kind=score.action_kind,
            utility=round(score.value, 4),
            selected_tick=tick,
            status="pending",
        )
        action.relation_tag[relations.PERFORMED_BY] = crew
        for target in score.targets:
            action.relation_tags_many[relations.TARGETS].add(target)
        log_event(
            world,
            f"{name_of(crew)} selects {score.action_kind} "
            f"(utility={score.value:.2f}, terms={score.contributions}).",
        )
