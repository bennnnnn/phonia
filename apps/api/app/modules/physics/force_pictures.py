"""Draw the forces on a body: its free-body diagram, with numbers or none.

"Draw the forces on a box sliding down a 30° incline with friction" names no mass
and no μ, so no law solves it and no solver drew its picture; the model drew ASCII
art in a text block instead. The picture needs only the situation: the body, what
it rests on or hangs from, and what pulls or pushes it. Its arrows keep symbol
labels (mg, N, f, T); an angle the user gave is drawn as given, and none is
invented ("θ" when they named none).

A block pushed or pulled along a slope, or sliding up one, gets the push or the
rope and friction against the motion. Pulleys and bodies going round are
``force_rigs.py``'s. A situation neither knows (two ropes, a spring, an orbit)
draws nothing, and the model answers in words.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.modules.physics.force_rigs import listed, rig_picture
from app.modules.physics.schemas import (
    SimulationAngle,
    SimulationBlockSpec,
    SimulationBody,
    SimulationVector,
)
from app.modules.physics.solvers.force_scenes import free_body_scene
from app.modules.physics.solvers.friction import incline_scene
from app.services.solving import VerifiedPhysicsBlock

# Asked to see the forces: "draw the forces on", "free-body diagram", "what forces act".
_ASKS = re.compile(
    r"\bfree[\s-]?body\b|\bfbds?\b|\bforce\s+diagram\b"
    r"|\b(?:draw|sketch|show|label|illustrate|mark|diagram)\b[^.?!\n]{0,40}?\bforces?\b"
    r"|\bwhat\s+(?:are\s+the\s+)?forces\b|\bforces?\s+(?:acting|that\s+acts?|which\s+acts?)\b",
    re.IGNORECASE,
)
# The thing the forces act on. "The forces of the market" names none.
_BODY = re.compile(
    r"\b(?:box|block|crate|mass|object|cart|sled|sledge|ball|book|car|brick|skier|person|"
    r"man|woman|child|kid|load|weight|package|parcel|trolley|wagon|cylinder|body|bob|lamp|"
    r"sign|picture|chandelier|bucket|stone|rock|apple|puck|suitcase|chair|bag|toy|truck|"
    r"bus|bike|bicycle|cyclist|motorcycle|vehicle)\b",
    re.IGNORECASE,
)
_INCLINE = re.compile(r"\b(?:incline[sd]?|inclined\s+plane|ramp|slope)\b", re.IGNORECASE)
_HANGING = re.compile(
    r"\b(?:hang(?:s|ing)?|hung|suspended|dangl(?:es|ing))\b"
    r"|\bfrom\s+(?:a|the)\s+(?:ceiling|rope|string|cable|hook|chain|thread|beam)\b",
    re.IGNORECASE,
)
_FALLING = re.compile(
    r"\b(?:falling|falls|dropped|free[\s-]?fall|thrown|tossed|projectile)\b"
    r"|\b(?:in|through)\s+the\s+air\b|\bmid-?air\b",
    re.IGNORECASE,
)
_SURFACE = re.compile(
    r"\b(?:table|floor|ground|desk|surface|road|ice|counter|shelf)\b", re.IGNORECASE
)
_PULLED = re.compile(r"\b(?:pull(?:s|ed|ing)?|tow(?:s|ed|ing)?|drag(?:s|ged|ging)?)\b", re.I)
_PUSHED = re.compile(r"\bpush(?:es|ed|ing)?\b|\bshov(?:e|es|ed|ing)\b", re.IGNORECASE)
_FRICTION = re.compile(r"\b(?:friction|rough|kinetic|static|coefficient)\b|μ", re.IGNORECASE)
_NO_FRICTION = re.compile(
    r"\b(?:frictionless|smooth|without\s+friction|no\s+friction|"
    r"(?:ignore|ignoring|neglect|neglecting)\s+friction)\b",
    re.IGNORECASE,
)
# A body pushed, pulled or sliding on a real surface rubs against it: "A book is placed
# on a table and pushed" and "a body sliding on an inclined plane" had no friction drawn
# (2026-10-30, a Class 8 book, whose chapter on friction draws it). Only "smooth",
# "frictionless" and the like leave it out, and a body at rest with nothing pushing it
# has none ("lies on the floor, not moving", "resting on the floor of a moving lift").
_DRIVEN = re.compile(
    r"\b(?:push(?:es|ed|ing)?|pull(?:s|ed|ing)?|drag(?:s|ged|ging)?|tow(?:s|ed|ing)?"
    r"|shov(?:e|es|ed|ing))\b",
    re.IGNORECASE,
)
# "A moving bus" or "a moving lift" names how the vehicle goes, not the body sliding.
_SLIDING = re.compile(
    r"\b(?:slid(?:e|es|ing)|mov(?:es|ed)|moving(?!\s+(?:bus|car|train|truck|lift|elevator"
    r"|vehicle|walkway|belt|platform|escalator)))\b",
    re.IGNORECASE,
)
# A vehicle stands on a road: "the forces acting on a car" names no surface.
_VEHICLE = re.compile(
    r"\b(?:car|bus|truck|lorry|bike|bicycle|cyclist|motorcycle|scooter|vehicle|tractor)\b",
    re.IGNORECASE,
)
# A part of the vehicle ("a car engine piston", "a bicycle chain"), someone riding in it
# ("a person standing in a moving bus") or a hill: not the vehicle on a level road.
_VEHICLES = r"(?:car|bus|truck|lorry|bike|bicycle|motorcycle|scooter|vehicle|tractor|train)"
_RIDERS = (
    r"(?:person|man|woman|child|boy|girl|passenger|driver|people|box|block|crate|book|bag"
    r"|ball|suitcase|package|parcel|load)"
)
_NOT_THE_VEHICLE = re.compile(
    rf"\b{_VEHICLES}(?:'s)?\s+(?:engine|piston|tyres?|tires?|wheels?|chain|seat|door|battery"
    r"|axle|pedals?)\b"
    rf"|\b{_RIDERS}\b[^.?!]*\b(?:in|on|of|inside)\s+(?:a|the)\s+(?:moving\s+)?{_VEHICLES}\b"
    r"|\b(?:hill|slope|ramp|incline)\b",
    re.IGNORECASE,
)
# "Draw the forces on the car", "forces acting on a parked car": the body is named after.
_FORCES_ON = re.compile(r"\bforces?\b[^.?!]{0,30}?\bon\b", re.IGNORECASE)
# Pulled by another: a rope's tension, not its own engine, which this picture does not draw.
_STEADY = re.compile(r"\b(?:constant|uniform|steady)\s+(?:velocity|speed)\b", re.I)
_TOWED = re.compile(r"\b(?:towed|being\s+pulled|pulled\s+by|trailer)\b", re.IGNORECASE)
_PARKED = re.compile(r"\b(?:parked|at\s+rest|stationary|not\s+moving|standing\s+still)\b", re.I)
# No engine force forward: braking, coasting or slowing down.
_NO_DRIVE = re.compile(
    r"\b(?:brak(?:e|es|ed|ing)|coast(?:s|ed|ing)?|engine\s+off|slow(?:s|ing)\s+down"
    r"|decelerat\w*)\b",
    re.IGNORECASE,
)
_AT_REST = re.compile(
    r"\b(?:at\s+rest|rests|resting|stationary|held|not\s+moving|"
    r"(?:does\s+not|doesn'?t)\s+(?:slide|move))\b",
    re.IGNORECASE,
)
_UPHILL = re.compile(
    r"\b(?:up|upward|upwards)\s+(?:the\s+|an?\s+)?(?:incline|ramp|slope|hill)\b"
    r"|\b(?:slid(?:es|ing)?|mov(?:es|ing)|pushed|pulled|dragged)\s+up\b",
    re.IGNORECASE,
)
_ROPE = re.compile(r"\b(?:rope|string|cable|cord|chain)\b", re.IGNORECASE)
_DOWNHILL = re.compile(
    r"\b(?:push|pull|drag|tow|lower)\w*\s+(?:it\s+)?down\b"
    r"|\bdown\s+(?:the\s+|an?\s+)?(?:incline|ramp|slope|hill)\b",
    re.IGNORECASE,
)
_HORIZONTAL = re.compile(r"\bhorizontal(?:ly)?\b", re.IGNORECASE)
_RISING = re.compile(r"\b(?:thrown|tossed|launched|going|moving)\s+(?:straight\s+)?up", re.I)
_AIR = re.compile(r"\b(?:air\s+resistance|drag\s+force|air\s+friction|with\s+drag)\b", re.I)
_ROUND = re.compile(r"\b(?:ball|stone|rock|apple|bob|puck)\b", re.IGNORECASE)
# "a 30 degree incline", "30°", "at 25 degrees above the horizontal".
_ANGLE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:°|º|-?\s*deg(?:rees?)?\b)", re.IGNORECASE)
# A rope or a second body: more than one free-body picture, or one this file does not draw.
_TOO_MANY = re.compile(
    r"\b(?:two|three|both|pair\s+of)\s+(?:ropes|strings|cables|blocks|boxes|masses)\b"
    r"|\bpulley\b|\batwood\b|\bcurve\b|\bcircle\b|\bloop\b|\borbit\b|\bspring\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ForcePicture:
    """The free-body picture of a described situation and what it shows, in words."""

    spec: SimulationBlockSpec
    shows: str


def force_picture(text: str) -> ForcePicture | None:
    """The free-body diagram a request to see the forces on a body asks for, or None."""
    if len(text) > 600 or _ASKS.search(text) is None or _BODY.search(text) is None:
        return None
    friction = _FRICTION.search(text) is not None and _NO_FRICTION.search(text) is None
    rig = rig_picture(text, friction)
    if rig is not None:
        return ForcePicture(*rig)
    if _TOO_MANY.search(text) is not None:
        return None
    # At rest, or sliding at a constant velocity with nothing driving it: a lone friction
    # arrow would leave the picture's forces unbalanced.
    still = _AT_REST.search(text) is not None or _STEADY.search(text) is not None
    rubs = friction or (
        _NO_FRICTION.search(text) is None
        and (_DRIVEN.search(text) is not None or (_SLIDING.search(text) is not None and not still))
    )
    if _VEHICLE.fullmatch(_subject(text)) is not None:
        return _vehicle(text)
    if _INCLINE.search(text) is not None:
        return _on_incline(text, rubs)
    if _HANGING.search(text) is not None:
        return _hanging()
    if _FALLING.search(text) is not None:
        return _in_the_air(text)
    if _SURFACE.search(text) is not None:
        return _on_surface(text, rubs)
    return None


def _subject(text: str) -> str:
    """The body whose forces are asked for: the one just after "forces on", else the
    first one named ("A lamp hangs from the ceiling of a bus" is the lamp's)."""
    asked = _FORCES_ON.search(text)
    body = _BODY.search(text, asked.end(), asked.end() + 40) if asked else None
    body = body or _BODY.search(text)
    return body.group(0).lower() if body else ""


def _angle(text: str) -> float | None:
    match = _ANGLE.search(text)
    if match is None:
        return None
    deg = float(match[1])
    return deg if 0 < deg < 90 else None


def _on_incline(text: str, friction: bool) -> ForcePicture | None:
    deg = _angle(text)
    held = _AT_REST.search(text) is not None
    push = _PUSHED.search(text) is not None
    rope = not push and (_PULLED.search(text) is not None or _ROPE.search(text) is not None)
    if push or rope or _UPHILL.search(text) is not None:
        return _driven_on_incline(text, deg, friction, held=held, push=push, rope=rope)
    specs = incline_scene(deg or 30.0, mu=1.0 if friction else 0.0, held=held)
    if not specs:
        return None
    shown = f"{deg:g}°" if deg else "θ"
    forces = ["its weight mg", "the normal force N"]
    if friction or held:
        forces.append("friction f up the slope")
    spec = specs[0]
    angles = [angle.model_copy(update={"label": shown}) for angle in spec.angles]
    shows = f"a block on a {shown} slope with " + listed(forces)
    alt = f"A block on a {shown} slope: " + listed(forces) + "."
    return ForcePicture(spec.model_copy(update={"angles": angles, "alt": alt}), shows)


def _driven_on_incline(
    text: str, deg: float | None, friction: bool, *, held: bool, push: bool, rope: bool
) -> ForcePicture | None:
    """A push or a rope along the slope, or a block sliding up it: friction opposes the
    motion. Held still by the push or the rope, friction takes whichever way keeps the
    block from sliding, so it is named in words and not drawn."""
    down = (push or rope) and _DOWNHILL.search(text) is not None
    moving_up = not held and not down
    specs = incline_scene(deg or 30.0, mu=1.0 if friction and down and not held else 0.0)
    if not specs:
        return None
    spec = specs[0]
    theta = math.radians(deg or 30.0)
    # The slope falls to the right: down it is (cos θ, -sin θ), its surface normal (sin θ, cos θ).
    along = (math.cos(theta), -math.sin(theta)) if down else (-math.cos(theta), math.sin(theta))
    shown = f"{deg:g}°" if deg else "θ"
    forces = ["its weight mg", "the normal force N"]
    vectors: list[SimulationVector] = []
    if push or rope:
        name = "F" if push else "T"
        flat = push and _HORIZONTAL.search(text) is not None
        dx, dy = ((1.0 if down else -1.0), 0.0) if flat else along
        vectors.append(SimulationVector(anchor=[0.0, 0.0], dx=dx, dy=dy, label=name, body=0))
        way = "horizontal" if flat else f"{'down' if down else 'up'} the slope"
        forces.append(f"the {'push' if push else 'rope tension'} {name}, {way}")
    if friction and moving_up:
        lift = spec.bodies[0].radius * 0.6
        vectors.append(
            SimulationVector(
                anchor=[-lift * math.sin(theta), -lift * math.cos(theta)],
                dx=0.6 * math.cos(theta),
                dy=-0.6 * math.sin(theta),
                label="f",
                body=0,
            )
        )
        forces.append("friction f down the slope, against the motion")
    elif friction and down and not held:
        forces.append("friction f up the slope, against the motion")
    shows = f"a block on a {shown} slope with " + listed(forces)
    if friction and held:
        shows += " (friction acts along the slope, whichever way keeps the block still)"
    angles = [angle.model_copy(update={"label": shown}) for angle in spec.angles]
    alt = f"A block on a {shown} slope: " + listed(forces) + "."
    update = {"angles": angles, "alt": alt, "vectors": vectors}
    return ForcePicture(spec.model_copy(update=update), shows)


def _hanging() -> ForcePicture:
    vectors = [
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=1.0, label="T", body=0),
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label="mg", body=0),
    ]
    forces = ["the tension T up the rope", "its weight mg down"]
    spec = free_body_scene(vectors, shape="box", alt="A hanging mass: " + listed(forces) + ".")
    return ForcePicture(spec[0], "a hanging mass with " + listed(forces))


