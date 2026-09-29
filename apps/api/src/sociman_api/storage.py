"""Armazenamento de objetos no MinIO (research.md R4).

O bucket é privado; só o imgproxy o lê. Objetos nunca são apagados (FR-010), por isso este
módulo não tem função de delete de propósito.
"""

import io
from functools import lru_cache

from minio import Minio

from sociman_api.config import get_settings


@lru_cache
def get_client() -> Minio:
    s = get_settings()
    return Minio(s.s3_endpoint, access_key=s.s3_access_key, secret_key=s.s3_secret_key,
                 secure=s.s3_secure)


def ensure_bucket(name: str) -> None:
    client = get_client()
    if not client.bucket_exists(name):
        client.make_bucket(name)


def put(key: str, data: bytes, content_type: str) -> None:
    get_client().put_object(get_settings().s3_bucket, key, io.BytesIO(data), len(data),
                            content_type=content_type)


def get(key: str) -> bytes:
    resp = get_client().get_object(get_settings().s3_bucket, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()
