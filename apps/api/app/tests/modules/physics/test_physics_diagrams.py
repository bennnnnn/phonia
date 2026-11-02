"""Scene v2: the pictures a solved question carries, and the diagrams the phone lays out.

Every picture here comes from a real question through the real extractor and
solver, so a test fails when a question stops drawing, draws the wrong
apparatus (a concave mirror as a lens, a roller coaster as a straight drop),
or labels a number the answer does not carry.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.modules.physics import extract_physics_intent
from app.modules.physics.schemas import (
    CircuitNode,
    CircuitSource,
    CircuitSpec,
    OpticsArrow,
    OpticsRay,
    OpticsSpec,
    PhysicsIntent,
    SimulationBlockSpec,
    SimulationVector,
    WaveSpec,
)
from app.modules.physics.solver import solve_physics
from app.modules.physics.solvers.wave_scenes import standing_scene, travelling_scene


def _scenes(text: str) -> list[SimulationBlockSpec]:
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent), text
    return solve_physics(intent).simulation_specs


def _scene(text: str) -> SimulationBlockSpec:
    specs = _scenes(text)
    assert len(specs) == 1, text
    return specs[0]


@pytest.mark.parametrize(
    ("text", "kind", "title_key", "alt"),
    [
        # Circuits
        (
            "Resistors of 4 Ω, 6 Ω and 12 Ω are connected in parallel. "
            "What is the equivalent resistance?",
            "circuit",
            "circuit",
            "in parallel: 2 Ω in total",
        ),
        ("A 60 W bulb runs on 240 V. What current does it draw?", "circuit", "circuit", "0.25 A"),
        # Optics
        (
            "A converging lens has a focal length of 8 cm. An object is 12 cm away. "
            "Where is the image?",
            "rays",
            "lens",
            "24 cm behind it",
        ),
        (
            "An object is placed 20 cm in front of a concave mirror with focal length 15 cm. "
            "Where is the image?",
            "rays",
            "mirror",
            "60 cm in front of it",
        ),
        (
            "A light ray passes from air into glass (n = 1.5) at an angle of incidence of "
            "30 degrees. What is the angle of refraction?",
            "rays",
            "refraction",
            "bends to 19.5°",
        ),
        (
            "What is the critical angle for glass of refractive index 1.5?",
            "rays",
            "refraction",
            "41.8°",
        ),
        (
            "A ray hits a plane mirror at 35 degrees to the normal. What is the angle of reflection?",
            "rays",
            "mirror",
            "35° from the normal",
        ),
        # Waves
        (
            "A wave has a frequency of 50 Hz and a wavelength of 4 m. What is its speed?",
            "wave",
            "wave",
            "travelling at 200 m/s",
        ),
        (
            "A water wave travels 12 m in 4 s and its wavelength is 1.5 m. What is the frequency?",
            "wave",
            "wave",
            "frequency 2 Hz",
        ),
        (
            "What is the wavelength of a microwave with frequency 2.45 GHz?",
            "wave",
            "wave",
            "0.122 m",
        ),
        (
            "A guitar string 0.65 m long has a wave speed of 260 m/s. "
            "What is its fundamental frequency?",
            "wave",
            "standing_wave",
            "0.65 m string",
        ),
        # Forces and motion solved as catalog arithmetic
        (
            "A 10 kg box is pulled with 50 N to the right and 20 N to the left. "
            "What is its acceleration?",
            "free_body",
            "free_body",
            "a net 30 N",
        ),
        (
            "A 0.5 kg ball on a string is swung in a circle of radius 1.2 m at 6 m/s. "
            "What is the tension in the string?",
            "orbit",
            "circular_motion",
            "inward with 15 N",
        ),
        (
            "How long does it take the ISS to orbit Earth at an altitude of 400 km?",
            "orbit",
            "satellite",
            "every 92.4 minutes",
        ),
        ("How long must a pendulum be to have a period of 2 s?", "pendulum", "pendulum", "0.994 m"),
        (
            "A 4 kg rifle fires a 0.01 kg bullet at 400 m/s. What is the recoil speed of the rifle?",
            "collision",
            "recoil",
            "recoils at 1 m/s",
        ),
        (
            "what is the component of gravity along a 40 degree slope for a 3 kg mass",
            "incline",
            "incline",
            "down the slope with 18.9 N",
        ),
        (
            "A 2 kg cart moving at 3 m/s compresses a spring of constant 200 N/m. "
            "What is the maximum compression?",
            "spring",
            "spring",
            "squeezes the spring 0.3 m",
        ),
        (
            "A stone is dropped from rest. How far does it fall in 2 seconds?",
            "projectile_motion",
            "free_fall",
            "dropped from 19.6 m",
        ),
        ("Find the force between two 1 µC charges 5 cm apart.", "free_body", "charges", "3.6 N"),
    ],
)
def test_a_question_carries_the_picture_of_its_apparatus(
    text: str, kind: str, title_key: str, alt: str
) -> None:
    scene = _scene(text)
    assert scene.type == kind
    assert scene.title_key == title_key
    assert scene.alt is not None and alt in scene.alt, scene.alt


@pytest.mark.parametrize(
    "text",
    [
        # The speed at the bottom is path-free; the picture is not.
        "A roller coaster starts from rest at the top of a 45 m hill. What is its speed at the bottom?",
        "A pendulum bob is released from 0.2 m above its lowest point. "
        "How fast is it moving at the bottom?",
        "A skateboarder starts from rest at the top of a 3 m ramp. How fast is she going at the bottom?",
    ],
)
def test_a_drop_down_a_track_is_not_drawn_as_a_straight_fall(text: str) -> None:
    assert _scenes(text) == []


def test_a_dropped_body_is_drawn_falling() -> None:
    scene = _scene("A diver steps off a 10 m platform. With what speed does she hit the water?")
    assert scene.title_key == "free_fall"
    assert scene.bodies[0].path[0][1] > scene.bodies[0].path[-1][1]


def test_a_landing_solved_to_the_ground_is_described_as_landing() -> None:
    scene = _scenes(
        "A coin is dropped from a 125 m tall building. How fast is it moving when it hits the ground?"
    )[0]
    assert scene.alt == "A ball dropped from 125 m reaches the ground after 5.05 s."


def test_a_lens_ray_diagram_meets_at_the_image_it_labels() -> None:
    optics = _scene(
        "An object is 30 cm from a converging lens of focal length 10 cm. Where is the image?"
    ).optics
    assert optics is not None and optics.image is not None and optics.object is not None
    assert optics.element == "converging_lens"
    assert optics.image.label == "v = 15 cm"
    image = [optics.image.x, optics.image.height]
    for ray in optics.rays:
        assert ray.points[0] == [optics.object.x, optics.object.height]
        assert ray.points[-1] == pytest.approx(image)
    # Real and inverted: behind the lens, below the axis.
    assert optics.image.x > 0 and optics.image.height < 0


def test_a_concave_mirror_reflects_back_to_an_image_in_front_of_it() -> None:
    optics = _scene(
        "An object is placed 20 cm in front of a concave mirror with focal length 15 cm. "
        "Where is the image?"
    ).optics
    assert optics is not None and optics.image is not None
    assert optics.element == "concave_mirror"
    assert optics.image.x == pytest.approx(-60.0)
    for ray in optics.rays:
        # Every ray turns back at the mirror rather than passing through it.
        assert all(x <= 0 for x, _ in ray.points)
        assert ray.points[-1] == pytest.approx([optics.image.x, optics.image.height])


def test_a_reflection_draws_two_equal_angles_from_the_normal() -> None:
    scene = _scene(
        "A ray hits a plane mirror at 35 degrees to the normal. What is the angle of reflection?"
    )
    assert scene.optics is not None and scene.optics.element == "plane_mirror"
    incident, reflected = scene.angles
    assert incident.label == reflected.label == "35°"
    assert reflected.role == "result"
    assert abs(incident.end_deg - incident.start_deg) == pytest.approx(35)
    assert abs(reflected.end_deg - reflected.start_deg) == pytest.approx(35)


def test_a_refraction_bends_toward_the_normal_entering_glass() -> None:
    scene = _scene(
        "A light ray passes from air into glass (n = 1.5) at an angle of incidence of 30 degrees. "
        "What is the angle of refraction?"
    )
    assert scene.optics is not None and scene.optics.media == ["air", "n = 1.5"]
    incident, refracted = scene.angles
    assert incident.label == "30°" and refracted.label == "19.5°"
    assert refracted.role == "result"


def test_a_circuit_carries_the_values_the_question_gave() -> None:
    circuit = _scene(
        "A 12 V battery is connected to a 4 Ω and an 8 Ω resistor in series. What is the current?"
    ).circuit
    assert circuit is not None
    assert circuit.source.label == "12 V"
    assert circuit.current is not None and circuit.current.startswith("I = 1 A")


def test_a_parallel_network_names_each_resistor_and_the_total() -> None:
    circuit = _scene(
        "Resistors of 4 Ω, 6 Ω and 12 Ω are connected in parallel. What is the equivalent resistance?"
    ).circuit
    assert circuit is not None and circuit.load.parallel is not None
    assert [part.label for part in circuit.load.parallel] == ["R₁ = 4 Ω", "R₂ = 6 Ω", "R₃ = 12 Ω"]
    assert circuit.load.label == "R = 2 Ω" and circuit.load.role == "result"


@pytest.mark.parametrize(
    ("text", "group", "parts", "total", "current"),
    [
        (
            "Draw a circuit with a 9V battery and two 3 ohm resistors in parallel "
            "and find the total current",
            "parallel",
            ["R₁ = 3 Ω", "R₂ = 3 Ω"],
            "R = 1.5 Ω",
            "I = 6 A",
        ),
        (
            "A 12 V battery is connected to three 6 ohm resistors in parallel. "
            "Find the total current.",
            "parallel",
            ["R₁ = 6 Ω", "R₂ = 6 Ω", "R₃ = 6 Ω"],
            "R = 2 Ω",
            "I = 6 A",
        ),
        (
            "A 12 V battery is connected to a 4 Ω and an 8 Ω resistor in series. "
            "What is the current?",
            "series",
            ["R₁ = 4 Ω", "R₂ = 8 Ω"],
            "R = 12 Ω",
            "I = 1 A",
        ),
    ],
)
def test_a_network_asked_for_its_current_keeps_every_resistor(
    text: str, group: str, parts: list[str], total: str, current: str
) -> None:
    """Two 3 Ω in parallel were drawn as one 1.5 Ω resistor; the total is the group's label."""
    circuit = _scene(text).circuit
    assert circuit is not None
    members = getattr(circuit.load, group)
    assert members is not None and [part.label for part in members] == parts
    assert circuit.load.label == total and circuit.load.role == "given"
    assert circuit.current == current


