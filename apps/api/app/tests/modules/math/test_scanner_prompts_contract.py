"""The scan captions match the phone's, through one fixture (code-health audit CLAR-13).

The phone sends a camera caption with a scan and the API recognizes it by exact text.
The pin was a comment in ``lib/math/cameraPrompt.ts`` naming a deleted file; both suites
now compare their constants with ``docs/fixtures/scanner_prompts.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.subject_scan import SCAN_CONFIRMED_PREFIX, SCANNER_CAMERA_PROMPTS

_FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "scanner_prompts.json"


def test_the_scan_captions_are_the_fixtures() -> None:
    fixture = json.loads(_FIXTURE.read_text())
    assert dict(SCANNER_CAMERA_PROMPTS) == fixture["camera_prompts"]
    assert SCAN_CONFIRMED_PREFIX == fixture["confirmed_prefix"]
