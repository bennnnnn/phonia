"""Physics HTTP surface: read a scanned problem back before it is solved.

``POST /physics/scan/read`` returns the problem as plain text for the student
to confirm or edit. The confirmed text is then sent as an ordinary message,
so a photographed problem is verified like a typed one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings
from app.core.consent import get_consented_user
from app.core.deps import get_settings_dep
from app.models.orm import User
from app.models.schemas.scan import ScanReadingOut
from app.modules.physics.read import read_physics_problem
from app.services.scan_read import ScanPhoto, ScanRefusedError, read_scan

router = APIRouter(prefix="/physics", tags=["physics"])


@router.post("/scan/read", response_model=ScanReadingOut)
async def read_physics_scan(
    request: Request,
    user: User = Depends(get_consented_user),
    settings: Settings = Depends(get_settings_dep),
) -> ScanReadingOut:
    # Physics is verified only while math tools are on; a reading the chat
    # cannot verify would only add a step before the same unverified answer.
    if not settings.math_tools_enabled:
        raise ScanRefusedError("Not available", status_code=404, code="not_available")

    async def read(photo: ScanPhoto, seconds_left: float) -> str:
        return await read_physics_problem(
            settings,
            content_type=photo.content_type,
            data=photo.data,
            timeout_seconds=seconds_left,
        )

    reading = await read_scan(request, user=user, settings=settings, subject="physics", read=read)
    text = (reading or "").strip()
    return ScanReadingOut(reading=text, uncertain=not text, source="vision" if text else "none")
