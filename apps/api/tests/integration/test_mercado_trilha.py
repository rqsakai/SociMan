"""T053 (US4): a trilha `mercado` com o coletor falso. Dois perfis; rankings da união das
categorias; a vitrine vale para ambos (`perfil_id` nulo); link manual entra no nível 1; produto fora
do ranking há 8 dias vira `morna` sem perder foto; 31 dias → `parada`; reaparece → `quente`;
relacionados até o limite com uma notificação por dia; reservas vencidas voltam; o dia anterior
expira; rodada sem batimento → `interrompida`; `coleta_parada` depois de 48 h; ociosa com
`COLETA_HABILITADA=false`; nada apagado (contagens antes e depois)."""

import uuid
from datetime import UTC, datetime, timedelta

from fakes.coletor_fake import SP
from sqlalchemy import func, select, text

from integration.coleta_helpers import (  # noqa: F401
    ColetorFake,
    coletor,
    dono,
    ligado,
    ligar_coleta,
)
from integration.postagem_helpers import criar_perfil
from sociman_api.mercado import trilha
from sociman_api.mercado.models import (
    Calor,
    Categoria,
    Coleta,
    ColetaEstado,
    FilaEstado,
    FotoProduto,
    Interesse,
    Loja,
    Produto,
    Tarefa,
)
from sociman_api.notificacoes.models import Notificacao

AGORA = datetime.now(UTC)
HOJE = AGORA.astimezone(SP).date()


def _contagens(db) -> dict[str, int]:
    return {t: db.scalar(select(func.count()).select_from(m)) or 0
            for t, m in (("fotos", FotoProduto), ("produtos", Produto), ("interesses", Interesse),
                         ("tarefas", Tarefa))}


def _fila_hoje(db, tipo: str | None = None) -> list[Tarefa]:
    stmt = select(Tarefa).where(Tarefa.estado == FilaEstado.pendente)
    if tipo:
        stmt = stmt.where(Tarefa.tipo == tipo)
    return list(db.scalars(stmt.order_by(Tarefa.nivel, Tarefa.prioridade)))


def _config(client, h, perfil_id: str, categoria_ids: list[str], version: int = 0) -> dict:
    r = client.put(f"/api/perfis/{perfil_id}/mercado/config", headers=h,
                   json={"version": version, "categoriaIds": categoria_ids,
                         "maxRelacionadosDia": 2, "avisarNovoEmAlta": True})
    assert r.status_code == 200, r.text
    return r.json()


def test_fila_do_dia_com_dois_perfis_rankings_vitrine_e_link_manual(client, db, ligado, coletor):  # noqa: F811
    p1 = criar_perfil(client, ligado, "Perfil A")
    p2 = criar_perfil(client, ligado, "Perfil B")
    # Semente: 3 produtos × 2 dias (com ranking em cat45) e uma vitrine com o produto 0.
    coletor.semear(db, produtos=3, dias=2)
    fem = db.scalar(select(Categoria).where(Categoria.rede_categoria_id == "cat45"))
    moda = db.scalar(select(Categoria).where(Categoria.rede_categoria_id == "cat1"))
    _config(client, ligado, p1["id"], [str(fem.id)])
    _config(client, ligado, p2["id"], [str(moda.id)])  # a união: cat45 e cat1 (cat1 contém cat45)
    tid = coletor.tarefa(db, "vitrine", "vitrine", "https://exemplo.test/shop/showcase", HOJE,
                         nivel=1, fonte="affiliate", reservar=True)
    coletor.abrir()
    r = coletor.itens([coletor.item(tid, {"itens": [
        {"redeProdutoId": coletor.produto_id(0), "urlCanonica": coletor.url_produto(0),
         "titulo": "Produto 0", "imagemSha": None}]}, HOJE)])
    assert r["resultados"][0]["status"] == "gravado", r
    coletor.fechar()
    # Link manual no perfil B: produto novo no lago.
    r = client.post(f"/api/perfis/{p2['id']}/mercado/interesses", headers=ligado,
                    json={"url": "https://exemplo.test/shop/pdp/x/7400000000000000001"})
    assert r.status_code == 201, r.text
    antes = _contagens(db)

    trilha.rodar(db, AGORA)
    db.commit()
    db.expire_all()

    # Vitrine: interesse com perfil nulo, visível nos dois perfis.
    vit = db.scalars(select(Interesse).where(Interesse.origem == "vitrine")).all()
    assert len(vit) == 1 and vit[0].perfil_id is None
    for p in (p1, p2):
        lista = client.get(f"/api/perfis/{p['id']}/mercado/interesses", headers=ligado).json()
        assert any(i["todosOsPerfis"] for i in lista["itens"])
    # Rankings de hoje viram interesses `ranking` nos perfis cujas categorias (com descendentes)
    # incluem cat45: os dois.
    rk = db.scalars(select(Interesse).where(Interesse.origem == "ranking")).all()
    assert {str(i.perfil_id) for i in rk} == {p1["id"], p2["id"]}
    # A fila: nível 1 tem o manual (produto novo, 2/dia) e a vitrine; nível 3 os rankings da união
    # (cat45 e cat1, por tipo); nenhuma tarefa de produto repetida.
    fila = _fila_hoje(db)
    assert fila, "a fila do dia nasceu"
    por_nivel = {}
    for t in fila:
        por_nivel.setdefault(t.nivel, []).append(t)
    chaves_n1 = {t.chave for t in por_nivel.get(1, [])}
    assert "produto:7400000000000000001" in chaves_n1
    manual = next(t for t in por_nivel[1] if t.chave == "produto:7400000000000000001")
    assert manual.perfil_id is not None and manual.turno is not None  # 2 por dia → turno
    rankings = {t.chave for t in por_nivel.get(3, [])}
    assert any(c.startswith("ranking:cat45:") for c in rankings)
    assert any(c.startswith("ranking:cat1:") for c in rankings)
    chaves = [(t.tipo, t.chave, t.turno) for t in fila]
    assert len(chaves) == len(set(chaves))
    # Idempotente: rodar de novo não duplica.
    n = len(fila)
    trilha.rodar(db, AGORA)
    db.commit()
    db.expire_all()
    assert len(_fila_hoje(db)) == n
    # Nada apagado.
    depois = _contagens(db)
    assert all(depois[k] >= antes[k] for k in antes)
    assert depois["fotos"] == antes["fotos"]


