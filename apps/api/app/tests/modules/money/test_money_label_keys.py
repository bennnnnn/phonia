"""Every key a calculator card names has text on the phone, or the phone shows a blank label."""

from __future__ import annotations

import json

from app.modules.money.catalog import PRODUCTS
from app.modules.money.schemas import Marker
from app.tests.architecture.boundary_support import MOBILE_ROOT


def _sent_keys() -> set[str]:
    keys = {Marker.model_fields["label_key"].default}
    for product in PRODUCTS:
        keys.add(product.title_key)
        keys.update(item.label_key for item in product.inputs)
        keys.update(item.label_key for item in product.outputs)
        keys.update(item.never_key for item in product.outputs if item.never_key)
    return keys


def test_every_card_key_has_phone_text() -> None:
    english = json.loads((MOBILE_ROOT / "lib" / "i18n" / "en.json").read_text())
    missing = sorted(key for key in _sent_keys() if key not in english)
    assert not missing, f"add these to apps/mobile/lib/i18n (all nine locales): {missing}"