def test_opposing_forces_are_drawn_to_scale_with_what_is_left_over() -> None:
    scene = _scene(
        "A 10 kg box is pulled with 50 N to the right and 20 N to the left. What is its acceleration?"
    )
    forward, back, motion = scene.vectors
    assert (forward.dx, back.dx) == (50.0, -20.0)
    assert motion.role == "motion" and motion.label == "a = 3 m/s²"
    assert motion.dx > 0


def test_a_recoil_sends_the_two_bodies_opposite_ways_from_rest() -> None:
    scene = _scene(
        "A 4 kg rifle fires a 0.01 kg bullet at 400 m/s. What is the recoil speed of the rifle?"
    )
    rifle, bullet = scene.bodies
    # A short pause at rest, then most of the clock on the separation.
    assert rifle.path[0] == rifle.path[6] and bullet.path[0] == bullet.path[6]
    assert len(rifle.path) > 40
    assert rifle.path[-1][0] < rifle.path[0][0]
    assert bullet.path[-1][0] > bullet.path[0][0]


@pytest.mark.parametrize(
    ("text", "ends", "nodes", "antinodes"),
    [
        (
            "A string 1.2 m long has a wave speed of 240 m/s. "
            "What is the frequency of the third harmonic?",
            ["fixed", "fixed"],
            [0.0, 0.4, 0.8, 1.2],
            [0.2, 0.6, 1.0],
        ),
        (
            "An organ pipe open at both ends is 0.85 m long. The speed of sound is 340 m/s. "
            "What is the frequency of its third harmonic?",
            ["open", "open"],
            [0.85 / 6, 0.425, 0.85 * 5 / 6],
            [0.0, 0.85 / 3, 0.85 * 2 / 3, 0.85],
        ),
        (
            "A pipe closed at one end is 0.5 m long. Sound travels at 340 m/s. "
            "Find the fundamental frequency.",
            ["closed", "open"],
            [0.0],
            [0.5],
        ),
    ],
)
def test_a_standing_wave_puts_its_nodes_where_its_ends_require(
    text: str, ends: list[str], nodes: list[float], antinodes: list[float]
) -> None:
    wave = _scene(text).wave
    assert wave is not None
    assert wave.ends == ends
    assert wave.nodes == pytest.approx(nodes)
    assert wave.antinodes == pytest.approx(antinodes)
    # A node never moves: every frame is (close to) zero there.
    for node in wave.nodes:
        index = min(range(len(wave.x)), key=lambda i: abs(wave.x[i] - node))
        if abs(wave.x[index] - node) < 1e-6:
            assert all(abs(frame[index]) < 1e-3 for frame in wave.frames)


