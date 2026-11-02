"""Which attachment types Recall accepts, and whether the bytes match the claimed type.

The allowlist, MIME aliases, magic-byte sniffing and the DOCX zip-bomb guard.
Extraction itself lives in ``content.py``.
"""

from __future__ import annotations

import io
import zipfile

from app.core.attachment_limits import MAX_ATTACHMENT_SIZE

IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
        # HEIC/HEIF rejected — unreliable cross-platform preview + vision; ask for JPEG/PNG.
    }
)

DOCUMENT_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        # Legacy .doc (application/msword) intentionally excluded — no pure-Python
        # parser can read it, so uploads succeed but RAG silently fails. Reject
        # at presign with a clear error so users convert to .docx instead.
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
)

ALLOWED_CONTENT_TYPES = IMAGE_CONTENT_TYPES | DOCUMENT_CONTENT_TYPES

_CONTENT_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
}

# Text-ish types have no reliable magic signature. Accept only clean UTF-8
# with no NUL (rejects polyglot binaries claimed as txt/json/csv/md). HEIC/HEIF
# use an ISO BMFF ftyp box that's awkward to sniff here and are rare via the
# local upload path, so they're accepted on trust for now.
_TEXTISH_TYPES = frozenset({"text/plain", "text/markdown", "text/csv", "application/json"})
_UNVERIFIABLE_TYPES: frozenset[str] = frozenset()


_DOCX_MARKER_ENTRY = "word/document.xml"
_MAX_DOCX_TOTAL_UNCOMPRESSED = 32 * 1024 * 1024
_OFFICE_MARKERS = {
    _DOCX_MARKER_ENTRY: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xl/workbook.xml": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt/presentation.xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
}


def _office_content_type(data: bytes) -> str | None:
    try:
        if _docx_zip_bomb(data):
            return None
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            # Reject ambiguous containers and macro-bearing files even if renamed.
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                return None
            matches = [mime for marker, mime in _OFFICE_MARKERS.items() if marker in names]
            return matches[0] if len(matches) == 1 else None
    except (zipfile.BadZipFile, OSError, EOFError, NotImplementedError):
        return None


def _docx_zip_bomb(data: bytes) -> bool:
    """True when any ZIP entry or the total uncompressed size looks like a bomb.

    Per-entry cap matches ``MAX_ATTACHMENT_SIZE``; total uncompressed across
    all entries is capped at 32 MiB so a small compressed upload can't expand
    into gigabytes during DOCX parse.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > 4096:
                return True
            total = 0
            for info in archive.infolist():
                if info.file_size > MAX_ATTACHMENT_SIZE:
                    return True
                total += info.file_size
                if total > _MAX_DOCX_TOTAL_UNCOMPRESSED:
                    return True
        return False
    except (zipfile.BadZipFile, OSError, EOFError, NotImplementedError):
        return False


def _sniff_signature(data: bytes) -> str | None:
    """Detect a few common binary types by leading magic bytes."""
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 4 and data[:4] == b"%PDF":
        return "application/pdf"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 4 and data[:4] == b"PK\x03\x04":
        return _office_content_type(data)
    if len(data) >= 8 and data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "application/msword"
    return None


def _is_clean_textish(data: bytes) -> bool:
    """UTF-8 text with no NUL — rejects polyglot binaries claimed as txt/json/csv/md."""
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def bytes_match_claimed(claimed: str, data: bytes) -> bool:
    """True if the uploaded bytes are consistent with the claimed content type.

    The presign step validates the *claim*; this checks the *actual bytes* on
    upload so a client can't presign "image/png" and then upload a shell script
    that later gets served back with `Content-Type: image/png` (a content-
    spoofing risk for any externally-shared signed URL).
    """
    norm = "image/jpeg" if claimed == "image/jpg" else claimed
    if norm in _UNVERIFIABLE_TYPES:
        return True
    detected = _sniff_signature(data)
    if detected is None:
        # No binary signature. Accept only for text-ish claims; an image/pdf
        # claim with no matching signature is a spoof.
        if norm not in _TEXTISH_TYPES:
            return False
        return _is_clean_textish(data)
    if detected != norm:
        return False
    if norm in _TEXTISH_TYPES:
        return _is_clean_textish(data)
    return True


def normalize_content_type(content_type: str) -> str:
    """Normalize client MIME types (strip params, map common aliases)."""
    base = content_type.split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_ALIASES.get(base, base)


def is_allowed_content_type(content_type: str) -> bool:
    return normalize_content_type(content_type) in ALLOWED_CONTENT_TYPES


def is_image_content_type(content_type: str) -> bool:
    return normalize_content_type(content_type) in IMAGE_CONTENT_TYPES


_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Types extract_text_details actually knows how to parse. Used to tell a
# genuinely unsupported type (e.g. legacy .doc, which has no good pure-Python
# parser) apart from a supported type that just yielded no text (e.g. a
# scanned image-only PDF) — the two deserve different user-facing messages.
EXTRACTABLE_CONTENT_TYPES = _TEXTISH_TYPES | {"application/pdf", *_OFFICE_MARKERS.values()}
