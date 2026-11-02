"""Optics certifies only the signs it read (retro review, 2026-11-01).

- A myopic eye's lens, a minus lens, a rear-view mirror and an upright, diminished image
  are diverging elements, however the question words them.
- m = -v/u and the image distance read every distance as a real one: a sign on a number or
  a distance called negative declines.
- Where the image is sets a magnification's sign, and no wording of it is read: any place
  word (behind, in front, beyond, a side, left or right of) declines m = -v/u and heights.
- Heights give m = h_i/h_o only for an image not called real or inverted.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.optic_elements import (
    diverging_element,
    inverted_image,
    places_named,
    signed_distances,
)
from app.tests.modules.physics.support import answer_number

_SETTINGS = Settings(mock_llm_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(
    "text",
    [
        "A myopic person uses a lens of focal length 80 cm.",
        "A myope wears lenses of focal length 40 cm.",
        "A short sighted person uses a lens of focal length 40 cm.",
        "A person who is nearsighted wears glasses.",
        "An object is placed 30 cm from a minus lens of focal length 15 cm.",
        "The lens is a negative lens.",
        "A mirror of focal length 15 cm is used as a rear-view mirror in a car.",
        "A wing mirror on a car has a focal length of 50 cm.",
        "A mirror forms a virtual, erect and diminished image.",
        "A lens forms an erect image smaller than the object.",
    ],
)
def test_a_diverging_element_however_worded(text: str) -> None:
    assert diverging_element(text)


@pytest.mark.parametrize(
    "text",
    [
        "A long-sighted person uses a lens of focal length 50 cm.",
        "A convex lens forms a virtual, magnified image.",
        "A concave mirror forms a real, diminished image.",
        "The side of a plane mirror.",
    ],
)
def test_not_a_diverging_element(text: str) -> None:
    assert not diverging_element(text)


@pytest.mark.parametrize(
    ("text", "signed"),
    [
        ("u = -15 cm and v = +30 cm for a convex lens.", True),
        ("The object distance is \u221215 cm.", True),
        ("The image distance is negative 30 cm.", True),
        ("Objects 10-20 cm from a lens.", False),
        ("An object is placed 20 cm in front of a concave mirror.", False),
    ],
)
def test_signed_distances(text: str, signed: bool) -> None:
    assert signed_distances(text) is signed


@pytest.mark.parametrize(
    ("text", "placed"),
    [
        ("A concave mirror and the image forms 30 cm behind it.", True),
        ("The image of the object is formed 30 cm behind a concave mirror.", True),
        ("A convex lens. The image is formed 30 cm in front of the lens.", True),
        ("A convex lens; its image is formed 30 cm on the object's side.", True),
        ("A concave mirror; the image is 30 cm on the other side of the mirror.", True),
        ("The image forms 30 cm to the left of the lens.", True),
        ("The image is beyond 2F.", True),
        ("An object is 20 cm from a lens and its image is 60 cm from it.", False),
    ],
)
def test_places_named(text: str, placed: bool) -> None:
    assert places_named(text) is placed


@pytest.mark.parametrize(
    ("text", "inverted"),
    [
        ("A real, inverted image that is 6 cm tall.", True),
        ("An image of height 9 cm that is upside down.", True),
        ("An erect image 2 cm high.", False),
        ("An image of height 6 cm.", False),
        ("Is the image real or virtual, erect or inverted?", False),
    ],
)
def test_inverted_image(text: str, inverted: bool) -> None:
    assert inverted_image(text) is inverted


@pytest.mark.parametrize(
    "text",
    [
        "A myopic person uses a lens of focal length 80 cm. Find the lens power.",
        "A myope wears lenses of focal length 40 cm. Find the power of the lenses.",
        "A lens forms a virtual, diminished image. Its focal length is 20 cm. Find its power.",
        "A mirror has a radius of curvature of 30 cm and forms an erect, diminished image. "
        "Find its focal length.",
        "An object is placed 10 cm from a concave mirror and the image forms 30 cm behind it. "
        "Find the magnification.",
        "An object is 10 cm from a concave mirror and the image is formed 30 cm on the other "
        "side of the mirror. Find the magnification.",
        "An object is placed 10 cm from a convex lens and its image is formed 30 cm from the "
        "lens on the object's side. Find the magnification.",
        "The image of the object is formed 30 cm behind a concave mirror. The object is 10 cm "
        "from the mirror. Find the magnification.",
        "For a convex lens, the object distance is -15 cm and the image distance is +30 cm. "
        "Find the magnification.",
        "The image distance is negative 30 cm and the object distance is 10 cm for a lens. "
        "Find the magnification.",
        # A real image's place too: no wording of the image's place is read.
        "An object is placed 20 cm in front of a concave mirror and the image is formed 60 cm "
        "in front of the mirror. Find the magnification.",
        "An object is placed 20 cm from a convex lens and the image is formed 60 cm on the "
        "other side of the lens. Find the magnification.",
        "An object 2 cm tall forms an image 6 cm tall 60 cm in front of a concave mirror. Find "
        "the magnification.",
        "An object is placed 30 cm from a minus lens of focal length 15 cm. Find the image "
        "distance.",
        "A mirror forms a virtual, erect and diminished image. Its focal length is 10 cm and "
        "the object is 15 cm away. Find the image distance.",
        "A mirror of focal length 15 cm is used as a rear-view mirror in a car. An object is "
        "20 cm away. Find the image distance.",
        "A 2 cm tall object forms a real, inverted image that is 6 cm tall. Find the "
        "magnification.",
        "A lens produces an image 6 cm tall of an object 2 cm tall. The image is real. Find "
        "the magnification.",
        "An object of height 2 cm has an image of height -6 cm. Find the magnification.",
        "An object of height 2 cm has an image whose height is negative 6 cm. Find the "
        "magnification.",
    ],
)
def test_a_sign_not_read_declines(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("A long-sighted person uses a lens of focal length 50 cm. Find the lens power.", 2.0),
        ("A lens has a focal length of -40 cm. Find the lens power.", -2.5),
        # An object's place names no sign the image distance reads.
        (
            "An object is placed 20 cm in front of a concave mirror of focal length 15 cm. "
            "Find the image distance.",
            60.0,
        ),
        ("An object 4 cm high forms an erect image 2 cm high. What is the magnification?", 0.5),
        (
            "A convex lens forms a real, inverted image. The object is 30 cm away and the "
            "focal length is 10 cm. Find the image distance.",
            15.0,
        ),
        # A nature the question asks about is not one it states.
        (
            "A thin lens of focal length 20 cm. An object is 30 cm away. Find the image "
            "distance and say whether the image is real or virtual.",
            60.0,
        ),
        (
            "An object of height 2 cm forms an image of height 6 cm. Find the magnification "
            "and state whether the image is erect or inverted.",
            3.0,
        ),
    ],
)
def test_a_sign_read_answers(text: str, value: float) -> None:
    answer = _answer(text)
    assert answer is not None and answer_number(answer) == pytest.approx(value)