def test_a_travelling_wave_marks_one_wavelength_crest_to_crest() -> None:
    scene = travelling_scene(200.0, 50.0, 4.0)
    wave = scene.wave
    assert wave is not None
    measure = scene.vectors[0]
    assert measure.role == "measure" and measure.dx == 4.0 and measure.label == "λ = 4 m"
    # The first frame has a crest at λ/4, where the measure starts.
    first = wave.frames[0]
    crest = wave.x[first.index(max(first))]
    assert crest == pytest.approx(measure.anchor[0], abs=4.0 / 24)
    # It moves: the next frame is the same wave shifted right.
    assert wave.frames[1] != wave.frames[0]


def test_a_wave_is_small_enough_to_store_in_a_reply() -> None:
    for scene in (travelling_scene(3e8, 6e14, 5e-7), standing_scene(1.2, 3, 2.0, pipe=False)):
        assert scene is not None
        assert len(scene.model_dump_json()) < 16_000


def test_a_standing_wave_past_ten_loops_is_not_drawn() -> None:
    assert standing_scene(1.0, 11, 2.0, pipe=False) is None
    # A closed pipe has no even harmonics to draw.
    assert standing_scene(1.0, 2, 4.0, pipe=True) is None


# --- the schema the phone trusts ----------------------------------------------