def _in_the_air(text: str) -> ForcePicture:
    vectors = [SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label="mg", body=0)]
    forces = ["its weight mg down"]
    if _AIR.search(text) is not None:
        # Drag opposes the motion: down while it rises, up while it falls.
        rising = _RISING.search(text) is not None
        vectors.append(
            SimulationVector(
                anchor=[0.0, 0.0], dx=0.0, dy=-0.4 if rising else 0.4, label="drag", body=0
            )
        )
        forces.append(f"air resistance {'down' if rising else 'up'}")
    shape = "circle" if _ROUND.search(text) else "box"
    alt = "A body in the air: " + listed(forces) + "."
    spec = free_body_scene(vectors, shape=shape, alt=alt)
    return ForcePicture(spec[0], "a body in the air with " + listed(forces))


def _on_surface(text: str, friction: bool) -> ForcePicture:
    """A box on a level floor: weight and normal, then the pull or push, then friction."""
    size = 0.5
    pulled = _PULLED.search(text) is not None
    pushed = not pulled and _PUSHED.search(text) is not None
    deg = _angle(text) if pulled or pushed else None
    lift = math.sin(math.radians(deg)) * 0.7 if deg else 0.0
    vectors = [
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label="mg", body=0),
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=1.0 - lift, label="N", body=0),
    ]
    forces = ["its weight mg", "the normal force N"]
    angles: list[SimulationAngle] = []
    if pulled or pushed:
        name = "T" if pulled else "F"
        rad = math.radians(deg or 0.0)
        vectors.append(
            SimulationVector(
                anchor=[size, 0.0],
                dx=0.7 * math.cos(rad),
                dy=0.7 * math.sin(rad),
                label=name,
                body=0,
            )
        )
        forces.append(f"the {'pull' if pulled else 'push'} {name}")
        if deg:
            angles.append(
                SimulationAngle(vertex=[size, size], start_deg=0.0, end_deg=deg, label=f"{deg:g}°")
            )
    if friction and (pulled or pushed or _SLIDING.search(text) is not None):
        vectors.append(
            SimulationVector(anchor=[-size, -size * 0.6], dx=-0.5, dy=0.0, label="f", body=0)
        )
        forces.append("friction f against the motion")
    # The body named, drawn as a box: "a man on a level surface", not "a box".
    body = _BODY.search(text)
    noun = body.group(0).lower() if body else "box"
    article = "an" if noun[0] in "aeiou" else "a"
    alt = f"{article.capitalize()} {noun} on a level surface: " + listed(forces) + "."
    spec = _level_scene(vectors, angles, alt)
    return ForcePicture(spec, f"{article} {noun} on a level surface with " + listed(forces))


