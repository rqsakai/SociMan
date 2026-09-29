"""Armazenamento de objetos no MinIO (research.md R4 da 003; R5 da 004).

Um MinIO só, com os dados no HD, e um bucket por tipo: `imagens` (o único que o imgproxy lê),
`fontes` e `videos`. Toda escrita confere antes o HD (`datadir.ensure_writable`). Objetos nunca
são apagados (FR-010 da 003, FR-016 da 004), por isso este módulo não tem função de delete de
propósito.
"""

import io
import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Literal

from minio import Minio
from minio.datatypes import Object

from sociman_api import datadir
from sociman_api.config import get_settings

Bucket = Literal["imagens", "fontes", "videos"]

PART_SIZE = 16 * 1024 * 1024
CHUNK = 64 * 1024


@lru_cache
def get_client() -> Minio:
    s = get_settings()
    return Minio(s.s3_endpoint, access_key=s.s3_access_key, secret_key=s.s3_secret_key,
                 secure=s.s3_secure)


def bucket_name(bucket: Bucket) -> str:
    s = get_settings()
    return {"imagens": s.s3_bucket, "fontes": s.s3_fonts_bucket,
            "videos": s.s3_videos_bucket}[bucket]


def ensure_bucket(name: str) -> None:
    client = get_client()
    if not client.bucket_exists(name):
        client.make_bucket(name)


def ensure_buckets() -> None:
    for bucket in ("imagens", "fontes", "videos"):
        ensure_bucket(bucket_name(bucket))


def put(key: str, data: bytes, content_type: str, *, bucket: Bucket = "imagens") -> None:
    datadir.ensure_writable(len(data))
    get_client().put_object(bucket_name(bucket), key, io.BytesIO(data), len(data),
                            content_type=content_type)


def put_file(key: str, path: str | os.PathLike, content_type: str, *,
             bucket: Bucket = "imagens") -> int:
    """Envia um arquivo do disco em partes (multipart), sem lê-lo inteiro. Devolve os bytes."""
    size = os.path.getsize(path)
    datadir.ensure_writable(size)
    get_client().fput_object(bucket_name(bucket), key, os.fspath(path),
                             content_type=content_type, part_size=PART_SIZE)
    return size


def get(key: str, *, bucket: Bucket = "imagens") -> bytes:
    resp = get_client().get_object(bucket_name(bucket), key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def get_to_file(key: str, path: str | os.PathLike, *, bucket: Bucket = "imagens") -> None:
    """Baixa o objeto para `path` (quem chama escolhe a pasta, em `work/` no HD)."""
    get_client().fget_object(bucket_name(bucket), key, os.fspath(path))


def stat(key: str, *, bucket: Bucket = "imagens") -> Object:
    return get_client().stat_object(bucket_name(bucket), key)


def get_range(key: str, offset: int, length: int, *, bucket: Bucket = "imagens"
              ) -> Iterator[bytes]:
    """Lê `length` bytes a partir de `offset`, em pedaços. A requisição ao MinIO é feita já
    (erros como objeto inexistente saem aqui, não no meio da resposta); a conexão é liberada
    quando o iterador termina ou é fechado."""
    resp = get_client().get_object(bucket_name(bucket), key, offset=offset, length=length)

    def _chunks() -> Iterator[bytes]:
        try:
            yield from resp.stream(CHUNK)
        finally:
            resp.close()
            resp.release_conn()

    return _chunks()
