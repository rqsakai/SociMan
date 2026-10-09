"""Desempenho das listas do AI Studio (spec 029, T037, SC-006): com 5 mil assets em 3 perfis e mais
os sem perfil, a lista da agência responde em menos de 1 s sem filtro, com `perfilId=sem` e com
um perfil."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import time
import uuid

from integration.estudio_helpers import listar, perfil, semear_biblioteca
from integration.geracao_helpers import _buckets, owner  # noqa: F401 (fixtures)

LIMITE_S = 1.0


def test_lista_da_agencia_com_5_mil(client, owner, db):
    h = owner[1]
    perfis = [uuid.UUID(perfil(client, h, f"perfil-{i}")) for i in range(3)]
    semear_biblioteca(db, 5000, [*perfis, None])
    listar(client, h, "assets", tipo="imagem")  # aquece a conexão e o plano
    for filtros in ({}, {"perfilId": "sem"}, {"perfilId": str(perfis[0])}):
        inicio = time.perf_counter()
        pagina = listar(client, h, "assets", tipo=["imagem", "sticker", "marca_dagua", "fundo"],
                        **filtros)
        gasto = time.perf_counter() - inicio
        assert len(pagina["items"]) == 48 and pagina["nextCursor"]
        assert gasto < LIMITE_S, (filtros, gasto)
        # A segunda página pelo cursor também.
        inicio = time.perf_counter()
        listar(client, h, "assets", tipo="imagem", cursor=pagina["nextCursor"], **filtros)
        assert time.perf_counter() - inicio < LIMITE_S
