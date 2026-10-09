"""Fixture `s3`: bucket de teste real no MinIO, isolado do bucket de dev."""

import io

from sociman_api.config import get_settings


def test_s3_fixture_uses_empty_test_bucket(s3):
    assert s3.name == get_settings().s3_bucket != "sociman"
    assert s3.keys() == []
    s3.client.put_object(s3.name, "perfis/x/a.png", io.BytesIO(b"abc"), 3)
    assert s3.keys() == ["perfis/x/a.png"]
    s3.empty()
    assert s3.keys() == []