def test_cadencia_morna_parada_e_reaparece_sem_perder_foto(client, db, ligado, coletor):  # noqa: F811
    coletor.semear(db, produtos=1, dias=1, ranking=False)
    produto = db.scalar(select(Produto).where(Produto.rede_produto_id == coletor.produto_id(0)))
    fotos_antes = db.scalar(select(func.count()).select_from(FotoProduto)
                            .where(FotoProduto.produto_id == produto.id))
    hoje = HOJE
    # Só ranking, há 8 dias; sem interesse: morna, sem apagar nada.
    db.execute(text("UPDATE mercado_produtos SET ultimo_ranking_em = :d, primeira_vez_em = :p "
                    "WHERE id = :id"),
               {"d": hoje - timedelta(days=8), "p": AGORA - timedelta(days=20), "id": produto.id})
    db.commit()
    db.expire_all()
    trilha.recalcular_cadencia(db, "BR", hoje, AGORA)
    db.expire_all()
    produto = db.get(Produto, produto.id)
    assert produto.calor == Calor.morna and produto.fotos_por_dia == 1
    # 31 dias: parada, próxima coleta nula.
    db.execute(text("UPDATE mercado_produtos SET ultimo_ranking_em = :d, primeira_vez_em = :p "
                    "WHERE id = :id"),
               {"d": hoje - timedelta(days=31), "p": AGORA - timedelta(days=40), "id": produto.id})
    db.commit()
    db.expire_all()
    trilha.recalcular_cadencia(db, "BR", hoje, AGORA)
    db.expire_all()
    produto = db.get(Produto, produto.id)
    assert produto.calor == Calor.parada and produto.proxima_coleta_em is None
    # Reaparece hoje no ranking: quente no mesmo dia (SC-005), com as fotos intactas.
    db.execute(text("UPDATE mercado_produtos SET ultimo_ranking_em = :d WHERE id = :id"),
               {"d": hoje, "id": produto.id})
    db.commit()
    db.expire_all()
    trilha.recalcular_cadencia(db, "BR", hoje, AGORA)
    db.expire_all()
    produto = db.get(Produto, produto.id)
    assert produto.calor == Calor.quente and produto.proxima_coleta_em is not None
    assert db.scalar(select(func.count()).select_from(FotoProduto)
                     .where(FotoProduto.produto_id == produto.id)) == fotos_antes


