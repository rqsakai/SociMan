"""Apoio dos testes da spec 026: dono e membro, cliente de coleta pela API e a coleta ligada
(aceite + botão + `.env` por override). O coletor falso fica em `tests/fakes/coletor_fake.py`."""

import pytest
from fakes.coletor_fake import ColetorFake, bearer, criar_cliente_coleta, ligar_coleta

from integration.postagem_helpers import dono, membro

__all__ = ["ColetorFake", "bearer", "coletor", "criar_cliente_coleta", "dono", "ligado",
           "ligar_coleta", "membro"]


@pytest.fixture
def ligado(client, dono, coleta_habilitada):
    """A coleta ligada nos dois níveis, com o aceite de risco; devolve os headers do dono."""
    _, h = dono
    ligar_coleta(client, h, coleta_habilitada)
    return h


@pytest.fixture
def coletor(client, ligado):
    """Um cliente de coleta com token real e o `ColetorFake` pronto."""
    _, token = criar_cliente_coleta(client, ligado)
    return ColetorFake(client, token)
