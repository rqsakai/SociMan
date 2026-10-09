"""Fixtures dos testes unitários: só Redis (banco de teste 15), sem Postgres."""

import os

import pytest
import redis


@pytest.fixture
def r():
    client = redis.Redis.from_url(os.environ["TEST_REDIS_URL"], decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()
