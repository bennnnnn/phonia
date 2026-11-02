"""The ordered physics extractor chain and the cues that say a verified template could match.

The order is load-bearing: each comment says which reader must run before
which, and why.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.physics.extractors.circuit_patterns import _CIRCUIT_CUE_RES, _CIRCUIT_CUES
from app.modules.physics.extractors.circuits import _extract_circuit_intent
from app.modules.physics.extractors.circular import (
    _CIRCULAR_CUE_RES,
    _CIRCULAR_CUES,
    _extract_circular_intent,
)
from app.modules.physics.extractors.cues import (
    _has_cue_either_case,
)
from app.modules.physics.extractors.drag import _DRAG_CUES, extract_drag_intent
from app.modules.physics.extractors.electrostatics import (
    _ELECTROSTATICS_CUE_RES,
    _ELECTROSTATICS_CUES,
    _extract_electrostatics_intent,
)
from app.modules.physics.extractors.energy import (
    _ENERGY_CUE_RES,
    _ENERGY_CUES,
    _extract_energy_intent,
)
from app.modules.physics.extractors.fluids import (
    _FLUIDS_CUE_RES,
    _FLUIDS_CUES,
    _extract_fluids_intent,
)
from app.modules.physics.extractors.forces import _FORCE_CUE_RES, _FORCE_CUES, _extract_force_intent
from app.modules.physics.extractors.friction import (
    _FRICTION_CUE_RES,
    _FRICTION_CUES,
    _extract_friction_intent,
)
from app.modules.physics.extractors.gravitation import (
    _GRAVITATION_CUE_RES,
    _GRAVITATION_CUES,
    _extract_gravitation_intent,
)
from app.modules.physics.extractors.kinematics import (
    _KINEMATICS_CUE_RES,
    _KINEMATICS_CUES,
    _extract_kinematics_intent,
)
from app.modules.physics.extractors.magnetism import (
    _MAGNETISM_CUE_RES,
    _MAGNETISM_CUES,
    _extract_magnetism_intent,
)
from app.modules.physics.extractors.materials import (
    _MATERIALS_CUE_RES,
    _MATERIALS_CUES,
    _extract_materials_intent,
)
from app.modules.physics.extractors.modern import (
    _MODERN_CUE_RES,
    _MODERN_CUES,
    _extract_modern_intent,
)
from app.modules.physics.extractors.momentum import (
    _MOMENTUM_CUE_RES,
    _MOMENTUM_CUES,
    _extract_momentum_intent,
)
from app.modules.physics.extractors.optics import _OPTICS_CUES, _extract_optics_intent
from app.modules.physics.extractors.oscillations import (
    _PENDULUM_CUE_RES,
    _SHM_CUE_RES,
    _SPRING_CUE_RES,
    _SPRING_CUES,
    _extract_pendulum_intent,
    _extract_shm_intent,
    _extract_spring_intent,
)
from app.modules.physics.extractors.projectile import (
    _PROJECTILE_CUE_RES,
    _PROJECTILE_CUES,
    _extract_projectile_intent,
)
from app.modules.physics.extractors.rates import _RATE_CUES, extract_rate_intent
from app.modules.physics.extractors.relative_motion import (
    extract_chase_intent,
    extract_legs_intent,
)
from app.modules.physics.extractors.rotation import (
    _ROTATION_CUE_RES,
    _ROTATION_CUES,
    _extract_rotation_intent,
)
from app.modules.physics.extractors.school_extensions import (
    _EXTENSION_CUE_RES,
    _EXTENSION_CUES,
    extract_school_extension,
)
from app.modules.physics.extractors.stopping import _STOPPING_CUE_RES, extract_stopping_distance
from app.modules.physics.extractors.suvat import _SUVAT_CUE_RES, _SUVAT_CUES, _extract_suvat_intent
from app.modules.physics.extractors.tension import (
    _TENSION_CUE_RES,
    _VECTOR_FORCE_CUE_RES,
    _extract_tension_intent,
    _extract_vector_force_intent,
)
from app.modules.physics.extractors.thermal import (
    _THERMAL_CUE_RES,
    _THERMAL_CUES,
    _extract_thermal_intent,
)
from app.modules.physics.extractors.torque import (
    _TORQUE_CUE_RES,
    _TORQUE_CUES,
    _extract_torque_intent,
)
from app.modules.physics.extractors.two_stage import extract_two_stage_intent
from app.modules.physics.extractors.waves import _WAVE_CUE_RES, _WAVE_CUES, _extract_waves_intent
from app.modules.physics.schemas import PhysicsIntent

PHYSICS_EXTRACTORS: tuple[Callable[[str], PhysicsIntent | None], ...] = (
    # Before kinematics: a drop that states F = -kv is not free fall.
    extract_drag_intent,
    # Before circuit, fluids, thermal, and waves. A partial Kirchhoff, Gauss,
    # Poiseuille, or ideal-gas reading must not fall through to Ohm's law.
    extract_school_extension,
    # Before the constant-speed rate law. A reaction interval plus a later
    # brake-to-stop is not d = vt, and the rate extractor only sees two numbers.
    extract_stopping_distance,
    # Before the rate law and SUVAT: speeding up, then holding the speed or
    # braking, is two intervals. Each of those reads one.
    extract_two_stage_intent,
    # Before the rate law: a chase's two speeds and a walk's two legs are roles
    # one d = vt would read as one speed or one distance.
    extract_chase_intent,
    extract_legs_intent,
    extract_rate_intent,
    _extract_kinematics_intent,
    # After kinematics, not before: free fall is a constant acceleration too,
    # and kinematics already owns it. SUVAT sees only what gravity did not
    # claim, so adding it perturbs nothing that already answered.
    _extract_suvat_intent,
    _extract_projectile_intent,
    _extract_momentum_intent,
    _extract_friction_intent,
    _extract_circular_intent,
    # Before the pendulum and the spring: both of those read a *period* as the
    # answer, and the two SHM ops read it as a given.
    _extract_shm_intent,
    # Before springs: a pendulum has a length where a spring has a constant,
    # so the two cannot collide, and reading in this order keeps the spring
    # extractor's k requirement untouched.
    _extract_pendulum_intent,
    _extract_spring_intent,
    _extract_electrostatics_intent,
    _extract_circuit_intent,
    _extract_torque_intent,
    # Ahead of force so the two rope shapes below are claimed before the
    # blanket refusal in _UNSUPPORTED_FORCE_CONTEXT sees them. Everything else
    # rope-shaped still reaches that refusal.
    _extract_tension_intent,
    _extract_vector_force_intent,
    # Round 3, all three ahead of force and energy. Each says a word those two
    # own - optics says "power" (of a lens, in dioptres), thermal says "energy"
    # and modern will too - and running first makes the split deterministic
    # rather than lucky.
    _extract_waves_intent,
    _extract_optics_intent,
    _extract_thermal_intent,
    _extract_gravitation_intent,
    _extract_magnetism_intent,
    # Before fluids, and the ordering is load-bearing: sigma = F/A and P = F/A
    # are the same arithmetic, so nothing about the numbers can separate them.
    # Stress is the narrower vocabulary, so it chooses first and fluids refuses
    # those words outright.
    _extract_materials_intent,
    _extract_fluids_intent,
    _extract_modern_intent,
    # After torque, deliberately. P9 refuses "moment of inertia" there because
    # it was not solved; that refusal is what stops *torque* claiming it, and
    # is kept. This picks up the fall-through.
    _extract_rotation_intent,
    _extract_force_intent,
    _extract_energy_intent,
)

PHYSICS_CUES: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *_DRAG_CUES,
            *_KINEMATICS_CUES,
            *_RATE_CUES,
            *_SUVAT_CUES,
            *_PROJECTILE_CUES,
            *_MOMENTUM_CUES,
            *_WAVE_CUES,
            *_OPTICS_CUES,
            *_THERMAL_CUES,
            *_GRAVITATION_CUES,
            *_FLUIDS_CUES,
            *_ROTATION_CUES,
            *_MAGNETISM_CUES,
            *_MATERIALS_CUES,
            *_MODERN_CUES,
            *_FRICTION_CUES,
            *_CIRCULAR_CUES,
            *_SPRING_CUES,
            *_ELECTROSTATICS_CUES,
            *_CIRCUIT_CUES,
            *_TORQUE_CUES,
            *_FORCE_CUES,
            *_ENERGY_CUES,
            *_EXTENSION_CUES,
        )
    )
)

PHYSICS_CUE_RES: tuple[re.Pattern[str], ...] = (
    *_KINEMATICS_CUE_RES,
    *_MOMENTUM_CUE_RES,
    *_SUVAT_CUE_RES,
    *_STOPPING_CUE_RES,
    *_PROJECTILE_CUE_RES,
    *_FRICTION_CUE_RES,
    *_CIRCULAR_CUE_RES,
    *_WAVE_CUE_RES,
    *_THERMAL_CUE_RES,
    *_GRAVITATION_CUE_RES,
    *_FLUIDS_CUE_RES,
    *_ROTATION_CUE_RES,
    *_MAGNETISM_CUE_RES,
    *_MATERIALS_CUE_RES,
    *_MODERN_CUE_RES,
    *_SHM_CUE_RES,
    *_PENDULUM_CUE_RES,
    *_SPRING_CUE_RES,
    *_ELECTROSTATICS_CUE_RES,
    *_CIRCUIT_CUE_RES,
    *_TORQUE_CUE_RES,
    *_TENSION_CUE_RES,
    *_VECTOR_FORCE_CUE_RES,
    *_FORCE_CUE_RES,
    *_ENERGY_CUE_RES,
    *_EXTENSION_CUE_RES,
)


def has_supported_physics_cue(cleaned: str) -> bool:
    """True when a verified physics template could match this text.

    Takes the text **as written**, not lowercased. See `_has_cue_either_case`.
    """
    return _has_cue_either_case(cleaned, PHYSICS_CUES, PHYSICS_CUE_RES)
