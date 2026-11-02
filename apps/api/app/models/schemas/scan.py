"""A scanned photo sent to be read back, and what the reader saw.

Math, physics and chemistry each read a cropped camera photo for the student
to confirm before anything is solved. They share this request and response.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Decoded image cap for a scan read-back. The phone sends one crop as JPEG at
# quality 0.8, its long edge at most 2048 px (``features/scanner/model/scanImage.ts``):
# about 0.3-1.5 MB, and under 4 MB even for a 2048 x 2048 crop of fine detail.
# ``core/settings/edge.py``'s scan body cap sits just above the request this allows.
SCAN_MAX_IMAGE_BYTES = 4_000_000
SCAN_MAX_B64_CHARS = 4 * ((SCAN_MAX_IMAGE_BYTES + 2) // 3)
SCAN_MAX_REQUEST_BYTES = SCAN_MAX_B64_CHARS + 4096


class ScanPhotoIn(BaseModel):
    image_base64: str = Field(min_length=1, max_length=SCAN_MAX_B64_CHARS)
    content_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"


class ScanReadingOut(BaseModel):
    # What the photo says, as plain editable text; empty when nothing was legible.
    reading: str
    # Low OCR confidence, or a read the subject could not structure: ask the
    # student to look closely before solving.
    uncertain: bool
    source: Literal["mathpix", "vision", "none"]
