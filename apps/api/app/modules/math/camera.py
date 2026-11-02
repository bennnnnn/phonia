"""Camera maths: read the equation in a turn's photo so SymPy can verify the answer.

It runs for the maths scanner's caption, a caption that still reads as a maths request,
or a reading the student already confirmed in the scanner. Chat asks it through maths'
adapter (``photo``, ``services/subjects/registry``) and hands it the photo's bytes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.core.config import Settings
from app.modules.math.schemas import MathImageExtract


async def read_camera_maths(
    content: str,
    *,
    image_attachments: list[tuple[str, str]],
    load_image: Callable[[str], Awaitable[bytes | None]],
    settings: Settings,
    on_status: Callable[[str], Awaitable[None]] | None,
) -> tuple[MathImageExtract | None, str]:
    """The equation in the first photo, and ``content`` with its ``Solve:`` line for the prompt.

    ``load_image`` gives a photo's bytes by its storage key (the caller keeps them for the
    vision injection).
    """
    image_math_extract: MathImageExtract | None = None
    # Camera math solver: vision-extract equation so SymPy can verify.
    from app.modules.math import image_extract as math_image_extract_service
    from app.modules.math import match as math_match
    from app.services.subject_scan import confirmed_scan_reading, scanner_camera_subject

    # The composer pre-fills the camera caption into an editable box, so the student may
    # have changed it (a word added, a typo fixed, autocorrect on the punctuation). An
    # edited caption still reads as a maths ask ("solve this", "find x"), so OCR runs
    # whenever the caption has a maths keyword, the signal needs_symbolic_math trusts for
    # an attached image, not only on the exact caption. A caption with no maths keyword
    # (or the blank one a plain photo sends) is left alone: no vision call on every photo.
    caption = content.strip()
    scan_subject = scanner_camera_subject(content)
    looks_like_math_caption = (
        scan_subject not in {"physics", "biology", "chemistry"}
        and bool(caption)
        and math_match.has_math_keyword(caption.lower())
    )
    # A physics or chemistry photo carries its confirmed reading too, but that
    # reading is the subject's request text, not an equation for math OCR.
    confirmed_reading = confirmed_scan_reading(content) if scan_subject in (None, "math") else None
    if image_attachments and (
        confirmed_reading or scan_subject == "math" or looks_like_math_caption
    ):
        if on_status is not None:
            await on_status("calculating")
        if confirmed_reading:
            # The student already verified OCR in the scanner. Re-running
            # vision here can silently solve a different equation.
            from app.modules.math.ocr import extract_from_confirmed_reading

            extracted = extract_from_confirmed_reading(confirmed_reading)
            if extracted is not None:
                image_math_extract = extracted
        else:
            mime, storage_key = image_attachments[0]
            image_bytes = await load_image(storage_key)
            if image_bytes:
                extracted = await math_image_extract_service.extract_equation_from_image(
                    settings, content_type=mime, data=image_bytes
                )
                if extracted is not None:
                    image_math_extract = extracted
                    suffix = math_image_extract_service.camera_math_user_suffix(extracted)
                    # Prompt/stream path sees Solve: for equations; stored bubble
                    # keeps the image marker + original caption only.
                    if suffix:
                        content = f"{content}\n\n{suffix}"
    return image_math_extract, content