def _circuit(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "circuit",
        "title": "Circuit",
        "circuit": {"source": {}, "load": {"part": "resistor"}},
    }
    return {**base, **overrides}


def test_a_diagram_with_its_spec_needs_no_bodies() -> None:
    spec = SimulationBlockSpec.model_validate(_circuit())
    assert spec.bodies == [] and spec.circuit is not None


@pytest.mark.parametrize(
    "bad",
    [
        # A circuit scene with no circuit, or a wave field on it.
        {"circuit": None},
        {"wave": {"x": [0, 1], "frames": [[0, 0], [0, 0]]}},
        # Bodies on a diagram.
        {"bodies": [{"path": [[0, 0], [0, 0]], "radius": 0.1}]},
    ],
)
def test_a_diagram_carries_only_its_own_spec(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SimulationBlockSpec.model_validate(_circuit(**bad))


def test_a_circuit_too_big_to_draw_is_refused() -> None:
    with pytest.raises(ValidationError):
        CircuitSpec(
            source=CircuitSource(),
            load=CircuitNode(
                series=[
                    CircuitNode(parallel=[CircuitNode(part="resistor")] * 4),
                    CircuitNode(parallel=[CircuitNode(part="resistor")] * 4),
                    CircuitNode(parallel=[CircuitNode(part="resistor")] * 4),
                ]
            ),
        )


def test_a_curved_element_needs_its_focal_length() -> None:
    with pytest.raises(ValidationError):
        OpticsSpec(element="converging_lens", object=OpticsArrow(x=-2.0, height=1.0))
    plane = OpticsSpec(element="plane_mirror", rays=[OpticsRay(points=[[-1, 1], [0, 0]])])
    assert plane.focal is None


def test_a_wave_frame_is_one_value_per_sample() -> None:
    with pytest.raises(ValidationError):
        WaveSpec(x=[0.0, 1.0, 2.0], frames=[[0.0, 1.0], [0.0, 1.0, 0.0]])
    with pytest.raises(ValidationError):
        WaveSpec(x=[0.0, 2.0, 1.0], frames=[[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]])


def test_an_unused_v2_field_stays_out_of_the_stored_reply() -> None:
    """A v1 scene serialises exactly as before: no empty v2 lists in old replies."""
    spec = SimulationBlockSpec(
        type="free_body",
        vectors=[SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label="W")],
        x_min=-1,
        x_max=1,
        y_min=-1,
        y_max=1,
    )
    dumped = spec.model_dump()
    for field in ("tethers", "pulley", "angles", "solids", "circuit", "optics", "wave", "strobe"):
        assert field not in dumped
    assert "body" not in dumped["vectors"][0]
    assert math.isfinite(dumped["x_min"])


def test_a_diagram_draws_only_measure_lines() -> None:
    arrow = {"anchor": [0, 0], "dx": 1, "dy": 0, "label": "v", "role": "motion"}
    with pytest.raises(ValidationError):
        SimulationBlockSpec.model_validate(_circuit(vectors=[arrow]))
    measure = {**arrow, "role": "measure", "label": "L = 1 m"}
    assert SimulationBlockSpec.model_validate(_circuit(vectors=[measure])).vectors
