from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.attachment_limits import MAX_ATTACHMENT_SIZE
from app.models.schemas.text import UserText
from app.modules.attachments.models import ORIGINAL_FILENAME_MAX_CHARS


class AttachmentPresignIn(BaseModel):
    content_type: str = Field(min_length=3, max_length=128)
    size_bytes: int = Field(gt=0, le=MAX_ATTACHMENT_SIZE)
    filename: UserText | None = Field(default=None, max_length=ORIGINAL_FILENAME_MAX_CHARS)


class AttachmentPresignOut(BaseModel):
    attachment_id: UUID
    upload_url: str
    storage_key: str
    headers: dict[str, str] = Field(default_factory=dict)
    api_upload: bool = False


class AttachmentOut(BaseModel):
    id: UUID
    content_type: str
    size_bytes: int
    download_url: str
    created_at: datetime
    indexed: bool = True
    # The name it was uploaded with; the stored message only links the file.
    original_filename: str | None = None


class AttachmentListItemOut(BaseModel):
    id: UUID
    content_type: str
    size_bytes: int
    download_url: str
    source: str
    created_at: datetime
    chat_id: UUID | None = None
    message_id: UUID | None = None
    original_filename: str | None = None
    chat_title: str | None = None