def test_relacionados_ate_o_limite_com_uma_notificacao_por_dia(client, db, ligado, coletor):  # noqa: F811
    perfil = criar_perfil(client, ligado)
    coletor.semear(db, produtos=4, dias=1, ranking=False)  # 4 produtos novos da Loja X
    loja_id = db.scalar(select(Loja.id).where(Loja.rede_loja_id == "loja123"))
    cfg = _config(client, ligado, perfil["id"], [])  # maxRelacionadosDia = 2
    r = client.post(f"/api/perfis/{perfil['id']}/mercado/lojas/{loja_id}/seguir", headers=ligado,
                    json={"version": cfg["version"]})
    assert r.status_code == 200, r.text
    trilha.rodar(db, AGORA)
    db.commit()
    db.expire_all()
    auto = db.scalars(select(Interesse).where(Interesse.origem == "loja")).all()
    assert len(auto) == 2 and all(str(i.perfil_id) == perfil["id"] for i in auto)
    assert all(i.motivo["lojaId"] == str(loja_id) for i in auto)
    notas = db.scalars(select(Notificacao).where(Notificacao.tipo == "mercado_interesse_auto")).all()
    assert len(notas) == 1 and perfil["name"] in notas[0].titulo
    # Outra volta no mesmo dia: nada a mais (limite) e sem outra notificação.
    trilha.rodar(db, AGORA)
    db.commit()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Interesse)
                     .where(Interesse.origem == "loja")) == 2
    assert db.scalar(select(func.count()).select_from(Notificacao)
                     .where(Notificacao.tipo == "mercado_interesse_auto")) == 1
    cfg = client.get(f"/api/perfis/{perfil['id']}/mercado/config", headers=ligado).json()
    assert cfg["relacionadosHoje"] == 2


def test_reservas_expiradas_batimento_e_parada(client, db, ligado, coletor):  # noqa: F811
    # O relógio do teste é o de agora (não o do import do módulo): os `now()` do banco abaixo
    # precisam ficar atrás dele mesmo quando a suíte inteira roda por minutos antes deste teste.
    agora = datetime.now(UTC)
    hoje = agora.astimezone(SP).date()
    # Uma tarefa reservada com lease vencido e outra viva de ontem.
    t1 = coletor.tarefa(db, "produto", "produto:1", "https://exemplo.test/p/1", hoje, reservar=True)
    t2 = coletor.tarefa(db, "produto", "produto:2", "https://exemplo.test/p/2",
                        hoje - timedelta(days=1))
    db.execute(text("UPDATE mercado_fila SET reservada_ate = now() - interval '1 minute' "
                    "WHERE id = :id"), {"id": t1})
    # Uma rodada ativa sem batimento há 15 min.
    coletor.abrir()
    db.execute(text("UPDATE mercado_coletas SET batimento_em = now() - interval '15 minutes'"))
    db.commit()
    trilha.rodar(db, agora)
    db.commit()
    db.expire_all()
    assert db.get(Tarefa, uuid.UUID(t1)).estado == FilaEstado.pendente
    assert db.get(Tarefa, uuid.UUID(t1)).tentativas == 1
    assert db.get(Tarefa, uuid.UUID(t2)).estado == FilaEstado.expirada
    rodada = db.scalar(select(Coleta))
    assert rodada.estado == ColetaEstado.interrompida and rodada.terminada_em is not None
    # Nenhuma linha sumiu.
    assert db.scalar(select(func.count()).select_from(Tarefa)) >= 2
    # Coleta parada: ligada e nada gravado há 48 h (a config foi ligada "há 3 dias").
    db.execute(text("UPDATE coleta_config SET updated_at = now() - interval '3 days', "
                    "risco_aceito_em = now() - interval '3 days'"))
    db.commit()
    trilha.rodar(db, agora)
    db.commit()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Notificacao)
                     .where(Notificacao.tipo == "coleta_parada")) >= 1
    # De novo no mesmo dia: a mesma notificação (dedupe por dia).
    trilha.rodar(db, agora)
    db.commit()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Notificacao)
                     .where(Notificacao.tipo == "coleta_parada")) == 1


def test_trilha_ociosa_com_servidor_desligado(client, db, dono, coleta_habilitada):  # noqa: F811
    _, h = dono
    ligar_coleta(client, h, coleta_habilitada)
    criar_perfil(client, h)
    coleta_habilitada(False)
    assert trilha.ociosa() is not None
    trilha.rodar(db, AGORA)
    assert db.scalar(select(func.count()).select_from(Tarefa)) == 0
    coleta_habilitada(True)
    assert trilha.ociosa() is None
