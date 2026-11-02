"""The `simulation` fence — a scene of moving bodies, not an x-y plot.

P3 animated the trajectory *graph*, which answers "what shape is the path" but
not "what is actually moving, and what is pulling on it". Seven of the eleven
verified physics kinds draw nothing at all, and for several the picture is the
explanation: an orbiting dot is the most natural animation in the subject, and
a number cannot show a momentum transfer.

`GraphBlockSpec` cannot express any of that. It is an x-y plot with axes, one
curve and a pair of axis labels; a scene needs bodies with sizes, a ground, and
force vectors that point somewhere in the world rather than along an axis.

What is deliberately *not* here: velocities, masses, forces as numbers, or
anything else the renderer would have to do physics with. Every body carries a
**sampled path** in world units, exactly as the trajectory graph carries sampled
points, and the index is the clock. The client walks the array. Nothing on the
device re-derives motion — the same rule that governs the math pipeline.
"""

from __future__ import annotations

import math
import typing
from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer, model_validator

from app.modules.physics.schemas.scene_titles import TitleKey

# Matches GraphBlockSpec.points: the solver never legitimately needs more
# samples than the canonical solve produced.
MAX_PATH_POINTS = 500


class SimulationBody(BaseModel):
    """One moving object, as a sampled path through the scene.

    ``radius`` is in world units so a 2 kg ball and a 1 kg ball can be drawn at
    honest relative sizes; the renderer scales it with the rest of the scene.
    """

    label: str | None = Field(default=None, max_length=32)
    radius: float = Field(default=0.4, gt=0)
    path: list[list[float]] = Field(min_length=2, max_length=MAX_PATH_POINTS)
    # Named roles rather than colours: the client owns the palette, and a
    # hex code from the server would not survive a theme change.
    role: Literal["primary", "secondary"] = "primary"
    # A block on a slope or a floor is a box, not a ball. A box is a square of
    # side 2 * radius, turned to lie on the slope when the scene has one.
    shape: Literal["circle", "box"] = "circle"

    @model_validator(mode="after")
    def finite_pairs(self) -> SimulationBody:
        for point in self.path:
            if len(point) != 2 or not all(math.isfinite(value) for value in point):
                raise ValueError("every path sample must be a finite [x, y] pair")
        return self

    @model_serializer(mode="wrap")
    def omit_default_shape(self, handler: Any) -> Any:
        return _omit(handler(self), shape="circle")


class SimulationVector(BaseModel):
    """An arrow whose direction the renderer cannot read off a path.

    Every other arrow in this spec is *derived* — velocity from the tangent,
    centripetal from the centre, normal and friction from the slope — precisely
    so it cannot disagree with the scene around it. These cannot be: the two
    loads on a see-saw, the 10 N pushing a block, the resultant of a 3 N and a
    4 N force. Their direction is the answer, so the solver states it, and the
    renderer draws exactly what it is given.

    The label carries the magnitude the solver already computed, so the picture
    and the pill cannot disagree either.
    """

    anchor: list[float]
    dx: float
    dy: float
    label: str | None = Field(default=None, max_length=24)
    # Visual weight only. `result` is the quantity the question asked for;
    # `measure` is an extent rather than a force — the h in mgh, the d in Fd —
    # drawn as a dimension line so it does not read as another arrow pushing;
    # `motion` is an acceleration, drawn so it never reads as a force.
    #
    # Length: a `measure`, and every arrow of a `vector_sum`, is drawn at its
    # world length. Any other arrow's (dx, dy) is a direction and a size
    # relative to the scene's other arrows of its kind: the renderer draws
    # the longest at a fixed screen length and the rest in proportion.
    role: Literal["force", "result", "measure", "motion"] = "force"
    # Rides on a moving body: `anchor` is then an offset from that body's
    # current position, so the tension on an Atwood mass goes where it goes.
    body: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def finite_and_directed(self) -> SimulationVector:
        _check_point(self.anchor, "anchor")
        if not math.isfinite(self.dx) or not math.isfinite(self.dy):
            raise ValueError("vector direction must be finite")
        if self.dx == 0 and self.dy == 0:
            raise ValueError("a vector needs a direction")
        return self

    @model_serializer(mode="wrap")
    def omit_unattached(self, handler: Any) -> Any:
        return _omit(handler(self), body=None)


def _check_point(point: list[float] | None, name: str) -> None:
    if point is not None and (len(point) != 2 or not all(math.isfinite(v) for v in point)):
        raise ValueError(f"{name} must be a finite [x, y] pair")


