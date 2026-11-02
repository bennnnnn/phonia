"""The battery and the sweeps model production, so their maths declines stay silent.

``RECALL_STRICT_DECLINES=1 uv run pytest app/tests/behavior`` (or the same variable on
``python -m app.tests.behavior.stem_sweep math``) runs them strict instead.
"""

import pytest


@pytest.fixture(autouse=True)
def _production_declines(production_declines: None) -> None:
    """See ``production_declines`` in ``app/tests/conftest.py``."""
