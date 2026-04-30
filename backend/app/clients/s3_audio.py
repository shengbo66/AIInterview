"""Async S3 audio client: upload + presigned GET URL + delete."""
import asyncio
import contextlib

import boto3
from botocore.exceptions import ClientError

from app.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("s3", region_name=settings.aws_region)
    return _client


def _upload_sync(key: str, data: bytes, content_type: str) -> None:
    _get_client().put_object(
        Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
    )


def _presign_sync(key: str, expires: int) -> str:
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires,
    )


def _delete_sync(keys: list[str]) -> None:
    if not keys:
        return
    # batch delete up to 1000 per request
    for i in range(0, len(keys), 1000):
        chunk = keys[i : i + 1000]
        _get_client().delete_objects(
            Bucket=settings.s3_bucket,
            Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
        )


async def upload(key: str, data: bytes, content_type: str = "audio/webm") -> str:
    """Upload bytes to S3. Retries 3x on transient errors. Returns the key."""
    last_err = None
    for attempt in range(3):
        try:
            await asyncio.to_thread(_upload_sync, key, data, content_type)
            return key
        except ClientError as e:
            last_err = e
            if attempt < 2:
                await asyncio.sleep(2**attempt)
    raise RuntimeError(f"S3 upload failed after 3 retries: {last_err}")


async def presign_get(key: str, expires: int | None = None) -> str:
    """Generate a presigned GET URL for an S3 key."""
    ttl = expires or settings.presigned_url_ttl_sec
    return await asyncio.to_thread(_presign_sync, key, ttl)


async def delete_many(keys: list[str]) -> None:
    """Best-effort batch delete. Swallows ClientError to avoid blocking cascade."""
    with contextlib.suppress(ClientError):
        await asyncio.to_thread(_delete_sync, keys)
