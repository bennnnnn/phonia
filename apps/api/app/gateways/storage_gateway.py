"""Storage gateway abstraction — swap R2/S3/local via config.

``local`` writes to disk (dev). ``r2`` presigns Cloudflare R2 (S3-compatible)
upload/download URLs so the mobile client talks to object storage directly —
blobs never stream through the API, and storage credentials stay server-side.
The client gets a short-lived signed PUT URL at presign time and a signed GET
URL on download. ``api_upload`` tells the client whether to PUT to the API
(local) or directly to the presigned URL (R2).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.blocking import run_blocking
from app.core.config import Settings

logger = logging.getLogger(__name__)


class StorageUnavailableError(RuntimeError):
    """Storage could not complete a request; this does not mean an object is missing."""


_R2_UNAVAILABLE = "Attachment storage is temporarily unavailable"


@dataclass(frozen=True)
class PresignedUpload:
    attachment_id: str
    upload_url: str
    storage_key: str
    headers: dict[str, str]
    api_upload: bool = False


class StorageGateway(Protocol):
    async def presign_upload(
        self, *, user_id: str, content_type: str, size_bytes: int
    ) -> PresignedUpload: ...

    async def presign_download(self, storage_key: str) -> str: ...

    async def write_bytes(self, storage_key: str, data: bytes) -> None: ...

    async def copy_bytes(self, source_key: str, target_key: str) -> bool:
        """Copy inside storage, bytes never through the API. False when the source is gone."""
        ...

    async def read_bytes(self, storage_key: str) -> bytes | None: ...

    async def delete_bytes(self, storage_key: str) -> None: ...

    async def delete_prefix(self, prefix: str) -> int: ...

    def resolve_local_path(self, storage_key: str) -> Path | None: ...


class LocalStorageGateway:
    """Dev/test storage — files under STORAGE_LOCAL_PATH."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = Path(base_path).expanduser().resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path_under_base(self, storage_key: str) -> Path:
        """Resolve ``storage_key`` and reject path escape (``..`` / absolute)."""
        if not storage_key or storage_key.startswith("/") or ".." in Path(storage_key).parts:
            raise ValueError("Invalid storage key")
        path = (self.base_path / storage_key).resolve()
        if not path.is_relative_to(self.base_path):
            raise ValueError("Invalid storage key")
        return path

    async def presign_upload(
        self, *, user_id: str, content_type: str, size_bytes: int
    ) -> PresignedUpload:
        attachment_id = str(uuid.uuid4())
        storage_key = f"{user_id}/{attachment_id}"
        return PresignedUpload(
            attachment_id=attachment_id,
            upload_url=f"/attachments/{attachment_id}/upload",
            storage_key=storage_key,
            headers={"Content-Type": content_type, "Content-Length": str(size_bytes)},
            api_upload=True,
        )

    async def presign_download(self, storage_key: str) -> str:
        return f"file://{self._path_under_base(storage_key)}"

    async def write_bytes(self, storage_key: str, data: bytes) -> None:
        path = self.local_path(storage_key)
        path.write_bytes(data)

    async def copy_bytes(self, source_key: str, target_key: str) -> bool:
        import shutil

        source = self.resolve_local_path(source_key)
        if source is None:
            return False
        shutil.copyfile(source, self.local_path(target_key))
        return True

    async def read_bytes(self, storage_key: str) -> bytes | None:
        path = self.resolve_local_path(storage_key)
        return path.read_bytes() if path is not None else None

    async def delete_bytes(self, storage_key: str) -> None:
        try:
            path = self._path_under_base(storage_key)
        except ValueError:
            return
        try:
            path.unlink(missing_ok=True)
        except IsADirectoryError:
            pass

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object under ``prefix`` (account-wipe residual sweep)."""
        if not prefix or prefix.startswith("/") or ".." in Path(prefix).parts:
            return 0
        root = (self.base_path / prefix).resolve()
        if not root.is_relative_to(self.base_path) or not root.exists():
            return 0
        if root.is_file():
            root.unlink(missing_ok=True)
            return 1
        deleted = sum(1 for path in root.rglob("*") if path.is_file())
        shutil.rmtree(root)
        return deleted

    def resolve_local_path(self, storage_key: str) -> Path | None:
        try:
            path = self._path_under_base(storage_key)
        except ValueError:
            return None
        return path if path.is_file() else None

    def local_path(self, storage_key: str) -> Path:
        path = self._path_under_base(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class R2StorageGateway:
    """Cloudflare R2 (S3-compatible) — presigned PUT/GET URLs, no blob I/O here.

    boto3's ``generate_presigned_url`` is an offline Signature V4 computation
    (no network call), so it's safe to run directly in the async path; we still
    offload to a thread to honour the async contract and keep boto3's brief
    import/construct cost off the event loop.
    """

    def __init__(self, settings: Settings) -> None:
        import boto3  # local import — keeps dev (no boto3 hot path) light
        from botocore.config import Config

        endpoint = settings.r2_endpoint or (
            f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        )
        self._bucket = settings.r2_bucket
        self._deadline = settings.r2_call_deadline_seconds
        self._expiry = settings.r2_presign_expiry_seconds
        self._upload_expiry = settings.r2_presign_upload_expiry_seconds
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name="auto",  # R2 ignores region but boto3 requires one
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            # Every call below runs on the storage pool (core/blocking.py). botocore's
            # defaults (60s + 60s, 5 legacy attempts) let a stalled R2 hold its
            # threads for minutes.
            config=Config(
                connect_timeout=settings.r2_connect_timeout_seconds,
                read_timeout=settings.r2_read_timeout_seconds,
                # total_max_attempts counts the first try (max_attempts would not).
                retries={
                    "total_max_attempts": max(1, settings.r2_max_attempts),
                    "mode": "standard",
                },
            ),
        )

    async def _call[T](self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """One R2 call on the storage pool, given up after the deadline."""
        async with asyncio.timeout(self._deadline):
            return await run_blocking("storage", fn, *args, **kwargs)

    async def presign_upload(
        self, *, user_id: str, content_type: str, size_bytes: int
    ) -> PresignedUpload:
        attachment_id = str(uuid.uuid4())
        storage_key = f"{user_id}/{attachment_id}"
        # R2/S3 presigned PUT — the client uploads directly; the signed URL
        # pins Content-Type so a swapped MIME can't be stored under this URL.
        url = await run_blocking(
            "storage",
            self._client.generate_presigned_url,
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": storage_key,
                "ContentType": content_type,
                "ContentLength": size_bytes,
            },
            ExpiresIn=self._upload_expiry,
        )
        return PresignedUpload(
            attachment_id=attachment_id,
            upload_url=url,
            storage_key=storage_key,
            # The client must send these exact headers for the signature to match.
            headers={"Content-Type": content_type, "Content-Length": str(size_bytes)},
            api_upload=False,
        )

    async def presign_download(self, storage_key: str) -> str:
        return await run_blocking(
            "storage",
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": storage_key},
            ExpiresIn=self._expiry,
        )

    async def write_bytes(self, storage_key: str, data: bytes) -> None:
        try:
            await self._call(
                self._client.put_object,
                Bucket=self._bucket,
                Key=storage_key,
                Body=data,
            )
        except Exception as exc:
            raise StorageUnavailableError(_R2_UNAVAILABLE) from exc

    async def copy_bytes(self, source_key: str, target_key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            await self._call(
                self._client.copy_object,
                Bucket=self._bucket,
                Key=target_key,
                CopySource={"Bucket": self._bucket, "Key": source_key},
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "NotFound", "404"}:
                return False
            raise StorageUnavailableError("Attachment storage is temporarily unavailable") from exc
        except Exception as exc:
            raise StorageUnavailableError("Attachment storage is temporarily unavailable") from exc
        return True

    async def read_bytes(self, storage_key: str) -> bytes | None:
        # Used by attachment_content to extract text/vision bytes for the prompt.
        from botocore.exceptions import ClientError

        try:
            resp = await self._call(self._client.get_object, Bucket=self._bucket, Key=storage_key)
            body = resp["Body"]
            try:
                return await self._call(body.read)
            finally:
                await self._call(body.close)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "NotFound", "404"}:
                return None
            raise StorageUnavailableError(_R2_UNAVAILABLE) from exc
        except Exception as exc:
            raise StorageUnavailableError(_R2_UNAVAILABLE) from exc

    async def delete_bytes(self, storage_key: str) -> None:
        try:
            await self._call(self._client.delete_object, Bucket=self._bucket, Key=storage_key)
        except Exception as exc:
            raise StorageUnavailableError(_R2_UNAVAILABLE) from exc

    async def delete_prefix(self, prefix: str) -> int:
        if not prefix or ".." in prefix or prefix.startswith("/"):
            return 0
        deleted = 0
        token: str | None = None
        while True:
            kwargs: dict[str, object] = {
                "Bucket": self._bucket,
                "Prefix": prefix,
                "MaxKeys": 1000,
            }
            if token:
                kwargs["ContinuationToken"] = token

            def _list_page(params: dict[str, object]) -> object:
                return self._client.list_objects_v2(**params)

            resp = await self._call(_list_page, kwargs)
            # Only a real listing continues the sweep. A reply that is not one, or
            # a page token that does not advance, would otherwise loop forever.
            if not isinstance(resp, dict):
                break
            contents = resp.get("Contents") or []
            keys = [
                obj["Key"]
                for obj in contents
                if isinstance(obj, dict) and isinstance(obj.get("Key"), str)
            ]
            if keys:
                deletion = await self._call(
                    self._client.delete_objects,
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
                )
                if deletion.get("Errors"):
                    raise StorageUnavailableError("Some attachment objects could not be deleted")
                deleted += len(keys)
            if not resp.get("IsTruncated"):
                break
            next_token = resp.get("NextContinuationToken")
            if not isinstance(next_token, str) or not next_token or next_token == token:
                break
            token = next_token
        return deleted

    def resolve_local_path(self, storage_key: str) -> Path | None:
        return None


class UnconfiguredStorageGateway:
    """Fail closed when production expects R2 but credentials are missing."""

    _msg = "Object storage is not configured"

    async def presign_upload(
        self, *, user_id: str, content_type: str, size_bytes: int
    ) -> PresignedUpload:
        raise StorageUnavailableError(self._msg)

    async def presign_download(self, storage_key: str) -> str:
        raise StorageUnavailableError(self._msg)

    async def write_bytes(self, storage_key: str, data: bytes) -> None:
        raise StorageUnavailableError(self._msg)

    async def copy_bytes(self, source_key: str, target_key: str) -> bool:
        raise StorageUnavailableError(self._msg)

    async def read_bytes(self, storage_key: str) -> bytes | None:
        raise StorageUnavailableError(self._msg)

    async def delete_bytes(self, storage_key: str) -> None:
        raise StorageUnavailableError(self._msg)

    async def delete_prefix(self, prefix: str) -> int:
        raise StorageUnavailableError(self._msg)

    def resolve_local_path(self, storage_key: str) -> Path | None:
        return None


def _r2_configured(settings: Settings) -> bool:
    return bool(
        settings.r2_account_id
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket
    )


_gateway_cache: tuple[tuple[object, ...], StorageGateway] | None = None


def get_storage_gateway(settings: Settings) -> StorageGateway:
    global _gateway_cache
    key = (
        settings.storage_backend.strip().lower(),
        settings.environment,
        settings.r2_account_id,
        settings.r2_access_key_id,
        settings.r2_secret_access_key,
        settings.r2_bucket,
        settings.r2_endpoint,
        settings.storage_local_path,
    )
    if _gateway_cache is not None and _gateway_cache[0] == key:
        return _gateway_cache[1]
    gateway = _build_storage_gateway(settings)
    _gateway_cache = (key, gateway)
    return gateway


def _build_storage_gateway(settings: Settings) -> StorageGateway:
    backend = settings.storage_backend.strip().lower()
    if backend == "r2":
        if _r2_configured(settings):
            return R2StorageGateway(settings)
        # Credentials not set yet. In dev, fall back to local so the app keeps
        # working; in production the attachment routes return 501 for non-local
        # backends, which is safer than silently storing to /tmp in prod.
        if settings.environment == "development":
            logger.warning(
                "STORAGE_BACKEND=r2 but R2 credentials are incomplete — "
                "falling back to local storage. Set r2_* secrets before production."
            )
            return LocalStorageGateway(Path(settings.storage_local_path))
        logger.error("R2 storage selected but credentials incomplete in production")
        return UnconfiguredStorageGateway()
    # default: local
    return LocalStorageGateway(Path(settings.storage_local_path))
