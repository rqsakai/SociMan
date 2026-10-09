"""Aba Público (spec 022, US3 e US4; research R9): os dados de público importados do TikTok Studio.

Por conta do filtro (na ordem de `ordem-contas`, nunca somando contas diferentes, FR-022):
- **Gênero e territórios:** a foto válida (a de maior data até o fim do período, mesmo que de antes
  do início: `anteriorAoPeriodo`) e a comparação em p.p. com a foto válida no fim do período
  anterior, quando é outra data (FR-016, resposta A). Rótulos `novo`/`saiu`; nos territórios,
  `outrosPct = 100 − Σ`. `seguidoresNaData` é o total da 020 no dia anterior à foto.
- **Atividade:** o mapa dia da semana × hora com a média dos dias do período que têm dado, e o n
  (FR-017, resposta A); `amostraPequena` com 0 < n < `MIN_DIAS_CELULA`. O dia da semana é o do dia
  do arquivo e a hora é a que veio (R13).
- **Espectadores:** a série diária (o "sem dado" fica nulo, nunca zero), os novos somados e as
  médias diárias de total e de recorrentes, cada um com o período anterior (019).
- **Motivos** do card vazio (FR-026): `sem_importacao`, `veio_vazia` ou `sem_dado_no_periodo`.

Só leitura: importa `metricas.studio.efetivo`, nunca o contrário.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, schemas
from sociman_api.analytics.filtros import Filtro, Periodo
from sociman_api.metricas.studio import efetivo
from sociman_api.metricas.studio.publico import rotulo_exibicao
from sociman_api.perfis.models import Conta

MIN_DIAS_CELULA = 2  # FR-025
SECOES = ("genero", "territorios", "atividade", "espectadores")


# ---- contas ----

def contas(db: Session, filtro: Filtro) -> list[tuple[base.SerieEscopo, schemas.PublicoConta]]:
    """As séries do escopo com a referência da conta, na ordem de `ordem-contas` (as anônimas
    no fim)."""
    ordem = {cid: i for i, cid in enumerate(db.scalars(
        select(Conta.id).order_by(Conta.created_at, Conta.id)))}
    out = []
    for s in base.series_escopo(db, filtro):
        anonima = s.conta_id is None
        out.append((s, schemas.PublicoConta(
            serie_id=None if anonima else s.serie_id, conta_id=s.conta_id, rotulo=s.rotulo,
            ordem=None if anonima else ordem.get(s.conta_id))))
    return sorted(out, key=lambda x: (x[1].ordem is None,
                                      x[1].ordem if x[1].ordem is not None else 0))


# ---- motivos ----

def motivo(estado: efetivo.EstadoSecao, tem_dado: bool) -> schemas.MotivoPublico | None:
    if tem_dado:
        return None
    if estado.veio_vazia:
        return "veio_vazia"
    if estado.sem_importacao:
        return "sem_importacao"
    return "sem_dado_no_periodo"


# ---- gênero e territórios ----

def distribuicao(fotos: Sequence[efetivo.Foto], periodo: Periodo, secao: str,
                 seguidores: dict[date, efetivo.DiaEfetivo]) -> schemas.PublicoDistribuicao | None:
    valida = efetivo.foto_valida(fotos, periodo.ate)
    if valida is None:
        return None
    comp = efetivo.comparacao(fotos, periodo.de, valida)
    itens = []
    for rotulo, pct in valida.itens.items():
        antes = comp.itens.get(rotulo) if comp is not None else None
        marca = "novo" if comp is not None and rotulo not in comp.itens else None
        itens.append(schemas.PublicoItem(
            rotulo=rotulo, rotulo_exibicao=rotulo_exibicao(secao, rotulo), pct=pct,
            pct_comparacao=antes,
            dif_pp=round(pct - antes, 3) if pct is not None and antes is not None else None,
            marca=marca))
    if comp is not None:
        itens += [schemas.PublicoItem(rotulo=rotulo, rotulo_exibicao=rotulo_exibicao(secao, rotulo),
                                      pct=None, pct_comparacao=antes, dif_pp=None, marca="saiu")
                  for rotulo, antes in comp.itens.items() if rotulo not in valida.itens]
    outros = None
    pcts = list(valida.itens.values())
    if secao == "territorios" and pcts and None not in pcts:
        outros = round(max(0.0, 100 - sum(pcts)), 3)  # type: ignore[arg-type]
    vespera = seguidores.get(valida.data_foto - timedelta(days=1))
    return schemas.PublicoDistribuicao(
        data_foto=valida.data_foto, anterior_ao_periodo=valida.data_foto < periodo.de,
        importacao_id=valida.importacao_id,
        data_foto_comparacao=comp.data_foto if comp is not None else None,
        seguidores_na_data=vespera.seguidores.seguidores
        if vespera is not None and vespera.seguidores is not None else None,
        itens=itens, outros_pct=outros)


# ---- atividade ----

def mapa_atividade(por_chave: dict[tuple[date, int], efetivo.ValorAtividade], periodo: Periodo,
                   ultimo: date | None) -> schemas.PublicoAtividade:
    soma: dict[tuple[int, int], int] = {}
    n: dict[tuple[int, int], int] = {}
    dias_com: set[date] = set()
    for (dia, hora), v in por_chave.items():
        if v.ativos is None or not periodo.de <= dia <= periodo.ate:
            continue
        chave = (dia.weekday(), hora)
        soma[chave] = soma.get(chave, 0) + v.ativos
        n[chave] = n.get(chave, 0) + 1
        dias_com.add(dia)
    celulas = []
    for d in range(7):
        for h in range(24):
            k = n.get((d, h), 0)
            celulas.append(schemas.CelulaMapa(
                dia=d, hora=h, valor=round(soma[(d, h)] / k, 1) if k else None, n=k,
                amostra_pequena=0 < k < MIN_DIAS_CELULA))
    return schemas.PublicoAtividade(celulas=celulas, dias_com_dado=len(dias_com),
                                    ultimo_dia_com_dado=ultimo)


def atividades(db: Session, filtro: Filtro,
               refs: Sequence[tuple[base.SerieEscopo, schemas.PublicoConta]] | None = None
               ) -> list[schemas.PublicoAtividadeConta]:
    """O mapa de atividade por conta (a aba Público e o 3º mapa de Quando postar)."""
    refs = contas(db, filtro) if refs is None else refs
    ids = [s.serie_id for s, _ in refs]
    por_serie = efetivo.atividade(db, ids, filtro.atual.de, filtro.atual.ate)
    ultimos = efetivo.ultimo_dia_atividade(db, ids)
    estados = efetivo.vazias(db, ids)
    out = []
    for s, ref in refs:
        mapa = mapa_atividade(por_serie.get(s.serie_id, {}), filtro.atual,
                              ultimos[s.serie_id])
        m = motivo(estados[s.serie_id]["atividade"], mapa.dias_com_dado > 0)
        # sem dado, o mapa vem vazio (168 células) com o `ultimoDiaComDado` para o atalho
        out.append(schemas.PublicoAtividadeConta(conta=ref, atividade=mapa, motivo=m))
    return out


# ---- espectadores ----

def _indicador(atual: list[int], anterior: list[int], soma: bool) -> schemas.PublicoIndicador:
    def valor(vs: list[int]) -> float | None:
        if not vs:
            return None
        return float(sum(vs)) if soma else round(sum(vs) / len(vs), 1)

    v, a = valor(atual), valor(anterior)
    variacao = round((v - a) / a, 4) if v is not None and a else None
    return schemas.PublicoIndicador(valor=v, anterior=a, variacao_pct=variacao, n=len(atual))


def espectadores(atual: dict[date, efetivo.ValorEspectadores],
                 anterior: dict[date, efetivo.ValorEspectadores]
                 ) -> schemas.PublicoEspectadores:
    def vals(por_dia: dict[date, efetivo.ValorEspectadores], campo: str) -> list[int]:
        return [getattr(v, campo) for v in por_dia.values() if getattr(v, campo) is not None]

    serie = [schemas.PublicoDiaEspectadores(dia=d, total=v.total, novos=v.novos,
                                            recorrentes=v.recorrentes)
             for d, v in sorted(atual.items())]
    return schemas.PublicoEspectadores(
        serie=serie,
        novos=_indicador(vals(atual, "novos"), vals(anterior, "novos"), soma=True),
        media_total=_indicador(vals(atual, "total"), vals(anterior, "total"), soma=False),
        media_recorrentes=_indicador(vals(atual, "recorrentes"), vals(anterior, "recorrentes"),
                                     soma=False),
        dias_sem_dado=sum(None in v.numeros() for v in atual.values()))


# ---- a aba ----

def _tem_dado(db: Session, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """As séries com algum dado de público efetivo (para mostrar uma conta anônima)."""
    com: set[uuid.UUID] = set()
    for tipo in ("genero", "territorio"):
        com |= set(efetivo.fotos(db, ids, tipo))
    com |= set(efetivo.atividade(db, ids)) | set(efetivo.espectadores(db, ids))
    return com


def calcular(db: Session, filtro: Filtro, agora: datetime | None = None) -> schemas.PublicoOut:
    refs = contas(db, filtro)
    anonimas = [s.serie_id for s, ref in refs if ref.conta_id is None]
    if anonimas:  # a conta anônima só aparece se tem público
        com = _tem_dado(db, anonimas)
        refs = [(s, ref) for s, ref in refs if ref.conta_id is not None or s.serie_id in com]
    ids = [s.serie_id for s, _ in refs]
    estados = efetivo.vazias(db, ids)
    fotos = {tipo: efetivo.fotos(db, ids, tipo, filtro.atual.ate)
             for tipo in ("genero", "territorio")}
    datas_foto = [f.data_foto for por in fotos.values() for fs in por.values() for f in fs]
    seguidores = efetivo.dias(db, ids, min(datas_foto) - timedelta(days=1),
                              max(datas_foto)) if datas_foto else {}
    esp = efetivo.espectadores(db, ids, filtro.atual.de, filtro.atual.ate)
    esp_ant = efetivo.espectadores(db, ids, filtro.anterior.de, filtro.anterior.ate)
    mapas = atividades(db, filtro, refs)

    out = []
    for (s, ref), ativ in zip(refs, mapas, strict=True):
        sid = s.serie_id
        est = estados[sid]
        dists = {secao: distribuicao(fotos[efetivo.TIPO_DA_SECAO[secao]].get(sid, []),
                                     filtro.atual, secao, seguidores.get(sid, {}))
                 for secao in ("genero", "territorios")}
        e = espectadores(esp.get(sid, {}), esp_ant.get(sid, {}))
        out.append(schemas.PublicoContaOut(
            conta=ref, genero=dists["genero"], territorios=dists["territorios"],
            atividade=ativ.atividade, espectadores=e if e.serie else None,
            motivos=schemas.PublicoMotivos(
                genero=motivo(est["genero"], dists["genero"] is not None),
                territorios=motivo(est["territorios"], dists["territorios"] is not None),
                atividade=ativ.motivo,
                espectadores=motivo(est["espectadores"], bool(e.serie)))))
    return schemas.PublicoOut(contexto=base.contexto(filtro, base.posts(db, filtro, agora=agora)),
                              contas=out)
