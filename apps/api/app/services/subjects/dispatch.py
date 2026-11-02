"""The subject dispatcher: a line's subject, its solve and its direct reply.

A line's subject comes from the subject order (``services/subjects/order``), so a subject
package never decides which peer owns a turn. The solve and the direct reply are the
subject's own, asked through its adapter (``services/subjects/registry``); nothing here
reaches into a subject.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.readings import read_off_loop, reading
from app.services.solving import SubjectAugmentation, VerifiedSolveBlock
from app.services.subjects.order import read_subject_reason
from app.services.subjects.registry import SubjectName as SubjectName
from app.services.subjects.registry import SubjectRequest, subject_adapter
from app.services.worked_parts import parts_in_one_layout

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.modules.math.schemas import MathImageExtract


def detect_subject(
    text: str,
    *,
    has_image_attachment: bool = False,
    image_math_extract: MathImageExtract | None = None,
    chemistry_enabled: bool = True,
) -> SubjectName | None:
    """Pick one subject for this line.

    An image math extract is math. A closed chemistry extraction wins over physics and
    math: molarity and Gibbs notation look like algebra, and a mass percent has masses
    physics would read. Otherwise physics wins over math, and a chemistry question that
    chemistry could not close (a pH, a Ka, a molarity, a formula or an equation) is still
    chemistry's, never math's. Chemistry runs for a lookup only when neither peer has
    claimed the line.
    """
    if image_math_extract is not None:
        return "math"
    return _subject_of_text(text, has_image_attachment, chemistry_enabled)


async def read_subject(
    text: str,
    settings: Settings,
    *,
    has_image_attachment: bool = False,
    image_math_extract: MathImageExtract | None = None,
) -> SubjectName | None:
    """``detect_subject`` read off the event loop, in the SymPy pool (``core/readings``)."""
    if image_math_extract is not None:
        return "math"
    return await read_off_loop(
        _subject_of_text,
        text,
        has_image_attachment,
        settings.chemistry_enabled,
        timeout=settings.subject_read_timeout_seconds,
    )


@reading(declined=None)
def _subject_of_text(
    text: str, has_image_attachment: bool, chemistry_enabled: bool
) -> SubjectName | None:
    """``detect_subject`` for a line with no image extract: a reading (``core/readings``)."""
    found = read_subject_reason(text, has_image_attachment, chemistry_enabled)
    return None if found is None else found.subject


# "Dilute …, and also solve …" is two problems. One failed reading of the
# whole line used to stamp "couldn't verify" under two correct answers.
_ANSWER_LABEL = re.compile(r"^\*\*Answer:?\*\*", re.MULTILINE)
_AND_ALSO = re.compile(r"(?:,\s*|\s+)\band\s+also\b\s+", re.IGNORECASE)


async def build_subject_augmentation(
    user_content: str,
    settings: Settings,
    *,
    math_user_content: str | None = None,
    has_image_attachment: bool = False,
    image_math_extract: MathImageExtract | None = None,
    prior_user_messages: list[str] | None = None,
    response_intent_text: str | None = None,
    detected_subject: SubjectName | None = None,
    redis: Redis | None = None,
    pair: bool = True,
    parts: Sequence[str] = (),
    parts_answer_all: bool = False,
) -> SubjectAugmentation:
    """The turn's subject solve.

    ``parts``: the separate questions the turn's plan read in the message, each with the
    setup it carries ("A ball is dropped from 20 m. What is its speed after 1 s?" and "…
    How long does it take to reach the ground?"). Each is solved on its own: when every part
    of the message is one (``parts_answer_all``) and each answers itself, the reply is the
    question in parts; otherwise the first part that verifies keeps its card, where the
    whole message read as one problem verified nothing.
    """
    if len(parts) >= 2 and not has_image_attachment:
        return await _solve_parts(
            user_content,
            settings,
            parts,
            answer_all=parts_answer_all,
            redis=redis,
            whole=lambda: build_subject_augmentation(
                user_content,
                settings,
                math_user_content=math_user_content,
                prior_user_messages=prior_user_messages,
                response_intent_text=response_intent_text,
                detected_subject=detected_subject,
                redis=redis,
                pair=False,
            ),
        )
    if pair and not has_image_attachment:
        paired = await _paired_direct_reply(
            user_content,
            settings,
            redis=redis,
        )
        if paired is not None:
            return SubjectAugmentation(None, None, None, direct_text=paired)
    math_text = math_user_content or user_content
    subject = detected_subject or await read_subject(
        user_content,
        settings,
        has_image_attachment=has_image_attachment,
        image_math_extract=image_math_extract,
    )
    if subject is None:
        return SubjectAugmentation(None, None, None)
    request = SubjectRequest(
        text=user_content,
        math_text=math_text,
        has_image_attachment=has_image_attachment,
        image_math_extract=image_math_extract,
        prior_user_messages=prior_user_messages,
        response_intent_text=response_intent_text,
        redis=redis,
    )
    return await subject_adapter(subject).solve(request, settings)


async def _paired_direct_reply(
    user_content: str,
    settings: Settings,
    *,
    redis: Redis | None,
) -> str | None:
    parts = [part.strip().rstrip(".").strip() for part in _AND_ALSO.split(user_content)]
    parts = [part for part in parts if part]
    if len(parts) != 2:
        return None
    replies: list[str] = []
    for part in parts:
        piece = await build_subject_augmentation(part, settings, pair=False, redis=redis)
        reply = await read_direct_reply(piece.verified, part, settings)
        if reply is None:
            return None
        replies.append(reply.strip())
    # Each question worked and answered on its own, a hairline between them.
    return "\n\n---\n\n".join(replies)


async def _solve_parts(
    user_content: str,
    settings: Settings,
    parts: Sequence[str],
    *,
    answer_all: bool,
    redis: Redis | None,
    whole: Callable[[], Awaitable[SubjectAugmentation]],
) -> SubjectAugmentation:
    """Each question solved on its own (``build_subject_augmentation``'s ``parts``)."""
    pieces = [
        await build_subject_augmentation(part, settings, pair=False, redis=redis) for part in parts
    ]
    if answer_all:
        replies = [
            await read_direct_reply(piece.verified, part, settings)
            for piece, part in zip(pieces, parts, strict=True)
        ]
        blocks = tuple(piece.verified for piece in pieces if piece.verified is not None)
        if all(reply is not None for reply in replies) and len(blocks) == len(pieces):
            # The first part's block stands for the turn's verified solve (the trace); the
            # reply holds every part's own card, which the fence check holds to its part.
            first = pieces[0]
            return SubjectAugmentation(
                first.subject,
                first.prompt_block,
                replace(blocks[0], question_parts=blocks),
                direct_text=_in_parts(parts, [r or "" for r in replies]),
            )
    verified = next((piece for piece in pieces if piece.verified is not None), None)
    found = await whole()
    if found.verified is not None or verified is None:
        return found
    return verified


def _in_parts(parts: Sequence[str], replies: Sequence[str]) -> str:
    """The question in parts, in the one layout every worked answer in parts has
    (``services/worked_parts``): the givens and what is asked once, then each part's
    working closed by its own answer card. A reply in another shape keeps the old one:
    each part's own question, then its reply."""
    shared = _shared_setup(parts)
    laid_out = parts_in_one_layout([part[len(shared) :] for part in parts], replies)
    if laid_out is not None:
        return laid_out
    sections = []
    for index, (part, reply) in enumerate(zip(parts, replies, strict=True)):
        label = chr(ord("a") + index) if index < 26 else str(index + 1)
        # A question in parts letters each answer: "**Answer (a)**".
        answer = _ANSWER_LABEL.sub(f"**Answer ({label})**", reply.strip(), count=1)
        sections.append(f"**({label}) {part[len(shared) :].strip()}**\n\n{answer}")
    return "\n\n---\n\n".join(sections)


def _shared_setup(parts: Sequence[str]) -> str:
    """The setup every part opens with, up to the end of its last sentence."""
    first = parts[0]
    size = min(len(part) for part in parts)
    same = next((i for i in range(size) if any(part[i] != first[i] for part in parts)), size)
    prefix = first[:same]
    end = max(prefix.rfind(". "), prefix.rfind("? "), prefix.rfind("! "))
    return prefix[: end + 2] if end >= 0 else ""


async def read_direct_reply(
    verified: VerifiedSolveBlock | None,
    user_text: str,
    settings: Settings,
    *,
    has_image_attachment: bool = False,
    verified_request_text: str | None = None,
) -> str | None:
    """``maybe_direct_subject_reply`` off the event loop: its checks parse with SymPy."""
    if verified is None:
        return None
    return await read_off_loop(
        maybe_direct_subject_reply,
        verified,
        user_text,
        has_image_attachment=has_image_attachment,
        verified_request_text=verified_request_text,
        timeout=settings.stem_solve_timeout_seconds,
    )


def maybe_direct_subject_reply(
    verified: VerifiedSolveBlock | None,
    user_text: str,
    *,
    has_image_attachment: bool = False,
    verified_request_text: str | None = None,
) -> str | None:
    if verified is None:
        return None
    return subject_adapter(verified.subject).direct_reply(
        verified,
        user_text,
        has_image_attachment=has_image_attachment,
        verified_request_text=verified_request_text,
    )
