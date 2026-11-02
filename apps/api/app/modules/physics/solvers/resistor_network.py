"""How a resistor network names its members: R1 to R9."""

from __future__ import annotations

import re

# Single-digit, so plain `sorted` orders them correctly.
RESISTOR_KEY_RE = re.compile(r"R[1-9]")
