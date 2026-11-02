"""Wave pictures: a travelling wave with its wavelength, and a standing wave's loops.

Every frame is the solved wave sampled here; the phone steps through the
frames and never evaluates a wave function. The amplitude is a display choice
(these questions give none), so no picture labels one.
"""

from __future__ import annotations

import math

from app.modules.physics.display import GIVEN_FIGURES, plain_number
from app.modules.physics.schemas import SimulationBlockSpec, SimulationVector, WaveSpec
from app.modules.physics.schemas.simulation import WaveEnd

# Enough samples for a smooth curve and frames for a smooth step, and no more:
# every value is in the stored reply.
_SAMPLES = 73
_FRAMES = 16
# Past ten loops the nodes crowd into a comb and the picture says nothing.
_MOST_LOOPS = 10
_ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth")


def _ordinal(n: int) -> str:
    return _ORDINALS[n - 1] if n <= len(_ORDINALS) else f"{n}th"


def travelling_scene(speed: float, frequency: float, wavelength: float) -> SimulationBlockSpec:
    """Three wavelengths of a wave moving right, crest to crest marked λ."""
    amplitude = 0.25 * wavelength
    span = 3 * wavelength
    xs = _rounded([span * i / (_SAMPLES - 1) for i in range(_SAMPLES)], span)
    frames = [
        _rounded(
            [amplitude * math.sin(2 * math.pi * (x / wavelength - j / _FRAMES)) for x in xs],
            amplitude,
        )
        for j in range(_FRAMES)
    ]
    shown_lambda = f"{plain_number(wavelength)} m"
    return SimulationBlockSpec(
        type="wave",
        title="Wave",
        title_key="wave",
        wave=WaveSpec(x=xs, frames=frames),
        vectors=[
            # The first crest sits at λ/4 in the first frame. The speed is not
            # an arrow: the wave visibly moves right, and the phone draws only
            # measure lines on a diagram.
            SimulationVector(
                anchor=[wavelength / 4, 1.45 * amplitude],
                dx=wavelength,
                dy=0.0,
                label=f"λ = {shown_lambda}",
                role="measure",
            ),
        ],
        x_min=0.0,
        x_max=span,
        y_min=-1.9 * amplitude,
        y_max=1.9 * amplitude,
        alt=(
            f"A wave of wavelength {shown_lambda} and frequency {plain_number(frequency)} Hz "
            f"travelling at {plain_number(speed)} m/s."
        ),
    )


def standing_scene(
    length: float, harmonic: int, mode_factor: float, *, pipe: bool
) -> SimulationBlockSpec | None:
    """The nth harmonic between two ends: its loops, nodes and antinodes.

    A string's clamped ends and a closed pipe end are displacement nodes; an
    open pipe end is an antinode. ``mode_factor`` 4 is a quarter-wave
    resonator, closed (or clamped) on the left and open (or free) on the right.
    """
    if length <= 0 or harmonic < 1 or harmonic > _MOST_LOOPS:
        return None
    quarter = mode_factor == 4.0
    if quarter and harmonic % 2 == 0:
        return None
    wavelength = mode_factor * length / harmonic
    k = 2 * math.pi / wavelength
    amplitude = 0.09 * length
    xs = _rounded([length * i / (_SAMPLES - 1) for i in range(_SAMPLES)], length)
    open_ends = pipe and not quarter

    def shape(x: float) -> float:
        return math.cos(k * x) if open_ends else math.sin(k * x)

    frames = [
        _rounded(
            [amplitude * shape(x) * math.cos(2 * math.pi * j / _FRAMES) for x in xs], amplitude
        )
        for j in range(_FRAMES)
    ]
    half = wavelength / 2
    first_node = half / 2 if open_ends else 0.0
    first_antinode = 0.0 if open_ends else half / 2
    nodes = _every(first_node, half, length)
    antinodes = _every(first_antinode, half, length)
    ends: list[WaveEnd]
    if pipe:
        ends = ["closed", "open"] if quarter else ["open", "open"]
    else:
        ends = ["fixed", "none"] if quarter else ["fixed", "fixed"]
    shown_length = f"{plain_number(length, GIVEN_FIGURES)} m"
    shown_lambda = f"{plain_number(wavelength)} m"
    # Clear of a pipe's walls and the A and N letters beside them.
    vectors = [
        SimulationVector(
            anchor=[0.0, -2.5 * amplitude],
            dx=length,
            dy=0.0,
            label=f"L = {shown_length}",
            role="measure",
        )
    ]
    if wavelength <= length * 1.0001:
        vectors.append(
            SimulationVector(
                anchor=[0.0, 2.5 * amplitude],
                dx=wavelength,
                dy=0.0,
                label=f"λ = {shown_lambda}",
                role="measure",
            )
        )
    if pipe:
        holder = (
            f"a {shown_length} pipe closed at one end"
            if quarter
            else f"a {shown_length} pipe open at both ends"
        )
    else:
        holder = f"a {shown_length} string" + (" free at one end" if quarter else "")
    counted = f"{_count(len(nodes), 'node')} and {_count(len(antinodes), 'antinode')}"
    return SimulationBlockSpec(
        type="wave",
        title="Standing Wave",
        title_key="standing_wave",
        wave=WaveSpec(x=xs, frames=frames, nodes=nodes, antinodes=antinodes, ends=ends),
        vectors=vectors,
        x_min=-0.06 * length,
        x_max=1.06 * length,
        y_min=-3.2 * amplitude,
        y_max=3.2 * amplitude,
        alt=(
            f"The {_ordinal(harmonic)} harmonic on {holder}: {counted}, wavelength {shown_lambda}."
        ),
    )


def _rounded(values: list[float], scale: float) -> list[float]:
    """Four figures of the drawing's own scale: the screen shows no more."""
    digits = 4 - math.floor(math.log10(scale))
    return [round(value, digits) + 0.0 for value in values]


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _every(start: float, step: float, end: float) -> list[float]:
    """start, start + step, … up to end, with the last one snapped onto it."""
    out: list[float] = []
    x = start
    while x <= end * (1 + 1e-9):
        out.append(round(min(x, end), 9))
        x += step
    return out


def wave_scene(op: str, p: dict[str, float], value: float) -> list[SimulationBlockSpec]:
    """The picture for a solved wave question, or none when it has no shape."""
    if op == "resonance_frequency":
        harmonic = p.get("harmonic", 0.0)
        if not harmonic.is_integer():
            return []
        scene = standing_scene(p["L"], int(harmonic), p["mode_factor"], pipe=p.get("pipe", 0.0) > 0)
        return [scene] if scene else []
    if op == "wave_speed":
        speed, frequency, wavelength = value, p["freq"], p["wavelength"]
    elif op == "wavelength":
        speed, frequency, wavelength = p["v_wave"], p["freq"], value
    elif op == "wave_frequency":
        speed, frequency, wavelength = p["v_wave"], value, p["wavelength"]
    else:
        return []
    if min(speed, frequency, wavelength) <= 0:
        return []
    return [travelling_scene(speed, frequency, wavelength)]
