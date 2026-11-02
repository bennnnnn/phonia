"""Free-body pictures of a rope over a pulley, or a body going round, with numbers or none.

``force_pictures.py`` draws one body on a slope, a floor or a rope. These are the rigs it
handed to words: two masses on one rope over a pulley (an Atwood machine), a block on a
table pulled by a hanging mass over a pulley at the edge, a car on a curve (flat or
banked, seen from behind), and a ball on a string at the top or the bottom of a vertical
circle. Arrows keep symbol labels (m₁g, T, N, f); a bank angle the user gave is drawn as
given, θ otherwise. A rig this file does not know (a block on a slope pulled over a
pulley, a cart in a loop of track) draws nothing.
"""

from __future__ import annotations

import re
from typing import Literal

from app.modules.physics.schemas import (
    SimulationBlockSpec,
    SimulationBody,
    SimulationPulley,
    SimulationSolid,
    SimulationTether,
    SimulationVector,
)
from app.modules.physics.solvers.friction import incline_scene

_PULLEY = re.compile(r"\bpulleys?\b|\batwood\b", re.IGNORECASE)
# Two bodies on the rope: "two blocks", "masses", "m1 and m2".
_PAIR = re.compile(
    r"\b(?:two|both|pair\s+of)\b|\b(?:masses|blocks|boxes|weights|objects)\b|\bm_?1\b|m₁|\batwood\b",
    re.IGNORECASE,
)
_ON_TABLE = re.compile(
    r"\b(?:table|desk|bench|counter|shelf|floor|horizontal\s+surface)\b", re.IGNORECASE
)
_SLOPE = re.compile(r"\b(?:incline[sd]?|inclined\s+plane|ramp|slope)\b", re.IGNORECASE)
_CURVE = re.compile(
    r"\bcurve[sd]?\b|\bbend\b|\bbank(?:ed|ing)?\b|\broundabout\b"
    r"|\b(?:turn(?:s|ing)?|round|around|rounding)\s+(?:a|the)\s+corner\b",
    re.IGNORECASE,
)
_VEHICLE = re.compile(
    r"\b(?:car|truck|lorry|bus|van|bike|bicycle|cyclist|motorcycle|motorbike|vehicle|"
    r"racer|race\s+car)\b",
    re.IGNORECASE,
)
_BANKED = re.compile(r"\bbank(?:ed|ing)?\b", re.IGNORECASE)
_VERTICAL_CIRCLE = re.compile(
    r"\bvertical\s+circle\b|\b(?:swung|swinging|whirled|whirling|spun)\b[^.?!\n]{0,30}?\bcircle\b",
    re.IGNORECASE,
)
_STRING = re.compile(r"\b(?:string|rope|cord|chain|thread|wire)\b", re.IGNORECASE)
_TOP = re.compile(r"\btop\b|\bhighest\s+point\b", re.IGNORECASE)
_BOTTOM = re.compile(r"\bbottom\b|\blowest\s+point\b", re.IGNORECASE)
_ROUND = re.compile(r"\b(?:ball|stone|rock|bob|apple|puck)\b", re.IGNORECASE)
# "a 20 degree bank", "banked at 15°".
_ANGLE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:°|º|-?\s*deg(?:rees?)?\b)", re.IGNORECASE)

RigPicture = tuple[SimulationBlockSpec, str]


def rig_picture(text: str, friction: bool) -> RigPicture | None:
    """The picture of a pulley rig or of a body going round, and what it shows; or None."""
    if _PULLEY.search(text) is not None:
        return _pulley(text, friction)
    if _VERTICAL_CIRCLE.search(text) is not None:
        return _vertical_circle(text)
    if _CURVE.search(text) is not None and _VEHICLE.search(text) is not None:
        return _banked_curve(text) if _BANKED.search(text) else _flat_curve(friction, text)
    return None


