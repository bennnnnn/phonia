"""Which optical element a question is about, and which signs its distances carry, however it
is worded.

A convex mirror and a concave lens diverge: their focal lengths and images carry the sign
the New Cartesian convention gives them, and a law written for a converging element
certifies the wrong one. "10 cm from a convex mirror of focal length 15 cm" was certified
30 cm (the image is 6 cm behind the mirror), and so was "a convex spherical mirror" and
"The mirror is convex" once the first was fixed by its words alone (2026-10-30). A myopic
eye's lens, a minus lens, a rear-view mirror and an erect, diminished image name one too:
each was certified as converging (2026-11-01).

The unsigned laws read every distance as a real one. A question that writes a sign
("u = -15 cm") or calls a distance negative states a convention they do not read. Where the
image is (behind, in front, which side) sets the sign of a magnification, and no wording of
it is read: m = -v/u certified -3 for an image 30 cm behind a concave mirror (it is +3), and
reading the image's clause leaked twice in review, so any place word declines one.
"""

from __future__ import annotations

import re

# "biconcave" and "double-concave" too; a plane mirror beside a convex lens is no convex mirror.
_CONVEX = re.compile(r"convex\b")
_CONCAVE = re.compile(r"concave\b")
_MIRROR = re.compile(r"(?<!plane )\bmirrors?\b")
_LENS = re.compile(r"\blens(?:es)?\b")
_DIVERGING = re.compile(
    r"\bdiverging\b|\bvirtual\s+image\b|\bnegative\s+focal\b"
    r"|\b(?:negative|minus)\s+(?:lens|lenses|power)\b"
    # A short-sighted eye is corrected by a concave lens.
    r"|\bmyop|\b(?:short|near)[\s-]?sight"
    # A vehicle's or a shop's mirror that widens the view is convex.
    r"|\brear[\s-]?view\b"
    r"|\b(?:wing|side|side[\s-]?view|security|surveillance|blind[\s-]?spot|traffic|road)"
    r"\s+mirrors?\b"
)
# Only a diverging element forms an upright image smaller than the object.
_UPRIGHT = re.compile(r"\b(?:virtual|erect|upright)\b")
_DIMINISHED = re.compile(r"\b(?:diminished|smaller)\b")
_INVERTED = re.compile(r"\b(?:real|inverted|upside[\s-]?down)\b")
# A nature asked about is not stated: "say whether the image is real or virtual" (a
# converging lens's 60 cm was declined for it in review).
_NATURES = r"(?:real|virtual|erect|upright|inverted|magnified|enlarged|diminished|smaller|larger)"
_NATURE_CHOICE = re.compile(rf"\b{_NATURES}\s*(?:/|,?\s*or\s+(?:an?\s+)?){_NATURES}\b")
# "u = -15 cm" (a hyphen, a minus sign or a dash), "(+30 cm)": a sign on a number, not a
# range's dash ("10-15 cm").
_SIGNED_NUMBER = re.compile(r"(?<![\w.,)])[-+\u2212\u2013]\s?\d")
_SIGN_WORD = re.compile(r"\b(?:negative|minus)\b")
# Where something is put beside a lens or a mirror: "behind", "in front", "beyond", "the other
# side", "the object's side", "to the left of".
_PLACE = re.compile(r"\b(?:behind|beyond|sides?)\b|\bin\s+front\b|\b(?:left|right)\s+of\b")


def diverging_element(text: str) -> bool:
    """A convex mirror, a concave lens or a diverging element, named in any order."""
    lower = text.lower()
    return bool(
        _DIVERGING.search(lower)
        or (_CONVEX.search(lower) and _MIRROR.search(lower))
        or (_CONCAVE.search(lower) and _LENS.search(lower))
        or _upright_diminished(_stated_natures(lower))
    )


def converging_element(text: str) -> bool:
    """A converging lens or mirror, a convex lens or a concave mirror, named in any order."""
    lower = text.lower()
    return bool(
        "converging" in lower
        or (_CONVEX.search(lower) and _LENS.search(lower))
        or (_CONCAVE.search(lower) and _MIRROR.search(lower))
    )


def upright_image(text: str) -> bool:
    """The image is called virtual, erect or upright."""
    return _UPRIGHT.search(_stated_natures(text.lower())) is not None


def inverted_image(text: str) -> bool:
    """The image is called real or inverted."""
    return _INVERTED.search(_stated_natures(text.lower())) is not None


def places_named(text: str) -> bool:
    """The question says where something is beside the element: the image's place, which
    sets a magnification's sign, may be any of them."""
    return _PLACE.search(text.lower()) is not None


def _stated_natures(lower: str) -> str:
    """The question without the natures it asks to choose between."""
    return _NATURE_CHOICE.sub(" ", lower)


def _upright_diminished(lower: str) -> bool:
    return _UPRIGHT.search(lower) is not None and _DIMINISHED.search(lower) is not None


def signed_distances(text: str) -> bool:
    """The question gives a distance its sign, on a number or in words."""
    lower = text.lower()
    return _SIGNED_NUMBER.search(lower) is not None or _SIGN_WORD.search(lower) is not None