def _omit(data: Any, **defaults: Any) -> Any:
    """Drop keys still at their default, so a stored reply that never had them stays the same."""
    if isinstance(data, dict):
        for key, default in defaults.items():
            if key in data and data[key] == default:
                del data[key]
    return data


class SimulationTether(BaseModel):
    """A taut string or rope from a fixed point to a body: a pendulum, a ball on a string."""

    anchor: list[float]
    body: int = Field(ge=0)

    @model_validator(mode="after")
    def finite_anchor(self) -> SimulationTether:
        _check_point(self.anchor, "tether anchor")
        return self


class SimulationPulley(BaseModel):
    """A wheel the ropes of an Atwood machine run over."""

    centre: list[float]
    radius: float = Field(gt=0)

    @model_validator(mode="after")
    def finite_centre(self) -> SimulationPulley:
        _check_point(self.centre, "pulley centre")
        return self


class SimulationPlanet(BaseModel):
    """The body an orbit goes round, drawn at the scene's `centre` at true scale."""

    radius: float = Field(gt=0)
    label: str | None = Field(default=None, max_length=24)


class SimulationAngle(BaseModel):
    """An arc at a vertex: the θ of a slope or a launch, or a moment's turning sense.

    Degrees, counter-clockwise from +x. With ``arrow`` the arc is a curved
    arrow from ``start_deg`` to ``end_deg``: the torque about a pivot.
    """

    vertex: list[float]
    start_deg: float
    end_deg: float
    label: str | None = Field(default=None, max_length=24)
    arrow: bool = False
    role: Literal["given", "result"] = "given"

    @model_validator(mode="after")
    def finite_arc(self) -> SimulationAngle:
        _check_point(self.vertex, "angle vertex")
        if not (math.isfinite(self.start_deg) and math.isfinite(self.end_deg)):
            raise ValueError("angle ends must be finite")
        if self.start_deg == self.end_deg:
            raise ValueError("an angle needs a sweep")
        return self


class SimulationSolid(BaseModel):
    """A static rectangle: the table a ball rolls off, a cliff, a tank of water."""

    rect: list[float]
    kind: Literal["solid", "fluid"] = "solid"
    label: str | None = Field(default=None, max_length=24)

    @model_validator(mode="after")
    def ordered_rect(self) -> SimulationSolid:
        if len(self.rect) != 4 or not all(math.isfinite(v) for v in self.rect):
            raise ValueError("rect must be a finite [x_min, y_min, x_max, y_max]")
        if self.rect[2] <= self.rect[0] or self.rect[3] <= self.rect[1]:
            raise ValueError("rect needs ordered corners")
        return self


# --- circuits ------------------------------------------------------------------

CircuitPart = Literal["resistor", "bulb", "capacitor", "inductor", "ammeter", "voltmeter", "switch"]
MAX_CIRCUIT_PARTS = 10
MAX_CIRCUIT_DEPTH = 3


class CircuitNode(BaseModel):
    """One part, or parts in series, or parts in parallel.

    The client lays the network out; the server only says what is connected to
    what. ``label`` names a part ("R₁ = 4 Ω") or a group (its combined value);
    ``detail`` is what the solver found for it ("1.5 A", "6 V").
    """

    part: CircuitPart | None = None
    series: list[CircuitNode] | None = Field(default=None, min_length=2, max_length=6)
    parallel: list[CircuitNode] | None = Field(default=None, min_length=2, max_length=4)
    label: str | None = Field(default=None, max_length=24)
    detail: str | None = Field(default=None, max_length=24)
    role: Literal["given", "result"] = "given"

    @model_validator(mode="after")
    def one_kind(self) -> CircuitNode:
        kinds = [self.part is not None, self.series is not None, self.parallel is not None]
        if sum(kinds) != 1:
            raise ValueError("a circuit node is a part, a series group or a parallel group")
        return self

    @model_serializer(mode="wrap")
    def omit_empty(self, handler: Any) -> Any:
        return _omit(
            handler(self),
            part=None,
            series=None,
            parallel=None,
            label=None,
            detail=None,
            role="given",
        )

    def parts(self) -> int:
        children = self.series or self.parallel or []
        return 1 if self.part else sum(child.parts() for child in children)

    def depth(self) -> int:
        children = self.series or self.parallel or []
        return 0 if self.part else 1 + max(child.depth() for child in children)


class CircuitSource(BaseModel):
    kind: Literal["battery", "ac"] = "battery"
    label: str | None = Field(default=None, max_length=24)


