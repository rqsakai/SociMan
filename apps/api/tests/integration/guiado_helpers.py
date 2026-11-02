"""Helpers do wizard do vídeo guiado (spec 031, US3): um roteiro guiado montado à mão em
`aguardando_texto` (uma posição por item de `trechos`, cada uma com a sua cena e a sequência de
quadros vazia), as linhas do gerador e as ações novas (aprovar por posição, recusar)."""

import uuid

from sqlalchemy import select

from integration.padrao_helpers import cenario_com_cena
from integration.roteiro_helpers import (
    acao,
    aprovar,
    criar_roteiro,
    montar,
    rodar_ate,
    ver_roteiro,
)
from sociman_api.auth.deps import Actor
from sociman_api.cenas import quadros
from sociman_api.cenas.models import Cena
from sociman_api.geracao.models import Geracao
from sociman_api.roteiros import grade
from sociman_api.roteiros.estado import S
from sociman_api.roteiros.models import (
    ConversaEstado,
    PosicaoReuso,
    Roteiro,
    RoteiroCena,
    RoteiroTipoVideo,
)

FRASES = ["Gente, olha o caimento!", "Corre no link!", "Tem bolso também!"]


def guiado(client, h, m, db, dono, trechos: list[int]) -> tuple[dict, dict, list[uuid.UUID]]:
    """(blocos, roteiro, ids das cenas por posição): base de 5 s, uma frase por posição."""
    b = montar(client, h, m, n_cenas=len(trechos))
    b["cenario"] = cenario_com_cena(client, h, m, b["perfil_id"])
    rot = criar_roteiro(client, h, b)
    r = db.get(Roteiro, uuid.UUID(rot["id"]))
    r.tipo_video = RoteiroTipoVideo.avatar_pov
    r.cenario_id = uuid.UUID(b["cenario"]["id"])
    r.duracao_alvo_s, r.trecho_base_s = sum(trechos) * 5, 5
    r.conversa_estado = ConversaEstado.respondida
    r.frases = FRASES[:len(trechos)]
    ator = Actor(kind="user", user_id=dono.id)
    cenas = []
    for i, n in enumerate(trechos):
        cena_id = uuid.UUID(b["cenas"][i]["id"])
        r.posicoes_rel.append(RoteiroCena(roteiro_id=r.id, ordem=i, cena_id=cena_id, frases=[i],
                                          trechos=n, reuso=PosicaoReuso.nova,
                                          orcamento_chars=grade.orcamento_chars(n * 5)))
        quadros.criar(db, ator, db.get(Cena, cena_id),
                      [f"She holds the dress, state {k}" for k in range(n + 1)])
        cenas.append(cena_id)
    r.status = S.aguardando_texto
    r.comandado_por = dono.id
    db.commit()
    return b, ver_roteiro(client, h, rot["id"]), cenas


def ate_narracao(client, h, m, rot: dict) -> dict:
    rot = aprovar(client, h, rot, "texto")
    return rodar_ate(client, h, m, rot["id"], "aguardando_narracao")


def ate_quadros(client, h, m, rot: dict) -> dict:
    """Aprova a narração e roda a cadeia até o portão de keyframes."""
    rot = aprovar(client, h, ate_narracao(client, h, m, rot), "narracao")
    return rodar_ate(client, h, m, rot["id"], "aguardando_keyframes")


def ativos(db, cena_id):
    db.expire_all()
    return quadros.ativos(db, cena_id)


def geracoes(db, passo: str, alvo_id) -> list[Geracao]:
    db.expire_all()
    return list(db.scalars(select(Geracao).where(Geracao.passo == passo,
                                                 Geracao.alvo_id == alvo_id)
                           .order_by(Geracao.created_at, Geracao.id)))


def aprovar_posicao(client, h, rot: dict, ordem: int, etapa: str = "keyframes",
                    status: int = 200) -> dict:
    r = client.post(f"/api/roteiros/{rot['id']}/posicoes/{ordem}/aprovar", headers=h,
                    json={"version": rot["version"], "etapa": etapa})
    assert r.status_code == status, r.text
    return r.json()


def recusar(client, h, rot: dict, alvo: dict, status: int = 200, opcoes: list[str] | None = None,
            texto: str | None = None) -> dict:
    corpo = {"version": rot["version"], "alvo": alvo, "opcoes": opcoes or []}
    if texto is not None:
        corpo["texto"] = texto
    return acao(client, h, rot, "recusar", status, **{k: v for k, v in corpo.items()
                                                       if k != "version"})


def versoes(client, h, rot: dict) -> list[dict]:
    r = client.get(f"/api/roteiros/{rot['id']}/versoes", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]