def _vehicle(text: str) -> ForcePicture | None:
    """A vehicle on a level road: weight and normal, and while it drives, the engine's
    forward force and the friction and air resistance against it."""
    vectors = [
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label="mg", body=0),
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=1.0, label="N", body=0),
    ]
    if _NOT_THE_VEHICLE.search(text) is not None or _TOWED.search(text) is not None:
        return None
    forces = ["its weight mg", "the normal force N from the road"]
    if _PARKED.search(text) is None and _AT_REST.search(text) is None:
        # Braking or coasting: nothing drives it, and the resistance slows it.
        if _NO_DRIVE.search(text) is None:
            vectors.append(SimulationVector(anchor=[0.5, 0.0], dx=0.7, dy=0.0, label="F", body=0))
            forces.append("the driving force F forward")
        vectors.append(SimulationVector(anchor=[-0.5, -0.3], dx=-0.5, dy=0.0, label="f", body=0))
        forces.append("friction and air resistance f backward")
    alt = "A vehicle on a level road: " + listed(forces) + "."
    spec = _level_scene(vectors, [], alt)
    return ForcePicture(spec, "a vehicle on a level road with " + listed(forces))


def _level_scene(
    vectors: list[SimulationVector], angles: list[SimulationAngle], alt: str
) -> SimulationBlockSpec:
    size = 0.5
    centre = [0.0, size]
    return SimulationBlockSpec(
        type="free_body",
        title="Free-Body Diagram",
        title_key="free_body",
        bodies=[SimulationBody(path=[centre, centre], radius=size, shape="box")],
        vectors=vectors,
        angles=angles,
        ground=True,
        x_min=-3.0,
        x_max=3.0,
        y_min=-0.5,
        y_max=3.0,
        alt=alt,
    )


def _picture_note(shows: str) -> str:
    return (
        f"Physics picture: the free-body diagram shown below the words is {shows}; call it "
        "the diagram below, never say where or how it is drawn. "
        "Do not draw it yourself: no ASCII or text-art sketch, no ```text, ```mermaid or "
        "```simulation fence for it. Name each force on the body, what exerts it and its "
        "direction, with its size in symbols (mg, N = mg cos θ, f = μN, T). Use only numbers "
        "the user gave. No Answer heading and no final value unless they asked for one and "
        "gave what it needs. Never mention a system block or that a diagram is attached."
    )


def force_picture_block(text: str) -> VerifiedPhysicsBlock | None:
    """A turn's picture with no solve behind it: the scene, and no answer or card."""
    picture = force_picture(text)
    if picture is None:
        return None
    return VerifiedPhysicsBlock(
        text=_picture_note(picture.shows),
        subject="physics",
        canonical_fence=picture.spec.model_dump(),
        allow_direct=False,
    )
