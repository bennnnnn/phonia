"""The scene titles the phone translates (``rich.scene_title_<key>``)."""

from __future__ import annotations

from typing import Literal

# Titles the client translates. A scene sets the one that names it; the
# English `title` stays for clients that do not know the key.
TitleKey = Literal[
    "projectile",
    "free_fall",
    "orbit",
    "satellite",
    "circular_motion",
    "collision",
    "recoil",
    "incline",
    "moments",
    "free_body",
    "height",
    "atwood",
    "forces",
    "spring",
    "pendulum",
    "circuit",
    "lens",
    "mirror",
    "refraction",
    "wave",
    "standing_wave",
    "buoyancy",
    "charges",
]