def listed(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _pulley(text: str, friction: bool) -> RigPicture | None:
    if _SLOPE.search(text) is not None:
        return None
    if _ON_TABLE.search(text) is not None:
        return _table_pulley(friction)
    if _PAIR.search(text) is not None:
        return _atwood()
    return None


def _atwood() -> RigPicture:
    """Two masses on one rope over a wheel: tension up on both, each one's weight down."""
    wheel, axle, size = 0.5, 3.55, 0.36
    left, right = [-wheel, 1.9], [wheel, 2.6]
    vectors = [
        SimulationVector(anchor=[0.0, size], dx=0.0, dy=1.0, label="T", body=0),
        SimulationVector(anchor=[0.0, -size], dx=0.0, dy=-1.0, label="m₁g", body=0),
        SimulationVector(anchor=[0.0, size], dx=0.0, dy=1.0, label="T", body=1),
        SimulationVector(anchor=[0.0, -size], dx=0.0, dy=-1.0, label="m₂g", body=1),
    ]
    forces = ["the tension T up the rope on each mass", "their weights m₁g and m₂g down"]
    spec = SimulationBlockSpec(
        type="free_body",
        title="Atwood Machine",
        title_key="atwood",
        bodies=[
            SimulationBody(path=[left, left], radius=size, role="primary", shape="box"),
            SimulationBody(path=[right, right], radius=size, role="secondary", shape="box"),
        ],
        pulley=SimulationPulley(centre=[0.0, axle], radius=wheel),
        tethers=[
            SimulationTether(anchor=[-wheel, axle], body=0),
            SimulationTether(anchor=[wheel, axle], body=1),
        ],
        vectors=vectors,
        x_min=-2.4,
        x_max=2.4,
        y_min=0.0,
        y_max=axle + wheel + 0.4,
        alt="Two masses on one rope over a pulley: " + listed(forces) + ".",
    )
    return spec, "two masses on a rope over a pulley, with " + listed(forces)


def _table_pulley(friction: bool) -> RigPicture:
    """A block on a table, a rope over a wheel at the edge, a mass hanging from it."""
    size, wheel, top = 0.35, 0.3, 1.5
    block = [-0.6, top + size]
    # The rope leaves the block level with its centre, over the top of the wheel.
    axle = [1.8, top + size - wheel]
    hanging = [axle[0] + wheel, 0.45]
    vectors = [
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label="m₁g", body=0),
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=1.0, label="N", body=0),
        SimulationVector(anchor=[size, 0.0], dx=1.0, dy=0.0, label="T", body=0),
        SimulationVector(anchor=[0.0, size], dx=0.0, dy=1.0, label="T", body=1),
        SimulationVector(anchor=[0.0, -size], dx=0.0, dy=-1.0, label="m₂g", body=1),
    ]
    forces = [
        "on the block its weight m₁g, the normal force N and the tension T toward the pulley",
        "on the hanging mass the tension T up and its weight m₂g down",
    ]
    if friction:
        vectors.insert(
            3,
            SimulationVector(anchor=[-size, -size * 0.6], dx=-0.5, dy=0.0, label="f", body=0),
        )
        forces.insert(1, "friction f on the block, away from the pulley")
    spec = SimulationBlockSpec(
        type="free_body",
        title="Free-Body Diagram",
        title_key="free_body",
        bodies=[
            SimulationBody(path=[block, block], radius=size, role="primary", shape="box"),
            SimulationBody(path=[hanging, hanging], radius=size, role="secondary", shape="box"),
        ],
        solids=[SimulationSolid(rect=[-3.0, 0.0, 1.5, top])],
        pulley=SimulationPulley(centre=axle, radius=wheel),
        tethers=[
            SimulationTether(anchor=[axle[0], top + size], body=0),
            SimulationTether(anchor=[hanging[0], axle[1]], body=1),
        ],
        vectors=vectors,
        x_min=-3.2,
        x_max=3.0,
        y_min=-0.3,
        y_max=2.8,
        alt="A block on a table pulled over a pulley by a hanging mass: " + listed(forces) + ".",
    )
    return spec, "a block on a table and a hanging mass on one rope over a pulley: " + listed(
        forces
    )


