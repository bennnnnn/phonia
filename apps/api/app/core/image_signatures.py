"""The image types a file's leading bytes show: one table for uploads and scans.

Attachments check stored bytes against the type a client claimed
(``modules/attachments/content_types.py``); a scan read-back checks the photo it
forwards to a paid reader (``services/scan_read.py``). Both read these
signatures, so a type added here is recognised by both.
"""

from __future__ import annotations


def sniff_image_type(data: bytes) -> str | None:
    """``image/jpeg``, ``image/png``, ``image/gif`` or ``image/webp``; None for anything else."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None
