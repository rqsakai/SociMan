"""Clipes prontos (spec 013, US6, T042, Q2): linha + vídeo → conteúdo `video_proprio` sem destino,
com o título do registro e a anotação da origem; dedup pelo SHA-256; linha sem vídeo, vídeo sem
linha e vídeo inválido ficam fora; o total de bytes entra na conferência do HD."""

from sqlalchemy import select

from integration.agencia_helpers import (  # noqa: F401
    _buckets,
    agencia,
    confirmar,
    dono,
    importar,
    itens,
    previa,
    um,
    yt,
)
from sociman_api import datadir
from sociman_api.anotacoes.models import Anotacao, AnotacaoAlvo
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.postagem.models import Postagem


def test_clipes_viram_conteudos_sem_destino(client, db, dono, agencia, yt, s3, monkeypatch):  # noqa: F811
    _, h = dono
    agencia.perfil()
    agencia.registro("taverna-teste", "taverna-teste-1", "taverna-teste-2", "taverna-teste-3")
    v1 = agencia.clipe("taverna-teste", "taverna-teste-1", cor="0x101010")
    agencia.clipe("taverna-teste", "taverna-teste-2", cor="0x202020")
    agencia.clipe("taverna-teste", "taverna-teste-9", cor="0x303030")  # sem linha
    agencia.clipe("taverna-teste", "taverna-teste-3", valido=False)
    agencia.clipe("taverna-teste", "x", data="sem-data", cor="0x404040")

    p = previa(client, h)

    clipes = {i["origem"]["trecho"]: i for i in itens(p, "clipe")}
    assert clipes["taverna-teste-1"]["situacao"] == "novo"
    assert clipes["taverna-teste-1"]["proposto"]["titulo"] == "Título do taverna-teste-1"
    assert clipes["taverna-teste-1"]["bytes"] == v1.stat().st_size
    assert clipes["taverna-teste-9"]["motivo"] == "video_sem_linha"
    assert clipes["taverna-teste-3"]["motivo"] == "video_invalido"
    assert clipes["x"]["motivo"] == "caminho_de_clipe"
    assert p["bytesNovos"] >= v1.stat().st_size

    pedidos = []
    original = datadir.ensure_writable
    monkeypatch.setattr(datadir, "ensure_writable",
                        lambda n=0, *a, **k: (pedidos.append(n), original(n, *a, **k))[1])
    imp = confirmar(client, h, p)

    assert pedidos and pedidos[0] >= v1.stat().st_size  # o total da importação
    conteudos = db.scalars(select(Conteudo)).all()
    assert len(conteudos) == 2
    assert {c.titulo for c in conteudos} == {"Título do taverna-teste-1",
                                             "Título do taverna-teste-2"}
    assert all(c.origem == ConteudoOrigem.video_proprio for c in conteudos)
    assert db.scalar(select(Postagem.id)) is None  # sem destino
    notas = db.scalars(select(Anotacao).where(Anotacao.alvo_tipo == AnotacaoAlvo.conteudo)).all()
    assert len(notas) == 2
    assert any("registro-clipes.md · taverna-teste-1 · 2026-09-25 · Fonte: https://" in n.texto
               for n in notas)
    assert imp["contagens"]["naoGravado"] == 0
    p2 = previa(client, h)
    assert {i["origem"]["trecho"]: i["situacao"] for i in itens(p2, "clipe")}[
        "taverna-teste-1"] == "igual"


def test_linha_sem_video(client, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil()
    agencia.registro("taverna-teste", "taverna-teste-5")
    p = previa(client, h)
    c = um(p, "clipe")
    assert (c["situacao"], c["motivo"]) == ("fora", "linha_sem_video")
    assert c["origem"]["arquivo"] == "shared:perfis/taverna-teste/registro-clipes.md"
