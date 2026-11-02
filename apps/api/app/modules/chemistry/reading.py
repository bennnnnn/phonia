"""Confirmed chemistry scanner line, using the shared scan protocol."""

from __future__ import annotations

from app.services.student_claim import without_stated_results
from app.services.subject_scan import confirmed_scan_reading, scanner_camera_subject


def confirmed_chemistry_reading(text: str) -> str | None:
    """The line the student checked, when the chemistry camera caption is present."""
    if scanner_camera_subject(text) != "chemistry":
        return None
    return confirmed_scan_reading(text)


def chemistry_text_for_solve(text: str) -> str:
    """Solve the confirmed line (a caption with no reading stays the caption), without
    the student's stated result: "I got 29.2 g, am I right?" is a check, not a given."""
    return without_stated_results(confirmed_chemistry_reading(text) or text)