class CircuitSpec(BaseModel):
    """A source driving one network: what a series/parallel question draws."""

    source: CircuitSource
    load: CircuitNode
    # The source current, drawn as an arrow on the wire beside the battery.
    current: str | None = Field(default=None, max_length=24)

    @model_validator(mode="after")
    def drawable(self) -> CircuitSpec:
        if self.load.parts() > MAX_CIRCUIT_PARTS:
            raise ValueError("too many parts to draw")
        if self.load.depth() > MAX_CIRCUIT_DEPTH:
            raise ValueError("groups nested too deep to draw")
        return self


# --- optics --------------------------------------------------------------------

OpticsElement = Literal[
    "converging_lens",
    "diverging_lens",
    "concave_mirror",
    "convex_mirror",
    "plane_mirror",
    "interface",
]


class OpticsArrow(BaseModel):
    """An object or an image, standing on the axis (a negative height is inverted)."""

    x: float
    height: float
    label: str | None = Field(default=None, max_length=24)
    virtual: bool = False

    @model_validator(mode="after")
    def finite(self) -> OpticsArrow:
        if not (math.isfinite(self.x) and math.isfinite(self.height)) or self.height == 0:
            raise ValueError("an optics arrow needs a finite place and a nonzero height")
        return self


class OpticsRay(BaseModel):
    """A ray as the polyline the solver traced; ``virtual`` is a dashed construction line."""

    points: list[list[float]] = Field(min_length=2, max_length=8)
    virtual: bool = False

    @model_validator(mode="after")
    def finite_points(self) -> OpticsRay:
        for point in self.points:
            _check_point(point, "ray point")
        return self


class OpticsSpec(BaseModel):
    """A ray diagram. The axis is y = 0 and the element stands at x = 0; light
    travels left to right. An ``interface`` is the line y = 0 instead, with its
    normal along x = 0 and ``media`` naming the side above, then below.
    """

    element: OpticsElement
    focal: float | None = Field(default=None, gt=0)
    object: OpticsArrow | None = None
    image: OpticsArrow | None = None
    rays: list[OpticsRay] = Field(default_factory=list, max_length=8)
    media: list[str] | None = Field(default=None, min_length=2, max_length=2)

    @model_validator(mode="after")
    def coherent(self) -> OpticsSpec:
        curved = self.element not in ("plane_mirror", "interface")
        if curved and self.focal is None:
            raise ValueError("a lens or curved mirror needs its focal length")
        if self.media is not None and any(len(name) > 16 for name in self.media):
            raise ValueError("a medium's name is at most 16 characters")
        if not self.rays and self.object is None:
            raise ValueError("a ray diagram needs an object or a ray")
        return self


# --- waves ---------------------------------------------------------------------

WaveEnd = Literal["none", "fixed", "open", "closed"]


_FREE_ENDS: list[WaveEnd] = ["none", "none"]


class WaveSpec(BaseModel):
    """A wave as frames of displacement over fixed x samples: the client steps
    through the frames, it never evaluates a wave function.
    """

    x: list[float] = Field(min_length=2, max_length=160)
    frames: list[list[float]] = Field(min_length=2, max_length=48)
    nodes: list[float] = Field(default_factory=list, max_length=12)
    antinodes: list[float] = Field(default_factory=list, max_length=12)
    # What holds each end: a clamped string ("fixed"), or a pipe "open" or
    # "closed" there. "none" is a travelling wave running off the edge.
    ends: list[WaveEnd] = Field(
        default_factory=lambda: _FREE_ENDS.copy(), min_length=2, max_length=2
    )

    @model_validator(mode="after")
    def sampled(self) -> WaveSpec:
        if any(not math.isfinite(v) for v in self.x) or any(
            b <= a for a, b in zip(self.x, self.x[1:], strict=False)
        ):
            raise ValueError("wave x samples must be finite and increasing")
        for frame in self.frames:
            if len(frame) != len(self.x) or not all(math.isfinite(v) for v in frame):
                raise ValueError("every frame is one finite value per x sample")
        return self


SimulationType = Literal[
    "projectile_motion",
    "orbit",
    "collision",
    "incline",
    # Static figures. Nothing moves in these, and that is the point: a
    # free-body diagram is what the question is asking to see.
    "lever",
    "free_body",
    "vector_sum",
    # A mass on a horizontal spring. The path is the displacement the graph
    # already sampled; the client draws the coil out to the current sample.
    "spring",
    # A bob on its string: the sampled arc, with a tether to the pivot.
    "pendulum",
    # Diagrams with no bodies: the client lays them out from `circuit`,
    # `optics` or `wave`.
    "circuit",
    "rays",
    "wave",
]

