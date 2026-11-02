"""Math HTTP surface: read a scanned problem back before it is solved.

The scanner used to send the photo straight into the chat, so a misread
digit was solved with full confidence. ``POST /math/scan/read`` runs the same
OCR the chat turn uses and returns the reading for the student to confirm or
edit; the confirmed text is then sent as an ordinary message.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings
from app.core.consent import get_consented_user
from app.core.deps import get_settings_dep
from app.models.orm import User
from app.models.schemas.scan import ScanReadingOut
from app.modules.math.ocr import MathOcrResult, extract_math_from_image
from app.services.scan_read import ScanPhoto, ScanRefusedError, read_scan

router = APIRouter(prefix="/math", tags=["math"])

# "2*x+3" reads as "2x+3"; "x**2" as "x^2". The chat parser accepts both.
_IMPLICIT_TIMES = re.compile(r"(\d)\s*\*\s*(?=[A-Za-z(])")


def readable_reading(text: str) -> str:
    return _IMPLICIT_TIMES.sub(r"\1", text.replace("**", "^")).strip()


@router.post("/scan/read", response_model=ScanReadingOut)
async def read_math_scan(
    request: Request,
    user: User = Depends(get_consented_user),
    settings: Settings = Depends(get_settings_dep),
) -> ScanReadingOut:
    if not settings.math_tools_enabled:
        raise ScanRefusedError("Not available", status_code=404, code="not_available")

    async def read(photo: ScanPhoto, seconds_left: float) -> MathOcrResult:
        return await extract_math_from_image(
            settings,
            content_type=photo.content_type,
            data=photo.data,
            timeout_seconds=seconds_left,
        )

    result = await read_scan(request, user=user, settings=settings, subject="math", read=read)
    if result is None:
        # A failed read falls back to sending the photo; never a 500 here.
        return ScanReadingOut(reading="", uncertain=True, source="none")
    reading = readable_reading(result.display_text)
    return ScanReadingOut(
        reading=reading,
        uncertain=result.uncertain or not reading,
        source=result.source if reading else "none",
    )
