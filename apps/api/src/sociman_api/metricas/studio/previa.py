"""Pré-visualização (research R4; data-model "Estado efêmero" e "Contagens").

Arquivos → formato → datas → conta e @ → contagens contra o valor efetivo → avisos. O resultado
da leitura (poucos KB, sem os arquivos) vai para o Redis em `studio:previa:<uuid>`, por 30 min e
de uso único (`consumir` faz `GETDEL`). Nada vai para o PostgreSQL, o MinIO ou o disco.

A `base` é a impressão da série no momento da leitura (importações ativas com a versão e o 1º
dia coberto): o confirmar recalcula sob o lock da série e recusa se mudou.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User
from sociman_api.errors import ApiError
from sociman_api.metricas.models import Serie
from sociman_api.metricas.studio import arquivos, datas, efetivo, formato, schemas
from sociman_api.metricas.studio.formato import SEGUIDORES, VISAO_GERAL, Leitura, Problema
from sociman_api.metricas.studio.models import Importacao, ImportacaoEstado
from sociman_api.perfis.models import Conta, Perfil, Platform
from sociman_api.redis import get_redis

TTL = timedelta(minutes=30)
CHAVE = "studio:previa:{}"
PROBLEMAS_MAX = 50
AMOSTRA_PONTA = 5
DIVERGENCIA_MAX = 0.30
PERIODO_LONGO_DIAS = 366
CAMPOS = {VISAO_GERAL: ("views", "visitas_perfil", "likes", "comments", "shares"),
          SEGUIDORES: ("seguidores", "seguidores_dif")}
INDISPONIVEL = "Esta pré-visualização já foi usada ou expirou; envie os arquivos de novo"
DESATUALIZADA = "Os dados da conta mudaram desde a pré-visualização; envie os arquivos de novo"


# ---- conta e série ----

def serie_viva(db: Session, conta: Conta) -> Serie:
    serie = None
    if conta.platform == Platform.tiktok:
        serie = db.scalar(select(Serie).where(Serie.conta_id == conta.id,
                                              Serie.anonimizada_em.is_(None)))
    if serie is None:
        raise ApiError(409, "serie_indisponivel",
                       "Esta conta não tem métricas ativas: o histórico do Studio só entra numa "
                       "conta TikTok conectada com métricas.", details={"contaId": str(conta.id)})
    return serie


def conta_or_404(db: Session, conta_id: uuid.UUID) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    return conta


def base(db: Session, serie_id: uuid.UUID) -> dict[str, Any]:
    ativas = db.execute(select(Importacao.id, Importacao.version).where(
        Importacao.serie_id == serie_id, Importacao.estado == ImportacaoEstado.ativa)
        .order_by(Importacao.id)).all()
    primeiro = efetivo.primeiro_dia_coberto(db, [serie_id])[serie_id]
    return {"ativas": [[str(i), v] for i, v in ativas],
            "primeiroDiaCoberto": primeiro.isoformat() if primeiro else None}


# ---- leitura ----

@dataclass
class SecaoLida:
    leitura: Leitura
    arquivo: arquivos.Arquivo
    sha: str
    dias: list[date]  # um por linha, na ordem
    ano_origem: str  # nome_zip | deduzido
    com_ano: bool  # as datas do arquivo já trazem o ano (sem dedução)


def _invalido(problemas: list[Problema]) -> ApiError:
    primeiros = problemas[:PROBLEMAS_MAX]
    linhas = "; ".join(
        f"{p.arquivo}, linha {p.linha}" + (f", {p.coluna}" if p.coluna else "")
        + (f" = \"{p.valor}\"" if p.valor is not None else "") + f": {p.motivo}"
        for p in primeiros[:3])
    mais = f" (e mais {len(problemas) - 3})" if len(problemas) > 3 else ""
    return ApiError(400, "studio_invalido",
                    f"O arquivo tem problemas e não foi importado: {linhas}{mais}.",
                    details={"problemas": [p.json() for p in primeiros],
                             "total": len(problemas)})


def _datas_erro(arquivo: str, motivo: str) -> ApiError:
    return ApiError(400, "studio_datas", f"{arquivo}: {motivo}",
                    details={"arquivo": arquivo, "motivo": motivo})


def _ler_datas(leitura: Leitura, problemas: list[Problema]) -> list[datas.DataLida]:
    lidas: list[datas.DataLida] = []
    for linha in leitura.linhas:
        d = datas.ler_data(linha.dia_bruto)
        if d is None:
            problemas.append(Problema(leitura.arquivo, linha.numero, formato.NOMES["dia"],
                                      linha.dia_bruto, "data inválida"))
        else:
            lidas.append(d)
    if lidas and len({d.ano is None for d in lidas}) > 1:
        problemas.append(Problema(leitura.arquivo, None, formato.NOMES["dia"], None,
                                  "datas com e sem ano no mesmo arquivo"))
    return lidas


def ler(conta: Conta, uploads: list[arquivos.Upload], hoje: date
        ) -> tuple[list[arquivos.Arquivo], dict[str, SecaoLida]]:
    """Lê e valida o envio inteiro (US2). Recusa por `ApiError` antes de qualquer prévia."""
    tz = efetivo.tz()
    enviados = arquivos.ler_envio(uploads)
    lidos = [arquivos.ler_arquivo(e, tz) for e in enviados]
    handle_conta = datas.normalizar_handle(conta.handle)
    for a in lidos:
        if a.handle is not None and a.handle != handle_conta:
            raise ApiError(400, "studio_conta_diferente",
                           f"O arquivo é de @{a.handle}, não de @{handle_conta}.",
                           details={"arquivo": a.nome, "handleArquivo": a.handle,
                                    "handleConta": handle_conta})

    leituras: list[tuple[Leitura, arquivos.Arquivo, str]] = []
    for a in lidos:
        for c in a.csvs:
            leituras.append((formato.ler(a.nome if a.tipo == "csv" else f"{a.nome}/{c.entrada}",
                                         c.dados), a, c.sha))
    secoes = [lt.secao for lt, _, _ in leituras]
    if len(set(secoes)) != len(secoes):
        raise ApiError(400, "studio_arquivos",
                       "A mesma seção veio duas vezes: envie um ZIP da Visão geral e/ou um de "
                       "Seguidores.", details={"recebidos": len(uploads)})

    problemas: list[Problema] = []
    lidas = {lt.secao: _ler_datas(lt, problemas) for lt, _, _ in leituras}
    for lt, _, _ in leituras:
        problemas.extend(lt.problemas)
    if problemas:
        raise _invalido(problemas)

    out: dict[str, SecaoLida] = {}
    for secao in (VISAO_GERAL, SEGUIDORES):  # a visão geral primeiro: ela ancora o ano
        achada = next(((lt, a, sha) for lt, a, sha in leituras if lt.secao == secao), None)
        if achada is None:
            continue
        lt, a, sha = achada
        ds = lidas[secao]
        nome = a.nome_zip
        try:
            if ds[0].ano is not None:
                dias, origem = datas.com_ano(ds), "deduzido"
            elif secao == VISAO_GERAL and nome is not None and nome.secao == VISAO_GERAL:
                dias, origem = datas.pelo_nome(ds, nome.inicio, nome.fim), "nome_zip"  # type: ignore[arg-type]
            else:
                dias, origem = None, "deduzido"
                vg = out.get(VISAO_GERAL)
                if vg is not None and vg.ano_origem == "nome_zip":
                    dias = datas.mesmo_mapa(ds, lidas[VISAO_GERAL], vg.dias)
                    origem = "nome_zip" if dias is not None else "deduzido"
                if dias is None:
                    dias = datas.deduzir(ds, hoje)
        except datas.DatasErro as e:
            raise _datas_erro(lt.arquivo, str(e)) from None
        futuros = [Problema(lt.arquivo, linha.numero, formato.NOMES["dia"], linha.dia_bruto,
                            f"data futura ({dia:%d/%m/%Y})")
                   for linha, dia in zip(lt.linhas, dias, strict=True) if dia > hoje]
        problemas.extend(futuros)
        out[secao] = SecaoLida(lt, a, sha, dias, origem, ds[0].ano is not None)
    if problemas:
        raise _invalido(problemas)
    return lidos, out


# ---- contagens ----

def _numeros(secao: str, valores: dict[str, int | None]) -> tuple:
    return tuple(valores.get(c) for c in CAMPOS[secao])


def _valor_efetivo(secao: str, dia: efetivo.DiaEfetivo | None):
    if dia is None:
        return None
    return dia.visao_geral if secao == VISAO_GERAL else dia.seguidores


def _ja_importada(db: Session, serie_id: uuid.UUID, secao: str, sha: str
                  ) -> schemas.JaImportada | None:
    coluna = Importacao.sha_visao_geral if secao == VISAO_GERAL else Importacao.sha_seguidores
    achada = db.execute(select(Importacao, User.name)
                        .join(User, User.id == Importacao.criada_por)
                        .where(Importacao.serie_id == serie_id,
                               Importacao.estado == ImportacaoEstado.ativa, coluna == sha)
                        .order_by(Importacao.criada_em, Importacao.id)).first()
    if achada is None:
        return None
    imp, nome = achada
    return schemas.JaImportada(importacao_id=imp.id, em=imp.criada_em, por=nome)


def _aviso(codigo: str, mensagem: str, **detalhes: Any) -> schemas.Aviso:
    return schemas.Aviso(codigo=codigo, mensagem=mensagem, detalhes=detalhes or None)  # type: ignore[arg-type]


def montar(db: Session, actor: Actor, conta: Conta, uploads: list[arquivos.Upload],
           agora: datetime | None = None) -> schemas.PreviaStudio:
    agora = agora or datetime.now(UTC)
    hoje = agora.astimezone(efetivo.tz()).date()
    serie = serie_viva(db, conta)
    lidos, secoes = ler(conta, uploads, hoje)
    perfil = db.get(Perfil, conta.perfil_id)

    validos = [d for s in secoes.values() for d in s.dias if d != hoje]
    todos = [d for s in secoes.values() for d in s.dias]
    de, ate = min(validos or todos), max(validos or todos)
    efetivos = efetivo.dias(db, [serie.id], de, ate).get(serie.id, {})
    primeiro = efetivo.primeiro_dia_coberto(db, [serie.id])[serie.id]
    api = efetivo.api_por_dia(db, [serie.id], de, ate)[serie.id] if primeiro else {}

    secoes_out, avisos, guardar = [], [], {}
    for secao, s in secoes.items():
        cont = {"gravados": 0, "iguais": 0, "divergentes": 0, "coletados": 0}
        ignorados, amostra, linhas = [], [], []
        studio_soma = api_soma = 0
        for linha, dia in zip(s.leitura.linhas, s.dias, strict=True):
            numeros = _numeros(secao, linha.valores)
            if dia == hoje:
                situacao = "ignorado"
                ignorados.append(dia)
            else:
                cont["gravados"] += 1
                linhas.append({"dia": dia.isoformat(),
                               **{c: linha.valores.get(c) for c in CAMPOS[secao]}})
                atual = _valor_efetivo(secao, efetivos.get(dia))
                if efetivo.coberto(dia, primeiro):
                    situacao = "coletado"
                    cont["coletados"] += 1
                    d_api = api.get(dia)
                    if secao == VISAO_GERAL and d_api is not None and d_api.tem_dado:
                        studio_soma += numeros[0]
                        api_soma += d_api.views
                    elif secao == SEGUIDORES and d_api is not None \
                            and d_api.seguidores_fim is not None:
                        studio_soma += numeros[0]
                        api_soma += d_api.seguidores_fim
                elif atual is not None:
                    igual = atual.numeros() == numeros
                    situacao = "igual" if igual else "divergente"
                    cont["iguais" if igual else "divergentes"] += 1
                else:
                    situacao = "novo"
            amostra.append(schemas.LinhaAmostra(dia=dia, situacao=situacao,
                                                **dict(zip(CAMPOS[secao], numeros,
                                                           strict=True))))
        presentes = set(s.dias)
        faltando = [d for d in efetivo.intervalo(s.dias[0], s.dias[-1]) if d not in presentes]
        if len(amostra) > 2 * AMOSTRA_PONTA:
            amostra = amostra[:AMOSTRA_PONTA] + amostra[-AMOSTRA_PONTA:]
        gravaveis = [ln for ln, d in zip(s.leitura.linhas, s.dias, strict=True) if d != hoje]
        if secao == VISAO_GERAL:
            def soma(campo: str, ls=gravaveis) -> int | None:
                vs = [ln.valores.get(campo) for ln in ls]
                return sum(v for v in vs if v is not None) \
                    if any(v is not None for v in vs) else None
            totais: Any = schemas.TotaisVisaoGeral(
                views=soma("views") or 0, visitas_perfil=soma("visitas_perfil"),
                likes=soma("likes"), comments=soma("comments"), shares=soma("shares"))
        else:
            seg = [ln.valores["seguidores"] or 0 for ln in gravaveis] or [0]
            totais = schemas.TotaisSeguidores(seguidores_inicio=seg[0], seguidores_fim=seg[-1],
                                              ganhos=seg[-1] - seg[0])
        ja = _ja_importada(db, serie.id, secao, s.sha)
        contagens = schemas.ContagensPrevia(**cont, faltando=faltando, ignorados=ignorados)
        secoes_out.append(schemas.SecaoPrevia(
            secao=secao, ja_importada=ja, contagens=contagens, totais=totais,
            colunas=schemas.Colunas(reconhecidas=s.leitura.reconhecidas,
                                    ausentes=s.leitura.ausentes,
                                    ignoradas=s.leitura.ignoradas),
            amostra=amostra))
        guardar[secao] = {"sha": s.sha, "anoOrigem": s.ano_origem, "linhas": linhas,
                          "contagens": {**cont, "faltando": len(faltando),
                                        "ignorados": len(ignorados)}}

        rotulo = "Visão geral" if secao == VISAO_GERAL else "Seguidores"
        if api_soma and abs(studio_soma - api_soma) / api_soma > DIVERGENCIA_MAX:
            pct = round(abs(studio_soma - api_soma) / api_soma, 4)
            avisos.append(_aviso(
                "diverge_da_coleta",
                f"{rotulo}: os números não batem com a coleta ({pct:.0%} de diferença nos dias "
                f"em comum); confira se o arquivo é desta conta.",
                secao=secao, diferencaPct=pct, studio=studio_soma, coleta=api_soma))
        if ignorados:
            avisos.append(_aviso("dia_incompleto",
                                 f"{rotulo}: o dia de hoje ({hoje:%d/%m}) está incompleto e "
                                 "não será gravado.", secao=secao))
        if faltando:
            lista = ", ".join(f"{d:%d/%m}" for d in faltando[:10])
            avisos.append(_aviso("dias_faltando",
                                 f"{rotulo}: faltam {len(faltando)} dias no arquivo: {lista}"
                                 + ("…" if len(faltando) > 10 else "") + ".",
                                 secao=secao, dias=len(faltando)))
        if s.ano_origem == "deduzido" and not s.com_ano:
            avisos.append(_aviso("ano_deduzido",
                                 f"{rotulo}: o arquivo não traz o ano, e ele foi deduzido "
                                 f"({s.dias[0]:%d/%m/%Y} a {s.dias[-1]:%d/%m/%Y}); confira o "
                                 "período.", secao=secao))
        if s.leitura.ausentes:
            avisos.append(_aviso("colunas_ausentes",
                                 f"{rotulo}: sem as colunas {', '.join(s.leitura.ausentes)}; "
                                 "esses valores ficam sem dado.", secao=secao,
                                 colunas=s.leitura.ausentes))
        if s.leitura.provisorio:
            avisos.append(_aviso("cabecalho_provisorio",
                                 f"{rotulo}: o cabeçalho em português ainda não foi conferido "
                                 "com um arquivo real; confira os números na amostra.",
                                 secao=secao))
    if (ate - de).days + 1 > PERIODO_LONGO_DIAS:
        avisos.append(_aviso("periodo_longo",
                             f"O período tem {(ate - de).days + 1} dias (mais de um ano).",
                             dias=(ate - de).days + 1))

    origens = {s.ano_origem for s in secoes.values()}
    ano_origem = origens.pop() if len(origens) == 1 else "misto"
    exige = any(a.handle is None for a in lidos)
    novas = [x for x in secoes_out if x.ja_importada is None and x.contagens.gravados]
    previa_id = uuid.uuid4()
    estado = {
        "userId": str(actor.user_id), "contaId": str(conta.id), "serieId": str(serie.id),
        "criadaEm": agora.isoformat(), "exigeConfirmacaoConta": exige, "anoOrigem": ano_origem,
        "secoes": guardar, "nomesArquivos": [a.nome for a in lidos],
        "base": base(db, serie.id),
    }
    get_redis().set(CHAVE.format(previa_id), json.dumps(estado), ex=int(TTL.total_seconds()))
    return schemas.PreviaStudio(
        previa_id=previa_id, expira_em=agora + TTL,
        conta=schemas.ContaPrevia(id=conta.id, handle=datas.normalizar_handle(conta.handle),
                                  perfil=perfil.name if perfil else ""),
        arquivos=[schemas.ArquivoPrevia(nome=a.nome, tipo=a.tipo,  # type: ignore[arg-type]
                                        secao=s.leitura.secao, handle=a.handle,  # type: ignore[arg-type]
                                        ignorados=a.ignorados)
                  for a in lidos for s in secoes.values() if s.arquivo is a],
        periodo=schemas.PeriodoPrevia(de=de, ate=ate, ano_origem=ano_origem),  # type: ignore[arg-type]
        secoes=secoes_out, avisos=avisos, exige_confirmacao_conta=exige,
        pode_confirmar=bool(novas))


# ---- consumo (confirmar) ----

def ler_estado(previa_id: uuid.UUID, actor: Actor, conta: Conta) -> dict[str, Any]:
    """O estado guardado, sem consumir: 410 se não existe ou é de outro dono ou conta (sem
    apagar a prévia dos outros)."""
    bruto = get_redis().get(CHAVE.format(previa_id))
    if not bruto:
        raise ApiError(410, "previa_indisponivel", INDISPONIVEL)
    estado = json.loads(bruto)
    if estado.get("userId") != str(actor.user_id) or estado.get("contaId") != str(conta.id):
        raise ApiError(410, "previa_indisponivel", INDISPONIVEL)
    return estado


def consumir(previa_id: uuid.UUID) -> None:
    """Uso único: só quem apaga a chave segue (o 2º clique recebe 410)."""
    if not get_redis().getdel(CHAVE.format(previa_id)):
        raise ApiError(410, "previa_indisponivel", INDISPONIVEL)
