from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.client_disconnect import ClientLeft, until_client_leaves
from app.core.config import Settings
from app.core.consent import get_consented_user
from app.core.deps import get_settings_dep
from app.core.log_context import bound_log_ids
from app.core.rate_limit import allow_request_unless_down
from app.core.redis import get_redis_client
from app.exceptions import RateLimitedError
from app.models.orm import User
from app.models.schemas.chats import MessageOut
from app.modules.account import profile as profile_service
from app.modules.images import generation as image_generation_service
from app.modules.images import intent as image_intent_service
from app.modules.images.schemas import (
    ImageGenerateIn,
    ImageGenerateOut,
    ImageIntentIn,
    ImageIntentOut,
)

ImageGenerateOut.model_rebuild(_types_namespace={"MessageOut": MessageOut})

router = APIRouter(prefix="/images", tags=["images"])


# nginx's "client closed request": nobody is there to read it.
_CLIENT_CLOSED = 499
# Composer asks a user may make a minute. Each reads the text in the SymPy pool, which
# chat turns share: only the global REST limit (240 a minute) bounded it. The phone asks
# only before a send that might be a picture and reads any failure as a plain send.
INTENT_ASKS_PER_MINUTE = 30
_INTENT_WINDOW_SECONDS = 60


@router.post("/generate", response_model=ImageGenerateOut)
async def generate_image(
    body: ImageGenerateIn,
    request: Request,
    user: User = Depends(get_consented_user),
    settings: Settings = Depends(get_settings_dep),
) -> ImageGenerateOut | Response:
    """A picture for the chat. The phone's Cancel closes the request: the provider call
    stops and nothing is stored (until_client_leaves). The day's slot comes back only
    when the provider was not yet asked: a call cut short may still be billed."""
    original = (body.user_message or "").strip() or None
    work = image_generation_service.generate_for_chat(
        settings,
        user=user,
        chat_id=body.chat_id,
        prompt=body.prompt,
        aspect_ratio=body.aspect_ratio,
        user_message_content=original,
        reference_attachment_ids=body.reference_attachment_ids,
    )
    try:
        user_message, assistant_message = await until_client_leaves(request, work)
    except ClientLeft:
        return Response(status_code=_CLIENT_CLOSED)

    return ImageGenerateOut(
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
    )


@router.post("/intent", response_model=ImageIntentOut)
async def image_intent(
    body: ImageIntentIn,
    user: User = Depends(get_consented_user),
    settings: Settings = Depends(get_settings_dep),
) -> ImageIntentOut:
    """How the phone's composer sends a turn: a photo lookup, a picture, or chat.

    The phone reads no image intent itself; it asks here before a send that might
    be a picture, and this answers with the chat turn's own reading of the text and
    the chat's recent turns. A chat that is not the user's is not found.

    Limited per user (``INTENT_ASKS_PER_MINUTE``), and its pool read runs under the
    user's id, so one user's asks take one pool slot at a time (``core/sympy_executor``).
    """
    if not await allow_request_unless_down(
        get_redis_client(),
        f"rate:images:intent:{user.id}",
        limit=INTENT_ASKS_PER_MINUTE,
        window_seconds=_INTENT_WINDOW_SECONDS,
    ):
        raise RateLimitedError(
            "Too many requests. Try again shortly.", retry_after_seconds=_INTENT_WINDOW_SECONDS
        )
    with bound_log_ids(user_id=user.id):
        verdict = await image_intent_service.composer_intent_for_chat(
            profile_service.settings_for_user(settings, user),
            user_id=user.id,
            text=body.text,
            chat_id=body.chat_id,
            image_attached=body.image_attached,
        )
    if verdict is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    request = verdict.request
    return ImageIntentOut(
        subject=verdict.subject,
        lookup_query=verdict.lookup_query,
        generate_prompt=request.prompt if request else None,
        revision=bool(request and request.revision),
        reference_attachment_ids=list(request.reference_ids) if request else [],
    )
