"""Idempotência (spec 013, US2, T025, SC-002): importar a pasta completa duas vezes não cria
entidade, versão nem objeto no MinIO na 2ª vez; uma linha nova no `fontes.md` é o único `novo`."""

from sqlalchemy import func, select, text

from integration.agencia_helpers import (  # noqa: F401
    UC,
    UC2,
    _buckets,
    agencia,
    dono,
    importar,
    itens,
    jpg,
    png,
    previa,
    yt,
)
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion

TABELAS = ("perfis", "contas", "canais_fonte", "canal_perfis", "assets", "asset_files", "images",
           "anotacoes", "ia_guias", "conteudos")


def _contagens(s3) -> dict:
    with get_engine().connect() as conn:
        out = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABELAS}
    out["objetos"] = len(s3.keys())
    return out


def _pasta(agencia, yt):  # noqa: F811
    yt.add_canal(UC, "Canal Um", handle="canalum")
    agencia.perfil()
    agencia.fontes("taverna-teste",
                   ("Canal Um", "youtube.com/@canalum", "`programa-de-cortes`",
                    "https://exemplo.com/regras", "48h", "dono", "2026-09-24"))
    agencia.pesquisa("taverna-teste", {"1. Termos de busca": "- PT: rpg",
                                       "2. Hashtags": "#rpg #dnd"})
    agencia.escrever("perfis/taverna-teste/assets/logo.png", png((90, 60, 30, 255), (300, 300)))
    agencia.escrever("perfis/taverna-teste/assets/foto-perfil.jpg", jpg())
    agencia.escrever("perfis/taverna-teste/assets/avatar-poses/avatar-1-rpg.jpg",
                     jpg((10, 10, 10)))
    agencia.registro("taverna-teste", "taverna-teste-1")
    agencia.clipe("taverna-teste", "taverna-teste-1")


def test_segunda_importacao_nao_grava_nada(client, db, dono, agencia, yt, s3):  # noqa: F811
    _, h = dono
    _pasta(agencia, yt)
    _, imp1 = importar(client, h)
    assert imp1["contagens"]["criado"] > 5, imp1["contagens"]
    assert not [i for i in imp1["itens"] if i["resultado"] == "nao_gravado"], [
        (i["tipo"], i["resultadoMotivo"]) for i in imp1["itens"] if i["resultado"] == "nao_gravado"]
    antes = _contagens(s3)
    versoes = db.scalar(select(func.count()).select_from(EntityVersion).where(
        EntityVersion.entity_type != "importacao_agencia"))

    p2, imp2 = importar(client, h)

    assert p2["contagens"]["novo"] == 0 and p2["contagens"]["diverge"] == 0, [
        (i["tipo"], i["situacao"], i["origem"]) for i in p2["itens"]
        if i["situacao"] in ("novo", "diverge")]
    assert imp2["contagens"]["criado"] == imp2["contagens"]["atualizado"] == 0
    assert _contagens(s3) == antes
    assert db.scalar(select(func.count()).select_from(EntityVersion).where(
        EntityVersion.entity_type != "importacao_agencia")) == versoes


def test_linha_nova_no_fontes_e_o_unico_novo(client, dono, agencia, yt, s3):  # noqa: F811
    _, h = dono
    _pasta(agencia, yt)
    importar(client, h)
    yt.add_canal(UC2, "Canal Dois", handle="canaldois")
    agencia.fontes("taverna-teste",
                   ("Canal Um", "youtube.com/@canalum", "`programa-de-cortes`",
                    "https://exemplo.com/regras", "48h", "dono", "2026-09-24"),
                   ("Canal Dois", "youtube.com/@canaldois", "`autorizado`", "", "", "dono",
                    "2026-10-01"))

    p = previa(client, h)

    novos = itens(p, situacao="novo")
    assert [(i["tipo"], i["origem"]["trecho"]) for i in novos] == [("canal", "Canal Dois")]