# The one place a scene's `type` values are written down. Both the fence layer
# and the direct-reply guard have to tell a scene from a graph, and a fourth
# copy of this set living in each of them is precisely the drift the fence
# registry's docblock warns about — `sources` and `copy` were known to one list
# and not another for exactly that reason.
SIMULATION_SPEC_TYPES: frozenset[str] = frozenset(typing.get_args(SimulationType))

_DEFAULT_TITLES: dict[str, str] = {
    "projectile_motion": "Projectile",
    "orbit": "Orbit",
    "collision": "Collision",
    "incline": "Inclined Plane",
    "lever": "Moments",
    "free_body": "Free-Body Diagram",
    "vector_sum": "Forces",
    "spring": "Spring",
    "pendulum": "Pendulum",
    "circuit": "Circuit",
    "rays": "Ray Diagram",
    "wave": "Wave",
}

ArrowKind = Literal["gravity", "velocity", "centripetal", "normal", "friction"]
_BODILESS = frozenset({"circuit", "rays", "wave"})


class SimulationBlockSpec(BaseModel):
    """A scene the client can play.

    ``arrows`` names the vectors worth drawing; the renderer derives each from
    the path rather than being handed components, so an arrow can never
    disagree with the motion it annotates. ``normal`` and ``friction`` are the
    exception and the reason ``incline_deg`` exists: a block that has not
    started moving has no tangent to read them off, and a free-body diagram of
    a stationary block is most of what an incline question wants.
    """

    type: SimulationType
    title: str | None = Field(default=None, max_length=64)
    # Empty on a static figure: a see-saw's picture is its beam and its two
    # load arrows, with nothing to walk a clock through.
    bodies: list[SimulationBody] = Field(default_factory=list, max_length=4)
    # World bounds. Named x_/y_ like GraphBlockSpec so the two read alike, but
    # these are a *scene* box: both axes are space, always.
    x_min: float = 0.0
    x_max: float = 10.0
    y_min: float = 0.0
    y_max: float = 10.0
    # gravity     — straight down from the body, constant (this is the weight)
    # velocity    — tangent to the body's own path at the current frame
    # centripetal — from the body toward `centre`
    # normal      — perpendicular to the slope, away from its surface
    # friction    — up the slope, opposing the slide
    arrows: list[ArrowKind] = Field(default_factory=list, max_length=5)
    # The point an orbit turns about; required by a centripetal arrow, since
    # "toward the centre" is meaningless without one.
    centre: list[float] | None = None
    # Draw a ground line at y = 0. A projectile landing on nothing reads as a
    # dot drifting in a box.
    ground: bool = False
    # The slope, in degrees, descending left to right. Draws the surface the
    # block sits on and fixes the normal and friction directions.
    incline_deg: float | None = Field(default=None, gt=-90.0, lt=90.0)
    # Arrows the renderer cannot derive — see SimulationVector.
    vectors: list[SimulationVector] = Field(default_factory=list, max_length=6)
    # A rigid beam, as its two ends: [x1, y1, x2, y2]. The lever it turns about
    # is `pivot`, drawn as a wedge beneath it.
    beam: list[float] | None = None
    pivot: list[float] | None = None
    # The fixed end of a spring, in world units. The coil is drawn from here
    # to the mass, so the renderer never chooses a wall of its own.
    anchor: list[float] | None = None
    # --- added in v2; each is left out of the fence when unused ---
    # Strings and ropes, each from a fixed point to a body.
    tethers: list[SimulationTether] = Field(default_factory=list, max_length=4)
    pulley: SimulationPulley | None = None
    # The planet an orbit goes round, drawn at `centre`.
    central_body: SimulationPlanet | None = None
    angles: list[SimulationAngle] = Field(default_factory=list, max_length=4)
    solids: list[SimulationSolid] = Field(default_factory=list, max_length=4)
    # A short label at the tip of a derived arrow: {"velocity": "v", "gravity": "mg"}.
    arrow_labels: dict[ArrowKind, str] = Field(default_factory=dict)
    # Faint copies of each body at this many evenly spaced samples, so a still
    # frame shows the motion too: the widening gaps of a fall.
    strobe: int | None = Field(default=None, ge=2, le=12)
    # One sentence a screen reader says for the picture.
    alt: str | None = Field(default=None, max_length=300)
    title_key: TitleKey | None = None
    circuit: CircuitSpec | None = None
    optics: OpticsSpec | None = None
    wave: WaveSpec | None = None

    @model_validator(mode="after")
    def coherent_scene(self) -> SimulationBlockSpec:
        # A scene with neither is an empty box. One or the other is what makes
        # it a picture; a circuit, a ray diagram and a wave carry their own.
        if self.type not in _BODILESS and not self.bodies and not self.vectors:
            raise ValueError("a simulation needs at least one body or vector")
        if self.type in _BODILESS and (self.bodies or self.tethers):
            # The phone lays a diagram out from its own spec and draws no
            # bodies on it; one sent anyway would vanish without a word.
            raise ValueError(f"a {self.type} diagram has no moving bodies")
        if self.type in _BODILESS and any(v.role != "measure" for v in self.vectors):
            # Only a measure line has meaning on a diagram the phone lays out.
            raise ValueError(f"a {self.type} diagram draws only measure lines")
        for kind, field_name in (("circuit", "circuit"), ("rays", "optics"), ("wave", "wave")):
            if (self.type == kind) != (getattr(self, field_name) is not None):
                raise ValueError(f"a {kind} scene, and only one, carries `{field_name}`")
        if self.type == "pendulum" and (len(self.bodies) != 1 or not self.tethers):
            raise ValueError("a pendulum scene needs one bob and its string")
        attached = [t.body for t in self.tethers] + [
            v.body for v in self.vectors if v.body is not None
        ]
        if any(index >= len(self.bodies) for index in attached):
            raise ValueError("a tether or vector names a body the scene does not have")
        if self.central_body is not None and self.centre is None:
            raise ValueError("a central body sits at the scene's centre, so it needs one")
        if set(self.arrow_labels) - set(self.arrows):
            raise ValueError("an arrow label names an arrow the scene does not draw")
        if any(len(label) > 24 for label in self.arrow_labels.values()):
            raise ValueError("an arrow label is at most 24 characters")
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("simulation requires ordered bounds")
        if not all(math.isfinite(v) for v in (self.x_min, self.x_max, self.y_min, self.y_max)):
            raise ValueError("simulation requires finite bounds")
        if "centripetal" in self.arrows and self.centre is None:
            raise ValueError("a centripetal arrow requires a centre")
        if self.centre is not None:
            if len(self.centre) != 2 or not all(math.isfinite(v) for v in self.centre):
                raise ValueError("centre must be a finite [x, y] pair")
        # Both are read off the slope, not off the motion, so neither can be
        # drawn without one — and a normal force pointing the wrong way is a
        # more confident lie than no arrow at all.
        if {"normal", "friction"} & set(self.arrows) and self.incline_deg is None:
            raise ValueError("normal and friction arrows require incline_deg")
        if self.incline_deg is not None and not math.isfinite(self.incline_deg):
            raise ValueError("incline_deg must be finite")
        if self.beam is not None and (
            len(self.beam) != 4 or not all(math.isfinite(v) for v in self.beam)
        ):
            raise ValueError("beam must be a finite [x1, y1, x2, y2]")
        if self.pivot is not None and (
            len(self.pivot) != 2 or not all(math.isfinite(v) for v in self.pivot)
        ):
            raise ValueError("pivot must be a finite [x, y] pair")
        # A pivot with no beam is a dot in space, and a beam is the thing that
        # makes a lever readable as a lever.
        if self.pivot is not None and self.beam is None:
            raise ValueError("a pivot requires a beam")
        if self.anchor is not None and (
            len(self.anchor) != 2 or not all(math.isfinite(v) for v in self.anchor)
        ):
            raise ValueError("anchor must be a finite [x, y] pair")
        # Without a stated wall the coil would start at whatever edge the
        # canvas happened to have, and that edge is not the spring.
        if self.type == "spring" and (self.anchor is None or len(self.bodies) != 1):
            raise ValueError("a spring scene needs one mass and an anchor")
        # Every body is walked by one shared clock, so paths of different
        # lengths would drift apart on screen — a two-body scene would show a
        # collision at the wrong moment.
        lengths = {len(body.path) for body in self.bodies}
        if len(lengths) > 1:
            raise ValueError("every body must have the same number of samples")
        if not self.title:
            self.title = _DEFAULT_TITLES[self.type]
        return self

    @model_serializer(mode="wrap")
    def omit_empty_anchor(self, handler: Any) -> Any:
        # Other scenes have no wall. Writing `"anchor": null` into their fence
        # would change a stored reply that never had the key; the v2 fields
        # are left out the same way.
        return _omit(
            handler(self),
            anchor=None,
            tethers=[],
            pulley=None,
            central_body=None,
            angles=[],
            solids=[],
            arrow_labels={},
            strobe=None,
            alt=None,
            title_key=None,
            circuit=None,
            optics=None,
            wave=None,
        )
