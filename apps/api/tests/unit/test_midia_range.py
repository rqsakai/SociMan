"""`Range` e `Content-Disposition` do streaming de mídia (T010, R6)."""

import pytest

from sociman_api import midia
from sociman_api.errors import ApiError


@pytest.mark.parametrize(("header", "size", "expected"), [
    (None, 100, None),
    ("", 100, None),
    ("bytes=0-9", 100, (0, 9)),
    ("bytes=90-", 100, (90, 99)),
    ("bytes=-10", 100, (90, 99)),
    ("bytes=-1000", 100, (0, 99)),
    ("bytes=10-1000", 100, (10, 99)),
    ("bytes=99-99", 100, (99, 99)),
    (" bytes = 0 - 1 ", 100, (0, 1)),
    ("bytes=0-1,4-5", 100, None),  # várias faixas: ignora
    ("items=0-1", 100, None),
    ("bytes=5-1", 100, None),
    ("bytes=-", 100, None),
    ("bytes=a-b", 100, None),
])
def test_parse_range(header, size, expected):
    got = midia.parse_range(header, size)
    assert (None if got is None else (got.start, got.end)) == expected


@pytest.mark.parametrize(("header", "size"), [
    ("bytes=100-", 100), ("bytes=500-600", 100), ("bytes=-0", 100), ("bytes=0-", 0),
    ("bytes=-5", 0),
])
def test_parse_range_416(header, size):
    with pytest.raises(ApiError) as exc:
        midia.parse_range(header, size)
    assert exc.value.status == 416
    assert exc.value.headers == {"Content-Range": f"bytes */{size}"}


def test_content_disposition():
    assert midia.content_disposition("a-b.mp4") == (
        "attachment; filename=\"a-b.mp4\"; filename*=UTF-8''a-b.mp4")
    header = midia.content_disposition('Fonte "Ção"/x.ttf')
    assert header.startswith('attachment; filename="Fonte _Cao__x.ttf"; ')
    assert header.endswith("filename*=UTF-8''Fonte%20%22%C3%87%C3%A3o%22%2Fx.ttf")
