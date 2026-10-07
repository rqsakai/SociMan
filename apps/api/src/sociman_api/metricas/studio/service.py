"""Confirmar, desfazer, listar e cobertura (research R5, R6 e R8).

- **Confirmar:** lê a prévia sem consumir (dono e conta), exige `confirmoConta` quando o envio não
  tinha @, consome (`GETDEL`), trava a série (`pg_advisory_xact_lock`) e recusa se a base mudou.
  Seções com o mesmo SHA de uma importação ativa saem do envio; sem nenhuma nova, devolve a
  existente com `gravados = 0` (idempotente). Senão grava a importação e os dias de uma vez (a
  transação da requisição: tudo ou nada) e o histórico `created`, sem nome de arquivo.
- **Desfazer:** a reversão da importação (não há revert genérico nem "refazer"): `ativa` →
  `desfeita`, com autor e data, histórico `updated` com `{acao: "desfeita"}`. Os dias ficam.
- **Público (spec 022, R8):** as seções de público entram na mesma importação (fotos, atividade e
  espectadores, em lote), com o SHA de cada uma, a data da foto e as `secoes_vazias`; `gravados`
  é o total de linhas. Desfazer tira de uso todas as seções juntas.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User
from sociman_api.errors import ApiError
from sociman_api.metricas.models import Serie
from sociman_api.metricas.studio import efetivo, previa, schemas
from sociman_api.metricas.studio.formato import (
    ATIVIDADE,
    ESPECTADORES,
    FOTOS,
    PUBLICO,
    SEGUIDORES,
    VISAO_GERAL,
)
from sociman_api.metricas.studio.models import (
    ENTITY_TYPE,
    SECOES,
    AtividadeStudio,
    DiaStudio,
    EspectadoresStudio,
    FotoDistribuicao,
    Importacao,
    ImportacaoEstado,
)
from sociman_api.perfis.models import Conta
from sociman_api.perfis.schemas import UserRef

SHA = previa.SHA


def travar(db: Session, serie_id: uuid.UUID) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"studio:{serie_id}"})


def importacao_out(db: Session, imp: Importacao, gravados: int = 0) -> schemas.Importacao:
    serie = db.get(Serie, imp.serie_id)
    nomes = {u.id: u.name for u in db.scalars(select(User).where(
        User.id.in_([i for i in (imp.criada_por, imp.desfeita_por) if i is not None])))}

    def ref(uid: uuid.UUID | None) -> UserRef | None:
        return UserRef(id=uid, name=nomes.get(uid, "")) if uid is not None else None

    return schemas.Importacao(
        id=imp.id, conta_id=serie.conta_id if serie else None, serie_id=imp.serie_id,
        version=imp.version, estado=imp.estado.value, secoes=list(imp.secoes),  # type: ignore[arg-type]
        periodo_de=imp.periodo_de, periodo_ate=imp.periodo_ate,
        ano_origem=imp.ano_origem, contagens=imp.contagens,  # type: ignore[arg-type]
        nomes_arquivos=imp.nomes_arquivos, criada_em=imp.criada_em,
        criada_por=ref(imp.criada_por), desfeita_em=imp.desfeita_em,  # type: ignore[arg-type]
        desfeita_por=ref(imp.desfeita_por), gravados=gravados, data_foto=imp.data_foto,
        data_foto_origem=imp.data_foto_origem,  # type: ignore[arg-type]
        secoes_vazias=list(imp.secoes_vazias or []))  # type: ignore[arg-type]


def confirmar(db: Session, actor: Actor, conta: Conta, body: schemas.ConfirmarIn
              ) -> tuple[schemas.Importacao, bool]:
    """(importação, criada?)."""
    estado = previa.ler_estado(body.previa_id, actor, conta)
    if estado.get("exigeConfirmacaoConta") and not body.confirmo_conta:
        raise ApiError(400, "confirmar_conta",
                       f"Marque \"confirmo que este arquivo é de @{conta.handle.lstrip('@')}\" "
                       "para importar um arquivo sem o @ no nome.")
    previa.consumir(body.previa_id)
    serie = previa.serie_viva(db, conta)
    if str(serie.id) != estado["serieId"]:
        raise ApiError(409, "previa_desatualizada", previa.DESATUALIZADA)
    travar(db, serie.id)
    if previa.base(db, serie.id) != estado["base"]:
        raise ApiError(409, "previa_desatualizada", previa.DESATUALIZADA)

    novas: dict[str, dict[str, Any]] = {}
    repetida: Importacao | None = None
    publico = estado.get("publico", {})
    for secao, dados in [*estado["secoes"].items(), *publico.items()]:
        mesma = db.scalar(select(Importacao).where(
            Importacao.serie_id == serie.id, Importacao.estado == ImportacaoEstado.ativa,
            getattr(Importacao, SHA[secao]) == dados["sha"])
            .order_by(Importacao.criada_em, Importacao.id).limit(1))
        if mesma is not None:
            repetida = repetida or mesma
        elif dados.get("linhas") or dados.get("itens"):
            novas[secao] = dados
    if not novas:
        if repetida is not None:
            return importacao_out(db, repetida), False
        raise ApiError(400, "studio_arquivos", "O envio não tem nenhum dia para gravar.",
                       details={"recebidos": 0})

    por_dia: dict[str, dict[str, Any]] = {}
    for secao, dados in novas.items():
        if secao not in (VISAO_GERAL, SEGUIDORES):
            continue
        for linha in dados["linhas"]:
            alvo = por_dia.setdefault(linha["dia"], {})
            alvo.update({k: v for k, v in linha.items() if k != "dia"})
            alvo[f"tem_{secao}"] = True
    fotos = {s: d for s, d in novas.items() if s in FOTOS}
    data_foto = next((date.fromisoformat(d["dataFoto"]) for d in fotos.values()), None)
    origem_foto = next((d["dataFotoOrigem"] for d in fotos.values()), None)
    dias = {date.fromisoformat(d) for d in por_dia} | {
        date.fromisoformat(ln["dia"]) for s in (ATIVIDADE, ESPECTADORES) if s in novas
        for ln in novas[s]["linhas"]} | ({data_foto} if data_foto else set())
    origens = {d["anoOrigem"] for s, d in novas.items() if s not in FOTOS}
    if not origens:  # só fotos (R8)
        origens = {next(iter(fotos.values()))["anoOrigem"]}
    secoes = [s for s in SECOES if s in novas]
    imp = Importacao(
        serie_id=serie.id, secoes=secoes,
        **{SHA[s]: novas[s]["sha"] for s in secoes},
        data_foto=data_foto, data_foto_origem=origem_foto,
        secoes_vazias=[s for s in PUBLICO if s in estado.get("vazias", []) and s not in novas],
        periodo_de=min(dias), periodo_ate=max(dias),
        ano_origem=origens.pop() if len(origens) == 1 else "misto",
        contagens={s: d["contagens"] for s, d in novas.items()},
        nomes_arquivos=estado["nomesArquivos"], criada_por=actor.user_id,
        created_by=actor.user_id, updated_by=actor.user_id)
    db.add(imp)
    db.flush()
    db.add_all(DiaStudio(
        importacao_id=imp.id, serie_id=serie.id, dia=date.fromisoformat(dia),
        tem_visao_geral=bool(v.get("tem_visao_geral")), views=v.get("views"),
        visitas_perfil=v.get("visitas_perfil"), likes=v.get("likes"),
        comments=v.get("comments"), shares=v.get("shares"),
        tem_seguidores=bool(v.get("tem_seguidores")), seguidores=v.get("seguidores"),
        seguidores_dif=v.get("seguidores_dif")) for dia, v in por_dia.items())
    gravados = len(por_dia)
    # público em lote (INSERT … VALUES em lote, sem um objeto por linha: até 24 linhas por dia)
    for secao, dados in fotos.items():
        _inserir(db, FotoDistribuicao, [
            {"importacao_id": imp.id, "serie_id": serie.id,
             "tipo": efetivo.TIPO_DA_SECAO[secao], "data_foto": data_foto,
             "rotulo": i["rotulo"], "pct": i["pct"]} for i in dados["itens"]])
        gravados += len(dados["itens"])
    if ATIVIDADE in novas:
        _inserir(db, AtividadeStudio, [
            {"importacao_id": imp.id, "serie_id": serie.id, "dia": date.fromisoformat(ln["dia"]),
             "hora": ln["hora"], "ativos": ln["ativos"]} for ln in novas[ATIVIDADE]["linhas"]])
        gravados += len(novas[ATIVIDADE]["linhas"])
    if ESPECTADORES in novas:
        _inserir(db, EspectadoresStudio, [
            {"importacao_id": imp.id, "serie_id": serie.id, "dia": date.fromisoformat(ln["dia"]),
             "total": ln["total"], "novos": ln["novos"], "recorrentes": ln["recorrentes"]}
            for ln in novas[ESPECTADORES]["linhas"]])
        gravados += len(novas[ESPECTADORES]["linhas"])
    # sem rótulo, nome de arquivo nem handle (FR-019): só as seções e as contagens; `vazias` e
    # `publico` só quando há (a importação só da 020 grava o mesmo `details` de antes)
    details: dict[str, Any] = {"secoes": imp.secoes, "gravados": gravados}
    if imp.secoes_vazias:
        details["vazias"] = list(imp.secoes_vazias)
    if any(s in novas for s in PUBLICO):
        details["publico"] = {s: novas[s]["contagens"] for s in PUBLICO if s in novas}
    history.record(db, actor, ENTITY_TYPE, imp, "created", None, history.snapshot(imp),
                   details=details)
    db.flush()
    db.refresh(imp)
    return importacao_out(db, imp, gravados), True


def _inserir(db: Session, modelo: Any, linhas: list[dict[str, Any]]) -> None:
    if linhas:
        db.execute(insert(modelo), linhas)


def importacao_or_404(db: Session, importacao_id: uuid.UUID) -> Importacao:
    imp = db.get(Importacao, importacao_id)
    if imp is None:
        raise ApiError(404, "not_found", "Importação não encontrada")
    return imp


def desfazer(db: Session, actor: Actor, importacao_id: uuid.UUID, version: int,
             agora: datetime | None = None) -> schemas.Importacao:
    imp = importacao_or_404(db, importacao_id)
    travar(db, imp.serie_id)
    db.refresh(imp)
    if imp.estado == ImportacaoEstado.desfeita:
        raise ApiError(409, "ja_desfeita", "Esta importação já foi desfeita")
    history.check_version(imp, version, "Esta importação")
    antes = history.snapshot(imp)
    imp.estado = ImportacaoEstado.desfeita
    imp.desfeita_em = agora or datetime.now(UTC)
    imp.desfeita_por = actor.user_id
    imp.updated_by = actor.user_id
    history.record(db, actor, ENTITY_TYPE, imp, "updated", antes, history.snapshot(imp),
                   details={"acao": "desfeita"})
    db.flush()
    return importacao_out(db, imp)


def listar(db: Session, conta: Conta) -> schemas.ImportacoesList:
    """As importações das séries da conta (a viva), mais recentes primeiro, com as desfeitas."""
    imps = db.scalars(select(Importacao).join(Serie, Serie.id == Importacao.serie_id)
                      .where(Serie.conta_id == conta.id)
                      .order_by(Importacao.criada_em.desc(), Importacao.id.desc())).all()
    return schemas.ImportacoesList(items=[importacao_out(db, i) for i in imps])


def _faixas(dias: list[date]) -> list[schemas.Faixa]:
    return [schemas.Faixa(de=a, ate=b) for a, b in efetivo.faixas(dias)]


def cobertura(db: Session, conta: Conta, agora: datetime | None = None) -> schemas.Cobertura:
    """Faixas do Studio efetivo por seção, a coleta, a sobreposição e os buracos (R6)."""
    hoje = (agora or datetime.now(UTC)).astimezone(efetivo.tz()).date()
    serie = db.scalar(select(Serie).where(Serie.conta_id == conta.id,
                                          Serie.anonimizada_em.is_(None)))
    vazia = [schemas.SecaoCobertura(secao=s, faixas=[], sobreposicao=[], buracos=[])
             for s in (VISAO_GERAL, SEGUIDORES)]
    if serie is None:
        return schemas.Cobertura(conta_id=conta.id, hoje=hoje, coleta=None, secoes=vazia,
                                 importacoes_ativas=0)
    primeiro = efetivo.primeiro_dia_coberto(db, [serie.id])[serie.id]
    coleta = schemas.ColetaCobertura(primeiro_dia=primeiro - timedelta(days=1),
                                     primeiro_dia_coberto=primeiro) if primeiro else None
    efetivos = efetivo.dias(db, [serie.id]).get(serie.id, {})
    secoes = []
    for secao in (VISAO_GERAL, SEGUIDORES):
        dias = sorted(d for d, e in efetivos.items()
                      if (e.visao_geral if secao == VISAO_GERAL else e.seguidores) is not None)
        if not dias:
            secoes.append(schemas.SecaoCobertura(secao=secao, faixas=[], sobreposicao=[],
                                                 buracos=[]))
            continue
        presentes = set(dias)
        sobre = [d for d in dias if primeiro is not None and d >= primeiro - timedelta(days=1)]
        limite = primeiro - timedelta(days=1) if primeiro else hoje - timedelta(days=1)
        buracos = [d for d in efetivo.intervalo(dias[0], limite) if d not in presentes] \
            if dias[0] <= limite else []
        secoes.append(schemas.SecaoCobertura(
            secao=secao,
            faixas=[schemas.FaixaFonte(de=a, ate=b, fonte="studio")
                    for a, b in efetivo.faixas(dias)],
            sobreposicao=_faixas(sobre), buracos=_faixas(buracos)))
    ativas = db.scalar(select(func.count()).select_from(Importacao).where(
        Importacao.serie_id == serie.id, Importacao.estado == ImportacaoEstado.ativa)) or 0
    return schemas.Cobertura(conta_id=conta.id, hoje=hoje, coleta=coleta, secoes=secoes,
                             importacoes_ativas=int(ativas),
                             publico=cobertura_publico(db, serie.id))


def _dias_cobertura(dias: list[date]) -> schemas.PublicoDiasCobertura:
    if not dias:
        return schemas.PublicoDiasCobertura()
    presentes = set(dias)
    buracos = [d for d in efetivo.intervalo(min(dias), max(dias)) if d not in presentes]
    return schemas.PublicoDiasCobertura(faixas=_faixas(dias), buracos=_faixas(buracos))


def cobertura_publico(db: Session, serie_id: uuid.UUID) -> schemas.CoberturaPublico:
    """As fotos (datas), as faixas e os buracos da atividade e dos espectadores e as vazias
    (R10), só das importações ativas."""
    fotos = [schemas.PublicoFotoCobertura(tipo=tipo, data_foto=f.data_foto,  # type: ignore[arg-type]
                                          importacao_id=f.importacao_id)
             for tipo in ("genero", "territorio")
             for f in efetivo.fotos(db, [serie_id], tipo).get(serie_id, [])]
    atividade = efetivo.atividade(db, [serie_id]).get(serie_id, {})
    espectadores = efetivo.espectadores(db, [serie_id]).get(serie_id, {})
    estados = efetivo.vazias(db, [serie_id])[serie_id]
    return schemas.CoberturaPublico(
        fotos=sorted(fotos, key=lambda f: (f.data_foto, f.tipo)),
        atividade=_dias_cobertura(sorted({d for d, _ in atividade})),
        espectadores=_dias_cobertura(sorted(espectadores)),
        vazias=[schemas.PublicoVaziaCobertura(secao=s, em=e.vazia_em)  # type: ignore[arg-type]
                for s, e in estados.items() if e.veio_vazia])
