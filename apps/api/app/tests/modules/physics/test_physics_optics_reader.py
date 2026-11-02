"""The optics reader: one law per cue, tried in a fixed order, the first cue deciding."""

from __future__ import annotations

import pytest

from app.modules.physics.extractors.optics import _extract_optics_intent


@pytest.mark.parametrize(
    ("text", "op", "params", "units"),
    [
        (
            "A ray hits a plane mirror at 35 degrees to the normal. What is the angle of "
            "reflection?",
            "reflection_angle",
            {"angle": 35.0},
            {"angle": "deg"},
        ),
        (
            "A ray strikes a plane mirror at 30 degrees to the mirror surface. What angle does "
            "the reflected ray make with the mirror?",
            "reflection_surface_angle",
            {"angle_surface": 30.0},
            {"angle_surface": "deg"},
        ),
        (
            "If the angle of incidence is 40 degrees, what is the angle between the incident ray "
            "and the reflected ray?",
            "reflection_ray_angle",
            {"angle": 40.0},
            {"angle": "deg"},
        ),
        (
            "Using Malus's law, light of intensity 800 W/m^2 passes a polarizer at 60 degrees. "
            "Find the transmitted intensity.",
            "malus_intensity",
            {"intensity0": 800.0, "angle": 60.0},
            {"intensity0": "W/m^2", "angle": "deg"},
        ),
        (
            "Find Brewster's angle for light going from n1 = 1.0 to n2 = 1.5.",
            "brewster_angle",
            {"n1": 1.0, "n2": 1.5},
            {"n1": "", "n2": ""},
        ),
        (
            "In a double slit experiment the wavelength is 600 nm, the slit separation is 0.2 mm "
            "and the screen distance is 2 m. Find the fringe spacing.",
            "double_slit_fringe_spacing",
            {"wavelength": 600.0, "L": 2.0, "d": 0.2},
            {"wavelength": "nm", "L": "m", "d": "mm"},
        ),
        (
            "In a single slit diffraction experiment the wavelength is 500 nm, the slit width is "
            "0.1 mm and the screen distance is 1.5 m. Find the width of the central maximum.",
            "diffraction_central_width",
            {"wavelength": 500.0, "L": 1.5, "d": 0.1},
            {"wavelength": "nm", "L": "m", "d": "mm"},
        ),
        (
            "What is the lens power of a lens with a focal length of 25 cm?",
            "lens_power",
            {"focal": 25.0},
            {"focal": "cm"},
        ),
        (
            "What is the critical angle for glass with refractive index 1.5?",
            "critical_angle",
            {"n1": 1.5},
            {"n1": ""},
        ),
        (
            "Light passes from air into glass at an angle of incidence of 45 degrees and refracts "
            "at 28 degrees. Find the refractive index of the glass.",
            "refractive_index",
            {"angle": 45.0, "angle2": 28.0},
            {"angle": "deg", "angle2": "deg"},
        ),
        (
            "Light travels at 2e8 m/s in glass. What is its refractive index?",
            "refractive_index",
            {"v_wave": 2e8},
            {"v_wave": "m/s"},
        ),
        (
            "An object 2 cm tall forms an image 6 cm tall. What is the magnification?",
            "magnification",
            {"h_img": 6.0, "h_obj": 2.0},
            {"h_img": "cm", "h_obj": "cm"},
        ),
        (
            "A convex lens has a focal length of 10 cm. An object is placed 30 cm from the lens. "
            "Find the image distance.",
            "image_distance",
            {"focal": 10.0, "d_obj": 30.0},
            {"focal": "cm", "d_obj": "cm"},
        ),
        (
            "A concave mirror has a focal length of 10 cm. An object is placed 15 cm from the "
            "mirror. Where is the image?",
            "image_distance",
            {"focal": 10.0, "d_obj": 15.0, "mirror": 1.0},
            {"focal": "cm", "d_obj": "cm", "mirror": ""},
        ),
    ],
)
def test_optics_reader_reads_each_law(
    text: str, op: str, params: dict[str, float], units: dict[str, str]
) -> None:
    intent = _extract_optics_intent(text)

    assert intent is not None
    assert (intent.kind, intent.physics_op) == ("optics", op)
    assert intent.physics_params == params
    assert intent.physics_units == units


@pytest.mark.parametrize(
    "text",
    [
        # The gates: a diverging lens, the catalog's microscope.
        "A diverging lens has a focal length of 10 cm and an object at 30 cm. Find the image "
        "distance.",
        "A microscope objective has focal length 4 mm and the object is 5 mm away. Find the "
        "image distance.",
        # A named law that cannot be read declines: it never falls through to a later law.
        "Using Malus's law, light passes a polarizer at 60 degrees. Find the transmitted "
        "intensity.",
        "Malus and Brewster: n1 = 1 and n2 = 1.5, find Brewster's angle.",
        "Find Brewster's angle for glass with n2 = 1.5.",
        "What is the critical angle for a refractive index of 0.9?",
        "What is the refractive index of glass if the index of refraction is 1.5?",
        "An object 20 cm from a lens of focal length 15 cm forms an image 60 cm from the lens. "
        "What is the magnification?",
    ],
)
def test_optics_reader_declines(text: str) -> None:
    assert _extract_optics_intent(text) is None


def test_optics_reader_tries_the_critical_angle_before_snell() -> None:
    intent = _extract_optics_intent(
        "What is the critical angle for a refractive index of 1.5 by Snell's law?"
    )

    assert intent is not None
    assert intent.physics_op == "critical_angle"
