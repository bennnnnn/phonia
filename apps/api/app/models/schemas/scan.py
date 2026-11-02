"""A scanned photo sent to be read back, and what the reader saw.

Math, physics and chemistry each read a cropped camera photo for the student
to confirm before anything is solved. They share this request and response.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Decoded image cap for a scan read-back; the camera sends a cropped photo.
SCAN_MAX_IMAGE_BYTES = 8_000_000
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
