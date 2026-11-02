"""Shared protocol captions for camera scans across school subjects."""

from __future__ import annotations

import re
from typing import Literal

from app.services.solving import SubjectName

# The registry's subjects, and biology, whose camera caption the phone already sends.
ScannerSubject = SubjectName | Literal["biology"]

MATH_CAMERA_PROMPT = "Solve the math problem in this image step by step."
PHYSICS_CAMERA_PROMPT = "Solve the physics problem in this image step by step."
CHEMISTRY_CAMERA_PROMPT = "Solve the chemistry problem in this image step by step."
BIOLOGY_CAMERA_PROMPT = "Solve the biology problem in this image step by step."

# The line a photo carries after the student confirmed what the scanner read.
SCAN_CONFIRMED_PREFIX = "I read this as:"
_BLANK_LINE = re.compile(r"\n[ \t]*\n")

SCANNER_CAMERA_PROMPTS: dict[ScannerSubject, str] = {
    "math": MATH_CAMERA_PROMPT,
    "physics": PHYSICS_CAMERA_PROMPT,
    "chemistry": CHEMISTRY_CAMERA_PROMPT,
    "biology": BIOLOGY_CAMERA_PROMPT,
}


def scanner_camera_subject(text: str) -> ScannerSubject | None:
    """Return the explicit scanner subject without classifying arbitrary chat."""
    folded = text.strip().casefold()
    for subject, prompt in SCANNER_CAMERA_PROMPTS.items():
        expected = prompt.casefold()
        if folded == expected or folded.startswith(expected + "\n"):
            return subject
    return None


def is_scanner_camera_prompt(text: str) -> bool:
    return scanner_camera_subject(text) is not None


def confirmed_scan_reading(text: str) -> str | None:
    """The reading the student confirmed in the scanner, from a photo caption.

    The text after the prefix, up to the first blank line. The app writes the
    reading with its lines but none blank (``composerTextAfterScanConfirm``),
    so that line is where a typed draft or an attachment note begins. Linear.
    """
    needle = SCAN_CONFIRMED_PREFIX.casefold()
    idx = text.casefold().find(needle)
    if idx < 0:
        return None
    rest = text[idx + len(SCAN_CONFIRMED_PREFIX) :].strip()
    blank = _BLANK_LINE.search(rest)
    if blank is not None:
        rest = rest[: blank.start()]
    return rest.strip() or None