def _flat_curve(friction: bool, text: str) -> RigPicture | None:
    """A car on a level curve seen from behind: friction is what turns it."""
    if not friction and re.search(r"\b(?:frictionless|ice|icy)\b", text, re.IGNORECASE):
        return None
    size = 0.5
    centre = [0.0, size]
    vectors = [
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label="mg", body=0),
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=1.0, label="N", body=0),
        SimulationVector(anchor=[-size, -size * 0.8], dx=-0.7, dy=0.0, label="f", body=0),
        SimulationVector(
            anchor=[0.0, size + 0.35], dx=-1.0, dy=0.0, label="a", role="motion", body=0
        ),
    ]
    forces = [
        "its weight mg",
        "the normal force N",
        "friction f toward the centre of the curve, which turns it",
    ]
    spec = SimulationBlockSpec(
        type="free_body",
        title="Free-Body Diagram",
        title_key="free_body",
        bodies=[SimulationBody(path=[centre, centre], radius=size, shape="box")],
        vectors=vectors,
        ground=True,
        x_min=-3.0,
        x_max=3.0,
        y_min=-0.5,
        y_max=3.0,
        alt="A car on a level curve, seen from behind: "
        + listed(forces)
        + "; its acceleration a points to the centre.",
    )
    return spec, "a car on a level curve seen from behind, with " + listed(forces)


def _banked_curve(text: str) -> RigPicture | None:
    """A car on a banked road seen from behind: weight down, normal tilted to the centre."""
    match = _ANGLE.search(text)
    deg = float(match[1]) if match and 0 < float(match[1]) < 90 else None
    specs = incline_scene(deg or 20.0, mu=0.0)
    if not specs:
        return None
    shown = f"{deg:g}°" if deg else "θ"
    spec = specs[0]
    # The bank falls to the right, so the inside of the curve, its centre, is that way.
    vectors = [
        SimulationVector(anchor=[0.0, 0.0], dx=1.0, dy=0.0, label="a", role="motion", body=0)
    ]
    angles = [angle.model_copy(update={"label": shown}) for angle in spec.angles]
    forces = ["its weight mg", "the normal force N, tilted toward the centre of the curve"]
    alt = (
        f"A car on a road banked at {shown}, seen from behind: "
        + listed(forces)
        + "; its acceleration a points to the centre."
    )
    banked = spec.model_copy(
        update={
            "title": "Banked Curve",
            "title_key": "circular_motion",
            "vectors": vectors,
            "angles": angles,
            "alt": alt,
        }
    )
    shows = (
        f"a car on a road banked at {shown} seen from behind, with "
        + listed(forces)
        + " (any friction runs along the bank, up or down it depending on the speed)"
    )
    return banked, shows


def _vertical_circle(text: str) -> RigPicture | None:
    """A ball on a string at the top and the bottom of a vertical circle."""
    if _STRING.search(text) is None:
        # A cart in a loop of track: the track pushes, and this draws no track.
        return None
    top = _TOP.search(text) is not None
    bottom = _BOTTOM.search(text) is not None
    if not top and not bottom:
        top = bottom = True
    radius, size = 2.0, 0.3
    shape: Literal["circle", "box"] = "circle" if _ROUND.search(text) else "box"
    bodies: list[SimulationBody] = []
    vectors: list[SimulationVector] = []
    shown: list[str] = []
    if top:
        bodies.append(SimulationBody(path=[[0.0, radius]] * 2, radius=size, shape=shape))
        at = len(bodies) - 1
        vectors += [
            SimulationVector(anchor=[-0.12, 0.0], dx=0.0, dy=-1.0, label="T", body=at),
            SimulationVector(anchor=[0.12, 0.0], dx=0.0, dy=-1.0, label="mg", body=at),
        ]
        shown.append("at the top the tension T and its weight mg both point down, to the centre")
    if bottom:
        bodies.append(SimulationBody(path=[[0.0, -radius]] * 2, radius=size, shape=shape))
        at = len(bodies) - 1
        vectors += [
            SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=1.0, label="T", body=at),
            SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label="mg", body=at),
        ]
        shown.append("at the bottom the tension T points up, to the centre, and mg down")
    spec = SimulationBlockSpec(
        type="free_body",
        title="Vertical Circle",
        title_key="circular_motion",
        bodies=bodies,
        tethers=[SimulationTether(anchor=[0.0, 0.0], body=index) for index in range(len(bodies))],
        vectors=vectors,
        angles=[],
        x_min=-3.0,
        x_max=3.0,
        y_min=-3.0,
        y_max=3.0,
        alt="A ball on a string in a vertical circle: " + "; ".join(shown) + ".",
    )
    return spec, "a ball on a string in a vertical circle: " + "; ".join(shown)
